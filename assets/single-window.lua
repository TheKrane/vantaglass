-- Center a lone dwindle window at 75% of the usable monitor area.
-- Native workspace selectors restore ordinary gaps when another tiled window opens.
local rules = {}

local function update()
  for _, monitor in ipairs(hl.get_monitors()) do
    local width, height = monitor.width / monitor.scale, monitor.height / monitor.scale
    if (monitor.transform or 0) % 2 == 1 then
      width, height = height, width
    end
    local reserved = monitor.reserved or {}
    width = width - (reserved.left or 0) - (reserved.right or 0)
    height = height - (reserved.top or 0) - (reserved.bottom or 0)
    local horizontal = math.floor(width * 0.125 + 0.5)
    local vertical = math.floor(height * 0.125 + 0.5)
    local entry = rules[monitor.name]
    if not entry or entry.horizontal ~= horizontal or entry.vertical ~= vertical then
      if entry then entry.rule:set_enabled(false) end
      entry = {
        horizontal = horizontal,
        vertical = vertical,
        rule = hl.workspace_rule({
          workspace = "m[" .. monitor.name .. "]s[false]w[tv1]",
          gaps_out = { top = vertical, bottom = vertical, left = horizontal, right = horizontal },
        }),
      }
      rules[monitor.name] = entry
    end
    local workspace = monitor.active_workspace
    local enabled = workspace ~= nil and workspace.tiled_layout == "dwindle" and not workspace.has_fullscreen
    if entry.rule:is_enabled() ~= enabled then
      entry.rule:set_enabled(enabled)
    end
  end
end

for _, event in ipairs({ "config.reloaded", "config.props_refreshed", "monitor.layout_changed", "workspace.active", "window.fullscreen" }) do
  hl.on(event, update)
end
update()
