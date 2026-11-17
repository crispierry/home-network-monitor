#!/usr/bin/env python3

import argparse
from pathlib import Path
import json
import math
import sys
import time

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import monitor as m
import devices
import investigation


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('directory', type=Path)
    p.add_argument('--state', choices=('recovered', 'outage', 'stale'), default='outage')
    args = p.parse_args()
    root = args.directory.resolve()
    if root in (m.DATA.resolve(), m.BASE.resolve()) or root.exists():
        raise SystemExit('Use a new isolated fixture directory, never the real evidence directory.')
    root.mkdir(parents=True, mode=0o700)
    now = time.time()
    c = {**m.DEFAULT, 'satellites': ['192.0.2.10', '192.0.2.11']}
    detector = m.Detector(c)
    samples, events = m.journals(root)
    for index in range(241):
        if 100 <= index < 120:
            continue
        at = now-3600+index*15
        failed = set()
        if 35 <= index < 43:
            failed = {'orbi_dns', 'system_dns'}
        if 160 <= index < 168 or (args.state == 'outage' and index >= 232):
            failed = {s['id'] for s in m.specs(c) if s['id'].startswith(('cloudflare', 'google'))}
        checks = [dict(s, ok=s['id'] not in failed, started_at=m.stamp(at), finished_at=m.stamp(at+.1),
                       latency_ms=None if s['id'] in failed else round(10+4*math.sin(index/4)+(35 if 190 <= index < 193 else 0), 2),
                       elapsed_ms=100, detail='SYNTHETIC TEST EVIDENCE') for s in m.specs(c)]
        sample = dict(type='sample', started_at=m.stamp(at), finished_at=m.stamp(at+.2), interval_seconds=15,
                      host={'hostname':'Synthetic-Mini'}, checks=checks, network={'interface':'en0'}, speed_test_active=190 <= index < 193)
        samples.append(sample)
        for event in detector.update(sample):
            events.append(event)
    detector.state.update(network={'interface':'en0'}, speed_test_active=False, satellites_configured=2)
    device_rows = [dict(id=identifier, name=name, address=f'192.0.2.{20+i}', mac=f'02:00:00:00:02:{i+1:02x}', attachment='Synthetic attachment', inventory_at='2026-01-01', note='Synthetic evidence') for i,(identifier,name) in enumerate([('mini_one','Wired observer'),('mini_two','Wireless observer'),('ring_doorbell','Doorbell'),('ring_camera','Garage camera'),('alexa','Speaker'),('google_home','Home speaker')])]
    detector.state['devices'] = [dict(r, observed_at=m.stamp(now-10), last_reply_at=m.stamp(now-10) if i < 4 else None,
        reply=i < 4, identity='match' if i < 4 else 'unverified', latency_ms=12 if i < 4 else None,
        is_local=i == 0, status='responding' if i < 4 else 'unknown') for i,r in enumerate(device_rows)]
    detector.state['device_events'] = [dict(name='Ring doorbell',type='device_unreachable',at=m.stamp(now-300),first_failed_at=m.stamp(now-360)),
        dict(name='Ring doorbell',type='device_recovered',at=m.stamp(now-120),first_recovered_at=m.stamp(now-180))]
    if args.state == 'stale':
        detector.state['last_completed_at'] = m.stamp(now-180)
    m.atomic(root/'state.json', json.dumps(detector.state))
    speed = m.Journal(root, 'performance', 1024**2, 8, 180)
    for offset, down, up in [(3400, 1030, 1130), (2100, 940, 1080), (700, 1010, 1160)]:
        speed.append(dict(started_at=m.stamp(now-offset), finished_at=m.stamp(now-offset+25), status='success',
                          download_mbps=down, upload_mbps=up, idle_latency_ms=15, download_responsiveness_rpm=2000,
                          upload_responsiveness_rpm=900, requested_interface='en0'))
    report = dict(schema=investigation.SCHEMA, id='synthetic-closeup', kind='load-comparison', reason='SYNTHETIC TEST EVIDENCE',
                  host='Synthetic-Mini', time=now-90, end=now-30, status='complete', details=['Synthetic episode for UI testing. No network packets were sent.'], points=[])
    for i in range(60):
        phase='before' if i<10 else 'during' if i<45 else 'after'
        for target in ('Main Orbi','Cloudflare','Google'):
            miss=i in (22,23) and target!='Main Orbi'
            latency=None if miss else (2 if target=='Main Orbi' else 10+(80 if 15<=i<40 else 0)+4*math.sin(i))
            report['points'].append(dict(time=now-90+i,target=target,phase=phase,interface='en1',ok=not miss,latency=latency))
    report['groups']=investigation.groups(report['points'])
    m.atomic(root/'investigation-latest.json',json.dumps([report]))
    print(root)


if __name__ == '__main__':
    main()
