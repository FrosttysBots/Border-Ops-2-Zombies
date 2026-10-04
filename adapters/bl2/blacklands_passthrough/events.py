"""Finite read-only call capture. No gameplay calls, writes or return overrides."""
import json
import math
import time
import uuid
from mods_base import get_pc
from unrealsdk import hooks, logging
from unrealsdk.unreal import WeakPointer
from .event_wire import EVENT_FILE, MAX_EVENT_BYTES, EventBuffer, parse_events
from .hit_trace import describe, function_schema, bullet_schemas

_capture = None
_specs = (
    ('WillowGame.WillowWeapon:ConsumeAmmo', 'consume_ammo'),
    ('WillowGame.WillowWeapon:FiringModeDefinitionFire', 'fire_mode'),
    ('WillowGame.WillowWeapon:ProjectileDefinitionFire', 'projectile'),
    ('WillowGame.WillowWeapon:BeginReload', 'reload_begin'),
    ('WillowGame.WillowWeapon:ReloadDone', 'reload_done'),
    ('WillowGame.WillowDamageTypeDefinition:DisplayRecentDamageForPlayer', 'display_damage'),
    ('WillowGame.WillowWeapon:ExecuteProjectileFiredConstructEvent', 'projectile_spawn'),
    ('WillowGame.WillowAIPawn:TakeDamage', 'take_damage'),
)
_tick = 'Engine.PlayerController:PlayerTick'
_impact = 'WillowGame.WillowWeapon:ProcessInstantHitBullet'
_prefix = 'blacklands.readonly.events.'


def path(obj):
    return None if obj is None else str(obj._path_name())[:256]


def number(value):
    if type(value) not in (int, float) or not math.isfinite(value) or abs(value) > 1e15:
        raise ValueError('Invalid native numeric event value')
    return value


def packet():
    c = _capture
    return dict(schema=1, source='bl2_events', capture_id=c['id'], donor_session=c['session'],
                seq=c['seq'], active=c['active'], stop_reason=c['reason'], errors=c['errors'],
                last_id=c['buffer'].last_id, evicted=c['buffer'].evicted,
                events=list(c['buffer'].events))


def flush():
    c = _capture
    c['seq'] += 1
    text = json.dumps(packet(), allow_nan=False)
    parse_events(text)
    if len(text.encode('utf-8')) > MAX_EVENT_BYTES:
        raise ValueError('Event buffer exceeded bound')
    target = c['mailbox']/EVENT_FILE
    temp = target.with_suffix('.tmp')
    try:
        temp.write_text(text+'\n', encoding='utf-8')
        temp.replace(target)
        if c['hit_diagnostics']:
            diagnostics = json.dumps(c['hit_diagnostics'], allow_nan=False)
            if len(diagnostics.encode('utf-8')) <= MAX_EVENT_BYTES:
                (c['mailbox']/'blacklands_hit_api.json').write_text(diagnostics+'\n',encoding='utf-8')
    finally:
        temp.unlink(missing_ok=True)


