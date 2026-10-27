# Turtle unexplored-map checklist

Last verified: 2026-10-25

This checklist covers every explored source PNG under
`D:\Development\unrealMap_data\#Maps\zones\Turtle`. The similarly written
`D:\Development\unrealMap\_data` path does not exist on the current machine.

## Current result

| Check | Count |
| --- | ---: |
| Turtle explored source PNGs | 31 |
| Distinct unexplored maps that must be built | 16 |
| Distinct unexplored maps added to PandaMap | 16 |
| Distinct unexplored maps still missing | 0 |
| Turtle-edited maps that reuse an existing unexplored base | 15 |

An unexplored map is **Added** only when all twelve files named
`<AssetKey>_Unexplored1.blp` through `<AssetKey>_Unexplored12.blp` exist in
`Packs/PandaMap_Unexplored/World_Unexplored/<AssetKey>` and the asset key is
listed in `UNEXPLORED_BASE_MAPS` in `pandaMap.lua`.

The Turtle source directory contains fully explored PNGs. The current builder
does not require separate unexplored PNG masters in that directory: for the
sixteen maps below, `build_turtle_maps.py` assembles the unexplored base from
the installed client's native map tiles and writes PandaMap's twelve BLP
tiles. If bespoke HD unexplored PNG masters are created later, these sixteen
are the complete target list.

## Must have a distinct unexplored map

These are the unexplored maps that have to be generated. All are currently
present in the add-on.

| Done | Map | Asset key | Explored source | Why distinct art is required | Pack status |
| --- | --- | --- | --- | --- | --- |
| [x] | Stonetalon Mountains | `StonetalonMountains` | `Stonetalon_Mountains.png` | Turtle changes the base terrain and coastline geometry. | Added (12/12 tiles) |
| [x] | Tirisfal Glades | `Tirisfal` | `Tirisfal.png` | Turtle changes the western land, coast, mountain, and lake geometry. | Added (12/12 tiles) |
| [x] | Alah'Thalas | `AlahThalas` | `New-Zones/AlahThalas.png` | New map key; no classic unexplored base exists. | Added (12/12 tiles) |
| [x] | Balor | `Balor` | `New-Zones/Balor.png` | New map key; no classic unexplored base exists. | Added (12/12 tiles) |
| [x] | Blackstone Island | `BlackstoneIsland` | `New-Zones/BlackstoneIsland.png` | New map key; no classic unexplored base exists. | Added (12/12 tiles) |
| [x] | Gillijim's Isle | `Gillijim` | `New-Zones/Gillijim.png` | New map key; no classic unexplored base exists. | Added (12/12 tiles) |
| [x] | Gilneas | `Gilneas` | `New-Zones/Gilneas.png` | New map key; no classic unexplored base exists. | Added (12/12 tiles) |
| [x] | Grim Reaches | `GrimReaches` | `New-Zones/GrimReaches.png` | New map key; no classic unexplored base exists. | Added (12/12 tiles) |
| [x] | Hyjal | `Hyjal` | `New-Zones/Hyjal.png` | New map key; no classic unexplored base exists. | Added (12/12 tiles) |
| [x] | Icepoint | `Icepoint` | `New-Zones/IcePoint.png` | New map key; no classic unexplored base exists. | Added (12/12 tiles) |
| [x] | Island of Lapidis | `Lapidis` | `New-Zones/Lapidis.png` | New map key; no classic unexplored base exists. | Added (12/12 tiles) |
| [x] | Moonwhisper Coast | `Moonwhisper` | `New-Zones/Moonwhisper.png` | New map key; no classic unexplored base exists. | Added (12/12 tiles) |
| [x] | Northwind | `Northwind` | `New-Zones/Northwind.png` | New map key; no classic unexplored base exists. | Added (12/12 tiles) |
| [x] | Scarlet Enclave | `ScarletEnclave` | `New-Zones/Scarlet Enclave.png` | New map key; no classic unexplored base exists. | Added (12/12 tiles) |
| [x] | Tel'Abim | `TelAbim` | `New-Zones/TelAbim.png` | New map key; no classic unexplored base exists. | Added (12/12 tiles) |
| [x] | Thalassian Highlands | `ThalassianHighlands` | `New-Zones/ThalassianHighlands.png` | New map key; no classic unexplored base exists. | Added (12/12 tiles) |

## Reuses an existing unexplored map

These Turtle explored maps do **not** need newly generated unexplored art.
Their base geography still matches the existing PandaMap unexplored master;
only explored content or exploration overlays changed.

| Map | Asset key | Explored source | Status |
| --- | --- | --- | --- |
| Ashenvale | `Ashenvale` | `Ashenvale.png` | Reuse existing unexplored base |
| Azshara | `Aszhara` | `Aszhara.png` | Reuse existing unexplored base |
| Badlands | `Badlands` | `Badlands.png` | Reuse existing unexplored base |
| Burning Steppes | `BurningSteppes` | `BurningSteppes.png` | Reuse existing unexplored base |
| Dun Morogh | `DunMorogh` | `DunMorogh.png` | Reuse existing unexplored base |
| Durotar | `Durotar` | `Durotar.png` | Reuse existing unexplored base |
| Dustwallow Marsh | `Dustwallow` | `DustWallow.png` | Reuse existing unexplored base |
| Eastern Plaguelands | `EasternPlaguelands` | `Eastern_Plaguelands.png` | Reuse existing unexplored base |
| Felwood | `Felwood` | `Felwood.png` | Reuse existing unexplored base |
| Feralas | `Feralas` | `Feralas.png` | Reuse existing unexplored base |
| Mulgore | `Mulgore` | `mulgore.png` | Reuse existing unexplored base |
| Stranglethorn Vale | `Stranglethorn` | `Stranglethorn.png` | Reuse existing unexplored base |
| Swamp of Sorrows | `SwampOfSorrows` | `SwampOfSorrows.png` | Reuse existing unexplored base |
| Tanaris | `Tanaris` | `Tanaris.png` | Reuse existing unexplored base |
| Wetlands | `Wetlands` | `Wetlands.png` | Reuse existing unexplored base |

## Updating this checklist

When another PNG is added below the Turtle source directory:

1. Add it to `SOURCE_FILES` in `build_turtle_maps.py`.
2. If it is a new client map key, add it to `NEW_MAPS`; it will automatically
   be included in `REBUILD_UNEXPLORED`.
3. If it is an existing map whose base geography changed, add its asset key
   directly to `REBUILD_UNEXPLORED`. Otherwise, document it in the reuse table.
4. Run `build_turtle_maps.py` for the asset key.
5. Mark it **Added** only after verifying the exact twelve unexplored BLP tiles
   and its `UNEXPLORED_BASE_MAPS` registration.

An unchecked row in the distinct-map table, or fewer than twelve output
tiles, means the unexplored map is still missing.
