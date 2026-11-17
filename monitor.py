#!/usr/bin/env python3

import argparse
from collections import deque
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
import fcntl
import hashlib
import html
import ipaddress
import json
import logging
import math
from logging.handlers import RotatingFileHandler
import os
from pathlib import Path
import re
import signal
import socket
import subprocess
import sys
import threading
import tempfile
import time
import uuid

VERSION = '2.7.1'
BASE = Path.home() / 'Library/Application Support/NetworkMonitor'
DATA = Path.home() / 'Library/Logs/NetworkMonitor'
DEFAULT = dict(interval_seconds=15, timeout_seconds=3, failure_threshold=2,
               recovery_threshold=2, expected_host='Mini-One', orbi='10.0.0.1',
               gateway='192.168.1.254', dns_name='example.com', peer='',
               satellites=[], speed_enabled=True, speed_hours=list(range(24)), speed_slot=0,
               speed_max_seconds=30)


def stamp(epoch=None):
    return datetime.fromtimestamp(time.time() if epoch is None else epoch,
                                  timezone.utc).isoformat(timespec='milliseconds')


def epoch(ts):
    return datetime.fromisoformat(ts).timestamp()


def command(args, timeout=4, limit=16384):
    try:
        p = subprocess.run(args, capture_output=True, text=True, timeout=timeout,
                           env={**os.environ, 'LC_ALL': 'C'})
        return p.returncode, p.stdout[:limit]
    except subprocess.TimeoutExpired:
        return 124, ''
    except OSError:
        return 127, ''


def identity():
    return {'hostname': socket.gethostname(),
            'computer_name': command(['/usr/sbin/scutil', '--get', 'ComputerName'])[1].strip(),
            'local_hostname': command(['/usr/sbin/scutil', '--get', 'LocalHostName'])[1].strip()}


def normalized(name):
    return re.sub('[^a-z0-9]', '', name.split('.')[0].lower())


def validate_host(expected):
    host = identity()
    if normalized(expected) not in {normalized(n) for n in host.values()}:
        raise ValueError(f"Expected {expected}; actual host is {host}. No service installed.")
    return host


def config(path):
    c = DEFAULT.copy()
    if path.exists():
        supplied = read_json(path, 65536)
        if not isinstance(supplied, dict):
            raise ValueError('Configuration must be a JSON object')
        if set(supplied) - set(DEFAULT):
            raise ValueError('Unknown config keys; credentials are never required')
        c.update(supplied)
    for key, lo, hi in [('interval_seconds', 15, 300), ('timeout_seconds', 1, 5),
                        ('failure_threshold', 1, 10), ('recovery_threshold', 1, 10)]:
        if type(c[key]) is not int or not lo <= c[key] <= hi:
            raise ValueError(f'{key} must be an integer in {lo}..{hi}')
    for key in ('orbi', 'gateway'):
        ipaddress.IPv4Address(c[key])
    if not isinstance(c['dns_name'], str) or not re.fullmatch(r'[a-zA-Z0-9][a-zA-Z0-9.-]{0,250}', c['dns_name']):
        raise ValueError('Invalid DNS name')
    if not isinstance(c['peer'], str) or (c['peer'] and not re.fullmatch(r'[a-zA-Z0-9][a-zA-Z0-9.-]{0,250}', c['peer'])):
        raise ValueError('peer must be an empty string or a valid hostname')
    if type(c['satellites']) is not list or len(c['satellites']) > 8:
        raise ValueError('satellites must contain at most eight confirmed IPv4 addresses')
    for address in c['satellites']:
        ipaddress.IPv4Address(address)
    if type(c['speed_enabled']) is not bool or type(c['speed_slot']) is not int or c['speed_slot'] not in (0, 1):
        raise ValueError('Invalid speed scheduling configuration')
    if type(c['speed_max_seconds']) is not int or not 10 <= c['speed_max_seconds'] <= 60:
        raise ValueError('speed_max_seconds must be in 10..60')
    if not isinstance(c['speed_hours'], list) or len(c['speed_hours']) > 24 or any(type(h) is not int or not 0 <= h <= 23 for h in c['speed_hours']):
        raise ValueError('speed_hours must contain at most 24 hours in 0..23')
    if not isinstance(c['expected_host'], str) or not re.fullmatch(r'[A-Za-z0-9][A-Za-z0-9.-]{0,250}', c['expected_host']):
        raise ValueError('Invalid expected host name')
    return c


