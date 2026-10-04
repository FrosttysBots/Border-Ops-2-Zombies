"""Finite, reversible world-key test using one owned post-process chain; presentation only.

A single UberPostProcessEffect is assigned to the world depth-priority group so that,
if the native renderer honors SceneDPG, donor-world pixels are replaced by a flat key
colour before the foreground group (arms/weapon) and the Scaleform HUD are drawn.
Whether BL2 honors this is exactly what the live trial must show; nothing here proves it.
"""
import json
import math
import time
from mods_base import get_pc
from unrealsdk import construct_object, find_enum, hooks, logging, make_struct
from unrealsdk.unreal import WeakPointer

HOOKS = ('Engine.PlayerController:PlayerTick', 'WillowGame.WillowGameViewportClient:PostRender')
IDENTIFIER = 'blacklands.render.postprocess_trial'
CHAIN_NAME = 'BlackLandsWorldKeyChain'
EFFECT_NAME = 'BlackLandsWorldKey'
DPG_ENUMS = ('ESceneDepthPriorityGroup', 'Engine.Scene.ESceneDepthPriorityGroup')
# Uber shader inputs chosen to saturate every channel to 1, then tint by the key colour.
# These values are a hypothesis about BL2's uber shader, recorded with the readback.
EFFECT_FIELDS = ('SceneDPG', 'bShowInGame', 'bUseWorldSettings', 'SceneShadows',
                 'SceneHighLights', 'SceneMidTones', 'SceneDesaturation', 'SceneColorize')
DEFAULT_KEY = (1.0, 0.0, 1.0)
_state = None


def report():
    if _state is None:
        return {'active': False}
    return {k:v for k,v in _state.items() if k not in ('player_ref', 'chain_ref', 'mailbox', 'registered')}


def publish():
    target = _state['mailbox']/'blacklands_postprocess_trial.json'
    temp = target.with_suffix('.tmp')
    temp.write_text(json.dumps(report(), allow_nan=False)+'\n', encoding='utf-8')
    temp.replace(target)


def transition(phase):
    _state['phase'] = phase
    _state['history'].append(dict(phase=phase, elapsed=time.monotonic()-_state['started']))


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


def is_owned(chain):
    """Match only this module's fixed names. Live BL2 renamed the inserted chain
    (a clone despite bInClone=False), so the effect name is checked as well."""
    if chain is None:
        return False
    if str(chain.Name) == CHAIN_NAME:
        return True
    return any(effect is not None and EFFECT_NAME in (str(effect.Name), str(effect.EffectName))
               for effect in chain.Effects)


def owned_indices(player):
    """Indices of chains this module created."""
    return [i for i, chain in enumerate(player.PlayerPostProcessChains) if is_owned(chain)]


def remove_owned(player):
    """Remove only owned chains, highest index first; returns how many were removed."""
    removed = 0
    for index in reversed(owned_indices(player)):
        if not player.RemovePostProcessingChain(index):
            raise RuntimeError('Native chain removal reported failure')
        removed += 1
    if owned_indices(player):
        raise RuntimeError('Owned post-process chain still present after removal')
    return removed


def vector(values):
    return make_struct('Vector', X=float(values[0]), Y=float(values[1]), Z=float(values[2]))


def readback(effect):
    values = {}
    for name in EFFECT_FIELDS:
        item = getattr(effect, name)
        values[name] = [item.X, item.Y, item.Z] if hasattr(item, 'X') else (
            int(item) if name == 'SceneDPG' else item)
    return values


