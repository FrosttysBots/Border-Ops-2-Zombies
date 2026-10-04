"""Synthetic lifecycle tests: held isolation mode, heartbeat, weapon follow, restore."""
import json
from pathlib import Path
import sys
import unittest
from unittest.mock import patch

import test_foreground_trial as fgt
from test_fog_trial import Fog
from test_foreground_trial import Component, MODS, load


class IsolationModeTests(unittest.TestCase):
    setUp = fgt.ForegroundTrialTests.setUp
    tearDown = fgt.ForegroundTrialTests.tearDown

    def prepare(self):
        self.fog = Fog()
        sys.modules['unrealsdk'].find_all = lambda cls, exact=True: [self.fog]
        self.adapter.foreground_trial = load('foreground_trial_iso', MODS/'foreground_trial.py')
        self.adapter.fog_trial = load('fog_trial_iso', MODS/'fog_trial.py')
        self.iso = load('isolation_mode_test', MODS/'isolation_mode.py')
        self.clock.stop()
        self.clock = patch.object(self.iso.time, 'monotonic', return_value=100.)
        self.now = self.clock.start()

    def status(self):
        return json.loads((Path(self.temp.name)/'blacklands_isolation.json').read_text())

    def test_engages_holds_reasserts_publishes_and_restores_at_deadline(self):
        self.prepare()
        self.iso.start(seconds=10)
        self.iso.on_frame()
        self.assertEqual((self.arms.DepthPriorityGroup, self.gun.DepthPriorityGroup), (2, 2))
        self.assertEqual(self.fog.Density, 1.0)
        first = self.status()
        self.assertEqual(first['phase'], 'isolated')
        self.fog.Density = 3e-06  # game rewrites the fog
        self.now.return_value = 100.5
        self.iso.on_frame()
        self.assertEqual(self.fog.Density, 1.0)
        self.assertGreater(self.status()['seq'], first['seq'])
        self.assertEqual(self.status()['overwrites'], 1)
        self.now.return_value = 110.
        self.iso.on_frame()
        self.assertEqual(self.fog.Density, 5.487e-06)  # originals captured at engage
        self.assertEqual((self.arms.DepthPriorityGroup, self.gun.DepthPriorityGroup), (1, 1))
        final = self.status()
        self.assertFalse(final['active'])
        self.assertEqual(final['reason'], 'duration_complete')
        self.assertFalse(self.registered)

    def test_new_weapon_follows_into_foreground_and_is_restored(self):
        self.prepare()
        self.iso.start(seconds=10)
        self.iso.on_frame()
        other = Component('Weapon_2.FirstPersonMesh')
        self.pc.Pawn.Weapon.FirstPersonMesh = other
        self.now.return_value = 101.
        self.iso.on_frame()
        self.assertEqual(other.DepthPriorityGroup, 2)
        self.assertEqual(self.status()['weapon_switches'], 1)
        self.iso.stop()
        self.assertEqual((other.DepthPriorityGroup, self.gun.DepthPriorityGroup, self.arms.DepthPriorityGroup), (1, 1, 1))

    def test_rejects_invalid_duration(self):
        self.prepare()
        with self.assertRaises(ValueError): self.iso.start(seconds=181)


if __name__ == '__main__':
    unittest.main()
