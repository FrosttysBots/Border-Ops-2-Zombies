"""Synthetic lifecycle tests: AO coverage profiles + chain refresh + group restore."""
import json
from pathlib import Path
import unittest
from unittest.mock import patch

import test_foreground_trial as fgt
from test_foreground_trial import MODS, load


class CoverageTrialTests(unittest.TestCase):
    setUp = fgt.ForegroundTrialTests.setUp
    tearDown = fgt.ForegroundTrialTests.tearDown

    def prepare(self):
        self.effect.OcclusionRadius = 40.0
        self.touches = []
        self.pc.Player.TouchPlayerPostProcessChain = lambda: self.touches.append(
            (self.effect.OcclusionBias, self.effect.OcclusionRadius))
        self.adapter.foreground_trial = load('foreground_trial_cov', MODS/'foreground_trial.py')
        self.cov = load('coverage_trial_test', MODS/'coverage_trial.py')
        self.clock.stop()
        self.clock = patch.object(self.cov.time, 'monotonic', return_value=100.)
        self.now = self.clock.start()

    def test_profiles_refresh_then_full_restore(self):
        self.prepare()
        self.cov.start()
        for t in (103., 106., 109., 112.):
            self.now.return_value = t
            self.cov.on_frame()
            self.assertEqual((self.arms.DepthPriorityGroup, self.gun.DepthPriorityGroup), (2, 2))
        self.assertEqual(self.effect.OcclusionRadius, 5000.0)
        self.assertEqual(len(self.touches), 3)
        self.now.return_value = 115.
        self.cov.on_frame()
        self.assertEqual((self.effect.OcclusionBias, self.effect.OcclusionRadius, self.effect.OcclusionPower),
                         (0.2, 40.0, 4.0))
        self.assertEqual(self.touches[-1], (0.2, 40.0))  # refreshed after originals restored
        self.assertEqual((self.arms.DepthPriorityGroup, self.gun.DepthPriorityGroup), (1, 1))
        self.assertFalse(self.registered)
        status = json.loads((Path(self.temp.name)/'blacklands_coverage_trial.json').read_text())
        self.assertTrue(status['restored'])
        self.assertEqual([h.get('name') for h in status['history'] if h['phase'] == 'profile'],
                         ['baseline', 'refresh_chain', 'low_power', 'wide_radius'])

    def test_failed_refresh_after_restore_keeps_hooks_and_retries(self):
        self.prepare()
        self.cov.start()
        for t in (103., 106.):
            self.now.return_value = t
            self.cov.on_frame()
        def broken(): raise RuntimeError('Synthetic refresh failure')
        self.pc.Player.TouchPlayerPostProcessChain = broken
        self.adapter._session = 'new'
        self.cov.on_frame()
        self.assertTrue(self.cov.report()['active'])
        self.assertEqual(self.effect.OcclusionBias, 0.2)
        self.pc.Player.TouchPlayerPostProcessChain = lambda: self.touches.append('retry')
        self.cov.on_frame()
        self.assertEqual(self.touches[-1], 'retry')
        self.assertEqual((self.arms.DepthPriorityGroup, self.gun.DepthPriorityGroup), (1, 1))
        self.assertFalse(self.registered)

    def test_rejects_invalid_step(self):
        self.prepare()
        with self.assertRaises(ValueError): self.cov.start(step=5)


if __name__ == '__main__':
    unittest.main()
