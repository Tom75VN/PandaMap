"""Measure PandaMap HD art against the client's own world map, as drawn in game.

Reference: the native Interface\\WorldMap tiles and overlays read from the
client MPQs (highest patch first) and placed with the client's
WorldMapOverlay.dbc geometry. PandaMap side: the HD base tiles with the
TILE_TRANSFORMS of pandaMap.lua, and the HD overlays with the geometry from
MapOverlayData.lua and the OVERLAY_TRANSFORMS, using the 1.12
WorldMapFrame_Update piece layout and texture coordinates.

Every residual is in map units (1002 x 668 plane). Requires: numpy,
opencv-python-headless, pillow, mpyq.

    python audit_native_alignment.py [Map ...] [--csv out.csv]
"""

from __future__ import annotations

import argparse
import csv
import io
import math
import re
import struct
from pathlib import Path

import cv2
import mpyq
import numpy as np
from PIL import Image

ADDON = Path(__file__).resolve().parent
PACKS = ADDON / "Packs"
DATA = ADDON.parents[2] / "Data"
ARCHIVES = ["patch-5.mpq", "patch-4.mpq", "patch-3.mpq", "patch-2.mpq",
            "patch-1.mpq", "patch.MPQ", "interface.MPQ", "dbc.MPQ"]
SCALE = 2
PREFIXED = {"BlastedLands": {"altarofstorms"}, "BurningSteppes": {"altarofstorms"},
            "DunMorogh": {"ironforge"}, "EasternPlaguelands": {"thondrorilriver"},
            "Elwynn": {"stormwind"}, "Mulgore": {"thunderbluff"},
            "WesternPlaguelands": {"thondrorilriver"}}
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


def parse_dbc(data: bytes):
    _, count, fields, size, _ = struct.unpack("<4s4I", data[:20])
    rows = [struct.unpack("<%dI" % fields, data[20 + i * size:20 + (i + 1) * size])
            for i in range(count)]
    strings = data[20 + count * size:]
    return rows, lambda o: strings[o:strings.index(b"\0", o)].decode("latin-1")


def client_overlays() -> dict[str, dict[str, tuple[int, int, int, int]]]:
    areas, area_name = parse_dbc(read_client("DBFilesClient\\WorldMapArea.dbc"))
    names = {row[0]: area_name(row[3]) for row in areas}
    rows, name = parse_dbc(read_client("DBFilesClient\\WorldMapOverlay.dbc"))
    result: dict[str, dict] = {}
    for row in rows:
        if name(row[8]):
            result.setdefault(names.get(row[1], ""), {})[name(row[8]).upper()] = row[9:13]
    return result


def shipped_overlays() -> dict[str, list[tuple]]:
    text = (ADDON / "MapOverlayData.lua").read_text(encoding="utf-8")
    result = {}
    for block in re.finditer(r"^  (\w+) = \{(.*?)^  \},", text, re.M | re.S):
        result[block.group(1)] = [
            (entry.split(":")[0],) + tuple(int(v) for v in entry.split(":")[1:])
            for entry in re.findall(r'"([^"]+)"', block.group(2))]
    return result


def lua_transforms(table: str) -> dict[str, tuple[float, ...]]:
    text = (ADDON / "pandaMap.lua").read_text(encoding="utf-8")
    body = re.search(r"local %s = \{(.*?)^\}" % table, text, re.M | re.S).group(1)
    result = {}
    for key, values in re.findall(r"(\w+) = \{([^}]*)\}", body):
        result[key] = tuple(float(v) for v in values.split(","))
    return result


def lua_aliases(table: str, source: dict) -> dict:
    text = (ADDON / "pandaMap.lua").read_text(encoding="utf-8")
    body = re.search(r"local %s = \{(.*?)^\}" % table, text, re.M | re.S).group(1)
    result = lua_transforms(table)
    for key, other in re.findall(r"(\w+) = TILE_TRANSFORMS\.(\w+)", body):
        result[key] = source[other]
    return result


