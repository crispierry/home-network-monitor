# Contributing

The project uses standard-library Python 3.10+ and native SwiftUI/Charts on Apple Silicon macOS 14+. Run `sh scripts/check.sh` for offline Python tests and configuration checks. Run `sh scripts/check_macos.sh` for the native evidence-reader tests. Use `python3 scripts/build_macos.py` to compile the dashboard without installing it.

Generate an isolated visual fixture with `python3 scripts/dashboard_fixture.py /tmp/network-monitor-example` (choose a new directory). Launch the built executable with `--fixture --evidence-dir /tmp/network-monitor-example`. Check recovered, outage and stale fixtures, keyboard navigation, full-row disclosures, minimum window size, readable dark/light colors, chart zoom and missing-data semantics. Never mix synthetic records with installed evidence.

A checkout is separate from deployment. Normal upgrades preserve private installed configuration; first installation requires explicit settings. Do not run bandwidth tests, open listeners, change routers or delete real evidence as part of routine tests. Do not commit real inventories, logs, certificates, cookies, passwords or private incident reports. Use documentation addresses and locally administered synthetic MACs in fixtures.

Keep names and small functions explanatory. Source comments/docstrings are omitted by project convention; maintain rationale and contracts in focused documentation and behavioral regression tests. Preserve executable shebangs and required compiler directives. Do not vendor third-party source without reviewing its license and notices. Contributions are under the project's MIT license.

For incident reports, include version, time/timezone, observation host/interface, actual user impact, evidence freshness and a redacted summary. Missing measurements are unknown, not zero. State diagnostic conclusions as hypotheses. Read SECURITY.md before reporting a vulnerability.
