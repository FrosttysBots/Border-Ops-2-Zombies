"""Read-only, one-shot fog component reflection. No engine commands or setters.

Hypothesis under test: UE3 renders height fog for the world group only, so a dense
key-coloured fog could cover donor-world pixels while arms/gun in SDPG_Foreground
remain. This file only reports which fog components exist and their fields.
"""
from datetime import datetime, timezone
import json
import math
import os
from pathlib import Path
from mods_base import get_pc
from unrealsdk import find_all, find_class, logging
from unrealsdk.unreal import UFunction

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


CLASSES = ('Engine.HeightFogComponent', 'Engine.ExponentialHeightFogComponent',
           'Engine.HeightFog', 'Engine.ExponentialHeightFog')
MAX_OBJECTS = 16
MAX_FIELDS = 96


def describe(obj):
    rows = {}
    for cls in obj.Class._superfields():
        if cls._path_name() in ('Core.Object', 'Engine.ActorComponent', 'Engine.Actor'):
            continue
        for field in cls._fields():
            name = str(field.Name)
            if len(rows) >= MAX_FIELDS:
                return rows
            if name in rows:
                continue
            if isinstance(field, UFunction):
                rows[name] = {'type': 'Function', 'declared_on': cls._path_name(),
                              'parameters': [str(p.Name) for p in field._properties() if p.PropertyFlags & 0x80][:12]}
            elif str(field.Class.Name).endswith('Property'):
                row = {'type': str(field.Class.Name), 'declared_on': cls._path_name()}
                try: row['value'] = primitive(getattr(obj, name))
                except Exception as exc: row['unavailable'] = type(exc).__name__
                rows[name] = row
    return rows


def run():
    pc = get_pc(possibly_loading=True)
    if pc is None or pc.Pawn is None:
        raise RuntimeError('Load a BL2 character first.')
    report = dict(schema=1, revision=1, readonly=True, observed_at=datetime.now(timezone.utc).isoformat(),
                  classes={})
    for name in CLASSES:
        try:
            cls = find_class(name)
        except Exception as exc:
            report['classes'][name] = dict(unavailable=type(exc).__name__)
            continue
        objects = []
        for obj in find_all(cls, exact=False):
            if len(objects) >= MAX_OBJECTS:
                break
            path = obj._path_name()
            if 'Default__' in path:
                continue
            objects.append(dict(path=path, cls=obj.Class._path_name(), fields=describe(obj)))
        report['classes'][name] = dict(count=len(objects), objects=objects)
    box = (Path(os.environ['BLACKLANDS_MAILBOX']) if os.environ.get('BLACKLANDS_MAILBOX')
           else Path(os.environ['LOCALAPPDATA'])/'Plutonium/storage/t6/raw/scriptdata')
    text = json.dumps(report, indent=2, allow_nan=False)
    if len(text.encode('utf-8')) > 1048576:
        raise ValueError('Fog report exceeds 1 MiB bound')
    target = box/'blacklands_fog_api.json'
    temp = target.with_suffix('.tmp')
    temp.write_text(text+'\n', encoding='utf-8')
    temp.replace(target)
    logging.info('BlackLands: read-only fog report written; no rendering state changed.')


run()
