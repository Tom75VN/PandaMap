local TILE_COUNT = 12
local MAX_OVERLAY_TILES = 64
local DRIVER_INTERVAL = 0.2
local TERRAIN_FADE_DURATION = 0.3

local UNEXPLORED_CATEGORY = "World_Unexplored"
local TERRAIN_CATEGORY = "World_Terrain"
local CATEGORY_PACKS = {
  Battlegrounds = "PandaMap_World",
  Capitals = "PandaMap_World",
  Continents = "PandaMap_World",
  World = "PandaMap_World",
  World_Unexplored = "PandaMap_Unexplored",
  World_Terrain = "PandaMap_Terrain",
}
-- Every data pack, in the order the settings page lists them.
local PACKS = { "PandaMap_World", "PandaMap_Unexplored", "PandaMap_Terrain" }
local KNOWN_PACKS = {
  PandaMap_World = true,
  PandaMap_Unexplored = true,
  PandaMap_Terrain = true,
}
local packRoots = {}

-- Packs are separate addons. Each one registers its own texture root after
-- PandaMap loads; the repository's development shim registers the legacy
-- nested roots so a checkout in Interface/AddOns/pandaMap still runs in game.
local function RegisterPack(pack, root)
  if not KNOWN_PACKS[pack] or type(root) ~= "string" or root == "" then
    return false
  end
  root = string.gsub(root, "/", "\\")
  if string.sub(root, -1) ~= "\\" then root = root .. "\\" end
  packRoots[pack] = root
  return true
end

local function IsPackInstalled(pack)
  return packRoots[pack] ~= nil
end

-- 3D terrain (build_terrain_tiles.py): from this zoom on, a zone's base tiles
-- show the top-down terrain render instead of the parchment map. The tiles
-- are cut on the client's WorldMapArea frame, the plane the HD maps and every
-- map position use, so they take no TILE_TRANSFORMS entry.
local TERRAIN_ZOOM = 3

-- HD artwork that is offset from the client's own map art (Interface\WorldMap
-- tiles in the client MPQs), measured by audit_native_alignment.py. Each entry
-- places HD point p at native = scale * p + offset, in map units (y down):
-- scale X, scale Y, offset X, offset Y. Unlisted maps already match within
-- about half a unit. Base tiles are keyed by tile stem, overlays by map.
-- Unexplored bases built by build_unexplored_tiles.py are aligned in the
-- files; the explored-stem entries are that script's reference geometry.
local TILE_TRANSFORMS = {
  Alterac_Unexplored = { 0.99838, 1.00013, 6.31, 4.15 },
  Arathi_Unexplored = { 1.00136, 1.00155, -1.78, -0.33 },
  Elwynn_Unexplored = { 1.00126, 0.99815, -1.27, 0.76 },
  SearingGorge = { 0.99757, 0.99962, 1.37, 0.10 },
  Silithus = { 0.99752, 1.00054, 0.35, -1.37 },
}
local OVERLAY_TRANSFORMS = {
  Alterac = { 0.99806, 1.00077, 6.18, 4.02 },
  SearingGorge = TILE_TRANSFORMS.SearingGorge,
  Silithus = TILE_TRANSFORMS.Silithus,
}

local function CategoryRoot(category)
  local root = packRoots[CATEGORY_PACKS[category]]
  return root and root .. category .. "\\" or nil
end

local MAP_CATEGORIES = {
  AlteracValley = "Battlegrounds",
  ArathiBasin = "Battlegrounds",
  Azeroth = "Continents",
  Darnassis = "Capitals",
  Ironforge = "Capitals",
  Kalimdor = "Continents",
  Ogrimmar = "Capitals",
  Stormwind = "Capitals",
  ThunderBluff = "Capitals",
  Undercity = "Capitals",
  WarsongGulch = "Battlegrounds",
  World = "Continents",
}

local UNEXPLORED_BASE_MAPS = {
  AlahThalas = true, Alterac = true, Arathi = true, Ashenvale = true,
  Aszhara = true,
  Badlands = true, Balor = true, Barrens = true, BlackstoneIsland = true,
  BlastedLands = true, BurningSteppes = true,
  Darkshore = true, DeadwindPass = true, Desolace = true, DunMorogh = true,
  Durotar = true, Duskwood = true, Dustwallow = true,
  EasternPlaguelands = true, Elwynn = true, Felwood = true, Feralas = true,
  Gillijim = true, Gilneas = true, GrimReaches = true, Hilsbrad = true,
  Hinterlands = true, Hyjal = true, Icepoint = true, Lapidis = true,
  LochModan = true, Moonglade = true, Moonwhisper = true, Mulgore = true,
  Northwind = true, Redridge = true, ScarletEnclave = true,
  SearingGorge = true, Silithus = true,
  Silverpine = true, StonetalonMountains = true, Stranglethorn = true,
  SwampOfSorrows = true, Tanaris = true, TelAbim = true, Teldrassil = true,
  ThalassianHighlands = true,
  ThousandNeedles = true, Tirisfal = true, UngoroCrater = true,
  WesternPlaguelands = true, Westfall = true, Wetlands = true,
  Winterspring = true,
}
-- The original 40 outdoor zones have a 3D terrain base. The new Turtle maps
-- stay on parchment at x3 until matching terrain renders are available.
local TERRAIN_BASE_MAPS = UNEXPLORED_BASE_MAPS
local TERRAIN_BASE_EXCLUSIONS = {
  AlahThalas = true, Balor = true, BlackstoneIsland = true, Gillijim = true,
  Gilneas = true, GrimReaches = true, Hyjal = true, Icepoint = true,
  Lapidis = true, Moonwhisper = true, Northwind = true,
  ScarletEnclave = true, TelAbim = true, ThalassianHighlands = true,
}

