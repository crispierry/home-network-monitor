import copy
import json
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

import monitor as m

BASE_TIME = 1794844800


def sample(second, failed=()):
    ts = m.stamp(BASE_TIME+second)
    return dict(started_at=ts, finished_at=ts, host={'hostname': 'simulation'},
                checks=[dict(s, ok=s['id'] not in failed, started_at=ts, finished_at=ts,
                             latency_ms=1 if s['id'] not in failed else None,
                             elapsed_ms=1, detail='synthetic') for s in m.specs(m.DEFAULT)])


class DetectionTests(unittest.TestCase):
    def test_failure_recovery_and_staggered_checks(self):
        d = m.Detector(m.DEFAULT)
        d.update(sample(0))
        self.assertEqual(d.update(sample(30, ['google_tcp'])), [])
        events = d.update(sample(60, ['google_tcp', 'cloudflare_tcp']))
        self.assertEqual(events[1]['first_failed_at'], m.stamp(BASE_TIME+30))
        d.update(sample(90, ['cloudflare_tcp']))
        d.update(sample(120, ['cloudflare_tcp']))
        self.assertIsNotNone(d.state['incident'])
        d.update(sample(150))
        events = d.update(sample(180))
        inc = events[-1]['incident']
        self.assertEqual(inc['episodes'][0]['first_recovered_at'], m.stamp(BASE_TIME+90))
        self.assertEqual(inc['episodes'][1]['first_recovered_at'], m.stamp(BASE_TIME+150))
        self.assertEqual(inc['recovered_at'], m.stamp(BASE_TIME+150))
        self.assertIsNone(d.state['incident'])

    def test_single_failure_is_raw_only_and_flapping_resets_confirmation(self):
        d = m.Detector(m.DEFAULT)
        for sec, fail in [(0, []), (30, ['orbi_icmp']), (60, []), (90, ['orbi_icmp']), (120, [])]:
            self.assertEqual(d.update(sample(sec, fail)), [])
        self.assertEqual(d.state['recent_incidents'], [])

    def test_restart_keeps_open_incident_and_marks_gap(self):
        d = m.Detector(m.DEFAULT)
        d.update(sample(0, ['google_dns']))
        d.update(sample(30, ['google_dns']))
        saved = json.loads(json.dumps(d.state))
        d = m.Detector(m.DEFAULT, saved)
        events = d.update(sample(3600))
        self.assertEqual(events[0]['type'], 'monitor_gap')
        self.assertIsNotNone(d.state['incident'])
        events = d.update(sample(3630))
        self.assertTrue(events[-1]['incident']['has_observation_gap'])
        self.assertEqual(events[-1]['incident']['episodes'][0]['first_recovered_at'], m.stamp(BASE_TIME+3600))

    def test_gap_breaks_failure_streak(self):
        d = m.Detector(m.DEFAULT)
        d.update(sample(0, ['orbi_tcp']))
        d.update(sample(600, ['orbi_tcp']))
        self.assertIsNone(d.state['incident'])
        d.update(sample(630, ['orbi_tcp']))
        self.assertEqual(d.state['incident']['started_at'], m.stamp(BASE_TIME+600))

    def test_clock_backwards_marks_gap(self):
        d = m.Detector(m.DEFAULT)
        d.update(sample(30))
        self.assertEqual(d.update(sample(0))[0]['type'], 'monitor_gap')

    def test_config_change_cannot_silently_reinterpret_state(self):
        d = m.Detector(m.DEFAULT)
        with self.assertRaises(ValueError):
            m.Detector({**m.DEFAULT, 'orbi': '10.1.0.1'}, d.state)

    def test_failure_at_start_does_not_invent_previous_success(self):
        d = m.Detector(m.DEFAULT)
        d.update(sample(0, ['orbi_icmp']))
        events = d.update(sample(30, ['orbi_icmp']))
        self.assertIsNone(events[1]['last_success_at'])

    def test_interpretations_are_hypotheses(self):
        for failed, text in [(['orbi_icmp'], 'ICMP filtering'),
                             (['system_dns', 'orbi_dns'], 'DNS trouble'),
                             ([s['id'] for s in m.specs(m.DEFAULT) if s['id'].startswith(('google', 'cloudflare'))], 'AT&T')]:
            notes = m.hypotheses(sample(0, failed)['checks'])
            self.assertTrue(any(text in n for n in notes))
            self.assertTrue(all(n.startswith('Hypothesis:') for n in notes))

    def test_stale_status(self):
        d = m.Detector(m.DEFAULT)
        d.update(sample(0))
        with patch('monitor.time.time', return_value=BASE_TIME+1000):
            self.assertIn('STALE', m.report(d.state))

    def test_local_permission_error_is_not_reported_as_equipment_failure(self):
        checks = sample(0, ['peer_icmp'])['checks']
        checks.append(dict(id='satellite_1_tcp', ok=False, detail='OSError_65'))
        notes = m.hypotheses(checks)
        self.assertTrue(any('Local Network permission' in note for note in notes))
        self.assertTrue(all(note.startswith('Hypothesis:') for note in notes))


