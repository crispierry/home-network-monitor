#!/usr/bin/env python3

import argparse
import hashlib
import json
from pathlib import Path
import plistlib
import shutil
import time
import subprocess
import tempfile

SOURCE = Path(__file__).resolve().parents[1]
BUNDLE_ID = 'com.crispierry.network-monitor.dashboard'
LSREGISTER = '/System/Library/Frameworks/CoreServices.framework/Frameworks/LaunchServices.framework/Support/lsregister'


def run(args):
    subprocess.run(list(map(str, args)), check=True)


def retire_dashboard(path):

    path = Path(path)
    if not path.exists():
        return
    if path.is_symlink():
        raise ValueError('Refusing a symlink: '+str(path))
    info = plistlib.loads((path/'Contents/Info.plist').read_bytes())
    if info.get('CFBundleIdentifier') != BUNDLE_ID:
        raise ValueError('Not a dashboard bundle: '+str(path))
    trash = Path.home()/'.Trash'
    trash.mkdir(exist_ok=True)

    subprocess.run([LSREGISTER, '-u', str(path)], capture_output=True)
    destination = trash/f'Network Monitor retired {time.time_ns()}.app'
    shutil.move(path, destination)
    print('Moved older dashboard to Trash:', path.name)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--install', action='store_true')
    args = parser.parse_args()
    release = json.loads((SOURCE/'release.json').read_text())
    target = SOURCE/'dist/Network Monitor.app'
    if target.exists():
        shutil.rmtree(target)
    contents = target/'Contents'
    (contents/'MacOS').mkdir(parents=True)
    (contents/'Resources').mkdir()
    files = [SOURCE/'macos'/name for name in ('DashboardData.swift', 'DashboardStore.swift', 'DashboardView.swift', 'NetworkMonitorApp.swift')]
    with tempfile.TemporaryDirectory(prefix='network-monitor-build-') as temp:
        temp = Path(temp)
        run(['xcrun', 'swiftc', '-O', '-swift-version', '5', '-parse-as-library', '-target', 'arm64-apple-macosx14.0',
             '-module-cache-path', temp/'cache', '-framework', 'SwiftUI', '-framework', 'Charts',
             *files, '-o', contents/'MacOS/NetworkMonitor'])
        run(['xcrun', 'swiftc', SOURCE/'macos/Icon.swift', '-module-cache-path', temp/'cache', '-o', temp/'draw-icon'])
        run([temp/'draw-icon', temp/'AppIcon.iconset'])
        run(['iconutil', '-c', 'icns', temp/'AppIcon.iconset', '-o', contents/'Resources/AppIcon.icns'])
        shutil.copy2(temp/'AppIcon.iconset/icon_512x512@2x.png', contents/'Resources/AppIcon.png')
    info = dict(CFBundleName='Network Monitor', CFBundleDisplayName='Network Monitor', CFBundleExecutable='NetworkMonitor',
                CFBundleIdentifier=BUNDLE_ID, CFBundlePackageType='APPL', CFBundleVersion=str(release['build']), CFBundleShortVersionString=release['version'],
                CFBundleIconFile='AppIcon', LSMinimumSystemVersion='14.0', NSHighResolutionCapable=True,
                NSHumanReadableCopyright='Local network evidence · no router credentials required')
    (contents/'Info.plist').write_bytes(plistlib.dumps(info))
    manifest = {str(p.relative_to(SOURCE)): hashlib.sha256(p.read_bytes()).hexdigest() for p in files+[SOURCE/'macos/Icon.swift',SOURCE/'release.json']}
    (contents/'Resources/source.plist').write_bytes(plistlib.dumps(manifest))
    run(['codesign', '--force', '--sign', '-', '--identifier', BUNDLE_ID, target])
    run(['codesign', '--verify', '--strict', target])
    if args.install:
        destination = Path.home()/'Applications/Network Monitor.app'
        destination.parent.mkdir(exist_ok=True)
        retire_dashboard(destination)
        shutil.copytree(target, destination)
        run(['codesign', '--verify', '--strict', destination])
        for previous in (Path.home()/'Library/Application Support/NetworkMonitor').glob('Dashboard Previous*.app'):
            retire_dashboard(previous)
        subprocess.run([LSREGISTER, '-u', str(target)], capture_output=True)
        run([LSREGISTER, '-f', destination])
        support = Path.home()/'Library/Application Support/NetworkMonitor'
        if support.exists():
            for name in ('README.md', 'DASHBOARD_DESIGN.md'):
                shutil.copy2(SOURCE/name, support/name)
                (support/name).chmod(0o600)
        print('Installed native dashboard:', destination)
    print('Built:', target)
    print('Recorder remains independent; closing this app does not stop monitoring.')


if __name__ == '__main__':
    main()
