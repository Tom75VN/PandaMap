"""Build Turtle/OctoWoW HD map assets while preserving exploration fog.

The enhanced source images are fully explored 1536 x 1024 maps.  This
builder places them on PandaMap's 2004 x 1336 visible canvas, cuts the normal
4 x 3 grid of 512 px base tiles, and rebuilds every exploration overlay with
the alpha mask from the native Turtle client.  Overlay placement comes from
MapOverlayData.lua, which is kept on the client's 1002 x 668 coordinate plane.

Stonetalon Mountains and Tirisfal receive regenerated unexplored bases because
their Turtle geometry changed.  The fourteen new Turtle map keys receive
native unexplored bases as well.  Existing unexplored art for the other maps
remains untouched.

Requires Pillow with BCN/DDS encoding support.
"""

from __future__ import annotations

import argparse
import io
import math
import re
import struct
from pathlib import Path

from PIL import Image


ADDON = Path(__file__).resolve().parent
WORLD = ADDON / "Packs" / "PandaMap_World" / "World"
UNEXPLORED = ADDON / "Packs" / "PandaMap_Unexplored" / "World_Unexplored"
DEFAULT_SOURCE = Path(r"D:\Development\unrealMap_data\#Maps\zones\Turtle")
DEFAULT_NATIVE = Path(r"D:\Development\unrealMap_data\turtleWoW-SD")

MAP_W, MAP_H = 2004, 1336
CANVAS_W, CANVAS_H, TILE = 2048, 1536, 512
NATIVE_TILE = 256

SOURCE_FILES = {
    "Ashenvale": "Ashenvale.png",
    "Aszhara": "Aszhara.png",
    "Badlands": "Badlands.png",
    "BurningSteppes": "BurningSteppes.png",
    "DunMorogh": "DunMorogh.png",
    "Durotar": "Durotar.png",
    "Dustwallow": "DustWallow.png",
    "EasternPlaguelands": "Eastern_Plaguelands.png",
    "Felwood": "Felwood.png",
    "Feralas": "Feralas.png",
    "Mulgore": "mulgore.png",
    "StonetalonMountains": "Stonetalon_Mountains.png",
    "Stranglethorn": "Stranglethorn.png",
    "SwampOfSorrows": "SwampOfSorrows.png",
    "Tanaris": "Tanaris.png",
    "Tirisfal": "Tirisfal.png",
    "Wetlands": "Wetlands.png",
    "AlahThalas": "New-Zones/AlahThalas.png",
    "Balor": "New-Zones/Balor.png",
    "BlackstoneIsland": "New-Zones/BlackstoneIsland.png",
    "Gillijim": "New-Zones/Gillijim.png",
    "Gilneas": "New-Zones/Gilneas.png",
    "GrimReaches": "New-Zones/GrimReaches.png",
    "Hyjal": "New-Zones/Hyjal.png",
    "Icepoint": "New-Zones/IcePoint.png",
    "Lapidis": "New-Zones/Lapidis.png",
    "Moonwhisper": "New-Zones/Moonwhisper.png",
    "Northwind": "New-Zones/Northwind.png",
    "ScarletEnclave": "New-Zones/Scarlet Enclave.png",
    "TelAbim": "New-Zones/TelAbim.png",
    "ThalassianHighlands": "New-Zones/ThalassianHighlands.png",
}

NEW_MAPS = {
    "AlahThalas", "Balor", "BlackstoneIsland", "Gillijim", "Gilneas",
    "GrimReaches", "Hyjal", "Icepoint", "Lapidis", "Moonwhisper",
    "Northwind", "ScarletEnclave", "TelAbim", "ThalassianHighlands",
}
REBUILD_UNEXPLORED = NEW_MAPS | {"StonetalonMountains", "Tirisfal"}

# The 1.12 client resolves addon textures by basename, so these collision-prone
# files carry their map key on disk.  Keep this in sync with pandaMap.lua.
PREFIXED = {
    "BurningSteppes": {"altarofstorms"},
    "DunMorogh": {"ironforge"},
    "EasternPlaguelands": {"thondrorilriver"},
    "Mulgore": {"thunderbluff"},
}


def overlay_geometry() -> dict[str, list[tuple[str, int, int, int, int]]]:
    text = (ADDON / "MapOverlayData.lua").read_text(encoding="utf-8")
    result: dict[str, list[tuple[str, int, int, int, int]]] = {}
    for block in re.finditer(r"^  (\w+) = \{(.*?)^  \},", text, re.M | re.S):
        entries = []
        for encoded in re.findall(r'"([^"]+)"', block.group(2)):
            name, width, height, x, y = encoded.split(":")
            entries.append((name, int(width), int(height), int(x), int(y)))
        result[block.group(1)] = entries
    return result


