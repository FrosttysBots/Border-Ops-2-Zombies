"""Synthetic SDK lifecycle plus actual Windows snapshot-sharing regression."""
import importlib.util
import json
import os
from pathlib import Path
import sys
import tempfile
import types
import unittest
from unittest.mock import patch

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'bridge'))
from record_player import read_player


class PlayerProbeTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory(dir=ROOT/'work')
        self.box=Path(self.temp.name);self.registered=set();self.fail_hook=None
        self.pc=types.SimpleNamespace(Pawn=object())
        self.adapter=types.ModuleType('blacklands_passthrough')
        self.adapter._mailbox=self.box;self.adapter._session='b'*32
        def add(fn,*_):
            if fn==self.fail_hook:return False
            self.registered.add(fn);return True
        self.sdk=types.SimpleNamespace(find_all=lambda *_:[],
            hooks=types.SimpleNamespace(Type=types.SimpleNamespace(POST=1),add_hook=add,
                  has_hook=lambda fn,*_:fn in self.registered,
                  remove_hook=lambda fn,*_:self.registered.discard(fn)),
            logging=types.SimpleNamespace(info=lambda *_:None,warning=lambda *_:None))
        modules={'blacklands_passthrough':self.adapter,'unrealsdk':self.sdk,
            'mods_base':types.SimpleNamespace(get_pc=lambda **_:self.pc),
            'blacklands_passthrough.player_state':types.SimpleNamespace(inspect_player=lambda _:dict(test=True),path=lambda _:'Object')}
        self.patch=patch.dict(sys.modules,modules);self.patch.start()
        spec=importlib.util.spec_from_file_location('blacklands_passthrough.player_probe',ROOT/'adapters/bl2/blacklands_passthrough/player_probe.py')
        self.mod=importlib.util.module_from_spec(spec);spec.loader.exec_module(self.mod)
        self.clock=patch.object(self.mod.time,'monotonic',return_value=100.);self.now=self.clock.start()
    def tearDown(self):
        self.clock.stop();self.patch.stop();self.temp.cleanup()
    def test_timeout_removes_both_hooks(self):
        self.mod.start();self.mod.on_frame();self.now.return_value=280.;self.mod.on_frame()
        self.assertFalse(self.registered);self.assertFalse(self.mod._state['active'])
        self.assertEqual(self.mod._state['reason'],'duration_complete')
    def test_registration_failure_cleans_up_partial_hooks(self):
        self.fail_hook=self.mod.HOOKS[1]
        with self.assertRaises(RuntimeError):self.mod.start()
        self.assertFalse(self.registered)
    def test_menu_failure_does_not_end_player_capture(self):
        self.mod.start()
        self.sdk.find_all=lambda *_:(_ for _ in ()).throw(ValueError('Missing menu class'))
        self.mod.on_frame()
        self.assertTrue(self.mod._state['active']);self.assertIsNone(self.mod._state['menus'])
        self.assertEqual(self.mod._state['player'],{'test':True})
    @unittest.skipUnless(os.name=='nt','Windows sharing semantics')
    def test_busy_reader_skips_snapshot_without_stopping_observer(self):
        self.mod.start()
        with (self.box/'blacklands_player.json').open('rb'):
            self.mod.on_frame()
        self.assertEqual(self.mod._state['write_skips'],1)
        self.assertTrue(self.mod._state['active']);self.assertEqual(self.mod._state['errors'],0)
        self.now.return_value=101.;self.mod.on_frame()
        packet=read_player(self.box/'blacklands_player.json')
        self.assertEqual(packet['write_skips'],1);self.assertEqual(packet['seq'],2)
    def test_session_change_stops_without_reusing_player(self):
        self.mod.start();self.adapter._session='c'*32;self.mod.on_frame()
        self.assertEqual(self.mod._state['reason'],'adapter_changed');self.assertFalse(self.registered)

    def test_false_return_after_successful_insert_uses_presence(self):
        real_add=self.sdk.hooks.add_hook
        self.sdk.hooks.add_hook=lambda *args:(real_add(*args),False)[1]
        self.mod.start();self.assertEqual(len(self.registered),2)
        self.mod._state=None;self.mod.stop();self.assertFalse(self.registered)


class PlayerReaderTests(unittest.TestCase):
    def test_reader_releases_handle_before_returning(self):
        with tempfile.TemporaryDirectory(dir=ROOT/'work') as tmp:
            target=Path(tmp)/'state.json'
            target.write_text(json.dumps(dict(schema=1,source='bl2_player',readonly=True,
                capture_id='a'*32,donor_session='b'*32,seq=1,active=True)))
            self.assertEqual(read_player(target)['seq'],1)
            replacement=Path(tmp)/'new.tmp';replacement.write_bytes(b'new');replacement.replace(target)
            self.assertEqual(target.read_bytes(),b'new')
