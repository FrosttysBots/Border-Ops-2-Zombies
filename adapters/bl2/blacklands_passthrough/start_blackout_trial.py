"""Explicit finite presentation test; restore an older blackout trial before reloading."""
import importlib
from blacklands_passthrough import ao_key_trial, foreground_trial, blackout_trial

blackout_trial.stop('module_refresh')
importlib.reload(ao_key_trial)
importlib.reload(foreground_trial)
importlib.reload(blackout_trial)
blackout_trial.start()
