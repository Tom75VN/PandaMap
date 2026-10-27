# Turtle WoW HD map integration audit

Audit date: 2026-10-25

Implementation status: 2D integration complete. All 17 changed existing zones
and all 14 new client map keys are integrated in PandaMap.
`build_turtle_maps.py` rebuilds the HD bases and exploration overlays from the
enhanced Turtle maps, using the installed client's alpha masks and exact
overlay geometry.

Sources:

- OctoWoW's [New Locations & Maps](https://octowow.st/new-locations-and-maps)
  page (the Turtle content inventory requested for this audit).
- The installed Octo/Turtle client's `WorldMapArea.dbc`,
  `WorldMapOverlay.dbc`, and `Interface\WorldMap` files, read in patch order.
- PandaMap's HD source masters in
  `D:\Development\unrealMap_data\#Maps` and the TurtleHD tiles in
  `D:\Development\unrealMap_data\TurtleHD`.
- The complete SD client-map export in
  `D:\Development\unrealMap_data\turtleWoW-SD`, classified against
  `WorldMapArea.dbc` so instances and entrance maps are not counted as zones.
- PandaMap's current `MapOverlayData.lua`, `pandaMap.lua`, and pack folders.

## Result

PandaMap currently has complete explored, unexplored, and terrain packs for
40 outdoor zones. The source page identifies 20 existing maps with Turtle
changes: 19 of the outdoor zones plus Stormwind. Direct comparison with the
WoW Classic explored sources shows that only 17 of those outdoor maps need
regeneration: Arathi Highlands and Westfall have no rendered cartographic
difference even though the page and client metadata call out added gameplay
areas. The page also identifies six new zones outside the current 40-zone
catalog. The complete SD export and current client contain seven further
top-level outdoor zones not present on that page: Balor, Grim Reaches,
Northwind, Moonwhisper Coast, Hyjal, the Scarlet Enclave, and Icepoint.

This result was reverified after TurtleHD added its fully explored JPG
exports and corrected after comparing those exports directly with
`WoW Classic Maps/Explored zones`. Arathi's new area and fog-reveal metadata
does not change its rendered map and is therefore not regeneration work.

Stormwind is also complete: PandaMap already uses the Turtle layout with the
harbor. The full client-defined scope is therefore 17 edited outdoor zone maps
and 13 Turtle outdoor zones beyond the original 40-map catalog.

The client adds one implementation split: Alah'Thalas is a separate top-level
map asset (`AlahThalas`) as well as content within `ThalassianHighlands`.
Supporting the 13 client zones therefore requires 14 new map asset keys. The
full target set is 31 map assets: 17 regenerated existing zones plus 14 new
maps. All 31 are integrated.

The source page is an editorial overview, not a complete client manifest.
Its location labels do not always correspond one-for-one with DBC overlay
names. The client comparison below is authoritative for filenames and map
registration.

## Comparison method

TurtleHD now pairs `TurtleHD/<Map>/<Map>_Unexplored.jpg` (the fogged/base map)
with `TurtleHD/<Map>/<Map>.jpg` (the fully explored map). The audit uses the
explored JPG directly and places it beside the corresponding PandaMap source
master for visual inspection. `audit_turtle_content.py` retains a fallback
that reconstructs overlays from the client's `WorldMapOverlay.dbc` geometry
for older TurtleHD exports that do not contain the paired unexplored file.

The audit ignores color grading, texture treatment, and drawing style. A map
is marked for regeneration only when the cartographic content differs: a
location, label, road, structure, coastline, terrain shape, or other map
feature is present in one source and absent or materially different in the
other.

Run the reproducible comparison with:

```text
py -3.10 audit_turtle_content.py --output <directory>
```

For the dedicated unexplored/base-map comparison, run:

```text
py -3.10 audit_turtle_content.py --unexplored --output <directory>
```

To verify whether Turtle changes the rendered explored art rather than only
adding area or reveal metadata, compare it directly with the classic sources:

```text
py -3.10 audit_turtle_content.py --classic --output <directory>
```

## Regeneration-source inventory

The status source of truth is
`D:\Development\unrealMap_data\#Maps\zones\Turtle`. A map is marked
**Regenerated** when its explored-map source PNG is present in that folder (or
its `New-Zones` subfolder) and its 2D World and Unexplored assets are integrated.
Terrain is tracked separately because the fourteen new maps do not yet have
3D terrain renders. **Missing** means that no regenerated source PNG exists there
and the map is absent from the World, Unexplored, and Terrain packs.

