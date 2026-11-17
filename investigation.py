from collections import deque
from concurrent.futures import ThreadPoolExecutor
from contextlib import contextmanager
import fcntl
import ipaddress
import json
import math
import os
import re
from pathlib import Path
import statistics
import subprocess
import tempfile
import threading
import time
import uuid

import monitor as m

SCHEMA = 'network-monitor.investigation.v1'
TARGETS = ('orbi_icmp', 'cloudflare_icmp', 'google_icmp')
NAMES = {'orbi_icmp':'Main Orbi', 'cloudflare_icmp':'Cloudflare', 'google_icmp':'Google'}
MAX_OUTPUT = 65536


def journal(data):
    return m.Journal(data, 'investigations', 2*1024**2, 4, 30)


def recent(data):
    try:
        path = data/'investigation-latest.json'
        if path.stat().st_size > 512*1024: return []
        value = m.read_json(path, 512*1024)
        return [r for r in value if isinstance(r,dict) and type(r.get('end')) in (int,float) and time.time()-30*86400 <= r['end'] <= time.time()+5] if isinstance(value, list) and len(value) <= 4 else []
    except (OSError, ValueError):
        return []


def paused(data):
    return data == m.DATA and (m.BASE/'monitoring-paused').exists()


@contextmanager
def exclusive(data, name):
    os.umask(0o077)
    data.mkdir(parents=True, exist_ok=True, mode=0o700)
    with (data/name).open('a') as lock:
        try: fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError: raise ValueError('Another diagnostic or speed test is running; try later')
        marker = data/'investigation-active.json' if name == 'investigation.lock' else None
        if marker:
            m.atomic(marker, json.dumps(dict(pid=os.getpid(), expires=time.time()+180)))
        try:
            yield
        finally:
            if marker:
                try: marker.unlink()
                except FileNotFoundError: pass


def new(kind, reason):
    return dict(schema=SCHEMA, id=uuid.uuid4().hex, kind=kind, reason=reason, time=time.time(),
                host=m.identity()['hostname'], status='complete', points=[], groups=[], details=[])


def groups(points):
    result = []
    for target, phase, interface in sorted({(p['target'], p['phase'], p['interface']) for p in points}):
        rows = [p for p in points if (p['target'],p['phase'],p['interface']) == (target,phase,interface)]
        values = sorted(p['latency'] for p in rows if p['ok'] and p['latency'] is not None)
        def percentile(q): return values[math.ceil(q*len(values))-1] if values else None
        misses = sum(not p['ok'] for p in rows)
        result.append(dict(target=target, phase=phase, interface=interface, attempted=len(rows), missed=misses,
            loss=100*misses/len(rows), p10=percentile(.1), median=statistics.median(values) if values else None,
            p95=percentile(.95), maximum=max(values) if values else None))
    return result


def save(data, report):
    report['end'] = time.time()
    report['groups'] = groups(report['points'])
    with exclusive(data, 'investigation-save.lock'):
        journal(data).append(report)
        compact = {k:v for k,v in report.items() if k != 'raw'}
        previous = [r for r in recent(data) if r.get('kind') != report['kind']]
        m.atomic(data/'investigation-latest.json', json.dumps((previous+[compact])[-4:], allow_nan=False))
    return report


def capture(c, data, seconds, phase, stop=None):

    stop = stop or threading.Event()
    targets = [s for s in m.specs(c) if s['id'] in TARGETS]
    interface = m.diagnostics().get('interface') or 'unknown'
    rows, deadline = [], time.monotonic()+seconds
    with ThreadPoolExecutor(max_workers=3) as pool:
        while time.monotonic() < deadline and not stop.is_set() and not paused(data):
            tick = time.monotonic()
            label = phase() if callable(phase) else phase
            import performance
            loaded = performance.active(data)
            probes = list(pool.map(lambda s: m.probe(s, 1), targets))
            for p in probes:
                rows.append(dict(time=m.epoch(p['started_at']), target=NAMES[p['id']], phase=label,
                                 interface=interface, ok=p['ok'], latency=p['latency_ms'], loaded=loaded))
            stop.wait(max(0, min(deadline-time.monotonic(), 1-(time.monotonic()-tick))))
    return rows


def burst(c, data, reason='manual', stop=None):
    with exclusive(data, 'investigation.lock'):
        if paused(data): raise ValueError('Monitoring is paused')
        report = new('close-up', reason)
        before = m.diagnostics()
        report['points'] = capture(c, data, 60, 'observation', stop)
        after = m.diagnostics()
        report['details'] = ['Nominal one-second rounds for 60 seconds; timeouts can reduce cadence. Three ICMP targets, no bandwidth load.',
            'Successful replies define latency percentiles; misses remain counted. ICMP filtering and host scheduling can affect results.',
            'This is a recorded episode, not current health. It does not reconstruct time before the trigger.']
        if any(p.get('loaded') is True for p in report['points']):
            report['details'].append('A local load test overlapped this close-up; it may have affected responses.')
        if before.get('interface') != after.get('interface'):
            report['status'] = 'incomplete'
            report['details'].append('Default interface changed during capture; do not treat this as one path.')
        if (stop and stop.is_set()) or paused(data): report['status'] = 'cancelled'
        return save(data, report)


