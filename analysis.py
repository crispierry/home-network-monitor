from collections import defaultdict, deque
from array import array
import statistics
import math
import time
import monitor as m
import performance


def summary(data, hours):
    since = time.time()-max(1, hours)*3600
    checks = {}
    for row in m.journals(data)[0].records():
        if m.epoch(row['started_at']) < since:
            continue
        interface, cadence = row.get('network', {}).get('interface'), row.get('interval_seconds', 15)
        for check in row['checks']:
            stat = checks.setdefault(check['id'], dict(n=0, failed=0, values=array('d'), step_sum=0., step_count=0, previous=None))
            stat['n'] += 1
            stat['failed'] += not check['ok']
            latency = check['latency_ms'] if check['ok'] else None
            at = m.epoch(check['started_at'])
            if latency is not None:
                stat['values'].append(latency)
                previous = stat['previous']
                if previous and previous[1] is not None and previous[2] == interface and 0 < at-previous[0] <= previous[3]*1.5:
                    stat['step_sum'] += abs(latency-previous[1])
                    stat['step_count'] += 1
            stat['previous'] = (at, latency, interface, cadence)
    lines = [f'Last {hours} hours (observed samples only; gaps are not successes or losses).',
             'Check                 n    failed%  median_ms  p95_ms  mean_step_ms']
    for name, stat in checks.items():
        values = sorted(stat['values'])
        fmt = lambda x: f'{x:.2f}' if x is not None else 'n/a'
        median = statistics.median(values) if values else None
        p95 = values[min(len(values)-1, math.ceil(len(values)*.95)-1)] if values else None
        step = stat['step_sum']/stat['step_count'] if stat['step_count'] else None
        lines.append(f'{name:21} {stat["n"]:5} {100*stat["failed"]/stat["n"]:9.2f} {fmt(median):>10} {fmt(p95):>8} {fmt(step):>13}')
    lines += ['ICMP failed% is sampled packet loss; other failed% values describe probe failures.',
              'Mean step is successive successful latency variation, not RFC jitter. Speed-test load is included.']
    return '\n'.join(lines)


def correlate(first, second, hours):
    since = time.time()-max(1, hours)*3600
    buckets = defaultdict(dict)
    windows = []
    for data in (first, second):
        for row in performance.journal(data).records():
            if row.get('status') not in ('skipped',) and row.get('finished_at'):
                windows.append((m.epoch(row['started_at']), m.epoch(row['finished_at'])))
        for row in m.journals(data)[0].records():
            t = m.epoch(row['started_at'])
            if t < since:
                continue
            host = row['host']['hostname']
            value = buckets[int(t//60)*60].setdefault(host, dict(failed=set(), samples=0, interfaces=set()))
            value['samples'] += 1
            value['failed'].update(c['id'] for c in row['checks'] if not c['ok'])
            value['interfaces'].add(str(row.get('network', {}).get('interface')))
    hosts = sorted({host for bucket in buckets.values() for host in bucket})
    lines = ['UTC minute | '+ ' | '.join(hosts)+' | speed load (either host)',
             'Missing means no observation. Any failures within the minute are listed; this is correlation, not causation.']
    if buckets:
        for t in range(min(buckets), max(buckets)+60, 60):
            row = buckets.get(t, {})
            cells = []
            for host in hosts:
                v = row.get(host)
                cells.append('MISSING' if not v else f"{v['samples']} samples; {','.join(sorted(v['interfaces']))}; "+(','.join(sorted(v['failed'])) or 'PASS'))
            lines.append(m.stamp(t)+' | '+' | '.join(cells)+' | '+str(any(a<t+60 and b>=t for a,b in windows)))
    return '\n'.join(lines)
