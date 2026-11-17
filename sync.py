import argparse
import fcntl
import hashlib
import json
import math
import os
from pathlib import Path
import re
import shutil
import signal
import subprocess
import sys
import time
import uuid

import monitor as m

ROOT = m.BASE/'Sync'
MIB = 1024**2
MAX_EXPORT = 16*MIB
MAX_FILE = MIB
MAX_MANIFEST = MIB
NAME = re.compile(r'(samples|performance|observations)-[0-9]{20}-[a-f0-9]{8}\.jsonl\Z')
ID = re.compile(r'[a-f0-9]{32}\Z')
LANES = [['cloudflare_https','google_https'], ['orbi_icmp','orbi_tcp'],
         ['gateway_icmp','gateway_tcp'], ['system_dns','orbi_dns','cloudflare_dns','google_dns'],
         ['satellite_1_icmp','satellite_1_tcp','satellite_1_identity'],
         ['satellite_2_icmp','satellite_2_tcp','satellite_2_identity'], ['peer_icmp']]


def read(path, limit=MAX_MANIFEST):
    return m.read_json(path, limit)


def save(path, value):
    path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    m.atomic(path, json.dumps(value, separators=(',', ':'), allow_nan=False))
    path.chmod(0o600)


def optional(path, default=None):
    try:
        return read(path)
    except FileNotFoundError:
        return {} if default is None else default


def digest(data):
    return hashlib.sha256(data).hexdigest()


def compact_sample(row):
    checks = {c['id']: c for c in row['checks']}
    def group(ids):
        if not all(i in checks for i in ids): return -1
        good=sum(bool(checks[i]['ok']) for i in ids)
        return 2 if good==len(ids) else 1 if good else 0
    def latency(i):
        c=checks.get(i,{})
        return c.get('latency_ms') if c.get('ok') else None
    pings=[checks[i] for i in ('cloudflare_icmp','google_icmp') if i in checks]
    return dict(schema='network-monitor.sample.v1', time=m.epoch(row['started_at']),
        interval=row.get('interval_seconds',15), lanes=[group(x) for x in LANES],
        cloudflare=latency('cloudflare_icmp'), google=latency('google_icmp'), orbi=latency('orbi_icmp'),
        failed=sum(not c['ok'] for c in checks.values()), total=len(checks),
        pingFailed=sum(not c['ok'] for c in pings), pingTotal=len(pings),
        loaded=row.get('speed_test_active') is True, loadKnown=isinstance(row.get('speed_test_active'),bool), interface=row.get('network',{}).get('interface') or 'unknown')


def compact_speed(row):
    return {k:v for k,v in row.items() if k in ('started_at','finished_at','status','download_mbps','upload_mbps',
        'idle_latency_ms','download_responsiveness_rpm','upload_responsiveness_rpm','requested_interface','reason')}


def tree_bytes(root):

    return sum(max(p.stat().st_size, getattr(p.stat(),'st_blocks',0)*512)
               for p in root.rglob('*') if p.is_file() and not p.is_symlink()) if root.exists() else 0


