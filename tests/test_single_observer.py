import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

import agent_query
import manage
import monitor as m


class SingleObserverTests(unittest.TestCase):
    def configuration(self, value):
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder)/'config.json'
            path.write_text(json.dumps(value))
            return m.config(path)

    def test_omitted_and_empty_peer_do_not_create_a_probe(self):
        for value in ({}, {'peer': ''}):
            c = self.configuration(value)
            checks = m.specs(c)
            self.assertNotIn('peer_icmp', {row['id'] for row in checks})
            self.assertTrue({'orbi_icmp', 'gateway_icmp', 'system_dns',
                             'cloudflare_https', 'google_https'} <= {row['id'] for row in checks})

    def test_invalid_peer_is_not_silently_disabled(self):
        for peer in (None, False, [], ' ', 'host;command', '-host'):
            with self.subTest(peer=peer), self.assertRaises(ValueError):
                self.configuration({'peer': peer})

    def test_single_observer_detects_and_recovers_internet_failure(self):
        c = self.configuration({'peer': '', 'satellites': []})
        detector = m.Detector(c)
        def update(second, failed=False):
            at = m.stamp(1794844800+second)
            checks = [dict(spec, ok=not (failed and spec['id'].startswith(('google', 'cloudflare'))),
                           started_at=at, finished_at=at, latency_ms=1, detail='synthetic')
                      for spec in m.specs(c)]
            return detector.update(dict(started_at=at, finished_at=at, host={'hostname': 'Only-Mac'}, checks=checks))
        update(0)
        update(15)
        self.assertIsNone(detector.state['incident'])
        update(30, True)
        update(45, True)
        self.assertEqual(detector.state['incident']['started_at'], m.stamp(1794844830))
        update(60)
        update(75)
        self.assertIsNone(detector.state['incident'])
        self.assertEqual(len(detector.state['recent_incidents']), 1)
        self.assertNotIn('peer_icmp', detector.state['checks'])
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            m.atomic(root/'state.json', json.dumps(detector.state))
            result = agent_query.briefing(root, now=1794844876)
        self.assertEqual(result['internet'], 'reachable')
        self.assertFalse(result['recorder']['stale'])
        self.assertNotIn('peer_icmp', {row['id'] for row in result['checks']})

    def test_explicit_peer_is_still_monitored(self):
        c = self.configuration({'peer': 'Second-Mac.local'})
        peer = [row for row in m.specs(c) if row['id'] == 'peer_icmp']
        self.assertEqual(peer, [dict(id='peer_icmp', kind='icmp', target='Second-Mac.local')])

    def test_upgrade_preserves_existing_peer_setting(self):
        with tempfile.TemporaryDirectory() as folder:
            base = Path(folder)
            (base/'config.json').write_text(json.dumps({'peer': 'Second-Mac.local'}))
            with patch.object(m, 'BASE', base):
                c, rows = manage.installation_settings(base)
            self.assertEqual(c['peer'], 'Second-Mac.local')
            self.assertEqual(rows, [])