The folder currently contains 31 completed sources: 17 regenerated existing
zones and fourteen new-zone sources. No outdoor 2D map sources remain missing.

### Regenerated existing maps

These 17 existing zones have regenerated explored bases and affected overlays.
The unexplored master is reused when Turtle only changes explored content and
the base geography is unchanged. The 3D terrain layer still needs a
Turtle-derived source wherever terrain itself changed; rebuilding it from the
current WoW Classic renders would preserve the known mismatch.

| Map | Asset key | Regenerated source | Turtle content | Status |
| --- | --- | --- | --- | --- |
| Wetlands | `Wetlands` | `Wetlands.png` | Hawk's Vigil; Dun Agrath | Regenerated; 2D map integrated |
| Stranglethorn Vale | `Stranglethorn` | `Stranglethorn.png` | Jaguero Isle | Regenerated; 2D map integrated with the Jaguero Isle label |
| Azshara | `Aszhara` | `Aszhara.png` | Flaxwhisker Front; Rethress Sanctum; Bloodfist Point | Regenerated; 2D map integrated |
| Swamp of Sorrows | `SwampOfSorrows` | `SwampOfSorrows.png` | Sorrowguard Keep | Regenerated; 2D map integrated |
| Durotar | `Durotar` | `Durotar.png` | Anchor's Edge; Sparkwater Port | Regenerated; 2D map integrated |
| Stonetalon Mountains | `StonetalonMountains` | `Stonetalon_Mountains.png` | Bramblethorn Pass; Bael Hardul; Blacksand Oil Fields; Venture Camp and Broken Cliff Mine; Powder Town | Regenerated; 2D map integrated |
| Badlands | `Badlands` | `Badlands.png` | Crystalline Oasis; Redbrand's Digsite; Angor Digsite; Ruins of Corthan; Scalebane Ridge | Regenerated; 2D map integrated |
| Feralas | `Feralas` | `Feralas.png` | Thalanaar; Chimaera Roost Vale | Regenerated; 2D map integrated |
| Felwood | `Felwood` | `Felwood.png` | Talonbranch Glade; Shrine of the Betrayer | Regenerated; 2D map integrated |
| Ashenvale | `Ashenvale` | `Ashenvale.png` | Forest Song | Regenerated; 2D map integrated |
| Dustwallow Marsh | `Dustwallow` | `DustWallow.png` | Deserter's Hideout; Shady Rest Inn; Blackhorn Village; Westhaven Hollow; Hermit of the Eastern Coast | Regenerated; 2D map integrated |
| Tanaris | `Tanaris` | `Tanaris.png` | Caverns of Time; Sandmoon Village | Regenerated; 2D map integrated |
| Dun Morogh | `DunMorogh` | `DunMorogh.png` | Gnomeregan Reclamation Facility | Regenerated; 2D map integrated |
| Mulgore | `Mulgore` | `mulgore.png` | Redcloud Roost; Suntail Pass | Regenerated; 2D map integrated |
| Eastern Plaguelands | `EasternPlaguelands` | `Eastern_Plaguelands.png` | Forlorn Summit | Regenerated; 2D map integrated |
| Burning Steppes | `BurningSteppes` | `BurningSteppes.png` | Karfang Hold; Hateforge Excavation | Regenerated; 2D map integrated |
| Tirisfal Glades | `Tirisfal` | `Tirisfal.png` | Tirisfal Uplands | Regenerated; 2D map integrated |

## Unexplored-map regeneration result

The unexplored audit compares PandaMap's current
`#Maps/zones_unexplored/<Map>.png` master directly with TurtleHD's
`<Map>/<Map>_Unexplored.jpg`. Color grading and drawing treatment are ignored;
regeneration is required only when the underlying coastline, mountain layout,
landmass, or other base geography changes.

Only these two existing unexplored masters required regeneration, and both are
now integrated:

| Map | Asset key | Reason | Status |
| --- | --- | --- | --- |
| Stonetalon Mountains | `StonetalonMountains` | Turtle's redesign changes the base mountain and western coastline geometry. | Regenerated and integrated |
| Tirisfal Glades | `Tirisfal` | Turtle adds changed western/left-side land, coast, mountain, and lake geometry for the Tirisfal Uplands. | Regenerated and integrated |

