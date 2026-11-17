# Network Monitor

Network Monitor records evidence of intermittent home-network problems and displays it in a native macOS dashboard. It runs fully on one Mac. An optional second Mac adds a wired-versus-wireless comparison when the internet slows down or becomes unreachable.

The recorder continues working when the network fails or the dashboard is closed. Evidence stays on each Mac. No cloud account, router password, telemetry service, or paid subscription is required.

**Release:** 2.7.1 · **Platform:** Apple Silicon, macOS 14 or later · **License:** MIT

This is a source release. You build the app locally; a notarized installer is not provided.

## What you can learn

| Question | Evidence available |
| --- | --- |
| Can this Mac reach the router and internet? | Checks every 15 seconds by default, using ping, TCP connections, DNS, and certificate-validated HTTPS |
| When did a problem begin and recover? | Per-check incident timelines, confirmation thresholds, and gaps when the recorder could not observe |
| Is the wired path behaving differently from Wi-Fi? | Independent observations from two Macs, compared through imported snapshots or optional sharing |
| Is performance deteriorating? | Response times, ping loss, scheduled download/upload tests, and latency observations during those tests |
| Which devices still answer locally? | Up to twelve configured devices, with address reachability and MAC identity where available |
| What else was happening? | Observer CPU/memory/interface context, supported gateway status pages, and bounded diagnostic captures |

A successful check proves only what it tested. Device replies do not prove camera video or voice-assistant cloud access works. Clean public probes cannot rule out a problem on another computer or on Zoom's actual media path.

## Find internet interruptions

The **Overview** starts with an **Internet access · incident timeline**. It is also at the top of **Incidents** and **Performance**, whether you select one Mini or both. Use the **Show** selector above the content to choose Mini-One, Mini-Two, or Both Minis. The sidebar provides the same choices. Selection changes the charts and counts; it does not change recording.

Each timeline row shows sampled HTTPS reachability from that Mac: passing, mixed, failing, or no evidence. Crosses mark confirmed interruptions, so short events remain visible in a full-day view. Drag horizontally to zoom, click to inspect, or use the zoom and time-navigation buttons. **Incidents** provides expandable timing and evidence; an individual Mini also has the detailed path timeline.

An interruption count requires overlapping confirmed failures to **both** public HTTPS destinations. An isolated ping, DNS, satellite, or single-destination failure remains in the detailed incident list without being counted as lost internet access. Counts are per observer and use retained incident history; do not add the two counts to estimate distinct household outages. Missing recording time remains unknown, and a recording gap makes continuity and duration uncertain. The timeline is evidence from the monitoring Macs, not proof of another device's cloud connectivity or the physical cause.

Wide latency charts preserve peaks instead of drawing averages. Zoom in for individual measurements; use the performance statistics to distinguish typical latency from occasional spikes.

Click the legend labels beneath a graph to show or hide its series. Speed labels identify each Mini and direction separately, so any combination can stay visible; hidden labels stay available to restore a series. Speed charts show measured dots, an optional smooth trend curve and optional dashed average lines. The numeric averages and test counts use only measured values in the visible time interval, separately for each Mini and direction. Zooming recalculates them. The curve averages up to three recent tests; it is not a measurement of speeds between tests. Missing values are excluded, and the curve breaks at failed tests, interface changes and gaps over two hours. Use **Reset** to return to the full history range.

## One computer is enough

The recorder, dashboard, incident detection, device checks, internet speed tests, and local agent queries all work on a single Mac. Leave `peer` as `""` and skip the optional sharing setup. No second account, computer, or synchronization service is required. Without configured satellites or a peer, the default profile runs 14 checks.

The dashboard shows only configured path lanes and offers cross-observer views when peer evidence is available. Missing optional process/resource measurements do not stop recording; Activity Monitor can show CPU and memory use without the summary worker.

A second computer is useful for comparing two paths and is required for the optional iperf3 LAN test. One observer cannot conclusively separate its own Wi-Fi or hardware problem from a shared network fault. Your existing two-computer configuration is preserved on upgrade.

## Before installing

You need Python 3.10 or later and Apple's Command Line Tools. The recorder uses Python's standard library and macOS utilities; the dashboard uses SwiftUI and Charts. Keep the selected Python interpreter installed at a stable path because the background job uses that exact interpreter.

Install from the intended user's logged-in macOS session. After a reboot, the recorder resumes **after that user logs in**. It does not unlock FileVault, run before login, or prevent sleep. A headless Mac still needs a user session.

The probes were developed for an Orbi router behind an AT&T gateway. Some details remain specific to that setup:

- Router and gateway service checks expect TCP port 80; the router DNS check expects a DNS service.
- Gateway web diagnostics understand AT&T status pages. Unsupported pages remain unavailable.
- Satellite identity checks currently expect Orbi **RBE770**. Other models can answer ping/TCP while failing that identity check; this alone is not an outage.
- Automatic sharing supports only the named two-Mini profile described in [SYNC_SETUP.md](SYNC_SETUP.md). Local recording and snapshot export/import do not require sharing.

## First installation

Run these commands from Terminal on each Mac you want to monitor.

