import copy
import json
from pathlib import Path
import tempfile
import time
import unittest

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
    def test_invalid_record_times_and_limits(self):
        row=sync.compact_sample(self.sample); row['time']=float('inf')
        with self.assertRaises(ValueError): sync.validate_records('samples-x',json.dumps(row).encode()+b'\n',self.now)
        with self.assertRaises(ValueError): sync.validate_records('samples-x',b'{}',self.now)

if __name__=='__main__': unittest.main()