local MAP_OVERLAYS = {
  AlteracValley = {
    "DunBaldar1", "DunBaldar2", "FrostwolfKeep1", "FrostwolfKeep2",
    "IcebloodGarrison1", "IcebloodGarrison2", "IcebloodGarrison3",
    "IcebloodGarrison4",
  },
  ArathiBasin = {},
  Azeroth = {},
  Darnassis = {},
  Ironforge = {},
  Kalimdor = {},
  Ogrimmar = {},
  Stormwind = {},
  ThunderBluff = {},
  Undercity = {},
  WarsongGulch = {},
  World = {},
}

local OVERLAY_EXCLUSIONS = {
  DeadwindPass = {
    karazhan1 = true, karazhan2 = true, thevice1 = true, thevice2 = true,
    thevice3 = true, thevice4 = true,
  },
}

do
  local mapName
  for mapName in pairs(PandaMapOverlayData) do
    if mapName ~= "AlteracValley" then
      MAP_CATEGORIES[mapName] = "World"
    end
  end
end

-- 1.12-derived clients can report corrected or legacy map keys that differ from the
-- shipped asset catalog names.
local MAP_ASSET_NAMES = {
  Blastedlands = "BlastedLands",
  Darnassus = "Darnassis",
  HinterLands = "Hinterlands",
  Orgrimmar = "Ogrimmar",
  TheBlastedLands = "BlastedLands",
  TheHinterlands = "Hinterlands",
  UnGoroCrater = "UngoroCrater",
}

local function AssetMapName(mapName)
  return MAP_ASSET_NAMES[mapName] or mapName
end

local function AssetRoot(mapName)
  local assetMapName = AssetMapName(mapName)
  local category = MAP_CATEGORIES[assetMapName]
  if not category then return nil end
  local root = CategoryRoot(category)
  return root and root .. assetMapName or nil
end

local function MapPacksInstalled(mapName)
  local category = MAP_CATEGORIES[AssetMapName(mapName)]
  return category ~= nil and IsPackInstalled(CATEGORY_PACKS[category])
end

-- A zone with a themed unexplored master keeps its standard base in
-- PandaMap_World. The bundled PandaMap_Unexplored set adds a second base,
-- <Map>_Unexplored1..12; overlays are shared.
local function UsesUnexploredBase(assetMapName)
  return UNEXPLORED_BASE_MAPS[assetMapName] == true
end

local function UsesUnexploredPack(assetMapName)
  return UsesUnexploredBase(assetMapName)
    and IsPackInstalled("PandaMap_Unexplored")
end

local function AssetTileRoot(mapName, terrain)
  local assetMapName = AssetMapName(mapName)
  if terrain then
    local root = CategoryRoot(TERRAIN_CATEGORY)
    return root and root .. assetMapName or nil
  end
  if UsesUnexploredPack(assetMapName) then
    local root = CategoryRoot(UNEXPLORED_CATEGORY)
    return root and root .. assetMapName or nil
  end
  return AssetRoot(assetMapName)
end

local function AssetTileStem(mapName, terrain)
  local assetMapName = AssetMapName(mapName)
  if terrain then return assetMapName .. "_Terrain" end
  if UsesUnexploredPack(assetMapName) then
    return assetMapName .. "_Unexplored"
  end
  return assetMapName
end

-- The zoom of whichever addon owns the map zoom: PandaMap's own MapZoom, or
-- pandaUI's worldmapzoom module. 1 when neither is installed.
local pandaUIZoomState

-- Also returns which zoom answered, for /pmap terrain.
local function CurrentZoom()
  local own = _G["PandaMapZoom"]
  if type(own) == "table" and type(own.IsInstalled) == "function"
      and own.IsInstalled() then
    return tonumber(own.GetZoom()) or 1, "pandaMap"
  end
  if not pandaUIZoomState then
    local hostUI = _G["PandaUI"]
    if type(hostUI) ~= "table" or type(hostUI.GetModule) ~= "function" then
      return 1, "none"
    end
    local ok, module = pcall(hostUI.GetModule, "worldmapzoom")
    if not ok or type(module) ~= "table" or type(module.state) ~= "table" then
      return 1, "none"
    end
    pandaUIZoomState = module.state
  end
  if not pandaUIZoomState.installed then return 1, "pandaUI (not installed)" end
  return tonumber(pandaUIZoomState.zoom) or 1, "pandaUI"
end

local function IsTerrainEnabled()
  local db = _G["PandaMapDB"]
  return not (type(db) == "table" and db.terrain3D == false)
end

local function WantsTerrain(assetMapName)
  return assetMapName ~= nil and TERRAIN_BASE_MAPS[assetMapName] == true
    and not TERRAIN_BASE_EXCLUSIONS[assetMapName]
    and IsPackInstalled("PandaMap_Terrain")
    and IsTerrainEnabled() and CurrentZoom() >= TERRAIN_ZOOM
end

-- The client resolves addon texture paths by basename alone (probe
-- mapbasename.v1), so overlay stems shared with another shipped file carry
-- their map name on disk. Keep in sync with map_geometry.RUNTIME_PREFIXED.
local OVERLAY_FILE_PREFIXED = {
  BlastedLands = { altarofstorms = true },
  BurningSteppes = { altarofstorms = true },
  DunMorogh = { ironforge = true },
  EasternPlaguelands = { thondrorilriver = true },
  Elwynn = { stormwind = true },
  Mulgore = { thunderbluff = true },
  WesternPlaguelands = { thondrorilriver = true },
}

-- Keep only the active map's basename lookup. The geometry catalog is bounded,
-- but duplicating every overlay name at startup wastes memory for maps that
-- are not being viewed.
local overlayLookupMap
local overlayLookup = {}

local function AddOverlayName(mapName, name, prefixed)
  local key = string.lower(name)
  local stem = string.gsub(key, "%d+$", "")
  if prefixed and prefixed[stem] then
    overlayLookup[key] = mapName .. name
  else
    overlayLookup[key] = name
  end
end

