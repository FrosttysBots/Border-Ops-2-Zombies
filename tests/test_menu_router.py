import sys
from pathlib import Path
import unittest
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'bridge'))
from menu_router import MenuRouter

class MenuRouterTests(unittest.TestCase):
    def packet(self,seq,opened=True,**changes):
        return dict(capture_id='a'*32,donor_session='b'*32,seq=seq,active=True,
                    menus=[{'open':True,'screen':3}] if opened else [],menu_error=None)|changes
    def test_native_open_close_needs_advancing_state(self):
        r=MenuRouter();r.observe(self.packet(1),'b'*32,0)
        self.assertEqual(r.select(0)[0],'bo2')
        r.observe(self.packet(2),'b'*32,.25);self.assertEqual(r.select(.25)[0],'bl2')
        r.observe(self.packet(3,False),'b'*32,.5);self.assertEqual(r.select(.5)[0],'bo2')
    def test_duplicates_and_backwards_sequences_do_not_keep_menu_live(self):
        r=MenuRouter()
        for seq,t in [(1,0),(2,.25),(2,1),(1,2)]:r.observe(self.packet(seq),'b'*32,t)
        self.assertEqual(r.select(3)[0],'bo2')
    def test_wrong_donor_and_inactive_fail_to_host(self):
        for bad in [self.packet(3,donor_session='c'*32),self.packet(3,active=False)]:
            r=MenuRouter();r.observe(self.packet(1),'b'*32,0);r.observe(self.packet(2),'b'*32,.25)
            r.observe(bad,'b'*32,.5);self.assertEqual(r.select(.5)[0],'bo2')
    def test_new_capture_requires_fresh_progress(self):
        r=MenuRouter();r.observe(self.packet(1),'b'*32,0);r.observe(self.packet(2),'b'*32,.25)
        r.observe(self.packet(1,capture_id='d'*32),'b'*32,.5)
        self.assertEqual(r.select(.5)[0],'bo2')
