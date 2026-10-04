"""Explicit finite presentation test; remove an older owned chain before reloading."""
import importlib
from blacklands_passthrough import postprocess_trial

postprocess_trial.stop('module_refresh')
importlib.reload(postprocess_trial)
postprocess_trial.start()