def dds_payload(image: Image.Image) -> bytes:
    stream = io.BytesIO()
    image.convert("RGBA").save(stream, "DDS", pixel_format="DXT5")
    data = stream.getvalue()
    if data[:4] != b"DDS " or data[84:88] != b"DXT5":
        raise RuntimeError("Pillow did not produce a DXT5 DDS stream")
    return data[128:]


def mip_chain(image: Image.Image) -> list[Image.Image]:
    levels = [image.convert("RGBA")]
    while levels[-1].width > 1:
        size = levels[-1].width // 2
        levels.append(levels[-1].resize((size, size), Image.Resampling.LANCZOS))
    return levels


def write_blp(path: Path, image: Image.Image) -> None:
    if image.size[0] != image.size[1] or image.size[0] & (image.size[0] - 1):
        raise ValueError(f"BLP texture must be square power-of-two: {path} {image.size}")
    blocks = []
    for level in mip_chain(image):
        if level.width < 4:
            level = level.resize((4, 4), Image.Resampling.NEAREST)
        blocks.append(dds_payload(level))
    blocks.append(blocks[-1])
    offsets, sizes, cursor = [], [], 148 + 1024
    for block in blocks:
        offsets.append(cursor)
        sizes.append(len(block))
        cursor += len(block)
    offsets += [0] * (16 - len(offsets))
    sizes += [0] * (16 - len(sizes))
    header = b"BLP2" + struct.pack(
        "<IBBBBII", 1, 2, 8, 7, 1, image.width, image.height
    )
    header += struct.pack("<16I", *offsets) + struct.pack("<16I", *sizes)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(header + bytes(1024) + b"".join(blocks))


def padded_canvas(area: Image.Image) -> Image.Image:
    area = area.convert("RGBA")
    if area.size != (MAP_W, MAP_H):
        raise ValueError(area.size)
    canvas = Image.new("RGBA", (CANVAS_W, CANVAS_H))
    canvas.paste(area, (0, 0))
    right = area.crop((MAP_W - 1, 0, MAP_W, MAP_H)).resize(
        (CANVAS_W - MAP_W, MAP_H), Image.Resampling.NEAREST
    )
    canvas.paste(right, (MAP_W, 0))
    bottom = canvas.crop((0, MAP_H - 1, CANVAS_W, MAP_H)).resize(
        (CANVAS_W, CANVAS_H - MAP_H), Image.Resampling.NEAREST
    )
    canvas.paste(bottom, (0, MAP_H))
    return canvas


def write_base_tiles(folder: Path, stem: str, area: Image.Image) -> set[str]:
    canvas = padded_canvas(area)
    written = set()
    for index in range(12):
        row, column = divmod(index, 4)
        name = f"{stem}{index + 1}.blp"
        tile = canvas.crop((
            column * TILE, row * TILE,
            (column + 1) * TILE, (row + 1) * TILE,
        ))
        write_blp(folder / name, tile)
        written.add(name.lower())
    return written


def native_files(folder: Path) -> dict[str, Path]:
    return {path.stem.lower(): path for path in folder.glob("*.blp")}


def open_blp(path: Path) -> Image.Image:
    try:
        image = Image.open(path)
        image.load()
        return image
    except OSError as error:
        data = path.read_bytes()
        if not data.startswith(b"BLP2") or "Truncated File Read" not in str(error):
            raise
        image = Image.open(io.BytesIO(data + bytes(max(0, 1172 - len(data)))))
        image.load()
        return image