def publish(data=m.DATA, root=ROOT, host=None, now=None):
    now=time.time() if now is None else now
    root.mkdir(parents=True,exist_ok=True,mode=0o700)
    identity=optional(root/'identity.json')
    if not identity:
        identity={'host_id':uuid.uuid4().hex}; save(root/'identity.json',identity)
    state=optional(data/'state.json')
    if not state: return None
    state['recording_paused'] = data == m.DATA and (m.BASE/'monitoring-paused').exists()
    host=host or state['host'].get('local_hostname') or state['host']['hostname'].removesuffix('.local')
    if host not in ('Mini-One','Mini-Two'): raise ValueError('Unexpected observation host')
    out=root/'outbox'; out.mkdir(exist_ok=True,mode=0o700)
    cursor=optional(root/'cursor.json')

    generation=optional(root/'generation.json')
    if not generation:
        generation={'id':uuid.uuid4().hex}; save(root/'generation.json',generation)
    if cursor.get('generation') != generation['id']:
        for p in out.iterdir():
            if p.is_file() and (NAME.fullmatch(p.name) or p.name=='manifest.json'): p.unlink()
        cursor={'generation':generation['id'],'offsets':{},'sequence':0}
    journals={'samples':m.Journal(out,'samples',512*1024,24,7),
              'performance':m.Journal(out,'performance',256*1024,4,180),
              'observations':m.Journal(out,'observations',256*1024,4,180)}
    present=set()
    for kind in journals:
        for path in sorted(data.glob(kind+'-*.jsonl')):
            if path.is_symlink() or path.stat().st_size>9*MIB: continue
            present.add(path.name)
            old=cursor['offsets'].get(path.name,0)
            size=path.stat().st_size
            if size<old: old=0
            with path.open('rb') as f:
                f.seek(old)
                while True:
                    line=f.readline(MAX_FILE+1)
                    if not line: break
                    if len(line)>MAX_FILE: raise ValueError('Oversized local record')
                    if not line.endswith(b'\n'): break
                    old+=len(line)
                    try:
                        row=json.loads(line)
                        at=row.get('recorded') if kind=='observations' else m.epoch(row['started_at'])
                        if at<now-(7 if kind=='samples' else 180)*86400: continue
                        result=compact_sample(row) if kind=='samples' else compact_speed(row) if kind=='performance' else row
                        journals[kind].append(result,now)
                    except (ValueError,KeyError,TypeError):
                        continue
            cursor['offsets'][path.name]=old
    cursor['offsets']={k:v for k,v in cursor['offsets'].items() if k in present}

    for kind,journal in journals.items():
        for p in journal.files():
            if now-int(p.name.split('-')[1])/1e9>journal.days*86400: p.unlink()
    files=[]
    for p in sorted(out.glob('*.jsonl')):
        payload=p.read_bytes(); files.append(dict(name=p.name,size=len(payload),sha256=digest(payload)))
    cursor['sequence']+=1
    manifest=dict(schema='network-monitor.exchange.v1',host_id=identity['host_id'],host=host,
        generation=generation['id'],sequence=cursor['sequence'],published_at=now,
        state=state,files=files,raw_diagnostics_included=False)
    encoded=json.dumps(manifest,separators=(',',':'),allow_nan=False).encode()
    if len(encoded)>MAX_MANIFEST or sum(f['size'] for f in files)+len(encoded)>MAX_EXPORT:
        raise ValueError('Export budget exceeded')
    save(out/'manifest.json',manifest)
    save(root/'cursor.json',cursor)
    return manifest


def validate_manifest(value, peer_id, peer_host, now=None):
    try:
        _validate_manifest(value, peer_id, peer_host, now)
    except (AttributeError, KeyError, TypeError, OverflowError) as exc:
        raise ValueError('Malformed peer manifest') from exc


def _validate_manifest(value, peer_id, peer_host, now=None):
    now=time.time() if now is None else now
    if not isinstance(value,dict): raise ValueError('Invalid manifest')
    if value.get('schema')!='network-monitor.exchange.v1' or value.get('host_id')!=peer_id or value.get('host')!=peer_host:
        raise ValueError('Unpaired source or unsupported schema')
    if not ID.fullmatch(value.get('generation','')) or type(value.get('sequence')) is not int or value['sequence']<1:
        raise ValueError('Invalid generation/sequence')
    published=value.get('published_at')
    if type(published) not in (int,float) or not math.isfinite(published) or published>now+5:
        raise ValueError('Invalid/future publication time')
    state=value.get('state',{})
    if state.get('host',{}).get('hostname','').removesuffix('.local')!=peer_host or not isinstance(state.get('checks'),dict) or not 1<=len(state['checks'])<=100:
        raise ValueError('Invalid state identity/checks')
    if type(state.get('interval_seconds')) not in (int,float) or not 15<=state['interval_seconds']<=300:
        raise ValueError('Invalid sampling interval')
    for key, check in state['checks'].items():
        latest=check['latest']
        if latest.get('id')!=key or type(latest.get('ok')) is not bool:
            raise ValueError('Invalid check identity/result')
        latency=latest.get('latency_ms')
        if latency is not None and (type(latency) not in (int,float) or not math.isfinite(latency) or latency<0):
            raise ValueError('Invalid check latency')
        if m.epoch(latest['started_at'])>now+5: raise ValueError('Future check')
    if m.epoch(state['last_completed_at'])>now+5: raise ValueError('Future observations')
    files=value.get('files')
    if not isinstance(files,list) or len(files)>64: raise ValueError('Invalid file count')
    seen=set(); total=0
    for item in files:
        name=item.get('name',''); size=item.get('size')
        if not NAME.fullmatch(name) or name in seen or type(size) is not int or not 0<size<=MAX_FILE or not re.fullmatch('[a-f0-9]{64}',item.get('sha256','')):
            raise ValueError('Invalid manifest entry')
        total+=size; seen.add(name)
    if total>14*MIB: raise ValueError('Peer export budget exceeded')


