import copy
import json
from pathlib import Path
import socket
import ssl
import struct
import tempfile
import threading
import time
import unittest
from contextlib import contextmanager
from unittest.mock import patch

import monitor as m
import peer_transport as t
import sync
from scripts.configure_sync import pair


class TransportTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmp=tempfile.TemporaryDirectory(); cls.base=Path(cls.tmp.name)
        cls.one=cls.base/'one'; cls.two=cls.base/'two'; cls.stranger=cls.base/'stranger'
        cls.ids=[t.identity(cls.one,'Mini-One'),t.identity(cls.two,'Mini-Two'),t.identity(cls.stranger,'Mini-Two')]
        pair(cls.one,'Mini-One',cls.ids[1],cls.ids[1]['fingerprint'])
        pair(cls.two,'Mini-Two',cls.ids[0],cls.ids[0]['fingerprint'])
        pair(cls.stranger,'Mini-Two',cls.ids[0],cls.ids[0]['fingerprint'])
    @classmethod
    def tearDownClass(cls): cls.tmp.cleanup()

    def connection(self, client, action, no_certificate=False):

        left,right=socket.socketpair(); left.settimeout(2); right.settimeout(2)
        errors=[]
        def server():
            try:
                with t.context(self.one,server=True).wrap_socket(left,server_side=True) as sock:
                    t.check_peer(sock,self.one); t.handle(sock,self.one,sync.read(self.one/'config.json'))
            except Exception as exc: errors.append(exc)
            finally: left.close()
        thread=threading.Thread(target=server); thread.start()
        try:
            if no_certificate:
                ctx=ssl.create_default_context(cafile=str(self.one/'keys/certificate.pem'))
            else: ctx=t.context(client)
            with ctx.wrap_socket(right,server_hostname='Mini-One.local') as sock:
                t.check_peer(sock,client); result=action(sock)
        finally:
            right.close(); thread.join(3)
        self.assertFalse(thread.is_alive())
        return result,errors

    def test_mutual_authentication_and_exact_pin(self):
        result,errors=self.connection(self.two,lambda s:(t.frame(s,{'op':'received'}),t.receive(s))[1])
        self.assertTrue(result['ok']); self.assertEqual(errors,[])
        class Fake:
            def getpeercert(self,**_): return b'other certificate'
        with self.assertRaises(ssl.SSLError): t.check_peer(Fake(),self.one)

    def test_unpaired_and_missing_client_certificates_rejected(self):
        for client,no_cert in ((self.stranger,False),(self.two,True)):
            with self.subTest(no_cert=no_cert):
                with self.assertRaises((ssl.SSLError,OSError,ValueError)):
                    self.connection(client,lambda s:(t.frame(s,{'op':'received'}),t.receive(s)),no_cert)

    def test_bounded_frames_and_incomplete_input(self):
        a,b=socket.socketpair()
        try:
            a.sendall(struct.pack('!I',t.MAX_FRAME+1))
            with self.assertRaises(ValueError): t.receive(b)
            a.sendall(struct.pack('!I',10)+b'{}'); a.shutdown(socket.SHUT_WR)
            with self.assertRaises(ValueError): t.receive(b)
        finally: a.close(); b.close()

    def test_public_pairing_requires_trusted_fingerprint(self):
        with self.assertRaises(ValueError): pair(self.one,'Mini-One',self.ids[1],'0'*64)
        self.assertFalse(sync.read(self.one/'config.json')['enabled'])
        self.assertEqual((self.one/'keys/private.pem').stat().st_mode & 0o777,0o600)

    def test_publication_and_corruption_preserve_last_cache(self):
        with tempfile.TemporaryDirectory() as temp:
            data=Path(temp); now=time.time()-1
            config={**m.DEFAULT,'satellites':[]}
            checks=[dict(s,ok=True,started_at=m.stamp(now),latency_ms=10,detail='fixture') for s in m.specs(config)]
            sample=dict(started_at=m.stamp(now),finished_at=m.stamp(now+.1),checks=checks,
                        host={'hostname':'Mini-Two'},interval_seconds=15,network={'interface':'en1'})
            detector=m.Detector(config); detector.update(sample)
            sync.save(data/'state.json',detector.state); m.journals(data)[0].append(sample)
            manifest=sync.publish(data,self.two,host='Mini-Two')
            payloads=[(self.two/'outbox'/f['name']).read_bytes() for f in manifest['files']]
            def send(sock, value, corrupt=False):
                t.frame(sock,dict(op='publish',manifest=value,offsets={f['name']:0 for f in value['files']}))
                for p in payloads: sock.sendall(b'x'+p[1:] if corrupt else p)
                return t.receive(sock)
            result,errors=self.connection(self.two,lambda sock:send(sock,manifest))
            self.assertTrue(result['ok']); self.assertFalse(errors)
            before=sync.read(self.one/'peer/current.json')
            bad=copy.deepcopy(manifest); bad['sequence']+=1
            with self.assertRaises((ValueError,OSError)):
                self.connection(self.two,lambda sock:send(sock,bad,True))
            self.assertEqual(before,sync.read(self.one/'peer/current.json'))
            self.assertFalse((self.one/'incoming').exists())

    def test_bidirectional_exchange_over_mutually_authenticated_tls(self):
        with tempfile.TemporaryDirectory() as temp:
            base=Path(temp); one=base/'one'; two=base/'two'
            first=t.identity(one,'Mini-One'); second=t.identity(two,'Mini-Two')
            pair(one,'Mini-One',second,second['fingerprint']); pair(two,'Mini-Two',first,first['fingerprint'])
            c=sync.read(two/'config.json'); c['enabled']=True; sync.save(two/'config.json',c)
            now=time.time()-1
            for host,root in (('Mini-One',one),('Mini-Two',two)):
                data=base/host; data.mkdir()
                config={**m.DEFAULT,'satellites':[]}
                checks=[dict(s,ok=True,started_at=m.stamp(now),latency_ms=10 if host=='Mini-One' else 20,detail='fixture') for s in m.specs(config)]
                sample=dict(started_at=m.stamp(now),finished_at=m.stamp(now+.1),checks=checks,host={'hostname':host},interval_seconds=15,network={'interface':'en0' if host=='Mini-One' else 'en1'})
                detector=m.Detector(config); detector.update(sample)
                sync.save(data/'state.json',detector.state); m.journals(data)[0].append(sample)
                sync.publish(data,root,host=host)
            errors=[]; connections=[]
            @contextmanager
            def connection(root,config):
                left,right=socket.socketpair(); left.settimeout(2); right.settimeout(2)
                def server():
                    try:
                        with t.context(one,server=True).wrap_socket(left,server_side=True) as sock:
                            t.check_peer(sock,one); t.handle(sock,one,sync.read(one/'config.json'))
                    except Exception as error: errors.append(error)
                    finally: left.close()
                worker=threading.Thread(target=server); worker.start()
                try:
                    with t.context(root).wrap_socket(right,server_hostname='Mini-One.local') as sock:
                        t.check_peer(sock,root); connections.append(sock.version()); yield sock
                finally:
                    right.close(); worker.join(3)
                    self.assertFalse(worker.is_alive())
            with patch.object(t,'connect',side_effect=connection): t.exchange(two)
            self.assertFalse(errors); self.assertTrue(all(v=='TLSv1.3' for v in connections))
            for root,expected,latency in ((one,'Mini-Two',20),(two,'Mini-One',10)):
                brief=sync.peer_briefing(root,1,time.time())
                self.assertEqual(brief['host']['hostname'],expected)
                self.assertFalse(brief['recorder']['stale'])
                self.assertEqual(brief['observed_samples'],1)
                peer=sync.current_peer(root)
                row=json.loads(next(peer.glob('samples-*.jsonl')).read_text().splitlines()[0])
                self.assertEqual(row['cloudflare'],latency)

    def test_path_traversal_and_controls_not_exposed(self):
        for request in ({'op':'read','name':'../keys/private.pem','offset':0,'length':100},{'op':'stop'}):
            with self.assertRaises((ValueError,OSError)):
                self.connection(self.two,lambda s:(t.frame(s,request),t.receive(s)))

if __name__=='__main__': unittest.main()
