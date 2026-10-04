"""Synthetic lifecycle tests: fog edit + ForceUpdate + group restore, not native proof."""
import json
from pathlib import Path
import types
import unittest
from unittest.mock import patch

import test_foreground_trial as fgt
from test_foreground_trial import MODS, load


class Fog:
    def __init__(self):
        self.bEnabled, self.bAttached = True, True
        self.Height, self.Density, self.LightBrightness = 16211.68, 5.487e-06, 0.666
        self.ExtinctionDistance, self.StartDistance = 49963928.0, 6495.45
        self.LightColor = types.SimpleNamespace(R=62, G=121, B=219, A=255)
        self.updates, self.fail_density = [], None

    def __setattr__(self, name, value):
        if name == 'Density' and getattr(self, 'fail_density', None) == value:
            raise RuntimeError('Synthetic setter failure')
        object.__setattr__(self, name, value)

    def _path_name(self):
        return 'Ice_Light.TheWorld:PersistentLevel.HeightFog_0.HeightFogComponent_0'

    def ForceUpdate(self, transform_only):
        self.updates.append((transform_only, self.Density))


class FogTrialTests(unittest.TestCase):
    setUp = fgt.ForegroundTrialTests.setUp
    tearDown = fgt.ForegroundTrialTests.tearDown

    def prepare(self):
        self.fog = Fog()
        import sys
        sys.modules['unrealsdk'].find_all = lambda cls, exact=True: [self.fog]
        self.adapter.foreground_trial = load('foreground_trial_fog', MODS/'foreground_trial.py')
        self.mod_fog = load('fog_trial_test', MODS/'fog_trial.py')
        self.clock.stop()
        self.clock = patch.object(self.mod_fog.time, 'monotonic', return_value=100.)
        self.now = self.clock.start()

    def test_foreground_then_fog_profiles_then_full_restore(self):
        self.prepare()
        self.mod_fog.start()
        self.now.return_value = 103.
        self.mod_fog.on_frame()
        self.assertEqual((self.arms.DepthPriorityGroup, self.gun.DepthPriorityGroup), (2, 2))
        self.assertEqual(self.fog.updates, [])
        for t, density in ((106., 0.01), (109., 1.0)):
            self.now.return_value = t
            self.mod_fog.on_frame()
            self.assertEqual(self.fog.Density, density)
            self.assertEqual((self.fog.LightColor.R, self.fog.LightColor.G), (255, 0))
        self.now.return_value = 112.
        self.mod_fog.on_frame()
        self.assertEqual((self.fog.Density, self.fog.Height, self.fog.LightColor.B), (5.487e-06, 16211.68, 219))
        self.assertEqual(self.fog.updates[-1], (False, 5.487e-06))
        self.assertEqual((self.arms.DepthPriorityGroup, self.gun.DepthPriorityGroup), (1, 1))
        self.assertFalse(self.registered)
        status = json.loads((Path(self.temp.name)/'blacklands_fog_trial.json').read_text())
        self.assertTrue(status['restored'])
        self.assertEqual(status['updates'], 3)
        self.assertEqual(status['overwrites'], 0)

    def test_failed_profile_restores_fog_and_groups(self):
        self.prepare()
        self.fog.fail_density = 0.01
        self.mod_fog.start()
        for t in (103., 106.):
            self.now.return_value = t
            self.mod_fog.on_frame()
        self.assertIn('Synthetic', self.mod_fog.report()['error'])
        self.assertEqual(self.fog.Density, 5.487e-06)
        self.assertEqual((self.arms.DepthPriorityGroup, self.gun.DepthPriorityGroup), (1, 1))
        self.assertFalse(self.registered)

    def test_game_overwrite_is_reasserted_and_latest_original_restored(self):
        self.prepare()
        self.mod_fog.start()
        self.fog.Density = 7.0e-06  # game's own updater changes fog during the delay
        for t in (103., 106.):
            self.now.return_value = t
            self.mod_fog.on_frame()
        self.fog.Density = 8.0e-06  # game overwrites the profile mid-step
        self.now.return_value = 107.
        self.mod_fog.on_frame()
        self.assertEqual(self.fog.Density, 0.01)
        self.assertEqual(self.mod_fog.report()['overwrites'], 1)
        self.mod_fog.stop()
        self.assertEqual(self.fog.Density, 7.0e-06)
        self.assertEqual((self.arms.DepthPriorityGroup, self.gun.DepthPriorityGroup), (1, 1))

    def test_refuses_without_single_enabled_fog(self):
        self.prepare()
        self.fog.bEnabled = False
        with self.assertRaises(RuntimeError): self.mod_fog.start()
        self.assertEqual(self.arms.calls, [])
        self.assertFalse(self.registered)

    def test_rejects_invalid_key(self):
        self.prepare()
        with self.assertRaises(ValueError): self.mod_fog.start(key=(255, 0, 300))


if __name__ == '__main__':
    unittest.main()
