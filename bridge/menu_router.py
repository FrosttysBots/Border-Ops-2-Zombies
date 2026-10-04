"""Read-only diagnostic view choice; never routes input or controls either game."""
class MenuRouter:
    def __init__(self):
        self.capture_id=None
        self.seq=-1
        self.samples=0
        self.last_advance=None
        self.menu_open=False
        self.reason='waiting_for_player_state'

    def observe(self,packet,donor_session,now):
        if packet['donor_session']!=donor_session or not packet['active']:
            self.menu_open=False;self.reason='inactive_or_wrong_donor';self.samples=0
            return
        if packet['capture_id']!=self.capture_id:
            self.capture_id=packet['capture_id'];self.seq=-1;self.samples=0
            self.menu_open=False;self.last_advance=None
        if packet['seq']<=self.seq:return
        self.seq=packet['seq'];self.samples+=1;self.last_advance=now
        menus=packet.get('menus')
        if packet.get('menu_error') or not isinstance(menus,list):
            self.menu_open=False;self.reason='menu_state_unavailable';return
        self.menu_open=any(m.get('open') is True for m in menus)
        self.reason='native_menu_open' if self.menu_open else 'native_menu_closed'

    def select(self,now):
        if self.samples<2 or self.last_advance is None or now-self.last_advance>2:
            return 'bo2','player_state_stale_or_starting'
        return ('bl2' if self.menu_open else 'bo2'),self.reason
