"""Finite, reversible test: gun/arms in SDPG_Foreground plus viewport world-disable flag.

Live evidence (2026-10-04): bDisableWorldRendering alone hid the world AND the gun
(both were in SDPG_World). foreground_trial proved arms/gun can be moved to
SDPG_Foreground and restored. This trial asks whether the foreground group still
draws while the world-disable flag is set. Order: move groups, hold, set the flag,
hold, restore the flag first, then the groups. Presentation only.
"""
import json
import time
from mods_base import get_pc
from unrealsdk import hooks, logging
from unrealsdk.unreal import WeakPointer
from blacklands_passthrough import foreground_trial as fg

HOOKS = ('Engine.PlayerController:PlayerTick', 'WillowGame.WillowGameViewportClient:PostRender')
IDENTIFIER = 'blacklands.render.blackout_trial'
_state = None


def report():
    if _state is None:
        return {'active': False}
    return {k:v for k,v in _state.items() if k not in ('viewport_ref', 'parts', 'mailbox', 'registered')}


def publish():
    target = _state['mailbox']/'blacklands_blackout_trial.json'
    temp = target.with_suffix('.tmp')
    temp.write_text(json.dumps(report(), allow_nan=False)+'\n', encoding='utf-8')
    temp.replace(target)


def transition(phase):
    _state['phase'] = phase
    _state['history'].append(dict(phase=phase, elapsed=time.monotonic()-_state['started'], wall=time.time()))


def stop(reason='manual_stop'):
    state = _state
    if state is None or not state['active']:
        return
    # Viewport flag first, then groups; any failure keeps hooks so the next frame retries.
    viewport = state['viewport_ref']()
    if state['flag_restore_needed'] and viewport is not None:
        if viewport._path_name() != state['viewport_path']:
            raise RuntimeError('Viewport identity changed; refusing to write another object')
        viewport.bDisableWorldRendering = state['flag_original']
        if viewport.bDisableWorldRendering != state['flag_original']:
            raise RuntimeError('Viewport restoration did not read back correctly')
    state['flag_restore_needed'] = False
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
    logging.info(f'BlackLands blackout trial ended: {reason}; restored={state["restored"]}.')


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
        viewport = state['viewport_ref']()
        if viewport is None or pc.Player.ViewportClient != viewport:
            stop('viewport_changed'); return
        if state['phase'] == 'armed' and now >= state['next_at']:
            if viewport.bDisableWorldRendering != state['flag_original']:
                stop('flag_changed_before_test'); return
            fg.to_foreground(state)
            state['next_at'] = now + state['hold']
            transition('foreground'); publish()
        elif state['phase'] == 'foreground' and now >= state['next_at']:
            state['flag_restore_needed'] = True  # setter could mutate then throw
            viewport.bDisableWorldRendering = True
            if viewport.bDisableWorldRendering is not True:
                raise RuntimeError('World flag failed readback')
            state['next_at'] = now + state['blackout']
            transition('foreground_world_disabled'); publish()
        elif state['phase'] == 'foreground_world_disabled' and now >= state['next_at']:
            stop('duration_complete')
    except Exception as exc:
        state['error'] = str(exc)
        logging.warning(f'BlackLands blackout trial: {exc}')
        try:
            stop('error')
        except Exception as restore_exc:
            logging.warning(f'BlackLands blackout restore pending: {restore_exc}')


def start(hold=2, blackout=6):
    global _state
    if not all(isinstance(v, (int, float)) for v in (hold, blackout)) or not (1 <= hold <= 5 and 1 <= blackout <= 10):
        raise ValueError('hold must be 1..5s and blackout 1..10s')
    stop('restarted')
    import blacklands_passthrough as adapter
    pc = get_pc(possibly_loading=True)
    if adapter._mailbox is None or not adapter._session or pc is None or pc.Pawn is None:
        raise RuntimeError('Enable the main probe and load a character first')
    viewport = pc.Player.ViewportClient
    if viewport.bDisableWorldRendering is not False:
        raise RuntimeError('World rendering is already disabled; leaving it unchanged')
    world, foreground = fg.groups()
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
    now = time.monotonic()
    _state = dict(schema=1, active=True, phase='armed', reason=None, error=None,
                  world=world, foreground=foreground, hold=float(hold), blackout=float(blackout),
                  flag_original=False, flag_restore_needed=False,
                  viewport_path=viewport._path_name(), viewport_ref=WeakPointer(viewport),
                  parts=parts, components=None, restored=False,
                  donor_session=adapter._session, mailbox=adapter._mailbox,
                  started=now, next_at=now+3, registered=[], history=[])
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
    logging.info(f'BlackLands: blackout trial starts in 3s: gun/arms foreground {hold}s, '
                 f'then world disabled {blackout}s, then full restore.')
