"""Reload only our read-only inspector; never register duplicate tick hooks."""
import importlib
from pathlib import Path
import blacklands_passthrough as adapter
from unrealsdk import logging

module = importlib.import_module('blacklands_passthrough.weapon')
if Path(module.__file__).parent.resolve() != Path(adapter.__file__).parent.resolve():
    raise RuntimeError('Inspector must belong to the loaded BlackLands adapter.')
importlib.invalidate_caches()
module = importlib.reload(module)
adapter.inspect_weapon = module.inspect_weapon
logging.info('BlackLands: weapon inspector revision 2 refreshed; existing tick hook retained.')
