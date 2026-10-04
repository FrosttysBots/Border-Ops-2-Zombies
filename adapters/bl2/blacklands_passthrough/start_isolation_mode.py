"""Explicit finite presentation mode; restore an older mode before reloading."""
import importlib
from blacklands_passthrough import ao_key_trial, foreground_trial, fog_trial, isolation_mode

isolation_mode.stop('module_refresh')
importlib.reload(ao_key_trial)
importlib.reload(foreground_trial)
importlib.reload(fog_trial)
importlib.reload(isolation_mode)
isolation_mode.start()
