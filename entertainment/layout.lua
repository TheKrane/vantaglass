-- The stage and its live shelf are one Hyprland layout.
local workspace = "name:entertainment"
local state = { order = {}, offset = 0 }
local gutter, gap, padding, header, footer = 14, 10, 12, 12, 49

local function monitor_size(monitor)
  local width, height = monitor.width, monitor.height
  if (monitor.transform or 0) % 2 == 1 then width, height = height, width end
  return width / monitor.scale, height / monitor.scale
end

local function fit(width, height, aspect)
  local w = math.max(1, math.min(width, height * aspect))
  return math.max(1, math.floor(w + .5)), math.max(1, math.floor(w / aspect + .5))
end

local function geometry(area, monitor)
  local width, height = monitor_size(monitor)
  local aspect = width / height
  local shelf_width = math.max(1, math.min(1440, area.w - gutter * 2))
  local tile_width, tile_height = fit(math.min(192, shelf_width - padding * 2),
    math.min(116, math.max(45, area.h * .145)), aspect)
  local columns = math.max(1, math.floor((shelf_width - padding * 2 + gap) / (tile_width + gap)))
  local row_width = columns * tile_width + (columns - 1) * gap
  local shelf_x = math.floor((area.w - shelf_width) / 2)
  local tile_x = shelf_x + math.floor((shelf_width - row_width) / 2)
  local shelf_height = header + tile_height + footer
  local stage_area_height = math.max(1, area.h - shelf_height - gutter * 3)
  local stage_width, stage_height = fit(area.w - gutter * 2, stage_area_height, aspect)
  return {
    columns = columns, shelfX = shelf_x, shelfY = area.h - shelf_height - gutter,
    shelfWidth = shelf_width, shelfHeight = shelf_height,
    bottom = gutter, tileX = tile_x, tileY = header, tileWidth = tile_width, tileHeight = tile_height, gap = gap,
    stageX = math.floor((area.w - stage_width) / 2),
    stageY = gutter + math.floor((stage_area_height - stage_height) / 2),
    stageWidth = stage_width, stageHeight = stage_height,
  }
end