def specs(c):
    out = []
    for name, target in [('orbi', c['orbi']), ('gateway', c['gateway']),
                         ('cloudflare', '1.1.1.1'), ('google', '8.8.8.8')]:
        out += [dict(id=name+'_icmp', kind='icmp', target=target),
                dict(id=name+'_tcp', kind='tcp', target=target,
                     port=80 if name in ('orbi', 'gateway') else 443)]
    out.append(dict(id='system_dns', kind='system_dns', target=c['dns_name']))
    for name, target in [('orbi', c['orbi']), ('cloudflare', '1.1.1.1'), ('google', '8.8.8.8')]:
        out.append(dict(id=name+'_dns', kind='dns', target=target, query=c['dns_name']))
    for name, target, hostname, path in [('cloudflare', '1.1.1.1', 'cloudflare-dns.com', '/dns-query'),
                                         ('google', '8.8.8.8', 'dns.google', '/resolve')]:
        out.append(dict(id=name+'_https', kind='https', target=target, hostname=hostname,
                        path=path+'?name='+c['dns_name']+'&type=A'))
    if c['peer']:
        out.append(dict(id='peer_icmp', kind='icmp', target=c['peer']))
    for index, address in enumerate(c['satellites']):
        out.append(dict(id=f'satellite_{index+1}_icmp', kind='icmp', target=address))
        out.append(dict(id=f'satellite_{index+1}_tcp', kind='tcp', target=address, port=80))
        out.append(dict(id=f'satellite_{index+1}_identity', kind='orbi_identity', target=address))
    return out


def probe(spec, timeout):
    start = time.monotonic()
    result = {**spec, 'started_at': stamp(), 'ok': False, 'latency_ms': None}
    detail = 'failed'
    try:
        if spec['kind'] == 'icmp':
            rc, out = command(['/sbin/ping', '-n', '-c', '1', '-W', str(timeout*1000),
                               spec['target']], timeout+0.5)
            match = re.search(r'time[=<]([\d.]+)\s*ms', out)
            result['ok'] = rc == 0 and match is not None
            if result['ok']:
                result['latency_ms'] = float(match.group(1))
            detail = f'ping_exit_{rc}'
            destination = re.search(r'^PING .*?\(([^)]+)\)', out)
            if destination:
                result['resolved_address'] = destination[1]
        elif spec['kind'] == 'tcp':

            with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
                sock.settimeout(timeout)
                sock.connect((spec['target'], spec['port']))
            result['ok'], detail = True, 'connected'
        elif spec['kind'] == 'dns':
            rc, out = command(['/usr/bin/dig', '@'+spec['target'], spec['query'], 'A',
                               '+time='+str(timeout), '+tries=1', '+noall', '+comments', '+answer'], timeout+0.5)
            status = re.search(r'status: (\w+)', out)
            result['ok'] = (rc == 0 and status is not None and status[1] == 'NOERROR'
                            and bool(re.search(r'\sIN\s+A\s+\d+\.\d+\.\d+\.\d+', out)))
            detail = 'dns_'+status[1] if status else f'dig_exit_{rc}'
        elif spec['kind'] == 'orbi_identity':
            rc, out = command(['/usr/bin/curl', '-q', '--silent', '--noproxy', '*', '--fail',
                               '--max-time', str(timeout), 'http://'+spec['target']+'/currentsetting.htm'], timeout+0.5)
            fields = dict(re.findall(r'^(Model|Firmware)=(.+?)\s*$', out, re.MULTILINE))
            result['ok'] = rc == 0 and fields.get('Model') == 'RBE770'
            result['identity'] = fields
            detail = 'verified_RBE770' if result['ok'] else 'identity_unverified_or_address_changed'
        elif spec['kind'] == 'https':
            rc, out = command(['/usr/bin/curl', '-q', '-4', '--silent', '--noproxy', '*',
                               '--connect-timeout', str(timeout), '--max-time', str(timeout),
                               '--resolve', f"{spec['hostname']}:443:{spec['target']}",
                               '-H', 'Accept: application/dns-json', '-o', '/dev/null', '-w',
                               '%{http_code}|%{time_connect}|%{time_appconnect}|%{time_starttransfer}|%{time_total}',
                               'https://'+spec['hostname']+spec['path']], timeout+0.5)
            parts = out.strip().split('|')
            status = parts[0] if re.fullmatch(r'\d{3}', parts[0]) else '000'
            result['ok'], detail = rc == 0 and status == '200', f'curl_exit_{rc}_http_{status}'


            timings = dict.fromkeys(('tcp_connected', 'tls_connected', 'first_byte', 'total'))
            if len(parts) == 5:
                for key, text in zip(timings, parts[1:]):
                    try:
                        value = float(text)
                        if math.isfinite(value) and value > 0:
                            timings[key] = round(value*1000, 3)
                    except ValueError:
                        pass
            result['https_timing_ms'] = timings
        else:

            rc, _ = command([sys.executable, '-c',
                             'import socket,sys; socket.getaddrinfo(sys.argv[1],443,socket.AF_INET,socket.SOCK_STREAM)',
                             spec['target']], timeout+0.5)
            result['ok'], detail = rc == 0, f'system_resolver_exit_{rc}'
    except OSError as exc:
        detail = type(exc).__name__ + (f'_{exc.errno}' if exc.errno else '')
    result['elapsed_ms'] = round((time.monotonic()-start)*1000, 3)
    if result['ok'] and result['latency_ms'] is None:
        result['latency_ms'] = result['elapsed_ms']
    result.update(finished_at=stamp(), detail=detail)
    return result


