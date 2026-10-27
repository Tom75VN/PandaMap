"""Compare TurtleHD's explored maps with PandaMap's HD source masters.

Current TurtleHD exports pair ``<Map>_Unexplored.jpg`` (the fogged/base map)
with ``<Map>.jpg`` (the fully explored map). The explored export is used
directly. For an older export without the paired unexplored file, this script
falls back to rebuilding the explored map from the client's
WorldMapOverlay.dbc geometry and the folder's BLP overlays.

The output is intended for content review, not pixel-equality testing: the two
packs use different color grading and drawing styles.

Requires Pillow and mpyq.

    py -3.10 audit_turtle_content.py --output DIR [Map ...]
"""

from __future__ import annotations

import argparse
import math
import struct
from pathlib import Path

import mpyq
from PIL import Image, ImageChops, ImageDraw, ImageFilter, ImageOps, ImageStat


ADDON = Path(__file__).resolve().parent
DATA = ADDON.parents[2] / "Data"
CURRENT = Path(r"D:\Development\unrealMap_data\#Maps")
TURTLE = Path(r"D:\Development\unrealMap_data\TurtleHD")
CLASSIC = Path(r"D:\Development\unrealUI_data\wowclassic_illus_maps\WoW Classic Maps\Explored zones")
ARCHIVES = [
    "patch-5.mpq", "patch-4.mpq", "patch-3.mpq", "patch-2.mpq",
    "patch-1.mpq", "patch.MPQ", "interface.MPQ", "dbc.MPQ",
]

# The source masters predate the normalized client asset names.
SOURCE_MASTERS = {
    "Arathi": "zones/arathi.png",
    "Wetlands": "zones/Wetlands.png",
    "Stranglethorn": "zones/Stranglethorn.png",
    "Aszhara": "zones/azshara.png",
    "SwampOfSorrows": "zones/swamp_of_sorrows.png",
    "Durotar": "zones/durotar.png",
    "StonetalonMountains": "zones/Stonetalon_Mountains.png",
    "Badlands": "zones/Badlands.png",
    "Feralas": "zones/Feralas.png",
    "Felwood": "zones/felwood.png",
    "Ashenvale": "zones/Ashenvale.png",
    "Dustwallow": "zones/dustwallowmarsh.png",
    "Tanaris": "zones/Tanaris.png",
    "DunMorogh": "zones/DunMorogh.png",
    "Mulgore": "zones/mulgore.png",
    "EasternPlaguelands": "zones/Eastern_Plaguelands.png",
    "BurningSteppes": "zones/BurningSteppes.png",
    "Tirisfal": "zones/Tirisfal.png",
    "Westfall": "zones/Westfall.png",
    "Stormwind": "Capitals/Stormwind-turtle.png",
}

CLASSIC_MASTERS = {
    "Arathi": "arathi.jpg",
    "Wetlands": "wetlands.jpg",
    "Stranglethorn": "stranglethorn.jpg",
    "Aszhara": "azshara.jpg",
    "SwampOfSorrows": "swampofsorrows.jpg",
    "Durotar": "durotar.jpg",
    "StonetalonMountains": "stonetalon.jpg",
    "Badlands": "badlands.jpg",
    "Feralas": "feralas.jpg",
    "Felwood": "felwood.jpg",
    "Ashenvale": "ashenvale.jpg",
    "Dustwallow": "dustwallowmarsh.jpg",
    "Tanaris": "tanaris.jpg",
    "DunMorogh": "dunmorogh.jpg",
    "Mulgore": "mulgore.jpg",
    "EasternPlaguelands": "eplaguelands.jpg",
    "BurningSteppes": "burningsteppes.jpg",
    "Tirisfal": "tirisfal.jpg",
    "Westfall": "westfall.jpg",
    "Stormwind": "stormwind.jpg",
}


def read_client(path: str) -> bytes:
    for archive_name in ARCHIVES:
        archive_path = DATA / archive_name
        if not archive_path.exists():
            continue
        archive = mpyq.MPQArchive(str(archive_path), listfile=False)
        data = archive.read_file(path)
        if data:
            return data
    raise FileNotFoundError(path)


