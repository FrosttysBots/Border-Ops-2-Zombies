"""Explicit finite presentation test; restore an older foreground trial before reloading."""
import importlib
from blacklands_passthrough import ao_key_trial, foreground_trial

foreground_trial.stop('module_refresh')
importlib.reload(ao_key_trial)
importlib.reload(foreground_trial)
foreground_trial.start()
