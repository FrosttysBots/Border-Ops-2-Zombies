"""Finite, reversible test: move first-person arms/gun to the foreground group, then key.

Live evidence (2026-10-04): Pawn.Arms and Weapon.FirstPersonMesh report
DepthPriorityGroup=1, which is SDPG_World on this build (Foreground=2). The AO
world-key trial therefore tinted the gun as well. This trial calls the native
SetDepthPriorityGroup on exactly those two components, holds, then enables the
AO key profile, and restores AO values first and component groups second.
Presentation only: no items, saves, viewport or HUD flags change.
"""
import json
import time
from mods_base import get_pc
from unrealsdk import find_enum, hooks, logging
from unrealsdk.unreal import WeakPointer
from blacklands_passthrough import ao_key_trial as ao

HOOKS = ('Engine.PlayerController:PlayerTick', 'WillowGame.WillowGameViewportClient:PostRender')
IDENTIFIER = 'blacklands.render.foreground_trial'
KEY_PROFILE = 0  # bias +1, MinOcclusion 0: widest live world coverage of the four
_state = None


def report():
    if _state is None:
        return {'active': False}
    return {k:v for k,v in _state.items() if k not in ('effect_ref', 'parts', 'mailbox', 'registered')}


def publish():
    target = _state['mailbox']/'blacklands_foreground_trial.json'
    temp = target.with_suffix('.tmp')
    temp.write_text(json.dumps(report(), allow_nan=False)+'\n', encoding='utf-8')
    temp.replace(target)


def transition(phase):
    _state['phase'] = phase
    _state['history'].append(dict(phase=phase, elapsed=time.monotonic()-_state['started'], wall=time.time()))


def groups():
    for name in ao.DPG_ENUMS:
        try:
            members = find_enum(name).__members__
        except Exception:
            continue
        world, foreground = members.get('SDPG_World'), members.get('SDPG_Foreground')
        if world is not None and foreground is not None and int(world) < int(foreground):
            return int(world), int(foreground)
    raise RuntimeError('SDPG_World/SDPG_Foreground enum not found; refusing to guess values')


def set_group(component, value):
    component.SetDepthPriorityGroup(value)
    if int(component.DepthPriorityGroup) != value:
        raise RuntimeError(f'Depth group readback failed for {component._path_name()}')


def restore_parts(state):
    """Attempt every changed component even if one fails; raise afterwards to retry."""
    failures = []
    for part in state['parts']:
        component = part['ref']()
        if not part['changed']:
            continue
        try:
            if component is None:
                part['destroyed'] = True
            else:
                if component._path_name() != part['path']:
                    raise RuntimeError('Component identity changed; refusing to write another object')
                set_group(component, part['original'])
            part['changed'] = False
        except Exception as exc:
            failures.append(f'{part["name"]}: {exc}')
    if failures:
        raise RuntimeError('; '.join(failures))


def stop(reason='manual_stop'):
    state = _state
    if state is None or not state['active']:
        return
    # AO first, then depth groups; any failure keeps hooks so the next frame retries.
    effect = state['effect_ref']()
    if state['ao_restore_needed'] and effect is not None:
        if effect._path_name() != state['effect_path']:
            raise RuntimeError('AO effect identity changed; refusing to write another object')
        ao.write(effect, state['ao_original'])
        if not ao.matches(ao.capture(effect), state['ao_original']):
            raise RuntimeError('AO restoration did not read back correctly')
    state['ao_restore_needed'] = False
    restore_parts(state)
    state['components'] = [{k:v for k,v in p.items() if k != 'ref'} for p in state['parts']]
    state['restored'] = True
    state['active'] = False
    state['reason'] = reason
    transition('finished')
    for function in state['registered']:
        hooks.remove_hook(function, hooks.Type.POST, IDENTIFIER)
    state['registered'].clear()
    publish()
    logging.info(f'BlackLands foreground trial ended: {reason}; restored={state["restored"]}.')


def to_foreground(state):
    for part in state['parts']:
        component = part['ref']()
        if component is None or int(component.DepthPriorityGroup) != part['original']:
            raise RuntimeError(f'{part["name"]} changed before test')
    for part in state['parts']:
        part['changed'] = True  # native setter could apply and then throw
        set_group(part['ref'](), state['foreground'])


def apply_key(state, effect):
    values = dict(ao.COMMON, **ao.PROFILES[KEY_PROFILE])
    values['OcclusionColor'] = list(state['key']) + [1.0]
    state['ao_restore_needed'] = True
    ao.write(effect, values)
    if not ao.matches(ao.capture(effect), values):
        raise RuntimeError('AO key failed readback')
    state['ao_values'] = values


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
            if not ao.matches(ao.capture(effect), state['ao_original']):
                stop('effect_changed_before_test'); return
            to_foreground(state)
            state['next_at'] = now + state['hold']
            transition('foreground'); publish()
        elif state['phase'] == 'foreground' and now >= state['next_at']:
            apply_key(state, effect)
            state['next_at'] = now + state['keyed']
            transition('foreground_keyed'); publish()
        elif state['phase'] == 'foreground_keyed' and now >= state['next_at']:
            stop('duration_complete')
    except Exception as exc:
        state['error'] = str(exc)
        logging.warning(f'BlackLands foreground trial: {exc}')
        try:
            stop('error')
        except Exception as restore_exc:
            logging.warning(f'BlackLands foreground restore pending: {restore_exc}')


def start(hold=3, keyed=6, key=ao.DEFAULT_KEY):
    global _state
    if not all(isinstance(v, (int, float)) for v in (hold, keyed)) or not (1 <= hold <= 5 and 1 <= keyed <= 8):
        raise ValueError('hold must be 1..5s and keyed 1..8s')
    if len(key) != 3 or not all(isinstance(c, (int, float)) and 0 <= c <= 1 for c in key):
        raise ValueError('Key colour must be three components in 0..1')
    stop('restarted')
    import blacklands_passthrough as adapter
    pc = get_pc(possibly_loading=True)
    if adapter._mailbox is None or not adapter._session or pc is None or pc.Pawn is None:
        raise RuntimeError('Enable the main probe and load a character first')
    world, foreground = groups()
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
                  world=world, foreground=foreground, key=[float(c) for c in key],
                  hold=float(hold), keyed=float(keyed), ao_original=ao.capture(effect),
                  ao_values=None, ao_restore_needed=False, effect_path=effect._path_name(),
                  effect_ref=WeakPointer(effect), parts=parts, components=None, restored=False,
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
    logging.info(f'BlackLands: foreground trial starts in 3s: gun/arms foreground {hold}s, '
                 f'then AO key {keyed}s, then full restore.')
