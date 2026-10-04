"""Finite, reversible world-key test that retunes BL2's own world-group AO effect.

Live evidence (2026-10-04): BL2's active chain already holds an AmbientOcclusionEffect
at SceneDPG=SDPG_World, while an inserted extra chain was neither merged into the
active chain nor kept at SDPG_World. This trial therefore edits only fields of that
existing effect, steps through a few parameter profiles (the AO shader's exact
formula in BL2 is unknown), and restores every captured original value.
Presentation only: no chains are added/removed and no viewport/HUD flags change.
"""
import json
import math
import time
from mods_base import get_pc
from unrealsdk import find_enum, hooks, logging, make_struct
from unrealsdk.unreal import WeakPointer

HOOKS = ('Engine.PlayerController:PlayerTick', 'WillowGame.WillowGameViewportClient:PostRender')
IDENTIFIER = 'blacklands.render.ao_key_trial'
EFFECT_CLASS = 'Engine.AmbientOcclusionEffect'
DPG_ENUMS = ('ESceneDepthPriorityGroup', 'Engine.Scene.ESceneDepthPriorityGroup')
FLOATS = ('OcclusionPower', 'OcclusionScale', 'OcclusionBias', 'MinOcclusion',
          'OcclusionFadeoutMinDistance', 'OcclusionFadeoutMaxDistance')
FIELDS = FLOATS + ('bAffectsLightingOnly', 'OcclusionColor')
FAR = 1.0e9
# Both bias signs and both MinOcclusion extremes, because the shader convention
# (occlusion vs visibility) has not been observed for this build.
PROFILES = (
    dict(OcclusionBias=1.0, MinOcclusion=0.0),
    dict(OcclusionBias=1.0, MinOcclusion=1.0),
    dict(OcclusionBias=-1.0, MinOcclusion=0.0),
    dict(OcclusionBias=-1.0, MinOcclusion=1.0),
)
COMMON = dict(OcclusionPower=1.0, OcclusionScale=0.0, OcclusionFadeoutMinDistance=FAR,
              OcclusionFadeoutMaxDistance=FAR, bAffectsLightingOnly=False)
DEFAULT_KEY = (1.0, 0.0, 1.0)
_state = None


def report():
    if _state is None:
        return {'active': False}
    return {k:v for k,v in _state.items() if k not in ('ref', 'mailbox', 'registered')}


def publish():
    target = _state['mailbox']/'blacklands_ao_key_trial.json'
    temp = target.with_suffix('.tmp')
    temp.write_text(json.dumps(report(), allow_nan=False)+'\n', encoding='utf-8')
    temp.replace(target)


def transition(phase, **extra):
    _state['phase'] = phase
    _state['history'].append(dict(phase=phase, elapsed=time.monotonic()-_state['started'],
                                  wall=time.time(), **extra))


def world_dpg():
    for name in DPG_ENUMS:
        try:
            members = find_enum(name).__members__
        except Exception:
            continue
        world, foreground = members.get('SDPG_World'), members.get('SDPG_Foreground')
        if world is not None and foreground is not None and int(world) < int(foreground):
            return int(world)
    raise RuntimeError('SDPG_World/SDPG_Foreground enum not found; refusing to guess its value')


def find_effect(player, dpg):
    """The single AO effect in the active chain that runs in the world group."""
    chain = player.PlayerPostProcess
    if chain is None:
        raise RuntimeError('No active player post-process chain')
    found = [e for e in chain.Effects if e is not None and e.Class._path_name() == EFFECT_CLASS
             and int(e.SceneDPG) == dpg and e.bShowInGame]
    if len(found) != 1:
        raise RuntimeError(f'Expected one world-group AO effect, found {len(found)}')
    return found[0]


def capture(effect):
    color = effect.OcclusionColor
    values = {name: getattr(effect, name) for name in FLOATS}
    values['bAffectsLightingOnly'] = bool(effect.bAffectsLightingOnly)
    values['OcclusionColor'] = [color.R, color.G, color.B, color.A]
    return values


