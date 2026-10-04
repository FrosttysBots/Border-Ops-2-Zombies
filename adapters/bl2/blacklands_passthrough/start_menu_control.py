"""Explicitly activate finite inventory control and refresh read-only player state."""
import importlib
from blacklands_passthrough import menu_control, menu_wire, player_probe, player_state

menu_control.stop('module_refresh')
player_probe.stop('module_refresh')
for module in (menu_wire, player_state, player_probe, menu_control):
    importlib.reload(module)
player_probe.start()
try:
    menu_control.start()
except Exception:
    player_probe.stop('menu_start_failed')
    raise
