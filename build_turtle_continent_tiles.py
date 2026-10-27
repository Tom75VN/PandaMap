"""Build the three Turtle continent/world masters into PandaMap BLP tiles."""

from __future__ import annotations

import struct
from pathlib import Path

import quicktex
import quicktex.s3tc.bc3 as bc3
from PIL import Image


ADDON = Path(__file__).resolve().parent
SOURCE = Path(r"D:\Development\unrealMap_data\#Maps")
OUTPUT = ADDON / "Packs" / "PandaMap_World" / "Continents"
MASTERS = {
    "Azeroth": SOURCE / "Eastern_Kingdoms_Turtle.png",
    "Kalimdor": SOURCE / "Kalimdor_Turtle.png",
    "World": SOURCE / "World_Turtle.png",
}
MAP_SIZE = (2004, 1336)
CANVAS_SIZE = (2048, 1536)
TILE_SIZE = 512
ENCODER_LEVEL = 18


def build_canvas(master: Path) -> Image.Image:
    source = Image.open(master).convert("RGBA")
    if source.size != (1536, 1024):
        raise ValueError(f"Unexpected master size for {master}: {source.size}")
    image = source.resize(MAP_SIZE, Image.Resampling.LANCZOS)
    canvas = Image.new("RGBA", CANVAS_SIZE)
    canvas.paste(image, (0, 0))
    canvas.paste(
        image.crop((MAP_SIZE[0] - 1, 0, MAP_SIZE[0], MAP_SIZE[1])).resize(
            (CANVAS_SIZE[0] - MAP_SIZE[0], MAP_SIZE[1]), Image.Resampling.NEAREST
        ),
        (MAP_SIZE[0], 0),
    )
    canvas.paste(
        canvas.crop((0, MAP_SIZE[1] - 1, CANVAS_SIZE[0], MAP_SIZE[1])).resize(
            (CANVAS_SIZE[0], CANVAS_SIZE[1] - MAP_SIZE[1]), Image.Resampling.NEAREST
        ),
        (0, MAP_SIZE[1]),
    )
    return canvas


def mip_chain(tile: Image.Image) -> list[Image.Image]:
    levels = [tile]
    while levels[-1].width > 1:
        size = levels[-1].width // 2
        levels.append(levels[-1].resize((size, size), Image.Resampling.BOX))
    return levels


def encode(level: Image.Image, encoder: bc3.BC3Encoder) -> bytes:
    if level.width < 4:
        level = level.resize((4, 4), Image.Resampling.NEAREST)
    raw = quicktex.RawTexture.frombytes(level.tobytes(), level.width, level.height)
    return encoder.encode(raw).tobytes()


def encode_blp(tile: Image.Image, encoder: bc3.BC3Encoder) -> bytes:
    blocks = [encode(level, encoder) for level in mip_chain(tile)]
    blocks.append(blocks[-1])
    offsets: list[int] = []
    sizes: list[int] = []
    cursor = 148 + 1024
    for block in blocks:
        offsets.append(cursor)
        sizes.append(len(block))
        cursor += len(block)
    offsets += [0] * (16 - len(offsets))
    sizes += [0] * (16 - len(sizes))
    header = b"BLP2" + struct.pack("<IBBBBII", 1, 2, 8, 7, 1, TILE_SIZE, TILE_SIZE)
    header += struct.pack("<16I", *offsets) + struct.pack("<16I", *sizes) + bytes(1024)
    return header + b"".join(blocks)


def main() -> None:
    missing = [str(path) for path in MASTERS.values() if not path.is_file()]
    if missing:
        raise FileNotFoundError("Missing masters:\n" + "\n".join(missing))

    encoder = bc3.BC3Encoder(ENCODER_LEVEL)
    for zone, master in MASTERS.items():
        canvas = build_canvas(master)
        folder = OUTPUT / zone
        folder.mkdir(parents=True, exist_ok=True)
        temporary: list[tuple[Path, Path]] = []
        for index in range(12):
            row, column = divmod(index, 4)
            tile = canvas.crop(
                (
                    column * TILE_SIZE,
                    row * TILE_SIZE,
                    (column + 1) * TILE_SIZE,
                    (row + 1) * TILE_SIZE,
                )
            )
            output = folder / f"{zone}{index + 1}.blp"
            temp = output.with_suffix(".blp.tmp")
            temp.write_bytes(encode_blp(tile, encoder))
            temporary.append((temp, output))
        for temp, output in temporary:
            temp.replace(output)
        print(f"{zone}: 12 tiles from {master.name}")


if __name__ == "__main__":
    main()