local function OverlayNames(mapName)
  if overlayLookupMap == mapName then return overlayLookup end
  local key
  for key in pairs(overlayLookup) do overlayLookup[key] = nil end
  local prefixed = OVERLAY_FILE_PREFIXED[mapName]
  local names = MAP_OVERLAYS[mapName]
  local i
  if type(names) == "table" then
    for i = 1, table.getn(names) do
      AddOverlayName(mapName, names[i], prefixed)
    end
  else
    local encoded = PandaMapOverlayData[mapName]
    local excluded = OVERLAY_EXCLUSIONS[mapName]
    if type(encoded) == "table" then
      for i = 1, table.getn(encoded) do
        local _, _, stem, width, height = string.find(
          encoded[i], "^(%w+):(%d+):(%d+):%d+:%d+$")
        width, height = tonumber(width), tonumber(height)
        if stem and width and height then
          local pieces = math.floor((width + 255) / 256)
            * math.floor((height + 255) / 256)
          local piece
          for piece = 1, pieces do
            local name = stem .. piece
            if not excluded or not excluded[string.lower(name)] then
              AddOverlayName(mapName, name, prefixed)
            end
          end
        end
      end
      AddOverlayName(mapName, mapName .. "Highlight", prefixed)
    end
  end
  overlayLookupMap = mapName
  return overlayLookup
end

local activeMap
local presentationActive = false
local overlayReplacementEnabled = true
local driver
local driverLastTick = 0
local driverStartedAt = 0
local driverAwaitingTextures = false
local tilesConcealed = false
local revealTicks = 0
local worldMap = _G["WorldMapFrame"]
local ResetRevealCache
local detailTiles = {}
local detailTilesReady = false
local activeTileMap
local activeTileTerrain = false
local activeTilePaths = {}
local transformedArtworkRegions = {}
local terrainShown = false        -- the bound base is the 3D terrain
local overlaysMuted = false       -- overlay slots set to alpha 0 for it
local terrainFadeFrame
local terrainFadeTiles = {}
local terrainFadeOverlays = {}
local terrainFadeRegions = {}
local terrainFadeStartedAt = 0
local terrainFadeActive = false

local function Now()
  if type(GetTime) ~= "function" then return 0 end
  local ok, value = pcall(GetTime)
  return ok and type(value) == "number" and value or 0
end

local function NormalizePath(path)
  if type(path) ~= "string" then return nil end
  return string.lower(string.gsub(path, "\\", "/"))
end

local function HasPackPrefix(path)
  path = NormalizePath(path)
  if not path then return false end
  local _, root
  for _, root in pairs(packRoots) do
    root = NormalizePath(root)
    if root and string.sub(path, 1, string.len(root)) == root then return true end
  end
  return false
end

local function TextureBasename(path)
  local normalized = NormalizePath(path)
  if not normalized then return nil end
  local _, _, basename = string.find(normalized, "([^/]+)$")
  return basename
end

local function SamePath(left, right)
  if left == right then return true end
  return NormalizePath(left) == NormalizePath(right)
end

local function SafeTexture(region)
  if not region or type(region.GetTexture) ~= "function" then return nil end
  local ok, value = pcall(region.GetTexture, region)
  return ok and value or nil
end

local function ResolveTiles()
  if detailTilesReady then return detailTiles end
  local i
  for i = 1, TILE_COUNT do
    local tile = _G["WorldMapDetailTile" .. i]
    if not tile or type(tile.SetTexture) ~= "function" then
      return nil
    end
    detailTiles[i] = tile
  end
  detailTilesReady = true
  return detailTiles
end

local function ReadArtworkGeometry(region)
  if not region or type(region.GetPoint) ~= "function"
      or type(region.GetWidth) ~= "function"
      or type(region.GetHeight) ~= "function" then
    return nil
  end
  local ok, point, relativeTo, relativePoint, x, y =
    pcall(region.GetPoint, region, 1)
  if not ok or not point or type(x) ~= "number" or type(y) ~= "number" then
    return nil
  end
  local widthOk, width = pcall(region.GetWidth, region)
  local heightOk, height = pcall(region.GetHeight, region)
  if not widthOk or not heightOk or type(width) ~= "number"
      or type(height) ~= "number" or width <= 0 or height <= 0 then
    return nil
  end
  return {
    point = point,
    relativeTo = relativeTo,
    relativePoint = relativePoint,
    x = x,
    y = y,
    width = width,
    height = height,
  }
end

local function IsTransformedArtworkRegion(region, state)
  if not state or not state.transform then return false end
  local current = ReadArtworkGeometry(region)
  if not current then return false end
  local transform = state.transform
  if math.abs(current.width - state.width * transform[1]) >= 0.05
      or math.abs(current.height - state.height * transform[2]) >= 0.05 then
    return false
  end
  if not state.transformPoint then return true end
  return current.point == state.point
    and current.relativeTo == state.relativeTo
    and current.relativePoint == state.relativePoint
    and math.abs(current.x - (state.x * transform[1] + transform[3])) < 0.05
    and math.abs(current.y - (state.y * transform[2] - transform[4])) < 0.05
end

local function ShouldRecaptureArtworkGeometry(region, texture)
  if HasPackPrefix(texture) then return false end
  return not IsTransformedArtworkRegion(region,
    transformedArtworkRegions[region])
end

-- Correct only the artwork geometry. WorldMapButton remains the client's
-- untouched 1002 x 668 coordinate plane used by POIs, quest areas and clicks.
local function TransformArtworkRegion(region, transform, recapture,
    transformPoint)
  if not region or not transform or type(region.SetWidth) ~= "function"
      or type(region.SetHeight) ~= "function" then
    return false
  end
  local state = transformedArtworkRegions[region]
  if recapture or not state or state.transform ~= transform
      or state.transformPoint ~= transformPoint then
    state = ReadArtworkGeometry(region)
    if not state then return false end
    state.transform = transform
    state.transformPoint = transformPoint and true or false
    transformedArtworkRegions[region] = state
  end
  if IsTransformedArtworkRegion(region, state) then return true end

  pcall(region.SetWidth, region, state.width * transform[1])
  pcall(region.SetHeight, region, state.height * transform[2])
  if state.transformPoint then
    if type(region.ClearAllPoints) ~= "function"
        or type(region.SetPoint) ~= "function" then
      return false
    end
    pcall(region.ClearAllPoints, region)
    return pcall(region.SetPoint, region, state.point, state.relativeTo,
      state.relativePoint, state.x * transform[1] + transform[3],
      state.y * transform[2] - transform[4])
  end
  return true
