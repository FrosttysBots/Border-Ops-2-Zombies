import json
from pathlib import Path
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'bridge'))
from presentation_health import choose_capture
from record_player import read_player


class PresentationHealthTests(unittest.TestCase):
    def state(self, **changes):
        return dict(latest=(10.,1,None),closed=False,error=None)|changes

    def test_donor_closed_stale_and_error_fall_back(self):
        for changes in [dict(closed=True),dict(error='capture failure'),dict(latest=None),dict(latest=(7.,1,None))]:
            result=choose_capture('bl2',dict(bl2=self.state(**changes),bo2=self.state()),10.)
            self.assertEqual(result,('bo2','bl2_capture_unavailable'))

    def test_healthy_inventory_and_host_selection(self):
        states={s:self.state() for s in ('bo2','bl2')}
        for desired in states:self.assertEqual(choose_capture(desired,states,10.),(desired,None))

    def test_unavailable_host_does_not_show_unrequested_donor_world(self):
        self.assertIsNone(choose_capture('bo2',dict(bo2=self.state(closed=True),bl2=self.state()),10.)[0])

    def test_invalid_nested_menu_packets_are_rejected(self):
        with tempfile.TemporaryDirectory(dir=ROOT/'work') as directory:
            path=Path(directory)/'player.json'
            base=dict(schema=1,source='bl2_player',readonly=True,capture_id='a'*32,
                      donor_session='b'*32,seq=1,active=True)
            for menus in [42,[None],[{'open':True,'screen':True}],[{'open':False,'screen':3}],[]*0+[{}]*33]:
                path.write_text(json.dumps(base|dict(menus=menus)))
                with self.assertRaises(ValueError):read_player(path)
            path.write_text('[]')
            with self.assertRaises(ValueError):read_player(path)
