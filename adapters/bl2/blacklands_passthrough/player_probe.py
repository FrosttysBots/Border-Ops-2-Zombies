"""Finite 4 Hz native player/HUD/menu observer, separate from the bootstrap probe."""
import json
import time
import uuid
from mods_base import get_pc
import unrealsdk
from unrealsdk import hooks, logging
from .player_state import inspect_player, path

HOOKS = ('Engine.PlayerController:PlayerTick','WillowGame.WillowGameViewportClient:PostRender')
IDENTIFIER = 'blacklands.readonly.player_state'
_state = None


def publish():
    state=_state
    packet={k:v for k,v in state.items() if k not in ('mailbox','next_sample','deadline','registered')}
    text=json.dumps(packet,allow_nan=False)
    if len(text.encode('utf-8'))>32768: raise ValueError('Player packet exceeds 32 KiB')
    target=state['mailbox']/'blacklands_player.json'
    temp=target.with_suffix('.tmp')
    try:
        temp.write_text(text+'\n',encoding='utf-8');temp.replace(target)
    except OSError as exc:
        if getattr(exc,'winerror',None) not in (5,32,33):raise
        # A Windows reader without FILE_SHARE_DELETE may hold the prior snapshot.
        # Drop this observation; never sleep/retry/block the game thread.
        state['write_skips']+=1
        return False
    return True


def stop(reason='manual_stop'):
    # Fixed owned identifiers also recover hooks left by an interrupted refresh.
    for fn in HOOKS:hooks.remove_hook(fn,hooks.Type.POST,IDENTIFIER)
    if _state is None:return
    _state['registered'].clear();_state['active']=False;_state['reason']=reason
    publish()


def menus():
    # StatusMenu is the native character/inventory/skills menu. No menu is opened.
    result=[]
    for i,obj in enumerate(unrealsdk.find_all('StatusMenuExGFxMovie')):
        if i>=32:raise ValueError('Too many status menu objects')
        if not obj.bMovieIsOpen:continue
        result.append(dict(path=path(obj),open=True,screen=int(obj.CurrentScreen)))
    return result


def on_frame(*_args):
    state=_state
    if state is None or not state['active']:return
    now=time.monotonic()
    import blacklands_passthrough as adapter
    if adapter._session!=state['donor_session'] or adapter._mailbox is None:
        stop('adapter_changed');return
    if now>=state['deadline']:stop('duration_complete');return
    if now<state['next_sample']:return
    state['next_sample']=now+.25
    try:
        pc=get_pc(possibly_loading=True)
        state['seq']+=1
        state['elapsed']=now-state['started']
        state['player']=None if pc is None or pc.Pawn is None else inspect_player(pc)
        try:
            state['menus']=menus();state['menu_error']=None
        except Exception as exc:
            state['menus']=None;state['menu_error']=str(exc)
        publish()
    except Exception as exc:
        state['errors']+=1;state['error']=str(exc)
        logging.warning(f'BlackLands player observer: {exc}')
        stop('observation_error')


def start(seconds=180):
    global _state
    if not 1<=seconds<=180:raise ValueError('Duration must be 1..180 seconds')
    stop('restarted')
    import blacklands_passthrough as adapter
    if adapter._mailbox is None or not adapter._session:raise RuntimeError('Enable the main probe first')
    now=time.monotonic()
    _state=dict(schema=1,source='bl2_player',readonly=True,capture_id=uuid.uuid4().hex,
                donor_session=adapter._session,seq=0,active=True,reason=None,errors=0,error=None,write_skips=0,
                started=now,elapsed=0.,deadline=now+seconds,next_sample=now,
                mailbox=adapter._mailbox,registered=[],player=None,menus=None,menu_error=None)
    try:
        for fn in HOOKS:
            # SDK b1852aa4 may return False after inserting a second POST hook.
            # Presence after our cleanup/add is the authoritative registration check.
            hooks.add_hook(fn,hooks.Type.POST,IDENTIFIER,on_frame)
            if not hooks.has_hook(fn,hooks.Type.POST,IDENTIFIER):raise RuntimeError('Player hook registration failed')
            _state['registered'].append(fn)
        publish()
    except Exception:
        stop('registration_error');raise
    logging.info('BlackLands: finite read-only player/HUD/menu observer started.')