def validate_records(name, payload, now):
    try:
        _validate_records(name, payload, now)
    except (AttributeError, KeyError, TypeError, OverflowError) as exc:
        raise ValueError('Malformed peer record') from exc


def _validate_records(name, payload, now):
    if not payload.endswith(b'\n'): raise ValueError('Incomplete journal')
    if payload.count(b'\n')>10000: raise ValueError('Record count exceeded')
    for line in payload.splitlines():
        row=json.loads(line,parse_constant=lambda _: (_ for _ in ()).throw(ValueError('Nonfinite number')))
        if name.startswith('samples-'):
            if row.get('schema')!='network-monitor.sample.v1' or len(row.get('lanes',[]))!=7 or not all(type(x) is int and -1<=x<=2 for x in row['lanes']): raise ValueError('Invalid compact sample')
            if any(type(row.get(key)) is not int for key in ('failed','total','pingFailed','pingTotal')) or not 0<=row['pingFailed']<=row['pingTotal']<=2 or not isinstance(row.get('loaded'),bool) or not isinstance(row.get('interface'),str): raise ValueError('Invalid sample fields')
            if 'loadKnown' in row and type(row['loadKnown']) is not bool: raise ValueError('Invalid load tag')
            if type(row.get('interval')) not in (int,float) or not 15<=row.get('interval',0)<=300 or not 0<=row.get('failed',-1)<=row.get('total',0)<=100 or row['total']==0: raise ValueError('Invalid sample counts')
            at=row['time']
            for key in ('cloudflare','google','orbi'):
                val=row.get(key)
                if val is not None and (type(val) not in (int,float) or not math.isfinite(val) or val<0): raise ValueError('Invalid latency')
        elif name.startswith('performance-'):
            at=m.epoch(row['started_at'])
            for key in ('download_mbps','upload_mbps','idle_latency_ms','download_responsiveness_rpm','upload_responsiveness_rpm'):
                value=row.get(key)
                if value is not None and (type(value) not in (int,float) or not math.isfinite(value) or value<0):
                    raise ValueError('Invalid speed measurement')
            if row.get('finished_at') and not at<=m.epoch(row['finished_at'])<=now+5:
                raise ValueError('Invalid speed interval')
        else:
            at=row['time']
            if not isinstance(row.get('note',''),str) or len(row.get('note',''))>2000: raise ValueError('Oversized note')
        if type(at) not in (int,float) or not math.isfinite(at) or at>now+5 or at<0: raise ValueError('Invalid record time')


def transfer(source, destination, peer_id, peer_host, now=None):


    now=time.time() if now is None else now
    manifest=read(source/'manifest.json'); validate_manifest(manifest,peer_id,peer_host,now)
    destination.mkdir(parents=True,exist_ok=True,mode=0o700)
    old_pointer=optional(destination/'current.json')
    if source.is_symlink() or destination.is_symlink(): raise ValueError('Exchange directory symlink refused')
    if old_pointer and old_pointer.get('directory') not in ('slot-a','slot-b'): raise ValueError('Invalid cache pointer')
    old=destination/old_pointer.get('directory','missing')
    if old.is_symlink(): raise ValueError('Cache slot symlink refused')
    prior=optional(old/'manifest.json') if old_pointer else {}
    if prior and prior['generation']==manifest['generation'] and manifest['sequence']<prior['sequence']:
        raise ValueError('Replay refused')
    if prior and prior['generation']==manifest['generation'] and manifest['sequence']==prior['sequence']:
        if digest(json.dumps(prior,sort_keys=True).encode())!=digest(json.dumps(manifest,sort_keys=True).encode()): raise ValueError('Changed sequence')
        return dict(received_at=now,observed_at=m.epoch(manifest['state']['last_completed_at']),unchanged=True)
    stage=destination/'staging'
    if stage.exists(): shutil.rmtree(stage)
    stage.mkdir(mode=0o700)
    try:
        old_files={f['name']:f for f in prior.get('files',[])} if prior.get('generation')==manifest['generation'] else {}
        for item in manifest['files']:
            name=item['name']; prior_item=old_files.get(name)
            prefix=b''
            if prior_item and prior_item['size']<=item['size']:
                p=old/name
                if not p.is_symlink():
                    prefix=p.read_bytes()
                    if len(prefix)!=prior_item['size'] or digest(prefix)!=prior_item['sha256']: prefix=b''
            src=source/name
            if src.is_symlink(): raise ValueError('Source symlink refused')
            if len(prefix)==item['size'] and digest(prefix)==item['sha256']:
                payload=prefix
            else:
                with src.open('rb') as f:
                    f.seek(len(prefix)); tail=f.read(item['size']-len(prefix))
                payload=prefix+tail
            if len(payload)!=item['size'] or digest(payload)!=item['sha256']: raise ValueError('Transfer checksum mismatch')
            validate_records(name,payload,now)
            (stage/name).write_bytes(payload); (stage/name).chmod(0o600)
        save(stage/'state.json',manifest['state']); save(stage/'manifest.json',manifest)

        slot='slot-b' if old_pointer.get('directory')=='slot-a' else 'slot-a'
        target=destination/slot
        if target.exists(): shutil.rmtree(target)
        stage.rename(target)
        save(destination/'current.json',dict(directory=slot,host_id=peer_id,generation=manifest['generation'],received_at=now))
        if old.exists() and old!=target:
            if prior.get('generation') != manifest['generation']:
                archive=destination/'previous-generation'
                if archive.exists(): shutil.rmtree(archive)
                old.rename(archive)
            else: shutil.rmtree(old)
        return dict(received_at=now,observed_at=m.epoch(manifest['state']['last_completed_at']),unchanged=False)
    finally:
        if stage.exists(): shutil.rmtree(stage)


