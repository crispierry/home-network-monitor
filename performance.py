from datetime import datetime
import fcntl
import json
import math
import os
from pathlib import Path
import subprocess
import time
from zoneinfo import ZoneInfo

import monitor as m

ZONE = ZoneInfo('America/Los_Angeles')
SCHEDULE_MINUTES = (15, 45)


def report(record):
    def value(key, unit):
        number = record.get(key)
        return 'unavailable' if number is None else f'{number:.1f} {unit}'
    return (f"{record.get('started_at', 'unknown time')} | {record.get('status', 'unknown')} | "
            f"down {value('download_mbps', 'Mbps')} | up {value('upload_mbps', 'Mbps')} | "
            f"idle {value('idle_latency_ms', 'ms')} | "
            f"loaded down/up {value('download_responsiveness_rpm', 'RPM')}/{value('upload_responsiveness_rpm', 'RPM')}"
            + (' | '+record['reason'] if record.get('reason') else ''))


def journal(data):
    return m.Journal(data, 'performance', 1024**2, 8, 180)


def read(path):
    try:
        value = m.read_json(path, 65536)
        if not isinstance(value, dict):
            raise ValueError('Expected a speed-state object')
        return value
    except FileNotFoundError:
        return {}


def active(data):
    try:
        state = read(data/'speed-active.json')
        until = state.get('active_until', 0)
        return until > time.time() if type(until) in (float, int) and math.isfinite(until) else None
    except (ValueError, OSError, AttributeError):
        return None


def allowed(c, now=None):


    now = time.time() if now is None else now
    local = datetime.fromtimestamp(now, ZONE)
    into = local.minute*60 + local.second + local.microsecond/1e6
    start = SCHEDULE_MINUTES[c['speed_slot']]*60
    return start+30 <= into < start+300-c['speed_max_seconds']-35


def due(c, data, now=None):
    now = time.time() if now is None else now
    local = datetime.fromtimestamp(now, ZONE)
    minute = SCHEDULE_MINUTES[c['speed_slot']]
    if not c['speed_enabled'] or local.hour not in c['speed_hours'] or local.minute not in (minute, minute+1, minute+2):
        return False
    if not allowed(c, now):
        return False
    key = local.strftime('%Y-%m-%dT%H')
    schedule = read(data/'speed-schedule.json')
    if schedule.get('last_slot') == key:
        return False

    m.atomic(data/'speed-schedule.json', json.dumps({'last_slot': key, 'claimed_at': m.stamp(now)}))
    return True


def measurements(raw, returncode):
    if not isinstance(raw, dict):
        raw = {}
    def number(key):
        value = raw.get(key)
        return value if type(value) in (float, int) and math.isfinite(value) and value > 0 else None
    down, up = number('dl_throughput'), number('ul_throughput')
    return dict(status=('error' if returncode else 'incomplete' if down is None or up is None else 'success'),
                download_mbps=down/1e6 if down is not None else None,
                upload_mbps=up/1e6 if up is not None else None,
                idle_latency_ms=number('base_rtt'),
                download_responsiveness_rpm=number('dl_responsiveness'),
                upload_responsiveness_rpm=number('ul_responsiveness'))


def execute(c, data, manual):
    os.umask(0o077)
    data.mkdir(parents=True, exist_ok=True, mode=0o700)
    record = dict(type='speed_test', started_at=m.stamp(), host=m.identity(), manual=manual)
    def skipped(reason):
        record.update(status='skipped', reason=reason, finished_at=m.stamp())
        journal(data).append(record)
        return record
    if (data == m.DATA and (m.BASE/'monitoring-paused').exists()):
        return skipped('Monitoring is paused')
    if not allowed(c):
        return skipped('Outside this host\'s time window; retry in its next five-minute slot (see README).')
    with (data/'speed.lock').open('w') as lock:
        try:
            fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            return skipped('Another local speed test is running')
        state = m.read_state(data)
        age = time.time()-m.epoch(state['last_completed_at']) if state else None
        if age is None or age < -5 or age > c['interval_seconds']*3:
            return skipped('No fresh health sample')
        checks = state.get('checks', {})
        expected = {spec['id'] for spec in m.specs(c)}
        if state.get('recording_paused') or (data == m.DATA and (m.BASE/'monitoring-paused').exists()):
            return skipped('Monitoring is paused')
        if state.get('incident') or not expected <= checks.keys() or not all(v.get('latest', {}).get('ok') and v.get('pass_count', 0) >= 2 for v in checks.values()):
            return skipped('Active incident, failing check, or not yet two healthy samples')
        route = m.diagnostics()
        interface = route['interface']
        record['network_before'] = route
        if not interface:
            return skipped('No active route/interface')

        import investigation
        context = None
        try:
            context = investigation.LoadCapture(c, data)
            context.start()
        except Exception as exc:
            record['latency_capture_error'] = type(exc).__name__
            context = None
        try:
            latest = m.read_state(data) or {}
            latest_checks = latest.get('checks', {})
            latest_age = time.time()-m.epoch(latest['last_completed_at']) if latest.get('last_completed_at') else None
            if latest_age is None or not -5 <= latest_age <= c['interval_seconds']*3 or investigation.paused(data) or latest.get('recording_paused') or latest.get('incident') or not expected <= latest_checks.keys() or not all(v.get('latest', {}).get('ok') for v in latest_checks.values()):
                return skipped('Monitoring paused or health changed during preparation')
            args = ['/usr/bin/networkQuality', '-c', '-s', '-I', interface, '-M', str(c['speed_max_seconds'])]
            until = time.time()+c['speed_max_seconds']+5
            m.atomic(data/'speed-active.json', json.dumps(dict(started_at=record['started_at'], active_until=until)))
            raw, rc = {}, 127
            try:
                p = subprocess.run(args, capture_output=True, text=True, timeout=c['speed_max_seconds']+5)
                rc = p.returncode
                try:
                    raw = json.loads(p.stdout)
                except ValueError:
                    pass
            except subprocess.TimeoutExpired:
                rc = 124
            except OSError:
                rc = 127
            finally:
                finished_at = m.stamp()
                m.atomic(data/'speed-active.json', json.dumps(dict(active_until=0, finished_at=finished_at)))
                if context:
                    try:
                        captured = context.finish()
                        record['latency_capture_id'] = captured['id']
                    except Exception as exc:
                        record['latency_capture_error'] = type(exc).__name__
            record.update(finished_at=finished_at, exit_code=rc, **measurements(raw, rc), raw=raw,
                          network_after=m.diagnostics(), requested_interface=interface)
            if record['network_after']['interface'] != interface:
                record.update(status='incomplete', reason='Default route changed during the bound-interface test')
            journal(data).append(record)
            return record
        finally:
            if context: context.close()