class Trigger:

    def __init__(self, data=None):
        self.previous, self.last, self.data = set(), None, data
        if data is not None:
            try:
                path=data/'investigation-auto.json'
                if path.stat().st_size <= 1024:
                    claimed=m.read_json(path,1024).get('claimed_at')
                    if type(claimed) in (int,float) and math.isfinite(claimed):
                        elapsed=max(0,time.time()-claimed)
                        if elapsed<300: self.last=time.monotonic()-elapsed
            except (OSError,ValueError,AttributeError): pass

            if self.last is None:
                for report in recent(data):
                    if report.get('kind')=='close-up' and type(report.get('time')) in (int,float):
                        elapsed=max(0,time.time()-report['time'])
                        if elapsed<300: self.last=time.monotonic()-elapsed
    def due(self, sample, now, busy=False):
        failed = {p['id'] for p in sample['checks'] if not p['ok']}
        for p in sample['checks']:
            latency=p.get('latency_ms')
            threshold=30 if p['id']=='orbi_icmp' else 150
            if p['id'] in TARGETS and p['ok'] and type(latency) in (int,float) and math.isfinite(latency) and latency>threshold:
                failed.add('slow '+p['id'])
        changed = failed-self.previous
        self.previous = failed
        if changed and not busy and (self.last is None or now-self.last >= 300):
            self.last = now
            if self.data is not None:
                m.atomic(self.data/'investigation-auto.json',json.dumps(dict(claimed_at=time.time())))
            return 'New failed or slow probes: '+', '.join(sorted(changed))
        return None


class LoadCapture:

    def __init__(self, c, data):
        self.c, self.data = c, data
        self.interface = None
        self.report = new('load-comparison', 'Scheduled or explicitly requested internet speed test')
        self.stop = threading.Event()
        self.pool = None
        self.future = None
        self.phase = 'before'
        self.lock = None
    def start(self):
        lock = exclusive(self.data, 'investigation.lock')
        lock.__enter__()
        self.lock = lock
        try:
            self.interface = m.diagnostics().get('interface')
            self.report['points'] = capture(self.c, self.data, 5, 'before')
            self.phase = 'during'
            self.pool = ThreadPoolExecutor(max_workers=1)
            self.future = self.pool.submit(capture, self.c, self.data, self.c['speed_max_seconds']+15, lambda:self.phase, self.stop)
        except Exception:
            self.close()
            raise
    def finish(self):
        self.phase = 'after'
        self.stop.wait(5)
        self.stop.set()
        if self.future: self.report['points'] += self.future.result()
        self.report['details'] = ['Before/during/after this Mini’s internet speed test. The before period may contain other household traffic.',
            'During combines download and upload phases; it is not Flent RRUL or a bufferbloat grade.',
            'Compare the same target/interface and enough replies. Loss and host load can confound differences.']
        if self.interface != m.diagnostics().get('interface'):
            self.report['status']='incomplete'
            self.report['details'].append('Default interface changed during capture; do not compare phases as one path.')
        return save(self.data, self.report)
    def close(self):
        self.stop.set()
        if self.pool: self.pool.shutdown(wait=True)
        if self.lock:
            self.lock.__exit__(None, None, None)
            self.lock = None


def tool(name):
    if name not in ('iperf3','mtr'): raise ValueError('Unsupported tool')
    for folder in ('/opt/homebrew/bin','/opt/homebrew/sbin','/usr/local/bin','/usr/local/sbin'):
        path = Path(folder)/name
        if path.is_file() and os.access(path, os.X_OK): return str(path)
    return None


def command(args, seconds, data):

    with tempfile.TemporaryFile() as output:
        p = subprocess.Popen(args, stdout=output, stderr=subprocess.STDOUT, env={**os.environ, 'LC_ALL':'C'})
        deadline, reason = time.monotonic()+seconds, None
        try:
            while p.poll() is None:
                if paused(data): reason = 'Monitoring paused'; break
                if time.monotonic() >= deadline: reason = 'Deadline exceeded'; break
                if os.fstat(output.fileno()).st_size > MAX_OUTPUT: reason = 'Output limit exceeded'; break
                time.sleep(.1)
        finally:
            if p.poll() is None:
                p.terminate()
                try: p.wait(timeout=2)
                except subprocess.TimeoutExpired: p.kill(); p.wait()
        output.seek(0); raw = output.read(MAX_OUTPUT+1)
        return dict(exit=p.returncode, output=raw[:MAX_OUTPUT].decode('utf-8','replace'),
                    truncated=len(raw)>MAX_OUTPUT, error=reason)


