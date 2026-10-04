"""Explicit, finite presentation mode: hold arms/gun in SDPG_Foreground plus a key fog.

This is fog_trial's verified combination (live 2026-10-04: ~99.7% of the world keyed,
gun and HUD clean) held for up to 180 seconds so an external receiver can key BL2's
gun+HUD over the BO2 capture. It publishes a heartbeat with an advancing sequence so
the receiver only composites while the mode is genuinely active. Restore order and
retry behavior match fog_trial: fog originals + ForceUpdate first, then groups.
Presentation only: no items, saves, viewport/HUD flags or game files change.
"""
import json
import time
from mods_base import get_pc
from unrealsdk import hooks, logging
from unrealsdk.unreal import WeakPointer
from blacklands_passthrough import fog_trial as fog
from blacklands_passthrough import foreground_trial as fg

HOOKS = ('Engine.PlayerController:PlayerTick', 'WillowGame.WillowGameViewportClient:PostRender')
IDENTIFIER = 'blacklands.render.isolation_mode'
VALUES = dict(fog.COMMON, Density=1.0)
PUBLISH_INTERVAL = 0.25
MAX_PARTS = 16
_state = None


def report():
    if _state is None:
        return {'active': False}
    return {k:v for k,v in _state.items() if k not in ('fog_ref', 'parts', 'mailbox', 'registered')}


def publish():
    _state['seq'] += 1
    _state['published_wall'] = time.time()
    target = _state['mailbox']/'blacklands_isolation.json'
    temp = target.with_suffix('.tmp')
    try:
        temp.write_text(json.dumps(report(), allow_nan=False)+'\n', encoding='utf-8')
        temp.replace(target)
    except OSError as exc:
        # A reader may briefly hold the file (WinError 5/32/33); skip, never sleep here.
        if getattr(exc, 'winerror', None) not in (5, 32, 33):
            raise
        _state['write_skips'] += 1


def transition(phase):
    _state['phase'] = phase
    _state['history'].append(dict(phase=phase, elapsed=time.monotonic()-_state['started'], wall=time.time()))


def stop(reason='manual_stop'):
    state = _state
    if state is None or not state['active']:
        return
    target = state['fog_ref']()
    if state['fog_restore_needed'] and target is not None:
        if target._path_name() != state['fog_path']:
            raise RuntimeError('Fog identity changed; refusing to write another object')
        fog.write(target, state['fog_original'])
        if not fog.matches(fog.capture(target), state['fog_original']):
            raise RuntimeError('Fog restoration did not read back correctly')
        fog.push(state, target)
    state['fog_restore_needed'] = False
    fg.restore_parts(state)
    state['components'] = [{k:v for k,v in p.items() if k != 'ref'} for p in state['parts']]
    state['restored'] = True
    state['active'] = False
    state['reason'] = reason
    transition('finished')
    for function in state['registered']:
        hooks.remove_hook(function, hooks.Type.POST, IDENTIFIER)
    state['registered'].clear()
    publish()
    logging.info(f'BlackLands isolation mode ended: {reason}; restored={state["restored"]}.')


def engage(state, target):
    fg.to_foreground(state)
    state['fog_original'] = fog.capture(target)
    state['fog_restore_needed'] = True  # a setter could mutate and then throw
    fog.write(target, state['values'])
    if not fog.matches(fog.capture(target), state['values']):
        raise RuntimeError('Isolation fog failed readback')
    fog.push(state, target)


def follow_weapon(state, pawn):
    """Move a newly equipped first-person weapon mesh to Foreground and track it."""
    weapon = pawn.Weapon
    component = weapon.FirstPersonMesh if weapon is not None else None
    if component is None:
        return
    path = component._path_name()
    if any(part['path'] == path for part in state['parts']):
        return
    if len(state['parts']) >= MAX_PARTS:
        raise RuntimeError('Too many weapon switches tracked; stopping to restore')
    original = int(component.DepthPriorityGroup)
    part = dict(name='weapon', path=path, original=original, ref=WeakPointer(component),
                changed=False, destroyed=False)
    state['parts'].append(part)
    if original == state['world']:
        part['changed'] = True  # native setter could apply and then throw
        fg.set_group(component, state['foreground'])
    state['weapon_switches'] += 1


