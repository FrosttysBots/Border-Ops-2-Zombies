"""Synthetic lifecycle tests: depth-group + AO restoration safety, not native rendering proof."""
import importlib.util
import json
from pathlib import Path
import sys
import tempfile
import types
import unittest
from unittest.mock import patch

from test_ao_key_trial import DPG, Effect

ROOT = Path(__file__).resolve().parents[1]
MODS = ROOT/'adapters/bl2/blacklands_passthrough'


class Component:
    def __init__(self, path, group=1):
        self.path, self.DepthPriorityGroup = path, group
        self.calls, self.fail_value = [], None

    def _path_name(self):
        return self.path

    def SetDepthPriorityGroup(self, value):
        self.calls.append(value)
        if value == self.fail_value:
            raise RuntimeError('Synthetic setter failure')
        self.DepthPriorityGroup = value


def load(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class ForegroundTrialTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(dir=ROOT/'work')
        self.effect = Effect()
        self.arms = Component('Pawn.Arms')
        self.gun = Component('Weapon.FirstPersonMesh')
        pawn = types.SimpleNamespace(Arms=self.arms, Weapon=types.SimpleNamespace(FirstPersonMesh=self.gun))
        chain = types.SimpleNamespace(Effects=[self.effect])
        self.pc = types.SimpleNamespace(Pawn=pawn, Player=types.SimpleNamespace(PlayerPostProcess=chain))
        self.registered = set()
        def add(function, *_):
            self.registered.add(function)
            return False
        hooks = types.SimpleNamespace(Type=types.SimpleNamespace(POST=1), add_hook=add,
                    has_hook=lambda function,*_: function in self.registered,
                    remove_hook=lambda function,*_: self.registered.discard(function))
        self.adapter = types.SimpleNamespace(_mailbox=Path(self.temp.name), _session='test')
        sdk = types.SimpleNamespace(hooks=hooks, find_enum=lambda name: DPG,
                    make_struct=lambda _name, **kw: types.SimpleNamespace(**kw),
                    logging=types.SimpleNamespace(info=lambda *_:None, warning=lambda *_:None))
        modules = {'mods_base': types.SimpleNamespace(get_pc=lambda **_:self.pc), 'unrealsdk': sdk,
                   'unrealsdk.unreal': types.SimpleNamespace(WeakPointer=lambda obj:lambda:obj),
                   'blacklands_passthrough': self.adapter}
        self.modules = patch.dict(sys.modules, modules)
        self.modules.start()
        self.adapter.ao_key_trial = load('ao_key_trial_fg', MODS/'ao_key_trial.py')
        self.mod = load('foreground_trial_test', MODS/'foreground_trial.py')
        self.clock = patch.object(self.mod.time, 'monotonic', return_value=100.)
        self.now = self.clock.start()

    def tearDown(self):
        self.clock.stop()
        self.modules.stop()
        self.temp.cleanup()

    def test_foreground_then_key_then_full_restore(self):
        self.mod.start()
        self.now.return_value = 103.
        self.mod.on_frame()
        self.assertEqual((self.arms.DepthPriorityGroup, self.gun.DepthPriorityGroup), (2, 2))
        self.assertEqual(self.effect.OcclusionBias, 0.2)  # key not applied yet
        self.now.return_value = 106.
        self.mod.on_frame()
        self.assertEqual(self.effect.OcclusionBias, 1.0)
        self.assertEqual(self.effect.OcclusionColor.R, 1.0)
        self.now.return_value = 112.
        self.mod.on_frame()
        self.assertEqual((self.arms.DepthPriorityGroup, self.gun.DepthPriorityGroup), (1, 1))
        self.assertEqual((self.effect.OcclusionBias, self.effect.bAffectsLightingOnly), (0.2, True))
        self.assertFalse(self.registered)
        status = json.loads((Path(self.temp.name)/'blacklands_foreground_trial.json').read_text())
        self.assertTrue(status['restored'])
        self.assertEqual([h['phase'] for h in status['history']],
                         ['armed', 'foreground', 'foreground_keyed', 'finished'])

    def test_refuses_components_not_in_world_group(self):
        self.gun.DepthPriorityGroup = 2
        with self.assertRaises(RuntimeError): self.mod.start()
        self.assertEqual(self.arms.calls, [])
        self.assertFalse(self.registered)

    def test_partial_foreground_failure_restores_changed_component(self):
        self.gun.fail_value = 2
        self.mod.start()
        self.now.return_value = 103.
        self.mod.on_frame()
        self.assertEqual((self.arms.DepthPriorityGroup, self.gun.DepthPriorityGroup), (1, 1))
        self.assertIn('Synthetic', self.mod.report()['error'])
        self.assertFalse(self.registered)

    def test_failed_group_restore_keeps_hooks_and_retries(self):
        self.mod.start()
        self.now.return_value = 103.
        self.mod.on_frame()
        self.arms.fail_value = 1
        self.adapter._session = 'new'
        self.mod.on_frame()
        self.assertTrue(self.mod.report()['active'])
        self.assertEqual(len(self.registered), 2)
        self.assertEqual(self.gun.DepthPriorityGroup, 1)
        self.arms.fail_value = None
        self.mod.on_frame()
        self.assertEqual(self.arms.DepthPriorityGroup, 1)
        self.assertFalse(self.registered)

    def test_rejects_invalid_timing(self):
        with self.assertRaises(ValueError): self.mod.start(hold=0)
        with self.assertRaises(ValueError): self.mod.start(keyed=9)


if __name__ == '__main__':
    unittest.main()