def apply(player):
    if owned_indices(player):
        raise RuntimeError('An owned chain is already installed; stop() before starting again')
    chain = construct_object('PostProcessChain', player, CHAIN_NAME)
    effect = construct_object('UberPostProcessEffect', chain, EFFECT_NAME)
    effect.EffectName = EFFECT_NAME
    effect.SceneDPG = _state['scene_dpg']
    effect.bShowInGame = True
    effect.bUseWorldSettings = False
    effect.SceneShadows = vector((-1.0, -1.0, -1.0))
    effect.SceneHighLights = vector((1.0, 1.0, 1.0))
    effect.SceneMidTones = vector((1.0, 1.0, 1.0))
    effect.SceneDesaturation = 0.0
    effect.SceneColorize = vector(_state['key'])
    chain.Effects = [effect]
    _state['effect_readback'] = readback(effect)
    _state['restore_needed'] = True  # native insertion could succeed and then raise
    if not player.InsertPostProcessingChain(chain, -1, False):
        raise RuntimeError('Native chain insertion reported failure')
    if len(owned_indices(player)) != 1:
        raise RuntimeError('Owned chain not found after insertion')
    _state['chain_ref'] = WeakPointer(chain)
    _state['chain_count_applied'] = len(player.PlayerPostProcessChains)


def stop(reason='manual_stop'):
    state = _state
    if state is None or not state['active']:
        return
    # Remove the owned chain before either hook. A failure keeps hooks to retry.
    player = state['player_ref']()
    if state['restore_needed'] and player is not None:
        if player._path_name() != state['player_path']:
            raise RuntimeError('LocalPlayer identity changed; refusing to edit another object')
        state['removed'] = remove_owned(player)
        state['chain_count_restored'] = len(player.PlayerPostProcessChains)
        state['restored'] = state['chain_count_restored'] == state['chain_count_original']
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
    logging.info(f'BlackLands post-process trial ended: {reason}; restored={state["restored"]}.')


def recover():
    """Remove owned chains/hooks even if this module's Python state was lost."""
    for function in HOOKS:
        hooks.remove_hook(function, hooks.Type.POST, IDENTIFIER)
    pc = get_pc(possibly_loading=True)
    if pc is None or pc.Player is None:
        return 0
    return remove_owned(pc.Player)


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
        player = state['player_ref']()
        if player is None or pc.Player != player:
            stop('player_changed'); return
        if state['phase'] == 'armed' and now >= state['apply_at']:
            if len(player.PlayerPostProcessChains) != state['chain_count_original']:
                stop('chains_changed_before_test'); return
            apply(player)
            state['restore_at'] = now + state['duration']
            transition('world_keyed')
            publish()
        elif state['phase'] == 'world_keyed' and now >= state['restore_at']:
            stop('duration_complete')
    except Exception as exc:
        state['error'] = str(exc)
        logging.warning(f'BlackLands post-process trial: {exc}')
        try:
            stop('error')
        except Exception as restore_exc:
            logging.warning(f'BlackLands chain removal pending: {restore_exc}')


def start(seconds=12, key=DEFAULT_KEY):
    global _state
    if not 1 <= seconds <= 15:
        raise ValueError('Post-process test duration must be 1..15 seconds')
    if len(key) != 3 or not all(isinstance(c, (int, float)) and math.isfinite(c) and 0 <= c <= 1 for c in key):
        raise ValueError('Key colour must be three finite components in 0..1')
    stop('restarted')
    import blacklands_passthrough as adapter
    pc = get_pc(possibly_loading=True)
    if adapter._mailbox is None or not adapter._session or pc is None or pc.Pawn is None:
        raise RuntimeError('Enable the main probe and load a character first')
    player = pc.Player
    if owned_indices(player):
        raise RuntimeError('An owned chain is already installed; run postprocess_trial.recover()')
    now = time.monotonic()
    _state = dict(schema=1, active=True, phase='armed', reason=None, error=None,
                  scene_dpg=world_dpg(), key=[float(c) for c in key],
                  chain_count_original=len(player.PlayerPostProcessChains),
                  chain_count_applied=None, chain_count_restored=None, removed=0,
                  restored=False, restore_needed=False, object_destroyed=False, effect_readback=None,
                  player_path=player._path_name(), player_ref=WeakPointer(player), chain_ref=None,
                  donor_session=adapter._session, mailbox=adapter._mailbox,
                  started=now, apply_at=now+3, restore_at=None, duration=seconds,
                  registered=[], history=[])
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
    logging.info(f'BlackLands: world-key trial starts in 3s, removes its chain after {seconds}s; '
                 'HUD flags and viewport flags unchanged.')
