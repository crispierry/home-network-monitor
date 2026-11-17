from collections import defaultdict, deque
from array import array
import json
import statistics
import math
import time
import monitor as m


class LoadComparison:

    def __init__(self):
        self.groups = defaultdict(lambda: dict(attempted=0, missed=0, values=array('d')))

    def add(self, row):

        if not isinstance(row.get('speed_test_active'), bool):
            return
        for check in row.get('checks', []):
            if check.get('id') not in ('orbi_icmp', 'cloudflare_icmp', 'google_icmp'):
                continue
            group = self.groups[(row.get('network', {}).get('interface') or 'unknown', check['id'], row['speed_test_active'])]
            group['attempted'] += 1
            group['missed'] += not check['ok']
            value = check.get('latency_ms')
            if check['ok'] and isinstance(value, (int, float)) and not isinstance(value, bool) and math.isfinite(value) and value >= 0:
                group['values'].append(value)

    def summary(self):
        rows = []
        for (interface, target, active), group in sorted(self.groups.items()):
            values = sorted(group['values'])
            rows.append(dict(interface=interface, target=target, speed_test_active=active,
                attempted=group['attempted'], missed=group['missed'], replies_with_latency=len(values),
                median_ms=statistics.median(values) if values else None,
                p95_ms=values[math.ceil(len(values)*.95)-1] if values else None))
        return dict(groups=rows, interpretation='Tagged at probe-cycle start during this Mini’s speed test. Other samples may include household traffic or the other Mini’s test; they are not idle baselines. Successful replies only for latency; missed probes remain counted. Associations, not a controlled bufferbloat test or causal diagnosis.')


def records(root, prefix):
    yield from m.read_records(sorted(p for p in root.glob(prefix+'-*.jsonl') if not p.is_symlink() and p.is_file()))


def valid_sample(row):
    try:
        if not math.isfinite(m.epoch(row['started_at'])):
            return False
        cadence = row.get('interval_seconds', 15)
        if type(cadence) not in (int,float) or not 15 <= cadence <= 300:
            return False
        checks = row.get('checks')
        if not isinstance(checks, list) or len(checks)>100 or not isinstance(row.get('network',{}),dict):
            return False
        seen=set()
        for check in checks:
            name=check['id']; value=check.get('latency_ms')
            if not isinstance(name,str) or len(name)>100 or name in seen or type(check.get('ok')) is not bool:
                return False
            seen.add(name)
            if value is not None and (type(value) not in (int,float) or not math.isfinite(value) or value<0):
                return False
        return True
    except (ValueError,KeyError,TypeError,AttributeError,OverflowError):
        return False


def recent_performance(rows, now):

    paths = {}
    rows = sorted((r for r in rows if now-300 <= m.epoch(r['started_at']) <= now), key=lambda r: m.epoch(r['started_at']))
    for name in ('orbi_icmp', 'cloudflare_icmp', 'google_icmp'):
        values, changes, previous = [], [], None
        attempted, missed = 0, 0
        for row in rows:
            check = next((c for c in row.get('checks', []) if c['id'] == name), None)
            if check is None:
                previous = None
                continue
            attempted += 1
            missed += not check['ok']
            value = check.get('latency_ms') if check['ok'] else None
            if not isinstance(value, (int, float)) or isinstance(value, bool) or not math.isfinite(value) or value < 0:
                previous = None
                continue
            t, interface = m.epoch(row['started_at']), row.get('network', {}).get('interface')
            values.append(value)
            if previous is not None:
                before, x, cadence, path = previous
                if 0 < t-before <= cadence*1.5 and interface == path:
                    changes.append(abs(value-x))
            previous = (t, value, row.get('interval_seconds', 15), interface)
        values.sort()
        paths[name] = dict(attempted=attempted, missed=missed,
            loss_percent=100*missed/attempted if attempted else None,
            median_ms=statistics.median(values) if values else None,
            p95_ms=values[max(0, math.ceil(len(values)*.95)-1)] if values else None,
            mean_adjacent_rtt_change_ms=statistics.mean(changes) if changes else None)
    return dict(start=m.stamp(now-300), end=m.stamp(now), paths=paths,
        speed_test_overlap=any(r.get('speed_test_active', False) for r in rows),
        interpretation='Sparse 15-second ping evidence, not Zoom jitter or meeting quality. Failures, gaps and interface changes break delay-variation pairs. Observer CPU context is separate; Zoom media and the actual meeting computer are not collected. Compare the same time on both Minis and the actual meeting computer.')


def diagnostic_status(snapshot, now):
    snapshot = snapshot or {}
    completed = snapshot.get('finished_at')
    age = now-m.epoch(completed) if completed else None
    host_at = snapshot.get('host_metrics', {}).get('at')
    host_age = now-m.epoch(host_at) if host_at else None
    return dict(host_context_stale=host_age is None or not -5 <= host_age <= 180,
                host_context_age_seconds=round(host_age, 1) if host_age is not None else None,
                stale=snapshot.get('type') != 'diagnostic_snapshot' or age is None or not -5 <= age <= 180,
                sample_age_seconds=round(age, 1) if age is not None else None, latest=snapshot or None)