end

local function RestoreArtworkRegions()
  local region, state
  for region, state in pairs(transformedArtworkRegions) do
    -- If the native updater has already reused this slot for another map, its
    -- new geometry wins. Restore only regions still carrying our transform.
    if IsTransformedArtworkRegion(region, state) then
      if type(region.SetWidth) == "function" then
        pcall(region.SetWidth, region, state.width)
      end
      if type(region.SetHeight) == "function" then
        pcall(region.SetHeight, region, state.height)
      end
      if state.transformPoint and type(region.ClearAllPoints) == "function"
          and type(region.SetPoint) == "function" then
        pcall(region.ClearAllPoints, region)
        pcall(region.SetPoint, region, state.point, state.relativeTo,
          state.relativePoint, state.x, state.y)
      end
    end
  end
  transformedArtworkRegions = {}
end

local function TilePaths(mapName, terrain)
  terrain = terrain and true or false
  if activeTileMap == mapName and activeTileTerrain == terrain then
    return activeTilePaths
  end
  local assetRoot = AssetTileRoot(mapName, terrain)
  if not assetRoot then return nil end
  local root = assetRoot .. "\\" .. AssetTileStem(mapName, terrain)
  local i
  for i = 1, TILE_COUNT do activeTilePaths[i] = root .. i end
  activeTileMap, activeTileTerrain = mapName, terrain
  return activeTilePaths
end

-- The terrain shows the whole zone, so the exploration overlays are hidden
-- with alpha while it is up. The native updater shows and hides overlay
-- slots but never sets their alpha.
local function SetOverlaysMuted(muted)
  if not muted and not overlaysMuted then return end
  local alpha = muted and 0 or 1
  local i
  for i = 1, MAX_OVERLAY_TILES do
    local overlay = _G["WorldMapOverlay" .. i]
    -- Only write a changed alpha: identical writes every tick still cost
    -- (perf.reanchoring_many_frames_per_tick_stutters).
    if overlay and type(overlay.SetAlpha) == "function"
        and type(overlay.GetAlpha) == "function" then
      local ok, current = pcall(overlay.GetAlpha, overlay)
      if not ok or current ~= alpha then
        pcall(overlay.SetAlpha, overlay, alpha)
      end
    end
  end
  overlaysMuted = muted and true or false
end

-- Preserve the outgoing map briefly above the newly bound one. Because the
-- new map is already fully visible below it, fading this snapshot produces a
-- true parchment/terrain cross-fade without changing the alpha that the
-- native updater expects on its own texture slots.
local function EnsureTerrainFadeRegions()
  if terrainFadeFrame then return true end
  local detail = _G["WorldMapDetailFrame"]
  if not detail or type(detail.CreateTexture) ~= "function" then return false end
  terrainFadeFrame = CreateFrame("Frame", "PandaMapTerrainFadeFrame", detail)
  pcall(terrainFadeFrame.SetPoint, terrainFadeFrame, "TOPLEFT", detail,
    "TOPLEFT", 0, 0)
  pcall(terrainFadeFrame.SetPoint, terrainFadeFrame, "BOTTOMRIGHT", detail,
    "BOTTOMRIGHT", 0, 0)
  if type(detail.GetFrameLevel) == "function"
      and type(terrainFadeFrame.SetFrameLevel) == "function" then
    local ok, level = pcall(detail.GetFrameLevel, detail)
    if ok and type(level) == "number" then
      pcall(terrainFadeFrame.SetFrameLevel, terrainFadeFrame, level + 1)
    end
  end
  local i
  for i = 1, TILE_COUNT do
    local region = terrainFadeFrame:CreateTexture(nil, "ARTWORK")
    terrainFadeTiles[i] = region
    table.insert(terrainFadeRegions, region)
  end
  for i = 1, MAX_OVERLAY_TILES do
    local region = terrainFadeFrame:CreateTexture(nil, "OVERLAY")
    terrainFadeOverlays[i] = region
    table.insert(terrainFadeRegions, region)
  end
  terrainFadeFrame:Hide()
  return true
end

local function ClearTerrainFade()
  terrainFadeActive = false
  terrainFadeStartedAt = 0
  if terrainFadeFrame then terrainFadeFrame:Hide() end
  local i
  for i = 1, table.getn(terrainFadeRegions) do
    local region = terrainFadeRegions[i]
    region:Hide()
    region:SetTexture("")
  end
end

local function CopyFadeTexture(source, target, replacements)
  local texture = SafeTexture(source)
  if type(texture) ~= "string" or texture == "" then return false end
  if type(source.IsShown) == "function" then
    local ok, shown = pcall(source.IsShown, source)
    if ok and not shown then return false end
  end
  local alpha = 1
  if type(source.GetAlpha) == "function" then
    local ok, value = pcall(source.GetAlpha, source)
    if ok and type(value) == "number" then alpha = value end
  end
  if alpha <= 0 then return false end
  local geometry = ReadArtworkGeometry(source)
  if not geometry then return false end

  target:Hide()
  target:ClearAllPoints()
  target:SetWidth(geometry.width)
  target:SetHeight(geometry.height)
  local relativeTo = replacements[geometry.relativeTo] or geometry.relativeTo
  target:SetPoint(geometry.point, relativeTo, geometry.relativePoint,
    geometry.x, geometry.y)
  target:SetTexture(texture)
  if type(source.GetTexCoord) == "function"
      and type(target.SetTexCoord) == "function" then
    local ok, ulx, uly, llx, lly, urx, ury, lrx, lry =
      pcall(source.GetTexCoord, source)
    if ok and type(lry) == "number" then
      target:SetTexCoord(ulx, uly, llx, lly, urx, ury, lrx, lry)
    elseif ok and type(ulx) == "number" and type(uly) == "number"
        and type(llx) == "number" and type(lly) == "number" then
      target:SetTexCoord(ulx, uly, llx, lly)
    end
  end
  target:SetAlpha(alpha)
  target:Show()
  return true
