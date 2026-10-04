"""Protocol tests with localhost sockets, not live game evidence."""
import json
from pathlib import Path
import socket
import sys
import tempfile
import unittest

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'bridge'))
from runtime_ipc import Publisher, read_endpoint


class RuntimeProtocolTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory(dir=ROOT/'work')
        self.receiver=socket.socket(socket.AF_INET,socket.SOCK_DGRAM)
        self.receiver.bind(('127.0.0.1',0));self.receiver.settimeout(1)
        self.path=Path(self.temp.name)/'endpoint.json'
        self.endpoint=dict(schema=1,transport='udp_loopback',host='127.0.0.1',
                           port=self.receiver.getsockname()[1],epoch='a'*32,token='b'*32,
                           capabilities=['bl2_pose_readonly'],max_bytes=8192)
        self.path.write_text(json.dumps(self.endpoint))
        self.publisher=Publisher(self.path,origin='synthetic_test')

    def tearDown(self):
        self.publisher.close();self.receiver.close();self.temp.cleanup()

    def packet(self):
        self.publisher.send([1,2,3],[0,0,0],None)
        raw,addr=self.receiver.recvfrom(8192)
        return json.loads(raw),addr

    def ack(self,packet,addr,**changes):
        ack={k:packet[k] for k in ('schema','epoch','session','seq','sent_us')}
        ack.update(kind='ack');ack.update(changes)
        self.receiver.sendto(json.dumps(ack).encode(),addr)
        # Select makes the test deterministic without adding waits to the publisher.
        import select
        select.select([self.publisher.socket],[],[],1)
        self.publisher.poll()

    def test_rejects_remote_or_command_capable_endpoint(self):
        for change in ({'host':'192.0.2.1'},{'capabilities':['damage']},{'port':True},{'schema':2}):
            self.path.write_text(json.dumps(self.endpoint|change))
            with self.assertRaises(ValueError):read_endpoint(self.path)

    def test_two_advancing_acknowledgements_required_and_closed_is_offline(self):
        p,addr=self.packet();self.ack(p,addr)
        self.assertFalse(self.publisher.status()['online'])
        p,addr=self.packet();self.ack(p,addr)
        self.assertTrue(self.publisher.status()['online'])
        self.publisher.close();self.assertFalse(self.publisher.status()['online'])

    def test_old_session_wrong_timestamp_and_unsent_ack_are_ignored(self):
        p,addr=self.packet()
        for change in ({'session':'c'*32},{'sent_us':p['sent_us']+1},{'seq':999},{'kind':'fire'}):
            self.ack(p,addr,**change)
            self.assertEqual(self.publisher.ack_count,0)
        self.ack(p,addr);self.ack(p,addr)
        self.assertEqual(self.publisher.ack_count,1)

    def test_nonfinite_coordinates_are_not_sent(self):
        for coords in ([float('nan'),0,0],[True,0,0],[1,2]):
            with self.assertRaises(ValueError):self.publisher.send(coords,[0,0,0],None)