def hypotheses(checks):

    ok = {r['id']: r['ok'] for r in checks}
    up = lambda name: any(ok.get(name+'_'+p, False) for p in ('icmp', 'tcp', 'dns', 'https'))
    notes = []
    if any(r.get('detail') == 'OSError_65' for r in checks) and (up('cloudflare') or up('google')):
        notes.append('Hypothesis: local routing or macOS Local Network permission may block a probe; compare foreground and LaunchAgent results before attributing this to equipment.')
    public = [up('cloudflare'), up('google')]
    if not any(public):
        if not up('orbi'):
            notes.append('Hypothesis: local host/link, LAN, or Orbi trouble; upstream reachability is also lost.')
        elif not up('gateway'):
            notes.append('Hypothesis: Orbi forwarding/WAN link or gateway trouble; gateway management filtering is another possibility.')
        else:
            notes.append('Hypothesis: upstream forwarding, passthrough/WAN state, or AT&T service trouble; reachable gateway management does not prove fiber health.')
    elif not all(public):
        notes.append('Hypothesis: endpoint-specific, protocol-specific, or routing trouble; one public provider still responds.')
    if ok.get('cloudflare_dns') or ok.get('google_dns'):
        if not ok.get('system_dns') or not ok.get('orbi_dns'):
            notes.append('Hypothesis: local/system/Orbi DNS trouble; a direct public DNS query succeeded.')
    for name in ('orbi', 'gateway', 'cloudflare', 'google'):
        if not ok.get(name+'_icmp') and up(name):
            notes.append(f'Hypothesis: {name} ICMP filtering/deprioritization or loss; another protocol succeeded.')
        if ok.get(name+'_icmp') and not ok.get(name+'_tcp'):
            notes.append(f'Hypothesis: {name} TCP port unavailable or filtered; ICMP still responds.')
    if not notes and not all(ok.values()):
        notes.append('Hypothesis: isolated probe/protocol/DNS failure; inspect individual checks and baseline.')
    return notes


class Journal:

    def __init__(self, root, name, segment_bytes, count, days):
        self.root, self.name = root, name
        self.size, self.count, self.days = segment_bytes, count, days
        root.mkdir(parents=True, exist_ok=True, mode=0o700)

    def files(self):
        return sorted(p for p in self.root.glob(self.name+'-*.jsonl') if not p.is_symlink() and p.is_file())

    def append(self, record, now=None):


        with (self.root/(self.name+'.journal.lock')).open('a') as lock:
            fcntl.flock(lock, fcntl.LOCK_EX)
            return self._append(record, now)

    def _append(self, record, now=None):
        now = time.time() if now is None else now
        line = (json.dumps(record, separators=(',', ':'), ensure_ascii=True)+'\n').encode()
        if len(line) > self.size:
            raise ValueError('Journal record exceeds segment limit')
        files = self.files()
        for p in files:
            try:
                created = int(p.name.split('-')[1])/1e9
            except (ValueError, IndexError):
                created = p.stat().st_mtime
            if now-created > self.days*86400:
                p.unlink()
        files = self.files()
        if not files or files[-1].stat().st_size+len(line) > self.size:
            while len(files) >= self.count:
                files.pop(0).unlink()
            path = self.root / f'{self.name}-{int(now*1e9):020d}-{uuid.uuid4().hex[:8]}.jsonl'
        else:
            path = files[-1]

        if path.exists():
            with path.open('rb+') as f:
                f.seek(0, 2)
                length = f.tell()
                if length:
                    f.seek(-1, 2)
                    if f.read(1) != b'\n':
                        f.seek(max(0, length-self.size))
                        content = f.read()
                        end = content.rfind(b'\n')
                        f.truncate(max(0, length-self.size) + end+1)
        with path.open('ab') as f:
            f.write(line)
            f.flush()
            os.fsync(f.fileno())

    def records(self):
        yield from read_records(self.files(), self.size)


