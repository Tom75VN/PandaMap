"""Compare PandaMap and native screenshots using marker and map geometry."""

from __future__ import annotations

import argparse
from pathlib import Path

import cv2
import numpy as np
from PIL import Image, ImageDraw


def load(path: Path) -> np.ndarray:
    return np.asarray(Image.open(path).convert("RGB"))


def sift_pairs(source: np.ndarray, target: np.ndarray, ratio: float = 0.78):
    detector = cv2.SIFT_create(nfeatures=20000, contrastThreshold=0.012)
    source_gray = cv2.cvtColor(source, cv2.COLOR_RGB2GRAY)
    target_gray = cv2.cvtColor(target, cv2.COLOR_RGB2GRAY)
    source_keys, source_desc = detector.detectAndCompute(source_gray, None)
    target_keys, target_desc = detector.detectAndCompute(target_gray, None)
    matcher = cv2.BFMatcher(cv2.NORM_L2)
    forward = matcher.knnMatch(source_desc, target_desc, k=2)
    reverse = matcher.knnMatch(target_desc, source_desc, k=2)
    good_forward = {
        match.queryIdx: match.trainIdx
        for match, second in forward
        if match.distance < ratio * second.distance
    }
    good_reverse = {
        match.queryIdx: match.trainIdx
        for match, second in reverse
        if match.distance < ratio * second.distance
    }
    pairs = [
        (source_keys[query].pt, target_keys[train].pt)
        for query, train in good_forward.items()
        if good_reverse.get(train) == query
    ]
    return np.float32([pair[0] for pair in pairs]), np.float32(
        [pair[1] for pair in pairs]
    )


def fit(source: np.ndarray, target: np.ndarray, threshold: float = 3.0):
    matrix, mask = cv2.estimateAffine2D(
        source,
        target,
        method=cv2.RANSAC,
        ransacReprojThreshold=threshold,
        maxIters=30000,
        confidence=0.999,
        refineIters=50,
    )
    predicted = cv2.transform(source[:, None, :], matrix)[:, 0, :]
    errors = np.linalg.norm(predicted - target, axis=1)
    return matrix, mask.ravel().astype(bool), errors


def in_rectangles(point, rectangles):
    x, y = point
    return any(left <= x <= right and top <= y <= bottom
               for left, top, right, bottom in rectangles)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--panda", type=Path, required=True)
    parser.add_argument("--native", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()

    panda = load(args.panda)
    native = load(args.native)
    source, target = sift_pairs(native, panda)

    # Native-screenshot rectangles containing markers, labels, health bars and
    # translucent quest areas. They are excluded to obtain an artwork-only fit.
    marker_rectangles = [
        (880, 315, 1000, 455),
        (1130, 320, 1260, 455),
        (560, 500, 685, 620),
        (1270, 480, 1445, 625),
        (965, 560, 1085, 670),
        (1050, 675, 1190, 800),
        (1340, 685, 1455, 805),
        (185, 695, 305, 820),
        (465, 720, 610, 855),
        (365, 755, 485, 875),
        (200, 700, 370, 960),
    ]
    artwork_mask = np.asarray(
        [not in_rectangles(point, marker_rectangles) for point in source],
        dtype=bool,
    )

    all_matrix, all_inliers, all_errors = fit(source, target)
    art_matrix, art_inliers, art_errors = fit(
        source[artwork_mask], target[artwork_mask]
    )

    # SIFT matches inside the UI rectangles come from identical icons, health
    # bars and translucent area shapes. They establish the marker-plane
    # transform more accurately than manually selected centres.
    marker_match_mask = ~artwork_mask
    marker_matrix, marker_inliers, marker_errors = fit(
        source[marker_match_mask], target[marker_match_mask], threshold=2.0
    )

    def report(name, matrix, inliers, errors):
        print(name)
        print(np.array2string(matrix, precision=6, suppress_small=True))
        print(
            "inliers", int(inliers.sum()), "of", len(inliers),
            "p50", float(np.percentile(errors[inliers], 50)),
            "p90", float(np.percentile(errors[inliers], 90)),
        )

    report("all", all_matrix, all_inliers, all_errors)
    report("artwork", art_matrix, art_inliers, art_errors)
    report("markers", marker_matrix, marker_inliers, marker_errors)

    relative = np.vstack([art_matrix, [0, 0, 1]]) @ np.linalg.inv(
        np.vstack([marker_matrix, [0, 0, 1]])
    )
    print("artwork relative to markers")
    print(np.array2string(relative[:2], precision=6, suppress_small=True))

    height, width = panda.shape[:2]
    native_on_panda = cv2.warpAffine(
        native,
        marker_matrix,
        (width, height),
        flags=cv2.INTER_LINEAR,
        borderMode=cv2.BORDER_CONSTANT,
    )
    blend = Image.blend(
        Image.fromarray(panda), Image.fromarray(native_on_panda), 0.5
    )
    draw = ImageDraw.Draw(blend)
    transformed_markers = cv2.transform(
        source[marker_match_mask][marker_inliers, None, :], marker_matrix
    )[:, 0, :]
    for x, y in transformed_markers:
        draw.ellipse((x - 6, y - 6, x + 6, y + 6), outline=(255, 0, 255), width=2)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    blend.save(args.output)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
