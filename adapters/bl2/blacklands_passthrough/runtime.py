"""Optional finite native pose publisher; all UObject reads stay on the game thread."""
import json
import time
from mods_base import get_pc
from unrealsdk import hooks, logging
from .runtime_ipc import ENDPOINT_FILE, Publisher

_state = None
_function = 'Engine.PlayerController:PlayerTick'
_identifier = 'blacklands.readonly.runtime.tick'


def status():
    if _state is None:
        return dict(active=False)
    return _state['publisher'].status() | dict(active=_state['active'],errors=_state['errors'],
                                              reason=_state['reason'])


def write_status():
    state=_state
    target=state['mailbox']/'blacklands_runtime_bl2.json'
    temp=target.with_suffix('.tmp')
    try:
        temp.write_text(json.dumps(status(),allow_nan=False)+'\n',encoding='utf-8')
        temp.replace(target)
    except OSError:
        pass


def stop(reason='manual_stop'):
    hooks.remove_hook(_function,hooks.Type.POST,_identifier)
    if _state is not None:
        _state['active']=False
        _state['reason']=reason
        _state['publisher'].close()
        write_status()


def on_tick(obj,*_args):
    state=_state
    if state is None or not state['active']:
        return
    import blacklands_passthrough as adapter
    now=time.monotonic()
    if adapter._mailbox is None or adapter._session != state['donor_session']:
        stop('adapter_disabled_or_restarted');return
    if now >= state['deadline']:
        stop('duration_complete');return
    publisher=state['publisher']
    # No permanent background work if the sidecar goes away or is never started.
    if now-state['started']>5 and (publisher.last_ack is None or now-publisher.last_ack>5):
        stop('sidecar_unresponsive');return
    if now<state['next_send']:
        return
    try:
        pc=get_pc(possibly_loading=True)
        if pc is None or obj != pc or pc.Pawn is None:
            return
        state['next_send']=now+1/60
        location=pc.Pawn.Location
        rotation=pc.Rotation
        weapon=pc.Pawn.Weapon
        publisher.send([float(location.X),float(location.Y),float(location.Z)],
                       [float(rotation.Pitch),float(rotation.Yaw),float(rotation.Roll)],
                       None if weapon is None else weapon._path_name())
        if now>=state['next_status']:
            state['next_status']=now+1
            write_status()
    except Exception as exc:
        state['errors']+=1
        logging.warning(f'BlackLands runtime observation failed: {exc}')
        stop('observation_error')


def start(seconds=180):
    global _state
    if not 0<seconds<=180:
        raise ValueError('Runtime observation must be 0..180 seconds')
    stop('restarted')
    import blacklands_passthrough as adapter
    if adapter._mailbox is None or not adapter._session:
        raise RuntimeError('Enable the main BlackLands probe first')
    publisher=Publisher(adapter._mailbox/ENDPOINT_FILE)
    now=time.monotonic()
    _state=dict(active=True,reason=None,publisher=publisher,started=now,deadline=now+seconds,
                next_send=now,next_status=now,errors=0,mailbox=adapter._mailbox,donor_session=adapter._session)
    try:
        if not hooks.add_hook(_function,hooks.Type.POST,_identifier,on_tick):
            raise RuntimeError('Runtime tick hook registration failed')
    except Exception:
        stop('registration_failed');raise
    logging.info('BlackLands: optional read-only pose IPC started, capped at 60 Hz for 180s maximum.')
