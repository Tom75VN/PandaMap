"""Build PandaMap_Terrain tiles: the 3D terrain layer shown when the map is zoomed in.

Source: the WoW Classic top-down continent renders (Eastern Kingdoms, Kalimdor)
from the PandaConquest POI review. The per-zone images are not used: they are
framed on the terrain rather than on the map, darkened outside the zone and
watermarked. The Azeroth image is not used either.

Calibration (measured by pandaconquest-poi-review/generate_terrain_maps.py):
  0.48 px per yard (256 px per 533.33-yard ADT tile), and the world origin of
  each continent, so that
      column = originCol - y * 0.48,  row = originRow - x * 0.48.
Each zone's frame is its WorldMapArea row read from the client's own DBC, so
the terrain sits exactly on the coordinate plane that GetPlayerMapPosition,
POIs and the HD maps use. The frame is resampled once (Lanczos, antialiased)
onto the HD grid: 1002 x 668 map units at 2 px per unit, edge pixels repeated
into the 2048 x 1536 canvas, cut into the same 4 x 3 grid of 512 px tiles.

Output: Packs/PandaMap_Terrain/World_Terrain/<Map>/<Map>_Terrain<n>.blp,
BLP2 DXT1 (no alpha) with a full mip chain. DXT1 stores colour exactly as the
DXT5 HD tiles do, at half the size, since the terrain has no transparency.

The output equals the POI review's validated crop of the same frame, resized
(mean difference 0.01 / 255 on Elwynn). --overlay draws the HD base over the
built terrain for a visual landmark check.
Requires: numpy, opencv-python-headless, pillow, mpyq, quicktex.

    python build_terrain_tiles.py [Map ...] [--source DIR] [--force] [--overlay DIR]
"""

from __future__ import annotations

import argparse
import math
import struct
import sys
from pathlib import Path

import cv2
import numpy as np
import quicktex.s3tc.bc1 as bc1
from PIL import Image

import build_unexplored_tiles as hd

ADDON = Path(__file__).resolve().parent
OUT = ADDON / "Packs" / "PandaMap_Terrain" / "World_Terrain"
SOURCE = Path(r"C:\Games\Wow-Octo\#Addons-dev\runtime-reports\pandaconquest-poi-review\3d-maps")
SOURCE_PREFIX = "wow_classic_high_resolution_world_terrain_map_"
PIXELS_PER_YARD = 256 / (1600 / 3)
# WorldMapArea.MapID -> continent render and its world origin (pixels).
CONTINENTS = {
    0: {"image": "eastern_kingdoms", "originCol": 2669, "originRow": 3420},
    1: {"image": "kalimdor", "originCol": 2583, "originRow": 5972},
}
MAP_W, MAP_H = hd.MAP_W, hd.MAP_H
CANVAS_W, CANVAS_H, TILE = hd.CANVAS_W, hd.CANVAS_H, hd.TILE
MARGIN = 24                       # source px kept around the frame for the filter
ENCODER_LEVEL = 18                # quicktex maximum quality
ZONES = sorted([
    "Alterac", "Arathi", "Ashenvale", "Aszhara", "Badlands", "Barrens",
    "BlastedLands", "BurningSteppes", "Darkshore", "DeadwindPass", "Desolace",
    "DunMorogh", "Durotar", "Duskwood", "Dustwallow", "EasternPlaguelands",
    "Elwynn", "Felwood", "Feralas", "Hilsbrad", "Hinterlands", "LochModan",
    "Moonglade", "Mulgore", "Redridge", "SearingGorge", "Silithus", "Silverpine",
    "StonetalonMountains", "Stranglethorn", "SwampOfSorrows", "Tanaris",
    "Teldrassil", "ThousandNeedles", "Tirisfal", "UngoroCrater",
    "WesternPlaguelands", "Westfall", "Wetlands", "Winterspring",
])