The current unexplored masters can be reused for these 15 regenerated explored
maps because their base geography matches Turtle: `Wetlands`, `Stranglethorn`,
`Aszhara`, `SwampOfSorrows`, `Durotar`, `Badlands`, `Feralas`,
`Felwood`, `Ashenvale`, `Dustwallow`, `Tanaris`, `DunMorogh`, `Mulgore`,
`EasternPlaguelands`, and `BurningSteppes`.

In particular, Durotar's Anchor's Edge and Sparkwater Port changes belong to
the explored content; its existing unexplored geometry does not need to be
regenerated. All 14 new map assets listed below require newly generated
unexplored bases because PandaMap has no classic versions to reuse. All
fourteen are integrated. The focused added-versus-missing checklist is in
[`TURTLE-UNEXPLORED-MAP-CHECKLIST.md`](TURTLE-UNEXPLORED-MAP-CHECKLIST.md).

### No regeneration required

| Map | Asset key | Turtle locations called out by the source page | Comparison result |
| --- | --- | --- | --- |
| Arathi Highlands | `Arathi` | Wildtusk Village; Ruins of Zul'Rasaz; Livingstone Croft; Gallant Square | No rendered map difference from the WoW Classic explored source. The client adds area and fog-reveal metadata only; do not regenerate. |
| Westfall | `Westfall` | Gartside Plot; The Westfall Church | No cartographic difference. PandaMap and the fully explored Turtle export contain the same map features; do not regenerate. |
| Stormwind | `Stormwind` | Stormwind Harbor; Kul Tiran Embassy; Little Silvermoon | Already matched. The shipped `Stormwind-turtle.png` master contains the Turtle layout; do not regenerate. |

## New Turtle map assets

All fourteen identified keys now have regenerated source PNGs and are
integrated. They have World and Unexplored pack assets and are registered in
PandaMap's catalog. None has a matching terrain render yet.

| Turtle map | Client asset key | Regenerated source | Source-page level | Native overlays | Status |
| --- | --- | --- | ---: | ---: | --- |
| Balor | `Balor` | `New-Zones/Balor.png` | Not listed on the OctoWoW page | 15 | Regenerated; World + Unexplored integrated; terrain missing |
| Grim Reaches | `GrimReaches` | `New-Zones/GrimReaches.png` | Not listed on the OctoWoW page | 16 | Regenerated; World + Unexplored integrated; terrain missing |
| Hyjal | `Hyjal` | `New-Zones/Hyjal.png` | Not listed on the OctoWoW page | 10 | Regenerated; World + Unexplored integrated; terrain missing |
| Icepoint | `Icepoint` | `New-Zones/IcePoint.png` | Not listed on the OctoWoW page | 1 | Regenerated; World + Unexplored integrated; terrain missing |
| Moonwhisper Coast | `Moonwhisper` | `New-Zones/Moonwhisper.png` | Not listed on the OctoWoW page | 17 | Regenerated; World + Unexplored integrated; terrain missing |
| Northwind | `Northwind` | `New-Zones/Northwind.png` | Not listed on the OctoWoW page | 17 | Regenerated; World + Unexplored integrated; terrain missing |
| Scarlet Enclave | `ScarletEnclave` | `New-Zones/Scarlet Enclave.png` | Not listed on the OctoWoW page | 0 | Regenerated; World + Unexplored integrated; terrain missing |
| Blackstone Island | `BlackstoneIsland` | `New-Zones/BlackstoneIsland.png` | 1-16 | 7 | Regenerated; World + Unexplored integrated; terrain missing |
| Thalassian Highlands | `ThalassianHighlands` | `New-Zones/ThalassianHighlands.png` | 15-20 (High Elf start: 1-10) | 9 | Regenerated; World + Unexplored integrated; terrain missing |
| Alah'Thalas | `AlahThalas` | `New-Zones/AlahThalas.png` | Part of the Thalassian Highlands entry | 0 | Regenerated; separate World + Unexplored map integrated; terrain missing |
| Gilneas | `Gilneas` | `New-Zones/Gilneas.png` | 39-46 | 22 | Regenerated; World + Unexplored integrated; terrain missing |
| Gillijim's Isle | `Gillijim` | `New-Zones/Gillijim.png` | 48-53 | 15 | Regenerated; World + Unexplored integrated; terrain missing |
| Island of Lapidis | `Lapidis` | `New-Zones/Lapidis.png` | 48-53 | 10 | Regenerated; World + Unexplored integrated; terrain missing |
| Tel'Abim | `TelAbim` | `New-Zones/TelAbim.png` | 54-60 | 6 | Regenerated; World + Unexplored integrated; terrain missing |