def parse_dbc(data: bytes):
    magic, count, fields, size, _ = struct.unpack("<4s4I", data[:20])
    if magic != b"WDBC":
        raise ValueError("not a WDBC file")
    rows = [
        struct.unpack("<%dI" % fields, data[20 + i * size:20 + (i + 1) * size])
        for i in range(count)
    ]
    strings = data[20 + count * size:]

    def text(offset: int) -> str:
        return strings[offset:strings.index(b"\0", offset)].decode("latin-1")

    return rows, text


def client_overlays():
    areas, area_name = parse_dbc(read_client(r"DBFilesClient\WorldMapArea.dbc"))
    names = {row[0]: area_name(row[3]) for row in areas}
    rows, overlay_name = parse_dbc(read_client(r"DBFilesClient\WorldMapOverlay.dbc"))
    result = {}
    for row in rows:
        name = overlay_name(row[8])
        if name:
            result.setdefault(names.get(row[1], ""), []).append((name, *row[9:13]))
    return result


def file_dimension(pixels: int) -> int:
    size = 16
    while size < pixels:
        size *= 2
    return size


def paste_clipped(canvas: Image.Image, image: Image.Image, x: int, y: int) -> None:
    left, top = max(0, -x), max(0, -y)
    right = min(image.width, canvas.width - x)
    bottom = min(image.height, canvas.height - y)
    if right <= left or bottom <= top:
        return
    piece = image.crop((left, top, right, bottom))
    canvas.alpha_composite(piece, (x + left, y + top))


def reconstruct_turtle_map(map_name: str, overlays) -> tuple[Image.Image, list[str]]:
    folder = TURTLE / map_name
    unexplored = folder / (map_name + "_Unexplored.jpg")
    base = unexplored if unexplored.exists() else folder / (map_name + ".jpg")
    canvas = Image.open(base).convert("RGBA")
    scale_x, scale_y = canvas.width / 1002, canvas.height / 668
    if abs(scale_x - 2) > 0.001 or abs(scale_y - 2) > 0.001:
        raise ValueError(f"{map_name}: unexpected canvas {canvas.size}")

    files = {path.stem.lower(): path for path in folder.glob("*.blp")}
    missing = []
    for name, width, height, offset_x, offset_y in overlays.get(map_name, []):
        columns, rows = math.ceil(width / 256), math.ceil(height / 256)
        for row in range(rows):
            for column in range(columns):
                number = row * columns + column + 1
                path = files.get((name + str(number)).lower())
                if path is None:
                    missing.append(name + str(number) + ".blp")
                    continue
                piece = Image.open(path).convert("RGBA")
                piece_width = 256 if column < columns - 1 else (width % 256 or 256)
                piece_height = 256 if row < rows - 1 else (height % 256 or 256)
                file_width = 256 if column < columns - 1 else file_dimension(piece_width)
                file_height = 256 if row < rows - 1 else file_dimension(piece_height)
                crop_width = round(piece_width / file_width * piece.width)
                crop_height = round(piece_height / file_height * piece.height)
                piece = piece.crop((0, 0, crop_width, crop_height))
                x = round((offset_x + column * 256) * scale_x)
                y = round((offset_y + row * 256) * scale_y)
                paste_clipped(canvas, piece, x, y)
    return canvas.convert("RGB"), missing


def turtle_explored(map_name: str, overlays) -> tuple[Image.Image, list[str], str]:
    folder = TURTLE / map_name
    explored = folder / (map_name + ".jpg")
    unexplored = folder / (map_name + "_Unexplored.jpg")
    if unexplored.exists():
        return Image.open(explored).convert("RGB"), [], "explored export"
    image, missing = reconstruct_turtle_map(map_name, overlays)
    return image, missing, "overlay reconstruction"