def route(c, data):
    with exclusive(data, 'investigation.lock'):
        if paused(data): raise ValueError('Monitoring is paused')
        report = new('routes', 'Manual bounded route investigation')
        binary = tool('mtr')
        report['details'] = ['Repeated route probes to Cloudflare and Google. Intermediate-hop loss alone does not establish forwarding loss.',
            'Compare destination failures with the primary HTTPS/TCP/DNS checks at the same time. Route changes and ICMP filtering are possible.']
        report['raw'] = []
        if binary:
            report['details'].append('Engine: MTR, ten cycles, at most 16 hops per destination. No privilege changes performed.')
            report['raw'].append(dict(version=command([binary,'--version'], 3, data)))
        else:
            report['details'].append('Engine: macOS traceroute fallback, three passes, six hops. MTR is not installed; this is not a full MTR report.')
        for address in ('1.1.1.1','8.8.8.8'):
            attempts = 1 if binary else 3
            for attempt in range(attempts):
                if paused(data): report['status']='cancelled'; break
                args = [binary,'--report','--json','--no-dns','--report-cycles','10','--max-ttl','16',address] if binary else ['/usr/sbin/traceroute','-n','-m','6','-q','1','-w','1',address]
                result = command(args, 25 if binary else 9, data)
                report['raw'].append(dict(target=address, attempt=attempt+1, time=time.time(), arguments=args, **result))
                if result['exit'] != 0 or result['truncated'] or result['error']: report['status']='incomplete'
        report['details'] += route_details(report['raw'], bool(binary))
        report['details'].append('Full per-hop output is in the local investigations journal and the read-only CLI history.')
        return save(data, report)


def route_details(raw, use_mtr):

    details=[]
    for target in ('1.1.1.1','8.8.8.8'):
        records=[r for r in raw if r.get('target')==target]
        if use_mtr:
            try:
                hubs=json.loads(records[0]['output'])['report']['hubs']

                last=next((h for h in hubs if h.get('host')==target),None)
                if last:
                    details.append(f"{target}: MTR destination sent {last.get('Snt','?')}, loss {last.get('Loss%','?')}%, average {last.get('Avg','?')} ms.")
                else: details.append(target+': destination did not appear in the bounded MTR report; filtering or hop limit may be responsible.')
            except (ValueError,IndexError,KeyError,TypeError,AttributeError):
                details.append(target+': MTR output unavailable or unrecognized; inspect raw error/result.')
        else:
            reached=sum(bool(re.search(r'^\s*\d+\s+'+re.escape(target)+r'\s',r['output'],re.M)) for r in records)
            details.append(f'{target}: destination replied in {reached}/{len(records)} short traces. Six-hop limit can end before the destination.')
            hops={}
            for r in records:
                for line in r['output'].splitlines():
                    match=re.match(r'^\s*(\d+)\s+(.*)',line)
                    if match:
                        hops.setdefault(int(match[1]),[]).append(match[2])
            for hop, values in sorted(hops.items()):
                addresses=sorted(set(re.findall(r'\b(?:\d{1,3}\.){3}\d{1,3}\b',' '.join(values))))
                replies=sum(bool(re.search(r'\d+(?:\.\d+)?\s*ms',v)) for v in values)
                details.append(f"{target} hop {hop}: {', '.join(addresses) or 'no address'} · replies in {replies}/{len(records)} passes (ICMP response, not forwarding loss).")
    return details[:14]


def private_ipv4(value):
    address = ipaddress.IPv4Address(value)

    if not any(address in ipaddress.IPv4Network(net) for net in ('10.0.0.0/8','172.16.0.0/12','192.168.0.0/16')):
        raise ValueError('Use a private LAN IPv4 address')
    return str(address)


