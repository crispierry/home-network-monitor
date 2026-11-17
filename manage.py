#!/usr/bin/env python3

import argparse
import copy
import fcntl
from contextlib import ExitStack
import hashlib
import json
import os
from pathlib import Path
import plistlib
import shlex
import shutil
import subprocess
import sys
import time

import monitor

LABEL = 'com.crispierry.network-monitor'
PLIST = Path.home() / 'Library/LaunchAgents' / (LABEL+'.plist')
LAUNCHER = Path.home() / '.local/bin/network-monitor'
APP_ID = 'com.crispierry.network-monitor.service'


def build_service_app(source):

    app = monitor.BASE/'Network Monitor.app'
    contents = app/'Contents'
    binary = contents/'MacOS/network-monitor-service'
    digest = hashlib.sha256((source/'service.c').read_bytes()).hexdigest()
    marker = contents/'Resources/source.sha256'
    if not binary.exists() or not marker.exists() or marker.read_text() != digest:
        binary.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
        marker.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
        info = dict(CFBundleIdentifier=APP_ID, CFBundleName='Network Monitor',
                    CFBundleDisplayName='Network Monitor', CFBundleExecutable=binary.name,
                    CFBundlePackageType='APPL', CFBundleVersion='1', LSUIElement=True,
                    NSLocalNetworkUsageDescription='Check the Orbi router, satellites, gateway and other Mini to diagnose home network outages.')
        (contents/'Info.plist').write_bytes(plistlib.dumps(info))
        subprocess.run(['/usr/bin/xcrun', 'clang', '-O2', '-Wall', '-Wextra',
                        str(source/'service.c'), '-o', str(binary)], check=True)
        marker.write_text(digest)
        subprocess.run(['/usr/bin/codesign', '--force', '--sign', '-',
                        '--identifier', APP_ID, str(app)], check=True)
    subprocess.run(['/System/Library/Frameworks/CoreServices.framework/Frameworks/LaunchServices.framework/Support/lsregister',
                    '-f', str(app)], check=True)
    return binary


def launchctl(*args, check=True):
    return subprocess.run(['/bin/launchctl', *args], check=check, capture_output=True, text=True)


def stop_service(domain, label=LABEL):
    launchctl('bootout', domain+'/'+label, check=False)

    for _ in range(120):
        if launchctl('print', domain+'/'+label, check=False).returncode:
            return
        time.sleep(0.25)
    raise RuntimeError('Previous service has not exited; retry after it stops')


def cadence_migration(c, previous, state):

    monitor.Detector(previous, state)
    changed = {key for key in c if c[key] != previous[key]}
    if not changed or not changed <= {'interval_seconds', 'speed_hours'}:
        monitor.Detector(c, state)
        return state
    updated = copy.deepcopy(state)
    updated['config_hash'] = monitor.Detector(c).state['config_hash']
    updated['interval_seconds'] = c['interval_seconds']
    if 'interval_seconds' in changed:
        for check in updated['checks'].values():
            check.update(fail_count=0, pass_count=0)
        if updated['incident']:
            updated['incident']['has_observation_gap'] = True
    return updated


def wait_for_sample(data, installed_at, timeout=60):

    for _ in range(timeout):
        state = monitor.read_state(data)
        if state and monitor.epoch(state['last_completed_at']) >= installed_at-1:
            return state
        time.sleep(1)
    raise RuntimeError(f'Service loaded but no fresh sample within {timeout}s; inspect service.log and launchctl print')


def installation_settings(source, expected_host=None, config_path=None, devices_path=None):
    import devices
    installed = monitor.BASE/'config.json'
    selected = Path(config_path) if config_path else installed
    if not selected.is_file():
        raise ValueError('First installation requires --config with your private network settings')
    c = monitor.config(selected)
    if expected_host:
        c['expected_host'] = expected_host
    inventory_path = Path(devices_path) if devices_path else monitor.BASE/'devices.json'
    rows = devices.inventory(inventory_path)
    return c, rows