end

local function BeginTerrainFade(tiles)
  if not EnsureTerrainFadeRegions() then return end
  ClearTerrainFade()
  local replacements = {
    [_G["WorldMapDetailFrame"]] = terrainFadeFrame,
  }
  local i
  for i = 1, TILE_COUNT do replacements[tiles[i]] = terrainFadeTiles[i] end
  for i = 1, MAX_OVERLAY_TILES do
    local overlay = _G["WorldMapOverlay" .. i]
    if overlay then replacements[overlay] = terrainFadeOverlays[i] end
  end
  local copied = false
  for i = 1, TILE_COUNT do
    if CopyFadeTexture(tiles[i], terrainFadeTiles[i], replacements) then
      copied = true
    end
  end
  for i = 1, MAX_OVERLAY_TILES do
    local overlay = _G["WorldMapOverlay" .. i]
    if overlay then
      CopyFadeTexture(overlay, terrainFadeOverlays[i], replacements)
    end
  end
  if copied then
    terrainFadeStartedAt = Now()
    terrainFadeActive = true
    terrainFadeFrame:SetAlpha(1)
    terrainFadeFrame:Show()
  end
end

local function StepTerrainFade(now)
  if not terrainFadeActive then return end
  local elapsed = now - terrainFadeStartedAt
  local progress = elapsed / TERRAIN_FADE_DURATION
  if progress >= 1 then
    ClearTerrainFade()
    return
  end
  if progress < 0 then progress = 0 end
  -- Smoothstep avoids a visible jolt at either end of the transition.
  local eased = progress * progress * (3 - 2 * progress)
  terrainFadeFrame:SetAlpha(1 - eased)
end

local function ReleaseMapCaches()
  local i
  for i = 1, TILE_COUNT do activeTilePaths[i] = nil end
  activeTileMap, activeTileTerrain = nil, false
  local key
  for key in pairs(overlayLookup) do overlayLookup[key] = nil end
  overlayLookupMap = nil
  if ResetRevealCache then ResetRevealCache() end
end

local function CurrentMapName()
  if type(GetMapInfo) ~= "function" then return nil end
  local ok, name = pcall(GetMapInfo)
  if ok and type(name) == "string" then return name end
  local texture = NormalizePath(SafeTexture(_G["WorldMapDetailTile1"]))
  if texture and string.find(texture, "/world/world1$") then return "World" end
  return nil
end

local function IsSupportedMap(name)
  local assetMapName = name and AssetMapName(name) or nil
  return assetMapName ~= nil and MAP_CATEGORIES[assetMapName] ~= nil
end

local function MapHasOverlays(mapName)
  local names = MAP_OVERLAYS[mapName]
  if type(names) == "table" then return table.getn(names) > 0 end
  local encoded = PandaMapOverlayData[mapName]
  return type(encoded) == "table" and table.getn(encoded) > 0
end

local function HasActiveOverlayTexture()
  local i
  for i = 1, MAX_OVERLAY_TILES do
    local overlay = _G["WorldMapOverlay" .. i]
    local texture = SafeTexture(overlay)
    if type(texture) == "string" and texture ~= "" then return true end
  end
  return false
end

local function HasHDBaseTile()
  return HasPackPrefix(SafeTexture(_G["WorldMapDetailTile1"]))
end

local function SelectedMap()
  local name = CurrentMapName()
  if IsSupportedMap(name) then return name end
  if activeMap and HasHDBaseTile() then return activeMap end
  return nil
end

-- A map whose pack is missing stays native.
local function BindingMap()
  local mapName = SelectedMap()
  if mapName and MapPacksInstalled(mapName) then return mapName end
  return nil
end

local function IsWorldMapVisible()
  if not worldMap or type(worldMap.IsVisible) ~= "function" then return false end
  local ok, visible = pcall(worldMap.IsVisible, worldMap)
  return ok and visible and true or false
end

-- Overlay textures are the verified open-map signal; maps without overlays
-- (cities) fall back to a bound base tile. A zone with nothing explored and
-- fog kept draws no overlay, so it uses the base tile while the map is visible.
local function IsPresented(mapName)
  if HasActiveOverlayTexture() then return true end
  local assetMapName = mapName and AssetMapName(mapName) or nil
  if not assetMapName then return false end
  if MapHasOverlays(assetMapName) and not IsWorldMapVisible() then
    return false
  end
  local texture = SafeTexture(_G["WorldMapDetailTile1"])
  return type(texture) == "string" and texture ~= ""
end

local function ConcealCityTiles(mapName)
  local assetMapName = mapName and AssetMapName(mapName) or nil
  if not assetMapName or MapHasOverlays(assetMapName) then return end
  local tiles = ResolveTiles()
  if not tiles then return end
  local i
  for i = 1, TILE_COUNT do
    if type(tiles[i].Hide) == "function" then pcall(tiles[i].Hide, tiles[i]) end
  end
  tilesConcealed = true
  revealTicks = 1
end

local function CityTilesReady(mapName)
  local assetMapName = mapName and AssetMapName(mapName) or nil
  if not assetMapName or MapHasOverlays(assetMapName) then
    return true
  end
  local tiles = ResolveTiles()
  if not tiles then return false end
  local paths = TilePaths(assetMapName)
  if not paths then return false end
  local i
  for i = 1, TILE_COUNT do
    if not SamePath(SafeTexture(tiles[i]), paths[i]) then
      return false
    end
  end
  return true
end

local function RevealTiles()
  revealTicks = 0
  if not tilesConcealed then return end
  local tiles = ResolveTiles()
  local i
  if tiles then
    for i = 1, TILE_COUNT do
      if type(tiles[i].Show) == "function" then pcall(tiles[i].Show, tiles[i]) end
    end
  end
  tilesConcealed = false
end

