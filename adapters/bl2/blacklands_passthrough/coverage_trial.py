"""Finite, reversible AO coverage test with first-person arms/gun in SDPG_Foreground.

Live evidence (2026-10-04): with arms/gun in Foreground, the AO key tinted the world
and left the gun clean, but only on occluded areas and outlines. This trial keeps
the groups moved and steps through stronger AO profiles. One profile also asks the
native LocalPlayer to rebuild its post-process chain (TouchPlayerPostProcessChain),
in case bAffectsLightingOnly is only read when render proxies are created. Restore:
AO originals, one more chain refresh if any refresh happened, then component groups.
"""
import json
import time
from mods_base import get_pc
from unrealsdk import hooks, logging
from unrealsdk.unreal import WeakPointer
from blacklands_passthrough import ao_key_trial as ao
from blacklands_passthrough import foreground_trial as fg

HOOKS = ('Engine.PlayerController:PlayerTick', 'WillowGame.WillowGameViewportClient:PostRender')
IDENTIFIER = 'blacklands.render.coverage_trial'
FIELDS = ao.FLOATS + ('OcclusionRadius',)
BASE = dict(ao.COMMON, **ao.PROFILES[0])
PROFILES = (
    dict(name='baseline', values={}, touch=False),
    dict(name='refresh_chain', values={}, touch=True),
    dict(name='low_power', values=dict(OcclusionPower=0.01), touch=True),
    dict(name='wide_radius', values=dict(OcclusionPower=0.01, OcclusionRadius=5000.0,
                                         OcclusionScale=100.0), touch=True),
)
_state = None


def report():
    if _state is None:
        return {'active': False}
    return {k:v for k,v in _state.items()
            if k not in ('effect_ref', 'player_ref', 'parts', 'mailbox', 'registered')}


def publish():
    target = _state['mailbox']/'blacklands_coverage_trial.json'
    temp = target.with_suffix('.tmp')
    temp.write_text(json.dumps(report(), allow_nan=False)+'\n', encoding='utf-8')
    temp.replace(target)


def transition(phase, **extra):
    _state['phase'] = phase
    _state['history'].append(dict(phase=phase, elapsed=time.monotonic()-_state['started'],
                                  wall=time.time(), **extra))


def capture(effect):
    values = ao.capture(effect)
    values['OcclusionRadius'] = effect.OcclusionRadius
    return values


def touch(state):
    player = state['player_ref']()
    if player is None:
        raise RuntimeError('LocalPlayer unavailable for chain refresh')
    player.TouchPlayerPostProcessChain()
    state['touched'] += 1


def apply_profile(state, effect, index):
    profile = PROFILES[index]
    values = dict(BASE, **profile['values'])
    values['OcclusionColor'] = list(state['key']) + [1.0]
    state['ao_restore_needed'] = True  # a setter could mutate and then throw
    ao.write(effect, values)
    if not ao.matches(capture(effect), values):
        raise RuntimeError('AO coverage profile failed readback')
    if profile['touch']:
        touch(state)
    state['profile'] = index
    state['next_at'] = time.monotonic() + state['step']
    transition('profile', index=index, name=profile['name'], values=values)
    publish()


def stop(reason='manual_stop'):
    state = _state
    if state is None or not state['active']:
        return
    # AO values, chain refresh, then depth groups; any failure keeps hooks to retry.
    effect = state['effect_ref']()
    if state['ao_restore_needed'] and effect is not None:
        if effect._path_name() != state['effect_path']:
            raise RuntimeError('AO effect identity changed; refusing to write another object')
        ao.write(effect, state['ao_original'])
        if not ao.matches(capture(effect), state['ao_original']):
            raise RuntimeError('AO restoration did not read back correctly')
    state['ao_restore_needed'] = False
    if state['touched'] and not state['refreshed_after_restore']:
        touch(state)
        state['refreshed_after_restore'] = True
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
    logging.info(f'BlackLands coverage trial ended: {reason}; restored={state["restored"]}.')


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
        effect = state['effect_ref']()
        if effect is None:
            stop('effect_destroyed'); return
        if state['phase'] == 'armed' and now >= state['next_at']:
            if not ao.matches(capture(effect), state['ao_original']):
                stop('effect_changed_before_test'); return
            fg.to_foreground(state)
            apply_profile(state, effect, 0)
        elif state['phase'] == 'profile' and now >= state['next_at']:
            if state['profile'] + 1 < len(PROFILES):
                apply_profile(state, effect, state['profile'] + 1)
            else:
                stop('duration_complete')
    except Exception as exc:
        state['error'] = str(exc)
        logging.warning(f'BlackLands coverage trial: {exc}')
        try:
            stop('error')
        except Exception as restore_exc:
            logging.warning(f'BlackLands coverage restore pending: {restore_exc}')


def start(step=3, key=ao.DEFAULT_KEY):
    global _state
    if not isinstance(step, (int, float)) or not 1 <= step <= 3:
        raise ValueError('Profile step must be 1..3 seconds (4 profiles, <=12s total)')
    if len(key) != 3 or not all(isinstance(c, (int, float)) and 0 <= c <= 1 for c in key):
        raise ValueError('Key colour must be three components in 0..1')
    stop('restarted')
    import blacklands_passthrough as adapter
    pc = get_pc(possibly_loading=True)
    if adapter._mailbox is None or not adapter._session or pc is None or pc.Pawn is None:
        raise RuntimeError('Enable the main probe and load a character first')
    world, foreground = fg.groups()
    effect = ao.find_effect(pc.Player, world)
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
                  world=world, foreground=foreground, key=[float(c) for c in key], step=float(step),
                  profile=None, ao_original=capture(effect), ao_restore_needed=False,
                  effect_path=effect._path_name(), effect_ref=WeakPointer(effect),
                  player_ref=WeakPointer(pc.Player), touched=0, refreshed_after_restore=False,
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
    logging.info(f'BlackLands: coverage trial starts in 3s, gun/arms foreground, '
                 f'{len(PROFILES)} AO profiles x {step}s, then full restore.')