def color(values):
    return make_struct('LinearColor', R=float(values[0]), G=float(values[1]),
                       B=float(values[2]), A=float(values[3]))


def write(effect, values):
    for name, value in values.items():
        setattr(effect, name, color(value) if name == 'OcclusionColor' else value)


def matches(actual, expected):
    for name, value in expected.items():
        got = actual[name]
        if isinstance(value, list):
            if any(abs(a-b) > 1e-4 for a, b in zip(got, value)): return False
        elif isinstance(value, bool):
            if got is not value: return False
        elif abs(got-value) > max(1e-4, abs(value)*1e-6):
            return False
    return True


def apply_profile(effect, index):
    values = dict(COMMON, **PROFILES[index])
    values['OcclusionColor'] = list(_state['key']) + [1.0]
    _state['restore_needed'] = True  # a setter could mutate and then throw
    write(effect, values)
    if not matches(capture(effect), values):
        raise RuntimeError('AO profile failed readback')
    _state['profile'] = index
    _state['profile_until'] = time.monotonic() + _state['step']
    transition('profile', index=index, values=values)
    publish()


def stop(reason='manual_stop'):
    state = _state
    if state is None or not state['active']:
        return
    # Restore before removing either hook. A failed restore keeps hooks to retry.
    effect = state['ref']()
    if state['restore_needed'] and effect is not None:
        if effect._path_name() != state['effect_path']:
            raise RuntimeError('AO effect identity changed; refusing to write another object')
        write(effect, state['original'])
        if not matches(capture(effect), state['original']):
            raise RuntimeError('AO restoration did not read back correctly')
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
    logging.info(f'BlackLands AO key trial ended: {reason}; restored={state["restored"]}.')


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
        effect = state['ref']()
        if effect is None:
            stop('effect_destroyed'); return
        if state['phase'] == 'armed' and now >= state['apply_at']:
            if not matches(capture(effect), state['original']):
                stop('effect_changed_before_test'); return
            apply_profile(effect, 0)
        elif state['phase'] == 'profile' and now >= state['profile_until']:
            if state['profile'] + 1 < len(PROFILES):
                apply_profile(effect, state['profile'] + 1)
            else:
                stop('duration_complete')
    except Exception as exc:
        state['error'] = str(exc)
        logging.warning(f'BlackLands AO key trial: {exc}')
        try:
            stop('error')
        except Exception as restore_exc:
            logging.warning(f'BlackLands AO restore pending: {restore_exc}')


def start(step=3, key=DEFAULT_KEY):
    global _state
    if not isinstance(step, (int, float)) or not 1 <= step <= 3:
        raise ValueError('Profile step must be 1..3 seconds (4 profiles, <=12s total)')
    if len(key) != 3 or not all(isinstance(c, (int, float)) and math.isfinite(c) and 0 <= c <= 1 for c in key):
        raise ValueError('Key colour must be three finite components in 0..1')
    stop('restarted')
    import blacklands_passthrough as adapter
    pc = get_pc(possibly_loading=True)
    if adapter._mailbox is None or not adapter._session or pc is None or pc.Pawn is None:
        raise RuntimeError('Enable the main probe and load a character first')
    effect = find_effect(pc.Player, world_dpg())
    now = time.monotonic()
    _state = dict(schema=1, active=True, phase='armed', reason=None, error=None,
                  key=[float(c) for c in key], step=float(step), profile=None, profile_until=None,
                  original=capture(effect), restored=False, restore_needed=False,
                  object_destroyed=False, effect_path=effect._path_name(), ref=WeakPointer(effect),
                  donor_session=adapter._session, mailbox=adapter._mailbox,
                  started=now, apply_at=now+3, registered=[], history=[])
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
    logging.info(f'BlackLands: AO key trial starts in 3s, {len(PROFILES)} profiles x {step}s, '
                 'then restores the original AO values.')