local function ClearBindings(keepConcealed)
  ClearTerrainFade()
  RestoreArtworkRegions()
  SetOverlaysMuted(false)
  terrainShown = false
  local tiles = ResolveTiles()
  local i
  if tiles then
    for i = 1, TILE_COUNT do
      if HasPackPrefix(SafeTexture(tiles[i])) then
        pcall(tiles[i].SetTexture, tiles[i], "")
      end
    end
  end

  for i = 1, MAX_OVERLAY_TILES do
    local overlay = _G["WorldMapOverlay" .. i]
    if overlay and type(overlay.SetTexture) == "function"
        and HasPackPrefix(SafeTexture(overlay)) then
      pcall(overlay.SetTexture, overlay, "")
    end
  end
  activeMap = nil
  ReleaseMapCaches()
  if not keepConcealed then RevealTiles() end
end

local function ApplyOverlays(mapName, transform)
  if not overlayReplacementEnabled then return 0 end
  local assetMapName = AssetMapName(mapName)
  local names = OverlayNames(assetMapName)
  local assetRoot = AssetRoot(assetMapName)
  if not assetRoot then return 0 end
  local root = assetRoot .. "\\"
  local bound = 0
  local i
  for i = 1, MAX_OVERLAY_TILES do
    local overlay = _G["WorldMapOverlay" .. i]
    if overlay and type(overlay.SetTexture) == "function" then
      local current = SafeTexture(overlay)
      local recaptureGeometry =
        ShouldRecaptureArtworkGeometry(overlay, current)
      local basename = TextureBasename(current)
      local replacement = basename and names[basename] or nil
      if replacement then
        local path = root .. replacement
        if not SamePath(current, path) then
          pcall(overlay.SetTexture, overlay, path)
        end
        if transform then
          TransformArtworkRegion(overlay, transform, recaptureGeometry, true)
        end
        bound = bound + 1
      end
    end
  end
  return bound
end

local function ApplyReplacement(force)
  if not presentationActive and not force then return false end
  local mapName = BindingMap()
  if not mapName then
    ClearBindings()
    return false
  end
  -- Map switch: drop the previous map's bindings, including hidden overlay
  -- slots the native updater did not reuse.
  if activeMap and activeMap ~= mapName then ClearBindings(tilesConcealed) end

  local tiles = ResolveTiles()
  if not tiles then
    RevealTiles()
    return false
  end

  local assetMapName = AssetMapName(mapName)
  local terrain = WantsTerrain(assetMapName)
  if terrain ~= terrainShown then
    if activeMap == mapName then BeginTerrainFade(tiles) end
    -- The terrain sits on the native frame: drop the HD artwork transforms
    -- when it comes up; they are captured again when the HD base returns.
    RestoreArtworkRegions()
    terrainShown = terrain
  end
  local transform = not terrain and TILE_TRANSFORMS[AssetTileStem(assetMapName)]
    or nil
  local paths = TilePaths(assetMapName, terrain)
  if not paths then
    ClearBindings()
    return false
  end
  local i
  for i = 1, TILE_COUNT do
    local current = SafeTexture(tiles[i])
    local recaptureGeometry =
      ShouldRecaptureArtworkGeometry(tiles[i], current)
    if not SamePath(current, paths[i]) then
      pcall(tiles[i].SetTexture, tiles[i], paths[i])
    end
    if transform then
      -- Tile 1 owns the mosaic origin. The other tiles keep their native
      -- chained anchors; scaling their dimensions scales the complete image.
      TransformArtworkRegion(tiles[i], transform, recaptureGeometry, i == 1)
    end
  end
  if terrain then
    SetOverlaysMuted(true)
  else
    SetOverlaysMuted(false)
    ApplyOverlays(mapName, OVERLAY_TRANSFORMS[assetMapName])
  end
  activeMap = mapName
  if tilesConcealed then revealTicks = 1 end
  return true
end

-- Driver history for /pmap terrain: starts, stops and why, the last error.
local diag = { starts = 0, stops = 0, updates = 0 }

local function StopDriver(clear, reason)
  if presentationActive then
    diag.stops = diag.stops + 1
    diag.lastStop = reason or "?"
  end
  presentationActive = false
  driverAwaitingTextures = false
  driverStartedAt = 0
  if driver then
    driver:SetScript("OnUpdate", nil)
    driver:Hide()
  end
  if clear then ClearBindings() end
end

local function DriverUpdate()
  local now = Now()
  StepTerrainFade(now)
  if driverStartedAt <= 0 then driverStartedAt = now end
  local mapName = BindingMap()
  if not mapName then
    StopDriver(true, "driver: no supported map")
    return
  end
  if not IsPresented(mapName) or not IsWorldMapVisible() then
    if driverAwaitingTextures and now - driverStartedAt < 2 then return end
    StopDriver(true, "driver: map not presented")
    return
  end
  driverAwaitingTextures = false
  if not CityTilesReady(mapName) then
    ConcealCityTiles(mapName)
  end
  if tilesConcealed and revealTicks > 0 then
    if CityTilesReady(mapName) then
      revealTicks = revealTicks - 1
      if revealTicks == 0 then RevealTiles() end
    else
      revealTicks = 1
    end
  end
  -- A zoom across TERRAIN_ZOOM swaps the base at once, not on the next tick.
  if now - driverLastTick < DRIVER_INTERVAL
      and WantsTerrain(AssetMapName(mapName)) == terrainShown then
    return
  end
  driverLastTick = now
  ApplyReplacement()
end

-- Errors are kept for /pmap terrain, then raised as before.
local function DriverOnUpdate()
  local ok, err = pcall(DriverUpdate)
  if not ok then
    diag.lastError = tostring(err)
    error(err, 0)
  end
end

local function StartDriver(deferApply)
  if deferApply then
    local mapName = BindingMap()
    ConcealCityTiles(mapName)
  end
  if presentationActive then
    if deferApply then
      driverAwaitingTextures = true
      driverStartedAt = Now()
      driverLastTick = 0
    else
      ApplyReplacement()
    end
    return
  end
  if not driver then
    driver = CreateFrame("Frame", "PandaMapBindingDriver",
      _G["WorldFrame"] or UIParent)
  end
  presentationActive = true
  diag.starts = diag.starts + 1
  driverAwaitingTextures = deferApply and true or false
  driverStartedAt = 0
  driverLastTick = 0
  driver:Show()
  driver:SetScript("OnUpdate", DriverOnUpdate)
  if not deferApply then ApplyReplacement() end