class DeploymentTests(unittest.TestCase):
    def test_cadence_upgrade_preserves_incidents_and_resets_streaks(self):
        import manage
        old = {**m.DEFAULT, 'interval_seconds': 30}
        d = m.Detector(old)
        d.update(sample(0, ['google_dns']))
        d.update(sample(30, ['google_dns']))
        saved = copy.deepcopy(d.state)
        upgraded = manage.cadence_migration(m.DEFAULT, old, saved)
        self.assertEqual(saved, d.state)
        self.assertEqual(upgraded['incident']['id'], saved['incident']['id'])
        self.assertTrue(upgraded['incident']['has_observation_gap'])
        self.assertTrue(upgraded['checks']['google_dns']['down'])
        self.assertEqual(upgraded['checks']['google_dns']['fail_count'], 0)
        d = m.Detector(m.DEFAULT, upgraded)
        d.update(sample(45))
        self.assertIsNotNone(d.state['incident'])
        d.update(sample(60))
        self.assertIsNone(d.state['incident'])

    def test_cadence_migration_refuses_changed_probe_or_unverified_checkpoint(self):
        import manage
        old = {**m.DEFAULT, 'interval_seconds': 30}
        d = m.Detector(old)
        with self.assertRaises(ValueError):
            manage.cadence_migration({**m.DEFAULT, 'orbi': '10.1.0.1'}, old, d.state)
        with self.assertRaises(ValueError):
            manage.cadence_migration(m.DEFAULT, {**old, 'orbi': '10.1.0.1'}, d.state)

    def test_hourly_upgrade_preserves_open_incident_and_confirmation_streaks(self):
        import manage
        old = {**m.DEFAULT, 'speed_hours': [3, 15]}
        d = m.Detector(old)
        d.update(sample(0, ['google_dns']))
        d.update(sample(15, ['google_dns']))
        saved = copy.deepcopy(d.state)
        upgraded = manage.cadence_migration(m.DEFAULT, old, saved)
        self.assertEqual(saved, d.state)
        self.assertEqual(upgraded['checks'], saved['checks'])
        self.assertEqual(upgraded['incident'], saved['incident'])
        m.Detector(m.DEFAULT, upgraded)
        with self.assertRaises(ValueError):
            manage.cadence_migration({**m.DEFAULT, 'gateway': '10.1.0.1'}, old, saved)

    def test_readiness_allows_launchd_throttle_longer_than_twenty_seconds(self):
        import manage
        old = {'last_completed_at': m.stamp(BASE_TIME-10)}
        fresh = {'last_completed_at': m.stamp(BASE_TIME+35)}
        with patch('monitor.read_state', side_effect=[old]*35+[fresh]), patch('manage.time.sleep') as sleep:
            self.assertIs(manage.wait_for_sample(Path('/unused'), BASE_TIME), fresh)
            self.assertEqual(sleep.call_count, 35)

    def test_stop_waits_until_service_is_removed(self):
        import manage
        from subprocess import CompletedProcess
        with patch('manage.launchctl', side_effect=[CompletedProcess([], 0),
                   CompletedProcess([], 0), CompletedProcess([], 113)]) as launch, \
                patch('manage.time.sleep'):
            manage.stop_service('gui/501')
        self.assertEqual(launch.call_count, 3)

    def test_stop_refuses_to_replace_a_service_that_did_not_exit(self):
        import manage
        from subprocess import CompletedProcess
        with patch('manage.launchctl', return_value=CompletedProcess([], 0)), \
                patch('manage.time.sleep'), self.assertRaises(RuntimeError):
            manage.stop_service('gui/501')


