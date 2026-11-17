from concurrent.futures import Future, ThreadPoolExecutor
from contextlib import ExitStack
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

import agent_query
import analysis
import devices
import diagnostics
import monitor as m
import manage
import performance
import sync


class ImmediatePool:
    def __init__(self, **_): pass
    def __enter__(self): return self
    def __exit__(self, *_): pass
    def submit(self, fn, *args):
        f = Future()
        try: f.set_result(fn(*args))
        except Exception as exc: f.set_exception(exc)
        return f
    def map(self, fn, rows): return map(fn, rows)


class TwoCycles:
    def __init__(self): self.calls = 0
    def is_set(self):
        self.calls += 1
        return self.calls > 2
    def wait(self, _): pass
    def set(self): self.calls = 100


class ReviewTests(unittest.TestCase):
    def test_worker_restart_waits_for_its_own_service_to_disappear(self):
        from types import SimpleNamespace
        with patch.object(manage, 'launchctl', side_effect=[SimpleNamespace(returncode=n) for n in (0,0,0,1)]) as launch, patch.object(manage.time, 'sleep') as sleep:
            manage.stop_service('gui/501', 'synthetic.sync')
        self.assertEqual(sleep.call_count, 2)
        self.assertTrue(all(c.args[1]=='gui/501/synthetic.sync' for c in launch.call_args_list))

    def test_optional_collectors_and_bad_speed_schedule_do_not_stop_recording(self):
        with tempfile.TemporaryDirectory() as tmp, ExitStack() as stack:
            root = Path(tmp)
            def probe(spec, timeout):
                return dict(spec, started_at=m.stamp(), ok=True, latency_ms=1, detail='synthetic')
            patches = [(m, 'ThreadPoolExecutor', ImmediatePool), (m, 'identity', lambda: {'hostname':'Synthetic-Mini'}),
                       (m, 'diagnostics', lambda: dict(interface='en0')), (m, 'probe', probe)]
            for obj, key, value in patches: stack.enter_context(patch.object(obj, key, value))
            stack.enter_context(patch.object(m.threading, 'Event', return_value=TwoCycles()))
            stack.enter_context(patch.object(m.signal, 'signal'))
            stack.enter_context(patch.object(devices, 'inventory', return_value=[{'id':'synthetic'}]))
            stack.enter_context(patch.object(devices, 'collect', side_effect=OSError('synthetic')))
            stack.enter_context(patch.object(m, 'wifi_snapshot', side_effect=ValueError('synthetic')))
            stack.enter_context(patch.object(diagnostics, 'collect', return_value=dict(type='diagnostic_snapshot', at=m.stamp(), finished_at=m.stamp())))
            stack.enter_context(patch.object(performance, 'active', return_value=False))
            stack.enter_context(patch.object(performance, 'due', side_effect=ValueError('synthetic')))
            m.run(m.DEFAULT, root, enforce_host=False)
            samples = list(m.journals(root)[0].records())
            self.assertEqual(len(samples), 2)
            self.assertTrue(all(c['ok'] for s in samples for c in s['checks']))
            errors = {e['collector'] for e in m.journals(root)[1].records() if e['type']=='collector_error'}
            self.assertEqual(errors, {'devices','wifi','speed_schedule'})

    def test_paused_speed_cli_never_starts_network_quality(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp); (root/'monitoring-paused').write_text('paused')
            with patch.object(m, 'BASE', root), patch.object(m, 'DATA', root), patch.object(m, 'identity', return_value={}), patch.object(performance.subprocess, 'run') as run:
                result=performance.execute(m.DEFAULT, root, True)
            self.assertEqual(result['status'], 'skipped')
            self.assertIn('paused', result['reason'])
            run.assert_not_called()

    def test_missing_health_checks_never_authorize_load(self):
        with tempfile.TemporaryDirectory() as tmp:
            with patch.object(m, 'identity', return_value={}), patch.object(performance, 'allowed', return_value=True), patch.object(m, 'read_state', return_value={'last_completed_at':m.stamp(),'checks':{}}), patch.object(performance.subprocess, 'run') as run:
                result=performance.execute(m.DEFAULT, Path(tmp), True)
            self.assertEqual(result['status'],'skipped'); run.assert_not_called()

    def test_corrupt_load_marker_is_unknown_and_nonobject_output_is_incomplete(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp); (root/'speed-active.json').write_text('[]')
            self.assertIsNone(performance.active(root))
            self.assertEqual(performance.measurements([],0)['status'],'incomplete')
            row=dict(started_at=m.stamp(),checks=[],speed_test_active=None)
            compact=sync.compact_sample(row)
            self.assertFalse(compact['loaded']); self.assertFalse(compact['loadKnown'])

    def test_concurrent_journal_writers_and_uncommitted_tail(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp); journal=m.Journal(root,'samples',256,100,30)
            with ThreadPoolExecutor(max_workers=8) as pool:
                list(pool.map(lambda i: journal.append(dict(index=i)), range(50)))
            self.assertEqual({r['index'] for r in journal.records()},set(range(50)))
            with journal.files()[-1].open('ab') as f: f.write(b'{"index":999}')
            self.assertEqual(len(list(journal.records())),50)

    def test_percentile_and_variation_agree_with_dashboard(self):
        now=1800000000
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp); journal=m.journals(root)[0]
            for i in range(20):
                at=m.stamp(now-300+i*15)
                journal.append(dict(started_at=at,interval_seconds=15,network={'interface':'en0' if i%2 else 'en1'},
                    checks=[dict(id='orbi_icmp',started_at=at,ok=True,latency_ms=i)]))
            result=agent_query.briefing(root,hours=1,now=now)
            self.assertEqual(result['check_statistics']['orbi_icmp']['p95_ms'],18)
            with patch.object(analysis.time,'time',return_value=now): summary=analysis.summary(root,1)
            self.assertIn('18.00',summary)
            self.assertEqual(summary.splitlines()[2].split()[-1],'n/a')

    def test_malformed_peer_shapes_are_rejected_as_validation_errors(self):
        for value in ([], {}, {'schema':'network-monitor.exchange.v1','host_id':'x','host':'Mini-One','generation':[],'sequence':1}):
            with self.assertRaises(ValueError): sync.validate_manifest(value,'x','Mini-One')
        for row in ([], {}, {'schema':'network-monitor.sample.v1','lanes':None}):
            with self.assertRaises(ValueError): sync.validate_records('samples-x',json.dumps(row).encode()+b'\n',1800000000)


