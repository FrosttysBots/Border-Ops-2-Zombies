"""Synthetic lifecycle tests: owned-chain removal safety, not proof of native rendering."""
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


class Native:
    def __init__(self, name):
        self.Name = name
        self.Effects = []
        self.EffectName = 'None'


class LocalPlayer:
    def __init__(self):
        self.PlayerPostProcessChains = [Native('PostProcessChain_0')]
        self.fail_insert = False
        self.fail_remove = False
        self.clone = False
        self.calls = []

    def _path_name(self):
        return 'Test.LocalPlayer'

    def InsertPostProcessingChain(self, chain, index, clone):
        self.calls.append(('insert', index, clone))
        if self.fail_insert:
            return False
        if self.clone:  # live BL2 inserted a renamed copy with same-named effects
            copy = Native('PostProcessChain_9'); copy.Effects = list(chain.Effects)
            chain = copy
        self.PlayerPostProcessChains.append(chain)
        return True

    def RemovePostProcessingChain(self, index):
        self.calls.append(('remove', index))
        if self.fail_remove:
            raise RuntimeError('Synthetic removal failure')
        del self.PlayerPostProcessChains[index]
        return True


class DPG(enum.IntEnum):
    SDPG_UnrealEdBackground = 0
    SDPG_World = 1
    SDPG_Foreground = 2


class PostProcessTrialTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(dir=ROOT/'work')
        self.player = LocalPlayer()
        self.pc = types.SimpleNamespace(Pawn=object(), Player=self.player)
        self.registered = set()
        self.fail_hook = None
        def add(function, *_):
            if function != self.fail_hook:
                self.registered.add(function)
            return False  # installed SDK revision can insert and still return False
        hooks = types.SimpleNamespace(Type=types.SimpleNamespace(POST=1), add_hook=add,
                    has_hook=lambda function,*_: function in self.registered,
                    remove_hook=lambda function,*_: self.registered.discard(function))
        self.constructed = []
        def construct(cls, outer, name):
            obj = Native(name); obj.cls = cls; obj.outer = outer
            self.constructed.append(obj)
            return obj
        self.adapter = types.SimpleNamespace(_mailbox=Path(self.temp.name), _session='test')
        sdk = types.SimpleNamespace(hooks=hooks, construct_object=construct,
                    find_enum=lambda name: DPG,
                    make_struct=lambda _name, **kw: types.SimpleNamespace(**kw),
                    logging=types.SimpleNamespace(info=lambda *_:None, warning=lambda *_:None))
        modules = {'mods_base': types.SimpleNamespace(get_pc=lambda **_:self.pc),
                   'unrealsdk': sdk,
                   'unrealsdk.unreal': types.SimpleNamespace(WeakPointer=lambda obj:lambda:obj),
                   'blacklands_passthrough': self.adapter}
        self.modules = patch.dict(sys.modules, modules)
        self.modules.start()
        spec = importlib.util.spec_from_file_location('postprocess_trial_test',
                    ROOT/'adapters/bl2/blacklands_passthrough/postprocess_trial.py')
        self.mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(self.mod)
        self.clock = patch.object(self.mod.time, 'monotonic', return_value=100.)
        self.now = self.clock.start()

    def tearDown(self):
        self.clock.stop()
        self.modules.stop()
        self.temp.cleanup()

    def owned(self):
        return [c for c in self.player.PlayerPostProcessChains if self.mod.is_owned(c)]

    def apply(self):
        self.mod.start()
        self.now.return_value = 103.
        self.mod.on_frame()
        self.assertEqual(len(self.owned()), 1)

    def test_applies_world_group_effect_then_removes_only_owned_chain(self):
        self.apply()
        effect = self.owned()[0].Effects[0]
        self.assertEqual(effect.SceneDPG, DPG.SDPG_World)
        self.assertEqual(self.mod.report()['effect_readback']['SceneDPG'], 1)
        self.assertEqual(self.mod.report()['effect_readback']['SceneColorize'], [1.0, 0.0, 1.0])
        self.assertIn(('insert', -1, False), self.player.calls)
        self.now.return_value = 115.
        self.mod.on_frame()
        self.assertEqual([c.Name for c in self.player.PlayerPostProcessChains], ['PostProcessChain_0'])
        self.assertFalse(self.registered)
        status = json.loads((Path(self.temp.name)/'blacklands_postprocess_trial.json').read_text())
        self.assertTrue(status['restored'])
        self.assertEqual(status['reason'], 'duration_complete')

    def test_nothing_is_constructed_during_delay_or_on_registration_failure(self):
        self.fail_hook = self.mod.HOOKS[1]
        with self.assertRaises(RuntimeError): self.mod.start()
        self.assertFalse(self.registered)
        self.assertEqual(self.constructed, [])
        self.assertEqual(self.player.calls, [])

    def test_failed_removal_retains_hooks_and_retries(self):
        self.apply()
        self.player.fail_remove = True
        self.now.return_value = 115.
        self.mod.on_frame()
        self.assertTrue(self.mod.report()['active'])
        self.assertEqual(len(self.registered), 2)
        self.player.fail_remove = False
        self.mod.on_frame()
        self.assertEqual(self.owned(), [])
        self.assertTrue(self.mod.report()['restored'])
        self.assertFalse(self.registered)

    def test_failed_insertion_cleans_up_and_reports_error(self):
        self.player.fail_insert = True
        self.mod.start()
        self.now.return_value = 103.
        self.mod.on_frame()
        self.assertEqual(self.owned(), [])
        self.assertFalse(self.mod.report()['active'])
        self.assertIn('insertion', self.mod.report()['error'])
        self.assertFalse(self.registered)

    def test_external_chain_change_during_delay_is_not_touched(self):
        self.mod.start()
        self.player.PlayerPostProcessChains.append(Native('OtherModChain'))
        self.now.return_value = 103.
        self.mod.on_frame()
        self.assertEqual(self.mod.report()['reason'], 'chains_changed_before_test')
        self.assertEqual([c.Name for c in self.player.PlayerPostProcessChains],
                         ['PostProcessChain_0', 'OtherModChain'])
        self.assertEqual(self.constructed, [])

    def test_adapter_restart_removes_chain_immediately(self):
        self.apply()
        self.adapter._session = 'new'
        self.mod.on_frame()
        self.assertEqual(self.owned(), [])
        self.assertEqual(self.mod.report()['reason'], 'adapter_changed')

    def test_recover_removes_orphaned_owned_chain_after_state_loss(self):
        self.apply()
        self.player.PlayerPostProcessChains.insert(0, Native('OtherModChain'))
        self.mod._state = None
        self.assertEqual(self.mod.recover(), 1)
        self.assertEqual([c.Name for c in self.player.PlayerPostProcessChains],
                         ['OtherModChain', 'PostProcessChain_0'])
        self.assertFalse(self.registered)

    def test_renamed_clone_from_native_insert_is_found_and_removed(self):
        self.player.clone = True
        self.apply()
        self.assertEqual(self.owned()[0].Name, 'PostProcessChain_9')
        self.now.return_value = 115.
        self.mod.on_frame()
        self.assertEqual([c.Name for c in self.player.PlayerPostProcessChains], ['PostProcessChain_0'])
        self.assertTrue(self.mod.report()['restored'])

    def test_recover_removes_leftover_clones_but_not_other_chains(self):
        for name in ('PostProcessChain_7', 'PostProcessChain_8'):
            leftover = Native(name); leftover.Effects = [Native(self.mod.EFFECT_NAME)]
            self.player.PlayerPostProcessChains.append(leftover)
        other = Native('OtherModChain'); other.Effects = [Native('UberPostProcessEffect_0')]
        self.player.PlayerPostProcessChains.append(other)
        self.assertEqual(self.mod.recover(), 2)
        self.assertEqual([c.Name for c in self.player.PlayerPostProcessChains],
                         ['PostProcessChain_0', 'OtherModChain'])

    def test_rejects_invalid_key_and_duration(self):
        with self.assertRaises(ValueError): self.mod.start(seconds=16)
        with self.assertRaises(ValueError): self.mod.start(key=(1.0, 2.0, 0.0))
        self.assertEqual(self.player.calls, [])


if __name__ == '__main__':
    unittest.main()