def current_peer(root=ROOT):
    pointer=optional(root/'peer/current.json')
    if pointer.get('directory') not in ('slot-a','slot-b'): return None
    return root/'peer'/pointer['directory']


def all_hosts(data=m.DATA, root=ROOT, hours=24):
    import agent_query
    now=time.time()
    local=agent_query.briefing(data,hours=hours)
    peer=current_peer(root)
    result=dict(schema='network-monitor.home.v1',generated_at=m.stamp(now),
                local=local,peer=None,sync=optional(root/'status.json'),
                limitations=['Peer is a local validated cache. Sync failure is not proof of an internet failure.',
                             'Raw peer diagnostics remain on the source Mac. Speed tests are staggered, not simultaneous.'])
    if peer:
        brief=agent_query.briefing(peer,include_history=False,now=now)
        brief['limitations']=[x for x in brief['limitations'] if 'not automatically synchronized' not in x]
        samples=[]; speeds=[]
        for path in sorted(peer.glob('samples-*.jsonl')):
            for line in path.read_text().splitlines():
                row=json.loads(line)
                if now-hours*3600<=row['time']<=now: samples.append(row)
        for path in sorted(peer.glob('performance-*.jsonl')):
            speeds.extend(json.loads(x) for x in path.read_text().splitlines())
        samples.sort(key=lambda x:x['time']); covered=0; end=now-hours*3600
        for row in samples:
            a=max(end,row['time']); b=min(now,row['time']+row['interval']); covered+=max(0,b-a); end=max(end,b)
        notes=[]
        for path in sorted(peer.glob('observations-*.jsonl')):
            notes.extend(json.loads(x) for x in path.read_text().splitlines())
        brief.update(reported_symptoms=sorted(notes,key=lambda x:x['time'])[-100:],source='validated_peer_cache',received_at=optional(root/'peer/current.json').get('received_at'),
            coverage_seconds=covered,observed_samples=len(samples),
            public_ping_attempts=sum(x['pingTotal'] for x in samples),public_ping_failures=sum(x['pingFailed'] for x in samples),
            recent_incidents=optional(peer/'state.json').get('recent_incidents',[]),
            speeds=sorted(speeds,key=lambda x:x['started_at'])[-100:])
        result['peer']=brief
    return result


def exchange(root):

    import peer_transport
    return peer_transport.exchange(root)


