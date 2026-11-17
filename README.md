# Network Monitor

A local macOS recorder and native dashboard for intermittent home-network problems. Compare a wired observer with a wireless observer, preserve evidence through an outage, and inspect latency, loss, DNS, HTTPS and scheduled throughput measurements.

The recorder uses Python's standard library and macOS tools. The SwiftUI dashboard is optional: closing it does not stop collection. No cloud account, router password, telemetry service or paid subscription is required. This is a source release for Apple Silicon Macs running macOS 14 or later; builds are locally signed, not notarized distribution packages.

## What it measures

- Router, upstream gateway, configured satellites and another observer: ICMP and selected service checks.
- Independent Cloudflare and Google endpoints: ICMP, TCP, DNS and certificate-validated HTTPS.
- Incident start/recovery per check, with original failure times, confirmation thresholds and observation gaps.
- Up to twelve manually configured devices, with address reachability and MAC identity where macOS makes it available.
- Host CPU, memory pressure, interface traffic/errors, bounded gateway status and diagnostic routes.
- Optional scheduled download/upload tests, with latency observations before, during and after load.
- Bounded high-resolution incident close-ups, optional external MTR/iperf3 integrations and read-only JSON queries for local agents.

## Install

Install Python 3.10 or later and Apple's Command Line Tools. Use a stable interpreter path: removing that interpreter breaks the service. The dashboard build targets arm64/macOS 14.

```sh
git clone https://github.com/crispierry/home-network-monitor.git
cd home-network-monitor
cp config.json config.local.json
cp devices.example.json devices.local.json
```

Edit `config.local.json` with your Mac's LocalHostName (`scutil --get LocalHostName`), router/gateway IPv4 addresses, the other observer's hostname, and optional satellite addresses. Shipped `192.0.2.x` values are documentation examples, not working targets. `orbi` is the router field; gateway web diagnostics currently understand AT&T status pages. Other gateways retain reachability checks but may supply no status details.

Edit `devices.local.json` with confirmed device addresses/MACs and dated attachment notes, or use an empty array. Device attachment is manual inventory, not live satellite association. Both local files are ignored by Git; installed copies remain outside the checkout.

Speed tests are disabled in the public example. To enable them, set `speed_enabled` to true, choose `speed_hours` (0–23), and use slot 0 on one observer and slot 1 on the other. Slots start at :15:30 and :45:30 in America/Los_Angeles. Tests consume bandwidth and can affect calls; reduce the schedule when investigation ends. Skipped tests do not run a catch-up burst.

```sh
sh scripts/check.sh
python3 manage.py install --config config.local.json --devices devices.local.json
python3 scripts/build_macos.py --install
```

Install while logged into the intended macOS account. Allow the dedicated Network Monitor service Local Network access when macOS asks. Open `~/Applications/Network Monitor.app`. After reboot, LaunchAgents resume after that user logs in; they do not run before login, unlock FileVault or change sleep/power settings. A headless Mac still needs an active user session.

For upgrades, quit the dashboard, update the checkout, then run `python3 manage.py install` and `python3 scripts/build_macos.py --install`. Existing private settings and device inventory are preserved. The build installer retires verified old dashboard bundles to Trash and keeps the separate service launcher.

## Use

Overview shows current evidence, freshness, path history and recent incidents. Performance shows latency/loss and separate speed tests. Charts offer time-range selection, zoom/detail controls and individual sample inspection. Devices distinguishes replies, unknown identities and confirmed changes. Evidence and expandable details expose supporting measurements. Monitoring & storage provides stop/resume, deletion and storage information.

```sh
~/.local/bin/network-monitor status
~/.local/bin/network-monitor query --hours 24
~/.local/bin/network-monitor incidents --limit 10
~/.local/bin/network-monitor investigate status
python3 scripts/verify_install.py --compact
```

Local agents such as ChatGPT can use the read-only query without an API key. See [AGENTS.md](AGENTS.md). For remote viewing, use your existing authenticated remote desktop connection. Do not port-forward the app. Export/import snapshots for offline comparisons; exports contain private network evidence. Optional encrypted LAN sharing is disabled until paired; see [SYNC_SETUP.md](SYNC_SETUP.md) for its currently restricted two-observer profile.

## Interpret the evidence

Missing or stale evidence means unknown, never healthy. Two failed samples confirm a check outage with the default thresholds; recovery also needs two passes. Sampling can miss events between checks. Pings may be filtered or de-prioritized, so compare HTTPS, DNS and TCP. Intermediate traceroute loss does not identify a faulty forwarding hop. Device replies do not prove camera video, voice-assistant cloud access or remote desktop works.

Simultaneous wired and wireless public-endpoint failures with a responsive router suggest a shared upstream problem. Wireless-only deterioration toward the router suggests a local wireless path or observer issue. Failures toward the router from both observers suggest the router/local network deserves investigation. These are hypotheses, not proof of faulty hardware. Clean public probes cannot clear a separate meeting computer or the actual Zoom media path. Speed tests measure one observer's path under deliberate load, not every room or every device.

## Files and retention

| Location | Purpose |
| --- | --- |
| `~/Library/Application Support/NetworkMonitor` | Installed runtime, private configuration, optional sync cache |
| `~/Library/Logs/NetworkMonitor` | State and rotating raw JSONL evidence |
| `~/Library/LaunchAgents/com.crispierry.network-monitor.plist` | Per-user recorder job |
| `~/.local/bin/network-monitor` | CLI |
| `~/Applications/Network Monitor.app` | Dashboard |

Primary samples have a 256 MiB / 30-day ceiling. Events have 16 MiB / 180 days; speed history 8 MiB / 180 days; observations 4 MiB / 180 days; diagnostics 32 MiB / 30 days; investigations 8 MiB / 30 days. Whichever size or age bound is reached first wins. State, service errors and optional summary caches add bounded overhead. Dashboard charts retain seven days in memory and speed/observation caches retain 180 days. User exports, builds, Trash and migration backups are outside retention budgets. See [ARCHITECTURE.md](ARCHITECTURE.md).

## Troubleshoot and remove

If data is stale, check `python3 manage.py service-status`, the interpreter path, login/sleep state, and `service.log` in the evidence directory. If foreground checks work but background local checks fail, review macOS Local Network permission for the service app. Do not disable the firewall. Missing gateway pages or denied host metrics remain unavailable rather than passing.

Changing probe definitions deliberately requires archiving the old state: stop monitoring, preserve the evidence directory and installed configuration privately, move `state.json` out of the active directory, then install the explicit new configuration. This starts a new detector baseline; retain the archived checkpoint to explain any open incident. Normal upgrades do not require this procedure.

Use Monitoring & storage to stop/resume or explicitly delete history. Deletion leaves monitoring stopped and does not erase exports, backups or another observer's copy. Closing the app alone leaves monitoring running.

```sh
python3 manage.py uninstall
```

Uninstall removes the LaunchAgents and CLI while retaining evidence. Move the dashboard to Trash. Delete retained runtime/evidence only after saving what you need. Do not confuse the runtime's background launcher with a duplicate dashboard while monitoring remains installed.

## Development and license

See [CONTRIBUTING.md](CONTRIBUTING.md), [SECURITY.md](SECURITY.md), [INVESTIGATIONS.md](INVESTIGATIONS.md) and [CODE_REVIEW.md](CODE_REVIEW.md). Network Monitor is MIT licensed. External tools retain their own licenses and are not bundled; credits are in [ACKNOWLEDGMENTS.md](ACKNOWLEDGMENTS.md).
