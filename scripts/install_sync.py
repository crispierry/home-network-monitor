#!/usr/bin/env python3

import os
from pathlib import Path
import plistlib
import shutil
import subprocess
import sys
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
import monitor as m
import manage

source=Path(__file__).resolve().parents[1]
label='com.crispierry.network-monitor.sync'
domain=f'gui/{os.getuid()}'

launcher=m.BASE/'Network Monitor.app/Contents/MacOS/network-monitor-service'
if not launcher.exists(): raise SystemExit('Install the recorder first')
root=m.BASE/'Sync'; root.mkdir(exist_ok=True,mode=0o700)
manage.stop_service(domain, label)
for name in ('sync.py','peer_transport.py'):
    shutil.copy2(source/name,m.BASE/name); (m.BASE/name).chmod(0o600)
plist=Path.home()/'Library/LaunchAgents'/(label+'.plist')
job=dict(Label=label,ProgramArguments=[str(launcher),sys.executable,str(m.BASE/'sync.py'),'run'],
    RunAtLoad=True,KeepAlive=True,ThrottleInterval=30,ProcessType='Background',
    WorkingDirectory=str(m.BASE),Umask=63,StandardOutPath='/dev/null',StandardErrorPath='/dev/null',
    EnvironmentVariables={'PATH':'/usr/bin:/bin:/usr/sbin:/sbin'},AssociatedBundleIdentifiers=[manage.APP_ID])
plist.write_bytes(plistlib.dumps(job)); plist.chmod(0o600)
manage.launchctl('enable',domain+'/'+label)
manage.launchctl('bootstrap',domain,str(plist))
print('Local summary worker installed. Cross-Mac sharing remains disabled until explicitly configured.')