class PublicReleaseTests(unittest.TestCase):
    def test_installer_preserves_local_configuration_and_inventory(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp)
            config={**m.DEFAULT,'expected_host':'Test-Observer','speed_slot':1}
            (root/'config.json').write_text(json.dumps(config))
            row=dict(id='test',name='Synthetic device',address='192.0.2.20',mac='02:00:00:00:02:01',attachment='',inventory_at='',note='')
            (root/'devices.json').write_text(json.dumps([row]))
            with patch.object(m,'BASE',root):
                actual, rows=manage.installation_settings(Path('.'))
            self.assertEqual(actual,config)
            self.assertEqual(rows,[row])

    def test_first_install_requires_explicit_configuration(self):
        with tempfile.TemporaryDirectory() as tmp, patch.object(m,'BASE',Path(tmp)):
            with self.assertRaises(ValueError): manage.installation_settings(Path('.'))
            actual, rows=manage.installation_settings(Path('.'),config_path=Path('config.json'))
            self.assertFalse(actual['speed_enabled'])
            self.assertEqual(rows,[])

    def test_bounded_json_rejects_nonfinite_oversize_and_symlink(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp); path=root/'input.json'
            for contents in ('NaN','['*1200+']'*1200):
                path.write_text(contents)
                with self.assertRaises(ValueError): m.read_json(path)
            path.write_text(' '*100)
            with self.assertRaises(ValueError): m.read_json(path,20)
            link=root/'link'; link.symlink_to(path)
            with self.assertRaises(ValueError): m.read_json(link)

    def test_atomic_replacement_is_private_and_does_not_follow_symlinks(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp); path=root/'state.json'; m.atomic(path,'old')
            m.atomic(path,'new')
            self.assertEqual(path.read_text(),'new')
            self.assertEqual(path.stat().st_mode & 0o777,0o600)
            link=root/'link'; link.symlink_to(path)
            with self.assertRaises(ValueError): m.atomic(link,'bad')
            self.assertEqual(path.read_text(),'new')
            self.assertEqual(len(list(root.glob('.*.tmp'))),0)

    def test_bad_journal_line_does_not_hide_later_evidence(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp); journal=m.Journal(root,'sample',64,2,30)
            (root/'sample-test.jsonl').write_bytes(b'x'*200+b'\n'+b'{"ok":true}\n')
            self.assertEqual(list(journal.records()),[{'ok':True}])
            journal.append({'new':True})
            self.assertTrue(any(row.get('new') for row in journal.records()))


class EvidenceBoundaryTests(unittest.TestCase):
    def test_query_skips_malformed_sample_without_hiding_valid_evidence(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp); now=1800000000
            samples=m.journals(root)[0]
            samples.append({'started_at':'not a timestamp','checks':[]})
            samples.append({'started_at':m.stamp(now-15),'checks':[dict(id='google_icmp',ok=True,latency_ms=4)]})
            result=agent_query.briefing(root,now=now)
            self.assertEqual(result['rejected_sample_records'],1)
            self.assertEqual(result['check_statistics']['google_icmp']['median_ms'],4)

    def test_peer_speed_rejects_impossible_measurements(self):
        for value in (-1,1e309,'fast'):
            record=dict(started_at=m.stamp(1800000000),download_mbps=value)
            with self.assertRaises(ValueError):
                sync.validate_records('performance-test',json.dumps(record).encode()+b'\n',1800000001)
