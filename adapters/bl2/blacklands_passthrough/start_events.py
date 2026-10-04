"""SDK console entry point; repeated starts remove only our own prior hooks."""
import importlib
from blacklands_passthrough import events, event_wire, hit_trace
events.stop('module_refresh')
importlib.reload(event_wire)
importlib.reload(hit_trace)
importlib.reload(events)
events.start()