class StorageTests(unittest.TestCase):
    def test_rotation_hard_cap_and_readability(self):
        with tempfile.TemporaryDirectory() as tmp:
            journal = m.Journal(Path(tmp), 'test', 100, 3, 30)
            for i in range(50):
                journal.append({'number': i, 'padding': 'x'*20})
            self.assertLessEqual(sum(p.stat().st_size for p in journal.files()), 300)
            self.assertLessEqual(len(journal.files()), 3)
            self.assertEqual(list(journal.records())[-1]['number'], 49)

    def test_torn_append_is_repaired(self):
        with tempfile.TemporaryDirectory() as tmp:
            journal = m.Journal(Path(tmp), 'test', 1000, 3, 30)
            journal.append({'number': 1})
            with journal.files()[0].open('ab') as f:
                f.write(b'{"partial":')
            journal.append({'number': 2})
            self.assertEqual(list(journal.records()), [{'number': 1}, {'number': 2}])

    def test_age_retention(self):
        with tempfile.TemporaryDirectory() as tmp:
            journal = m.Journal(Path(tmp), 'test', 1000, 3, 30)
            journal.append({'old': True}, now=BASE_TIME)
            old = journal.files()[0]
            os.utime(old, (BASE_TIME, BASE_TIME))
            journal.append({'new': True}, now=BASE_TIME+31*86400)
            self.assertEqual(list(journal.records()), [{'new': True}])


class ProbeTests(unittest.TestCase):
    def test_icmp_latency_and_failures(self):
        spec = dict(id='test', kind='icmp', target='1.1.1.1')
        with patch('monitor.command', return_value=(0, '64 bytes time=8.20 ms')):
            result = m.probe(spec, 3)
            self.assertTrue(result['ok'])
            self.assertEqual(result['latency_ms'], 8.2)
        with patch('monitor.command', return_value=(124, '')):
            result = m.probe(spec, 3)
            self.assertFalse(result['ok'])
            self.assertIsNone(result['latency_ms'])

    def test_nxdomain_empty_and_timeout_are_not_dns_success(self):
        spec = dict(id='test', kind='dns', target='1.1.1.1', query='example.com')
        for rc, text in [(0, 'status: NXDOMAIN'), (0, 'status: NOERROR'), (124, '')]:
            with patch('monitor.command', return_value=(rc, text)):
                self.assertFalse(m.probe(spec, 3)['ok'])
        with patch('monitor.command', return_value=(0, 'status: NOERROR\nexample.com. 60 IN A 1.2.3.4')):
            self.assertTrue(m.probe(spec, 3)['ok'])

    def test_install_host_guard(self):
        with patch('monitor.identity', return_value={'hostname': 'Mini-Two'}):
            with self.assertRaises(ValueError):
                m.validate_host('Mini-One')
        with patch('monitor.identity', return_value={'hostname': 'Mini One.local'}):
            self.assertEqual(m.validate_host('Mini-One')['hostname'], 'Mini One.local')


if __name__ == '__main__':
    unittest.main()