def rgba(data) -> np.ndarray | None:
    """Decoded texture, or None for the few palette BLPs Pillow cannot read."""
    try:
        image = Image.open(io.BytesIO(data) if isinstance(data, bytes) else data)
        image.load()
    except OSError:
        return None
    return np.asarray(image.convert("RGBA")).astype(np.float32)


def file_dimension(pixels: int) -> int:
    size = 16
    while size < pixels:
        size *= 2
    return size


def draw_overlay(canvas, geometry, piece):
    """Draw one overlay the way WorldMapFrame_Update does."""
    width, height, x, y = geometry
    columns, rows = math.ceil(width / 256), math.ceil(height / 256)
    for j in range(rows):
        for k in range(columns):
            pw = 256 if k < columns - 1 else (width % 256 or 256)
            ph = 256 if j < rows - 1 else (height % 256 or 256)
            fw = 256 if k < columns - 1 else file_dimension(pw)
            fh = 256 if j < rows - 1 else file_dimension(ph)
            image = piece(j * columns + k + 1)
            if image is None:
                continue
            h, w = image.shape[:2]
            crop = image[:max(1, round(ph / fh * h)), :max(1, round(pw / fw * w))]
            crop = cv2.resize(crop, (pw * SCALE, ph * SCALE), interpolation=cv2.INTER_LINEAR)
            x0, y0 = (x + 256 * k) * SCALE, (y + 256 * j) * SCALE
            region = canvas[y0:y0 + crop.shape[0], x0:x0 + crop.shape[1]]
            crop = crop[:region.shape[0], :region.shape[1]]
            alpha = crop[..., 3:4] / 255.0
            region[..., :3] = crop[..., :3] * alpha + region[..., :3] * (1 - alpha)
            region[..., 3] = np.maximum(region[..., 3], crop[..., 3])


def transformed(canvas, transform):
    if not transform:
        return canvas
    sx, sy, tx, ty = transform
    matrix = np.float32([[sx, 0, tx * SCALE], [0, sy, ty * SCALE]])
    return cv2.warpAffine(canvas, matrix, (canvas.shape[1], canvas.shape[0]),
                          flags=cv2.INTER_LINEAR)


def blank():
    return np.zeros((668 * SCALE + 600, 1002 * SCALE + 600, 4), np.float32)


def gray(image):
    return cv2.GaussianBlur(cv2.cvtColor(np.ascontiguousarray(image[..., :3]),
                                         cv2.COLOR_RGB2GRAY), (0, 0), 1.0)


def residual(native, panda, rect, mask=None):
    """Translation (map units) from the native art to PandaMap's at rect."""
    x0, y0, x1, y1 = [max(0, v) for v in rect]
    a, b = gray(native[y0:y1, x0:x1]), gray(panda[y0:y1, x0:x1])
    if mask is None:
        mask = (native[y0:y1, x0:x1, 3] > 200) & (panda[y0:y1, x0:x1, 3] > 200)
        mask = cv2.erode(mask.astype(np.uint8), np.ones((9, 9), np.uint8))
    if mask.sum() < 400:
        return None
    best = None
    for start in ((0, 0), (8, 8), (-8, -8)):
        warp = np.float32([[1, 0, start[0]], [0, 1, start[1]]])
        try:
            score, warp = cv2.findTransformECC(
                a, b, warp, cv2.MOTION_TRANSLATION,
                (cv2.TERM_CRITERIA_EPS | cv2.TERM_CRITERIA_COUNT, 300, 1e-6), mask, 5)
        except cv2.error:
            continue
        if best is None or score > best[0]:
            best = (float(score), warp[0, 2] / SCALE, warp[1, 2] / SCALE)
    return best


