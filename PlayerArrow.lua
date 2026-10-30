-- PandaMap / PlayerArrow.lua
--
-- pandaUI's custom player cursor (Retail's UI-HUD-Minimap-Arrow-Player) on
-- the minimap and the World Map, for when pandaUI's playerarrow module is not
-- running (pandaUI absent, or its arrow failed). A port of pandaUI's
-- modules/playerarrow.lua without its corpse arrow; see that file for the
-- client findings behind each step.
--
-- GetPlayerFacing is absent on OctoWoW. Each map's native MinimapArrow Model
-- tracks the player instead, but only while its map is visible, so the
-- minimap uses the Minimap model and the World Map uses the WorldMapFrame one.

local TEXTURE = "Interface\\AddOns\\pandaMap\\Media\\Textures\\UI\\player-arrow-frames"
local FRAMES = 64
local COLUMNS = 8
-- pandaUI's media.playerArrow sizes: the baked cell is 64 texels.
local MINIMAP_SIZE = 0.375 * 64
local WORLD_MAP_SIZE = 0.5 * 64
local UPDATE_INTERVAL = 0.05
local PARK_OFFSET = -5000
local GATE_TIMEOUT = 10

local state = {}

local function NumberMethod(object, method)
  if not object or type(object[method]) ~= "function" then return nil end
  local ok, value = pcall(object[method], object)
  if ok then return tonumber(value) end
  return nil
end

local function MakeArrow(name, parent, size)
  if not parent then return nil end
  local frame = CreateFrame("Frame", name, parent)
  if not frame then return nil end
  frame:Hide()
  frame:SetWidth(size)
  frame:SetHeight(size)
  frame:SetFrameLevel((NumberMethod(parent, "GetFrameLevel") or 0) + 8)
  if frame.EnableMouse then frame:EnableMouse(false) end
  local texture = frame:CreateTexture(nil, "OVERLAY")
  if not texture then return nil end
  texture:SetTexture(TEXTURE)
  texture:SetAllPoints(frame)
  frame.arrow = texture
  return frame
end

-- Rotation is baked into 64 cells: this client breaks rotated UVs.
local function SetCell(texture, cell)
  local row = math.floor(cell / COLUMNS)
  local column = cell - row * COLUMNS
  texture:SetTexCoord(column / COLUMNS, (column + 1) / COLUMNS,
    row / COLUMNS, (row + 1) / COLUMNS)
end

-- Must run before the Minimap model is cleared: GetModel no longer returns
-- its path afterwards, though GetFacing keeps updating.
local function FindFacingModel(parent)
  if not parent or type(parent.GetChildren) ~= "function" then return nil end
  local children = { parent:GetChildren() }
  for i = 1, table.getn(children) do
    local child = children[i]
    if type(child.GetFacing) == "function" and type(child.GetModel) == "function" then
      local ok, path = pcall(child.GetModel, child)
      if ok and type(path) == "string" then
        path = string.lower(path)
        if string.find(path, "minimaparrow", 1, true) and
           not string.find(path, "rotating", 1, true) then
          return child
        end
      end
    end
  end
  return nil
end

local function FacingCell(model)
  local facing
  if type(GetPlayerFacing) == "function" then
    local ok, value = pcall(GetPlayerFacing)
    if ok and type(value) == "number" then facing = value end
  end
  if not facing and model then
    local ok, value = pcall(model.GetFacing, model)
    if ok and type(value) == "number" then facing = value end
  end
  if not facing then return nil end
  local turn = math.pi * 2
  facing = facing - math.floor(facing / turn) * turn
  local cell = math.floor(facing / turn * FRAMES + 0.5)
  if cell >= FRAMES then cell = 0 end
  return cell
end