def world_map_areas() -> dict[str, dict]:
    """WorldMapArea.dbc from the client archives: name -> map id and bounds."""
    data = None
    for name in ["patch-5.mpq", "patch-4.mpq", "patch-3.mpq", "patch-2.mpq",
                 "patch-1.mpq", "patch.MPQ", "dbc.MPQ"]:
        if not (hd.DATA / name).exists():
            continue
        if name not in hd._archives:
            hd._archives[name] = hd.mpyq.MPQArchive(str(hd.DATA / name), listfile=False)
        data = hd._archives[name].read_file("DBFilesClient\\WorldMapArea.dbc")
        if data:
            break
    if not data:
        raise SystemExit("WorldMapArea.dbc not found in the client archives")
    magic, records, fields, size, _ = struct.unpack("<4s4I", data[:20])
    if magic != b"WDBC" or fields != 8 or size != 32:
        raise SystemExit("unexpected WorldMapArea.dbc layout")
    strings = data[20 + records * size:]
    rows = {}
    for i in range(records):
        record = data[20 + i * size:20 + (i + 1) * size]
        _, map_id, area, offset = struct.unpack("<4I", record[:16])
        left, right, top, bottom = struct.unpack("<4f", record[16:32])
        name = strings[offset:strings.index(b"\0", offset)].decode()
        rows[name] = {"map": map_id, "area": area, "left": left, "right": right,
                      "top": top, "bottom": bottom}
    return rows


def frame_box(zone: dict) -> tuple[float, float, float, float]:
    origin = CONTINENTS[zone["map"]]
    k = PIXELS_PER_YARD
    return (origin["originCol"] - zone["left"] * k, origin["originRow"] - zone["top"] * k,
            origin["originCol"] - zone["right"] * k, origin["originRow"] - zone["bottom"] * k)


def padded_region(source: Image.Image, box, name: str):
    """The frame plus MARGIN px, as an image, and the frame box inside it.

    A frame reaching past the render (Feralas) is completed with the render's
    border colour, which must be uniform open sea."""
    left, top = math.floor(box[0]) - MARGIN, math.floor(box[1]) - MARGIN
    right, bottom = math.ceil(box[2]) + MARGIN, math.ceil(box[3]) + MARGIN
    inner = (max(left, 0), max(top, 0), min(right, source.width), min(bottom, source.height))
    region = source.crop(inner)
    local = (box[0] - left, box[1] - top, box[2] - left, box[3] - top)
    if inner == (left, top, right, bottom):
        return region, local, 0
    # Past the render by more than the filter margin: check that the border is sea.
    overshoot = max(-box[0], -box[1], box[2] - source.width, box[3] - source.height)
    edges = []
    if left < 0:
        edges.append((0, inner[1], 1, inner[3]))
    if top < 0:
        edges.append((inner[0], 0, inner[2], 1))
    if right > source.width:
        edges.append((source.width - 1, inner[1], source.width, inner[3]))
    if bottom > source.height:
        edges.append((inner[0], source.height - 1, inner[2], source.height))
    pixels = np.concatenate([np.asarray(source.crop(e)).reshape(-1, 3) for e in edges])
    spread = int((pixels.max(0).astype(int) - pixels.min(0)).max())
    if overshoot > 0 and spread > 8:
        raise SystemExit("%s: frame leaves the render and its border is not uniform sea "
                         "(spread %d)" % (name, spread))
    colour = tuple(int(round(c)) for c in pixels.mean(0))
    canvas = Image.new("RGB", (right - left, bottom - top), colour)
    canvas.paste(region, (inner[0] - left, inner[1] - top))
    return canvas, local, max(0.0, overshoot)


def build_canvas(source: Image.Image, box, name: str):
    region, local, overshoot = padded_region(source, box, name)
    # One antialiased Lanczos resample of the exact (sub-pixel) frame.
    frame = region.resize((MAP_W, MAP_H), Image.Resampling.LANCZOS, box=local)
    area = np.asarray(frame)
    return cv2.copyMakeBorder(np.ascontiguousarray(area), 0, CANVAS_H - MAP_H, 0,
                              CANVAS_W - MAP_W, cv2.BORDER_REPLICATE), overshoot


def write_blp(path: Path, tile: np.ndarray, encoder) -> None:
    """BLP2, DXT1 (alpha depth 0), mipmapped; 1 x 1 level twice like the HD tiles."""
    if tile.shape[:2] != (TILE, TILE):
        raise SystemExit("tile %s is %s, not %d x %d" % (path, tile.shape, TILE, TILE))
    rgba = cv2.cvtColor(tile, cv2.COLOR_RGB2RGBA)
    blocks = [hd.encode(level, encoder) for level in hd.mip_chain(rgba)]
    blocks.append(blocks[-1])
    offsets, sizes, cursor = [], [], 148 + 1024
    for block in blocks:
        offsets.append(cursor)
        sizes.append(len(block))
        cursor += len(block)
    offsets += [0] * (16 - len(offsets))
    sizes += [0] * (16 - len(sizes))
    header = b"BLP2" + struct.pack("<IBBBBII", 1, 2, 0, 0, 1, TILE, TILE)
    header += struct.pack("<16I", *offsets) + struct.pack("<16I", *sizes) + bytes(1024)
    path.write_bytes(header + b"".join(blocks))