class PerformanceTests(unittest.TestCase):
    def test_units_and_missing_are_not_zero(self):
        import performance as p
        row=p.measurements({'dl_throughput': 900000000, 'ul_throughput': 120000000, 'base_rtt': 12}, 0)
        self.assertEqual(row['download_mbps'], 900)
        self.assertEqual(row['upload_mbps'], 120)
        self.assertEqual(row['status'], 'success')
        row=p.measurements({'dl_throughput': 0}, 0)
        self.assertIsNone(row['download_mbps'])
        self.assertIsNone(row['upload_mbps'])
        self.assertEqual(row['status'], 'incomplete')
        self.assertEqual(p.measurements({}, 124)['status'], 'error')

    def test_host_windows_cannot_overlap_and_leave_guard(self):
        import performance as p
        a={**m.DEFAULT,'speed_slot':0}
        b={**m.DEFAULT,'speed_slot':1}
        for t in range(3600):
            self.assertFalse(p.allowed(a,t) and p.allowed(b,t))
            if p.allowed(a,t):
                self.assertLess(t+a['speed_max_seconds']+5, 20*60)
            if p.allowed(b,t):
                self.assertLess(t+b['speed_max_seconds']+5, 50*60)
        self.assertTrue(p.allowed(a, 15*60+30))
        self.assertTrue(p.allowed(b, 45*60+30))
        for t in (30, 5*60+30):
            self.assertFalse(p.allowed(a, t))
            self.assertFalse(p.allowed(b, t))

    def test_schedule_persists_claim_and_has_no_catchup(self):
        import performance as p
        from datetime import datetime
        with tempfile.TemporaryDirectory() as tmp:
            data=Path(tmp)
            now=datetime(2026,11,16,3,15,30,tzinfo=p.ZONE).timestamp()
            self.assertTrue(p.due(m.DEFAULT,data,now))
            self.assertFalse(p.due(m.DEFAULT,data,now+30))
            self.assertFalse(p.due(m.DEFAULT,data,now+600))

    def test_hourly_schedule_both_hosts_once_each_hour(self):
        import performance as p
        from datetime import datetime
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            config_path = root/'config.json'
            config_path.write_text(json.dumps({**m.DEFAULT, 'speed_hours': list(range(24))}))
            c = m.config(config_path)
            for slot in (0, 1):
                data = root/str(slot)
                data.mkdir()
                c['speed_slot'] = slot
                for hour in range(24):
                    now = datetime(2026, 11, 16, hour, (15, 45)[slot], 30, tzinfo=p.ZONE).timestamp()
                    self.assertTrue(p.due(c, data, now))
                    self.assertFalse(p.due(c, data, now+15))
                    self.assertFalse(p.due(c, data, now+600))
                self.assertFalse(p.due({**c, 'speed_enabled': False}, data, now+3600))
            config_path.write_text(json.dumps({**c, 'speed_hours': [24]}))
            with self.assertRaises(ValueError):
                m.config(config_path)

    def test_incident_skips_network_load(self):
        import performance as p
        with tempfile.TemporaryDirectory() as tmp:
            data=Path(tmp)
            with patch('performance.allowed', return_value=True), patch('monitor.identity',return_value={}), patch('monitor.read_state', return_value=None), patch('performance.subprocess.run') as call:
                self.assertEqual(p.execute(m.DEFAULT,data,True)['status'],'skipped')
                call.assert_not_called()

    def test_fresh_https_http_error_is_failure(self):
        s=next(s for s in m.specs(m.DEFAULT) if s['id']=='google_https')
        with patch('monitor.command', return_value=(0,'500')):
            self.assertFalse(m.probe(s,3)['ok'])
        with patch('monitor.command', return_value=(0,'200')):
            self.assertTrue(m.probe(s,3)['ok'])

    def test_https_timeout_preserves_only_reached_milestones(self):
        spec = next(s for s in m.specs(m.DEFAULT) if s['id']=='google_https')
        with patch('monitor.command', return_value=(28,'000|0.012|0|0|3.001')):
            row = m.probe(spec,3)
        self.assertFalse(row['ok'])
        self.assertEqual(row['detail'],'curl_exit_28_http_000')
        self.assertEqual(row['https_timing_ms'],dict(tcp_connected=12.0,tls_connected=None,first_byte=None,total=3001.0))
        with patch('monitor.command', return_value=(0,'200|0.01|0.03|0.05|0.06')):
            row = m.probe(spec,3)
        self.assertTrue(row['ok'])
        self.assertEqual(row['https_timing_ms']['tls_connected'],30.0)
        with patch('monitor.command', return_value=(124,'000|nan|-1|bad|inf')):
            row = m.probe(spec,3)
        self.assertTrue(all(v is None for v in row['https_timing_ms'].values()))

