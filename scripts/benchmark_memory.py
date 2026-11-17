#!/usr/bin/env python3

import argparse
from datetime import datetime, timezone
import json
from pathlib import Path
import subprocess
import tempfile

SOURCE = Path(__file__).resolve().parents[1]

def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--samples', type=int, default=40320, help='Default: seven days at 15-second cadence')
    parser.add_argument('--reader-source', type=Path, default=SOURCE/'macos/DashboardData.swift')
    args = parser.parse_args()
    if not 1 <= args.samples <= 40320:
        parser.error('samples must be in 1..40320')
    with tempfile.TemporaryDirectory(prefix='network-monitor-memory-') as tmp:
        root = Path(tmp); fixture = root/'fixture'; fixture.mkdir()
        now = 1800000000
        def stamp(t):
            return datetime.fromtimestamp(t, timezone.utc).isoformat()
        ids = ['orbi_icmp', 'orbi_tcp', 'gateway_icmp', 'gateway_tcp', 'cloudflare_icmp', 'cloudflare_tcp',
               'google_icmp', 'google_tcp', 'system_dns', 'orbi_dns', 'cloudflare_dns', 'google_dns',
               'cloudflare_https', 'google_https', 'peer_icmp', 'satellite_1_icmp', 'satellite_1_tcp',
               'satellite_1_identity', 'satellite_2_icmp', 'satellite_2_tcp', 'satellite_2_identity']
        def check(t, name):
            return dict(id=name, ok=True, latency_ms=12.25, target='192.0.2.1', kind='icmp',
                        detail='synthetic memory benchmark', started_at=stamp(t))
        state = dict(host=dict(hostname='Synthetic-Mini'), last_completed_at=stamp(now), interval_seconds=15,
                     checks={ids[0]:dict(latest=check(now, ids[0]), down=False)}, recent_incidents=[])
        (fixture/'state.json').write_text(json.dumps(state))
        segment, size, handle = 0, 0, None
        try:
            for i in range(args.samples):
                t = now-(args.samples-1-i)*15
                row = dict(started_at=stamp(t), interval_seconds=15, speed_test_active=False,
                           network=dict(interface='en1'), checks=[check(t, name) for name in ids])
                line = (json.dumps(row, separators=(',', ':'))+'\n').encode()
                if handle is None or size+len(line) > 4*1024**2:
                    if handle: handle.close()
                    handle = (fixture/f'samples-{segment:03}.jsonl').open('wb'); segment += 1; size = 0
                handle.write(line); size += len(line)
        finally:
            if handle: handle.close()
        print(f'Synthetic records: {args.samples}; segments: {segment}', flush=True)
        subprocess.run(['xcrun','swiftc','-O','-swift-version','5','-parse-as-library',
                        '-module-cache-path',str(root/'cache'),str(args.reader_source.resolve()),
                        str(SOURCE/'tests/MemoryBenchmark.swift'),'-o',str(root/'benchmark')],check=True)
        subprocess.run([str(root/'benchmark'),str(fixture)],check=True)

if __name__ == '__main__':
    main()
