"""Build PandaMap_Unexplored base tiles from the HD unexplored zone masters.

For each master <Map>.png the script registers the artwork against the
client's own map (Interface\\WorldMap tiles from the client MPQs), then
resamples the master once, directly into its aligned place on the 4 x 3
grid of 512 px tiles (2004 x 1336 px of map, edge pixels repeated into the
2048 x 1536 canvas). The tiles therefore need no runtime transform. A master
that cannot be registered reliably is placed by plain scaling and reported.

Output: Packs/PandaMap_Unexplored/World_Unexplored/<Map>/<Map>_Unexplored<n>.blp,
BLP2 DXT5 with full mip chain, the same layout as the existing tiles.
Requires: numpy, opencv-python-headless, pillow, mpyq, quicktex.

    python build_unexplored_tiles.py [Map ...] [--source DIR] [--force] [--dry-run]
"""

from __future__ import annotations

import argparse
import io
import math
import struct
from pathlib import Path

import cv2
import mpyq
import numpy as np
import quicktex
import quicktex.s3tc.bc3 as bc3
from PIL import Image

ADDON = Path(__file__).resolve().parent
OUT = ADDON / "Packs" / "PandaMap_Unexplored" / "World_Unexplored"
DATA = ADDON.parents[2] / "Data"
SOURCE = Path(r"D:\Development\unrealMap_data\#Maps\zones_unexplored")
ARCHIVES = ["patch-5.mpq", "patch-4.mpq", "patch-3.mpq", "patch-2.mpq",
            "patch-1.mpq", "patch.MPQ", "interface.MPQ"]
MAP_W, MAP_H = 2004, 1336          # 1002 x 668 map units at 2 px per unit
CANVAS_W, CANVAS_H, TILE = 2048, 1536, 512
MIN_INLIERS = 150
ENCODER_LEVEL = 18                 # quicktex maximum quality
_archives: dict[str, mpyq.MPQArchive] = {}


def read_client(path: str) -> bytes | None:
    for name in ARCHIVES:
        if not (DATA / name).exists():
            continue
        if name not in _archives:
            _archives[name] = mpyq.MPQArchive(str(DATA / name), listfile=False)
        data = _archives[name].read_file(path)
        if data:
            return data
    return None


