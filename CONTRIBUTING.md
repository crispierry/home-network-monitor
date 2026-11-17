# Contributing

Network Monitor uses standard-library Python 3.10+ and SwiftUI/Charts on Apple Silicon macOS 14+. Start with the [architecture](ARCHITECTURE.md) and [dashboard design](DASHBOARD_DESIGN.md) before changing behavior.

## Build and test

Run these commands from the repository root:

```sh
sh scripts/check.sh
sh scripts/check_macos.sh
python3 scripts/build_macos.py
```

The first script runs offline Python tests and configuration checks. The second runs native evidence-reader tests. The build creates `dist/Network Monitor.app` without installing it. These steps do not require live network probes or bandwidth tests.

## Check the interface

Create an isolated fixture in a new directory, then open the built executable against it:

```sh
python3 scripts/dashboard_fixture.py /tmp/network-monitor-example --state outage
"dist/Network Monitor.app/Contents/MacOS/NetworkMonitor" --fixture --evidence-dir /tmp/network-monitor-example
```

Use `--single-computer` to check the default standalone layout without peer or satellite checks. Repeat with `--state recovered` and `--state stale`, choosing a new directory for each. Never mix synthetic records with installed evidence. Check:

- Navigation, keyboard access, and full-row disclosure controls.
- Readability at the minimum window size and in light/dark appearances.
- Chart zoom, sample inspection, missing replies, and observation gaps.
- Clear source/time labels for live, imported, and stale data.

## Keep development separate from deployment

A checkout is not the installed recorder. Follow [DEPLOYMENT.md](DEPLOYMENT.md) when installing a change. Normal upgrades preserve private settings; first installation requires explicit configuration.

Routine tests must not run bandwidth tests, open listeners, change routers, or delete real evidence. Use documentation addresses and locally administered synthetic MACs in fixtures. Never commit real inventories, logs, certificates, cookies, passwords, or private incident reports.

## Code and documentation

Use explanatory names and small functions. Source comments/docstrings are omitted by project convention; document rationale and contracts in focused guides and behavioral tests. Preserve executable shebangs and required compiler directives.

Update user instructions when behavior changes. Distinguish a measurement from a hypothesis, and a tested feature from an intended design. Missing measurements are unknown, not zero. Do not vendor third-party source without reviewing its license and notices. Contributions are under the project's [MIT license](LICENSE).

## Report a problem

Include the version, time and timezone, observation host/interface, actual user impact, evidence freshness, and a redacted summary. Use synthetic reproductions where possible. Report suspected vulnerabilities privately using [SECURITY.md](SECURITY.md), not a public issue containing household logs.