end

-- The HD overlays were cut for the 1.12 overlay geometry in
-- PandaMapOverlayData. OctoWoW's WorldMapOverlay.dbc crops and moves the same
-- overlays (5-20 units per overlay), so while the native updater lays out a
-- map PandaMap replaces, it receives the geometry the HD art was cut for.
-- Overlays without HD art keep the client geometry.
local mapUpdateActive = false
local authoredGeometryMap
local authoredGeometry = {}

local function AuthoredOverlayGeometry(path)
  if not overlayReplacementEnabled then return nil end
  local mapName = CurrentMapName()
  if not IsSupportedMap(mapName) or not MapPacksInstalled(mapName) then
    return nil
  end
  local assetMapName = AssetMapName(mapName)
  if authoredGeometryMap ~= assetMapName then
    local key
    for key in pairs(authoredGeometry) do authoredGeometry[key] = nil end
    authoredGeometryMap = assetMapName
    local encoded = PandaMapOverlayData[assetMapName]
    local excluded = OVERLAY_EXCLUSIONS[assetMapName]
    local i
    if type(encoded) == "table" then
      for i = 1, table.getn(encoded) do
        local _, _, stem = string.find(encoded[i], "^(%w+):")
        stem = stem and string.lower(stem)
        if stem and not (excluded and excluded[stem .. "1"]) then
          authoredGeometry[stem] = encoded[i]
        end
      end
    end
  end
  local entry = authoredGeometry[TextureBasename(path) or ""]
  if not entry then return nil end
  local _, _, width, height, x, y =
    string.find(entry, "^%w+:(%d+):(%d+):(%d+):(%d+)$")
  if not width then return nil end
  return tonumber(width), tonumber(height), tonumber(x), tonumber(y)
end

local nativeUpdate = _G["WorldMapFrame_Update"]
if type(nativeUpdate) == "function" then
  _G["WorldMapFrame_Update"] = function()
    diag.updates = diag.updates + 1
    mapUpdateActive = true
    local ok, err = pcall(nativeUpdate)
    mapUpdateActive = false
    if not ok then
      diag.lastError = "WorldMapFrame_Update: " .. tostring(err)
      error(err, 0)
    end
    local mapName = BindingMap()
    if mapName and (presentationActive or IsPresented(mapName)) then
      -- Let the native click/update transaction finish before rebinding tiles.
      StartDriver(true)
    elseif presentationActive then
      StopDriver(true, "WorldMapFrame_Update: map not bound")
    end
  end
  diag.updateHook = _G["WorldMapFrame_Update"]
end

-- Fog of war. With the revealFog setting on, the overlay enumeration also
-- reports the current zone's unexplored overlays (PandaMapOverlayData), after
-- the explored ones. The native updater then draws them with its own texture
-- pool, geometry and texcoords, and the HD binding rebinds them by basename
-- like any explored piece. Only the map being drawn is parsed, into reused
-- arrays capped at REVEAL_MAX entries.
local REVEAL_MAX = 64
local nativeGetNumMapOverlays = _G["GetNumMapOverlays"]
local nativeGetMapOverlayInfo = _G["GetMapOverlayInfo"]
local revealEnabled, revealMap, revealNative
local revealCount = 0
local revealName, revealWidth, revealHeight, revealX, revealY = {}, {}, {}, {}, {}
local exploredNames = {}

local function IsFogRevealEnabled()
  local db = _G["PandaMapDB"]
  return type(db) == "table" and db.revealFog == true
end


ResetRevealCache = function()
  local i
  for i = 1, REVEAL_MAX do
    revealName[i], revealWidth[i], revealHeight[i] = nil, nil, nil
    revealX[i], revealY[i] = nil, nil
  end
  local key
  for key in pairs(exploredNames) do exploredNames[key] = nil end
  revealEnabled, revealMap, revealNative = nil, nil, nil
  revealCount = 0
end

local function NativeOverlayCount()
  if type(nativeGetNumMapOverlays) ~= "function" then return 0 end
  local ok, count = pcall(nativeGetNumMapOverlays)
  return ok and type(count) == "number" and count or 0
end

-- Rebuilds the unexplored list only when the map, the explored count or the
-- setting changed since the last call.
local function EnsureReveal(nativeCount)
  local enabled = IsFogRevealEnabled()
  local mapName = enabled and CurrentMapName() or nil
  if enabled == revealEnabled and mapName == revealMap
      and nativeCount == revealNative then
    return
  end
  revealEnabled, revealMap, revealNative = enabled, mapName, nativeCount
  revealCount = 0
  local dataMapName = mapName and AssetMapName(mapName) or nil
  local data = dataMapName and type(PandaMapOverlayData) == "table"
    and PandaMapOverlayData[dataMapName] or nil
  if type(data) ~= "table" or type(nativeGetMapOverlayInfo) ~= "function" then
    return
  end

  local key
  for key in pairs(exploredNames) do exploredNames[key] = nil end
  local i
  for i = 1, nativeCount do
    local ok, path = pcall(nativeGetMapOverlayInfo, i)
    local basename = ok and TextureBasename(path) or nil
    if basename then exploredNames[basename] = true end
  end

  for i = 1, table.getn(data) do
    local _, _, name, width, height, x, y =
      string.find(data[i], "^(%w+):(%d+):(%d+):(%d+):(%d+)$")
    if name and not exploredNames[string.lower(name)]
        and revealCount < REVEAL_MAX then
      revealCount = revealCount + 1
      revealName[revealCount] = name
      revealWidth[revealCount] = tonumber(width)
      revealHeight[revealCount] = tonumber(height)
      revealX[revealCount] = tonumber(x)
      revealY[revealCount] = tonumber(y)
    end
  end
end