def lan(c, data, peer, direction, confirmed=False):
    if not confirmed: raise ValueError('LAN tests generate load; explicit --confirm-load is required')
    peer = private_ipv4(peer)
    if direction not in ('send','receive'): raise ValueError('Direction must be send or receive')
    binary = tool('iperf3')
    if not binary: raise ValueError('iperf3 is missing. Install the Homebrew iperf3 formula on both Minis first.')
    with exclusive(data, 'speed.lock'), exclusive(data, 'investigation.lock'):
        if paused(data): raise ValueError('Monitoring is paused')
        avoid_speed_windows()
        report = new('lan', 'Manual iperf3 '+direction+' test to '+peer)
        report['points'] = capture(c, data, 5, 'before')
        args = [binary,'-c',peer,'-p','5201','-t','15','-P','1','-J','--connect-timeout','3000']
        if direction == 'receive': args.append('-R')
        marker = data/'speed-active.json'
        m.atomic(marker,json.dumps(dict(active_until=time.time()+30, started_at=m.stamp())))
        stop = threading.Event()
        before = m.diagnostics()
        try:
            with ThreadPoolExecutor(max_workers=1) as pool:
                future=pool.submit(capture,c,data,25,'during',stop)
                try: result=command(args,22,data)
                finally: stop.set()
                report['points'] += future.result()
        finally:
            m.atomic(marker,json.dumps(dict(active_until=0,finished_at=m.stamp())))
        report['points'] += capture(c,data,5,'after')
        report['raw'] = dict(arguments=args, result=result, version=command([binary,'--version'],3,data))
        report['details'] = ['LAN capacity between these two computers, not AT&T speed or every-room coverage.',
            'One TCP stream for 15 seconds; reverse direction is a separate test. Other traffic and host load can affect results.']
        try:
            parsed=json.loads(result['output']); summary=parsed['end']['sum_received']; rate=summary['bits_per_second']
            if type(rate) not in (float,int) or not math.isfinite(rate) or rate<0 or parsed.get('error'): raise ValueError('Invalid throughput')
            report['details'].append(f'{direction.capitalize()}: {rate/1e6:.1f} Mbps receiver throughput · peer {peer}')
            retransmits=parsed['end'].get('sum_sent',{}).get('retransmits')
            if type(retransmits) is int and retransmits>=0: report['details'].append(f'TCP retransmissions reported by sender: {retransmits}')
        except (ValueError,KeyError,TypeError): report['status']='incomplete'
        if result['exit'] != 0 or result['error'] or result['truncated']: report['status']='incomplete'
        if before.get('interface') != m.diagnostics().get('interface'):
            report['status']='incomplete'; report['details'].append('Default interface changed; do not treat this as one path.')
        return save(data,report)


def avoid_speed_windows():
    import performance
    minute = performance.datetime.now(performance.ZONE).minute
    if 14 <= minute <= 20 or 44 <= minute <= 50:
        raise ValueError('Try outside :14–:20 and :44–:50 Pacific to avoid scheduled internet tests')


def serve(data, bind, confirmed=False):
    if not confirmed: raise ValueError('A temporary listener requires --confirm-listener')
    bind=private_ipv4(bind)
    binary=tool('iperf3')
    if not binary: raise ValueError('iperf3 is not installed')
    with exclusive(data,'speed.lock'), exclusive(data,'investigation.lock'):
        if paused(data): raise ValueError('Monitoring is paused')
        avoid_speed_windows()
        report=new('lan', 'Temporary iperf3 receiver on '+bind)

        marker=data/'speed-active.json'
        m.atomic(marker,json.dumps(dict(active_until=time.time()+65,started_at=m.stamp())))
        try:
            result=command([binary,'-s','-1','-B',bind,'-p','5201','-J','--idle-timeout','60','--server-max-duration','20'],60,data)
        finally:
            m.atomic(marker,json.dumps(dict(active_until=0,finished_at=m.stamp())))
        report['raw']=result
        report['status']='complete' if result['exit']==0 and not result['error'] else 'incomplete'
        report['details']=['Temporary receiver closed. Raw iperf3 output is in the investigations journal.', 'The load flag covers the entire receiver window, including waiting for a client. Compare throughput using the initiating Mini’s report.']
        return save(data,report)


def cli(parser):
    sub=parser.add_subparsers(dest='investigation_action',required=True)
    sub.add_parser('status')
    history=sub.add_parser('history'); history.add_argument('--limit',type=int,default=5)
    sub.add_parser('capture'); sub.add_parser('routes')
    client=sub.add_parser('lan'); client.add_argument('--peer',required=True); client.add_argument('--direction',choices=('send','receive'),required=True); client.add_argument('--confirm-load',action='store_true')
    server=sub.add_parser('serve'); server.add_argument('--bind',required=True); server.add_argument('--confirm-listener',action='store_true')


def main(args, c):
    data=args.data_dir; action=args.investigation_action
    if action=='status': return dict(schema=SCHEMA,reports=recent(data),tools={n:bool(tool(n)) for n in ('iperf3','mtr')})
    if action=='history': return list(deque(journal(data).records(),maxlen=max(1,min(20,args.limit))))
    m.validate_host(c['expected_host'])
    if action=='capture': return burst(c,data)
    if action=='routes': return route(c,data)
    if action=='lan': return lan(c,data,args.peer,args.direction,args.confirm_load)
    return serve(data,args.bind,args.confirm_listener)
