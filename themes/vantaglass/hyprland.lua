-- Vantaglass geometry; user overrides load afterward.
hl.config({
  general = { gaps_in = 5, gaps_out = 12, border_size = 1,
    col = { active_border = "#FFFFFF30", inactive_border = "#FFFFFF16" } },
  decoration = { rounding = 18, rounding_power = 2.0,
    shadow = { enabled = true, range = 30, render_power = 3, color = "rgba(00000032)" },
    blur = { enabled = true, size = 6, passes = 2, new_optimizations = true,
      xray = false, contrast = 1.0, brightness = 1.0, noise = 0.008, vibrancy = 0.12, popups = true } },
  group = { col = { border_active = "#FFFFFF30", border_inactive = "#FFFFFF16" } },
})
for _, ns in ipairs({ "^omarchy-bar$", "^omarchy-menu$", "^omarchy-notifications$", "^omarchy-keyboard-panel$" }) do
  hl.layer_rule({ match = { namespace = ns }, blur = true, ignore_alpha = 0.35 })
end
-- Match the Omarchy bar's compositor settings when switching workspaces.
hl.layer_rule({ match = { namespace = "^vantaglass-entertainment$" },
  blur = true, ignore_alpha = 0.35, no_anim = true, animation = "none" })
local entertainment = (os.getenv("HOME") or "") .. "/.local/share/vantaglass/runtime/entertainment/layout.lua"
local layout_file = io.open(entertainment, "r")
if layout_file then
  layout_file:close()
  dofile(entertainment)
  hl.bind("SUPER + E", hl.dsp.global("vantaglass:entertainment"), {
    description = "Enter or return to Entertainment",
    dont_inhibit = true,
  })

  local function bind_entertainment_focus(key, target, direction)
    -- Omarchy normally uses these keys for directional window focus.
    hl.unbind(key)
    hl.bind(key, function()
      local workspace = hl.get_active_special_workspace() or hl.get_active_workspace()
      if workspace and workspace.name == "entertainment" then
        hl.dispatch(hl.dsp.global("vantaglass:entertainment-" .. target))
      elseif _G.omarchy_default_bindings ~= false then
        hl.dispatch(hl.dsp.focus({ direction = direction }))
      end
    end, { description = "Focus Entertainment " .. target .. " or move window focus" })
  end

  bind_entertainment_focus("SUPER + UP", "stage", "u")
  bind_entertainment_focus("SUPER + DOWN", "apps", "d")
end
-- Window rules retain the terminal silhouette when personal defaults differ.
-- Only the background is translucent; compositor opacity would also fade text.
hl.window_rule({
  match = { tag = "terminal" },
  rounding = 18, rounding_power = 2.0, border_size = 1,
  opacity = "1.0 override 1.0 override",
  no_blur = false, no_shadow = false,
  border_color = { colors = { "rgba(ffffff26)", "rgba(ffffff08)" }, angle = 110 },
})
hl.window_rule({
  match = { tag = "terminal", focus = true },
  border_color = { colors = { "rgba(ffffff52)", "rgba(ffffff0d)" }, angle = 110 },
})