def on_frame(*_args):
    state = _state
    if state is None or not state['active']:
        return
    try:
        import blacklands_passthrough as adapter
        now = time.monotonic()
        if state['error'] is not None:
            stop('error'); return
        if adapter._session != state['donor_session'] or adapter._mailbox is None:
            stop('adapter_changed'); return
        pc = get_pc(possibly_loading=True)
        if pc is None or pc.Pawn is None:
            stop('player_unavailable'); return
        target = state['fog_ref']()
        if target is None:
            stop('fog_destroyed'); return
        if state['phase'] == 'armed':
            engage(state, target)
            transition('isolated'); publish()
            state['next_publish'] = now + PUBLISH_INTERVAL
            return
        if now >= state['deadline']:
            stop('duration_complete'); return
        follow_weapon(state, pc.Pawn)
        # BL2 rewrites this fog every frame; reassert only when it changed.
        if not fog.matches(fog.capture(target), state['values']):
            state['overwrites'] += 1
            fog.write(target, state['values'])
            fog.push(state, target)
        if now >= state['next_publish']:
            state['next_publish'] = now + PUBLISH_INTERVAL
            publish()
    except Exception as exc:
        state['error'] = str(exc)
        logging.warning(f'BlackLands isolation mode: {exc}')
        try:
            stop('error')
        except Exception as restore_exc:
            logging.warning(f'BlackLands isolation restore pending: {restore_exc}')


def start(seconds=120, key=fog.DEFAULT_KEY):
    global _state
    if not isinstance(seconds, (int, float)) or not 1 <= seconds <= 180:
        raise ValueError('Isolation mode duration must be 1..180 seconds')
    if len(key) != 3 or not all(isinstance(c, int) and 0 <= c <= 255 for c in key):
        raise ValueError('Key colour must be three integers in 0..255')
    stop('restarted')
    import blacklands_passthrough as adapter
    pc = get_pc(possibly_loading=True)
    if adapter._mailbox is None or not adapter._session or pc is None or pc.Pawn is None:
        raise RuntimeError('Enable the main probe and load a character first')
    world, foreground = fg.groups()
    target = fog.find_fog()
    pawn = pc.Pawn
    weapon = pawn.Weapon
    if weapon is None or weapon.FirstPersonMesh is None or pawn.Arms is None:
        raise RuntimeError('Equip a weapon with first-person arms visible first')
    parts = []
    for name, component in (('arms', pawn.Arms), ('weapon', weapon.FirstPersonMesh)):
        original = int(component.DepthPriorityGroup)
        if original != world:
            raise RuntimeError(f'{name} is not in the world group ({original}); leaving it unchanged')
        parts.append(dict(name=name, path=component._path_name(), original=original,
                          ref=WeakPointer(component), changed=False, destroyed=False))
    values = dict(VALUES, LightColor=list(key) + [255])
    now = time.monotonic()
    _state = dict(schema=1, active=True, phase='armed', reason=None, error=None, seq=0,
                  published_wall=None, write_skips=0, key=list(key), values=values,
                  world=world, foreground=foreground, fog_original=None, fog_restore_needed=False,
                  updates=0, overwrites=0, weapon_switches=0, fog_path=target._path_name(), fog_ref=WeakPointer(target),
                  parts=parts, components=None, restored=False,
                  donor_session=adapter._session, mailbox=adapter._mailbox,
                  started=now, deadline=now+seconds, duration=float(seconds), next_publish=0.,
                  registered=[], history=[])
    _state['components'] = [{k:v for k,v in p.items() if k != 'ref'} for p in parts]
    try:
        for function in HOOKS:
            hooks.remove_hook(function, hooks.Type.POST, IDENTIFIER)
            # Installed SDK b1852aa4 can append and still return False; trust has_hook.
            hooks.add_hook(function, hooks.Type.POST, IDENTIFIER, on_frame)
            if not hooks.has_hook(function, hooks.Type.POST, IDENTIFIER):
                raise RuntimeError(f'Could not register restoration hook: {function}')
            _state['registered'].append(function)
        transition('armed')
        publish()
    except Exception:
        stop('registration_error')
        raise
    logging.info(f'BlackLands: isolation mode on for {seconds}s (gun/arms foreground + key fog). '
                 'Stop early: py from blacklands_passthrough import isolation_mode; isolation_mode.stop()')
