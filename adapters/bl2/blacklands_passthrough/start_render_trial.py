"""Explicit finite presentation test; restore an older trial before reloading."""
import importlib
from blacklands_passthrough import render_trial

render_trial.stop('module_refresh')
importlib.reload(render_trial)
render_trial.start()
