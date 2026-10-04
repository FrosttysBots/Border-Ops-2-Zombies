"""One-shot reflection only. Run with SDK pyexec; does not invoke game functions."""
import json
import math
import os
from pathlib import Path
from datetime import datetime, timezone
from mods_base import get_pc
from unrealsdk import logging
from unrealsdk.unreal import UFunction


def run():
    pc = get_pc(possibly_loading=True)
    if pc is None or pc.Pawn is None or pc.Pawn.Weapon is None:
        raise RuntimeError('Load a character and equip a weapon first.')
    weapon = pc.Pawn.Weapon
    words = ('damage', 'ammo', 'clip', 'projectile', 'firing', 'accuracy', 'spread', 'reload')
    rows = {}
    for cls in weapon.Class._superfields():
        for field in cls._fields():
            name = str(field.Name)
            if name in rows or not any(word in name.lower() for word in words):
                continue
            if len(rows) >= 256:
                break
            row = {'type': str(field.Class.Name), 'declared_on': cls._path_name()}
            if isinstance(field, UFunction):
                row['parameters'] = [
                    {'name': str(p.Name), 'type': str(p.Class.Name), 'flags': p.PropertyFlags}
                    for p in field._properties() if p.PropertyFlags & 0x80
                ][:32]
            else:
                try:
                    value = getattr(weapon, name)
                    if value is None or isinstance(value, (str, bool, int, float)):
                        row['value'] = value if not isinstance(value, float) or math.isfinite(value) else None
                    elif hasattr(value, '_path_name'):
                        row['object'] = value._path_name()
                    else:
                        row['python_type'] = type(value).__name__
                except Exception as exc:
                    row['unavailable'] = type(exc).__name__
            rows[name] = row
    box = Path(os.environ['BLACKLANDS_MAILBOX']) if os.environ.get('BLACKLANDS_MAILBOX') else Path(os.environ['LOCALAPPDATA'])/'Plutonium/storage/t6/raw/scriptdata'
    report = {'observed_at': datetime.now(timezone.utc).isoformat(),
              'object_path': weapon._path_name(), 'fields': rows}
    text = json.dumps(report, indent=2, allow_nan=False)
    if len(text.encode('utf-8')) > 131072:
        raise ValueError('Reflection report too large')
    (box/'blacklands_weapon_api.json').write_text(text+'\n', encoding='utf-8')
    logging.info('BlackLands: read-only weapon API report written.')


run()
