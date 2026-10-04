"""Finite, reversible test of one reflected viewport flag; no gameplay mutation."""
import json
import time
from mods_base import get_pc
from unrealsdk import hooks, logging
from unrealsdk.unreal import WeakPointer

HOOKS = ('Engine.PlayerController:PlayerTick', 'WillowGame.WillowGameViewportClient:PostRender')
IDENTIFIER = 'blacklands.render.world_trial'
_state = None


def report():
    if _state is None:
        return {'active': False}
    return {k:v for k,v in _state.items() if k not in ('ref', 'mailbox', 'registered')}


def publish():
    target = _state['mailbox']/'blacklands_render_trial.json'
    temp = target.with_suffix('.tmp')
    temp.write_text(json.dumps(report(), allow_nan=False)+'\n', encoding='utf-8')
    temp.replace(target)


def transition(phase):
    _state['phase'] = phase
    _state['history'].append(dict(phase=phase, elapsed=time.monotonic()-_state['started']))


def stop(reason='manual_stop'):
    state = _state
    if state is None or not state['active']:
        return
    # Restore before removing either hook. A failed setter leaves hooks available
    # to retry restoration on a subsequent render/tick or explicit stop().
    obj = state['ref']()
    if state['restore_needed'] and obj is not None:
        if obj._path_name() != state['object_path']:
            raise RuntimeError('Viewport identity changed; refusing to write another object')
        obj.bDisableWorldRendering = state['original']
        if obj.bDisableWorldRendering != state['original']:
            raise RuntimeError('Viewport restoration did not read back correctly')
        state['restored'] = True
    elif state['restore_needed']:
        state['object_destroyed'] = True
    state['restore_needed'] = False
    state['active'] = False
    state['reason'] = reason
    transition('finished')
    for function in state['registered']:
        hooks.remove_hook(function, hooks.Type.POST, IDENTIFIER)
    state['registered'].clear()
    publish()
    logging.info(f'BlackLands render trial ended: {reason}; restored={state["restored"]}.')


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
        obj = state['ref']()
        if obj is None or pc.Player.ViewportClient != obj:
            stop('viewport_changed'); return
        if state['phase'] == 'armed' and now >= state['apply_at']:
            if obj.bDisableWorldRendering != state['original']:
                stop('flag_changed_before_test'); return
            state['restore_needed'] = True  # setter could mutate then throw
            obj.bDisableWorldRendering = True
            if obj.bDisableWorldRendering is not True:
                raise RuntimeError('World flag failed readback')
            state['restore_at'] = now + state['duration']
            transition('world_disabled')
            publish()
        elif state['phase'] == 'world_disabled' and now >= state['restore_at']:
            stop('duration_complete')
    except Exception as exc:
        state['error'] = str(exc)
        logging.warning(f'BlackLands render trial: {exc}')
        try:
            stop('error')
        except Exception as restore_exc:
            logging.warning(f'BlackLands restore pending: {restore_exc}')


def start(seconds=12):
    global _state
    if not 1 <= seconds <= 15:
        raise ValueError('World-render test duration must be 1..15 seconds')
    stop('restarted')
    import blacklands_passthrough as adapter
    pc = get_pc(possibly_loading=True)
    if adapter._mailbox is None or not adapter._session or pc is None or pc.Pawn is None:
        raise RuntimeError('Enable the main probe and load a character first')
    viewport = pc.Player.ViewportClient
    original = viewport.bDisableWorldRendering
    if original is not False:
        raise RuntimeError('World rendering is already disabled; leaving it unchanged')
    now = time.monotonic()
    _state = dict(schema=1, active=True, phase='armed', reason=None, error=None,
                  original=original, restored=False, restore_needed=False, object_destroyed=False,
                  object_path=viewport._path_name(), ref=WeakPointer(viewport),
                  donor_session=adapter._session, mailbox=adapter._mailbox,
                  started=now, apply_at=now+3, restore_at=None, duration=seconds,
                  registered=[], history=[])
    try:
        for function in HOOKS:
            if not hooks.add_hook(function, hooks.Type.POST, IDENTIFIER, on_frame):
                raise RuntimeError(f'Could not register restoration hook: {function}')
            _state['registered'].append(function)
        transition('armed')
        publish()
    except Exception:
        stop('registration_error')
        raise
    logging.info('BlackLands: render-only trial starts in 3s, restores after 12s; no HUD flags changed.')
