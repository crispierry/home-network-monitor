import json
import subprocess
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import diagnostics as d
import monitor as m
import agent_query


class DiagnosticTests(unittest.TestCase):
    def test_allowlist_preserves_ports_and_omits_secrets(self):
        body = '''<script>password=secret</script><table><tr><th></th><th>Port 1</th><th>Port 2</th></tr>
          <tr><td>State</td><td>up</td><td>down</td></tr>
          <tr><td>Transmit Speed</td><td>2500000000</td><td>0</td></tr>
          <tr><td>Receive Errors</td><td>12</td><td>0</td></tr>
          <tr><td>Password</td><td>topsecret</td></tr>
          <tr><td>Serial Number</td><td>private</td></tr>
          <tr><td>Broadband IPv4 Address</td><td>203.0.113.9</td></tr></table>
          <h1>Rx Power&nbsp; Currently -181</h1>'''
        got = d.parse_status(body)
        self.assertEqual(got['tables'][0]['fields']['Receive Errors'], [12, 0])
        self.assertEqual(got['tables'][0]['fields']['State'], ['up', 'down'])
        self.assertEqual(got['optical_readings']['Rx Power'], -181)
        self.assertNotIn('secret', json.dumps(got))
        self.assertNotIn('203.0.113', json.dumps(got))
        self.assertNotIn('private', json.dumps(got))

    def test_http_errors_login_and_redirect_are_not_health(self):
        for body, code in [('<input value="secret">', '200'), ('', '302'), ('', '401')]:
            with patch.object(d, 'run_command', return_value=dict(output=body+'\n__HTTP_STATUS__'+code, exit=0, elapsed_ms=1)):
                row = d.gateway_page('192.168.1.254', 'sysinfo')
            self.assertNotEqual(row['status'], 'available')
            self.assertNotIn('secret', json.dumps(row))
        with self.assertRaises(ValueError):
            d.gateway_page('192.168.1.254', 'restart')
        with self.assertRaises(ValueError):
            d.gateway_page('att.example/evil', 'sysinfo')

    def test_gateway_request_has_no_credentials_or_redirects_and_deadline(self):
        with patch.object(d, 'run_command', return_value=dict(output='<table><tr><td>Model Number</td><td>BGW320-505</td></tr></table>\n__HTTP_STATUS__200', exit=0, elapsed_ms=1)) as call:
            row = d.gateway_page('192.168.1.254', 'sysinfo')
        args = call.call_args.args[0]
        self.assertEqual(row['status'], 'available')
        self.assertIn('--max-time', args)
        self.assertIn('--max-filesize', args)
        self.assertNotIn('-L', args)
        self.assertNotIn('--user', args)
        self.assertNotIn('--cookie', args)

    def test_busy_worker_does_not_queue_but_keeps_transition(self):
        s = d.Schedule()
        good = dict(started_at=m.stamp(0), checks=[dict(id='orbi_tcp', ok=True)], network=dict(interface='en0'))
        bad = dict(started_at=m.stamp(15), checks=[dict(id='orbi_tcp', ok=False)], network=dict(interface=None))
        s.observe(good)
        self.assertEqual(s.due(0), (dict(reason='periodic_baseline'), True))
        s.observe(bad)
        self.assertIsNone(s.due(15, busy=True))
        trigger, trace = s.due(30)
        self.assertEqual(trigger['failed_checks'], ['orbi_tcp'])
        self.assertFalse(trace)
        s.observe(good)
        self.assertEqual(s.due(45)[0]['failed_checks'], [])
        self.assertIsNone(s.due(46))
        self.assertEqual(s.due(105)[0]['reason'], 'periodic_baseline')

    def test_timeout_keeps_partial_route_evidence(self):
        with patch.object(d.subprocess, 'run', side_effect=subprocess.TimeoutExpired(['trace'], 9, output=b'1 10.0.0.1\n2 *')):
            row = d.run_command(['trace'], 9)
        self.assertEqual(row['exit'], 124)
        self.assertIn('10.0.0.1', row['output'])

    def test_latest_diagnostics_unknown_when_stale_or_error(self):
        now = 1800000000
        s = dict(type='diagnostic_snapshot', at=m.stamp(now-20), finished_at=m.stamp(now-10), gateway={})
        self.assertFalse(agent_query.diagnostic_status(s, now)['stale'])
        self.assertTrue(agent_query.diagnostic_status(s, now+300)['stale'])
        self.assertTrue(agent_query.diagnostic_status(dict(type='diagnostic_error',at=m.stamp(now)), now)['stale'])
        self.assertTrue(agent_query.diagnostic_status(None, now)['stale'])

    def test_diagnostic_journal_rotates_and_preserves_complete_json(self):
        with tempfile.TemporaryDirectory() as folder:
            j = m.Journal(Path(folder), 'diagnostics', 150, 2, 30)
            for i in range(10):
                j.append(dict(at=m.stamp(i), evidence='x'*40), now=100+i)
            self.assertLessEqual(len(j.files()), 2)
            self.assertTrue(all(r['evidence']=='x'*40 for r in j.records()))