def read_records(paths, limit=8*1024**2):
    for p in paths:
        try:
            with p.open('rb') as f:
                while line := f.readline(limit+1):
                    if len(line) > limit or not line.endswith(b'\n'):
                        while line and not line.endswith(b'\n'):
                            line = f.readline(limit+1)
                        continue
                    try:
                        value = json.loads(line)
                        if isinstance(value, dict):
                            yield value
                    except (ValueError, UnicodeError, RecursionError):
                        continue
        except FileNotFoundError:
            continue


def journals(data):
    return (Journal(data, 'samples', 8*1024**2, 32, 30),
            Journal(data, 'events', 1024**2, 16, 180))


def read_json(path, limit=1024*1024):
    if path.is_symlink():
        raise ValueError('Symbolic links are not accepted for evidence or settings')
    with path.open('rb') as handle:
        data = handle.read(limit+1)
    if len(data) > limit:
        raise ValueError('JSON exceeds the supported size limit')
    try:
        value = json.loads(data, parse_constant=lambda _: (_ for _ in ()).throw(ValueError('Nonfinite JSON number')))
        pending = [(value, 0)]
        while pending:
            node, depth = pending.pop()
            if depth > 64:
                raise ValueError('JSON nesting exceeds supported depth')
            if isinstance(node, float) and not math.isfinite(node):
                raise ValueError('Nonfinite JSON number')
            if isinstance(node, dict):
                pending.extend((child, depth+1) for child in node.values())
            elif isinstance(node, list):
                pending.extend((child, depth+1) for child in node)
        return value
    except RecursionError as exc:
        raise ValueError('JSON nesting exceeds supported depth') from exc


def atomic(path, text):
    if path.is_symlink():
        raise ValueError('Refusing to replace a symbolic link')
    fd, name = tempfile.mkstemp(prefix='.'+path.name+'.', suffix='.tmp', dir=path.parent)
    temporary = Path(name)
    try:
        with os.fdopen(fd, 'w') as handle:
            handle.write(text)
            handle.flush()
            os.fsync(handle.fileno())
        temporary.replace(path)
    finally:
        temporary.unlink(missing_ok=True)