def read_tiles(zone: str) -> np.ndarray | None:
    folder = OUT / zone
    canvas = np.zeros((CANVAS_H, CANVAS_W, 3), np.uint8)
    for i in range(12):
        path = folder / ("%s_Terrain%d.blp" % (zone, i + 1))
        if not path.exists():
            return None
        row, column = divmod(i, 4)
        canvas[row * TILE:(row + 1) * TILE, column * TILE:(column + 1) * TILE] = \
            np.asarray(Image.open(path).convert("RGB"))
    return canvas[:MAP_H, :MAP_W]


def overlay(zone: str, terrain: np.ndarray, path: Path) -> None:
    """Visual check: the HD base's strong edges drawn over the terrain, beside a
    50 % blend. Image registration cannot score the parchment art against a
    terrain render; landmarks (lakes, rivers, walls) are compared by eye."""
    base = hd.world_base(zone)
    if base is None:
        return
    gray = cv2.GaussianBlur(cv2.cvtColor(base, cv2.COLOR_RGB2GRAY), (0, 0), 1.2)
    edges = cv2.dilate(cv2.Canny(gray, 60, 140), np.ones((2, 2), np.uint8))
    view = terrain.copy()
    view[edges > 0] = (255, 40, 200)
    image = np.hstack([view, cv2.addWeighted(terrain, 0.5, base, 0.5, 0)])
    Image.fromarray(image).save(path)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("maps", nargs="*")
    parser.add_argument("--source", type=Path, default=SOURCE)
    parser.add_argument("--force", action="store_true", help="rebuild maps that already exist")
    parser.add_argument("--overlay", type=Path, metavar="DIR",
                        help="write HD-over-terrain check images of the built tiles to DIR, "
                             "build nothing")
    args = parser.parse_args()
    unknown = [m for m in args.maps if m not in ZONES]
    if unknown:
        raise SystemExit("unknown map: %s" % ", ".join(unknown))
    selected = args.maps or ZONES
    areas = world_map_areas()
    Image.MAX_IMAGE_PIXELS = None
    renders: dict[int, Image.Image] = {}
    encoder = bc1.BC1Encoder(ENCODER_LEVEL, bc1.BC1Encoder.ColorMode.FourColor)
    for zone in selected:
        if args.overlay:
            terrain = read_tiles(zone)
            if terrain is None:
                print("%-20s not built" % zone)
                continue
            args.overlay.mkdir(parents=True, exist_ok=True)
            overlay(zone, terrain, args.overlay / ("terrain_%s.png" % zone))
            print("%-20s %s" % (zone, args.overlay / ("terrain_%s.png" % zone)), flush=True)
            continue
        folder = OUT / zone
        if folder.exists() and not args.force and not args.maps:
            print("%-20s skipped (already built)" % zone)
            continue
        area = areas.get(zone)
        if not area or area["map"] not in CONTINENTS:
            raise SystemExit("%s: no WorldMapArea row on a continent" % zone)
        if area["map"] not in renders:
            path = args.source / (SOURCE_PREFIX + CONTINENTS[area["map"]]["image"] + ".png")
            renders[area["map"]] = Image.open(path).convert("RGB")
        box = frame_box(area)
        canvas, overshoot = build_canvas(renders[area["map"]], box, zone)
        folder.mkdir(parents=True, exist_ok=True)
        for i in range(12):
            row, column = divmod(i, 4)
            tile = canvas[row * TILE:(row + 1) * TILE, column * TILE:(column + 1) * TILE]
            write_blp(folder / ("%s_Terrain%d.blp" % (zone, i + 1)), tile, encoder)
        scale = MAP_W / (box[2] - box[0])
        note = " sea-padded %.0f px" % overshoot if overshoot else ""
        print("%-20s frame %.2f x %.2f src px at (%.2f, %.2f), x%.2f%s" % (
            zone, box[2] - box[0], box[3] - box[1], box[0], box[1], scale, note), flush=True)
    return 0


if __name__ == "__main__":
    sys.exit(main())
