-- Development checkout compatibility. Published core packages omit this file;
-- each separately installed map-pack addon registers its own top-level root.
local root = "Interface\\AddOns\\pandaMap\\Packs\\"

if PandaMap and type(PandaMap.RegisterPack) == "function" then
  PandaMap.RegisterPack("PandaMap_World", root .. "PandaMap_World\\")
  PandaMap.RegisterPack("PandaMap_Unexplored", root .. "PandaMap_Unexplored\\")
  PandaMap.RegisterPack("PandaMap_Terrain", root .. "PandaMap_Terrain\\")
end