class Detector:
    def __init__(self, c, state=None):
        self.c = c
        fingerprint = hashlib.sha256(json.dumps(c, sort_keys=True).encode()).hexdigest()
        if state and state.get('config_hash') != fingerprint:
            raise ValueError('Configuration changed; archive state.json before restarting (see README)')
        self.state = state or dict(schema=1, config_hash=fingerprint, checks={}, incident=None,
                                   recent_incidents=[], last_sample=None)

    def update(self, sample):
        s, events, now = self.state, [], sample['started_at']
        previous = s.get('last_sample')
        gap = previous and (epoch(now)-epoch(previous) > self.c['interval_seconds']*3 or epoch(now)<epoch(previous))
        if gap:
            events.append(dict(type='monitor_gap', after=previous, before=now,
                               note='No observations in this interval; continuity and exact recovery unknown.'))
            for check in s['checks'].values():
                check.update(fail_count=0, pass_count=0)
            if s['incident']:
                s['incident']['has_observation_gap'] = True
        for result in sample['checks']:
            key, at = result['id'], result['started_at']
            st = s['checks'].setdefault(key, dict(down=False, fail_count=0, pass_count=0, last_success=None))
            if not result['ok']:
                st['pass_count'] = 0
                if st['fail_count'] == 0:
                    st['first_failure'] = at
                    st['last_success_before_failure'] = st['last_success']
                st['fail_count'] += 1
                if not st['down'] and st['fail_count'] >= self.c['failure_threshold']:
                    st['down'] = True
                    episode = dict(check=key, first_failed_at=st['first_failure'],
                                   last_success_at=st['last_success_before_failure'], confirmed_at=at,
                                   first_recovered_at=None, recovery_confirmed_at=None)
                    st['episode'] = episode
                    if s['incident'] is None:
                        s['incident'] = dict(id=uuid.uuid4().hex[:12], started_at=st['first_failure'],
                                             confirmed_at=at, recovered_at=None, episodes=[],
                                             has_observation_gap=False, hypotheses=[])
                        events.append(dict(type='incident_started', incident_id=s['incident']['id']))
                    inc = s['incident']
                    inc['started_at'] = min(inc['started_at'], episode['first_failed_at'])

                    inc['episodes'] = (inc['episodes'] + [dict(episode)])[-100:]
                    events.append(dict(type='check_failed', incident_id=inc['id'], **episode))
            else:
                st['fail_count'] = 0
                st['last_success'] = at
                if st['pass_count'] == 0:
                    st['first_recovery'] = at
                st['pass_count'] += 1
                if st['down'] and st['pass_count'] >= self.c['recovery_threshold']:
                    st['down'] = False
                    episode = st['episode']
                    episode.update(first_recovered_at=st['first_recovery'], recovery_confirmed_at=at)
                    inc = s['incident']
                    if inc:
                        for item in reversed(inc['episodes']):
                            if item['check'] == key and item['recovery_confirmed_at'] is None:
                                item.update(episode)
                                break
                        events.append(dict(type='check_recovered', incident_id=inc['id'], **episode))
            st['fail_count'] = min(st['fail_count'], self.c['failure_threshold'])
            st['pass_count'] = min(st['pass_count'], self.c['recovery_threshold'])
            st['latest'] = result
        if s['incident']:
            inc = s['incident']
            inc['hypotheses'] = list(dict.fromkeys(inc['hypotheses']+hypotheses(sample['checks'])))[:20]
            if not any(st['down'] for st in s['checks'].values()):
                inc['recovered_at'] = max(e['first_recovered_at'] for e in inc['episodes'] if e['first_recovered_at'])
                inc['recovery_confirmed_at'] = now
                events.append(dict(type='incident_recovered', incident=dict(inc)))
                s['recent_incidents'] = (s['recent_incidents']+[inc])[-20:]
                s['incident'] = None
        s.update(last_sample=now, last_completed_at=sample['finished_at'], host=sample['host'],
                 interval_seconds=self.c['interval_seconds'], latest_hypotheses=hypotheses(sample['checks']))
        return [dict(at=now, **event) for event in events]


def diagnostics():
    rc, route = command(['/sbin/route', '-n', 'get', 'default'])
    match = re.search(r'interface:\s+(\w+)', route)
    link = ''
    if match:
        _, output = command(['/sbin/ifconfig', match[1]])
        link = '\n'.join(l for l in output.splitlines() if any(x in l for x in ('flags=', 'inet ', 'ether ', 'media:', 'status:')))
    _, dns = command(['/usr/sbin/scutil', '--dns'])
    dns = '\n'.join(l.strip() for l in dns.splitlines() if 'nameserver[' in l)
    return dict(route_exit=rc, default_route=route, interface=match[1] if match else None,
                active_link=link, nameservers=dns)


def wifi_snapshot():
    helper = BASE/'wifi-observer'
    if helper.is_file() and not helper.is_symlink():
        rc, out = command([str(helper)], 3, limit=8192)
        try:
            value = json.loads(out)
            if rc == 0 and isinstance(value,dict) and value.get('source') == 'CoreWLAN':
                return dict(value, at=stamp())
        except (ValueError,TypeError):
            pass
        return dict(at=stamp(),status='unavailable',source='CoreWLAN',tool_exit=rc)
    rc, out = command(['/usr/sbin/system_profiler', 'SPAirPortDataType', '-json'], 10, limit=262144)
    result = dict(at=stamp(), status='unavailable', bssid='unavailable (not exposed without additional permissions)')
    try:
        for group in json.loads(out).get('SPAirPortDataType', []):
            for interface in group.get('spairport_airport_interfaces', []):
                current = interface.get('spairport_current_network_information', {})
                if 'spairport_network_rate' in current:
                    result.update(status='available', interface=interface['_name'],
                                  signal_noise=current.get('spairport_signal_noise'),
                                  rate_mbps=current.get('spairport_network_rate'),
                                  channel=current.get('spairport_network_channel'),
                                  phy=current.get('spairport_network_phymode'))
    except (ValueError, TypeError):
        result['tool_exit'] = rc
    return result


def read_state(data):
    try:
        value = read_json(data/'state.json')
        if not isinstance(value, dict):
            raise ValueError('Recorder checkpoint must be an object')
        return value
    except FileNotFoundError:
        return None