The OctoWoW page lists six new zones. The complete SD/client comparison finds
13 Turtle outdoor zones beyond the original 40-map catalog. The implementation
count is 14 map assets because Alah'Thalas is split out from Thalassian
Highlands.

`AmaniAlor` is not counted as another standalone map: the SD/HD folder has no
top-level `WorldMapArea` record and the client uses `AMANIALOR` as Stonetalon
content. Other extra SD directories were excluded because they are cities,
instances, dungeon entrances, battlegrounds, continent/world maps, or aliases.

## Native client differences missing from PandaMap metadata

Across the 17 affected existing outdoor maps plus Arathi, the current client
has 31 overlay names that are absent from `MapOverlayData.lua`. Arathi accounts
for three of those names, but its rendered artwork is unchanged; those are
metadata updates rather than map-regeneration work. A dash means the page still
requires new art, but the change reuses an existing overlay name or is baked
into the base map rather than introducing a new overlay key.

| Asset key | Client overlay names absent from PandaMap |
| --- | --- |
| `Arathi` | `FARWELLSTEAD`, `RUINSOFZULRASAZ`, `WILDTUSKVILLAGE` |
| `Wetlands` | `DUNAGRATH`, `HAWKSVIGIL` |
| `Stranglethorn` | - |
| `Aszhara` | - |
| `SwampOfSorrows` | `SORROWGUARDKEEP` |
| `Durotar` | `SPARKWATERPORT` |
| `StonetalonMountains` | `AMANIALOR`, `BAELHARDUL`, `BLACKSANDOILFIELDS`, `BRAMBLETHORNPASS`, `BROKENCLIFFMINE`, `POWDERTOWN`, `THEEARTHENRING`, `VENTURECOMPANYCAMP` |
| `Badlands` | `CRYSTALLINEPINNACLE`, `REDBRANDSDIGSITE`, `RUINSOFCORTHAN`, `SCALEBANERIDGE` |
| `Feralas` | `CHIMAERAROOSTVALE` |
| `Felwood` | - |
| `Ashenvale` | `FORESTSONG` |
| `Dustwallow` | `WESTHAVENHOLLOW` |
| `Tanaris` | `SLICKWICKOILRIG` |
| `DunMorogh` | `IRONFORGEAIRFIELDS`, `RUGFORDSMOUNTAINREST` |
| `Mulgore` | `SUNTAILPASS` |
| `EasternPlaguelands` | `FORLORNSUMMIT` |
| `BurningSteppes` | - |
| `Tirisfal` | `GLENSHIRE`, `STEEPCLIFFPORT`, `THECORINTHFARMSTEAD`, `THEWHISPERINGFOREST` |

The client is newer or more detailed than the source page in several places.
For example, Dun Morogh and Tirisfal contain additional native overlays not
named on the page, while some page labels have no standalone overlay. Do not
derive asset filenames from the editorial labels; use the client's DBC and
`Interface\WorldMap` paths.

## Verification criteria used for each integrated map

1. Capture the current client base and every native overlay, preserving the
   client's `1002 x 668` coordinate plane.
2. Produce the explored HD base and overlay art on PandaMap's `2004 x 1336`
   visible canvas and cut the standard 12-tile `512 px` grid.
3. Regenerate the HD unexplored master and 12-tile set only for Stonetalon
   Mountains and Tirisfal Glades. Reuse the existing unexplored art for the
   other 15 existing-zone regenerations; create unexplored art for every new
   map asset.
4. Produce or source Turtle-correct 3D terrain. Do not mark terrain complete
   when it is still the WoW Classic landscape for a Turtle-edited zone.
5. Add exact map and overlay keys to `MapOverlayData.lua`, `pandaMap.lua`, and
   the build-script zone catalogs. New maps must not depend on a guessed
   display-name-to-folder conversion.
6. Run `audit_native_alignment.py` against the current client and visually
   verify coastlines, roads, walls, and every new location before marking the
   map complete.

