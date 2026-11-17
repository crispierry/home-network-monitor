from contextlib import ExitStack
from pathlib import Path
import json
import sys
import tempfile
import unittest
from unittest.mock import patch

import investigation as lab
import monitor as m
import performance


class Clock:
    def __init__(self): self.now=0; self.stopped=False
    def is_set(self): return self.stopped
    def set(self): self.stopped=True
    def wait(self, seconds): self.now+=max(0,seconds)


class InvestigationTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory(); self.root=Path(self.temp.name)
    def tearDown(self): self.temp.cleanup()
    def point(self, value=10, phase='before', interface='en1'):
        return dict(time=lab.time.time(),target='Cloudflare',phase=phase,interface=interface,ok=value is not None,latency=value)

    def test_statistics_keep_loss_and_separate_paths_and_phases(self):
        rows=[self.point(x) for x in (1,2,3,100,None)]
        rows += [self.point(1000,'during'),self.point(20,'before','en0')]
        groups=lab.groups(rows)
        group=next(g for g in groups if g['phase']=='before' and g['interface']=='en1')
        self.assertEqual((group['attempted'],group['missed'],group['loss']),(5,1,20))
        self.assertEqual((group['p10'],group['median'],group['p95']),(1,2.5,100))
        self.assertEqual(len(groups),3)
        self.assertIsNone(lab.groups([self.point(None)])[0]['median'])

    def test_trigger_has_no_repeat_queue_or_catchup(self):
        trigger=lab.Trigger()
        sample=lambda ok:dict(checks=[dict(id='orbi',ok=ok)])
        self.assertIsNone(trigger.due(sample(True),0))
        self.assertIsNotNone(trigger.due(sample(False),1))
        self.assertIsNone(trigger.due(sample(False),400))
        trigger.due(sample(True),401)
        self.assertIsNone(trigger.due(sample(False),402,busy=True))
        self.assertIsNone(trigger.due(sample(False),403))
        trigger.due(sample(True),404)
        self.assertIsNotNone(trigger.due(sample(False),405))
        trigger.due(sample(True),406)
        self.assertIsNone(trigger.due(sample(False),407))

    def test_automatic_cooldown_survives_restart(self):
        sample=dict(checks=[dict(id='orbi_icmp',ok=False)])
        first=lab.Trigger(self.root)
        self.assertIsNotNone(first.due(sample,lab.time.monotonic()))
        second=lab.Trigger(self.root)
        self.assertIsNone(second.due(sample,lab.time.monotonic()))

    def test_slow_ping_triggers_capture_without_becoming_a_failure(self):
        trigger=lab.Trigger()
        sample=dict(checks=[dict(id='orbi_icmp',ok=True,latency_ms=40)])
        self.assertIn('slow orbi_icmp',trigger.due(sample,0))
        self.assertTrue(sample['checks'][0]['ok'])
        self.assertIsNone(trigger.due(sample,600))

    def test_capture_is_bounded_one_round_per_second(self):
        clock=Clock()
        def probe(spec, timeout):
            self.assertEqual(timeout,1)
            return dict(spec,started_at=m.stamp(1800000000+clock.now),ok=True,latency_ms=5)
        with patch.object(lab.time,'monotonic',side_effect=lambda:clock.now), patch.object(m,'probe',side_effect=probe), patch.object(m,'diagnostics',return_value={'interface':'en1'}), patch.object(performance,'active',return_value=False):
            rows=lab.capture(m.DEFAULT,self.root,3,'before',clock)
        self.assertEqual(len(rows),9)
        self.assertEqual(len({r['time'] for r in rows}),3)
        self.assertTrue(all(r['loaded'] is False for r in rows))

    def test_paused_capture_and_stop_send_no_packets(self):
        stop=Clock();stop.set()
        with patch.object(m,'probe') as probe, patch.object(m,'diagnostics',return_value={}), patch.object(lab,'paused',return_value=True):
            self.assertEqual(lab.capture(m.DEFAULT,self.root,60,'before',stop),[])
            probe.assert_not_called()

    def test_save_preserves_raw_and_limits_latest_to_one_per_kind(self):
        for kind in ('close-up','lan','routes','load-comparison','close-up'):
            report=lab.new(kind,'test');report['points']=[self.point()];report['raw']={'secret_free':'raw evidence'}
            lab.save(self.root,report)
        latest=lab.recent(self.root)
        self.assertEqual(len(latest),4)
        self.assertTrue(all('raw' not in r for r in latest))
        self.assertEqual(len(list(lab.journal(self.root).records())),5)
        self.assertTrue(all('raw' in r for r in lab.journal(self.root).records()))
        self.assertEqual(lab.journal(self.root).count,4)

    def test_no_load_or_listener_without_explicit_confirmation(self):
        with patch.object(lab,'command') as command:
            with self.assertRaises(ValueError): lab.lan(m.DEFAULT,self.root,'10.0.0.98','send')
            with self.assertRaises(ValueError): lab.serve(self.root,'10.0.0.98')
            command.assert_not_called()

    def test_rejects_non_lan_destinations(self):
        for value in ('127.0.0.1','169.254.1.1','224.0.0.1','1.1.1.1','::1','--help'):
            with self.assertRaises(ValueError): lab.private_ipv4(value)
        self.assertEqual(lab.private_ipv4('10.0.0.98'),'10.0.0.98')

    def test_lan_receive_builds_bounded_command_and_preserves_result(self):
        def command(args,seconds,data):
            if '--version' in args: return dict(exit=0,output='iperf3 fixture',truncated=False,error=None)
            self.assertIn('-R',args);self.assertIn('15',args);self.assertEqual(seconds,22)
            return dict(exit=0,output=json.dumps({'end':{'sum_received':{'bits_per_second':100000000},'sum_sent':{'retransmits':2}}}),truncated=False,error=None)
        with patch.object(lab,'tool',return_value='/synthetic/iperf3'), patch.object(lab,'avoid_speed_windows'), patch.object(lab,'capture',return_value=[]), patch.object(lab,'command',side_effect=command), patch.object(m,'diagnostics',return_value={'interface':'en1'}):
            result=lab.lan(m.DEFAULT,self.root,'10.0.0.98','receive',True)
        self.assertEqual(result['status'],'complete')
        self.assertTrue(any('100.0 Mbps' in d for d in result['details']))
        self.assertFalse(performance.active(self.root))

    def test_lan_error_is_incomplete_and_clears_load_marker(self):
        with patch.object(lab,'tool',return_value='/synthetic/iperf3'), patch.object(lab,'avoid_speed_windows'), patch.object(lab,'capture',return_value=[]), patch.object(lab,'command',return_value=dict(exit=1,output='[]',truncated=False,error=None)), patch.object(m,'diagnostics',return_value={'interface':'en1'}):
            result=lab.lan(m.DEFAULT,self.root,'10.0.0.98','send',True)
        self.assertEqual(result['status'],'incomplete');self.assertFalse(performance.active(self.root))

    def test_server_is_bound_one_off_and_always_has_deadline(self):
        with patch.object(lab,'tool',return_value='/synthetic/iperf3'), patch.object(lab,'avoid_speed_windows'), patch.object(lab,'command',return_value=dict(exit=124,output='',truncated=False,error='Deadline exceeded')) as command:
            result=lab.serve(self.root,'10.0.0.98',True)
        args,timeout,_=command.call_args.args
        self.assertIn('-1',args);self.assertIn('-B',args);self.assertIn('--server-max-duration',args)
        self.assertEqual(timeout,60);self.assertEqual(result['status'],'incomplete')
        self.assertFalse(performance.active(self.root))

    def test_route_fallback_is_bounded_and_does_not_blame_silent_hops(self):
        with patch.object(lab,'tool',return_value=None), patch.object(lab,'command',return_value=dict(exit=0,output=' 1  10.0.0.1  1.0 ms\n 2 *\n',error=None,truncated=False)) as command:
            result=lab.route(m.DEFAULT,self.root)
        self.assertEqual(command.call_count,6)
        self.assertTrue(all(c.args[1]==9 for c in command.call_args_list))
        self.assertTrue(any('not forwarding loss' in d for d in result['details']))
        self.assertTrue(any('MTR is not installed' in d for d in result['details']))

    def test_mtr_uses_no_dns_ten_cycles_and_keeps_errors(self):
        with patch.object(lab,'tool',return_value='/synthetic/mtr'), patch.object(lab,'command',return_value=dict(exit=1,output='permission denied',error=None,truncated=False)) as command:
            result=lab.route(m.DEFAULT,self.root)
        self.assertEqual(command.call_count,3)
        self.assertIn('--no-dns',command.call_args.args[0]);self.assertIn('10',command.call_args.args[0])
        self.assertEqual(result['status'],'incomplete')

    def test_command_deadline_kills_only_its_child(self):
        result=lab.command([sys.executable,'-c','import time; time.sleep(10)'],.05,self.root)
        self.assertEqual(result['error'],'Deadline exceeded')
        self.assertNotEqual(result['exit'],0)

    def test_command_output_is_capped(self):
        result=lab.command([sys.executable,'-c','print("x"*100000)'],2,self.root)
        self.assertLessEqual(len(result['output']),lab.MAX_OUTPUT)
        self.assertTrue(result['truncated'])

    def test_local_speed_lock_excludes_lan_tests(self):
        with lab.exclusive(self.root,'speed.lock'), patch.object(lab,'tool',return_value='/synthetic/iperf3'), patch.object(lab,'command') as command:
            with self.assertRaises(ValueError): lab.lan(m.DEFAULT,self.root,'10.0.0.98','send',True)
            command.assert_not_called()

    def test_active_marker_is_removed_even_after_error(self):
        marker=self.root/'investigation-active.json'
        with self.assertRaises(RuntimeError):
            with lab.exclusive(self.root,'investigation.lock'):
                self.assertTrue(marker.exists())
                raise RuntimeError('synthetic')
        self.assertFalse(marker.exists())

    def test_health_change_during_preparation_cancels_load_and_releases_capture(self):
        state=dict(last_completed_at=m.stamp(),checks={s['id']:dict(latest={'ok':True},pass_count=2) for s in m.specs(m.DEFAULT)})
        with patch.object(performance,'allowed',return_value=True),patch.object(m,'read_state',side_effect=[state,{}]),patch.object(m,'identity',return_value={'hostname':'Synthetic-Mini'}),patch.object(m,'diagnostics',return_value={'interface':'en1'}),patch.object(lab,'LoadCapture') as capture,patch.object(performance.subprocess,'run') as run:
            report=performance.execute(m.DEFAULT,self.root,False)
        self.assertEqual(report['status'],'skipped')
        run.assert_not_called(); capture.return_value.close.assert_called_once()

    def test_load_capture_failure_does_not_prevent_authorized_speed_measurement(self):
        state=dict(last_completed_at=m.stamp(),checks={s['id']:dict(latest={'ok':True},pass_count=2) for s in m.specs(m.DEFAULT)})
        from types import SimpleNamespace
        with patch.object(performance,'allowed',return_value=True),patch.object(m,'read_state',return_value=state),patch.object(m,'identity',return_value={'hostname':'Synthetic-Mini'}),patch.object(m,'diagnostics',return_value={'interface':'en1'}),patch.object(lab.LoadCapture,'start',side_effect=ValueError('busy')),patch.object(performance.subprocess,'run',return_value=SimpleNamespace(returncode=0,stdout='{"dl_throughput":100000000,"ul_throughput":100000000}')):
            report=performance.execute(m.DEFAULT,self.root,False)
        self.assertEqual(report['status'],'success')
        self.assertEqual(report['latency_capture_error'],'ValueError')
