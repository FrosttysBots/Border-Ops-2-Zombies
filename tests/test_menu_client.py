"""Real temporary-mailbox exchange with a synthetic native-menu peer."""
from pathlib import Path
import sys
import tempfile
import threading
import time
import unittest
from unittest.mock import patch

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'bridge'))
from menu_client import open_inventory
from menu_wire import MenuGate, STATUS_FILE, REQUEST_FILE, read_packet, write_packet
import window_focus


class MenuClientTests(unittest.TestCase):
    def test_real_mailbox_handshake_observes_confirmation(self):
        with tempfile.TemporaryDirectory(dir=ROOT/'work') as directory:
            box=Path(directory); stop=threading.Event(); errors=[]; calls=[]
            def peer():
                gate=MenuGate('a'*32,'b'*32); seq=0; screens=[]
                def invoke(): calls.append('native_standin'); screens.append(3)
                try:
                    while not stop.is_set():
                        try:gate.submit(read_packet(box/REQUEST_FILE),int(time.time()*1000),time.monotonic(),screens,invoke)
                        except FileNotFoundError:pass
                        gate.observe(screens,time.monotonic()); seq+=1
                        write_packet(box/STATUS_FILE,dict(schema=1,source='bl2_menu_control',
                            activation=gate.activation,donor_session=gate.donor_session,seq=seq,
                            active=True,last_request=gate.last_request,result=gate.result))
                        stop.wait(.05)
                except Exception as exc:errors.append(exc)
            worker=threading.Thread(target=peer);worker.start()
            try:
                first=open_inventory(box)
                second=open_inventory(box)
                self.assertEqual(first['state'],'opened')
                self.assertEqual(second['state'],'already_open')
                self.assertEqual(len(calls),1)
            finally:stop.set();worker.join(2)
            self.assertFalse(errors)


class FocusTests(unittest.TestCase):
    def fake(self,foreground_pid,accept=True):
        class User:
            foreground=10
            def GetForegroundWindow(self):return self.foreground
        user=User(); calls=[]
        def activate(target):
            calls.append(target)
            if accept:user.foreground=target
            return accept
        user.SetForegroundWindow=activate
        return user,calls

    def run_focus(self,foreground_pid,accept=True):
        user,calls=self.fake(foreground_pid,accept)
        with patch.object(window_focus,'window_api',return_value=(user,None)), \
             patch.object(window_focus,'find_game_window',side_effect=lambda u,k,s:(20,200) if s=='bl2' else (30,300)), \
             patch.object(window_focus,'owner',return_value=(foreground_pid,'name')):
            result=window_focus.focus_game('bl2')
        return result,calls

    def test_other_application_never_loses_focus(self):
        result,calls=self.run_focus(999999)
        self.assertFalse(result['success']);self.assertFalse(calls)

    def test_success_requires_actual_foreground(self):
        result,calls=self.run_focus(300)
        self.assertTrue(result['success']);self.assertEqual(calls,[20])

    def test_windows_refusal_is_reported_without_repeated_attempts(self):
        result,calls=self.run_focus(300,False)
        self.assertFalse(result['success']);self.assertEqual(calls,[20])