def install(source, expected_host=None, config_path=None, devices_path=None):
    if sys.platform != 'darwin' or sys.version_info < (3, 10):
        raise ValueError('Requires macOS and Python 3.10 or later')
    c, device_rows = installation_settings(source, expected_host, config_path, devices_path)
    host = monitor.validate_host(c['expected_host'])
    for executable in ('/sbin/ping', '/usr/bin/dig', '/sbin/route', '/usr/sbin/scutil'):
        if not Path(executable).is_file():
            raise ValueError('Missing system tool: '+executable)
    domain = f'gui/{os.getuid()}'
    if launchctl('print', domain, check=False).returncode:
        raise ValueError('Log into the Mac desktop as the intended user before installing')
    print('Verified host:', json.dumps(host))
    print('Current default route (verify Ethernet in installation evidence):')
    print(monitor.diagnostics()['default_route'])
    os.umask(0o077)
    for directory in (monitor.BASE, monitor.DATA, PLIST.parent, LAUNCHER.parent):
        directory.mkdir(parents=True, exist_ok=True, mode=0o700)

    existing = monitor.read_state(monitor.DATA)
    previous = monitor.config(monitor.BASE/'config.json') if existing else c
    if existing:
        cadence_migration(c, previous, existing)

    service = build_service_app(source)
    stop_service(domain)

    existing = monitor.read_state(monitor.DATA)
    if existing:
        updated = cadence_migration(c, previous, existing)
        if updated is not existing:
            backup = monitor.BASE/f'checkpoint-before-cadence-{time.time_ns()}.json'
            monitor.atomic(backup, json.dumps(dict(config=previous, state=existing), indent=2)+'\n')
            monitor.atomic(monitor.DATA/'state.json', json.dumps(updated, indent=2)+'\n')
            events = monitor.journals(monitor.DATA)[1]
            if previous['interval_seconds'] != c['interval_seconds']:
                events.append(dict(type='cadence_changed', at=monitor.stamp(),
                    previous_seconds=previous['interval_seconds'], interval_seconds=c['interval_seconds'],
                    note='Checkpoint preserved; confirmation streaks reset. Probe definitions unchanged.'))
            if previous['speed_hours'] != c['speed_hours']:
                events.append(dict(type='speed_schedule_changed', at=monitor.stamp(),
                    previous_hours=previous['speed_hours'], speed_hours=c['speed_hours'],
                    speed_slot=c['speed_slot'], timezone='America/Los_Angeles',
                    note='Checkpoint and incident history preserved. No catch-up speed tests.'))
    for name in ('monitor.py', 'manage.py', 'performance.py', 'analysis.py', 'devices.py', 'agent_query.py', 'sync.py', 'peer_transport.py', 'diagnostics.py', 'host_metrics.py', 'investigation.py', 'AGENTS.md', 'service.c',
                 'README.md', 'CONTRIBUTING.md', 'DEPLOYMENT.md', 'DASHBOARD_DESIGN.md', 'DIAGNOSTIC_RESEARCH.md', 'ACKNOWLEDGMENTS.md', 'CODE_REVIEW.md', 'INVESTIGATIONS.md', 'LICENSE', 'SECURITY.md', 'ARCHITECTURE.md'):
        src, dst = source/name, monitor.BASE/name
        if src.resolve() != dst.resolve():
            shutil.copy2(src, dst)
            dst.chmod(0o600)
    monitor.atomic(monitor.BASE/'devices.json', json.dumps(device_rows, indent=2)+'\n')
    monitor.atomic(monitor.BASE/'config.json', json.dumps(c, indent=2)+'\n')
    python = sys.executable
    wrapper = '#!/bin/sh\nexec '+shlex.quote(python)+' '+shlex.quote(str(monitor.BASE/'monitor.py'))+' "$@"\n'
    monitor.atomic(LAUNCHER, wrapper)
    LAUNCHER.chmod(0o700)
    job = dict(Label=LABEL, ProgramArguments=[str(service), python, str(monitor.BASE/'monitor.py'), 'run'],
               RunAtLoad=True, KeepAlive=True, ThrottleInterval=30, ProcessType='Background',
               WorkingDirectory=str(monitor.BASE), Umask=63,
               StandardOutPath='/dev/null', StandardErrorPath='/dev/null',
               EnvironmentVariables={'PATH': '/usr/bin:/bin:/usr/sbin:/sbin'},
               AssociatedBundleIdentifiers=[APP_ID])
    PLIST.write_bytes(plistlib.dumps(job))
    PLIST.chmod(0o600)
    launchctl('enable', domain+'/'+LABEL)
    for attempt in range(5):
        result = launchctl('bootstrap', domain, str(PLIST), check=False)
        if result.returncode == 0:
            break
        time.sleep(1)
    else:
        raise RuntimeError('launchctl bootstrap failed: '+result.stderr.strip())
    (monitor.BASE/'monitoring-paused').unlink(missing_ok=True)
    state = wait_for_sample(monitor.DATA, time.time())
    print(monitor.report(state))
    print('\nInstalled:', PLIST)
    print('Logs:', monitor.DATA)
    print('Status command:', LAUNCHER, 'status')


def sync_control(action):
    label=LABEL+'.sync'
    plist=PLIST.with_name(label+'.plist')
    if not plist.exists(): return
    domain=f'gui/{os.getuid()}'
    if action=='resume':
        launchctl('enable',domain+'/'+label)
        if launchctl('print',domain+'/'+label,check=False).returncode:
            launchctl('bootstrap',domain,str(plist))
    else:
        launchctl('disable',domain+'/'+label)
        launchctl('bootout',domain+'/'+label,check=False)
        for _ in range(20):
            if launchctl('print',domain+'/'+label,check=False).returncode: break
            time.sleep(0.25)
        else: raise RuntimeError('Synchronization is still stopping; retry shortly')


