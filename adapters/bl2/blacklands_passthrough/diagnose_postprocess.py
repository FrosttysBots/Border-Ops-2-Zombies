"""Read-only, one-shot post-process chain reflection. No engine commands or setters."""
from datetime import datetime, timezone
import json
import math
import os
from pathlib import Path
from mods_base import get_pc
from unrealsdk import find_class, find_enum, logging
from unrealsdk.unreal import UFunction

# Effect classes that could replace donor-world pixels before the foreground group.
CLASSES = ('Engine.PostProcessChain', 'Engine.PostProcessEffect', 'Engine.UberPostProcessEffect',
           'Engine.MaterialEffect', 'Engine.DOFAndBloomEffect')
ENUMS = ('ESceneDepthPriorityGroup', 'Engine.Scene.ESceneDepthPriorityGroup')
MAX_EFFECTS = 32
MAX_FIELDS = 96


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


def properties(obj):
    """All reflected property values (no functions), bounded; never invokes methods."""
    rows = {}
    for cls in obj.Class._superfields():
        for field in cls._fields():
            name = str(field.Name)
            if len(rows) >= MAX_FIELDS:
                return rows
            if name in rows or isinstance(field, UFunction) or not str(field.Class.Name).endswith('Property'):
                continue
            row = {'type': str(field.Class.Name), 'declared_on': cls._path_name()}
            try: row['value'] = primitive(getattr(obj, name))
            except Exception as exc: row['unavailable'] = type(exc).__name__
            rows[name] = row
    return rows


def chain(obj):
    if obj is None:
        return dict(unavailable='null')
    effects = []
    for effect in list(obj.Effects)[:MAX_EFFECTS]:
        effects.append(dict(path=effect._path_name(), cls=effect.Class._path_name(),
                            fields=properties(effect)) if effect is not None else None)
    return dict(path=obj._path_name(), cls=obj.Class._path_name(), effect_count=len(obj.Effects),
                effects=effects)


def run():
    pc = get_pc(possibly_loading=True)
    if pc is None or pc.Pawn is None:
        raise RuntimeError('Load a BL2 character first.')
    player = pc.Player
    report = dict(schema=1, revision=1, readonly=True, observed_at=datetime.now(timezone.utc).isoformat(),
                  player_chain=None, player_chains=[], classes={}, enums={})
    try: report['player_chain'] = chain(player.PlayerPostProcess)
    except Exception as exc: report['player_chain'] = dict(unavailable=type(exc).__name__)
    for item in list(player.PlayerPostProcessChains)[:8]:
        try: report['player_chains'].append(chain(item))
        except Exception as exc: report['player_chains'].append(dict(unavailable=type(exc).__name__))
    for name in CLASSES:
        try:
            cls = find_class(name)
            # Class defaults show which fields a constructed effect would start with.
            report['classes'][name] = dict(path=cls._path_name(), defaults=properties(cls.ClassDefaultObject))
        except Exception as exc:
            report['classes'][name] = dict(unavailable=type(exc).__name__)
    for name in ENUMS:
        try: report['enums'][name] = {key: int(value) for key, value in find_enum(name).__members__.items()}
        except Exception as exc: report['enums'][name] = dict(unavailable=type(exc).__name__)
    box = (Path(os.environ['BLACKLANDS_MAILBOX']) if os.environ.get('BLACKLANDS_MAILBOX')
           else Path(os.environ['LOCALAPPDATA'])/'Plutonium/storage/t6/raw/scriptdata')
    text = json.dumps(report, indent=2, allow_nan=False)
    if len(text.encode('utf-8')) > 1048576:
        raise ValueError('Post-process report exceeds 1 MiB bound')
    target = box/'blacklands_postprocess_api.json'
    temp = target.with_suffix('.tmp')
    temp.write_text(text+'\n', encoding='utf-8')
    temp.replace(target)
    logging.info('BlackLands: read-only post-process report written; no rendering state changed.')


run()
