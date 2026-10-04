"""Explicit finite native inventory opener. No arbitrary calls, keys or item edits."""
import time
import uuid
from mods_base import get_pc
from unrealsdk import hooks, logging
from .menu_wire import MenuGate, STATUS_FILE, REQUEST_FILE, read_packet, write_packet
from .player_probe import menus

HOOKS = ('Engine.PlayerController:PlayerTick', 'WillowGame.WillowGameViewportClient:PostRender')
IDENTIFIER = 'blacklands.ui.inventory_control'
_state = None


def publish():
    state = _state
    gate = state['gate']
    packet = {key: state[key] for key in ('active', 'seq', 'reason', 'errors', 'write_skips', 'menu_screens')}
    packet.update(schema=1, source='bl2_menu_control', activation=gate.activation,
                  donor_session=gate.donor_session, last_request=gate.last_request, result=gate.result)
    if not write_packet(state['mailbox']/STATUS_FILE, packet):
        state['write_skips'] += 1


def stop(reason='manual_stop'):
    for fn in HOOKS:
        hooks.remove_hook(fn, hooks.Type.POST, IDENTIFIER)
    if _state is None:
        return
    _state['active'] = False
    _state['reason'] = reason
    _state['gate'].cancel()
    _state['registered'].clear()
    publish()


def on_frame(*_args):
    state = _state
    if state is None or not state['active']:
        return
    import blacklands_passthrough as adapter
    now = time.monotonic()
    if adapter._session != state['gate'].donor_session or adapter._mailbox is None:
        stop('adapter_changed'); return
    if now >= state['deadline']:
        stop('duration_complete'); return
    if now < state['next_sample']:
        return
    state['next_sample'] = now + .1
    try:
        pc = get_pc(possibly_loading=True)
        if pc is None or pc.Pawn is None:
            stop('player_unavailable'); return
        screens = [menu['screen'] for menu in menus()]
        state['menu_screens'] = screens
        state['gate'].observe(screens, now)
        try:
            request = read_packet(state['mailbox']/REQUEST_FILE)
            state['gate'].submit(request, int(time.time()*1000), now, screens,
                                 pc.ShowStatusMenu_Inventory)
        except (OSError, ValueError, KeyError, TypeError):
            # Stale/malformed/locked requests are inert; sender has its own deadline.
            pass
        state['seq'] += 1
        publish()
    except Exception as exc:
        state['errors'] += 1
        logging.warning(f'BlackLands menu control: {type(exc).__name__}: {exc}')
        stop('observation_error')


def start(seconds=180):
    global _state
    if not 1 <= seconds <= 180:
        raise ValueError('Duration must be 1..180 seconds')
    stop('restarted')
    import blacklands_passthrough as adapter
    if adapter._mailbox is None or not adapter._session:
        raise RuntimeError('Enable the main probe first')
    _state = dict(gate=MenuGate(uuid.uuid4().hex, adapter._session), mailbox=adapter._mailbox,
                  active=True, seq=0, reason=None, errors=0, write_skips=0, menu_screens=[],
                  deadline=time.monotonic()+seconds, next_sample=0., registered=[])
    try:
        for fn in HOOKS:
            hooks.add_hook(fn, hooks.Type.POST, IDENTIFIER, on_frame)
            if not hooks.has_hook(fn, hooks.Type.POST, IDENTIFIER):
                raise RuntimeError('Menu control hook registration failed')
            _state['registered'].append(fn)
        publish()
    except Exception:
        stop('registration_error'); raise
    logging.info('BlackLands: finite native inventory control enabled; only open_inventory is accepted.')
