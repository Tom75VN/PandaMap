"""Assemble selected Turtle/OctoWoW WorldMap BLP files into explored JPG maps."""

from __future__ import annotations

import argparse
import io
import math
import struct
from pathlib import Path

from PIL import Image


MAPS = (
    "Wetlands",
    "Stranglethorn",
    "Aszhara",
    "SwampOfSorrows",
    "Durotar",
    "StonetalonMountains",
    "Badlands",
    "Feralas",
    "Felwood",
    "Ashenvale",
    "Dustwallow",
    "Tanaris",
    "DunMorogh",
    "Mulgore",
    "EasternPlaguelands",
    "BurningSteppes",
    "Tirisfal",
    "Balor",
    "GrimReaches",
    "Hyjal",
    "Icepoint",
    "Moonwhisper",
    "Northwind",
    "ScarletEnclave",
    "BlackstoneIsland",
    "ThalassianHighlands",
    "AlahThalas",
    "Gilneas",
    "Gillijim",
    "Lapidis",
    "TelAbim",
)

CANVAS_WIDTH = 1002
CANVAS_HEIGHT = 668
TILE_SIZE = 256


def open_blp(path: Path) -> Image.Image:
    try:
        return Image.open(path).convert("RGBA")
    except OSError as error:
        data = path.read_bytes()
        if not data.startswith(b"BLP2") or "Truncated File Read" not in str(error):
            raise
        return Image.open(io.BytesIO(data + bytes(max(0, 1172 - len(data))))).convert("RGBA")


def parse_dbc(path: Path):
    data = path.read_bytes()
    magic, count, fields, row_size, _ = struct.unpack_from("<4s4I", data)
    if magic != b"WDBC" or row_size != fields * 4:
        raise ValueError(f"Unsupported DBC: {path}")
    rows = [
        struct.unpack_from(f"<{fields}I", data, 20 + index * row_size)
        for index in range(count)
    ]
    strings = data[20 + count * row_size :]

    def text(offset: int) -> str:
        if not 0 <= offset < len(strings):
            return ""
        end = strings.find(b"\0", offset)
        if end < 0:
            end = len(strings)
        return strings[offset:end].decode("latin-1")

    return rows, text


def overlay_geometry(dbc_root: Path):
    areas, area_name = parse_dbc(dbc_root / "WorldMapArea.dbc")
    map_names = {row[0]: area_name(row[3]) for row in areas}
    rows, overlay_name = parse_dbc(dbc_root / "WorldMapOverlay.dbc")
    result: dict[str, list[tuple[str, int, int, int, int]]] = {}
    for row in rows:
        name = overlay_name(row[8])
        map_name = map_names.get(row[1], "")
        if name and map_name:
            result.setdefault(map_name, []).append((name, *row[9:13]))
    return result


def file_dimension(visible_pixels: int) -> int:
    size = 16
    while size < visible_pixels:
        size *= 2
    return size


def paste_clipped(canvas: Image.Image, image: Image.Image, x: int, y: int) -> None:
    left = max(0, -x)
    top = max(0, -y)
    right = min(image.width, canvas.width - x)
    bottom = min(image.height, canvas.height - y)
    if right <= left or bottom <= top:
        return
    canvas.alpha_composite(image.crop((left, top, right, bottom)), (x + left, y + top))


def assemble_base(folder: Path, map_name: str) -> Image.Image:
    canvas = Image.new("RGBA", (CANVAS_WIDTH, CANVAS_HEIGHT), (0, 0, 0, 255))
    for number in range(1, 13):
        path = folder / f"{map_name}{number}.blp"
        if not path.exists():
            raise FileNotFoundError(path)
        tile = open_blp(path)
        column = (number - 1) % 4
        row = (number - 1) // 4
        x = column * TILE_SIZE
        y = row * TILE_SIZE
        paste_clipped(canvas, tile, x, y)
    return canvas


def apply_overlays(
    canvas: Image.Image,
    folder: Path,
    overlays: list[tuple[str, int, int, int, int]],
) -> list[str]:
    files = {path.stem.lower(): path for path in folder.glob("*.blp")}
    missing = []
    for name, width, height, offset_x, offset_y in overlays:
        columns = math.ceil(width / TILE_SIZE)
        rows = math.ceil(height / TILE_SIZE)
        # Some Turtle overlays contain a narrow storage-only column even when
        # the DBC rectangle ends exactly on a 256px boundary.  Its filename
        # still advances the row-major sequence.  Icepoint's KANEQNUUN is the
        # notable example: files 3 and 6 are 8px slivers, so the visible second
        # row starts at file 4 rather than file 3.
        file_columns = columns
        sliver = files.get(f"{name}{columns + 1}".lower())
        if width % TILE_SIZE == 0 and sliver is not None:
            if open_blp(sliver).width < TILE_SIZE:
                file_columns += 1
        for row in range(rows):
            for column in range(columns):
                number = row * file_columns + column + 1
                filename = f"{name}{number}.blp"
                path = files.get(Path(filename).stem.lower())
                if path is None:
                    missing.append(filename)
                    continue
                piece = open_blp(path)
                visible_width = TILE_SIZE if column < columns - 1 else (width % TILE_SIZE or TILE_SIZE)
                visible_height = TILE_SIZE if row < rows - 1 else (height % TILE_SIZE or TILE_SIZE)
                stored_width = TILE_SIZE if column < columns - 1 else file_dimension(visible_width)
                stored_height = TILE_SIZE if row < rows - 1 else file_dimension(visible_height)
                crop_width = round(visible_width / stored_width * piece.width)
                crop_height = round(visible_height / stored_height * piece.height)
                piece = piece.crop((0, 0, crop_width, crop_height))
                paste_clipped(
                    canvas,
                    piece,
                    offset_x + column * TILE_SIZE,
                    offset_y + row * TILE_SIZE,
                )
    return missing


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("source", type=Path, help="Folder containing one subfolder per map")
    parser.add_argument("dbc", type=Path, help="Extracted DBFilesClient folder")
    parser.add_argument("--quality", type=int, default=100)
    selection = parser.add_mutually_exclusive_group()
    selection.add_argument("--maps", nargs="+")
    selection.add_argument(
        "--missing",
        action="store_true",
        help="assemble every map folder that does not yet contain <Map>.jpg",
    )
    args = parser.parse_args()

    overlays = overlay_geometry(args.dbc)
    failures = []
    if args.missing:
        selected = sorted(
            folder.name
            for folder in args.source.iterdir()
            if folder.is_dir()
            and not (folder / f"{folder.name}.jpg").exists()
            and all((folder / f"{folder.name}{number}.blp").exists() for number in range(1, 13))
        )
    else:
        selected = args.maps or MAPS
    for map_name in selected:
        folder = args.source / map_name
        canvas = assemble_base(folder, map_name)
        missing = apply_overlays(canvas, folder, overlays.get(map_name, []))
        output = folder / f"{map_name}.jpg"
        canvas.convert("RGB").save(output, quality=args.quality, subsampling=0)
        if missing:
            failures.append((map_name, missing))
        print(f"{map_name}: {output} ({len(overlays.get(map_name, []))} overlays)")

    if failures:
        for map_name, missing in failures:
            print(f"MISSING {map_name}: {', '.join(missing)}")
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