def native_base(folder: Path, zone: str) -> Image.Image:
    files = native_files(folder)
    canvas = Image.new("RGB", (1024, 768))
    for number in range(1, 13):
        path = files.get(f"{zone}{number}".lower())
        if path is None:
            raise FileNotFoundError(folder / f"{zone}{number}.blp")
        tile = open_blp(path).convert("RGB")
        canvas.paste(tile, (((number - 1) % 4) * 256, ((number - 1) // 4) * 256))
    return canvas.crop((0, 0, 1002, 668)).resize(
        (MAP_W, MAP_H), Image.Resampling.LANCZOS
    )


def file_dimension(visible: int) -> int:
    size = 16
    while size < visible:
        size *= 2
    return size


def overlay_output_name(zone: str, name: str, number: int) -> str:
    prefix = zone if name.lower() in PREFIXED.get(zone, set()) else ""
    return f"{prefix}{name}{number}.blp"


def write_highlight(folder: Path, native_folder: Path, zone: str) -> bool:
    path = native_folder / f"{zone}Highlight.blp"
    if not path.is_file():
        return False
    native = open_blp(path).convert("RGBA")
    size = min(TILE, native.width * 2)
    write_blp(
        folder / f"{zone}Highlight.blp",
        native.resize((size, size), Image.Resampling.LANCZOS),
    )
    return True


def write_overlays(
    folder: Path,
    native_folder: Path,
    zone: str,
    explored: Image.Image,
    geometry: list[tuple[str, int, int, int, int]],
) -> tuple[set[str], list[str]]:
    files = native_files(native_folder)
    written, missing = set(), []
    for name, width, height, offset_x, offset_y in geometry:
        columns, rows = math.ceil(width / 256), math.ceil(height / 256)
        # A native overlay can contain a narrow storage-only column even when
        # the DBC rectangle ends exactly on a 256px boundary. Its filename
        # still advances the row-major sequence. Icepoint's KANEQNUUN uses
        # files 3 and 6 as 8px slivers, so the visible second row starts at
        # native file 4 while PandaMap's compact output remains piece 3.
        file_columns = columns
        sliver = files.get(f"{name}{columns + 1}".lower())
        if width % 256 == 0 and sliver is not None:
            if open_blp(sliver).width < 256:
                file_columns += 1
        for row in range(rows):
            for column in range(columns):
                number = row * columns + column + 1
                source_number = row * file_columns + column + 1
                key = f"{name}{source_number}".lower()
                path = files.get(key) or files.get(
                    f"{zone}{name}{source_number}".lower()
                )
                if path is None:
                    missing.append(f"{zone}/{name}{number}")
                    continue
                visible_w = 256 if column < columns - 1 else (width % 256 or 256)
                visible_h = 256 if row < rows - 1 else (height % 256 or 256)
                native = open_blp(path).convert("RGBA")
                alpha = native.getchannel("A").resize(
                    (TILE, TILE), Image.Resampling.LANCZOS
                )
                x0 = (offset_x + column * 256) * 2
                y0 = (offset_y + row * 256) * 2
                color = explored.crop((
                    x0, y0, x0 + visible_w * 2, y0 + visible_h * 2,
                ))
                encoded_w = max(1, round(visible_w / file_dimension(visible_w) * TILE))
                encoded_h = max(1, round(visible_h / file_dimension(visible_h) * TILE))
                color = color.resize(
                    (encoded_w, encoded_h), Image.Resampling.LANCZOS
                )
                texture = Image.new("RGBA", (TILE, TILE))
                texture.paste(color, (0, 0))
                texture.putalpha(alpha)
                output_name = overlay_output_name(zone, name, number)
                write_blp(folder / output_name, texture)
                written.add(output_name.lower())
    return written, missing


def remove_stale_assets(folder: Path, keep: set[str]) -> list[str]:
    removed = []
    for path in folder.glob("*.blp"):
        if path.name.lower() not in keep:
            path.unlink()
            removed.append(path.name)
    return removed


def validate_sources(source: Path, native: Path, maps: list[str]) -> None:
    missing = []
    for zone in maps:
        if not (source / SOURCE_FILES[zone]).is_file():
            missing.append(str(source / SOURCE_FILES[zone]))
        if not (native / zone).is_dir():
            missing.append(str(native / zone))
    if missing:
        raise FileNotFoundError("Missing Turtle inputs:\n" + "\n".join(missing))


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("maps", nargs="*", metavar="MAP")
    parser.add_argument("--source", type=Path, default=DEFAULT_SOURCE)
    parser.add_argument("--native", type=Path, default=DEFAULT_NATIVE)
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()
    unknown = sorted(set(args.maps) - set(SOURCE_FILES))
    if unknown:
        parser.error("unknown map(s): " + ", ".join(unknown))
    maps = args.maps or list(SOURCE_FILES)
    validate_sources(args.source, args.native, maps)
    geometry = overlay_geometry()
    failures = []
    for zone in maps:
        if zone not in geometry:
            failures.append(f"{zone}: missing MapOverlayData entry")
            continue
        source_path = args.source / SOURCE_FILES[zone]
        native_folder = args.native / zone
        print(
            f"{zone:<22} source={source_path.name} overlays={len(geometry[zone])}"
            f" unexplored={'rebuild' if zone in REBUILD_UNEXPLORED else 'keep'}",
            flush=True,
        )
        if args.dry_run:
            continue
        explored = Image.open(source_path).convert("RGB").resize(
            (MAP_W, MAP_H), Image.Resampling.LANCZOS
        )
        world_folder = WORLD / zone
        keep = write_base_tiles(world_folder, zone, explored)
        write_highlight(world_folder, native_folder, zone)
        keep.add(f"{zone}Highlight.blp".lower())
        overlay_files, missing = write_overlays(
            world_folder, native_folder, zone, explored, geometry[zone]
        )
        keep.update(overlay_files)
        removed = remove_stale_assets(world_folder, keep)
        if removed:
            print(f"  removed {len(removed)} obsolete overlay pieces", flush=True)
        failures.extend(f"missing native overlay {item}" for item in missing)
        if zone in REBUILD_UNEXPLORED:
            unexplored = native_base(native_folder, zone)
            write_base_tiles(
                UNEXPLORED / zone, zone + "_Unexplored", unexplored
            )
    if failures:
        print("FAILURES")
        for failure in failures:
            print(f"  {failure}")
        return 1
    print(f"Built {len(maps)} Turtle map assets successfully")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
