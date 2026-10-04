"""Synthetic chroma-key/heartbeat tests. Needs numpy (run with work/render-venv)."""
import json
from pathlib import Path
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT/'bridge'))
try:
    import numpy as np
    import composite
except ImportError:  # base interpreter without numpy
    np = None


@unittest.skipIf(np is None, 'numpy unavailable; run with work/render-venv python')
class CompositeTests(unittest.TestCase):
    KEY = (244, 9, 181)  # live tonemapped key, BGR

    def frames(self):
        host = np.full((60, 80, 3), (10, 200, 10), np.uint8)
        donor = np.zeros((60, 80, 3), np.uint8); donor[:] = self.KEY
        donor[40:, 50:] = (40, 60, 120)   # gun
        donor[50:, :20] = (200, 200, 200) # HUD
        return host, donor

    def test_key_becomes_host_and_content_stays(self):
        host, donor = self.frames()
        out = composite.composite(host, donor)
        self.assertEqual(tuple(out[5, 5]), (10, 200, 10))
        self.assertEqual(tuple(out[45, 60]), (40, 60, 120))
        self.assertEqual(tuple(out[55, 5]), (200, 200, 200))

    def test_coverage_detects_keyed_and_unkeyed_frames(self):
        _, donor = self.frames()
        self.assertEqual(composite.coverage(donor), 1.0)
        world = np.full((60, 80, 3), (180, 120, 60), np.uint8)  # ordinary BL2 world
        self.assertEqual(composite.coverage(world), 0.0)

    def test_donor_resized_to_host(self):
        host = np.zeros((600, 800, 3), np.uint8)
        _, donor = self.frames()
        self.assertEqual(composite.composite(host, donor).shape, (600, 800, 3))

    def test_partial_edge_is_despilled(self):
        host = np.zeros((1, 1, 3), np.uint8)
        edge = np.array([[[150, 40, 140]]], np.uint8)  # magenta-tinted edge
        a = composite.alpha(edge)[0, 0]
        self.assertTrue(0 < a < 1)
        out = composite.composite(host, edge)[0, 0]
        self.assertLess(int(out[0]), int(150 * a) + 1)


class TrackerTests(unittest.TestCase):
    def setUp(self):
        sys.path.insert(0, str(ROOT/'bridge'))
        if np is None:
            self.skipTest('numpy unavailable')

    def test_requires_active_isolated_advancing_fresh_heartbeat(self):
        t = composite.IsolationTracker()
        status = dict(schema=1, seq=1, active=True, phase='isolated', donor_session='s')
        t.observe(status, 10.)
        self.assertEqual(t.ready(10.), (False, 'awaiting_heartbeat'))
        t.observe(dict(status, seq=2), 10.3)
        self.assertEqual(t.ready(10.5), (True, 'isolated'))
        self.assertEqual(t.ready(13.), (False, 'heartbeat_stale'))
        t.observe(dict(status, seq=3, active=False, phase='finished'), 13.)
        self.assertEqual(t.ready(13.), (False, 'isolation_inactive'))

    def test_read_status_bounds_and_session(self):
        with tempfile.TemporaryDirectory(dir=ROOT/'work') as box:
            path = Path(box)/'status.json'
            path.write_text(json.dumps(dict(schema=1, seq=4, donor_session='s')))
            self.assertEqual(composite.read_status(path, 's')['seq'], 4)
            with self.assertRaises(ValueError): composite.read_status(path, 'other')
            path.write_text('x' * 70000)
            with self.assertRaises(ValueError): composite.read_status(path)


if __name__ == '__main__':
    unittest.main()
