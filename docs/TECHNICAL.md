# PandaMap technical notes

PandaMap is the OctoWoW 1.12.1 port of UnrealMap 0.6.0. It bundles the World
and Unexplored map sets in one addon and replaces native zone, continent,
capital, and battleground maps with HD artwork while retaining the client's
native map frame, coordinate APIs, labels, controls, and click targets.

## Memory model

- No HD map texture is bound at login.
- Only the currently visible map's 12 base tiles and visible native overlay
  slots are bound.
- Native map texture regions are reused; browsing maps does not create new
  texture regions or frames.
- Tile paths and overlay lookup data are cached for one active map only and
  released when the map closes or changes.
- Fog removal is off by default, avoiding unexplored overlay textures unless
  the player explicitly enables it.
- Closing the map clears every PandaMap texture binding. The game client may
  retain decoded textures in its internal cache; Lua cannot force that cache
  to evict resources.

## HD unexplored map coverage

All 54 currently integrated zone maps have dedicated unexplored artwork, listed in
`UNEXPLORED_BASE_MAPS` in `pandaMap.lua`. The original 40-map set is built by
`build_unexplored_tiles.py` from the masters in
`D:\Development\unrealMap_data\#Maps\zones_unexplored` (file names match the
map names). The script aligns each master to the zone's HD explored base,
which sits on the client map, and resamples it once into the tiles, adding a
smooth local warp where a master is locally out of shape. The Turtle builder
replaces the changed Stonetalon and Tirisfal bases and adds fourteen Turtle map
keys from the installed client's native unexplored art.

| Zone | HD unexplored map |
| --- | --- |
| Balor | Complete |
| Grim Reaches | Complete |
| Hyjal | Complete |
| Icepoint | Complete |
| Moonwhisper Coast | Complete |
| Northwind | Complete |
| Scarlet Enclave | Complete |
| Alterac Mountains | Complete |
| Arathi Highlands | Complete |
| Ashenvale | Complete |
| Azshara | Complete |
| Badlands | Complete |
| The Barrens | Complete |
| Blasted Lands | Complete |
| Burning Steppes | Complete |
| Darkshore | Complete |
| Deadwind Pass | Complete |
| Desolace | Complete |
| Dun Morogh | Complete |
| Durotar | Complete |
| Duskwood | Complete |
| Dustwallow Marsh | Complete |
| Eastern Plaguelands | Complete |
| Elwynn Forest | Complete |
| Felwood | Complete |
| Feralas | Complete |
| Hillsbrad Foothills | Complete |
| The Hinterlands | Complete |
| Loch Modan | Complete |
| Moonglade | Complete |
| Mulgore | Complete |
| Redridge Mountains | Complete |
| Searing Gorge | Complete |
| Silithus | Complete |
| Silverpine Forest | Complete |
| Stonetalon Mountains | Complete |
| Stranglethorn Vale | Complete |
| Swamp of Sorrows | Complete |
| Tanaris | Complete |
| Teldrassil | Complete |
| Thousand Needles | Complete |
| Tirisfal Glades | Complete |
| Un'Goro Crater | Complete |
| Western Plaguelands | Complete |
| Westfall | Complete |
| Wetlands | Complete |
| Winterspring | Complete |
| Alah'Thalas | Complete |
| Blackstone Island | Complete |
| Gillijim's Isle | Complete |
| Gilneas | Complete |
| Island of Lapidis | Complete |
| Tel'Abim | Complete |
| Thalassian Highlands | Complete |

`build_turtle_maps.py` integrates the 17 Turtle-edited existing zones and the
fourteen new client map keys from `#Maps\zones\Turtle`. It rebuilds explored
bases and every exploration overlay against the client's exact
`WorldMapOverlay.dbc` geometry. Stonetalon Mountains and Tirisfal Glades get
new unexplored bases; the other 15 existing zones retain their aligned bases.
The regeneration source of truth,
`D:\Development\unrealMap_data\#Maps\zones\Turtle`, currently contains 17
completed existing-zone PNGs and fourteen completed `New-Zones` PNGs.
All fourteen new outdoor map keys have World and Unexplored pack assets; they
remain on parchment at high zoom until matching terrain renders are available.
The completed audit inventory is recorded in
[`docs/TURTLE-HD-MAP-BACKLOG.md`](TURTLE-HD-MAP-BACKLOG.md). The focused
added-versus-missing unexplored-map tracker is
[`docs/TURTLE-UNEXPLORED-MAP-CHECKLIST.md`](TURTLE-UNEXPLORED-MAP-CHECKLIST.md).

## Commands

- `/pmap` opens settings.
- `/pmap fog on` and `/pmap fog off` control fog removal.
- `/pmap minimap` shows or hides the settings button.
- `/pmap terrain on` and `/pmap terrain off` control the 3D terrain; plain
  `/pmap terrain` prints the zoom read, the bound tile and the binding
  driver's state (starts, stops and why, last error).

## Map zoom

