"""Explicit SDK activation; preserves the original probe and its hooks."""
import importlib
from blacklands_passthrough import runtime, runtime_ipc

runtime.stop('module_refresh')
importlib.reload(runtime_ipc)
importlib.reload(runtime)
runtime.start()
