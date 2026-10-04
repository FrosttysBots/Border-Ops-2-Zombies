"""Synthetic lifecycle tests: restoration safety, not proof of native rendering."""
import importlib.util
from pathlib import Path
import sys
import tempfile
import types
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]


class Viewport:
    def __init__(self):
        self.value = False
        self.fail_restore = False
        self.writes = []

    def _path_name(self):
        return 'Test.Viewport'

    @property
    def bDisableWorldRendering(self):
        return self.value

    @bDisableWorldRendering.setter
    def bDisableWorldRendering(self, value):
        if not value and self.fail_restore:
            raise RuntimeError('Synthetic restore failure')
        self.writes.append(value)
        self.value = value


class RenderTrialTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(dir=ROOT/'work')
        self.viewport = Viewport()
        self.pc = types.SimpleNamespace(Pawn=object(), Player=types.SimpleNamespace(ViewportClient=self.viewport))
        self.registered = set()
        self.fail_hook = None
        def add(function, *_):
            if function == self.fail_hook: return False
            self.registered.add(function)
            return True
        hooks = types.SimpleNamespace(Type=types.SimpleNamespace(POST=1), add_hook=add,
                    remove_hook=lambda function,*_: self.registered.discard(function))
        self.adapter = types.SimpleNamespace(_mailbox=Path(self.temp.name), _session='test')
        modules = {'mods_base': types.SimpleNamespace(get_pc=lambda **_:self.pc),
                   'unrealsdk':types.SimpleNamespace(hooks=hooks,logging=types.SimpleNamespace(info=lambda *_:None,warning=lambda *_:None)),
                   'unrealsdk.unreal':types.SimpleNamespace(WeakPointer=lambda obj:lambda:obj),
                   'blacklands_passthrough':self.adapter}
        self.modules = patch.dict(sys.modules, modules)
        self.modules.start()
        spec = importlib.util.spec_from_file_location('render_trial_test', ROOT/'adapters/bl2/blacklands_passthrough/render_trial.py')
        self.mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(self.mod)
        self.clock = patch.object(self.mod.time,'monotonic',return_value=100.)
        self.now = self.clock.start()

    def tearDown(self):
        self.clock.stop()
        self.modules.stop()
        self.temp.cleanup()

    def apply(self):
        self.mod.start()
        self.now.return_value=103.
        self.mod.on_frame()
        self.assertTrue(self.viewport.value)

    def test_restores_original_after_deadline_and_removes_hooks(self):
        self.apply()
        self.now.return_value=115.
        self.mod.on_frame()
        self.assertFalse(self.viewport.value)
        self.assertFalse(self.registered)
        self.assertTrue(self.mod.report()['restored'])
        self.assertEqual(self.mod.report()['reason'],'duration_complete')

    def test_existing_disabled_flag_is_never_changed(self):
        self.viewport.value=True
        with self.assertRaises(RuntimeError):self.mod.start()
        self.assertEqual(self.viewport.writes,[])
        self.assertFalse(self.registered)

    def test_partial_registration_failure_never_changes_rendering(self):
        self.fail_hook=self.mod.HOOKS[1]
        with self.assertRaises(RuntimeError):self.mod.start()
        self.assertFalse(self.registered)
        self.assertEqual(self.viewport.writes,[])

    def test_adapter_restart_restores_immediately(self):
        self.apply()
        self.adapter._session='new'
        self.mod.on_frame()
        self.assertFalse(self.viewport.value)
        self.assertEqual(self.mod.report()['reason'],'adapter_changed')

    def test_failed_restoration_retains_hooks_and_retries(self):
        self.apply()
        self.viewport.fail_restore=True
        self.now.return_value=115.
        self.mod.on_frame()
        self.assertTrue(self.mod.report()['active'])
        self.assertEqual(len(self.registered),2)
        self.viewport.fail_restore=False
        self.mod.on_frame()
        self.assertFalse(self.viewport.value)
        self.assertTrue(self.mod.report()['restored'])

    def test_external_change_during_delay_is_not_overwritten(self):
        self.mod.start()
        self.viewport.value=True
        self.now.return_value=103.
        self.mod.on_frame()
        self.assertTrue(self.viewport.value)
        self.assertEqual(self.viewport.writes,[])
        self.assertFalse(self.registered)


if __name__ == '__main__':
    unittest.main()
