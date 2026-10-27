"""Audit PandaMap runtime tiles against the POI editor's coordinate masters.

The editor maps 0..100 directly over each complete source image. This audit
measures the per-zone source-to-runtime transform needed to reproduce that
same rectangle on the client's native 1002x668 WorldMapButton plane. The Lua
runtime applies its inverse to artwork only; it never changes the marker plane.
"""

from __future__ import annotations

import csv
import math
import re
from pathlib import Path

import cv2
import numpy as np
from PIL import Image


ADDON = Path(__file__).resolve().parent
PANDA_WORLD = ADDON / "Packs" / "PandaMap_World" / "World"
PANDA_UNEXPLORED = ADDON / "Packs" / "PandaMap_Unexplored" / "World_Unexplored"
SOURCE = Path(r"D:\Development\unrealMap_data\#Maps\zones")
MAP_SIZE = (1002, 668)
TILE_SIZE = 512
UNEXPLORED = {"Alterac", "Arathi", "Ashenvale", "Durotar", "Elwynn"}
EXCLUDED = {
    "DeadwindPass": {"karazhan1", "karazhan2", "thevice1", "thevice2",
                     "thevice3", "thevice4"},
}

SOURCE_FILES = {
    "Alterac": "Alterac.png", "Arathi": "arathi.png",
    "Ashenvale": "Ashenvale.png", "Aszhara": "azshara.png",
    "Badlands": "Badlands.png", "Barrens": "Barren.png",
    "BlastedLands": "BlastedLands.png", "BurningSteppes": "BurningSteppes.png",
    "Darkshore": "darkshore.png", "DeadwindPass": "deadwindpass.png",
    "Desolace": "Desolace.png", "DunMorogh": "DunMorogh.png",
    "Durotar": "durotar.png", "Duskwood": "duskwood.png",
    "Dustwallow": "dustwallowmarsh.png", "EasternPlaguelands": "Eastern_Plaguelands.png",
    "Elwynn": "elwynn.png", "Felwood": "felwood.png",
    "Feralas": "Feralas.png", "Hilsbrad": "Hillsbrad.png",
    "Hinterlands": "Hinterlands.png", "LochModan": "LochModan.png",
    "Moonglade": "Moonglade.png", "Mulgore": "mulgore.png",
    "Redridge": "redbridge.png", "SearingGorge": "SearingGorge.png",
    "Silithus": "Silithus.png", "Silverpine": "silverpine.png",
    "StonetalonMountains": "Stonetalon_Mountains.png",
    "Stranglethorn": "Stranglethorn.png", "SwampOfSorrows": "swamp_of_sorrows.png",
    "Tanaris": "Tanaris.png", "Teldrassil": "Teldrassil.png",
    "ThousandNeedles": "Thousandneedles.png", "Tirisfal": "Tirisfal.png",
    "UngoroCrater": "UngoroCrater.png", "WesternPlaguelands": "WesternPlaguelands.png",
    "Westfall": "Westfall.png", "Wetlands": "Wetlands.png",
    "Winterspring": "Winterspring.png",
}


def overlay_geometry() -> dict[str, list[tuple[str, int, int, int, int]]]:
    text = (ADDON / "MapOverlayData.lua").read_text(encoding="utf-8")
    result = {}
    for block in re.finditer(r"^  (\w+) = \{(.*?)^  \},", text, re.MULTILINE | re.DOTALL):
        entries = []
        for encoded in re.findall(r'"([^"]+)"', block.group(2)):
            name, width, height, x, y = encoded.split(":")
            entries.append((name, int(width), int(height), int(x), int(y)))
        result[block.group(1)] = entries
    return result


OVERLAYS = overlay_geometry()


def runtime_map(zone: str) -> Image.Image:
    folder = (PANDA_UNEXPLORED if zone in UNEXPLORED else PANDA_WORLD) / zone
    stem = zone + ("_Unexplored" if zone in UNEXPLORED else "")
    canvas = Image.new("RGBA", (2048, 1536))
    for number in range(1, 13):
        tile = Image.open(folder / f"{stem}{number}.blp").convert("RGBA")
        column = (number - 1) % 4
        row = (number - 1) // 4
        canvas.alpha_composite(tile, (column * TILE_SIZE, row * TILE_SIZE))

    overlay_folder = PANDA_WORLD / zone
    files = {path.stem.lower(): path for path in overlay_folder.glob("*.blp")}
    excluded = EXCLUDED.get(zone, set())
    for overlay, width, height, offset_x, offset_y in OVERLAYS.get(zone, []):
        columns = math.ceil(width / 256)
        rows = math.ceil(height / 256)
        for row in range(rows):
            for column in range(columns):
                number = row * columns + column + 1
                piece = f"{overlay}{number}".lower()
                if piece in excluded:
                    continue
                path = files.get(piece) or files.get((zone + overlay + str(number)).lower())
                if not path:
                    continue
                tile = Image.open(path).convert("RGBA")
                canvas.alpha_composite(
                    tile, (offset_x * 2 + column * TILE_SIZE,
                           offset_y * 2 + row * TILE_SIZE))
    return canvas.crop((0, 0, 2004, 1336)).convert("RGB").resize(
        MAP_SIZE, Image.Resampling.LANCZOS)


