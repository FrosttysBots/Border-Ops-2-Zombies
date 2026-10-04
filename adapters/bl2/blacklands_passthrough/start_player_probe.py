"""Refresh the read-only observer and report selective-render capability availability."""
import importlib
import json
from mods_base import get_pc
from blacklands_passthrough import player_probe, player_state
import blacklands_passthrough as adapter

player_probe.stop('module_refresh')
importlib.reload(player_state)
importlib.reload(player_probe)
pc=get_pc(possibly_loading=True)
capabilities={}
for field in ('HiddenActors','HiddenComponents','HiddenPrimitiveComponents'):
    try:
        value=getattr(pc,field)
        capabilities[field]=dict(available=True,type=type(value).__name__,count=len(value))
    except Exception as exc:
        capabilities[field]=dict(available=False,error=type(exc).__name__)
if adapter._mailbox is None:raise RuntimeError('Enable the main probe first')
(adapter._mailbox/'blacklands_visibility_capabilities.json').write_text(json.dumps(capabilities)+'\n',encoding='utf-8')
player_probe.start()
