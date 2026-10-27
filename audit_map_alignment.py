"""Measure PandaMap base-tile geometry against the TurtleHD reference pack.

The comparison deliberately ignores colour/style differences.  SIFT feature
matches are lifted from each 512px tile into the full 4x3 map coordinate
system, then a robust affine transform is fitted from TurtleHD to PandaMap.
An aligned map should be close to the identity transform.
"""

from __future__ import annotations

import argparse
import csv
import math
from pathlib import Path

import cv2
import numpy as np
from PIL import Image


MAP_WIDTH = 2004
MAP_HEIGHT = 1336
TILE_SIZE = 512


def load_gray(path: Path) -> np.ndarray:
    image = Image.open(path).convert("RGBA")
    rgba = np.asarray(image)
    gray = cv2.cvtColor(rgba[:, :, :3], cv2.COLOR_RGB2GRAY)
    alpha = rgba[:, :, 3]
    # Transparent overlay padding must never become a feature.
    gray = gray.copy()
    gray[alpha < 16] = 0
    return gray


def tile_path(folder: Path, map_name: str, number: int) -> Path | None:
    wanted = f"{map_name}{number}.blp".lower()
    for path in folder.glob("*.blp"):
        if path.name.lower() == wanted:
            return path
    return None


def mutual_sift(reference: np.ndarray, panda: np.ndarray):
    sift = cv2.SIFT_create(nfeatures=3500, contrastThreshold=0.015)
    key_ref, desc_ref = sift.detectAndCompute(reference, None)
    key_pan, desc_pan = sift.detectAndCompute(panda, None)
    if desc_ref is None or desc_pan is None:
        return []

    matcher = cv2.BFMatcher(cv2.NORM_L2)
    forward = matcher.knnMatch(desc_ref, desc_pan, k=2)
    reverse = matcher.knnMatch(desc_pan, desc_ref, k=2)
    good_fwd = {
        match.queryIdx: match.trainIdx
        for match, second in forward
        if match.distance < 0.78 * second.distance
    }
    good_rev = {
        match.queryIdx: match.trainIdx
        for match, second in reverse
        if match.distance < 0.78 * second.distance
    }
    return [
        (key_ref[query].pt, key_pan[train].pt)
        for query, train in good_fwd.items()
        if good_rev.get(train) == query
    ]


def audit_zone(
    panda_folder: Path,
    reference_folder: Path,
    map_name: str,
    panda_stem_suffix: str = "",
):
    source_points = []
    target_points = []
    matched_tiles = 0
    raw_matches = 0

    for number in range(1, 13):
        panda_path = tile_path(panda_folder, map_name + panda_stem_suffix, number)
        reference_path = tile_path(reference_folder, map_name, number)
        if panda_path is None or reference_path is None:
            continue
        matches = mutual_sift(load_gray(reference_path), load_gray(panda_path))
        if not matches:
            continue
        matched_tiles += 1
        raw_matches += len(matches)
        column = (number - 1) % 4
        row = (number - 1) // 4
        origin = np.array([column * TILE_SIZE, row * TILE_SIZE], dtype=np.float32)
        for source, target in matches:
            source_global = np.asarray(source, dtype=np.float32) + origin
            target_global = np.asarray(target, dtype=np.float32) + origin
            if (source_global[0] <= MAP_WIDTH and source_global[1] <= MAP_HEIGHT
                    and target_global[0] <= MAP_WIDTH and target_global[1] <= MAP_HEIGHT):
                source_points.append(source_global)
                target_points.append(target_global)

    result = {
        "zone": map_name,
        "tiles": matched_tiles,
        "matches": raw_matches,
        "inliers": 0,
        "inlier_ratio": 0.0,
        "dx": math.nan,
        "dy": math.nan,
        "scale_x": math.nan,
        "scale_y": math.nan,
        "rotation_deg": math.nan,
        "p50_error": math.nan,
        "p90_error": math.nan,
        "status": "insufficient",
    }
    if len(source_points) < 12:
        return result

    source = np.asarray(source_points, dtype=np.float32)
    target = np.asarray(target_points, dtype=np.float32)
    matrix, mask = cv2.estimateAffine2D(
        source, target, method=cv2.RANSAC, ransacReprojThreshold=3.0,
        maxIters=10000, confidence=0.999, refineIters=25,
    )
    if matrix is None or mask is None:
        return result

    inlier_mask = mask.ravel().astype(bool)
    predicted = cv2.transform(source.reshape(-1, 1, 2), matrix).reshape(-1, 2)
    errors = np.linalg.norm(predicted - target, axis=1)[inlier_mask]
    linear = matrix[:, :2]
    scale_x = float(np.linalg.norm(linear[:, 0]))
    scale_y = float(np.linalg.norm(linear[:, 1]))
    rotation = math.degrees(math.atan2(linear[1, 0], linear[0, 0]))
    inliers = int(inlier_mask.sum())

    result.update({
        "inliers": inliers,
        "inlier_ratio": inliers / len(source),
        "dx": float(matrix[0, 2]),
        "dy": float(matrix[1, 2]),
        "scale_x": scale_x,
        "scale_y": scale_y,
        "rotation_deg": rotation,
        "p50_error": float(np.percentile(errors, 50)),
        "p90_error": float(np.percentile(errors, 90)),
    })
    transform_error = max(
        abs(result["dx"]), abs(result["dy"]),
        abs(scale_x - 1.0) * MAP_WIDTH,
        abs(scale_y - 1.0) * MAP_HEIGHT,
    )
    if inliers >= 30 and result["inlier_ratio"] >= 0.35:
        result["status"] = "aligned" if transform_error <= 4.0 else "review"
    return result


