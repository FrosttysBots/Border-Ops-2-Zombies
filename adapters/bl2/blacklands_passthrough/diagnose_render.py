"""Read-only, one-shot native rendering reflection. No engine commands or setters."""
from datetime import datetime, timezone
import json
import math
import os
from pathlib import Path
from mods_base import get_pc
from unrealsdk import logging
from unrealsdk.unreal import UFunction

WORDS = ('render', 'view', 'show', 'hud', 'mesh', 'firstperson', 'arms', 'camera',
         'scene', 'depth', 'hidden', 'visibility', 'postprocess', 'suppress', 'clear',
         'health', 'shield', 'grenade', 'resource', 'exp', 'level', 'inventory',
         'backpack', 'equipped', 'character', 'movie', 'pause', 'open')
PATHS = ('', 'Player', 'Player.ViewportClient', 'Pawn', 'Pawn.Mesh', 'Pawn.Arms',
         'Pawn.Weapon', 'Pawn.Weapon.FirstPersonMesh', 'myHUD', 'myHUD.HUDMovie',
         'PlayerReplicationInfo', 'ResourcePoolManager', 'ExpPool.Data', 'Pawn.InvManager')


def primitive(value, depth=0):
    if value is None or isinstance(value, (str, bool, int)):
        return value
    if isinstance(value, float):
        return value if math.isfinite(value) else None
    if hasattr(value, '_path_name'):
        return {'object': value._path_name()}
    if depth < 2 and type(value).__name__ == 'WrappedStruct':
        # Named reflected members only. Opaque pointers are intentionally not read.
        fields = {}
        for prop in value._type._properties():
            name = str(prop.Name)
            if len(fields) >= 24: break
            if 'pointer' in name.lower(): continue
            try: fields[name] = primitive(getattr(value, name), depth+1)
            except Exception as exc: fields[name] = {'unavailable': type(exc).__name__}
        return {'struct': value._type._path_name(), 'fields': fields}
    if depth < 2 and type(value).__name__ in ('WrappedArray', 'tuple', 'list'):
        return {'count': len(value), 'first': [primitive(value[i], depth+1) for i in range(min(len(value),8))]}
    return {'python_type': type(value).__name__}


def describe(obj):
    rows = {}
    for cls in obj.Class._superfields():
        for field in cls._fields():
            name = str(field.Name)
            if len(rows) >= 320:
                return rows
            if name in rows or not any(word in name.lower() for word in WORDS):
                continue
            if not isinstance(field, UFunction) and not str(field.Class.Name).endswith('Property'):
                continue
            row = {'type': str(field.Class.Name), 'declared_on': cls._path_name()}
            if isinstance(field, UFunction):
                row['parameters'] = [dict(name=str(p.Name), type=str(p.Class.Name),
                                          flags=p.PropertyFlags)
                                     for p in field._properties() if p.PropertyFlags & 0x80][:24]
            else:
                try:
                    row['value'] = primitive(getattr(obj, name))
                except Exception as exc:
                    row['unavailable'] = type(exc).__name__
            rows[name] = row
    return rows


def run():
    pc = get_pc(possibly_loading=True)
    if pc is None or pc.Pawn is None:
        raise RuntimeError('Load a BL2 character first.')
    report = dict(schema=1, revision=2, readonly=True, observed_at=datetime.now(timezone.utc).isoformat(),
                  objects={})
    for path in PATHS:
        key = 'pc' + ('.'+path if path else '')
        try:
            obj = pc
            for name in path.split('.') if path else ():
                obj = getattr(obj, name)
            report['objects'][key] = (dict(path=obj._path_name(), fields=describe(obj))
                                      if obj is not None else dict(unavailable='null'))
        except Exception as exc:
            report['objects'][key] = dict(unavailable=type(exc).__name__)
    box = (Path(os.environ['BLACKLANDS_MAILBOX']) if os.environ.get('BLACKLANDS_MAILBOX')
           else Path(os.environ['LOCALAPPDATA'])/'Plutonium/storage/t6/raw/scriptdata')
    text = json.dumps(report, indent=2, allow_nan=False)
    if len(text.encode('utf-8')) > 1048576:
        raise ValueError('Interface report exceeds 1 MiB bound')
    target = box/'blacklands_render_api.json'
    temp = target.with_suffix('.tmp')
    temp.write_text(text+'\n', encoding='utf-8')
    temp.replace(target)
    logging.info('BlackLands: read-only rendering API report written; no rendering state changed.')


run()
