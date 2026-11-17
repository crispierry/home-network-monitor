#!/bin/sh
set -eu

cd "$(dirname "$0")/.."
monitor_python="${NETWORK_MONITOR_PYTHON:-python3}"

"$monitor_python" -m unittest discover -s tests -v
"$monitor_python" -m py_compile monitor.py manage.py performance.py analysis.py devices.py agent_query.py diagnostics.py host_metrics.py investigation.py sync.py peer_transport.py scripts/configure_sync.py
"$monitor_python" - <<'PY'
from pathlib import Path
import monitor

configuration = monitor.config(Path('config.json'))
checks = monitor.specs(configuration)
print(f'Configuration valid: {len(checks)} probes, {len(configuration["satellites"])} satellites.')
print('Local validation passed. No live probes or service changes were performed.')
PY
