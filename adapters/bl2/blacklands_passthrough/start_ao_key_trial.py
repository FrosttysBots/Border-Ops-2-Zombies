"""Explicit finite presentation test; restore an older AO trial before reloading."""
import importlib
from blacklands_passthrough import ao_key_trial

ao_key_trial.stop('module_refresh')
importlib.reload(ao_key_trial)
ao_key_trial.start()
