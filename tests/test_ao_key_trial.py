"""Synthetic lifecycle tests: AO field restoration safety, not proof of native rendering."""
import enum
import importlib.util
import json
from pathlib import Path
import sys
import tempfile
import types
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]


class DPG(enum.IntEnum):
    SDPG_World = 1
    SDPG_Foreground = 2
    SDPG_PostProcess = 4


class Effect:
    def __init__(self, cls='Engine.AmbientOcclusionEffect', dpg=1):
        self.Class = types.SimpleNamespace(_path_name=lambda: cls)
        self.SceneDPG = dpg
        self.bShowInGame = True
        self.OcclusionPower, self.OcclusionScale, self.OcclusionBias = 4.0, 20.0, 0.2
        self.MinOcclusion, self.OcclusionFadeoutMinDistance = 0.1, 0.0
        self.OcclusionFadeoutMaxDistance = 6000.0
        self.bAffectsLightingOnly = True
        self.OcclusionColor = types.SimpleNamespace(R=0.0, G=0.0, B=0.0, A=1.0)
        self.fail_restore = False

    def __setattr__(self, name, value):
        if name == 'OcclusionBias' and getattr(self, 'fail_restore', False) and value == 0.2:
            raise RuntimeError('Synthetic restore failure')
        object.__setattr__(self, name, value)

    def _path_name(self):
        return 'Transient.PostProcessChain_0:AmbientOcclusionEffect_0'


class AOKeyTrialTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(dir=ROOT/'work')
        self.effect = Effect()
        chain = types.SimpleNamespace(Effects=[Effect('Engine.UberPostProcessEffect', 4), self.effect])
        self.pc = types.SimpleNamespace(Pawn=object(), Player=types.SimpleNamespace(PlayerPostProcess=chain))
        self.registered = set()
        self.fail_hook = None
        def add(function, *_):
            if function != self.fail_hook:
                self.registered.add(function)
            return False  # installed SDK revision can insert and still return False
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
        spec = importlib.util.spec_from_file_location('ao_key_trial_test',
                    ROOT/'adapters/bl2/blacklands_passthrough/ao_key_trial.py')
        self.mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(self.mod)
        self.clock = patch.object(self.mod.time, 'monotonic', return_value=100.)
        self.now = self.clock.start()

    def tearDown(self):
        self.clock.stop()
        self.modules.stop()
        self.temp.cleanup()

    def assert_original(self):
        e = self.effect
        self.assertEqual((e.OcclusionBias, e.MinOcclusion, e.OcclusionScale, e.bAffectsLightingOnly),
                         (0.2, 0.1, 20.0, True))
        self.assertEqual((e.OcclusionColor.R, e.OcclusionColor.G), (0.0, 0.0))

    def test_steps_all_profiles_then_restores_and_unhooks(self):
        self.mod.start()
        seen = []
        for t in (103., 106., 109., 112.):
            self.now.return_value = t
            self.mod.on_frame()
            seen.append((self.effect.OcclusionBias, self.effect.MinOcclusion))
            self.assertFalse(self.effect.bAffectsLightingOnly)
            self.assertEqual((self.effect.OcclusionColor.R, self.effect.OcclusionColor.G), (1.0, 0.0))
        self.assertEqual(seen, [(1.0, 0.0), (1.0, 1.0), (-1.0, 0.0), (-1.0, 1.0)])
        self.now.return_value = 115.
        self.mod.on_frame()
        self.assert_original()
        self.assertFalse(self.registered)
        status = json.loads((Path(self.temp.name)/'blacklands_ao_key_trial.json').read_text())
        self.assertTrue(status['restored'])
        self.assertEqual(status['reason'], 'duration_complete')
        self.assertEqual(len([h for h in status['history'] if h['phase'] == 'profile']), 4)

    def test_registration_failure_changes_nothing(self):
        self.fail_hook = self.mod.HOOKS[1]
        with self.assertRaises(RuntimeError): self.mod.start()
        self.assertFalse(self.registered)
        self.assert_original()

    def test_failed_restore_retains_hooks_and_retries(self):
        self.mod.start()
        self.now.return_value = 103.
        self.mod.on_frame()
        self.effect.fail_restore = True
        self.adapter._session = 'new'
        self.mod.on_frame()
        self.assertTrue(self.mod.report()['active'])
        self.assertEqual(len(self.registered), 2)
        self.effect.fail_restore = False
        self.mod.on_frame()
        self.assert_original()
        self.assertFalse(self.registered)

    def test_external_change_during_delay_is_not_overwritten(self):
        self.mod.start()
        self.effect.OcclusionScale = 5.0
        self.now.return_value = 103.
        self.mod.on_frame()
        self.assertEqual(self.mod.report()['reason'], 'effect_changed_before_test')
        self.assertEqual(self.effect.OcclusionScale, 5.0)
        self.assertEqual(self.effect.OcclusionBias, 0.2)

    def test_refuses_when_no_world_group_ao_effect(self):
        self.effect.SceneDPG = 4
        with self.assertRaises(RuntimeError): self.mod.start()
        self.assertFalse(self.registered)

    def test_rejects_invalid_step_and_key(self):
        with self.assertRaises(ValueError): self.mod.start(step=4)
        with self.assertRaises(ValueError): self.mod.start(key=(0.0, -1.0, 0.0))


if __name__ == '__main__':
    unittest.main()
