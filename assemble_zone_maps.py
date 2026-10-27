"""Stitch TurtleHD's numbered 512px BLP map tiles into zone JPEGs.

Each full zone is a 4 x 3 tile grid.  The native map rectangle is 2004 x
1336px, so the unused right/bottom padding from the 2048 x 1536 tile canvas is
removed to match the existing TurtleHD output convention.
"""

from __future__ import annotations

import argparse
import math
import re
from pathlib import Path

from PIL import Image


ROOT = Path(r"D:\Development\unrealMap_data\TurtleHD")
OVERLAY_DATA = Path(__file__).with_name("MapOverlayData.lua")
TILE = 512
OUTPUT_SIZE = (2004, 1336)


def overlay_geometry() -> dict[str, list[tuple[str, int, int, int, int]]]:
    text = OVERLAY_DATA.read_text(encoding="utf-8")
    result = {}
    for block in re.finditer(r"^  (\w+) = \{(.*?)^  \},", text,
                            re.MULTILINE | re.DOTALL):
        entries = []
        for encoded in re.findall(r'"([^"]+)"', block.group(2)):
            name, width, height, x, y = encoded.split(":")
            entries.append((name, int(width), int(height), int(x), int(y)))
        result[block.group(1).casefold()] = entries
    return result


OVERLAYS = overlay_geometry()


def add_explored_overlays(canvas: Image.Image, folder: Path) -> int:
    """Composite every known map overlay, which is the explored-map art."""
    files = {path.stem.casefold(): path for path in folder.glob("*.blp")}
    used = 0
    for name, width, height, offset_x, offset_y in OVERLAYS.get(folder.name.casefold(), []):
        columns = math.ceil(width / 256)
        rows = math.ceil(height / 256)
        for row in range(rows):
            for column in range(columns):
                number = row * columns + column + 1
                path = (files.get(f"{name}{number}".casefold())
                        or files.get(f"{folder.name}{name}{number}".casefold()))
                if path is None:
                    continue
                with Image.open(path) as source:
                    canvas.alpha_composite(source.convert("RGBA"),
                                           (offset_x * 2 + column * TILE,
                                            offset_y * 2 + row * TILE))
                used += 1
    return used


def assemble(folder: Path) -> tuple[bool, str]:
    zone = folder.name
    output = folder / f"{zone}.jpg"
    tiles: dict[int, Path] = {}
    for path in folder.glob("*.blp"):
        match = re.fullmatch(re.escape(zone) + r"(1[0-2]|[1-9])", path.stem,
                             re.IGNORECASE)
        if match:
            tiles[int(match.group(1))] = path

    if not tiles:
        return False, "no numbered base tiles"
    missing = [str(number) for number in range(1, 13) if number not in tiles]

    canvas = Image.new("RGBA", (TILE * 4, TILE * 3))
    try:
        for number in sorted(tiles):
            with Image.open(tiles[number]) as source:
                tile = source.convert("RGBA")
                if tile.width > TILE or tile.height > TILE:
                    return False, f"tile {number} is {tile.size}, larger than {(TILE, TILE)}"
                canvas.alpha_composite(tile, (((number - 1) % 4) * TILE,
                                               ((number - 1) // 4) * TILE))
    except Exception as exc:
        return False, f"could not read tiles: {exc}"

    overlays = add_explored_overlays(canvas, folder)
    image = canvas.crop((0, 0, *OUTPUT_SIZE)).convert("RGB")
    # Avoid JPEG's expensive entropy optimization: it adds several minutes to
    # this batch while making no visible difference for these map references.
    image.save(output, "JPEG", quality=95, subsampling=0)
    status = f"{output.name} ({overlays} explored overlay tiles)"
    if missing:
        status += " (partial: missing " + ", ".join(missing) + ")"
    return True, status


def rename_unexplored() -> None:
    renamed = []
    for folder in sorted((path for path in ROOT.iterdir() if path.is_dir()),
                         key=lambda path: path.name.casefold()):
        source = folder / f"{folder.name}.jpg"
        destination = folder / f"{folder.name}_Unexplored.jpg"
        if source.exists() and not destination.exists():
            source.rename(destination)
            renamed.append(folder.name)
    print(f"Renamed {len(renamed)} JPEGs as unexplored.")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--rename-unexplored", action="store_true")
    parser.add_argument("--bucket", type=int, default=0,
                        help="zero-based partition number for a batch run")
    parser.add_argument("--buckets", type=int, default=1,
                        help="total number of partitions for a batch run")
    args = parser.parse_args()
    if args.rename_unexplored:
        rename_unexplored()
        return

    if args.buckets < 1 or not 0 <= args.bucket < args.buckets:
        raise SystemExit("--bucket must be from 0 through --buckets minus one")
    folders = sorted((path for path in ROOT.iterdir() if path.is_dir()),
                     key=lambda path: path.name.casefold())
    folders = [folder for index, folder in enumerate(folders)
               if index % args.buckets == args.bucket]
    created: list[str] = []
    skipped: list[tuple[str, str]] = []
    for folder in folders:
        ok, result = assemble(folder)
        if ok:
            created.append(folder.name)
        else:
            skipped.append((folder.name, result))

    print(f"Created {len(created)} zone JPEGs.")
    if skipped:
        print(f"Skipped {len(skipped)} folders:")
        for zone, reason in skipped:
            print(f"  {zone}: {reason}")


if __name__ == "__main__":
    main()