- The mouse wheel zooms the world map (1x to 4x, in 0.25 steps, about the
  cursor). The zoom eases to each step and ends exactly on it, so the 3D
  terrain comes up at x3. While it eases or the map pans, only the map
  art changes each frame; markers (units, POIs, pandaQuest and pandaConquest
  pins) are hidden and come back in place once movement settles. Pinned frames
  (zone name, cursor readout, hints, the pandaConquest toggle) stay shown.
  `/pmap perf` starts a lightweight performance capture. Zoom in and out,
  drag and glide the map, then `/reload`; the capture is saved in PandaMap's
  SavedVariables for analysis. A double click zooms in one level about the
  cursor; the first click still does what a click does on the stock map.
- Drag with the left button to pan while zoomed; a fast release keeps the map
  gliding until it slows down or reaches an edge. A click on the map stops it.
- A "Zoom" icon in the map's top-right corner shows the feature is there. Map
  updates and panning preserve the current zoom; closing and reopening the map
  resets it.
- PandaMap owns the zoom even with pandaUI installed: pandaUI's worldmapzoom
  module skips its install while `PandaMapZoom.ClaimsZoom()` is true, and
  hands its pins (cursor readout and others) to `PandaMapZoom.Pin`. If
  PandaMap's install fails, it enables pandaUI's zoom instead. If an older
  pandaUI already installed its zoom, or another addon has moved the native
  map canvas, `MapZoom.lua` installs nothing, so two zooms never stack.

## 3D terrain

- From zoom x3 on (`TERRAIN_ZOOM` in `pandaMap.lua`), the original 40 outdoor zone
  maps fade from parchment to a top-down 3D terrain render. The whole zone is
  shown and the exploration overlays are hidden (alpha 0) until the map is
  zoomed out again, when it fades back to parchment. The "3D terrain when
  zoomed in" setting turns it
  off. The zoom is read from PandaMap's own zoom or from pandaUI's. The fourteen
  new Turtle maps remain on parchment because no matching terrain renders are
  bundled yet.
- Tiles: `Packs/PandaMap_Terrain/World_Terrain/<Map>/<Map>_Terrain1..12`,
  the same 4 x 3 grid of 512 px tiles as the HD maps, BLP2 DXT1 with mips
  (about 2 MB per zone). They are bound only while the terrain is shown.
- `build_terrain_tiles.py` builds them from the WoW Classic continent renders
  (`#Addons-dev\runtime-reports\pandaconquest-poi-review\3d-maps`). Each frame
  is the zone's row of the client's `WorldMapArea.dbc`, placed with the
  continent calibration measured by the POI review
  (`generate_terrain_maps.py`, 0.48 px per yard), and resampled once onto the
  HD grid (2 px per map unit). The terrain therefore sits on the same plane as
  map positions and the HD maps, with no `TILE_TRANSFORMS` entry. The per-zone
  images are not used: they are framed on the terrain, darkened outside the
  zone and watermarked.
- The renders show the Blizzard terrain. Where OctoWoW changed the terrain
  (its patches replace Kalimdor terrain tiles), the render can differ from the
  game. Stonetalon Mountains uses OctoWoW's enlarged frame, like its HD map,
  but shows the zone's Blizzard terrain rather than OctoWoW's redesign.
- `build_terrain_tiles.py --overlay DIR` draws each HD base over its terrain
  for a landmark check. Checked by eye: coasts, lakes, rivers and walls fall
  within 1-3 map units of the painted HD art (Arathi, Darkshore, Westfall,
  Tanaris, Feralas, Stonetalon).

## Coordinate alignment

- `WorldMapButton`, the client's 1002 x 668 coordinate plane used by native
  markers, addon POIs, quest areas and clicks, is never moved or resized.
- The reference is the client's own map art: the `Interface\WorldMap` tiles
  and overlays in the client MPQs, placed with the client's
  `WorldMapOverlay.dbc`. Native markers are correct on that art, so HD art that
  matches it pixel for pixel keeps every marker in place.
- The HD base tiles already match the client map on almost every map. The
  few that do not (Alterac and the Arathi and Elwynn unexplored bases,
  Searing Gorge and Silithus) get an artwork-only scale and offset in
  `TILE_TRANSFORMS` / `OVERLAY_TRANSFORMS`.
- The 31 Turtle-integrated maps use the installed client's exact overlay
  geometry in `MapOverlayData.lua`. The remaining legacy HD overlays retain
  their authored 1.12 geometry. Overlays without HD art keep the client
  geometry.
- The HD Stormwind is the Turtle layout with the harbour
  (`#Maps\Capitals\Stormwind-turtle.png`), plainly scaled to 2004 x 1336 px;
  it matches the client map within about 0.1 unit.
- `audit_native_alignment.py` rebuilds both the native map and the PandaMap
  map as drawn in game and reports the residual per base map and overlay
  (needs numpy, opencv-python-headless, pillow and mpyq). PandaMap's textures
  remain unchanged.

## Roadmap

- [x] Regenerate World, Azeroth, and Kalimdor from the `_Turtle` masters.

## Credits

Original addon and HD world-map artwork: Thomas / UnrealMap. World of Warcraft
is a trademark of Blizzard Entertainment. This project is not affiliated with
or endorsed by Blizzard Entertainment.