### 1. Create private settings

```sh
git clone https://github.com/crispierry/home-network-monitor.git
cd home-network-monitor
cp config.json config.local.json
cp devices.example.json devices.local.json
scutil --get LocalHostName
```

Edit `config.local.json` before installing:

| Setting | What to enter |
| --- | --- |
| `expected_host` | This Mac's LocalHostName, printed by the command above |
| `orbi` | Main router's IPv4 address |
| `gateway` | Upstream gateway's IPv4 address |
| `peer` | Leave `""` for one computer (the default). Set a hostname only if you want to probe another computer. |
| `satellites` | An array of confirmed satellite IPv4 addresses, or `[]` |
| `speed_enabled` | Leave `false` initially, or configure the schedule below |

The shipped `192.0.2.x` addresses are documentation examples, not working targets. Keep the other defaults unless you need to change them. An empty `peer` removes that check entirely. If you explicitly configure a peer, its failed replies remain visible; they do not establish an internet outage.

Edit `devices.local.json` with confirmed device addresses, MACs, and dated attachment notes, or replace its contents with `[]`. Attachment notes are a manual inventory, not live satellite association. These two local files are ignored by Git. Installed settings are stored outside the checkout.

### 2. Validate, install, and open

```sh
sh scripts/check.sh
python3 manage.py install --config config.local.json --devices devices.local.json
python3 scripts/build_macos.py --install
open "$HOME/Applications/Network Monitor.app"
```

The check script uses synthetic data and does not probe your network. Installation starts live monitoring. Allow the Network Monitor service Local Network access when macOS requests it.

### 3. Verify the installation

```sh
~/.local/bin/network-monitor status
python3 scripts/verify_install.py --compact
```

Confirm that the host/interface are correct, `service_running` is true, samples and diagnostics are fresh, and installed source/signature checks pass. A failed network probe is evidence to investigate; it is not automatically an installation failure. See [DEPLOYMENT.md](DEPLOYMENT.md) for the full checklist.

## Configure speed tests

Speed tests are disabled in the public example. To enable them, set `speed_enabled` to `true`, list the desired hours in `speed_hours`, and select a `speed_slot`:

| Observer | Slot | Earliest start in each selected hour |
| --- | --- | --- |
| Only Mac, or first of two | `0` | :15:30 |
| Optional second Mac | `1` | :45:30 |

Schedules use **America/Los_Angeles**, including daylight saving time. To test hourly, list every integer from `0` through `23` in `speed_hours`. The test starts when the recorder next checks the schedule within its allowed window; it is not guaranteed to start at the exact second. Skipped tests do not cause a catch-up burst.

Tests consume bandwidth and can affect calls. Reduce the schedule when the investigation ends. They measure the observing Mac's path, not every room or device. To apply changed settings to an existing installation, run `python3 manage.py install --config config.local.json` from the checkout. Keep that private file current before using it; omitting `--config` preserves the installed settings instead.

## Use the dashboard

| Page or control | Use it for |
| --- | --- |
| **Overview** | Current reachability, evidence freshness, recent history, and symptoms |
| **Performance** | Latency/loss charts and separate throughput measurements; zoom or inspect individual samples |
| **Devices** | Local replies, identity uncertainty, and changes for watched devices |
| **Incidents** | Failure and recovery times for each affected check |
| **Evidence** | Raw logs and snapshot export |
| **Monitoring & storage** | Resource/storage information, stop/resume, and history deletion |

Click anywhere on an expandable row to open or close its details, including the label and blank space. **Show details** changes to **Hide details** when open. This also applies to **Affected checks** inside an incident.

For a short stall, expand **Performance → Investigations and computer details** and use **Connection investigation**. See [INVESTIGATIONS.md](INVESTIGATIONS.md) for captures, route inspection, and optional iperf3 tests.

Use your existing authenticated remote desktop connection to view the app remotely. For an offline comparison, choose **Evidence → Export snapshot…** on one Mac, transfer the file privately, and use **Import snapshot…** on the other. Snapshots contain private network evidence and do not update themselves. Optional encrypted sharing requires separate [pairing and verification](SYNC_SETUP.md); it is disabled by default. Do not port-forward the app.

## Read results from Terminal or a local agent

These commands read saved evidence without running probes or speed tests:

```sh
~/.local/bin/network-monitor status
~/.local/bin/network-monitor query --hours 24
~/.local/bin/network-monitor incidents --limit 10
~/.local/bin/network-monitor investigate status
```

ChatGPT or another agent on the Mac can run the JSON query with local command access. No API key is needed, and no cloud connector is registered automatically. [AGENTS.md](AGENTS.md) explains the evidence fields and interpretation rules.

## Interpret failures carefully

Missing or stale evidence means **unknown**. With the default thresholds, two failed samples confirm a check outage and two successful samples confirm recovery. The timeline preserves the first failure/recovery sample. Sampling can miss events between checks.

