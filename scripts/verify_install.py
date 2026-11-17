#!/usr/bin/env python3

import hashlib
import json
import os
from pathlib import Path
import plistlib
import re
import subprocess
import sys
import time

SOURCE = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(SOURCE))
import manage
import monitor
import performance


def main():
    state = monitor.read_state(monitor.DATA)
    if not state:
        print('No installed evidence found')
        return 1
    job = manage.launchctl('print', f'gui/{os.getuid()}/'+manage.LABEL, check=False)
    pid = re.search(r'^\s*pid = (\d+)', job.stdout, re.MULTILINE)
    files = ('monitor.py', 'manage.py', 'performance.py', 'analysis.py', 'devices.py', 'agent_query.py', 'sync.py', 'peer_transport.py', 'diagnostics.py', 'host_metrics.py', 'investigation.py', 'AGENTS.md', 'service.c', 'wifi.swift',
             'README.md', 'CONTRIBUTING.md', 'DEPLOYMENT.md', 'DASHBOARD_DESIGN.md', 'DIAGNOSTIC_RESEARCH.md', 'ACKNOWLEDGMENTS.md', 'CODE_REVIEW.md', 'INVESTIGATIONS.md', 'LICENSE', 'SECURITY.md', 'ARCHITECTURE.md')
    matches = {name: (monitor.BASE/name).exists() and
               hashlib.sha256((SOURCE/name).read_bytes()).digest() ==
               hashlib.sha256((monitor.BASE/name).read_bytes()).digest() for name in files}
    signature = subprocess.run(['/usr/bin/codesign', '--verify', '--strict',
                                str(monitor.BASE/'Network Monitor.app')], capture_output=True)
    checks = state['checks']
    age = time.time()-monitor.epoch(state['last_completed_at'])
    context = state.get('diagnostic_snapshot', {})
    context_age = time.time()-monitor.epoch(context['finished_at']) if context.get('finished_at') else None
    context_fresh = context.get('type') == 'diagnostic_snapshot' and context_age is not None and -5 <= context_age <= 180
    running = job.returncode == 0 and bool(re.search(r'^\s*state = running$', job.stdout, re.MULTILINE))
    configuration = monitor.config(monitor.BASE/'config.json')
    speed = list(performance.journal(monitor.DATA).records())
    latest_speed = speed[-1] if speed else {}
    last_successful_speed = next((entry for entry in reversed(speed) if entry.get('status') == 'success'), {})
    app = Path.home()/'Applications/Network Monitor.app'
    dashboard_signature = subprocess.run(['/usr/bin/codesign', '--verify', '--strict', str(app)], capture_output=True)
    helper = monitor.BASE/'wifi-observer'
    helper_signature = subprocess.run(['/usr/bin/codesign','--verify','--strict',str(helper)],capture_output=True)
    helper_marker = monitor.BASE/'wifi-observer.sha256'
    helper_valid = helper.is_file() and helper_signature.returncode == 0 and helper_marker.is_file() and helper_marker.read_text() == hashlib.sha256((SOURCE/'wifi.swift').read_bytes()).hexdigest()
    manifest = app/'Contents/Resources/source.plist'
    dashboard_matches = False
    if manifest.exists():
        digests = plistlib.loads(manifest.read_bytes())
        expected = {'macos/'+name for name in ('DashboardData.swift', 'DashboardStore.swift', 'DashboardView.swift', 'NetworkMonitorApp.swift', 'Icon.swift')}
        expected.add('release.json')
        dashboard_matches = set(digests) == expected and all(
            hashlib.sha256((SOURCE/path).read_bytes()).hexdigest() == digests[path] for path in expected)
    app_info = plistlib.loads((app/'Contents/Info.plist').read_bytes()) if app.exists() else {}
    print(json.dumps(dict(dashboard_version=app_info.get('CFBundleShortVersionString'), dashboard_build=app_info.get('CFBundleVersion'), host=state['host'], service_running=running,
        service_pid=int(pid[1]) if pid else None, last_completed_at=state['last_completed_at'],
        sample_age_seconds=round(age, 1), interface=state.get('network', {}).get('interface'),
        interval_seconds=state['interval_seconds'],
        checks_total=len(checks), checks_passing=sum(v['latest']['ok'] for v in checks.values()),
        failed_checks=[key for key, value in checks.items() if not value['latest']['ok']],
        peer_address=checks.get('peer_icmp', {}).get('latest', {}).get('resolved_address'),
        devices=[{key: row.get(key) for key in ('name', 'status', 'observed_at', 'identity', 'is_local')} for row in state.get('devices', [])],
        open_incident=state['incident']['id'] if state['incident'] else None,
        installed_files_match=matches, app_signature_valid=signature.returncode == 0,
        dashboard_installed=app.exists(), dashboard_signature_valid=dashboard_signature.returncode == 0,
        dashboard_sources_match=dashboard_matches, wifi_helper_valid=helper_valid,
        diagnostics_fresh=context_fresh,
        diagnostic_age_seconds=round(context_age, 1) if context_age is not None else None,
        gateway_pages={key: value.get('status') for key, value in context.get('gateway', {}).items()},
        speed_hours=configuration['speed_hours'], speed_slot=configuration['speed_slot'],
        speed_minute=performance.SCHEDULE_MINUTES[configuration['speed_slot']],
        latest_speed={key: latest_speed.get(key) for key in
                      ('status', 'started_at', 'download_mbps', 'upload_mbps', 'idle_latency_ms')},
        last_successful_speed={key: last_successful_speed.get(key) for key in
                      ('started_at', 'download_mbps', 'upload_mbps', 'idle_latency_ms')}
        ), indent=None if '--compact' in sys.argv else 2))
    return 0 if (running and 0 <= age < state['interval_seconds']*3 and all(matches.values())
                 and signature.returncode == 0 and dashboard_signature.returncode == 0 and dashboard_matches and context_fresh and helper_valid) else 1


if __name__ == '__main__':
    sys.exit(main())