def audit_tile(panda_path: Path, reference_path: Path):
    matches = mutual_sift(load_gray(reference_path), load_gray(panda_path))
    if len(matches) < 8:
        return None
    source = np.asarray([pair[0] for pair in matches], dtype=np.float32)
    target = np.asarray([pair[1] for pair in matches], dtype=np.float32)
    matrix, mask = cv2.estimateAffine2D(
        source, target, method=cv2.RANSAC, ransacReprojThreshold=3.0,
        maxIters=5000, confidence=0.999, refineIters=20,
    )
    if matrix is None or mask is None:
        return None
    inliers = int(mask.sum())
    return len(matches), inliers, matrix


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--panda-root", type=Path, required=True)
    parser.add_argument("--reference-root", type=Path, required=True)
    parser.add_argument("--csv", type=Path)
    parser.add_argument(
        "--detail-zones", default="",
        help="Comma-separated zones for which per-tile transforms are printed",
    )
    parser.add_argument(
        "--zones", default="",
        help="Optional comma-separated zone filter",
    )
    parser.add_argument(
        "--panda-stem-suffix", default="",
        help="Suffix added to Panda tile stems, for example _Unexplored",
    )
    args = parser.parse_args()
    detail_zones = {
        item.strip().lower() for item in args.detail_zones.split(",") if item.strip()
    }
    selected_zones = {
        item.strip().lower() for item in args.zones.split(",") if item.strip()
    }

    rows = []
    for panda_folder in sorted(
        (path for path in args.panda_root.iterdir() if path.is_dir()),
        key=lambda path: path.name.lower(),
    ):
        if selected_zones and panda_folder.name.lower() not in selected_zones:
            continue
        reference_folder = args.reference_root / panda_folder.name
        if not reference_folder.is_dir():
            # TurtleHD has inconsistent casing in a few names.
            reference_folder = next(
                (path for path in args.reference_root.iterdir()
                 if path.is_dir() and path.name.lower() == panda_folder.name.lower()),
                reference_folder,
            )
        if not reference_folder.is_dir():
            continue
        row = audit_zone(
            panda_folder, reference_folder, panda_folder.name,
            args.panda_stem_suffix,
        )
        rows.append(row)
        print(
            f"{row['zone']:<24} {row['status']:<12} "
            f"inliers={row['inliers']:4d} ratio={row['inlier_ratio']:.2f} "
            f"dx={row['dx']:7.2f} dy={row['dy']:7.2f} "
            f"sx={row['scale_x']:.6f} sy={row['scale_y']:.6f} "
            f"p90={row['p90_error']:.2f}"
        )
        if panda_folder.name.lower() in detail_zones:
            for number in range(1, 13):
                panda_path = tile_path(
                    panda_folder,
                    panda_folder.name + args.panda_stem_suffix,
                    number,
                )
                reference_path = tile_path(reference_folder, panda_folder.name, number)
                if panda_path is None or reference_path is None:
                    continue
                detail = audit_tile(panda_path, reference_path)
                if detail is None:
                    print(f"  tile {number:02d}: insufficient")
                    continue
                matches, inliers, matrix = detail
                linear = matrix[:, :2]
                sx = float(np.linalg.norm(linear[:, 0]))
                sy = float(np.linalg.norm(linear[:, 1]))
                print(
                    f"  tile {number:02d}: {inliers:3d}/{matches:3d} "
                    f"dx={matrix[0, 2]:7.2f} dy={matrix[1, 2]:7.2f} "
                    f"sx={sx:.5f} sy={sy:.5f}"
                )

    if args.csv:
        args.csv.parent.mkdir(parents=True, exist_ok=True)
        with args.csv.open("w", newline="", encoding="utf-8") as handle:
            writer = csv.DictWriter(handle, fieldnames=list(rows[0]))
            writer.writeheader()
            writer.writerows(rows)

    counts = {status: sum(row["status"] == status for row in rows)
              for status in ("aligned", "review", "insufficient")}
    print(f"SUMMARY {counts}")
    return 1 if counts["review"] else 0


if __name__ == "__main__":
    raise SystemExit(main())
