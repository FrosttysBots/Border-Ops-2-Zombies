"""Synthetic lifecycle tests: world flag + depth-group restoration, not native rendering proof."""
from pathlib import Path
import json
import sys
import types
import unittest

import test_foreground_trial as fgt
from test_foreground_trial import MODS, load


class Viewport:
    def __init__(self):
        self.value, self.fail_restore = False, False

    def _path_name(self):
        return 'Test.Viewport'

    @property
    def bDisableWorldRendering(self):
        return self.value

    @bDisableWorldRendering.setter
    def bDisableWorldRendering(self, value):
        if not value and self.fail_restore:
            raise RuntimeError('Synthetic restore failure')
        self.value = value


class BlackoutTrialTests(unittest.TestCase):
    setUp = fgt.ForegroundTrialTests.setUp
    tearDown = fgt.ForegroundTrialTests.tearDown

    def setUpHook(self):
        self.viewport = Viewport()
        self.pc.Player.ViewportClient = self.viewport
        self.adapter.foreground_trial = load('foreground_trial_bo', MODS/'foreground_trial.py')
        self.bo = load('blackout_trial_test', MODS/'blackout_trial.py')
        self.clock.stop()
        from unittest.mock import patch
        self.clock = patch.object(self.bo.time, 'monotonic', return_value=100.)
        self.now = self.clock.start()

    def run_to_blackout(self):
        self.setUpHook()
        self.bo.start()
        self.now.return_value = 103.
        self.bo.on_frame()
        self.assertEqual((self.arms.DepthPriorityGroup, self.gun.DepthPriorityGroup), (2, 2))
        self.assertFalse(self.viewport.value)
        self.now.return_value = 105.
        self.bo.on_frame()
        self.assertTrue(self.viewport.value)

    def test_foreground_then_blackout_then_full_restore(self):
        self.run_to_blackout()
        self.now.return_value = 111.
        self.bo.on_frame()
        self.assertFalse(self.viewport.value)
        self.assertEqual((self.arms.DepthPriorityGroup, self.gun.DepthPriorityGroup), (1, 1))
        self.assertFalse(self.registered)
        status = json.loads((Path(self.temp.name)/'blacklands_blackout_trial.json').read_text())
        self.assertTrue(status['restored'])
        self.assertEqual([h['phase'] for h in status['history']],
                         ['armed', 'foreground', 'foreground_world_disabled', 'finished'])

    def test_failed_flag_restore_keeps_groups_and_hooks_then_retries(self):
        self.run_to_blackout()
        self.viewport.fail_restore = True
        self.adapter._session = 'new'
        self.bo.on_frame()
        self.assertTrue(self.bo.report()['active'])
        self.assertEqual(len(self.registered), 2)
        self.viewport.fail_restore = False
        self.bo.on_frame()
        self.assertFalse(self.viewport.value)
        self.assertEqual((self.arms.DepthPriorityGroup, self.gun.DepthPriorityGroup), (1, 1))
        self.assertFalse(self.registered)

    def test_refuses_when_world_already_disabled(self):
        self.setUpHook()
        self.viewport.value = True
        with self.assertRaises(RuntimeError): self.bo.start()
        self.assertEqual(self.arms.calls, [])
        self.assertFalse(self.registered)

    def test_external_flag_change_during_delay_changes_nothing(self):
        self.setUpHook()
        self.bo.start()
        self.viewport.value = True
        self.now.return_value = 103.
        self.bo.on_frame()
        self.assertEqual(self.bo.report()['reason'], 'flag_changed_before_test')
        self.assertEqual(self.arms.calls, [])
        self.assertTrue(self.viewport.value)


if __name__ == '__main__':
    unittest.main()
