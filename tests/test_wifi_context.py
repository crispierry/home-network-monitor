import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

import agent_query
import diagnostics
import monitor as m


class WifiContextTests(unittest.TestCase):
    def test_helper_is_read_only_and_never_launches_profiler_when_available(self):
        with tempfile.TemporaryDirectory() as folder:
            root=Path(folder); (root/'wifi-observer').touch()
            with patch.object(m,'BASE',root),patch.object(m,'command',return_value=(0,json.dumps(dict(source='CoreWLAN',status='available',rssi_dbm=-54)))) as run:
                row=m.wifi_snapshot()
            self.assertEqual(row['rssi_dbm'],-54)
            self.assertEqual(run.call_args.args[0],[str(root/'wifi-observer')])
            self.assertEqual(run.call_count,1)

    def test_failed_native_provider_is_unknown_without_expensive_fallback(self):
        with tempfile.TemporaryDirectory() as folder:
            root=Path(folder); (root/'wifi-observer').touch()
            with patch.object(m,'BASE',root),patch.object(m,'command',return_value=(124,'')) as run:
                self.assertEqual(m.wifi_snapshot()['status'],'unavailable')
            self.assertEqual(run.call_count,1)

    def test_wifi_freshness_handles_missing_malformed_and_clock_reversal(self):
        for raw in [None,[],{},dict(at='invalid'),dict(at=m.stamp(1200)),dict(at=m.stamp(800))]:
            self.assertTrue(agent_query.wifi_status(raw,1000)['stale'])
        self.assertFalse(agent_query.wifi_status(dict(at=m.stamp(990)),1000)['stale'])
        self.assertTrue(agent_query.wifi_status(dict(at=m.stamp(990)),1000,True)['stale'])

    def test_path_context_omits_unrelated_power_output_and_marks_completion(self):
        sampler=unittest.mock.Mock();sampler.sample.return_value=dict(cpu_status='warming_up')
        with patch.object(diagnostics,'local_context',return_value={'interface_counters':{}}),patch.object(m,'wifi_snapshot',return_value={'status':'unavailable'}),patch.object(m,'diagnostics',return_value={'interface':'en1'}),patch.object(diagnostics,'run_command',return_value=dict(exit=0,output='AC Power:\n sleep 0\n unrelated private value\n lowpowermode 0')):
            row=diagnostics.path_context(sampler)
        self.assertNotIn('private',row['power']['output'])
        self.assertIn('lowpowermode',row['power']['output'])
        self.assertGreaterEqual(m.epoch(row['finished_at']),m.epoch(row['at']))