| Observed pattern | Hypothesis to investigate |
| --- | --- |
| Both Macs lose public endpoints while the router answers | Shared upstream connectivity or congestion |
| Only the wireless Mac deteriorates toward the router | Wi-Fi path, local load, or that observer |
| Both Macs lose checks toward the router | Router or local connectivity; also check each observer's state |
| Ping fails while HTTPS/TCP succeeds | ICMP filtering or de-prioritization, rather than complete loss of access |
| Direct public DNS works but system/router DNS fails | Local resolver or router DNS problem |

These patterns guide investigation; they do not prove a hardware defect. Intermediate traceroute loss does not identify a faulty forwarding hop. Compare overlapping times, protocols, and observers before drawing conclusions.

## Storage and retention

| Location | Contents |
| --- | --- |
| `~/Library/Application Support/NetworkMonitor` | Installed runtime, private settings, optional sync cache |
| `~/Library/Logs/NetworkMonitor` | Current state and rotating raw JSONL evidence |
| `~/Library/LaunchAgents/com.crispierry.network-monitor.plist` | Per-user recorder job |
| `~/.local/bin/network-monitor` | Command-line entry point |
| `~/Applications/Network Monitor.app` | Native dashboard |

Retention ends when either the size or age limit is reached:

| Evidence | Size ceiling | Age ceiling |
| --- | --- | --- |
| Primary samples | 256 MiB | 30 days |
| Events | 16 MiB | 180 days |
| Speed tests | 8 MiB | 180 days |
| Human observations | 4 MiB | 180 days |
| Diagnostics | 32 MiB | 30 days |
| Investigations | 32 MiB | 30 days |

State, service errors, and optional summary caches add bounded overhead. Charts keep seven days of samples in memory; speed/observation caches keep up to 180 days. User exports, builds, Trash, and migration backups are outside automatic retention. See [ARCHITECTURE.md](ARCHITECTURE.md) for storage and failure handling.

## Upgrade

Quit the dashboard, then run these commands from the checkout:

```sh
git pull --ff-only
python3 manage.py install
python3 scripts/build_macos.py --install
open "$HOME/Applications/Network Monitor.app"
python3 scripts/verify_install.py --compact
```

Existing private settings and device inventory are preserved. The dashboard installer moves verified older dashboard bundles to Trash. It retains the separate background service launcher. If you installed the optional summary worker, also follow its [upgrade instructions](SYNC_SETUP.md).

## Troubleshoot

| Symptom | First checks |
| --- | --- |
| Missing or stale results | Run `python3 manage.py service-status` from the checkout; inspect the Python path, login/sleep state, and `service.log` in the logs folder |
| Foreground probes work but background LAN probes fail | Review macOS Local Network permission for the service app; do not disable the firewall |
| Gateway pages or host metrics are unavailable | Check their individual timestamps and error details; unsupported or denied data is unknown |
| Other Mac is missing or stale | Check its recorder independently, then snapshot age or optional sharing setup |
| Speed result is missing | Check the configured hours/slot and saved skipped/error reason; missing throughput is not zero |

Changing probe targets or definitions requires a deliberate baseline reset. Stop monitoring, privately preserve the evidence folder and installed settings, move `state.json` out of the active evidence folder, and install the explicit new configuration. Retain the archived checkpoint to explain any open incident. Normal upgrades do not require this procedure.

## Stop, delete history, or remove

**Monitoring & storage** provides stop/resume and history deletion. Closing the dashboard alone leaves the recorder running. Deleting history leaves monitoring stopped and does not erase exports, backups, or another observer's copy.

To uninstall, run this from the checkout:

```sh
python3 manage.py uninstall
```

This removes the recorder/sync LaunchAgents and CLI while retaining evidence. Move the dashboard to Trash. Remove retained runtime/evidence only after saving what you need. While monitoring remains installed, the runtime's service launcher is required and is not a duplicate dashboard.

## Project documentation

| Guide | Audience and purpose |
| --- | --- |
| [Deployment](DEPLOYMENT.md) | Installers: verify each Mac and record deployment results |
| [Investigations](INVESTIGATIONS.md) | Users: run and interpret focused diagnostic tests |
| [Sharing setup](SYNC_SETUP.md) | Users: pair the supported two-Mini profile |
| [Agent access](AGENTS.md) | Local agents: query evidence and respect diagnostic limits |
| [Architecture](ARCHITECTURE.md) | Contributors: data flow, storage bounds, and failure handling |
| [Dashboard design](DASHBOARD_DESIGN.md) / [multiple observers](UNIFIED_DASHBOARD_DESIGN.md) | Contributors: presentation and comparison rules |
| [Contributing](CONTRIBUTING.md) | Contributors: builds, tests, fixtures, and reporting |
| [Security](SECURITY.md) | Trust boundaries and private vulnerability reporting |
| [Release review](CODE_REVIEW.md) | Validation performed for 2.6.0 and remaining limits |
| [Diagnostic references](DIAGNOSTIC_RESEARCH.md) / [comparative scope](COMPETITIVE_REVIEW.md) | Rationale and related tools |
| [Acknowledgments](ACKNOWLEDGMENTS.md) | Upstream credits and license references |

Network Monitor is licensed under [MIT](LICENSE). External tools are installed separately, are not bundled, and retain their own licenses.