if type(nativeGetNumMapOverlays) == "function" then
  _G["GetNumMapOverlays"] = function()
    if not IsFogRevealEnabled() then return nativeGetNumMapOverlays() end
    local count = NativeOverlayCount()
    EnsureReveal(count)
    return count + revealCount
  end
end

if type(nativeGetMapOverlayInfo) == "function" then
  _G["GetMapOverlayInfo"] = function(index)
    -- Other addons read overlays with the map closed; only an open map
    -- starts the driver, or the next ToggleWorldMap took the open for a close.
    local currentMap = CurrentMapName()
    if IsSupportedMap(currentMap) and MapPacksInstalled(currentMap)
        and IsWorldMapVisible() then
      StartDriver(true)
    end
    if IsFogRevealEnabled() and type(index) == "number" then
      local nativeCount = NativeOverlayCount()
      EnsureReveal(nativeCount)
      local slot = index - nativeCount
      if slot >= 1 and slot <= revealCount then
        -- Same form as the native paths: Interface/WorldMap/<map>/<NAME>.
        return "Interface/WorldMap/" .. revealMap .. "/" .. revealName[slot],
          revealWidth[slot], revealHeight[slot], revealX[slot], revealY[slot],
          0, 0
      end
    end
    if mapUpdateActive then
      local path, width, height, x, y, pointX, pointY =
        nativeGetMapOverlayInfo(index)
      local hdWidth, hdHeight, hdX, hdY = AuthoredOverlayGeometry(path)
      if hdWidth then
        return path, hdWidth, hdHeight, hdX, hdY, pointX, pointY
      end
      return path, width, height, x, y, pointX, pointY
    end
    return nativeGetMapOverlayInfo(index)
  end
end

-- Redraws an open map after the setting changed. A closed map is left alone:
-- running the updater while closed populates stale native paths.
local function RefreshOpenMap()
  if not IsWorldMapVisible() then return end
  -- Overlay slots the redraw stops using would keep their HD binding.
  ClearBindings()
  local update = _G["WorldMapFrame_Update"]
  if type(update) == "function" then pcall(update) end
end

if worldMap and type(worldMap.GetScript) == "function"
    and type(worldMap.SetScript) == "function" then
  local nativeOnHide = worldMap:GetScript("OnHide")
  worldMap:SetScript("OnHide", function()
    if nativeOnHide then nativeOnHide() end
    StopDriver(true, "map OnHide")
  end)
end

local nativeShowPanel = _G["ShowUIPanel"]
if worldMap and type(nativeShowPanel) == "function" then
  _G["ShowUIPanel"] = function(...)
    local frame = arg[1]
    nativeShowPanel(unpack(arg, 1, arg.n))
    if frame == worldMap then StartDriver(true) end
  end
end

local nativeHidePanel = _G["HideUIPanel"]
if worldMap and type(nativeHidePanel) == "function" then
  _G["HideUIPanel"] = function(...)
    local frame = arg[1]
    nativeHidePanel(unpack(arg, 1, arg.n))
    if frame == worldMap then StopDriver(true, "HideUIPanel") end
  end
end

local nativeToggle = _G["ToggleWorldMap"]
if type(nativeToggle) == "function" then
  -- Decided by the map's visibility after the toggle, not by the driver
  -- state, which another addon's overlay read may have left stale.
  _G["ToggleWorldMap"] = function()
    nativeToggle()
    if IsWorldMapVisible() then
      StartDriver(true)
    else
      StopDriver(true, "ToggleWorldMap closed")
    end
  end
end

PandaMap = {
  version = "1.0.1",
  ApplyReplacement = ApplyReplacement,
  ClearBindings = ClearBindings,
  GetFogRevealEnabled = IsFogRevealEnabled,
  GetPacks = function()
    return PACKS
  end,
  RegisterPack = RegisterPack,
  IsPackInstalled = IsPackInstalled,
  GetOverlayReplacementEnabled = function()
    return overlayReplacementEnabled
  end,
  GetTerrainEnabled = IsTerrainEnabled,
  GetTerrainZoom = function()
    return TERRAIN_ZOOM
  end,
  IsTerrainShown = function()
    return terrainShown
  end,
  -- One diagnostic line for /pmap terrain.
  GetTerrainStatus = function()
    local zoom, source = CurrentZoom()
    local mapName = CurrentMapName()
    local assetMapName = mapName and AssetMapName(mapName) or nil
    return string.format(
      "zoom %s (%s), threshold %s, enabled %s, map %s, has terrain %s, "
      .. "wanted %s, shown %s, presenting %s, visible %s, update hook %s, "
      .. "starts %d, stops %d (last: %s), updates %d, last error: %s, tile1 %s",
      tostring(zoom), tostring(source), tostring(TERRAIN_ZOOM),
      tostring(IsTerrainEnabled()), tostring(mapName),
      tostring(assetMapName and TERRAIN_BASE_MAPS[assetMapName] == true),
      tostring(WantsTerrain(assetMapName)), tostring(terrainShown),
      tostring(presentationActive), tostring(IsWorldMapVisible()),
      _G["WorldMapFrame_Update"] == diag.updateHook and "ours" or "REPLACED",
      diag.starts, diag.stops, tostring(diag.lastStop), diag.updates,
      tostring(diag.lastError),
      tostring(SafeTexture(_G["WorldMapDetailTile1"])))
  end,
  SetTerrainEnabled = function(enabled)
    if type(PandaMapDB) ~= "table" then PandaMapDB = {} end
    PandaMapDB.terrain3D = enabled and true or false
    if presentationActive then ApplyReplacement() end
    return PandaMapDB.terrain3D
  end,
  IsMapPresentationActive = function()
    return presentationActive
  end,
  SetFogRevealEnabled = function(enabled)
    if type(PandaMapDB) ~= "table" then PandaMapDB = {} end
    PandaMapDB.revealFog = enabled and true or false
    RefreshOpenMap()
    return PandaMapDB.revealFog
  end,
  SetOverlayReplacementEnabled = function(enabled)
    overlayReplacementEnabled = enabled and true or false
    return overlayReplacementEnabled
  end,
}