def base_canvas(read_tile, size):
    canvas = blank()
    for i in range(1, 13):
        tile = read_tile(i)
        if tile is None:
            return None
        if tile.shape[0] != size:
            tile = cv2.resize(tile, (size, size), interpolation=cv2.INTER_CUBIC)
        x0, y0 = ((i - 1) % 4) * size, ((i - 1) // 4) * size
        canvas[y0:y0 + size, x0:x0 + size] = tile
    return canvas


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("maps", nargs="*")
    parser.add_argument("--csv", type=Path)
    args = parser.parse_args()
    client, shipped = client_overlays(), shipped_overlays()
    lua = (ADDON / "pandaMap.lua").read_text(encoding="utf-8")
    unexplored = set(re.findall(r"(\w+) = true", re.search(
        r"local UNEXPLORED_BASE_MAPS = \{(.*?)^\}", lua, re.M | re.S).group(1)))
    tiles = lua_transforms("TILE_TRANSFORMS")
    overlays = lua_aliases("OVERLAY_TRANSFORMS", tiles)
    rows = []
    for zone in sorted(shipped):
        if args.maps and zone not in args.maps:
            continue
        folder = PACKS / "PandaMap_World" / ("Battlegrounds" if zone == "AlteracValley" else "World") / zone
        if not folder.is_dir():
            continue
        files = {p.stem.lower(): p for p in folder.glob("*.blp")}
        stem = zone + "_Unexplored" if zone in unexplored else zone
        tile_folder = (PACKS / "PandaMap_Unexplored" / "World_Unexplored" / zone
                       if zone in unexplored else folder)

        native_base = base_canvas(lambda i: (lambda d: None if d is None else rgba(d))(
            read_client("Interface\\WorldMap\\%s\\%s%d.blp" % (zone, zone, i))), 256 * SCALE)
        panda_base = base_canvas(lambda i: (lambda p: rgba(p) if p.exists() else None)(
            tile_folder / ("%s%d.blp" % (stem, i))), 256 * SCALE)
        if native_base is not None and panda_base is not None:
            panda_base = transformed(panda_base, tiles.get(stem))
            mask = np.zeros(native_base.shape[:2], np.uint8)
            mask[40:668 * SCALE - 40, 40:1002 * SCALE - 40] = 1
            fit = residual(native_base, panda_base, (0, 0, native_base.shape[1], native_base.shape[0]), mask)
            if fit:
                rows.append((zone, "(base)", fit[0], fit[1], fit[2]))

        for name, *geometry in shipped[zone]:
            native_geometry = client.get(zone, {}).get(name)
            if not native_geometry:
                continue

            def native_piece(n, name=name):
                data = read_client("Interface\\WorldMap\\%s\\%s%d.blp" % (zone, name, n))
                return None if data is None else rgba(data)

            def hd_piece(n, name=name):
                path = None
                if name.lower() in PREFIXED.get(zone, ()):
                    path = files.get((zone + name + str(n)).lower())
                path = path or files.get((name + str(n)).lower())
                return None if path is None else rgba(path)

            native, panda = blank(), blank()
            draw_overlay(native, native_geometry, native_piece)
            draw_overlay(panda, tuple(geometry), hd_piece)
            panda = transformed(panda, overlays.get(zone))
            w, h, x, y = native_geometry
            fit = residual(native, panda, (x * SCALE, y * SCALE, (x + w) * SCALE, (y + h) * SCALE))
            if fit:
                rows.append((zone, name, fit[0], fit[1], fit[2]))

        mine = [r for r in rows if r[0] == zone]
        if mine:
            dist = [math.hypot(r[3], r[4]) for r in mine]
            base = next((r for r in mine if r[1] == "(base)"), None)
            print("%-20s overlays=%2d median=%.2f max=%.2f%s" % (
                zone, len(mine) - (1 if base else 0), float(np.median(dist)), max(dist),
                "  base=(%.2f,%.2f)" % (base[3], base[4]) if base else ""), flush=True)
    if args.csv:
        with args.csv.open("w", newline="", encoding="utf-8") as handle:
            writer = csv.writer(handle)
            writer.writerow(["map", "overlay", "ecc", "dx", "dy"])
            writer.writerows(rows)
    worst = max((math.hypot(r[3], r[4]) for r in rows), default=0.0)
    print("SUMMARY entries=%d worst=%.2f" % (len(rows), worst))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
