import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
import devices
import agent_query
import monitor as m

T = 1794862800


def reading(seconds, reply=True, identity='match'):
    return dict(id='camera', name='Camera', address='192.0.2.12', mac='02:00:00:00:01:03',
        observed_at=m.stamp(T+seconds), reply=reply, identity=identity)


class DeviceTests(unittest.TestCase):
    def test_call_performance_breaks_variation_at_loss_gaps_and_path_changes(self):
        def sample(t, value, interface='en1'):
            return dict(started_at=m.stamp(T+t), interval_seconds=15, network=dict(interface=interface),
                        checks=[dict(id='google_icmp',ok=value is not None,latency_ms=value)])
        rows = [sample(-400,999), sample(-120,10), sample(-105,20), sample(-90,None),
                sample(-75,100), sample(-30,300), sample(-15,500,'en0')]
        result = agent_query.recent_performance(rows,T)['paths']
        self.assertEqual(result['google_icmp']['attempted'],6)
        self.assertEqual(result['google_icmp']['missed'],1)
        self.assertEqual(result['google_icmp']['p95_ms'],500)
        self.assertEqual(result['google_icmp']['mean_adjacent_rtt_change_ms'],10)
        self.assertIsNone(result['orbi_icmp']['loss_percent'])

    def test_briefing_includes_symptoms_as_reports_and_performance_staleness(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            (root/'observations-test.jsonl').write_text(json.dumps(dict(time=T-30,service='Zoom / video meeting',note='Synthetic'))+'\n')
            brief = agent_query.briefing(root,now=T)
            self.assertTrue(brief['recent_performance']['stale'])
            self.assertEqual(brief['reported_symptoms'][0]['service'],'Zoom / video meeting')
            self.assertIsNone(brief['recent_performance']['paths']['google_icmp']['median_ms'])

    def test_initial_nonresponder_is_unknown_and_does_not_create_incident(self):
        rows, events = devices.update([reading(0, False)], [])
        rows, events = devices.update([reading(60, False)], rows)
        self.assertEqual(rows[0]['status'], 'unknown')
        self.assertEqual(events, [])

    def test_confirm_failure_and_recovery_with_original_times(self):
        rows, _ = devices.update([reading(0)], [])
        rows, events = devices.update([reading(60, False)], rows)
        self.assertEqual(events, [])
        rows, events = devices.update([reading(120, False)], rows)
        self.assertEqual(events[0]['first_failed_at'], m.stamp(T+60))
        rows, events = devices.update([reading(180)], rows)
        self.assertEqual(rows[0]['status'], 'recovering')
        rows, events = devices.update([reading(240)], rows)
        self.assertEqual(events[0]['first_recovered_at'], m.stamp(T+180))
        self.assertEqual(rows[0]['status'], 'responding')

    def test_gap_breaks_streak_and_reassigned_address_never_passes(self):
        rows, _ = devices.update([reading(0)], [])
        rows, _ = devices.update([reading(60, False)], rows)
        rows, events = devices.update([reading(600, False)], rows)
        self.assertEqual(events, [])
        rows, events = devices.update([reading(660, True, 'mismatch')], rows)
        self.assertEqual(rows[0]['status'], 'address_changed')
        self.assertEqual(rows[0]['last_reply_at'], m.stamp(T))
        rows, events = devices.update([reading(720, True, 'unverified')], rows)
        self.assertEqual(rows[0]['status'], 'address_reply')
        self.assertEqual(events, [])

    def test_arp_cache_does_not_prove_liveness(self):
        target = dict(reading(0), attachment='Router', inventory_at='2026-11-16', note='')
        target = {k:target[k] for k in ('id','name','address','mac','attachment','inventory_at','note')}
        with patch('monitor.probe', return_value=dict(started_at=m.stamp(T),ok=False,latency_ms=None,detail='timeout')), patch('monitor.command',side_effect=[(0,'? (192.0.2.12) at 02:00:00:00:01:03 on en1'),(0,'inet 192.0.2.11 netmask')]):
            rows, _ = devices.update(devices.collect([target]), [])
        self.assertEqual(rows[0]['identity'], 'match')
        self.assertEqual(rows[0]['status'], 'unknown')

    def test_query_is_read_only_and_stale_never_healthy(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)/'absent'
            self.assertEqual(agent_query.briefing(root, now=T)['internet'], 'unknown')
            self.assertFalse(root.exists())
            root.mkdir()
            state = dict(last_completed_at=m.stamp(T), interval_seconds=15, checks={
                name:dict(latest=dict(id=name,ok=True)) for name in ('cloudflare_https','google_https')},
                devices=[dict(reading(0),status='responding')])
            (root/'state.json').write_text(json.dumps(state))
            before = (root/'state.json').read_bytes()
            brief = agent_query.briefing(root, now=T+1000)
            self.assertEqual(brief['internet'], 'unknown')
            self.assertEqual(brief['devices'][0]['status'], 'unknown')
            self.assertEqual((root/'state.json').read_bytes(), before)

    def test_inventory_validation_and_mac_normalization(self):
        self.assertEqual(devices.mac('2:0:0:0:1:2'), '02:00:00:00:01:02')
        self.assertIsNone(devices.mac('02:00:00:00:00:00'))
        self.assertEqual(len(devices.inventory(Path('devices.example.json'))), 1)
        with tempfile.TemporaryDirectory() as temp:
            path = Path(temp)/'inventory.json'
            path.write_text('[{"password":"not-accepted"}]')
            with self.assertRaises(ValueError): devices.inventory(path)

    def test_redacted_self_mac_is_unknown_identity_not_address_change(self):
        row = dict(id='mini',name='Mini',address='192.0.2.11',mac='02:00:00:00:01:02',attachment='',inventory_at='',note='')
        with patch('monitor.probe', return_value=dict(started_at=m.stamp(T),ok=True,latency_ms=1,detail='reply')), patch('monitor.command',side_effect=[(0,''),(0,'en1: flags=1\n ether 02:00:00:00:00:00\n inet 192.0.2.11 netmask')]):
            rows, _ = devices.update(devices.collect([row]), [])
        self.assertEqual(rows[0]['status'], 'address_reply')
        self.assertEqual(rows[0]['identity'], 'unverified')
        self.assertTrue(rows[0]['is_local'])
