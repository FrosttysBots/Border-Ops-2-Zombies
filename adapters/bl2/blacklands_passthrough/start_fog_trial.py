"""Explicit finite presentation test; restore an older fog trial before reloading."""
import importlib
from blacklands_passthrough import ao_key_trial, foreground_trial, fog_trial

fog_trial.stop('module_refresh')
importlib.reload(ao_key_trial)
importlib.reload(foreground_trial)
importlib.reload(fog_trial)
fog_trial.start()
