import importlib.util
import json
from pathlib import Path
import sys
import tempfile
import types
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT/'bridge'))
import menu_wire
from menu_wire import MenuGate, validate_request, validate_status
from menu_client import StatusTracker


def request(seq=1, **changes):
    return dict(schema=1, activation='a'*32, donor_session='b'*32, seq=seq,
                action='open_inventory', created_ms=10000, expires_ms=12000) | changes


class MenuGateTests(unittest.TestCase):
    def setUp(self):
        self.gate = MenuGate('a'*32, 'b'*32)
        self.calls = 0

    def invoke(self): self.calls += 1

    def test_duplicate_and_delayed_ack_invoke_only_once(self):
        for _ in range(5): self.gate.submit(request(), 10000, 0, [], self.invoke)
        self.assertEqual(self.calls, 1)
        self.assertEqual(self.gate.result['state'], 'awaiting_menu')
        self.gate.observe([3], .2)
        self.gate.submit(request(), 11000, 1, [], self.invoke)
        self.assertEqual(self.calls, 1)
        self.assertEqual(self.gate.result['state'], 'opened')

    def test_expired_request_does_not_invoke(self):
        self.gate.submit(request(), 12001, 0, [], self.invoke)
        self.assertEqual(self.calls, 0)
        self.assertEqual(self.gate.result['state'], 'expired')

    def test_old_activation_wrong_donor_unknown_action_extra_fields_rejected(self):
        for changes in [dict(activation='c'*32), dict(donor_session='c'*32),
                        dict(action='exec'), dict(code='anything'), dict(seq=True),
                        dict(seq=129), dict(expires_ms=15000), dict(created_ms=20000),
                        dict(schema=True)]:
            with self.subTest(changes=changes), self.assertRaises(ValueError):
                self.gate.submit(request(**changes), 10000, 0, [], self.invoke)
        self.assertEqual(self.calls, 0)

    def test_already_open_never_toggles_menu(self):
        self.gate.submit(request(), 10000, 0, [3], self.invoke)
        self.assertEqual(self.calls, 0)
        self.assertEqual(self.gate.result['state'], 'already_open')

    def test_other_tab_does_not_call_inventory_toggle(self):
        self.gate.submit(request(), 10000, 0, [5], self.invoke)
        self.assertEqual(self.gate.result['state'], 'other_menu_open')
        self.assertEqual(self.calls, 0)

    def test_native_error_is_not_reinvoked(self):
        def fails(): self.invoke(); raise RuntimeError('native failure')
        self.gate.submit(request(), 10000, 0, [], fails)
        self.gate.submit(request(), 10000, 1, [], fails)
        self.assertEqual(self.calls, 1)
        self.assertEqual(self.gate.result['state'], 'native_error')

    def test_unconfirmed_timeout_no_retry(self):
        self.gate.submit(request(), 10000, 0, [], self.invoke)
        self.gate.observe([], 3)
        self.assertEqual(self.gate.result['state'], 'unconfirmed')
        self.gate.submit(request(), 11000, 3, [], self.invoke)
        self.assertEqual(self.calls, 1)

    def test_pending_request_cannot_be_replaced(self):
        self.gate.submit(request(), 10000, 0, [], self.invoke)
        self.gate.submit(request(2), 10000, .2, [], self.invoke)
        self.assertEqual(self.gate.last_request, 1)
        self.gate.cancel()
        self.assertEqual(self.gate.result['state'], 'cancelled')

    def test_skipped_sequence_is_rejected(self):
        with self.assertRaises(ValueError): self.gate.submit(request(2), 10000, 0, [], self.invoke)


class MenuStatusTests(unittest.TestCase):
    def packet(self, seq=1, **changes):
        return dict(schema=1, source='bl2_menu_control', activation='a'*32,
                    donor_session='b'*32, seq=seq, last_request=0, active=True) | changes

    def test_stale_status_and_restart_require_progress(self):
        tracker = StatusTracker()
        self.assertFalse(tracker.observe(self.packet(), 0))
        self.assertTrue(tracker.observe(self.packet(2), .1))
        self.assertFalse(tracker.observe(self.packet(2), 2))
        self.assertFalse(tracker.observe(self.packet(1, activation='c'*32), 2.1))
        self.assertFalse(tracker.observe(self.packet(2, activation='c'*32, active=False), 2.2))

    def test_bounded_packet_object(self):
        with tempfile.TemporaryDirectory(dir=ROOT/'work') as directory:
            path = Path(directory)/'status.json'
            for data in ['[]', ' ' * 8193]:
                path.write_text(data)
                with self.assertRaises(ValueError): menu_wire.read_packet(path)


class MenuAdapterTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(dir=ROOT/'work')
        self.box = Path(self.temp.name); self.registered = set(); self.screens = []; self.calls = 0
        self.fail_hook = None
        self.pc = types.SimpleNamespace(Pawn=object(), ShowStatusMenu_Inventory=self.invoke)
        self.adapter = types.ModuleType('blacklands_passthrough')
        self.adapter._mailbox = self.box; self.adapter._session = 'b'*32
        def add(fn, *_):
            if fn == self.fail_hook: return False
            self.registered.add(fn); return True
        sdk = types.SimpleNamespace(hooks=types.SimpleNamespace(Type=types.SimpleNamespace(POST=1),
                    has_hook=lambda fn,*_:fn in self.registered,
                    add_hook=add, remove_hook=lambda fn, *_: self.registered.discard(fn)),
                    logging=types.SimpleNamespace(info=lambda *_:None, warning=lambda *_:None))
        modules = {'blacklands_passthrough':self.adapter, 'unrealsdk':sdk,
                   'mods_base':types.SimpleNamespace(get_pc=lambda **_:self.pc),
                   'blacklands_passthrough.menu_wire':menu_wire,
                   'blacklands_passthrough.player_probe':types.SimpleNamespace(menus=lambda:[dict(screen=s) for s in self.screens])}
        self.modules = patch.dict(sys.modules, modules); self.modules.start()
        spec = importlib.util.spec_from_file_location('blacklands_passthrough.menu_control',
                       ROOT/'adapters/bl2/blacklands_passthrough/menu_control.py')
        self.mod = importlib.util.module_from_spec(spec); spec.loader.exec_module(self.mod)
        self.clock = patch.object(self.mod.time, 'monotonic', return_value=100.); self.now = self.clock.start()
        self.wall = patch.object(self.mod.time, 'time', return_value=10.); self.wall.start()

    def tearDown(self):
        self.clock.stop(); self.wall.stop(); self.modules.stop(); self.temp.cleanup()

    def invoke(self): self.calls += 1

    def test_native_request_confirmed_on_later_tick(self):
        self.mod.start()
        packet = request(activation=self.mod._state['gate'].activation)
        menu_wire.write_packet(self.box/menu_wire.REQUEST_FILE, packet)
        self.mod.on_frame(); self.assertEqual(self.calls, 1)
        self.screens = [3]; self.now.return_value = 100.2; self.mod.on_frame()
        final = menu_wire.read_packet(self.box/menu_wire.STATUS_FILE)
        self.assertEqual(final['result']['state'], 'opened'); self.assertEqual(self.calls, 1)

    def test_deadline_and_restart_remove_hooks(self):
        for changed in (False, True):
            self.adapter._session='b'*32; self.now.return_value=100.; self.mod.start()
            if changed: self.adapter._session='c'*32
            else: self.now.return_value=280.
            self.mod.on_frame()
            self.assertFalse(self.registered); self.assertFalse(self.mod._state['active'])

    def test_partial_registration_cleanup(self):
        self.fail_hook=self.mod.HOOKS[1]
        with self.assertRaises(RuntimeError):self.mod.start()
        self.assertFalse(self.registered)

    def test_busy_ack_does_not_repeat_native_call(self):
        self.mod.start()
        menu_wire.write_packet(self.box/menu_wire.REQUEST_FILE,
                               request(activation=self.mod._state['gate'].activation))
        with patch.object(self.mod, 'write_packet', return_value=False):
            self.mod.on_frame(); self.now.return_value=100.2; self.mod.on_frame()
        self.assertEqual(self.calls, 1); self.assertEqual(self.mod._state['write_skips'], 2)

    def test_false_return_after_insert_and_lost_state_cleanup(self):
        real_add=self.mod.hooks.add_hook
        self.mod.hooks.add_hook=lambda *args:(real_add(*args),False)[1]
        self.mod.start();self.assertEqual(len(self.registered),2)
        self.mod._state=None;self.mod.stop();self.assertFalse(self.registered)