def gray_edges(image: Image.Image) -> np.ndarray:
    gray = np.asarray(image.convert("L"), dtype=np.uint8)
    return cv2.GaussianBlur(gray, (3, 3), 0)


def fit(source: Image.Image, runtime: Image.Image) -> dict[str, float | int | str]:
    detector = cv2.SIFT_create(nfeatures=14000, contrastThreshold=0.008)
    left_keys, left_desc = detector.detectAndCompute(gray_edges(source), None)
    right_keys, right_desc = detector.detectAndCompute(gray_edges(runtime), None)
    if left_desc is None or right_desc is None:
        return {"status": "insufficient", "matches": 0, "inliers": 0}
    matcher = cv2.BFMatcher(cv2.NORM_L2)
    forward = matcher.knnMatch(left_desc, right_desc, k=2)
    reverse = matcher.knnMatch(right_desc, left_desc, k=2)
    good_forward = {
        pair[0].queryIdx: pair[0].trainIdx
        for pair in forward if len(pair) == 2 and pair[0].distance < 0.78 * pair[1].distance
    }
    good_reverse = {
        pair[0].queryIdx: pair[0].trainIdx
        for pair in reverse if len(pair) == 2 and pair[0].distance < 0.78 * pair[1].distance
    }
    pairs = [
        (left_keys[left].pt, right_keys[right].pt)
        for left, right in good_forward.items() if good_reverse.get(right) == left
    ]
    if len(pairs) < 12:
        return {"status": "insufficient", "matches": len(pairs), "inliers": 0}
    left = np.asarray([pair[0] for pair in pairs], dtype=np.float32)
    right = np.asarray([pair[1] for pair in pairs], dtype=np.float32)
    matrix, mask = cv2.estimateAffine2D(
        left, right, method=cv2.RANSAC, ransacReprojThreshold=2.0,
        maxIters=10000, confidence=0.999, refineIters=25,
    )
    if matrix is None or mask is None:
        return {"status": "insufficient", "matches": len(pairs), "inliers": 0}
    inlier_mask = mask.ravel().astype(bool)
    source_inliers = left[inlier_mask]
    target_inliers = right[inlier_mask]
    scale_x, dx = np.polyfit(source_inliers[:, 0], target_inliers[:, 0], 1)
    scale_y, dy = np.polyfit(source_inliers[:, 1], target_inliers[:, 1], 1)
    scale_x, scale_y, dx, dy = map(float, (scale_x, scale_y, dx, dy))
    predicted = np.column_stack((
        source_inliers[:, 0] * scale_x + dx,
        source_inliers[:, 1] * scale_y + dy,
    ))
    errors = np.linalg.norm(predicted - target_inliers, axis=1)
    transform_error = max(
        abs(dx), abs(dy), abs(scale_x - 1) * MAP_SIZE[0],
        abs(scale_y - 1) * MAP_SIZE[1],
    )
    return {
        "status": "exact" if transform_error <= 1.0 else "review",
        "matches": len(pairs), "inliers": int(inlier_mask.sum()),
        "dx": dx, "dy": dy, "scale_x": scale_x, "scale_y": scale_y,
        "rotation_deg": 0.0,
        "p50_error": float(np.percentile(errors, 50)),
        "p90_error": float(np.percentile(errors, 90)),
    }


def main() -> int:
    rows = []
    for zone, filename in SOURCE_FILES.items():
        source = Image.open(SOURCE / filename).convert("RGB").resize(
            MAP_SIZE, Image.Resampling.LANCZOS)
        row = {"zone": zone, **fit(source, runtime_map(zone))}
        rows.append(row)
        print(
            f"{zone:<24} {row['status']:<12} inliers={row['inliers']:4d} "
            f"dx={row.get('dx', math.nan):7.3f} dy={row.get('dy', math.nan):7.3f} "
            f"sx={row.get('scale_x', math.nan):.7f} "
            f"sy={row.get('scale_y', math.nan):.7f}"
        )
    output = ADDON / "source-coordinate-audit.csv"
    fields = ["zone", "status", "matches", "inliers", "dx", "dy",
              "scale_x", "scale_y", "rotation_deg", "p50_error", "p90_error"]
    with output.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(rows)
    counts = {status: sum(row["status"] == status for row in rows)
              for status in ("exact", "review", "insufficient")}
    print("SUMMARY", counts)
    return 1 if counts["review"] or counts["insufficient"] else 0


if __name__ == "__main__":
    raise SystemExit(main())