def on_event(kind, obj, args, ret):
    c = _capture
    if c is None or not c['active'] or time.monotonic() >= c['deadline']:
        return
    try:
        pc = get_pc(possibly_loading=True)
        if pc is None or pc.Pawn is None:
            return
        if kind == 'take_damage':
            if args.InstigatedBy != pc:
                return
            if len(c['hit_diagnostics']) < 4:
                c['hit_diagnostics'].append(dict(target=path(obj), arguments=describe(args)))
            causer = getattr(args, 'DamageCauser', None)
            causer_path = path(causer)
            match = c['projectiles'].get(causer_path)
            exact = match is not None and match['weak']() == causer
            direct_weapon = causer is not None and str(causer.Class.Name) == 'WillowWeapon'
            weapon = match['weapon'] if exact else causer_path if direct_weapon else None
            frame = c['stack'][-1] if c['stack'] else None
            synchronous = direct_weapon and frame is not None and frame['weapon'] == causer_path
            data = dict(target=path(obj), causer=causer_path,
                        damage=number(args.Damage),
                        shot_id=match['shot_id'] if exact else frame['shot_id'] if synchronous else None,
                        attribution='spawned_projectile_reference' if exact else 'synchronous_weapon_call' if synchronous
                        else 'native_weapon_causer' if direct_weapon else 'unresolved')
            impact = c['impacts'][-1] if c['impacts'] else None
            # Scope plus both native object references, never timing/proximity.
            impact_match = (impact is not None and impact['weapon_ref']() == causer
                            and impact['target_ref']() == obj)
            data['impact_id'] = impact['impact_id'] if impact_match else None
        elif kind == 'display_damage':
            if args.PC != pc:
                return
            damage = args.DamageEventData
            # Damage display is not proven to belong to a particular shot/weapon.
            weapon = None
            data = dict(damage=number(damage.TotalDamageForDamageType),
                        target=path(damage.DamagedActor), damage_type=path(obj))
        else:
            if obj not in (pc.Pawn.Weapon, getattr(pc.Pawn, 'OffHandWeapon', None)):
                return
            weapon = path(obj)
            data = dict(reload_count=number(obj.ReloadCnt), reserve=number(obj.AmmoNotInClip))
            if kind in ('consume_ammo', 'reload_begin'):
                data['fire_mode'] = number(args.FireModeNum)
            elif kind == 'fire_mode':
                data['definition'] = path(args.FiringModeDefinition)
            elif kind == 'projectile':
                data['definition'] = path(args.FireModeDef)
                data['projectile'] = path(ret)
            elif kind == 'projectile_spawn':
                projectile = args.InProjectile
                data['projectile'] = path(projectile)
                frame = c['stack'][-1] if c['stack'] else None
                data['shot_id'] = frame['shot_id'] if frame and frame['weapon'] == weapon else None
                if projectile is not None and data['shot_id'] is not None:
                    if len(c['projectiles']) >= 256:
                        c['projectiles'].pop(next(iter(c['projectiles'])))
                    c['projectiles'][path(projectile)] = dict(weak=WeakPointer(projectile),
                                                             weapon=weapon, shot_id=data['shot_id'])
            if kind == 'fire_mode':
                frame = c['stack'].pop() if c['stack'] else None
                data['shot_id'] = frame['shot_id'] if frame and frame['weapon'] == weapon else None
        c['buffer'].append(kind, int((time.monotonic()-c['started'])*1000), weapon, data)
    except Exception as exc:
        c['errors'] += 1
        c['stack'].clear()
        c['impacts'].clear()
        if c['errors'] == 1:
            logging.warning(f'BlackLands event observation failed: {exc}')


def on_fire_begin(obj, args, _ret, _func):
    c = _capture
    if c is None or not c['active'] or time.monotonic() >= c['deadline']:
        return
    try:
        pc = get_pc(possibly_loading=True)
        if pc is None or pc.Pawn is None or obj not in (pc.Pawn.Weapon, getattr(pc.Pawn, 'OffHandWeapon', None)):
            return
        if len(c['stack']) >= 32:
            c['stack'].clear()
            c['errors'] += 1
            return
        c['shot_id'] += 1
        frame = dict(weapon=path(obj),shot_id=c['shot_id'])
        c['stack'].append(frame)
        c['buffer'].append('fire_begin',int((time.monotonic()-c['started'])*1000),frame['weapon'],
                           dict(shot_id=frame['shot_id'],definition=path(args.FiringModeDefinition)))
    except Exception as exc:
        c['errors'] += 1
        c['stack'].clear()
        logging.warning(f'BlackLands firing context failed: {exc}')


def on_impact(obj, args, _ret, _func, *, begin):
    c = _capture
    if c is None or not c['active'] or time.monotonic() >= c['deadline']:
        return
    try:
        if not begin:
            if c['impacts'] and c['impacts'][-1]['weapon_ref']() == obj:
                frame = c['impacts'].pop()
                c['buffer'].append('impact_end', int((time.monotonic()-c['started'])*1000),
                                   frame['weapon'], dict(impact_id=frame['impact_id']))
            return
        pc = get_pc(possibly_loading=True)
        if pc is None or pc.Pawn is None:
            return
        # Retain observations from a previously equipped weapon owned by the local pawn.
        if obj not in (pc.Pawn.Weapon, getattr(pc.Pawn, 'OffHandWeapon', None)) and getattr(obj, 'Instigator', None) != pc.Pawn:
            return
        if len(c['impacts']) >= 32:
            raise ValueError('Impact context depth exceeded')
        target = args.Impact.HitActor
        c['impact_id'] += 1
        frame = dict(impact_id=c['impact_id'], weapon=path(obj),
                     weapon_ref=WeakPointer(obj), target_ref=WeakPointer(target) if target is not None else lambda: None)
        c['impacts'].append(frame)
        data = dict(impact_id=frame['impact_id'], target=path(target),
                    damage=number(args.BulletDamage), definition=path(args.FiringModeDefinition))
        c['buffer'].append('impact_begin', int((time.monotonic()-c['started'])*1000), frame['weapon'], data)
    except Exception as exc:
        c['errors'] += 1
        c['impacts'].clear()
        logging.warning(f'BlackLands impact observation failed: {exc}')