def report(state):
    if not state:
        return 'No samples recorded.'
    age = time.time()-epoch(state['last_completed_at'])
    stale = age > state['interval_seconds']*3 or age < -5
    latest = [v['latest'] for v in state['checks'].values()]
    health = 'STALE / monitoring gap' if stale else ('DEGRADED' if not all(r['ok'] for r in latest) else 'All checks passing')
    lines = [health, f"Host: {state['host']['hostname']}",
             f"Last complete: {state['last_completed_at']} ({age:.0f}s ago)",
             'Times are UTC; first observations bound transitions, not exact physical failure times.', '']
    lines += [f"Active route/interface: {state.get('network', {}).get('interface', 'unknown')}",
              f"Speed-test load at sample time: {state.get('speed_test_active', False)}", '']
    lines += [f"Mesh inventory: {state.get('satellites_configured', 0)} satellite addresses configured; attachment/backhaul is not continuously observed.",
              'Wi-Fi AP/BSSID: '+(state.get('wifi') or {}).get('bssid', 'unavailable'), '']
    for r in latest:
        lines.append(f"{r['id']:19} {'PASS' if r['ok'] else 'FAIL':4}  {str(r['latency_ms']):>9} ms  {r['detail']}")
    lines += [''] + state.get('latest_hypotheses', [])
    if state.get('devices'):
        lines += ['', 'Watched devices (local replies, not cloud health):']
        for device in state['devices']:
            device_age = time.time()-epoch(device['observed_at'])
            status = 'unknown / stale' if stale or not -5 <= device_age <= 180 else device['status']
            lines.append(f"  {device['name']}: {status}; identity {device['identity']}; last reply {device.get('last_reply_at') or 'none'}")
    for inc in ([state['incident']] if state['incident'] else []) + list(reversed(state['recent_incidents'][-5:])):
        lines += ['', f"Incident {inc['id']}: {inc['started_at']} → {inc['recovered_at'] or 'OPEN'}",
                  f"Observation gap: {inc['has_observation_gap']}"]
        for e in inc['episodes']:
            lines.append(f"  {e['check']}: failed {e['first_failed_at']}; recovered {e['first_recovered_at'] or 'not yet'}")
        lines += inc['hypotheses']
    return '\n'.join(lines)


def page(state):

    return '''<!doctype html><meta charset="utf-8"><meta http-equiv="refresh" content="30">
<title>Network Monitor</title><style>body{font:16px system-ui;max-width:1100px;margin:3em auto;padding:1em;background:#f7f8fa;color:#183047}pre{white-space:pre-wrap;line-height:1.6}h1{font-size:28px}</style>
<h1>Network Monitor</h1><p id="fresh"></p><pre>'''+html.escape(report(state))+'''</pre><script>
const last='''+json.dumps(state['last_completed_at'])+''';
const staleAfter='''+str(state['interval_seconds']*3)+''';
function fresh(){const age=(Date.now()-Date.parse(last))/1000;document.getElementById('fresh').textContent=(age>staleAfter || age < -5?'STALE — no recent observations. ':'')+'Sample age: '+Math.round(age)+' seconds. All recorded timestamps are UTC.';}fresh();setInterval(fresh,1000);
</script>'''


def completed_auxiliary(future, name, events):

    try:
        return True, future.result()
    except Exception as exc:
        events.append(dict(type='collector_error', at=stamp(), collector=name, error=type(exc).__name__))
        return False, None