def fit(image: Image.Image, size: tuple[int, int]) -> Image.Image:
    return ImageOps.fit(image, size, Image.Resampling.LANCZOS)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("maps", nargs="*", metavar="MAP")
    parser.add_argument("--output", type=Path, required=True)
    comparison_mode = parser.add_mutually_exclusive_group()
    comparison_mode.add_argument(
        "--unexplored",
        action="store_true",
        help="compare PandaMap and TurtleHD unexplored/base maps directly",
    )
    comparison_mode.add_argument(
        "--classic",
        action="store_true",
        help="compare WoW Classic and TurtleHD explored maps directly",
    )
    args = parser.parse_args()

    available = set(SOURCE_MASTERS)
    if args.unexplored:
        available.remove("Stormwind")
    unknown = sorted(set(args.maps) - available)
    if unknown:
        parser.error("unknown map(s): " + ", ".join(unknown))
    selected = args.maps or [name for name in SOURCE_MASTERS if name in available]
    args.output.mkdir(parents=True, exist_ok=True)
    overlays = {} if args.unexplored else client_overlays()
    previews = []

    for map_name in selected:
        if args.unexplored:
            current = Image.open(CURRENT / "zones_unexplored" / (map_name + ".png")).convert("RGB")
            turtle = Image.open(TURTLE / map_name / (map_name + "_Unexplored.jpg")).convert("RGB")
            missing, turtle_source = [], "unexplored export"
            comparison_kind = "unexplored"
            left_source = "PandaMap source"
        elif args.classic:
            current = Image.open(CLASSIC / CLASSIC_MASTERS[map_name]).convert("RGB")
            turtle = Image.open(TURTLE / map_name / (map_name + ".jpg")).convert("RGB")
            turtle_for_diff = turtle.resize(current.size, Image.Resampling.LANCZOS)
            difference = ImageStat.Stat(ImageChops.difference(current, turtle_for_diff))
            mean_difference = sum(difference.mean) / len(difference.mean)
            classic_gray = ImageOps.grayscale(current)
            turtle_gray = ImageOps.grayscale(turtle_for_diff)
            classic_detail = ImageChops.subtract(
                classic_gray,
                classic_gray.filter(ImageFilter.GaussianBlur(4)),
                offset=128,
            )
            turtle_detail = ImageChops.subtract(
                turtle_gray,
                turtle_gray.filter(ImageFilter.GaussianBlur(4)),
                offset=128,
            )
            detail_difference = ImageStat.Stat(
                ImageChops.difference(classic_detail, turtle_detail)
            )
            detail_image = ImageChops.difference(classic_detail, turtle_detail)
            detail_mean = detail_difference.mean[0]
            block_means = []
            block_size = 64
            for top in range(0, detail_image.height, block_size):
                for left in range(0, detail_image.width, block_size):
                    block = detail_image.crop((
                        left,
                        top,
                        min(left + block_size, detail_image.width),
                        min(top + block_size, detail_image.height),
                    ))
                    block_means.append(ImageStat.Stat(block).mean[0])
            block_means.sort()
            block_p95 = block_means[round((len(block_means) - 1) * 0.95)]
            block_max = block_means[-1]
            missing, turtle_source = [], (
                f"explored export; mean RGB difference {mean_difference:.2f}; "
                f"detail mean/p95/max {detail_mean:.2f}/{block_p95:.2f}/{block_max:.2f}"
            )
            comparison_kind = "explored"
            left_source = "WoW Classic"
        else:
            current = Image.open(CURRENT / SOURCE_MASTERS[map_name]).convert("RGB")
            turtle, missing, turtle_source = turtle_explored(map_name, overlays)
            comparison_kind = "explored"
            left_source = "PandaMap source"
        if current.size != turtle.size:
            current = current.resize(turtle.size, Image.Resampling.LANCZOS)

        comparison = Image.new("RGB", (current.width * 2, current.height), "black")
        comparison.paste(current, (0, 0))
        comparison.paste(turtle, (current.width, 0))
        ImageDraw.Draw(comparison).text((12, 12), f"{map_name}: {left_source} | TurtleHD {comparison_kind}", fill="white", stroke_width=2, stroke_fill="black")
        comparison.save(args.output / (map_name + ".jpg"), quality=92, subsampling=0)

        preview = Image.new("RGB", (640, 230), "#111111")
        preview.paste(fit(current, (320, 214)), (0, 16))
        preview.paste(fit(turtle, (320, 214)), (320, 16))
        ImageDraw.Draw(preview).text((8, 2), map_name, fill="white")
        previews.append(preview)
        note = "" if not missing else ", missing pieces: " + ", ".join(missing)
        print(f"{map_name}: {turtle_source}{note}")

    columns = 2
    rows = math.ceil(len(previews) / columns)
    sheet = Image.new("RGB", (columns * 640, rows * 230), "#111111")
    for index, preview in enumerate(previews):
        sheet.paste(preview, ((index % columns) * 640, (index // columns) * 230))
    sheet.save(args.output / "contact-sheet.jpg", quality=92, subsampling=0)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