def on_tick(*_args):
    c = _capture
    if c is None or not c['active']:
        return
    # A blocked/aborted firing call cannot leave context active on later ticks.
    c['stack'].clear()
    c['impacts'].clear()
    import blacklands_passthrough as adapter
    if adapter._mailbox is None or adapter._session != c['session']:
        stop('adapter_disabled_or_restarted')
        return
    now = time.monotonic()
    if now >= c['deadline']:
        stop('duration_complete')
    elif now >= c['next_flush']:
        c['next_flush'] = now+0.25
        try:
            flush()
        except Exception as exc:
            c['errors'] += 1
            if c['errors'] == 1:
                logging.warning(f'BlackLands event output failed: {exc}')


def remove_hooks():
    for function, kind in (*_specs, (_tick, 'tick')):
        hooks.remove_hook(function, hooks.Type.POST, _prefix+kind)
    hooks.remove_hook('WillowGame.WillowWeapon:FiringModeDefinitionFire', hooks.Type.PRE, _prefix+'fire_begin')
    hooks.remove_hook(_impact, hooks.Type.PRE, _prefix+'impact_begin')
    hooks.remove_hook(_impact, hooks.Type.POST, _prefix+'impact_end')


def stop(reason='manual_stop'):
    if _capture is None:
        return
    _capture['active'], _capture['reason'] = False, reason
    remove_hooks()
    try:
        flush()
    except Exception as exc:
        logging.warning(f'BlackLands final event output failed: {exc}')


def start(seconds=180):
    global _capture
    if not 0 < seconds <= 180:
        raise ValueError('Capture must last at most 180 seconds')
    import blacklands_passthrough as adapter
    if adapter._mailbox is None or not adapter._session:
        raise RuntimeError('Enable the main BlackLands probe first.')
    if _capture is not None:
        stop('restarted')
    remove_hooks()
    now = time.monotonic()
    _capture = dict(id=uuid.uuid4().hex, session=adapter._session, mailbox=adapter._mailbox,
                    seq=0, active=True, reason=None, errors=0, buffer=EventBuffer(),
                    started=now, deadline=now+seconds, next_flush=now,
                    shot_id=0, stack=[], projectiles={}, hit_diagnostics=[], impact_id=0, impacts=[])
    try:
        pc = get_pc(possibly_loading=True)
        if pc is not None and pc.Pawn is not None and pc.Pawn.Weapon is not None:
            try:
                schema = json.dumps(function_schema(pc.Pawn.Weapon),allow_nan=False)
                if len(schema.encode('utf-8')) <= MAX_EVENT_BYTES:
                    (_capture['mailbox']/'blacklands_trace_api.json').write_text(schema+'\n',encoding='utf-8')
                schema = json.dumps(bullet_schemas(), allow_nan=False)
                if len(schema.encode('utf-8')) <= MAX_EVENT_BYTES:
                    (_capture['mailbox']/'blacklands_bullet_api.json').write_text(schema+'\n', encoding='utf-8')
            except Exception as exc:
                logging.warning(f'BlackLands optional trace schema unavailable: {exc}')
        if not hooks.add_hook('WillowGame.WillowWeapon:FiringModeDefinitionFire', hooks.Type.PRE,
                              _prefix+'fire_begin', on_fire_begin):
            raise RuntimeError('Firing context hook registration failed')
        for function, kind in _specs:
            def observe(obj, args, ret, _func, kind=kind):
                on_event(kind, obj, args, ret)
            if not hooks.add_hook(function, hooks.Type.POST, _prefix+kind, observe):
                raise RuntimeError(f'Hook registration failed: {kind}')
        if not hooks.add_hook(_tick, hooks.Type.POST, _prefix+'tick', on_tick):
            raise RuntimeError('Event tick registration failed')
        for hook_type, kind, begin in ((hooks.Type.PRE, 'impact_begin', True), (hooks.Type.POST, 'impact_end', False)):
            def observe_impact(obj, args, ret, func, begin=begin):
                on_impact(obj, args, ret, func, begin=begin)
            if not hooks.add_hook(_impact, hook_type, _prefix+kind, observe_impact):
                raise RuntimeError(f'Impact hook registration failed: {kind}')
        flush()
    except Exception:
        _capture['active'] = False
        remove_hooks()
        raise
    logging.info(f'BlackLands: read-only event capture started for {seconds} seconds.')