def run(c, data, once=False, enforce_host=True):
    if enforce_host:
        validate_host(c['expected_host'])
    os.umask(0o077)
    data.mkdir(parents=True, exist_ok=True, mode=0o700)
    os.chmod(data, 0o700)
    lock = (data/'monitor.lock').open('w')
    try:
        fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
    except BlockingIOError:
        raise ValueError('Another monitor already owns this data directory')
    samples, events = journals(data)
    detector = Detector(c, read_state(data))
    host = identity()
    events.append(dict(type='monitor_started', at=stamp(), host=host, version=VERSION))
    stop = threading.Event()
    for sig in (signal.SIGTERM, signal.SIGINT):
        signal.signal(sig, lambda *_: stop.set())
    import performance
    import devices
    import diagnostics as context
    import host_metrics
    import investigation
    host_sampler = host_metrics.Sampler()
    inventory = devices.inventory(BASE/'devices.json')
    watched = detector.state.get('devices', [])
    device_future, last_devices = None, -devices.INTERVAL
    last_diag, last_wifi, wifi, speed_future, wifi_future = 0, 0, None, None, None
    context_schedule, context_future = context.Schedule(), None
    context_journal = context.journal(data)
    closeup_schedule, closeup_future = investigation.Trigger(data), None
    with ThreadPoolExecutor(max_workers=16) as pool, ThreadPoolExecutor(max_workers=1) as speed_pool, ThreadPoolExecutor(max_workers=1) as device_pool, ThreadPoolExecutor(max_workers=1) as context_pool, ThreadPoolExecutor(max_workers=1) as wifi_pool, ThreadPoolExecutor(max_workers=1) as closeup_pool:
        while not stop.is_set():
            started = time.monotonic()
            if device_future is None and started-last_devices >= devices.INTERVAL and inventory:
                device_future = device_pool.submit(devices.collect, inventory, c['timeout_seconds'])
                last_devices = started
            sample = dict(type='sample', started_at=stamp(), host=host, version=VERSION,
                          interval_seconds=c['interval_seconds'])
            sample['network'] = diagnostics()
            sample['speed_test_active'] = performance.active(data)
            sample['checks'] = list(pool.map(lambda s: probe(s, c['timeout_seconds']), specs(c)))
            sample['finished_at'] = stamp()
            if closeup_future is not None and closeup_future.done():
                completed_auxiliary(closeup_future, 'close_up', events)
                closeup_future = None
            trigger = closeup_schedule.due(sample, time.monotonic(), busy=closeup_future is not None)
            if trigger and not once:
                closeup_future = closeup_pool.submit(investigation.burst, c, data, trigger, stop)
            context_schedule.observe(sample)
            if context_future is not None and context_future.done():
                try:
                    snapshot = context_future.result()
                except Exception as exc:

                    snapshot = dict(type='diagnostic_error', at=stamp(), error=type(exc).__name__)
                context_journal.append(snapshot)
                detector.state['diagnostic_snapshot'] = snapshot
                context_future = None
            scheduled = context_schedule.due(time.monotonic(), busy=context_future is not None)
            if scheduled:
                trigger, trace = scheduled
                context_future = context_pool.submit(context.collect, c, trigger, trace, host_sampler)
            if wifi_future is not None and wifi_future.done():
                ok, value = completed_auxiliary(wifi_future, 'wifi', events)
                wifi = value if ok else dict(at=stamp(), status='unavailable')
                wifi_future = None
            slow = any(p['id']=='orbi_icmp' and p['ok'] and (p.get('latency_ms') or 0)>30 for p in sample['checks'])
            if wifi_future is None and (last_wifi == 0 or started-last_wifi >= (30 if slow else 60)):
                wifi_future = wifi_pool.submit(wifi_snapshot)
                last_wifi = started
            sample['wifi'] = wifi
            device_events = []
            if device_future is not None and device_future.done():
                ok, value = completed_auxiliary(device_future, 'devices', events)
                if ok:
                    try:
                        watched, device_events = devices.update(value, watched)
                        sample['device_observations'] = watched
                    except Exception as exc:
                        events.append(dict(type='collector_error', at=stamp(), collector='device_update', error=type(exc).__name__))
                device_future = None


            samples.append(sample)
            changes = detector.update(sample) + device_events
            detector.state.update(network=sample['network'], wifi=wifi,
                                  speed_test_active=sample['speed_test_active'], satellites_configured=len(c['satellites']),
                                  devices=watched, device_interval_seconds=devices.INTERVAL,
                                  device_events=(detector.state.get('device_events', [])+device_events)[-200:])
            for event in changes:
                events.append(event)
            if changes or started-last_diag >= 900 or last_diag == 0:
                events.append(dict(type='diagnostics', at=sample['started_at'], **sample['network']))
                last_diag = started
            atomic(data/'state.json', json.dumps(detector.state, indent=2)+'\n')
            atomic(data/'status.html', page(detector.state))
            if not once and (speed_future is None or speed_future.done()):
                if speed_future is not None:
                    completed_auxiliary(speed_future, 'speed_test', events)
                try:
                    speed_due = performance.due(c, data)
                except (ValueError, OSError, TypeError, KeyError) as exc:
                    events.append(dict(type='collector_error', at=stamp(), collector='speed_schedule', error=type(exc).__name__))
                    speed_due = False
                speed_future = speed_pool.submit(performance.execute, c, data, False) if speed_due else None
            if once:
                print(report(detector.state))
                break
            stop.wait(max(1, c['interval_seconds']-(time.monotonic()-started)))
        if context_future is not None:
            try:
                snapshot = context_future.result()
            except Exception as exc:
                snapshot = dict(type='diagnostic_error', at=stamp(), error=type(exc).__name__)
            context_journal.append(snapshot)
    events.append(dict(type='monitor_stopped', at=stamp()))
    lock.close()


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--data-dir', type=Path, default=DATA)
    p.add_argument('--config', type=Path, default=BASE/'config.json')
    sub = p.add_subparsers(dest='action', required=True)
    sub.add_parser('run')
    sub.add_parser('once')
    speed_parser = sub.add_parser('speed')
    speed_parser.add_argument('--history', action='store_true')
    speed_parser.add_argument('--json', action='store_true', help='Include the raw measurement evidence')
    sub.add_parser('summary').add_argument('--hours', type=int, default=24)
    cp = sub.add_parser('correlate')
    cp.add_argument('other_data', type=Path)
    cp.add_argument('--hours', type=int, default=24)
    sub.add_parser('status').add_argument('--json', action='store_true')
    qp = sub.add_parser('query', help='Read-only, versioned JSON briefing for local agents')
    qp.add_argument('--all-hosts', action='store_true', help='Read local and validated peer evidence without networking')
    qp.add_argument('--hours', type=int, choices=range(1, 169), default=24, metavar='1..168')
    sub.add_parser('devices', help='Read current device evidence as JSON')
    import investigation
    investigation.cli(sub.add_parser('investigate', help='Bounded close-ups, route reports and controlled LAN tests'))
    for name in ('incidents', 'raw', 'diagnostics'):
        sp = sub.add_parser(name)
        sp.add_argument('--limit', type=int, default=20)
        sp.add_argument('--since', help='ISO timestamp with timezone, e.g. 2026-11-16T00:00:00-08:00')
    args = p.parse_args()
    if args.action == 'run':
        os.umask(0o077)
        args.data_dir.mkdir(parents=True, exist_ok=True, mode=0o700)
        handler = RotatingFileHandler(args.data_dir/'service.log', maxBytes=1024**2, backupCount=3)
        logging.basicConfig(handlers=[handler], level=logging.WARNING)
    try:
        if args.action in ('run', 'once'):
            run(config(args.config), args.data_dir, once=args.action=='once')
        elif args.action in ('query', 'devices'):
            import agent_query
            if args.action == 'query' and args.all_hosts:
                import sync
                value = sync.all_hosts(args.data_dir, hours=args.hours)
            else:
                value = agent_query.briefing(args.data_dir, args.hours if args.action == 'query' else 24,
                                             include_history=args.action == 'query')
            print(json.dumps(value, indent=2, allow_nan=False))
        elif args.action == 'investigate':
            c = config(args.config) if args.investigation_action not in ('status','history') else None
            print(json.dumps(investigation.main(args, c), indent=2, allow_nan=False))
        elif args.action == 'status':
            state = read_state(args.data_dir)
            print(json.dumps(state, indent=2) if args.json else report(state))
        elif args.action == 'speed':
            import performance
            if args.history:
                for row in deque(performance.journal(args.data_dir).records(), maxlen=20):
                    print(json.dumps(row) if args.json else performance.report(row))
            else:
                c = config(args.config)
                validate_host(c['expected_host'])
                row = performance.execute(c, args.data_dir, True)
                print(json.dumps(row, indent=2) if args.json else performance.report(row))
        elif args.action in ('summary', 'correlate'):
            import analysis
            if args.action == 'summary':
                print(analysis.summary(args.data_dir, args.hours))
            else:
                print(analysis.correlate(args.data_dir, args.other_data, args.hours))
        else:
            samples, events = journals(args.data_dir)
            if args.action == 'diagnostics':
                import diagnostics
                source = diagnostics.journal(args.data_dir)
            else:
                source = samples if args.action == 'raw' else events
            records = source.records()
            if args.action == 'incidents':
                records = (r for r in records if r.get('type') not in ('diagnostics',))
            if args.since:
                since = epoch(args.since)
                records = (r for r in records if epoch(r.get('started_at', r.get('at'))) >= since)
            for row in deque(records, maxlen=max(1, min(args.limit, 100000))):
                print(json.dumps(row))
    except (OSError, ValueError) as exc:
        if args.action == 'run':
            logging.error('%s: %s', type(exc).__name__, exc)
        print(f'Network Monitor: {exc}', file=sys.stderr)
        return 1
    return 0


if __name__ == '__main__':
    try:
        sys.exit(main())
    except Exception:
        logging.exception('Monitor stopped unexpectedly')
        sys.exit(1)
