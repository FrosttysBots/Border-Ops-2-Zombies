"""Finite, reversible test: arms/gun in SDPG_Foreground plus dense key-coloured height fog.

Live evidence (2026-10-04): Ice_Light has one enabled HeightFogComponent (and a
disabled ExponentialHeightFogComponent). The hypothesis is that height fog is drawn
for the world group only, so dense key-coloured fog could cover the donor world
while the Foreground gun stays clean. Only the existing enabled component is edited;
native ForceUpdate(False) pushes values to the renderer. Restore: fog originals and
ForceUpdate first, then the depth groups. Presentation only.
"""
import json
import time
from mods_base import get_pc
from unrealsdk import find_all, hooks, logging, make_struct
from unrealsdk.unreal import WeakPointer
from blacklands_passthrough import foreground_trial as fg

HOOKS = ('Engine.PlayerController:PlayerTick', 'WillowGame.WillowGameViewportClient:PostRender')
IDENTIFIER = 'blacklands.render.fog_trial'
FOG_CLASS = 'Engine.HeightFogComponent'
FLOATS = ('Height', 'Density', 'LightBrightness', 'ExtinctionDistance', 'StartDistance')
FAR = 1.0e9
PROFILES = (
    dict(name='dense', Density=0.01),
    dict(name='very_dense', Density=1.0),
)
COMMON = dict(Height=FAR, LightBrightness=1.0, ExtinctionDistance=FAR, StartDistance=0.0)
DEFAULT_KEY = (255, 0, 255)
_state = None


def report():
    if _state is None:
        return {'active': False}
    return {k:v for k,v in _state.items() if k not in ('fog_ref', 'parts', 'mailbox', 'registered')}


def publish():
    target = _state['mailbox']/'blacklands_fog_trial.json'
    temp = target.with_suffix('.tmp')
    temp.write_text(json.dumps(report(), allow_nan=False)+'\n', encoding='utf-8')
    temp.replace(target)


def transition(phase, **extra):
    _state['phase'] = phase
    _state['history'].append(dict(phase=phase, elapsed=time.monotonic()-_state['started'],
                                  wall=time.time(), **extra))


def find_fog():
    found = [c for c in find_all(FOG_CLASS, exact=True)
             if 'Default__' not in c._path_name() and c.bEnabled and c.bAttached]
    if len(found) != 1:
        raise RuntimeError(f'Expected one enabled, attached height fog component, found {len(found)}')
    return found[0]


def capture(fog):
    color = fog.LightColor
    values = {name: getattr(fog, name) for name in FLOATS}
    values['LightColor'] = [int(color.R), int(color.G), int(color.B), int(color.A)]
    return values


def write(fog, values):
    for name, value in values.items():
        if name == 'LightColor':
            fog.LightColor = make_struct('Color', R=value[0], G=value[1], B=value[2], A=value[3])
        else:
            setattr(fog, name, value)


def matches(actual, expected):
    for name, value in expected.items():
        got = actual[name]
        if isinstance(value, list):
            if list(got) != list(value): return False
        elif abs(got-value) > max(1e-12, abs(value)*1e-5):  # Density is ~1e-6
            return False
    return True


def push(state, fog):
    fog.ForceUpdate(False)
    state['updates'] += 1


def apply_profile(state, fog, index):
    profile = PROFILES[index]
    values = dict(COMMON, **{k:v for k,v in profile.items() if k != 'name'})
    values['LightColor'] = list(state['key']) + [255]
    if not state['fog_restore_needed']:
        # Live: BL2 changes this fog by itself, so originals are taken at first write.
        state['fog_original'] = capture(fog)
    state['fog_restore_needed'] = True  # a setter could mutate and then throw
    state['values'] = values
    write(fog, values)
    if not matches(capture(fog), values):
        raise RuntimeError('Fog profile failed readback')
    push(state, fog)
    state['profile'] = index
    state['next_at'] = time.monotonic() + state['step']
    transition('profile', index=index, name=profile['name'], values=values)
    publish()


def stop(reason='manual_stop'):
    state = _state
    if state is None or not state['active']:
        return
    # Fog values and renderer refresh first, then depth groups; failures keep hooks.
    fog = state['fog_ref']()
    if state['fog_restore_needed'] and fog is not None:
        if fog._path_name() != state['fog_path']:
            raise RuntimeError('Fog identity changed; refusing to write another object')
        write(fog, state['fog_original'])
        if not matches(capture(fog), state['fog_original']):
            raise RuntimeError('Fog restoration did not read back correctly')
        push(state, fog)
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
    logging.info(f'BlackLands fog trial ended: {reason}; restored={state["restored"]}.')


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
        fog = state['fog_ref']()
        if fog is None:
            stop('fog_destroyed'); return
        if state['phase'] == 'armed' and now >= state['next_at']:
            fg.to_foreground(state)
            state['next_at'] = now + state['step']
            transition('foreground'); publish()
        elif state['phase'] == 'foreground' and now >= state['next_at']:
            apply_profile(state, fog, 0)
        elif state['phase'] == 'profile' and now < state['next_at']:
            # The game's own fog updater may overwrite the profile; reassert it.
            if not matches(capture(fog), state['values']):
                state['overwrites'] += 1
                write(fog, state['values'])
                push(state, fog)
        elif state['phase'] == 'profile' and now >= state['next_at']:
            if state['profile'] + 1 < len(PROFILES):
                apply_profile(state, fog, state['profile'] + 1)
            else:
                stop('duration_complete')
    except Exception as exc:
        state['error'] = str(exc)
        logging.warning(f'BlackLands fog trial: {exc}')
        try:
            stop('error')
        except Exception as restore_exc:
            logging.warning(f'BlackLands fog restore pending: {restore_exc}')


def start(step=3, key=DEFAULT_KEY):
    global _state
    if not isinstance(step, (int, float)) or not 1 <= step <= 4:
        raise ValueError('Step must be 1..4 seconds (3 phases, <=12s total)')
    if len(key) != 3 or not all(isinstance(c, int) and 0 <= c <= 255 for c in key):
        raise ValueError('Key colour must be three integers in 0..255')
    stop('restarted')
    import blacklands_passthrough as adapter
    pc = get_pc(possibly_loading=True)
    if adapter._mailbox is None or not adapter._session or pc is None or pc.Pawn is None:
        raise RuntimeError('Enable the main probe and load a character first')
    world, foreground = fg.groups()
    fog = find_fog()
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
                  world=world, foreground=foreground, key=list(key), step=float(step), profile=None,
                  fog_original=None, fog_restore_needed=False, updates=0, overwrites=0, values=None,
                  fog_path=fog._path_name(), fog_ref=WeakPointer(fog),
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
    logging.info(f'BlackLands: fog trial starts in 3s: gun/arms foreground {step}s, then '
                 f'{len(PROFILES)} fog profiles x {step}s, then full restore.')