def briefing(root, hours=24, include_history=True, now=None):
    now = time.time() if now is None else now
    hours = max(1, min(168, hours))
    start = now-hours*3600
    state = m.read_state(root) or {}
    completed = state.get('last_completed_at')
    age = now-m.epoch(completed) if completed else None
    paused = bool(state.get('recording_paused')) or (root == m.DATA and (m.BASE/'monitoring-paused').exists())
    stale = paused or age is None or age < -5 or age > max(45, state.get('interval_seconds', 15)*3)
    checks = [r['latest'] for r in state.get('checks', {}).values() if 'latest' in r]
    internet = [r for r in checks if r['id'] in ('cloudflare_https', 'google_https')]
    health = 'unknown' if stale or len(internet) != 2 else 'reachable' if all(r['ok'] for r in internet) else 'partial' if any(r['ok'] for r in internet) else 'unreachable'
    devices = []
    for item in state.get('devices', []):
        row = dict(item)
        device_age = now-m.epoch(row['observed_at'])
        row.update(sample_age_seconds=round(device_age, 1), stale=stale or not -5 <= device_age <= 180)
        if row['stale']:
            row['status'] = 'unknown'
        devices.append(row)
    result = dict(schema='network-monitor.briefing.v1', generated_at=m.stamp(now),
        host=state.get('host'), source_directory=str(root), window=dict(start=m.stamp(start), end=m.stamp(now), hours=hours),
        recorder=dict(last_completed_at=completed, sample_age_seconds=round(age, 1) if age is not None else None, stale=stale, paused=paused),
        internet=health, network=state.get('network'), checks=checks, devices=devices,
        diagnostics=diagnostic_status(state.get('diagnostic_snapshot'), now),
        hypotheses=state.get('latest_hypotheses', []) if not stale else [],
        limitations=['Local outbound IPv4 observations; not whole-home coverage or camera cloud health.',
            'Each observer measures its own path, not Wi-Fi speed in every room. Device ping is reachability, not throughput.',
            'Attachment labels are dated inventory, not live associations. MAC matching is a guard, not authenticated identity.',
            'A local self-check does not traverse the network. No reply can mean sleep, filtering, changed IP or a fault.',
            'Missing/stale evidence is unknown. Imported snapshots do not update themselves; cross-computer sharing is optional.',
            'No remote alerts or per-device traffic accounting. Supplemental IPv6 and bounded route traces are context, not whole-path proof. Gateway snapshots can be unavailable during an outage.'])
    import investigation
    result['investigations'] = dict(reports=investigation.recent(root), note='Saved episodes, not current health; raw tool output is in investigations-*.jsonl. Nominal one-second close-ups may run slower on timeouts.')
    if not include_history:
        return result
    stats = defaultdict(lambda: dict(samples=0, failed=0, values=array('d')))
    coverage, cursor, count = 0.0, start, 0
    recent = []
    rejected = 0
    load = LoadComparison()
    for row in records(root, 'samples'):
        if not valid_sample(row):
            rejected += 1
            continue
        t = m.epoch(row['started_at'])
        if not start <= t <= now:
            continue
        count += 1
        load.add(row)
        if t >= now-300:
            recent.append(row)
        a, b = max(t, cursor), min(now, t+row.get('interval_seconds', 15))
        if b > a:
            coverage += b-a
            cursor = b
        for check in row.get('checks', []):
            stat = stats[check['id']]
            stat['samples'] += 1
            stat['failed'] += not check['ok']
            if check['ok'] and check.get('latency_ms') is not None:
                stat['values'].append(check['latency_ms'])
    for stat in stats.values():
        values = sorted(stat.pop('values'))
        stat.update(failure_percent=round(100*stat['failed']/stat['samples'], 3),
            median_ms=statistics.median(values) if values else None,
            p95_ms=values[min(len(values)-1, math.ceil(len(values)*.95)-1)] if values else None)
    incidents = state.get('recent_incidents', []) + ([state['incident']] if state.get('incident') else [])
    result.update(coverage=dict(observed_seconds=round(coverage, 1), window_seconds=hours*3600,
                               sample_count=count, note='Cadence-sized sampled intervals; gaps excluded. Not continuous uptime.'),
        check_statistics=dict(stats), incidents=[r for r in incidents if not r.get('recovered_at') or m.epoch(r['recovered_at']) >= start],
        device_events=[r for r in state.get('device_events', []) if m.epoch(r['at']) >= start],
        speed_tests=list(deque((r for r in records(root, 'performance') if start <= m.epoch(r['started_at']) <= now), maxlen=100)),
        evidence_files={'samples':'samples-*.jsonl', 'transitions':'events-*.jsonl', 'speeds':'performance-*.jsonl', 'diagnostics':'diagnostics-*.jsonl', 'investigations':'investigations-*.jsonl'},
        history_limits='Latest 20 completed network incidents, 200 device transitions and 100 speed tests; full retained events remain in JSONL.')
    result['recent_performance'] = recent_performance(recent, now)
    result['recent_performance']['stale'] = stale
    result['speed_test_latency_comparison'] = load.summary()
    result['reported_symptoms'] = list(deque((r for r in records(root, 'observations')
        if isinstance(r.get('time'), (int, float)) and start <= r['time'] <= now), maxlen=100))
    result['rejected_sample_records'] = rejected
    result['history_limits'] += ' Latest 100 reported symptoms included; these are user observations, not automated diagnoses.'
    return result
