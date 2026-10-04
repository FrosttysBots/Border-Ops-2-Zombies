"""Explicit finite presentation test; restore an older coverage trial before reloading."""
import importlib
from blacklands_passthrough import ao_key_trial, foreground_trial, coverage_trial

coverage_trial.stop('module_refresh')
importlib.reload(ao_key_trial)
importlib.reload(foreground_trial)
importlib.reload(coverage_trial)
coverage_trial.start()
