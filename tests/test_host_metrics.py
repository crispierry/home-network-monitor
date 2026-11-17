import unittest
from unittest.mock import patch

import host_metrics as h
from agent_query import LoadComparison


def counters(rx=1000, tx=2000, errors=0):
    return dict(exit=0, output=f'Name Mtu Network Address Ipkts Ierrs Ibytes Opkts Oerrs Obytes Coll\nen0 1500 <Link#4> aa:bb:cc:dd:ee:ff 5 {errors} {rx} 6 0 {tx} 0\nen0 1500 10.0.0 10.0.0.2 5 - {rx} 6 - {tx} -\nen1* 1500 <Link#5> 0 0 0 0 0 0 0')


def run(args, **kwargs):
    return dict(exit=0, output='1\n' if 'kern.memorystatus_vm_pressure_level' in args else 'total = 1.00G used = 0.25G free = 0.75G (encrypted)')


class HostMetricsTests(unittest.TestCase):
    def test_rates_cpu_and_error_deltas_without_duplicate_address_rows(self):
        s = h.Sampler()
        first = s.sample(run, counters(), 'first', now=10, ticks=[10, 10, 80, 0])
        self.assertIsNone(first['cpu_busy_percent'])
        self.assertIsNone(first['interfaces']['en0']['rx_mbps'])
        second = s.sample(run, counters(7501000, 15002000, 2), 'second', now=70, ticks=[30, 20, 150, 0])
        self.assertEqual(second['cpu_busy_percent'], 30)
        self.assertEqual(second['interfaces']['en0']['rx_mbps'], 1)
        self.assertEqual(second['interfaces']['en0']['tx_mbps'], 2)
        self.assertEqual(second['interfaces']['en0']['rx_errors_delta'], 2)
        self.assertEqual(second['memory_pressure'], 'normal')
        self.assertEqual(second['swap_used_mib'], 256)
        self.assertNotIn('aa:bb', str(second))
        self.assertEqual(second['interfaces']['en1']['rx_mbps'], 0)

    def test_reset_gap_and_clock_reversal_are_unknown_not_negative_rates(self):
        for elapsed, ticks, expected in [(60, [1, 1, 1, 0], 'counter_reset_or_no_delta'), (200, [20, 20, 100, 0], 'gap'), (-1, [20, 20, 100, 0], 'gap')]:
            s = h.Sampler()
            s.sample(run, counters(), 'first', now=10, ticks=[10, 10, 80, 0])
            row = s.sample(run, counters(0, 0), 'next', now=10+elapsed, ticks=ticks)
            self.assertEqual(row['cpu_status'], expected)
            self.assertIsNone(row['cpu_busy_percent'])
            self.assertIsNone(row['interfaces']['en0']['rx_mbps'])

    def test_unavailable_breaks_baselines_and_never_becomes_zero(self):
        s = h.Sampler()
        s.sample(run, counters(), 'first', now=10, ticks=[10, 10, 80, 0])
        with patch.object(h, 'cpu_ticks', return_value=None):
            row = s.sample(lambda *a, **k: dict(exit=1, output='1'), dict(exit=1, output=''), 'next', now=70)
        self.assertEqual(row['memory_pressure'], 'unknown')
        self.assertIsNone(row['cpu_busy_percent'])
        self.assertIsNone(row['swap_used_mib'])
        self.assertEqual(row['interfaces'], {})
        resumed = s.sample(run, counters(), 'last', now=130, ticks=[20, 20, 100, 0])
        self.assertIsNone(resumed['cpu_busy_percent'])
        self.assertIsNone(resumed['interfaces']['en0']['rx_mbps'])
        self.assertEqual(h.interface_counters(dict(**counters(), truncated=True)), {})

    def test_load_comparison_keeps_failures_and_interfaces_separate(self):
        c = LoadComparison()
        for interface, active, ok, value in [('en0', True, True, 100), ('en0', True, False, 999), ('en0', False, True, 5), ('en1', False, True, 50), ('en0', None, True, 900)]:
            c.add(dict(network=dict(interface=interface), speed_test_active=active, checks=[dict(id='cloudflare_icmp', ok=ok, latency_ms=value)]))
        groups = c.summary()['groups']
        self.assertEqual(len(groups), 3)
        loaded = next(g for g in groups if g['speed_test_active'])
        self.assertEqual((loaded['attempted'], loaded['missed'], loaded['median_ms']), (2, 1, 100))
        self.assertEqual(LoadComparison().summary()['groups'], [])
