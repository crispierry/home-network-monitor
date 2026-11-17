import copy
import json
from pathlib import Path
import tempfile
import time
import unittest
import threading
from unittest.mock import patch

import monitor as m
import sync

class ExchangeTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory(); self.root=Path(self.tmp.name)
        self.data=self.root/'data'; self.data.mkdir()
        self.source=self.root/'source'; self.peer=self.root/'peer'
        self.now=time.time()
        c={**m.DEFAULT,'satellites':[]}
        checks=[dict(s,ok=True,started_at=m.stamp(self.now),latency_ms=10,detail='fixture') for s in m.specs(c)]
        self.sample=dict(started_at=m.stamp(self.now),finished_at=m.stamp(self.now+.1),checks=checks,
                         host={'hostname':'Mini-One'},interval_seconds=15,network={'interface':'en0'})
        detector=m.Detector(c); detector.update(self.sample)
        m.atomic(self.data/'state.json',json.dumps(detector.state))
        m.journals(self.data)[0].append(self.sample)
        self.manifest=sync.publish(self.data,self.source,host='Mini-One',now=self.now+1)
    def tearDown(self): self.tmp.cleanup()
    def transfer(self):
        return sync.transfer(self.source/'outbox',self.peer,self.manifest['host_id'],'Mini-One',now=self.now+3)
    def current(self): return self.peer/sync.read(self.peer/'current.json')['directory']
    def test_roundtrip_duplicate_and_incremental(self):
        self.transfer(); first=self.current()
        self.assertTrue(self.transfer()['unchanged'])
        self.assertEqual(self.current(),first)
        m.journals(self.data)[0].append(self.sample)
        sync.publish(self.data,self.source,host='Mini-One',now=self.now+2)
        self.transfer(); self.assertNotEqual(self.current(),first)
        self.assertFalse(first.exists())
        rows=list(self.current().glob('samples-*.jsonl'))
        self.assertEqual(sum(len(p.read_text().splitlines()) for p in rows),2)
    def test_wrong_peer_path_oversize_future_and_replay(self):
        original=copy.deepcopy(self.manifest)
        for mutate in (lambda x:x.update(host_id='0'*32),
                       lambda x:x['files'][0].update(name='../state.json'),
                       lambda x:x['files'][0].update(size=sync.MAX_FILE+1),
                       lambda x:x.update(published_at=self.now+100),
                       lambda x:x['files'].append(x['files'][0])):
            value=copy.deepcopy(original); mutate(value)
            with self.assertRaises(ValueError): sync.validate_manifest(value,original['host_id'],'Mini-One',self.now+3)
        self.transfer()
        value=copy.deepcopy(original); value['sequence']=0
        sync.save(self.source/'outbox/manifest.json',value)
        with self.assertRaises(ValueError): self.transfer()
    def test_corruption_preserves_last_good(self):
        self.transfer(); before=sync.read(self.peer/'current.json')
        sync.publish(self.data,self.source,host='Mini-One',now=self.now+2)
        manifest=sync.read(self.source/'outbox/manifest.json')
        manifest['files'][0]['sha256']='0'*64
        sync.save(self.source/'outbox/manifest.json',manifest)
        with self.assertRaises(ValueError): self.transfer()
        self.assertEqual(sync.read(self.peer/'current.json'),before)
        self.assertFalse((self.peer/'staging').exists())
    def test_symlink_and_pointer_traversal_refused(self):
        outside=self.root/'outside'; outside.mkdir()
        sync.save(self.peer/'current.json',{'directory':'../outside'})
        with self.assertRaises(ValueError): self.transfer()
        self.assertTrue(outside.exists())
        (self.peer/'current.json').unlink()
        file=self.source/'outbox'/self.manifest['files'][0]['name']; file.unlink(); file.symlink_to(outside)
        with self.assertRaises(ValueError): self.transfer()
    def test_missing_interface_during_real_outage_is_preserved(self):
        sample=copy.deepcopy(self.sample); sample['network']['interface']=None
        row=sync.compact_sample(sample)
        self.assertEqual(row['interface'],'unknown')
        sync.validate_records('samples-x',json.dumps(row).encode()+b'\n',self.now+1)
    def test_torn_local_tail_retried(self):
        path=next(self.data.glob('samples-*.jsonl'))
        original=path.stat().st_size
        with path.open('ab') as f:f.write(b'{"unfinished":')
        sync.publish(self.data,self.source,host='Mini-One',now=self.now+2)
        self.assertEqual(sync.read(self.source/'cursor.json')['offsets'][path.name],original)
    def test_generation_resets_compact_history(self):
        self.transfer(); before=self.current()
        sync.save(self.source/'generation.json',{'id':'a'*32})
        sync.publish(self.data,self.source,host='Mini-One',now=self.now+2)
        self.transfer()
        self.assertEqual(sync.read(self.peer/'current.json')['generation'],'a'*32)
        self.assertFalse(before.exists())
    def test_stale_observations_stay_stale(self):
        self.transfer()
        import agent_query
        value=agent_query.briefing(self.current(),include_history=False,now=self.now+200)
        self.assertTrue(value['recorder']['stale']); self.assertEqual(value['internet'],'unknown')
    def test_source_retention_is_reported_as_missing_samples(self):
        self.transfer()
        for p in self.source.glob('outbox/*.jsonl'):p.unlink()
        sync.publish(self.data,self.source,host='Mini-One',now=self.now+2)
        self.transfer()
        self.assertEqual(list(self.current().glob('samples-*.jsonl')),[])
    def test_interrupted_publication_rebuilds_without_duplicate_history(self):
        original=sync.save
        def fail_cursor(path,value):
            if path.name=='cursor.json': raise OSError('simulated crash before cursor commit')
            return original(path,value)
        newer=copy.deepcopy(self.sample); newer['started_at']=m.stamp(self.now+1)
        m.journals(self.data)[0].append(newer)
        with patch.object(sync,'save',side_effect=fail_cursor):
            with self.assertRaises(OSError): sync.publish(self.data,self.source,host='Mini-One',now=self.now+2)
        self.assertTrue((self.source/'publish-pending.json').exists())
        sync.publish(self.data,self.source,host='Mini-One',now=self.now+3)
        self.assertFalse((self.source/'publish-pending.json').exists())
        rows=[json.loads(line) for p in (self.source/'outbox').glob('samples-*.jsonl') for line in p.read_text().splitlines()]
        self.assertEqual(len(rows),2)
        self.assertEqual(len({row['time'] for row in rows}),2)

    def test_retired_generation_cannot_replace_current_cache(self):
        self.transfer(); original=copy.deepcopy(self.manifest)
        sync.save(self.source/'generation.json',{'id':'b'*32})
        sync.publish(self.data,self.source,host='Mini-One',now=self.now+2); self.transfer()
        pointer=sync.read(self.peer/'current.json')
        sync.save(self.source/'outbox/manifest.json',original)
        with self.assertRaisesRegex(ValueError,'generation replay'): self.transfer()
        self.assertEqual(sync.read(self.peer/'current.json'),pointer)

    def test_cache_swap_waits_for_snapshot_reader(self):
        self.transfer()
        sync.publish(self.data,self.source,host='Mini-One',now=self.now+2)
        started=threading.Event(); finished=threading.Event(); errors=[]
        def writer():
            started.set()
            try: self.transfer()
            except Exception as error: errors.append(error)
            finally: finished.set()
        with sync.cache_lock(self.peer,shared=True):
            before=self.current()
            worker=threading.Thread(target=writer); worker.start()
            self.assertTrue(started.wait(1)); self.assertFalse(finished.wait(.05))
            self.assertEqual(self.current(),before); self.assertTrue(before.exists())
        worker.join(2)
        self.assertTrue(finished.is_set()); self.assertFalse(errors)

    def test_peer_query_filters_window_deduplicates_and_keeps_open_incident(self):
        import agent_query
        m.journals(self.data)[0].append(self.sample)
        sync.publish(self.data,self.source,host='Mini-One',now=self.now+2)
        self.transfer()
        root=self.root/'consumer'; root.mkdir()
        self.peer.rename(root/'peer')
        sync.save(root/'config.json',{'peer_id':self.manifest['host_id'],'peer_host':'Mini-One'})
        cache=sync.current_peer(root)
        speed=[{'started_at':m.stamp(self.now-7200),'status':'success','download_mbps':100},
               {'started_at':m.stamp(self.now-60),'status':'success','download_mbps':200}]
        path=cache/'performance-00000000000000000001-aaaaaaaa.jsonl'
        path.write_text(''.join(json.dumps(x)+'\n' for x in speed))
        state=sync.read(cache/'state.json')
        state['incident']={'id':'active','started_at':m.stamp(self.now-30),'episodes':[],'hypotheses':[]}
        state['recent_incidents']=[{'id':'old','started_at':m.stamp(self.now-8000),'recovered_at':m.stamp(self.now-7200),'episodes':[],'hypotheses':[]}]
        sync.save(cache/'state.json',state)
        q=sync.peer_briefing(root,1,self.now+3)
        self.assertEqual(q['window']['hours'],1)
        self.assertEqual(len(q['speed_tests']),1)
        self.assertEqual([i['id'] for i in q['incidents']],['active'])
        self.assertEqual(q['observed_samples'],1)
        self.assertEqual(q['public_ping_attempts'],2)
        self.assertLessEqual(q['coverage_seconds'],15)
        with patch.object(agent_query,'briefing',return_value={'local':'still readable'}):
            sync.save(cache/'manifest.json',{'malformed':True})
            q=sync.all_hosts(self.data,root,1)
        self.assertIsNone(q['peer']); self.assertIn('peer_error',q)
        self.assertEqual(q['local'],{'local':'still readable'})

    def test_malformed_local_rows_do_not_poison_publication(self):
        path=next(self.data.glob('samples-*.jsonl'))
        with path.open('a') as handle: handle.write('[]\n')
        sync.publish(self.data,self.source,host='Mini-One',now=self.now+2)
        self.transfer()
        self.assertFalse((self.source/'publish-pending.json').exists())
        rows=[line for p in self.current().glob('samples-*.jsonl') for line in p.read_text().splitlines()]
        self.assertEqual(len(rows),1)

    def test_single_observer_query_does_not_create_sync_state(self):
        import agent_query
        root=self.root/'unused-sync'
        with patch.object(agent_query,'briefing',return_value={'host':'local'}):
            result=sync.all_hosts(self.data,root,1)
        self.assertIsNone(result['peer']); self.assertFalse(root.exists())

    def test_invalid_record_times_and_limits(self):
        row=sync.compact_sample(self.sample); row['time']=float('inf')
        with self.assertRaises(ValueError): sync.validate_records('samples-x',json.dumps(row).encode()+b'\n',self.now)
        with self.assertRaises(ValueError): sync.validate_records('samples-x',b'{}',self.now)

if __name__=='__main__': unittest.main()