def native_map(zone: str) -> np.ndarray | None:
    canvas = Image.new("RGB", (1024, 768))
    for i in range(1, 13):
        data = read_client("Interface\\WorldMap\\%s\\%s%d.blp" % (zone, zone, i))
        if data is None:
            return None
        canvas.paste(Image.open(io.BytesIO(data)).convert("RGB"),
                     (((i - 1) % 4) * 256, ((i - 1) // 4) * 256))
    return np.asarray(canvas)[:668, :1002]


def world_base(zone: str) -> np.ndarray | None:
    """The zone's HD explored base as drawn in game (TILE_TRANSFORMS applied)."""
    folder = ADDON / "Packs" / "PandaMap_World" / "World" / zone
    canvas = np.zeros((CANVAS_H, CANVAS_W, 3), np.uint8)
    for i in range(12):
        path = folder / ("%s%d.blp" % (zone, i + 1))
        if not path.exists():
            return None
        row, column = divmod(i, 4)
        canvas[row * TILE:(row + 1) * TILE, column * TILE:(column + 1) * TILE] = \
            np.asarray(Image.open(path).convert("RGB"))
    transform = lua_tile_transforms().get(zone)
    if transform:
        sx, sy, tx, ty = transform
        canvas = cv2.warpAffine(canvas, np.float32([[sx, 0, 2 * tx], [0, sy, 2 * ty]]),
                                (CANVAS_W, CANVAS_H), flags=cv2.INTER_LANCZOS4)
    return np.ascontiguousarray(canvas[:MAP_H, :MAP_W])


def lua_tile_transforms() -> dict[str, tuple[float, ...]]:
    import re
    text = (ADDON / "pandaMap.lua").read_text(encoding="utf-8")
    body = re.search(r"local TILE_TRANSFORMS = \{(.*?)^\}", text, re.M | re.S).group(1)
    return {key: tuple(float(v) for v in values.split(","))
            for key, values in re.findall(r"(\w+) = \{([^}]*)\}", body)}


def register(source: np.ndarray, native: np.ndarray):
    """Fit native_px2 = s * plain_px + t, plain_px being the plainly scaled master."""
    plain = cv2.resize(source, (MAP_W, MAP_H), interpolation=cv2.INTER_AREA)
    reference = native if native.shape[1] == MAP_W else cv2.resize(
        native, (MAP_W, MAP_H), interpolation=cv2.INTER_CUBIC)
    clahe = cv2.createCLAHE(2.0, (8, 8))
    gray = lambda img: clahe.apply(cv2.cvtColor(img, cv2.COLOR_RGB2GRAY))
    sift = cv2.SIFT_create(nfeatures=20000, contrastThreshold=0.01)
    kp, dp = sift.detectAndCompute(gray(plain), None)
    kn, dn = sift.detectAndCompute(gray(reference), None)
    if dp is None or dn is None:
        return None
    matcher = cv2.BFMatcher(cv2.NORM_L2)
    good = lambda pairs: {m.queryIdx: m.trainIdx for m, s in
                          (p for p in pairs if len(p) == 2) if m.distance < 0.8 * s.distance}
    forward, reverse = good(matcher.knnMatch(dp, dn, k=2)), good(matcher.knnMatch(dn, dp, k=2))
    pairs = [(kp[q].pt, kn[t].pt) for q, t in forward.items() if reverse.get(t) == q]
    if len(pairs) < 20:
        return {"inliers": 0}
    p = np.float64([a for a, _ in pairs])
    n = np.float64([b for _, b in pairs])
    matrix, mask = cv2.estimateAffine2D(p, n, method=cv2.RANSAC, ransacReprojThreshold=3.0,
                                        maxIters=20000, confidence=0.999)
    if matrix is None:
        return {"inliers": 0}
    p, n = p[mask.ravel().astype(bool)], n[mask.ravel().astype(bool)]
    keep = np.ones(len(p), bool)
    for _ in range(4):
        sx, tx = np.linalg.lstsq(np.c_[p[keep, 0], np.ones(keep.sum())], n[keep, 0], rcond=None)[0]
        sy, ty = np.linalg.lstsq(np.c_[p[keep, 1], np.ones(keep.sum())], n[keep, 1], rcond=None)[0]
        error = np.hypot(p[:, 0] * sx + tx - n[:, 0], p[:, 1] * sy + ty - n[:, 1])
        keep = error < max(1.5, 2.5 * np.median(error))
    fit = {"inliers": int(keep.sum()), "sx": sx, "sy": sy, "tx": tx, "ty": ty,
           "p90": float(np.percentile(error[keep], 90)) / 2.0}
    fit["dense"] = dense_refine(plain, reference, fit)
    return fit


def edge_map(image: np.ndarray) -> np.ndarray:
    gray = cv2.GaussianBlur(cv2.cvtColor(image, cv2.COLOR_RGB2GRAY).astype(np.float32), (0, 0), 1.5)
    magnitude = np.hypot(cv2.Sobel(gray, cv2.CV_32F, 1, 0), cv2.Sobel(gray, cv2.CV_32F, 0, 1))
    return cv2.GaussianBlur(magnitude, (0, 0), 2.0) / (magnitude.max() + 1e-6)


def dense_refine(plain: np.ndarray, reference: np.ndarray, fit):
    """Independent dense (ECC) estimate of the same scale + offset, seeded by fit."""
    a, b = edge_map(reference), edge_map(plain)
    mask = np.zeros(a.shape, np.uint8)
    mask[80:-80, 80:-80] = 1       # leave out the parchment frame
    # ECC warps reference coords into plain coords: the inverse of fit.
    warp = np.float32([[1 / fit["sx"], 0, -fit["tx"] / fit["sx"]],
                       [0, 1 / fit["sy"], -fit["ty"] / fit["sy"]]])
    try:
        score, warp = cv2.findTransformECC(
            a, b, warp, cv2.MOTION_AFFINE,
            (cv2.TERM_CRITERIA_EPS | cv2.TERM_CRITERIA_COUNT, 200, 1e-7), mask, 5)
    except cv2.error:
        return None
    sx, sy = 1 / float(warp[0, 0]), 1 / float(warp[1, 1])
    return {"score": float(score), "sx": sx, "sy": sy,
            "tx": -float(warp[0, 2]) * sx, "ty": -float(warp[1, 2]) * sy}


def local_residuals(source: np.ndarray, reference: np.ndarray, fit, field=None) -> list[float]:
    """Misalignment (map units) left in each textured 334 px cell after placing."""
    placed = warp_source(source, fit, field, cv2.INTER_LINEAR)[:MAP_H, :MAP_W]
    a, b = edge_map(reference), edge_map(placed)
    result = []
    for y0 in range(0, MAP_H - 333, 334):
        for x0 in range(0, MAP_W - 333, 334):
            ca, cb = a[y0:y0 + 334, x0:x0 + 334], b[y0:y0 + 334, x0:x0 + 334]
            if ca.std() < 0.02 or cb.std() < 0.02:
                continue
            warp = np.eye(2, 3, dtype=np.float32)
            try:
                score, warp = cv2.findTransformECC(
                    ca, cb, warp, cv2.MOTION_TRANSLATION,
                    (cv2.TERM_CRITERIA_EPS | cv2.TERM_CRITERIA_COUNT, 100, 1e-6), None, 5)
            except cv2.error:
                continue
            if score > 0.5:
                result.append(math.hypot(warp[0, 2], warp[1, 2]) / 2)
    return result


def choose(source: np.ndarray, reference: np.ndarray, fit):
    """Pick the placement with the least local misalignment."""
    candidates = [("identity", None)]
    if fit and fit.get("inliers", 0) >= 20:
        candidates.append(("features", fit))
        if fit.get("dense"):
            candidates.append(("dense", fit["dense"]))
    best = None
    for name, candidate in candidates:
        cells = local_residuals(source, reference, candidate)
        if len(cells) < 4:
            continue
        score = (float(np.median(cells)), float(np.percentile(cells, 90)))
        if best is None or score[0] < best[2][0]:
            best = (name, candidate, score, len(cells))
    return best


def disagreement(fit) -> float:
    """Largest distance (map units) between the two estimates over the map."""
    dense = fit.get("dense")
    if not dense:
        return float("inf")
    return max(math.hypot((fit["sx"] - dense["sx"]) * x + fit["tx"] - dense["tx"],
                          (fit["sy"] - dense["sy"]) * y + fit["ty"] - dense["ty"]) / 2
               for x in (0, MAP_W) for y in (0, MAP_H))


def place(source: np.ndarray, fit, interpolation=cv2.INTER_LANCZOS4,
          border=cv2.BORDER_REPLICATE) -> np.ndarray:
    """One resample of the master into the aligned 2048 x 1536 canvas."""
    # plain_px = k * (src_px + 0.5) - 0.5 ; out_px = s * plain_px + t
    matrix = affine_matrix(source.shape, fit).astype(np.float32)
    return cv2.warpAffine(source, matrix, (CANVAS_W, CANVAS_H), flags=interpolation,
                          borderMode=border)


def affine_matrix(shape, fit) -> np.ndarray:
    h, w = shape[:2]
    kx, ky = MAP_W / w, MAP_H / h
    sx, sy, tx, ty = (fit["sx"], fit["sy"], fit["tx"], fit["ty"]) if fit else (1, 1, 0, 0)
    return np.float64([[sx * kx, 0, sx * (0.5 * kx - 0.5) + tx],
                       [0, sy * ky, sy * (0.5 * ky - 0.5) + ty]])


def displacement_field(source: np.ndarray, reference: np.ndarray, fit, field=None):
    """Smooth local correction (canvas px) left after the global placement.

    Patches of 256 px every 96 px are aligned by ECC on edge maps; unreliable
    patches are dropped, the rest is diffused into a smooth field."""
    placed = warp_source(source, fit, field, cv2.INTER_LINEAR)[:MAP_H, :MAP_W]
    a, b = edge_map(reference), edge_map(placed)
    size, step = 256, 96
    ys, xs = list(range(0, MAP_H - size + 1, step)), list(range(0, MAP_W - size + 1, step))
    dx = np.zeros((len(ys), len(xs)), np.float32)
    dy = np.zeros_like(dx)
    weight = np.zeros_like(dx)
    for j, y0 in enumerate(ys):
        for i, x0 in enumerate(xs):
            ca, cb = a[y0:y0 + size, x0:x0 + size], b[y0:y0 + size, x0:x0 + size]
            if ca.std() < 0.03 or cb.std() < 0.03:
                continue
            warp = np.eye(2, 3, dtype=np.float32)
            try:
                score, warp = cv2.findTransformECC(
                    ca, cb, warp, cv2.MOTION_TRANSLATION,
                    (cv2.TERM_CRITERIA_EPS | cv2.TERM_CRITERIA_COUNT, 100, 1e-6), None, 5)
            except cv2.error:
                continue
            if score > 0.6 and math.hypot(warp[0, 2], warp[1, 2]) < 24:
                dx[j, i], dy[j, i], weight[j, i] = warp[0, 2], warp[1, 2], score
    if weight.sum() == 0:
        return field
    # Fill gaps and smooth: normalised Gaussian diffusion of the reliable samples.
    sigma = 1.5
    blur = lambda m: cv2.GaussianBlur(m, (0, 0), sigma, borderType=cv2.BORDER_REPLICATE)
    norm = blur(weight) + 1e-6
    fx, fy = blur(dx * weight) / norm, blur(dy * weight) / norm
    for _ in range(6):      # spread into large empty regions
        empty = blur(weight) < 0.05
        if not empty.any():
            break
        fx = np.where(empty, cv2.GaussianBlur(fx, (0, 0), 3, borderType=cv2.BORDER_REPLICATE), fx)
        fy = np.where(empty, cv2.GaussianBlur(fy, (0, 0), 3, borderType=cv2.BORDER_REPLICATE), fy)
        weight = np.maximum(weight, blur(weight))
    # Patch centres -> every canvas pixel (cubic, clamped at the outer centres).
    yy, xx = np.mgrid[0:CANVAS_H, 0:CANVAS_W].astype(np.float32)
    u = np.clip((xx - size / 2) / step, 0, len(xs) - 1).astype(np.float32)
    v = np.clip((yy - size / 2) / step, 0, len(ys) - 1).astype(np.float32)
    gx = cv2.remap(fx, u, v, cv2.INTER_CUBIC, borderMode=cv2.BORDER_REPLICATE)
    gy = cv2.remap(fy, u, v, cv2.INTER_CUBIC, borderMode=cv2.BORDER_REPLICATE)
    if field is not None:
        gx, gy = gx + field[0], gy + field[1]
    return gx.astype(np.float32), gy.astype(np.float32)


def warp_source(source: np.ndarray, fit, field=None, interpolation=cv2.INTER_LANCZOS4,
                border=cv2.BORDER_REPLICATE) -> np.ndarray:
    """out(x) = source(A^-1 (x + field(x))): one resample of the master."""
    if field is None:
        return place(source, fit, interpolation, border)
    matrix = affine_matrix(source.shape, fit)
    yy, xx = np.mgrid[0:CANVAS_H, 0:CANVAS_W].astype(np.float32)
    px, py = xx + field[0], yy + field[1]
    map_x = ((px - matrix[0, 2]) / matrix[0, 0]).astype(np.float32)
    map_y = ((py - matrix[1, 2]) / matrix[1, 1]).astype(np.float32)
    return cv2.remap(source, map_x, map_y, interpolation, borderMode=border)


def mip_chain(tile: np.ndarray) -> list[np.ndarray]:
    levels = [tile]
    while levels[-1].shape[0] > 1:
        size = levels[-1].shape[0] // 2
        levels.append(cv2.resize(levels[-1], (size, size), interpolation=cv2.INTER_AREA))
    return levels


def encode(level: np.ndarray, encoder) -> bytes:
    size = level.shape[0]
    if size < 4:
        level = cv2.resize(level, (4, 4), interpolation=cv2.INTER_NEAREST)
    raw = quicktex.RawTexture.frombytes(np.ascontiguousarray(level).tobytes(),
                                        level.shape[1], level.shape[0])
    return encoder.encode(raw).tobytes()


def write_blp(path: Path, tile: np.ndarray, encoder) -> None:
    """BLP2, DXT5 (alpha depth 8, alpha type 7), mipmapped, like the shipped tiles."""
    blocks = [encode(level, encoder) for level in mip_chain(tile)]
    blocks.append(blocks[-1])      # the shipped tiles carry the 1x1 level twice
    offsets, sizes, cursor = [], [], 148 + 1024
    for block in blocks:
        offsets.append(cursor)
        sizes.append(len(block))
        cursor += len(block)
    offsets += [0] * (16 - len(offsets))
    sizes += [0] * (16 - len(sizes))
    header = b"BLP2" + struct.pack("<IBBBBII", 1, 2, 8, 7, 1, TILE, TILE)
    header += struct.pack("<16I", *offsets) + struct.pack("<16I", *sizes) + bytes(1024)
    path.write_bytes(header + b"".join(blocks))


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("maps", nargs="*")
    parser.add_argument("--source", type=Path, default=SOURCE)
    parser.add_argument("--force", action="store_true", help="rebuild maps that already exist")
    parser.add_argument("--dry-run", action="store_true", help="register only, write nothing")
    args = parser.parse_args()
    encoder = bc3.BC3Encoder(ENCODER_LEVEL)
    for master in sorted(args.source.glob("*.png")):
        zone = master.stem
        if args.maps and zone not in args.maps:
            continue
        folder = OUT / zone
        if folder.exists() and not args.force and not args.maps:
            print("%-20s skipped (already built)" % zone)
            continue
        source = np.asarray(Image.open(master).convert("RGB"))
        # The HD explored base shares the masters' style and sits on the client
        # map within half a unit; the native map is the fallback reference.
        reference = world_base(zone)
        if reference is None:
            reference = native_map(zone)
        fit = register(source, reference) if reference is not None else None
        best = choose(source, reference, fit) if reference is not None else None
        chosen = best[1] if best else None
        if chosen:
            corners = [math.hypot((chosen["sx"] - 1) * x + chosen["tx"],
                                  (chosen["sy"] - 1) * y + chosen["ty"]) / 2
                       for x in (0, MAP_W) for y in (0, MAP_H)]
            moved = "sx=%.5f sy=%.5f tx=%.2f ty=%.2f (max %.2f units)" % (
                chosen["sx"], chosen["sy"], chosen["tx"] / 2, chosen["ty"] / 2, max(corners))
        else:
            moved = "plain scaling"
        field, local = None, ""
        if best and best[2][1] > 1.0:
            # The master is locally out of shape: add a smooth local warp,
            # kept only if it lowers the measured misalignment.
            candidate = None
            for _ in range(2):
                candidate = displacement_field(source, reference, chosen, candidate)
            cells = local_residuals(source, reference, chosen, candidate)
            if len(cells) >= 4:
                score = (float(np.median(cells)), float(np.percentile(cells, 90)))
                if score[0] <= best[2][0] and score[1] < best[2][1]:
                    field = candidate
                    local = " -> local warp: median %.2f p90 %.2f (max shift %.1f units)" % (
                        score[0], score[1], float(np.hypot(*field)[:MAP_H, :MAP_W].max()) / 2)
                else:
                    local = " (local warp rejected: median %.2f p90 %.2f)" % score
        print("%-20s %dx%d %-8s %s | residual median %s p90 %s over %s cells%s" % (
            zone, source.shape[1], source.shape[0], best[0] if best else "none", moved,
            "%.2f" % best[2][0] if best else "-", "%.2f" % best[2][1] if best else "-",
            best[3] if best else 0, local), flush=True)
        if args.dry_run:
            continue
        canvas = warp_source(source, chosen, field)
        if reference is not None and reference.shape[1] == MAP_W:
            # Fill any map edge the shrunk master no longer covers from the
            # aligned HD explored base, then repeat the edge into the padding.
            covered = warp_source(np.full(source.shape[:2], 255, np.uint8), chosen, field,
                                  cv2.INTER_NEAREST, cv2.BORDER_CONSTANT)
            covered = cv2.erode((covered > 0).astype(np.uint8), np.ones((5, 5), np.uint8))
            area = canvas[:MAP_H, :MAP_W]
            area[covered[:MAP_H, :MAP_W] == 0] = reference[covered[:MAP_H, :MAP_W] == 0]
            canvas = cv2.copyMakeBorder(np.ascontiguousarray(area), 0, CANVAS_H - MAP_H, 0,
                                        CANVAS_W - MAP_W, cv2.BORDER_REPLICATE)
        canvas = cv2.cvtColor(canvas, cv2.COLOR_RGB2RGBA)
        folder.mkdir(parents=True, exist_ok=True)
        for i in range(12):
            row, column = divmod(i, 4)
            tile = canvas[row * TILE:(row + 1) * TILE, column * TILE:(column + 1) * TILE]
            write_blp(folder / ("%s_Unexplored%d.blp" % (zone, i + 1)), tile, encoder)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