class ControlTests(unittest.TestCase):
    def test_delete_requires_confirmation_and_stopped_service(self):
        import manage
        with self.assertRaises(ValueError):
            manage.control('delete-history')
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            with patch.object(m, 'BASE', root), patch.object(m, 'DATA', root):
                with self.assertRaises(RuntimeError):
                    manage.control('delete-history', True)
                (root/'monitoring-paused').write_text('paused')
                with patch.object(manage, 'launchctl') as job:
                    job.return_value.returncode = 0
                    with self.assertRaises(RuntimeError):
                        manage.control('delete-history', True)

    def test_delete_keeps_configuration_and_refuses_active_writer(self):
        import manage, fcntl
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            for name in ('monitoring-paused','config.json','samples-test.jsonl','state.json','observations-test.jsonl','diagnostics-test.jsonl','investigations-test.jsonl','investigation-latest.json','unrelated.txt'):
                (root/name).write_text('test')
            with patch.object(m, 'BASE', root), patch.object(m, 'DATA', root), patch.object(manage, 'launchctl') as job:
                job.return_value.returncode = 1
                with (root/'speed.lock').open('a') as lock:
                    fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
                    with self.assertRaises(RuntimeError):
                        manage.control('delete-history', True)
                    self.assertTrue((root/'state.json').exists())
                manage.control('delete-history', True)
            self.assertTrue((root/'config.json').exists())
            self.assertTrue((root/'monitoring-paused').exists())
            self.assertFalse((root/'investigations-test.jsonl').exists())
            self.assertFalse((root/'investigation-latest.json').exists())
            self.assertTrue((root/'unrelated.txt').exists())
            self.assertFalse((root/'state.json').exists())
            self.assertFalse((root/'samples-test.jsonl').exists())
            self.assertFalse((root/'diagnostics-test.jsonl').exists())

    def test_pause_disables_future_login_before_stopping(self):
        import manage
        with tempfile.TemporaryDirectory() as tmp, patch.object(m, 'BASE', Path(tmp)), patch.object(manage, 'launchctl') as job, patch.object(manage, 'stop_service') as stop, patch.object(manage, 'sync_control') as sync_control:
            manage.control('pause')
            self.assertEqual(job.call_args.args[0], 'disable')
            stop.assert_called_once()
            sync_control.assert_called_once_with('pause')
            self.assertTrue((Path(tmp)/'monitoring-paused').exists())

    def test_resume_reenables_service_and_clears_pause_only_on_success(self):
        import manage
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp); marker = root/'monitoring-paused'; plist = root/'job.plist'
            marker.write_text('paused'); plist.write_text('installed')
            with patch.object(m, 'BASE', root), patch.object(manage, 'PLIST', plist), patch.object(manage, 'launchctl') as job:
                job.return_value.returncode = 1
                def fail(*args, **kwargs):
                    if args[0] == 'bootstrap': raise RuntimeError('simulated launch failure')
                    return type('Result', (), {'returncode':1})()
                job.side_effect = fail
                with self.assertRaises(RuntimeError): manage.control('resume')
                self.assertTrue(marker.exists())
                job.side_effect = None
                manage.control('resume')
                self.assertFalse(marker.exists())
                self.assertTrue(any(call.args[0] == 'enable' for call in job.call_args_list))