def resource_sample(previous=None):

    output=subprocess.check_output(['ps','-S','-axo','pid=,ppid=,rss=,time=,args='],text=True,timeout=5)
    rows={}
    for line in output.splitlines():
        parts=line.strip().split(None,4)
        if len(parts)!=5: continue
        pid,parent,rss,clock,args=parts
        seconds=sum(float(x)*60**i for i,x in enumerate(reversed(clock.split(':'))))
        rows[int(pid)]=dict(parent=int(parent),rss=int(rss),seconds=seconds,args=args)
    now=time.monotonic(); result={}; counters={}
    for name in ('recorder','dashboard','sync'):
        ids={pid for pid,r in rows.items() if
             (name=='sync' and pid==os.getpid()) or
             (name=='recorder' and str(m.BASE/'monitor.py')+' run' in r['args']) or
             (name=='dashboard' and '/Applications/Network Monitor.app/Contents/MacOS/NetworkMonitor' in r['args'])}
        roots=sorted(ids)
        while True:
            more={pid for pid,r in rows.items() if r['parent'] in ids}
            if more<=ids: break
            ids|=more
        seconds=sum(rows[i]['seconds'] for i in ids)
        result[name]={'rss_mib':round(sum(rows[i]['rss'] for i in ids)/1024,1)}
        before=(previous or {}).get(name)
        if before and before['roots']==roots and roots and now>before['at'] and seconds>=before['seconds']:
            result[name]['cpu_percent']=round((seconds-before['seconds'])/(now-before['at'])*100,2)
        counters[name]=dict(roots=roots,seconds=seconds,at=now)
    return result,counters


def run(root=ROOT,data=m.DATA):
    os.umask(0o077); root.mkdir(parents=True,exist_ok=True,mode=0o700)
    lock=(root/'worker.lock').open('a'); fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
    child=None; server=None; next_server=0; deadline=0; failures=0; next_attempt=0; next_publish=0
    status=optional(root/'status.json')
    resource_counters=None; next_resources=0
    def shutdown(*_):
        for process in (child,server):
            if process and process.poll() is None: os.killpg(process.pid,signal.SIGKILL)
        raise SystemExit(0)
    signal.signal(signal.SIGTERM,shutdown)
    while True:
        now=time.time()
        if child:
            if child.poll() is not None:
                if child.returncode==0:
                    status.update(state='connected',last_sync_at=now,error=None); failures=0
                else:
                    status.update(state='unavailable',error='Peer exchange unavailable; local recording continues'); failures+=1
                child=None; next_attempt=now+(10 if failures==0 else min(300,30*2**min(failures,4)))
            elif now>deadline:
                os.killpg(child.pid,signal.SIGKILL); deadline=float('inf')
                status.update(state='unavailable',error='Peer transfer timed out; last good cache retained')
        if now>=next_publish and child is None:
            try:
                manifest=publish(data,root)
                status.update(published_at=now,host=manifest['host'] if manifest else None,local_bytes=tree_bytes(data),sync_bytes=tree_bytes(root))
            except (ValueError,OSError,KeyError,TypeError):
                status.update(error='Local summary unavailable',state='error')
            next_publish=now+10
        if now>=next_resources:
            try:
                status['resources'],resource_counters=resource_sample(resource_counters)
                status['resources_at']=now
            except (OSError,ValueError,subprocess.SubprocessError):
                status.pop('resources',None)
            next_resources=now+60
        c=optional(root/'config.json')
        if server and (server.poll() is not None or not c.get('enabled') or c.get('role')!='hub'):
            if server.poll() is None: os.killpg(server.pid,signal.SIGKILL)
            server.wait(timeout=5); server=None; next_server=now+30
        if not c.get('enabled'):
            if child and child.poll() is None: os.killpg(child.pid,signal.SIGKILL)
            status['state']='not_configured'
        elif c.get('role')=='hub':
            if server is None and now>=next_server:
                server=subprocess.Popen([sys.executable,str(Path(__file__).with_name('peer_transport.py')),'serve','--root',str(root),'--data',str(data)],
                    stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL,start_new_session=True)
            received=optional(root/'received.json').get('at')
            status.update(state='connected' if received and now-received<90 else 'unavailable',last_sync_at=received)
        elif c.get('role')=='client' and child is None and now>=next_attempt and (root/'outbox/manifest.json').exists():
            child=subprocess.Popen([sys.executable,str(Path(__file__).resolve()),'exchange','--root',str(root)],
                stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL,start_new_session=True)
            deadline=now+25
        status['updated_at']=now
        save(root/'status.json',status)
        time.sleep(5)


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('action',choices=['run','publish','exchange','query'])
    p.add_argument('--root',type=Path,default=ROOT); p.add_argument('--data',type=Path,default=m.DATA)
    a=p.parse_args()
    if a.action=='run': run(a.root,a.data)
    elif a.action=='publish': print(json.dumps(publish(a.data,a.root)))
    elif a.action=='exchange': exchange(a.root)
    else: print(json.dumps(all_hosts(a.data,a.root),indent=2))

if __name__=='__main__': main()