def control(action, confirm=False):
    if action in ('delete-history','clear-peer-cache') and not confirm:
        raise ValueError('Deletion requires --confirm; export evidence first.')
    with (monitor.BASE/'control.lock').open('a') as lock:
        try:
            fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            raise RuntimeError('Another monitoring control is in progress.')
        return _control(action, confirm)


def _control(action, confirm=False):

    domain = f'gui/{os.getuid()}'
    marker = monitor.BASE/'monitoring-paused'
    if action == 'pause':
        launchctl('disable', domain+'/'+LABEL)
        monitor.atomic(marker, 'Monitoring stopped by user. Resume explicitly.\n')
        stop_service(domain)
        sync_control('pause')
        print('Monitoring stopped on this Mac, including future logins. History preserved.')
    elif action == 'resume':
        if not PLIST.exists():
            raise RuntimeError('Recorder is not installed; install it first.')
        launchctl('enable', domain+'/'+LABEL)
        if launchctl('print', domain+'/'+LABEL, check=False).returncode:
            launchctl('bootstrap', domain, str(PLIST))
        marker.unlink(missing_ok=True)
        sync_control('resume')
        print('Monitoring started. Allow up to 60 seconds for a fresh sample.')
    elif action == 'clear-peer-cache':
        if not confirm: raise ValueError('Cache clearing requires --confirm')
        was_paused=marker.exists()
        sync_control('pause')
        peer=monitor.BASE/'Sync/peer'
        if peer.exists() and not peer.is_symlink(): shutil.rmtree(peer)
        if not was_paused: sync_control('resume')
        print('Local peer cache cleared. Source history is unchanged; synchronization can refill it.')
    elif action == 'delete-history':
        if not confirm:
            raise ValueError('Deletion requires --confirm; export evidence first.')
        if not marker.exists() or not launchctl('print', domain+'/'+LABEL, check=False).returncode:
            raise RuntimeError('Stop monitoring before deleting history.')
        sync_control('pause')
        with ExitStack() as stack:
            for name in ('monitor.lock', 'speed.lock', 'investigation.lock', 'investigation-save.lock'):
                lock = stack.enter_context((monitor.DATA/name).open('a'))
                try:
                    fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
                except BlockingIOError:
                    raise RuntimeError('A recorder or speed test is still running; retry after it exits.')

            names = ('samples-', 'events-', 'performance-', 'observations-', 'diagnostics-', 'investigations-')
            files = [p for p in monitor.DATA.iterdir() if
                     (p.name.startswith(names) and p.suffix == '.jsonl') or
                     p.name in ('state.json', 'status.html', 'service.log', 'service.log.1', 'service.log.2', 'service.log.3', 'speed-schedule.json', 'investigation-latest.json', 'investigation-active.json', 'investigation-auto.json')]
            for path in files:
                if path.is_file() and not path.is_symlink():
                    path.unlink()
            sync_root=monitor.BASE/'Sync'
            if sync_root.exists():
                import sync
                import uuid
                sync.save(sync_root/'generation.json', {'id':uuid.uuid4().hex})
                if (sync_root/'outbox').exists(): shutil.rmtree(sync_root/'outbox')
            print('Active monitoring history deleted. Monitoring remains stopped. Exported snapshots and archived backups are unchanged.')


def uninstall():
    sync_control('pause')
    PLIST.with_name(LABEL+'.sync.plist').unlink(missing_ok=True)
    launchctl('bootout', f'gui/{os.getuid()}/'+LABEL, check=False)
    PLIST.unlink(missing_ok=True)
    LAUNCHER.unlink(missing_ok=True)
    print('Service removed. Program and all evidence preserved at:')
    print(monitor.BASE)
    print(monitor.DATA)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('action', choices=('install', 'uninstall', 'service-status', 'pause', 'resume', 'delete-history', 'clear-peer-cache'))
    parser.add_argument('--expected-host')
    parser.add_argument('--config', type=Path)
    parser.add_argument('--devices', type=Path)
    parser.add_argument('--confirm', action='store_true')
    args = parser.parse_args()
    if args.action == 'install':
        install(Path(__file__).resolve().parent, args.expected_host, args.config, args.devices)
    elif args.action in ('pause', 'resume', 'delete-history', 'clear-peer-cache'):
        control(args.action, args.confirm)
    elif args.action == 'uninstall':
        uninstall()
    else:
        result = launchctl('print', f'gui/{os.getuid()}/'+LABEL, check=False)
        print(result.stdout or result.stderr)
        return result.returncode
    return 0


if __name__ == '__main__':
    try:
        sys.exit(main())
    except (ValueError, OSError, RuntimeError, subprocess.CalledProcessError) as exc:
        print('Install/manage failed:', exc, file=sys.stderr)
        sys.exit(1)