local function sync(targets)
  local current, ordered = {}, {}
  for _, target in ipairs(targets) do
    local window = target.window
    if window then current[window.address] = target end
  end
  for _, address in ipairs(state.order) do
    if current[address] then
      ordered[#ordered + 1] = address
      current[address] = nil
    end
  end
  for _, target in ipairs(targets) do
    local window = target.window
    if window and current[window.address] then ordered[#ordered + 1] = window.address end
  end
  state.order = ordered
end

local function parking_x()
  local right = 0
  for _, monitor in ipairs(hl.get_monitors()) do
    local width = monitor_size(monitor)
    right = math.max(right, monitor.x + width)
  end
  return right + 192
end

local function slot_for(address)
  for i, candidate in ipairs(state.order) do
    if candidate == address then return i end
  end
end

local function swap_with_stage(slot)
  state.order[1], state.order[slot] = state.order[slot], state.order[1]
end

hl.layout.register("vantaglass-entertainment", {
  recalculate = function(ctx)
    sync(ctx.targets)
    local ws = hl.get_workspace(workspace)
    local monitor = ws and ws.monitor
    if not monitor then return end
    local area = ctx.area
    local geo = geometry(area, monitor)
    local shelf_y = area.y + geo.shelfY
    local slots = {}
    for i, address in ipairs(state.order) do slots[address] = i end

    local parked
    for _, target in ipairs(ctx.targets) do
      local window = target.window
      local i = window and slots[window.address]
      if i == 1 then
        target:place({ x = area.x + geo.stageX, y = area.y + geo.stageY,
          w = geo.stageWidth, h = geo.stageHeight })
      elseif i then
        local slot = i - 2 - state.offset
        local x
        if slot >= 0 and slot < geo.columns then
          x = area.x + geo.tileX + slot * (geo.tileWidth + geo.gap)
        else
          parked = parked or parking_x()
          x = parked
        end
        target:place({ x = x, y = shelf_y + geo.tileY, w = geo.tileWidth, h = geo.tileHeight })
      end
    end
  end,
  layout_msg = function(_, message)
    local offset = tonumber(message:match("^page (%d+)$"))
    if offset then state.offset = math.min(10000, offset) end
    local address = message:match("^stage (0x%x+)$")
    if address then
      local slot = slot_for(address)
      if not slot then return "The window is outside the Entertainment layout" end
      swap_with_stage(slot)
    end
  end,
})

hl.workspace_rule({ workspace = workspace, layout = "lua:vantaglass-entertainment", persistent = true,
  gaps_in = 0, gaps_out = 0, no_border = true, no_shadow = true })
hl.window_rule({
  name = "vantaglass-entertainment-windows", match = { workspace = workspace },
  tile = true, no_follow_mouse = true, keep_aspect_ratio = true,
  suppress_event = "fullscreen maximize fullscreenoutput",
})

local function entertainment_workspace(ws)
  return ws and ws.name == "entertainment"
end

-- Like Omarchy's floating mode, scope the pointer policy to the active
-- workspace and restore the user's normal setting when leaving it.
local resize_on_border
local function update_border_resize()
  if resize_on_border == nil then return end
  local active = hl.get_active_special_workspace() or hl.get_active_workspace()
  local enabled = resize_on_border and not entertainment_workspace(active)
  if hl.get_config("general.resize_on_border") ~= enabled then
    hl.config({ general = { resize_on_border = enabled } })
  end
end
hl.on("config.reloaded", function()
  resize_on_border = hl.get_config("general.resize_on_border")
  update_border_resize()
end)
hl.on("workspace.active", update_border_resize)
hl.on("workspace.special_active", update_border_resize)
hl.on("monitor.focused", update_border_resize)

local function bind_window_gesture(key, description, dispatcher)
  o.rebind(key, description, function()
    local monitor = hl.get_monitor_at_cursor()
    local active = monitor and (monitor.active_special_workspace or monitor.active_workspace)
    if not entertainment_workspace(active) then hl.dispatch(dispatcher) end
  end, { mouse = true })
end

if _G.omarchy_default_bindings ~= false then
  bind_window_gesture("SUPER + mouse:272", "Move window", hl.dsp.window.drag())
  bind_window_gesture("SUPER + mouse:273", "Resize window", hl.dsp.window.resize())
end

local function entertainment_window(address)
  local window = address and hl.get_window("address:" .. address)
  if window and window.mapped and window.workspace and window.workspace.name == "entertainment" then
    return window
  end
end

local function clear_fullscreen(window)
  hl.dispatch(hl.dsp.window.fullscreen_state({ window = window, internal = 0, client = 0, action = "set" }))
end

-- Lua owns the shared dimensions. The shell just paints around the client rectangles.
vantaglass_entertainment = {
  present = function(active, address)
    address = address or state.order[1]
    local window = entertainment_window(address)
    if not window then return "The stage window is unavailable" end

    local slot = slot_for(address)
    if not slot then return "The window is outside the Entertainment layout" end

    if (window.fullscreen & 2) == 0 then
      local previous = active.fullscreen_window
      if previous and previous.address ~= address then clear_fullscreen(previous) end
      hl.dispatch(hl.dsp.focus({ window = window }))
      hl.dispatch(hl.dsp.window.fullscreen({ window = window, mode = "fullscreen", action = "set" }))
      if (window.fullscreen & 2) == 0 then return "The stage could not enter fullscreen" end
    end
    -- Keep the live tile as the animation origin and record the order the
    -- layout will use when Hyprland restores the tiled windows.
    swap_with_stage(slot)
    return "ok"
  end,
  promote = function(active, address)
    if active.fullscreen_window then return "Open the shelf before moving a window to the stage" end
    local window = entertainment_window(address)
    local slot = slot_for(address)
    if not window or not slot or slot <= state.offset + 1 then return "The shelf window is unavailable" end
    -- Change the two destinations in one layout pass. Hyprland interpolates
    -- both windows from their existing positions and sizes.
    hl.dispatch(hl.dsp.layout("stage " .. address))
    if state.order[1] ~= address then return "The window could not move to the stage" end
    return "ok"
  end,
  restore = function(active)
    local fullscreen = active.fullscreen_window
    if fullscreen then clear_fullscreen(fullscreen) end
    return "ok"
  end,
  snapshot = function()
    local ws = hl.get_workspace(workspace)
    local monitor = ws and ws.monitor
    if not monitor then return '{"windows":[],"offset":0,"geometry":{}}' end
    local width, height = monitor_size(monitor)
    local reserved = monitor.reserved
    local area = { w = width - reserved.left - reserved.right, h = height - reserved.top - reserved.bottom }
    local geo = geometry(area, monitor)
    local fields = {}
    for key, value in pairs(geo) do fields[#fields + 1] = string.format('"%s":%d', key, value) end
    local windows = #state.order > 0 and '"' .. table.concat(state.order, '","') .. '"' or ""
    return string.format('{"windows":[%s],"offset":%d,"geometry":{%s}}',
      windows, state.offset, table.concat(fields, ","))
  end,
}
