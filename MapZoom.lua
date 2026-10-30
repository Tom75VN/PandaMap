-- PandaMap / MapZoom.lua
--
-- Eased mouse-wheel and double-click zoom, drag panning with a glide on
-- release, on the native World Map, with a "Zoom" hint icon in the map's
-- top-right corner.
--
-- Who owns the zoom
--
--   * This file, with or without pandaUI. pandaUI's worldmapzoom module skips
--     its install while PandaMapZoom.ClaimsZoom() is true and forwards
--     U.WorldMapZoomPin here.
--   * This file's install fails -> it stops claiming and enables pandaUI's
--     zoom instead.
--   * An older pandaUI already installed its zoom, or some other addon has
--     moved WorldMapDetailFrame out of WorldMapFrame -> this file does nothing,
--     so two zooms never stack.
--
-- pandaUI enables its modules at PLAYER_LOGIN, the same event this file
-- waits for, so the install runs from an OnUpdate gate on the frames after
-- PLAYER_LOGIN, once PandaUI.ready is set (or pandaUI is known to be absent).
--
-- How it works (the design pandaUI's modules/worldmapzoom.lua uses on this
-- client; knowledge.json / map.worldmap_zoom_scaled_content_viewport and
-- map.worldmap_zoom_windowed_wheel_client_crash):
--
--   WorldFrame
--     PandaMapWorldMapViewport  (ScrollFrame on the native map rectangle;
--                                clips only, never scrolled)
--       PandaMapWorldMapZoomHolder  (scroll child, same size)
--         PandaMapWorldMapZoomContent  (art layer: scaled, at -panX, panY)
--           WorldMapDetailFrame  (native tiles; PandaMap's HD tiles bind here)
--         PandaMapWorldMapZoomMarkers  (markers layer: same scale and offset
--                                       once the zoom has settled)
--           WorldMapButton       (native hit-test, units, POIs, addon pins)
--
-- Every stock and addon map position is relative to those two canvases, so
-- scaling both layers alike keeps everything in place. While the zoom eases
-- or the map pans, only the art layer changes each frame and the markers (all
-- but the pinned frames) are hidden; the markers layer follows once, on the
-- last frame. Per-frame layout of the marker tree is too expensive. The viewport is a
-- WorldFrame child because the client reparents WorldMapFrame when the map is
-- minimized; a viewport inside that tree crashed the client.

local MIN_ZOOM = 1
local MAX_ZOOM = 4
local ZOOM_STEP = 0.25
local GATE_TIMEOUT = 10

-- The wheel eases toward its target zoom (about 95% of a step in 0.25 s) and
-- ends exactly on it: pandaMap.lua swaps in the 3D terrain at an exact zoom.
local ZOOM_RATE = 12
local ZOOM_SNAP = 0.002
local MAX_FRAME_TIME = 0.1

local DOUBLE_CLICK_TIME = 0.3
local DOUBLE_CLICK_DISTANCE = 6
local DOUBLE_CLICK_STEP = 1

-- Glide after a released drag, in viewport units per second.
local GLIDE_FRICTION = 5
local GLIDE_START_SPEED = 60
local GLIDE_STOP_SPEED = 15
local GLIDE_MAX_SPEED = 4000
local GLIDE_RELEASE_WINDOW = 0.08

-- The native rectangle, from WorldMapFrame.xml. Re-applied from constants;
-- GetPoint is avoided on the map tree.
local NATIVE_ANCHOR_X = -502
local NATIVE_ANCHOR_Y = -69

local VIEWPORT_NAME = "PandaMapWorldMapViewport"
local HINT_TEXTURE = "Interface\\AddOns\\pandaMap\\Media\\Textures\\UI\\mousewheel-zoom"
local HINT_ICON = 22
local HINT_BACKGROUND = { 0.06, 0.06, 0.06, 0.85 }
local HINT_TEXT = { 0.90, 0.90, 0.90, 1.00 }

local state = {
  installed = false,
  owner = nil,          -- "pandaMap", "pandaUI", "other" once decided
  failure = nil,
  zoom = 1,             -- shown zoom, read by pandaMap.lua's terrain swap
  targetZoom = 1,
  panX = 0,
  panY = 0,
  width = nil,
  height = nil,
  viewportScale = 1,
  mapKey = nil,
  pins = {},
  pinned = {},          -- pinned frame -> true; kept visible while zooming
  pinZoom = nil,
  artApplied = {},      -- last scale and offset written to each layer
  markerApplied = {},
  insets = {},
  markersHidden = false,
  hiddenMarkers = {},   -- frame or region -> alpha its owner last requested
  markerSetAlpha = {},  -- frame or region -> original SetAlpha method
  markerChildCount = nil,
  -- Set to a SavedVariables-backed capture by /pmap perf.
  perf = nil,
  dragging = false,
  justDragged = false,
  gliding = false,
  downX = nil,
  lastX = 0,
  lastY = 0,
  lastMoveAt = nil,
  velX = 0,             -- pan velocity, map units per second
  velY = 0,
  clickAt = nil,
  clickX = 0,
  clickY = 0,
}

local function NumberMethod(object, method)
  if not object or type(object[method]) ~= "function" then return nil end
  local ok, value = pcall(object[method], object)
  if ok then return tonumber(value) end
  return nil
end

local function Clamp(value, low, high)
  if value < low then return low end
  if value > high then return high end
  return value
end

local function SamplePerfMemory(perf, dt)
  perf.memoryElapsed = perf.memoryElapsed + dt
  if perf.memoryElapsed < 0.5 then return end
  perf.memoryElapsed = 0
  local memory = gcinfo()
  perf.endMemory = memory
  if memory < perf.minMemory then perf.minMemory = memory end
  if memory > perf.maxMemory then perf.maxMemory = memory end
end

local function RecordZoomFrame(perf, dt)
  perf.zoomFrames = perf.zoomFrames + 1
  perf.zoomTime = perf.zoomTime + dt
  perf.zoomTime2 = perf.zoomTime2 + dt * dt
  if dt > perf.zoomMax then perf.zoomMax = dt end
  if dt > 0.025 then perf.zoomSlow = perf.zoomSlow + 1 end
  if dt > 0.05 then perf.zoomVerySlow = perf.zoomVerySlow + 1 end
  SamplePerfMemory(perf, dt)
end

local function RecordPanFrame(perf, dt)
  perf.panFrames = perf.panFrames + 1
  perf.panTime = perf.panTime + dt
  perf.panTime2 = perf.panTime2 + dt * dt
  if dt > perf.panMax then perf.panMax = dt end
  if dt > 0.025 then perf.panSlow = perf.panSlow + 1 end
  if dt > 0.05 then perf.panVerySlow = perf.panVerySlow + 1 end
  if state.dragging then
    perf.dragFrames = perf.dragFrames + 1
    perf.dragTime = perf.dragTime + dt
    if dt > perf.dragMax then perf.dragMax = dt end
    if dt > 0.025 then perf.dragSlow = perf.dragSlow + 1 end
  elseif state.gliding then
    perf.glideFrames = perf.glideFrames + 1
    perf.glideTime = perf.glideTime + dt
    if dt > perf.glideMax then perf.glideMax = dt end
    if dt > 0.025 then perf.glideSlow = perf.glideSlow + 1 end
  end
  SamplePerfMemory(perf, dt)
end

-- Runs fn after the frame's current script. Handlers read this/arg1..., which
-- stay set while both run.
local function PostHookScript(frame, script, fn)
  if not frame or type(frame.GetScript) ~= "function" then return false end
  local ok, previous = pcall(frame.GetScript, frame, script)
  if not ok then return false end
  return pcall(frame.SetScript, frame, script,
    function(a1, a2, a3, a4, a5, a6, a7, a8, a9)
      if previous then previous(a1, a2, a3, a4, a5, a6, a7, a8, a9) end
      fn()
    end)
end

local function CursorRaw()
  local cursor = _G["GetCursorPosition"]
  if type(cursor) ~= "function" then return nil end
  local ok, x, y = pcall(cursor)
  if not ok or not tonumber(x) or not tonumber(y) then return nil end
  return x, y
end

-- Cursor in viewport units from its TOPLEFT (y down); inside is false when
-- the cursor is off the visible map rectangle.
local function CursorInView()
  local viewport = state.viewport
  if not viewport then return nil end
  local x, y = CursorRaw()
  if not x then return nil end
  local scale = NumberMethod(viewport, "GetEffectiveScale")
  local left = NumberMethod(viewport, "GetLeft")
  local top = NumberMethod(viewport, "GetTop")
  if not scale or scale == 0 or not left or not top then return nil end
  local cx = x / scale - left
  local cy = top - y / scale
  local inside = cx >= 0 and cy >= 0 and cx <= state.width and cy <= state.height
  return cx, cy, inside
end

-- Zoom -----------------------------------------------------------------------

local function ApplyPins()
  local perf = state.perf
  if perf and perf.active then
    perf.pinPasses = perf.pinPasses + 1
    perf.pinWrites = perf.pinWrites + table.getn(state.pins)
  end
  local i
  for i = 1, table.getn(state.pins) do
    local pin = state.pins[i]
    local frame = pin.frame
    pcall(frame.SetScale, frame, pin.scale / state.zoom)
    pcall(frame.ClearAllPoints, frame)
    pcall(frame.SetPoint, frame, pin.point, state.viewport, pin.relativePoint,
      pin.x, pin.y)
  end
end

-- Scale and pan writes re-lay every frame and region under the layer, so
-- identical writes are skipped.
local function PlaceLayer(layer, applied, z)
  local x, y = -state.panX, state.panY
  if applied.zoom ~= z then
    applied.zoom = z
    local perf = state.perf
    if perf and perf.active then
      if applied == state.artApplied then
        perf.artScaleWrites = perf.artScaleWrites + 1
      else
        perf.markerScaleWrites = perf.markerScaleWrites + 1
      end
    end
    pcall(layer.SetScale, layer, z)
  end
  if applied.x ~= x or applied.y ~= y then
    applied.x, applied.y = x, y
    local perf = state.perf
    if perf and perf.active then
      if applied == state.artApplied then
        perf.artMoveWrites = perf.artMoveWrites + 1
      else
        perf.markerMoveWrites = perf.markerMoveWrites + 1
      end
    end
    pcall(layer.ClearAllPoints, layer)
    pcall(layer.SetPoint, layer, "TOPLEFT", state.holder, "TOPLEFT", x, y)
  end
end

-- A marker owner may keep refreshing SetAlpha while the map moves (pandaQuest
-- pulses its quest targets this way). Keep the owner's requested alpha for
-- the restore, but hold the actual frame at zero until marker geometry catches
-- up. One shared replacement is installed per discovered marker; no per-frame
-- walk of the potentially large marker pool is needed.
local function MarkerSetAlpha(object, alpha)
  local original = state.markerSetAlpha[object]
  if not original then return end
  if state.markersHidden and state.hiddenMarkers[object] ~= nil then
    if type(alpha) == "number" then state.hiddenMarkers[object] = alpha end
    return original(object, 0)
  end
  return original(object, alpha)
end

local function InstallMarkerSetAlpha(object)
  object.SetAlpha = MarkerSetAlpha
end

local function HideMarkerList(hidden, list)
  local count = 0
  local i
  for i = 1, table.getn(list) do
    local object = list[i]
    if object and not state.pinned[object] and hidden[object] == nil then
      local alpha = NumberMethod(object, "GetAlpha")
      local setter = object.SetAlpha
      if alpha and type(setter) == "function" then
        if not state.markerSetAlpha[object] then
          state.markerSetAlpha[object] = setter
          if not pcall(InstallMarkerSetAlpha, object) then
            state.markerSetAlpha[object] = nil
          end
        end
        hidden[object] = alpha
        local original = state.markerSetAlpha[object] or setter
        pcall(original, object, 0)
        count = count + 1
      end
    end
  end
  return count
end

local function ButtonChildren(button) return { button:GetChildren() } end
local function ButtonRegions(button) return { button:GetRegions() } end

-- Discovers all markers at motion start. During motion GetNumChildren is an
-- O(1) guard; the full child list is rebuilt only if an addon creates a pin.
local function HideMarkers()
  local firstPass = not state.markersHidden
  state.markersHidden = true
  local button, hidden = state.button, state.hiddenMarkers
  local count = 0
  local childCount = NumberMethod(button, "GetNumChildren")
  if firstPass or childCount ~= state.markerChildCount then
    state.markerChildCount = childCount
    local ok, list = pcall(ButtonChildren, button)
    if ok and type(list) == "table" then
      count = count + HideMarkerList(hidden, list)
    end
  end
  -- Regions cannot be added by the known marker addons and GetNumRegions is
  -- broken on this client, so inventory them only at motion start.
  if firstPass then
    local ok, list = pcall(ButtonRegions, button)
    if ok and type(list) == "table" then
      count = count + HideMarkerList(hidden, list)
    end
  end
  local perf = state.perf
  if perf and perf.active and (firstPass or count > 0) then
    perf.markerHidePasses = perf.markerHidePasses + 1
    perf.markerHideObjects = perf.markerHideObjects + count
    if count > perf.markerHideMax then perf.markerHideMax = count end
  end
end

local function ShowMarkers()
  if not state.markersHidden then return end
  state.markersHidden = false
  local hidden = state.hiddenMarkers
  local object, alpha, count
  count = 0
  for object, alpha in pairs(hidden) do
    pcall(object.SetAlpha, object, alpha)
    hidden[object] = nil
    count = count + 1
  end
  local perf = state.perf
  if perf and perf.active then
    perf.markerShowPasses = perf.markerShowPasses + 1
    perf.markerShowObjects = perf.markerShowObjects + count
  end
end

-- The markers layer (WorldMapButton: units, POIs, pandaQuest and
-- pandaConquest pins) follows the art only once the zoom has settled: a
-- per-frame rescale of that many frames is what costs the frame rate.
local function SyncMarkers()
  local perf = state.perf
  if perf and perf.active then perf.markerSyncCalls = perf.markerSyncCalls + 1 end
  local z = state.zoom
  PlaceLayer(state.markers, state.markerApplied, z)
  -- Keep the canvas's mouse hits to the visible part of the scaled map.
  local left, top = state.panX, state.panY
  local right = state.width - state.panX - state.width / z
  local bottom = state.height - state.panY - state.height / z
  local insets = state.insets
  if insets[1] ~= left or insets[2] ~= right or insets[3] ~= top
      or insets[4] ~= bottom then
    insets[1], insets[2], insets[3], insets[4] = left, right, top, bottom
    if perf and perf.active then perf.hitRectWrites = perf.hitRectWrites + 1 end
    local button = state.button
    pcall(button.SetHitRectInsets, button, left, right, top, bottom)
  end
  -- Pins sit on the viewport; only a zoom change moves them.
  if state.pinZoom ~= z then
    state.pinZoom = z
    ApplyPins()
  end
  if state.markersHidden then ShowMarkers() end
end

local function Apply()
  if not state.installed then return end
  local z = state.zoom
  state.panX = Clamp(state.panX, 0, state.width - state.width / z)
  state.panY = Clamp(state.panY, 0, state.height - state.height / z)
  PlaceLayer(state.content, state.artApplied, z)
  if z == state.targetZoom and not state.dragging and not state.gliding then
    SyncMarkers()
  elseif not state.markersHidden then
    HideMarkers()
  end
end

local function ClearMotion()
  state.zoom, state.targetZoom, state.panX, state.panY = 1, 1, 0, 0
  state.dragging, state.justDragged, state.gliding = false, false, false
  state.velX, state.velY = 0, 0
  state.clickAt = nil
end

local function Reset()
  ClearMotion()
  Apply()
end

-- Keeps the map point under the cursor fixed; off the map, zooms about the
-- centre.
local function SetZoom(zoom)
  if zoom == state.zoom then return end
  local cx, cy, inside = CursorInView()
  if not cx or not inside then
    cx, cy = state.width / 2, state.height / 2
  end
  local mapX = state.panX + cx / state.zoom
  local mapY = state.panY + cy / state.zoom
  state.zoom = zoom
  state.panX = mapX - cx / zoom
  state.panY = mapY - cy / zoom
  Apply()
end

local function ZoomBy(step)
  local target = Clamp(state.targetZoom + step, MIN_ZOOM, MAX_ZOOM)
  if target == state.targetZoom then return end
  state.targetZoom = target
  state.gliding = false
end

-- Eases in log space so each step feels the same at any zoom.
local function StepZoom(dt)
  local target = state.targetZoom
  if state.zoom == target then return end
  local from = math.log(state.zoom)
  local t = 1 - math.exp(-ZOOM_RATE * dt)
  local zoom = math.exp(from + (math.log(target) - from) * t)
  if math.abs(zoom - target) < ZOOM_SNAP then zoom = target end
  SetZoom(zoom)
end

local function OnWheel()
  local delta = tonumber(arg1)
  if not delta or delta == 0 then return end
  local perf = state.perf
  if perf and perf.active then perf.wheelEvents = perf.wheelEvents + 1 end
  if delta > 0 then
    ZoomBy(ZOOM_STEP)
  else
    ZoomBy(-ZOOM_STEP)
  end
end

-- Keeps a WorldMapButton descendant at its own size, pinned to the visible
-- map, while zoomed. Callable before the zoom is installed.
local function Pin(frame, point, relativePoint, x, y)
  if not frame or type(frame.SetScale) ~= "function" then return end
  local i
  for i = 1, table.getn(state.pins) do
    if state.pins[i].frame == frame then return end
  end
  state.pinned[frame] = true
  table.insert(state.pins, {
    frame = frame,
    point = point,
    relativePoint = relativePoint,
    x = x or 0,
    y = y or 0,
    scale = NumberMethod(frame, "GetScale") or 1,
  })
  if state.installed then ApplyPins() end
end

-- Windowed map ---------------------------------------------------------------

local function Windowed()
  if _G["WORLDMAP_WINDOWED"] == 1 then return true end
  local map = _G["WorldMapFrame"]
  if not map or type(map.GetParent) ~= "function" then return false end
  local ok, parent = pcall(map.GetParent, map)
  return ok and parent ~= nil and parent == _G["UIParent"]
end

-- The client's minimized window is 720x521 around the canvas drawn at
-- WORLDMAP_WINDOWED_SCALE 0.7. A resized window keeps those border widths
-- (map units) and scales only the canvas.
local WINDOW = {
  nativeScale = 0.7,
  minScale = 0.45,
  left = 10.5,
  top = 23.1,
  right = 8.1,
  bottom = 30.3,
}

local resize = { active = false, elapsed = 0 }

-- UIParent's size in the map's units.
local function ScreenSize(map)
  local parent = _G["UIParent"]
  local w = NumberMethod(parent, "GetWidth")
  local h = NumberMethod(parent, "GetHeight")
  if not w or not h then return nil end
  local parentScale = NumberMethod(parent, "GetEffectiveScale")
  local mapScale = NumberMethod(map, "GetEffectiveScale")
  if parentScale and mapScale and mapScale > 0 then
    w, h = w * parentScale / mapScale, h * parentScale / mapScale
  end
  return w, h
end

-- Largest canvas scale whose window fits in width x height.
local function FitScale(width, height)
  local scale = math.min(
    (width - WINDOW.left - WINDOW.right) / state.width,
    (height - WINDOW.top - WINDOW.bottom) / state.height)
  if scale < WINDOW.minScale then return WINDOW.minScale end
  return scale
end

local function SavedWindowScale(map)
  local scale = type(PandaMapDB) == "table" and tonumber(PandaMapDB.windowScale)
  scale = scale or WINDOW.nativeScale
  local w, h = ScreenSize(map)
  if w then scale = math.min(scale, FitScale(w, h)) end
  if scale < WINDOW.minScale then scale = WINDOW.minScale end
  return scale
end

local function SetSize(frame, method, getter, value)
  local current = NumberMethod(frame, getter)
  if not current or math.abs(current - value) > 0.01 then
    pcall(frame[method], frame, value)
  end
end

-- Sizes the minimized window for its saved scale; returns that scale.
local function ApplyWindowSize(map)
  local scale = SavedWindowScale(map)
  setglobal("WORLDMAP_WINDOWED_SCALE", scale)
  SetSize(map, "SetWidth", "GetWidth",
    WINDOW.left + state.width * scale + WINDOW.right)
  SetSize(map, "SetHeight", "GetHeight",
    WINDOW.top + state.height * scale + WINDOW.bottom)
  return scale
end

local function ShowResizeGrip(shown, map)
  local grip, marker = resize.grip, resize.marker
  if not grip then return end
  if not shown then
    pcall(grip.Hide, grip)
    pcall(marker.Hide, marker)
    return
  end
  -- The client drops the minimized map to frame level 0.
  local level = (NumberMethod(map, "GetFrameLevel") or 0) + 20
  pcall(grip.SetFrameLevel, grip, level)
  pcall(marker.SetFrameLevel, marker, level)
  pcall(grip.Show, grip)
  pcall(marker.Show, marker)
end

-- Matches the viewport to the current mode. A mode switch resets the zoom.
local function Layout()
  if not state.installed then return end
  local map, viewport = _G["WorldMapFrame"], state.viewport
  local detail, button = state.detail, state.button

  -- Layout also runs to repair the button's geometry after a zoom settles
  -- (EnsureMapButtonGeometry); only an actual mode switch clears the zoom.
  local windowed = Windowed()
  if windowed ~= state.windowed then ClearMotion() end
  state.windowed = windowed

  local scale = 1
  if windowed then scale = ApplyWindowSize(map) end
  ShowResizeGrip(windowed, map)
  state.viewportScale = scale
  local mapScale = NumberMethod(map, "GetEffectiveScale") or 1
  local worldScale = NumberMethod(state.world, "GetEffectiveScale") or 1
  if worldScale <= 0 then worldScale = 1 end
  pcall(viewport.SetScale, viewport, mapScale * scale / worldScale)

  pcall(detail.SetScale, detail, 1)
  pcall(button.SetScale, button, 1)
  pcall(detail.ClearAllPoints, detail)
  pcall(detail.SetPoint, detail, "TOPLEFT", state.content, "TOPLEFT", 0, 0)
  -- Natively on WorldMapDetailFrame; the two layers match once settled.
  pcall(button.ClearAllPoints, button)
  pcall(button.SetPoint, button, "TOPLEFT", state.markers, "TOPLEFT", 0, 0)
  pcall(viewport.ClearAllPoints, viewport)
  if state.windowed then
    -- Offsets are in the viewport's own scale; the border stays fixed.
    pcall(viewport.SetPoint, viewport, "TOPLEFT", map, "TOPLEFT",
      WINDOW.left / scale, -WINDOW.top / scale)
  else
    pcall(viewport.SetPoint, viewport, "TOPLEFT", _G["WorldMapPositioningGuide"],
      "TOP", NATIVE_ANCHOR_X, NATIVE_ANCHOR_Y)
  end
  Apply()
end

-- The stock hover and left-click handlers immediately do arithmetic with
-- WorldMapButton:GetCenter().  During a window mode/layout transition the
-- 1.12 client can run one of those scripts while the reparented button has no
-- resolved screen position yet; GetCenter then returns nil, nil and
-- WorldMapFrame.lua errors.  Reapply our anchors once and skip that input tick
-- if the client still has not resolved them.
local geometryRepairing = false

local function HasScreenCenter(frame)
  if not frame or type(frame.GetCenter) ~= "function" then return false end
  local ok, x, y = pcall(frame.GetCenter, frame)
  return ok and type(x) == "number" and type(y) == "number"
end

local function EnsureMapButtonGeometry(button)
  if HasScreenCenter(button) then return true end
  if geometryRepairing or not state.installed or button ~= state.button then
    return false
  end
  geometryRepairing = true
  Layout()
  geometryRepairing = false
  return HasScreenCenter(button)
end

local function WrapNativeHover(button)
  local ok, previous = pcall(button.GetScript, button, "OnUpdate")
  if not ok then return false end
  return pcall(button.SetScript, button, "OnUpdate",
    function(a1, a2, a3, a4, a5, a6, a7, a8, a9)
      if not EnsureMapButtonGeometry(button) then return end
      if previous then previous(a1, a2, a3, a4, a5, a6, a7, a8, a9) end
    end)
end

local function WrapWindowToggle(name)
  local original = _G[name]
  if type(original) ~= "function" then return end
  setglobal(name, function(a1, a2, a3, a4)
    original(a1, a2, a3, a4)
    Layout()
  end)
end

-- Minimized map resize grip ------------------------------------------------------
--
-- pandaUI's chat and bag recipe (chat.native_chatframe_direct_resize): a
-- Button dragged with StartMoving, not Frame:StartSizing; the window size is
-- derived from the grip's position. The always-shown marker stays on the
-- window corner.
-- The grip is unnamed so the client does not cache its moved position.

local RESIZE_TEXTURE = "Interface\\AddOns\\pandaMap\\Media\\Textures\\UI\\resize"
local RESIZE_INTERVAL = 0.02

local function AnchorResizeGrip()
  local grip = resize.grip
  pcall(grip.ClearAllPoints, grip)
  pcall(grip.SetPoint, grip, "BOTTOMRIGHT", _G["WorldMapFrame"], "BOTTOMRIGHT", -2, 2)
end

local function ResizeToGrip()
  local grip = resize.grip
  local left = NumberMethod(grip, "GetLeft")
  local bottom = NumberMethod(grip, "GetBottom")
  if not left or not bottom then return end
  if left == resize.lastLeft and bottom == resize.lastBottom then return end
  resize.lastLeft, resize.lastBottom = left, bottom
  local scale = FitScale(resize.width + left - resize.left,
    resize.height - (bottom - resize.bottom))
  if scale > resize.maxScale then scale = resize.maxScale end
  if scale == resize.scale then return end
  resize.scale = scale
  if type(PandaMapDB) ~= "table" then PandaMapDB = {} end
  PandaMapDB.windowScale = scale
  Layout()
end

local function ResizeOnUpdate()
  resize.elapsed = resize.elapsed + (tonumber(arg1) or 0)
  if resize.elapsed < RESIZE_INTERVAL then return end
  resize.elapsed = 0
  ResizeToGrip()
end

local function StartResize()
  local map, grip = _G["WorldMapFrame"], resize.grip
  if resize.active or not state.windowed then return end
  local left = NumberMethod(map, "GetLeft")
  local top = NumberMethod(map, "GetTop")
  local width = NumberMethod(map, "GetWidth")
  local height = NumberMethod(map, "GetHeight")
  local screenW, screenH = ScreenSize(map)
  if not left or not top or not width or not height or not screenW then return end

  -- Hold the top-left corner; the window grows only into the screen.
  pcall(map.ClearAllPoints, map)
  pcall(map.SetPoint, map, "TOPLEFT", _G["UIParent"], "BOTTOMLEFT", left, top)
  resize.maxScale = FitScale(screenW - left, top)
  resize.width, resize.height = width, height

  pcall(grip.SetMovable, grip, true)
  if pcall(grip.StartMoving, grip) then pcall(grip.StopMovingOrSizing, grip) end
  AnchorResizeGrip()
  resize.left = NumberMethod(grip, "GetLeft")
  resize.bottom = NumberMethod(grip, "GetBottom")
  if not resize.left or not resize.bottom or not pcall(grip.StartMoving, grip) then
    AnchorResizeGrip()
    return
  end
  resize.lastLeft, resize.lastBottom = resize.left, resize.bottom
  resize.scale = state.viewportScale
  resize.elapsed = 0
  resize.active = true
  pcall(grip.SetScript, grip, "OnUpdate", ResizeOnUpdate)
end

local function FinishResize()
  if not resize.active then return end
  ResizeToGrip()
  resize.active = false
  local grip = resize.grip
  pcall(grip.SetScript, grip, "OnUpdate", nil)
  pcall(grip.StopMovingOrSizing, grip)
  AnchorResizeGrip()
end

local function BuildResizeGrip()
  local map = _G["WorldMapFrame"]
  local grip = CreateFrame("Button", nil, map)
  grip:SetWidth(22)
  grip:SetHeight(22)
  grip:RegisterForDrag("LeftButton")
  pcall(grip.EnableMouse, grip, true)

  local marker = CreateFrame("Frame", nil, map)
  marker:SetWidth(16)
  marker:SetHeight(16)
  marker:SetPoint("BOTTOMRIGHT", map, "BOTTOMRIGHT", -5, 5)
  pcall(marker.EnableMouse, marker, false)
  local icon = marker:CreateTexture(nil, "OVERLAY")
  icon:SetTexture(RESIZE_TEXTURE)
  icon:SetAllPoints(marker)

  resize.grip, resize.marker = grip, marker
  grip:SetScript("OnDragStart", StartResize)
  grip:SetScript("OnDragStop", FinishResize)
  grip:SetScript("OnMouseUp", FinishResize)
  AnchorResizeGrip()
  grip:Hide()
  marker:Hide()
end

-- Drag panning -----------------------------------------------------------------
--
-- The engine's drag threshold separates a pan from a click. The stock
-- OnMouseUp (zoom into a zone, or out) is skipped after a pan and for releases
-- outside the visible map. The drag pans by the cursor's movement each frame,
-- so a wheel zoom during a drag stays under the cursor; a fast release glides.

local function OnMouseDown()
  state.justDragged, state.gliding = false, false
  state.downX, state.downY = CursorRaw()
  if state.downX then state.lastX, state.lastY = state.downX, state.downY end
  state.velX, state.velY = 0, 0
  state.lastMoveAt = GetTime()
end

local function OnDragStart()
  if not state.downX then return end
  if state.zoom <= MIN_ZOOM and state.targetZoom <= MIN_ZOOM then return end
  state.dragging = true
  state.clickAt = nil
  local perf = state.perf
  if perf and perf.active then perf.dragStarts = perf.dragStarts + 1 end
end

local function OnDragStop()
  if state.dragging then
    state.justDragged = true
    local speed = math.sqrt(state.velX * state.velX + state.velY * state.velY)
      * state.zoom
    local recent = state.lastMoveAt
      and GetTime() - state.lastMoveAt < GLIDE_RELEASE_WINDOW
    if recent and speed >= GLIDE_START_SPEED then
      if speed > GLIDE_MAX_SPEED then
        state.velX = state.velX * GLIDE_MAX_SPEED / speed
        state.velY = state.velY * GLIDE_MAX_SPEED / speed
      end
      state.gliding = true
      local perf = state.perf
      if perf and perf.active then perf.glideStarts = perf.glideStarts + 1 end
    end
  end
  state.dragging = false
  if not state.gliding then Apply() end
end

local function StepDrag()
  local x, y = CursorRaw()
  local scale = NumberMethod(state.viewport, "GetEffectiveScale")
  if not x or not scale or scale == 0 then return end
  local dx = (x - state.lastX) / scale / state.zoom
  local dy = (y - state.lastY) / scale / state.zoom
  state.lastX, state.lastY = x, y
  if dx == 0 and dy == 0 then return end
  state.panX = state.panX - dx
  state.panY = state.panY + dy
  -- Velocity over the time since the cursor last moved: the cursor can hold
  -- still for frames between moves at a high frame rate.
  local now = GetTime()
  local span = now - (state.lastMoveAt or now)
  if span > 0 and span < MAX_FRAME_TIME then
    state.velX = state.velX * 0.5 - dx / span * 0.5
    state.velY = state.velY * 0.5 + dy / span * 0.5
  end
  state.lastMoveAt = now
  Apply()
end

local function StepGlide(dt)
  local x = state.panX + state.velX * dt
  local y = state.panY + state.velY * dt
  state.panX, state.panY = x, y
  Apply()
  -- Apply clamps the pan to the map; stop the axis that hit an edge.
  if state.panX ~= x then state.velX = 0 end
  if state.panY ~= y then state.velY = 0 end
  local decay = math.exp(-GLIDE_FRICTION * dt)
  state.velX, state.velY = state.velX * decay, state.velY * decay
  local speed = math.sqrt(state.velX * state.velX + state.velY * state.velY)
    * state.zoom
  if speed < GLIDE_STOP_SPEED then
    state.gliding = false
    Apply()
  end
end

local function DriverOnUpdate()
  if not state.dragging and not state.gliding
      and state.zoom == state.targetZoom then
    return
  end
  local map = _G["WorldMapFrame"]
  if not map or not map:IsVisible() then
    state.dragging, state.gliding = false, false
    state.targetZoom = state.zoom
    Apply()
    return
  end
  local dt = tonumber(arg1) or 0
  local perf = state.perf
  if perf and perf.active then
    perf.lastMotionAt = GetTime()
    if state.zoom ~= state.targetZoom then
      RecordZoomFrame(perf, dt)
    else
      RecordPanFrame(perf, dt)
    end
  end
  if dt > MAX_FRAME_TIME then dt = MAX_FRAME_TIME end
  if state.dragging then
    StepDrag()
  elseif state.gliding then
    StepGlide(dt)
  end
  StepZoom(dt)
  -- A marker pool may grow while motion is already in progress. The common
  -- path reads only GetNumChildren; a changed count inventories and mutes the
  -- newly created children before the frame is presented.
  if state.markersHidden then HideMarkers() end
end

-- A second left click close in time and place to the last one.
local function IsDoubleClick()
  local now = GetTime()
  local x, y = CursorRaw()
  local previousAt, px, py = state.clickAt, state.clickX, state.clickY
  state.clickAt, state.clickX, state.clickY = now, x or 0, y or 0
  if not previousAt or not x or now - previousAt > DOUBLE_CLICK_TIME then
    return false
  end
  local scale = NumberMethod(state.viewport, "GetEffectiveScale") or 1
  if scale == 0 then scale = 1 end
  local dx, dy = (x - px) / scale, (y - py) / scale
  if dx * dx + dy * dy > DOUBLE_CLICK_DISTANCE * DOUBLE_CLICK_DISTANCE then
    return false
  end
  state.clickAt = nil
  return true
end

-- The first click of a double click runs the stock handler; the second zooms
-- in about the cursor instead. A map change in between clears the first click.
local function WrapMouseUp(button)
  local ok, previous = pcall(button.GetScript, button, "OnMouseUp")
  if not ok then return false end
  return pcall(button.SetScript, button, "OnMouseUp",
    function(a1, a2, a3, a4, a5, a6, a7, a8, a9)
      local mouseButton = arg1
      local swallow = state.dragging or state.justDragged
      state.justDragged = false
      local cx, _, inside = CursorInView()
      if not swallow and state.zoom > MIN_ZOOM and cx and not inside then
        swallow = true
      end
      if swallow then return end
      if mouseButton == "LeftButton" and IsDoubleClick() then
        ZoomBy(DOUBLE_CLICK_STEP)
        return
      end
      -- WorldMapButton_OnClick uses the same unchecked GetCenter values as
      -- the hover handler.  Right-click only zooms out and does not need them.
      if mouseButton == "LeftButton" and not EnsureMapButtonGeometry(button) then
        return
      end
      if previous then previous(a1, a2, a3, a4, a5, a6, a7, a8, a9) end
    end)
end

-- pandaUI's playerarrow module parks the native arrow off the map and draws
-- its own on WorldMapDetailFrame, which moves with the zoom by itself.
-- PlayerArrow.lua does the same when pandaUI's arrow is not running.
local function NativeArrowParked()
  local own = _G["PandaMapPlayerArrow"]
  if type(own) == "table" and own.IsParked() then return true end
  local hostUI = _G["PandaUI"]
  if type(hostUI) ~= "table" or type(hostUI.GetModule) ~= "function" then
    return false
  end
  local ok, arrow = pcall(hostUI.GetModule, "playerarrow")
  return ok and type(arrow) == "table" and type(arrow.state) == "table"
    and arrow.state.originalWorldMapPosition ~= nil
end

-- The native player arrow is a WorldMapFrame Model placed in
-- WorldMapDetailFrame units, so its offsets are rescaled with the map.
local function WrapNativeArrow()
  local original = _G["PositionWorldMapArrowFrame"]
  if type(original) ~= "function" then return end
  PositionWorldMapArrowFrame = function(a1, a2, a3, a4, a5, a6)
    local vs = state.viewportScale or 1
    if (state.zoom ~= 1 or vs ~= 1) and type(a4) == "number"
        and type(a5) == "number" and not NativeArrowParked() then
      local mapX, mapY = a4, -a5
      if mapX < state.panX or mapY < state.panY
          or mapX > state.panX + state.width / state.zoom
          or mapY > state.panY + state.height / state.zoom then
        a4, a5 = -5000, -5000
      else
        a4 = (mapX - state.panX) * state.zoom * vs
        a5 = -(mapY - state.panY) * state.zoom * vs
        a2, a3 = VIEWPORT_NAME, "TOPLEFT"
      end
    end
    return original(a1, a2, a3, a4, a5, a6)
  end
end

local function MapKey()
  local continent, zone
  if type(GetCurrentMapContinent) == "function" then
    local ok, value = pcall(GetCurrentMapContinent)
    if ok then continent = value end
  end
  if type(GetCurrentMapZone) == "function" then
    local ok, value = pcall(GetCurrentMapZone)
    if ok then zone = value end
  end
  return tostring(continent) .. ":" .. tostring(zone)
end

-- Zoom hint ------------------------------------------------------------------
--
-- The verified world-map overlay shape (pandaUI's cursor readout): a
-- high-level Button with a file-backed BACKGROUND texture, the icon and a
-- label. Mouse is off so the map below keeps its hover and clicks.

local function BuildHint()
  local canvas = state.button
  local ok, frame = pcall(CreateFrame, "Button", "PandaMapWorldMapZoomHint", canvas)
  if not ok or not frame then return end
  frame:SetHeight(HINT_ICON + 4)
  frame:SetPoint("TOPRIGHT", canvas, "TOPRIGHT", -8, -8)
  frame:SetFrameLevel(math.max((NumberMethod(canvas, "GetFrameLevel") or 0) + 20, 120))
  if frame.EnableMouse then frame:EnableMouse(false) end

  local fill = frame:CreateTexture(nil, "BACKGROUND")
  fill:SetTexture("Interface\\Buttons\\WHITE8X8")
  fill:SetAllPoints(frame)
  fill:SetVertexColor(HINT_BACKGROUND[1], HINT_BACKGROUND[2], HINT_BACKGROUND[3],
    HINT_BACKGROUND[4])

  local icon = frame:CreateTexture(nil, "ARTWORK")
  icon:SetTexture(HINT_TEXTURE)
  icon:SetWidth(HINT_ICON)
  icon:SetHeight(HINT_ICON)
  icon:SetPoint("LEFT", frame, "LEFT", 4, 0)

  local width = 4 + HINT_ICON + 7
  local labelOk, label = pcall(frame.CreateFontString, frame, nil, "OVERLAY",
    "GameFontNormal")
  if labelOk and label then
    label:SetPoint("LEFT", icon, "RIGHT", 4, 0)
    label:SetJustifyH("LEFT")
    label:SetTextColor(HINT_TEXT[1], HINT_TEXT[2], HINT_TEXT[3], HINT_TEXT[4])
    label:SetText(PandaMapLocale.L("MAP_ZOOM_HINT"))
    local textWidth = NumberMethod(label, "GetStringWidth") or 0
    if textWidth <= 0 then textWidth = 40 end
    width = width + 4 + textWidth
  end
  frame:SetWidth(width)
  state.hint = frame
  Pin(frame, "TOPRIGHT", "TOPRIGHT", -8, -8)
end

-- Install ----------------------------------------------------------------------
--
-- Everything that can fail is created and checked before a native frame is
-- touched, so a failure leaves the stock map as it was.

local function Install()
  local map = _G["WorldMapFrame"]
  local guide = _G["WorldMapPositioningGuide"]
  local detail = _G["WorldMapDetailFrame"]
  local button = _G["WorldMapButton"]
  local world = _G["WorldFrame"]
  if not map or not guide or not detail or not button or not world then
    return false, "native map frames missing"
  end

  local width = NumberMethod(detail, "GetWidth")
  local height = NumberMethod(detail, "GetHeight")
  if not width or not height or width <= 0 or height <= 0 then
    return false, "no WorldMapDetailFrame size"
  end
  state.width, state.height = width, height

  local detailLevel = NumberMethod(detail, "GetFrameLevel")
  local buttonLevel = NumberMethod(button, "GetFrameLevel")
  if not detailLevel or not buttonLevel then return false, "no frame levels" end

  local ok, viewport = pcall(CreateFrame, "ScrollFrame", VIEWPORT_NAME, world)
  if not ok or not viewport then return false, "no ScrollFrame" end
  pcall(viewport.SetFrameStrata, viewport, "FULLSCREEN")
  local holder = CreateFrame("Frame", "PandaMapWorldMapZoomHolder", viewport)
  local content = CreateFrame("Frame", "PandaMapWorldMapZoomContent", holder)
  local markers = CreateFrame("Frame", "PandaMapWorldMapZoomMarkers", holder)
  if not holder or not content or not markers then
    viewport:Hide()
    return false, "no content frames"
  end

  local built = pcall(function()
    viewport:SetWidth(width)
    viewport:SetHeight(height)
    viewport:SetPoint("TOPLEFT", guide, "TOP", NATIVE_ANCHOR_X, NATIVE_ANCHOR_Y)
    viewport:SetFrameLevel(detailLevel)
    holder:SetWidth(width)
    holder:SetHeight(height)
    holder:SetFrameLevel(detailLevel)
    content:SetWidth(width)
    content:SetHeight(height)
    content:SetPoint("TOPLEFT", holder, "TOPLEFT", 0, 0)
    content:SetFrameLevel(detailLevel)
    markers:SetWidth(width)
    markers:SetHeight(height)
    markers:SetPoint("TOPLEFT", holder, "TOPLEFT", 0, 0)
    markers:SetFrameLevel(detailLevel)
    viewport:SetScrollChild(holder)
  end)
  if not built then
    viewport:Hide()
    return false, "viewport setup failed"
  end

  state.viewport, state.holder, state.content = viewport, holder, content
  state.markers = markers
  state.world, state.detail, state.button = world, detail, button

  -- SetParent is not assumed to keep frame levels; restore the measured ones
  -- so pins built from WorldMapButton:GetFrameLevel() stay above the tiles.
  detail:SetParent(content)
  detail:ClearAllPoints()
  detail:SetPoint("TOPLEFT", content, "TOPLEFT", 0, 0)
  button:SetParent(markers)
  button:ClearAllPoints()
  button:SetPoint("TOPLEFT", markers, "TOPLEFT", 0, 0)
  pcall(detail.SetFrameLevel, detail, detailLevel)
  pcall(button.SetFrameLevel, button, buttonLevel)

  pcall(viewport.EnableMouseWheel, viewport, true)
  pcall(viewport.SetScript, viewport, "OnMouseWheel", OnWheel)

  pcall(button.RegisterForDrag, button, "LeftButton")
  WrapNativeHover(button)
  PostHookScript(button, "OnMouseDown", OnMouseDown)
  PostHookScript(button, "OnDragStart", OnDragStart)
  PostHookScript(button, "OnDragStop", OnDragStop)
  WrapMouseUp(button)

  state.driver = CreateFrame("Frame", "PandaMapWorldMapZoomDriver", world)
  if state.driver then state.driver:SetScript("OnUpdate", DriverOnUpdate) end

  WrapNativeArrow()
  WrapWindowToggle("WorldMapFrame_Minimize")
  WrapWindowToggle("WorldMapFrame_Maximize")
  -- The stock OnShow pings the player (WorldMapFrame_PingPlayerPosition); with
  -- the zoom layout that ping draws away from the player cursor, so it is
  -- hidden before the first draw, as pandaUI does (knowledge.json /
  -- map.worldmap_open_ping_detached_from_player_arrow).
  PostHookScript(map, "OnShow", function()
    pcall(viewport.Show, viewport)
    Layout()
    Reset()
    local ping = _G["WorldMapPing"]
    if ping and ping.Hide then pcall(ping.Hide, ping) end
  end)
  PostHookScript(map, "OnHide", function()
    state.dragging = false
    FinishResize()
    pcall(viewport.Hide, viewport)
  end)
  if not (map.IsVisible and map:IsVisible()) then viewport:Hide() end

  -- WORLD_MAP_UPDATE can arrive as native map input settles, including at the
  -- end of a pan.  It is not a request to zoom out: keep the current zoom and
  -- pan across those updates.  The map's OnShow handler still starts a newly
  -- opened map at 1x, while the wheel remains the explicit zoom control.
  local events = CreateFrame("Frame", nil, world)
  events:RegisterEvent("WORLD_MAP_UPDATE")
  events:SetScript("OnEvent", function()
    local key = MapKey()
    if key ~= state.mapKey then
      state.mapKey = key
    end
  end)

  state.installed = true
  return true
end

-- Ownership --------------------------------------------------------------------

local function PandaUIZoomInstalled()
  if _G["PandaUIWorldMapViewport"] then return true end
  local hostUI = _G["PandaUI"]
  if type(hostUI) ~= "table" or type(hostUI.GetModule) ~= "function" then
    return false
  end
  local ok, zoom = pcall(hostUI.GetModule, "worldmapzoom")
  return ok and type(zoom) == "table" and type(zoom.state) == "table"
    and zoom.state.installed and true or false
end

-- True once pandaUI is known absent or has finished enabling its modules.
local function CanDecide()
  local hostUI = _G["PandaUI"]
  return type(hostUI) ~= "table" or hostUI.ready and true or false
end

-- Another addon has already moved the native canvas (a zoom of its own).
local function CanvasMoved()
  local detail, map = _G["WorldMapDetailFrame"], _G["WorldMapFrame"]
  if not detail or not map or type(detail.GetParent) ~= "function" then
    return false
  end
  local ok, parent = pcall(detail.GetParent, detail)
  return ok and parent ~= map
end

-- pandaUI skipped its zoom for this one; with this one failed, it installs.
local function EnablePandaUIZoom()
  local hostUI = _G["PandaUI"]
  if type(hostUI) ~= "table" or type(hostUI.GetModule) ~= "function" then return end
  local ok, zoom = pcall(hostUI.GetModule, "worldmapzoom")
  if ok and type(zoom) == "table" and type(zoom.OnEnable) == "function" then
    pcall(zoom.OnEnable, zoom)
  end
end

local function Decide()
  if PandaUIZoomInstalled() then
    state.owner = "pandaUI"
    return
  end
  if CanvasMoved() then
    state.owner = "other"
    return
  end
  local ok, installed, failure = pcall(Install)
  if not ok then
    state.failure = tostring(installed)
  elseif not installed then
    state.failure = failure
  end
  if state.failure then
    EnablePandaUIZoom()
    return
  end
  state.owner = "pandaMap"
  local area = _G["WorldMapFrameAreaFrame"]
  if area then Pin(area, "TOP", "TOP", 0, -10) end
  pcall(BuildHint)
  pcall(BuildResizeGrip)
  state.mapKey = MapKey()
  Layout()
end

local function StartPerf()
  if not state.installed then
    return "not started: PandaMap does not own the active map zoom"
  end
  if type(PandaMapDB) ~= "table" then PandaMapDB = {} end
  local memory = gcinfo()
  local perf = {
    schema = 1,
    active = true,
    startedAt = GetTime(),
    lastMotionAt = nil,
    mapKey = MapKey(),
    owner = state.owner,
    windowed = state.windowed and true or false,
    terrainEnabled = PandaMapDB.terrain3D ~= false,
    startZoom = state.zoom,
    pinCount = table.getn(state.pins),
    startMemory = memory,
    endMemory = memory,
    minMemory = memory,
    maxMemory = memory,
    memoryElapsed = 0,
    wheelEvents = 0,
    dragStarts = 0,
    glideStarts = 0,
    zoomFrames = 0,
    zoomTime = 0,
    zoomTime2 = 0,
    zoomMax = 0,
    zoomSlow = 0,
    zoomVerySlow = 0,
    panFrames = 0,
    panTime = 0,
    panTime2 = 0,
    panMax = 0,
    panSlow = 0,
    panVerySlow = 0,
    dragFrames = 0,
    dragTime = 0,
    dragMax = 0,
    dragSlow = 0,
    glideFrames = 0,
    glideTime = 0,
    glideMax = 0,
    glideSlow = 0,
    artScaleWrites = 0,
    artMoveWrites = 0,
    markerScaleWrites = 0,
    markerMoveWrites = 0,
    markerSyncCalls = 0,
    markerHidePasses = 0,
    markerHideObjects = 0,
    markerHideMax = 0,
    markerShowPasses = 0,
    markerShowObjects = 0,
    hitRectWrites = 0,
    pinPasses = 0,
    pinWrites = 0,
  }
  PandaMapDB.perfLog = perf
  state.perf = perf
  return "recording started - zoom, drag and glide, then /reload"
end

local gate = CreateFrame("Frame", "PandaMapWorldMapZoomGate", _G["WorldFrame"] or UIParent)
gate:RegisterEvent("PLAYER_LOGIN")
gate:SetScript("OnEvent", function()
  gate:UnregisterEvent("PLAYER_LOGIN")
  local waited = 0
  gate:SetScript("OnUpdate", function()
    waited = waited + (tonumber(arg1) or 0)
    if not CanDecide() and waited < GATE_TIMEOUT then return end
    gate:SetScript("OnUpdate", nil)
    Decide()
  end)
end)

PandaMapZoom = {
  Pin = Pin,
  -- Read by pandaUI's worldmapzoom module before it installs.
  ClaimsZoom = function()
    return state.failure == nil and state.owner ~= "pandaUI"
      and state.owner ~= "other"
  end,
  GetOwner = function() return state.owner end,
  IsInstalled = function() return state.installed end,
  StartPerf = StartPerf,
  -- Kept for diagnostics; /pmap perf starts a persistent capture instead.
  GetPerf = function()
    local p = state.perf
    if not p then return "no active capture" end
    local function Line(frames, total, max, slow)
      if frames == 0 then return "no frames" end
      return string.format("%d frames, avg %.1f ms, max %.1f ms, %d over 25 ms",
        frames, total / frames * 1000, max * 1000, slow)
    end
    local text = "zoom: " .. Line(p.zoomFrames, p.zoomTime, p.zoomMax, p.zoomSlow)
      .. " | pan: " .. Line(p.panFrames, p.panTime, p.panMax, p.panSlow)
    return text
  end,
  GetZoom = function() return state.zoom end,
  GetFailure = function() return state.failure end,
}