-- World Map ------------------------------------------------------------------
--
-- GetPlayerMapPosition is the only reliable position source (0, 0 off the
-- player's map). The arrow sits on WorldMapButton, so MapZoom's marker layer
-- carries it through zoom and pan.

local function HideWorldMapArrow()
  local frame = state.worldMap
  if frame and frame:IsShown() then frame:Hide() end
  state.worldMapX, state.worldMapY = nil, nil
end

local function UpdateWorldMapArrow()
  local frame = state.worldMap
  local canvas = _G["WorldMapDetailFrame"] or _G["WorldMapButton"]
  if not frame or not canvas or type(GetPlayerMapPosition) ~= "function" then return end

  local ok, x, y = pcall(GetPlayerMapPosition, "player")
  local width = NumberMethod(canvas, "GetWidth")
  local height = NumberMethod(canvas, "GetHeight")
  if not ok or type(x) ~= "number" or type(y) ~= "number" or
     not width or not height or width <= 0 or height <= 0 or
     (x <= 0 and y <= 0) then
    HideWorldMapArrow()
    return
  end

  if not state.worldMapFacingModel then
    state.worldMapFacingModel = FindFacingModel(_G["WorldMapFrame"])
  end
  local cell = FacingCell(state.worldMapFacingModel)
  if cell ~= nil and cell ~= state.worldMapCell then
    state.worldMapCell = cell
    SetCell(frame.arrow, cell)
  end

  local px, py = x * width, -y * height
  if px ~= state.worldMapX or py ~= state.worldMapY then
    state.worldMapX, state.worldMapY = px, py
    frame:ClearAllPoints()
    frame:SetPoint("CENTER", canvas, "TOPLEFT", px, py)
  end
  if not frame:IsShown() then frame:Show() end
end

-- UIParent is hidden while the fullscreen map is open, so this driver is a
-- WorldFrame child and runs every frame while the map is visible.
local function WorldMapDriverOnUpdate()
  local map = _G["WorldMapFrame"]
  if not map or not map:IsVisible() then
    HideWorldMapArrow()
    return
  end
  UpdateWorldMapArrow()
end

-- Parks the native World Map arrow model off the map.
local function InstallWorldMapPark()
  local original = _G["PositionWorldMapArrowFrame"]
  if type(original) ~= "function" then return false end
  local function Wrapped(a1, a2, a3, a4, a5, a6)
    if type(a2) == "number" then a2 = PARK_OFFSET end
    if type(a3) == "number" then a3 = PARK_OFFSET end
    if type(a4) == "number" then a4 = PARK_OFFSET end
    if type(a5) == "number" then a5 = PARK_OFFSET end
    return original(a1, a2, a3, a4, a5, a6)
  end
  PositionWorldMapArrowFrame = Wrapped
  if _G["PositionWorldMapArrowFrame"] ~= Wrapped then return false end
  state.parked = true
  pcall(original, "CENTER", PARK_OFFSET, PARK_OFFSET)
  return true
end

local function BuildWorldMapArrow()
  local canvas = _G["WorldMapButton"]
  local world = _G["WorldFrame"]
  if not canvas or not world then return nil end
  local frame = MakeArrow("PandaMapPlayerArrowWorldMap", canvas, WORLD_MAP_SIZE)
  if not frame then return nil end
  local driver = CreateFrame("Frame", "PandaMapPlayerArrowWorldMapDriver", world)
  if not driver then return nil end
  if not InstallWorldMapPark() then return nil end
  driver:SetScript("OnUpdate", WorldMapDriverOnUpdate)
  return frame
end

-- Minimap ----------------------------------------------------------------------

local function BuildMinimapArrow()
  local minimap = _G["Minimap"]
  if not minimap or type(minimap.SetPlayerModel) ~= "function" then return nil end
  local frame = MakeArrow("PandaMapPlayerArrowMinimap", minimap, MINIMAP_SIZE)
  if not frame then return nil end
  frame:SetPoint("CENTER", minimap, "CENTER", 0, 0)
  -- SetPlayerModel("") errors on OctoWoW yet still clears the native arrow:
  -- judge it by the native model afterwards.
  local called = pcall(minimap.SetPlayerModel, minimap, "")
  local model = state.facingModel
  local cleared = called
  if model and type(model.GetModel) == "function" then
    local ok, path = pcall(model.GetModel, model)
    cleared = not ok or type(path) ~= "string" or
      not string.find(string.lower(path), "minimaparrow", 1, true)
  end
  if not cleared then return nil end
  return frame
end

local function RefreshMinimap()
  local cell = FacingCell(state.facingModel)
  if cell ~= nil and cell ~= state.cell then
    state.cell = cell
    SetCell(state.minimap.arrow, cell)
  end
end

-- Install ----------------------------------------------------------------------

-- pandaUI draws the same arrows itself when its playerarrow module runs.
local function PandaUIArrowRunning()
  if _G["PandaUIPlayerArrowMinimap"] or _G["PandaUIPlayerArrowWorldMap"] then
    return true
  end
  local hostUI = _G["PandaUI"]
  if type(hostUI) ~= "table" or type(hostUI.GetModule) ~= "function" then
    return false
  end
  local ok, arrow = pcall(hostUI.GetModule, "playerarrow")
  return ok and type(arrow) == "table" and type(arrow.state) == "table"
    and arrow.state.enabled and true or false
end

local function Install()
  if PandaUIArrowRunning() then return end

  state.facingModel = FindFacingModel(_G["Minimap"])
  state.worldMapFacingModel = FindFacingModel(_G["WorldMapFrame"])
  local cell = FacingCell(state.facingModel)
  if cell == nil then return end

  local okMinimap, minimap = pcall(BuildMinimapArrow)
  if okMinimap and minimap then
    state.minimap = minimap
    state.cell = cell
    SetCell(minimap.arrow, cell)
    minimap:Show()
    local elapsed = 0
    local ticker = CreateFrame("Frame", "PandaMapPlayerArrowMinimapDriver", UIParent)
    ticker:SetScript("OnUpdate", function()
      elapsed = elapsed + (tonumber(arg1) or 0)
      if elapsed < UPDATE_INTERVAL then return end
      elapsed = 0
      RefreshMinimap()
    end)
  end

  local okMap, worldMap = pcall(BuildWorldMapArrow)
  if okMap and worldMap then
    state.worldMap = worldMap
    state.worldMapCell = cell
    SetCell(worldMap.arrow, cell)
  end
end

-- Runs after pandaUI has enabled its modules (PandaUI.ready) or is known
-- absent, and after MapZoom.lua's own gate has wrapped the native arrow.
local gate = CreateFrame("Frame", "PandaMapPlayerArrowGate", _G["WorldFrame"] or UIParent)
gate:RegisterEvent("PLAYER_LOGIN")
gate:SetScript("OnEvent", function()
  gate:UnregisterEvent("PLAYER_LOGIN")
  local waited = 0
  gate:SetScript("OnUpdate", function()
    waited = waited + (tonumber(arg1) or 0)
    local hostUI = _G["PandaUI"]
    local ready = type(hostUI) ~= "table" or hostUI.ready
    local zoom = _G["PandaMapZoom"]
    local zoomDecided = not zoom or zoom.GetOwner() ~= nil or zoom.GetFailure() ~= nil
    if (not ready or not zoomDecided) and waited < GATE_TIMEOUT then return end
    gate:SetScript("OnUpdate", nil)
    pcall(Install)
  end)
end)

PandaMapPlayerArrow = {
  -- Read by MapZoom.lua: a parked native arrow is not rescaled.
  IsParked = function() return state.parked and true or false end,
}
