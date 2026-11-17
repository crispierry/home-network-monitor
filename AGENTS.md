# Network Monitor: local agent access

## Start with saved evidence

When asked about the monitored network, start with this read-only command on the Mac where you are running:

```sh
~/.local/bin/network-monitor query --hours 24
```

It returns `network-monitor.briefing.v1` JSON: host, evidence age, outbound internet health, individual checks, device replies/identity, observed coverage, median/p95 latency, failure rates, incidents and measured speeds. `network-monitor devices` returns a smaller current briefing. No network calls or speed tests are performed by either command. Queries do not alter evidence or controls. Use the installed command rather than assuming the Git checkout is deployed.

## Interpretation and action limits

- Name the observation host and observation time in answers. A stale recorder or device sample means unknown, even when its last result passed.
- Do not treat local device replies as proof that Ring video, Alexa, Google Home or Workbench cloud access works. Self-checks do not traverse the network.
- Attachment labels are a dated manual Orbi inventory. Never present them as current association/backhaul measurements.
- Never call a device offline from one failed ping or an ARP cache entry. `unreachable` means two missed replies after a reply baseline; sleep/filtering/address changes remain hypotheses.
- Coverage is sampled time, not continuous uptime. Throughput values are separate bandwidth tests, not per-device usage or every-room Wi-Fi speeds. Missing values are not zero.
- Start with the compact query. Use `raw --since ISO_TIMESTAMP --limit N`, `incidents --limit N`, `summary --hours N`, or `speed --history --json` for supporting evidence. Retention can remove older records. The query caps incident/event lists and states its limits.
- For an integrated installation, `network-monitor query --all-hosts --hours 24` reads both sources without networking. Each source reports its own observation age. Peer `incidents`, `speed_tests`, symptom notes and coverage use the requested time window; compact peer history has fewer fields than local raw history. A `peer_error` means its cache could not be read, not that the peer lost internet access.
- The other Mini records independently. Do not claim to have checked it without executing there or receiving a dated exported snapshot. Use authorized Screen Sharing/Workbench/file transfer; do not create a network listener.
- Ask before running manual speed tests, modifying routers/network settings, exposing evidence to other services, or deleting real history. Do not put credentials, cookies or raw evidence in Git. A request for information does not authorize stop/resume/delete actions.

The native app's Devices page has a **Copy query command** button. ChatGPT/Dots must have local command access; this is not an automatically registered cloud connector. No API key is needed. Instructions are also installed at `~/Library/Application Support/NetworkMonitor/AGENTS.md`.

- `address_reply` explicitly means an IP answered while macOS withheld neighbor identity. Do not upgrade this to a verified named-device reply; DHCP reuse remains possible.

## Meetings and application symptoms

For choppy meetings, inspect `recent_performance` and `reported_symptoms` in the briefing. Five-minute ping variation is not Zoom/RTP jitter. Reports are human observations, not confirmed incidents. Establish the actual meeting computer and location before attributing a problem to the monitored network. Compare overlapping evidence from both Minis; ask for Zoom's own send/receive statistics and CPU/memory readings when needed. This monitor does not collect those automatically. Never rule out the machine or the Zoom path from clean public probes, and do not run a bandwidth test during a meeting without explicit authorization.

## Supplemental diagnostics

Supplemental fault context: `network-monitor diagnostics --limit 5` reads `diagnostics-*.jsonl`; `query` includes the latest snapshot and its separate freshness. Compare gateway WAN/optical status, LAN port counters, host links/DHCP and bounded traces across the event. Individual page timestamps matter. Missing/login/timeout pages are unknown; IPv6 needs a working baseline; traceroute stars are not fault locations. Uptime/counter resets and wraps must be considered. Raw diagnostic history is not included in a dashboard summary export. Preserve the journal separately. No router credentials or authenticated Orbi logs are collected automatically.

### Host context

The recorder supplies passive `diagnostics.latest.host_metrics`: observer-wide CPU busy percent, memory pressure, swap used, and per-interface byte/error deltas. Check `host_context_stale` and the reading's own `at`. First samples, counter resets, missing providers and gaps over 180 seconds have null rates, not zero. CPU is averaged across all cores and across the stated interval; it is not the recorder's own CPU cost and can hide short or single-core spikes. Interface traffic includes LAN and internet activity, not available bandwidth or per-device usage. These readings cannot clear a separate Zoom computer. Full history remains in `diagnostics-*.jsonl`.

### Load and HTTPS timing

`speed_test_latency_comparison` groups the requested window by interface, target and this Mini's speed-test flag. It includes attempts, misses and successful-reply median/p95. The flag is sampled at probe-cycle start. Untagged records are omitted; false does not mean the house was idle. Do not call the difference a bufferbloat score or claim causation. Small groups are inconclusive.

HTTPS checks include `https_timing_ms` cumulative milliseconds from curl start through TCP connection, TLS completion, first byte, and total. Null means unavailable/not reached. These are milestones, not independent durations. Numeric destination pinning bypasses system DNS; normal certificate checks remain enabled. A timeout after TCP does not prove router or TLS-server failure.

## Saved investigations

Close-ups now include local loopback and configured satellite/peer pings in the same round as the router and public endpoints. Raw points retain `elapsed_ms`, `dispatch_delay_ms` and `round_started_at`; those process/dispatch timings are not wire RTT or a pure CPU measurement. `path_context_before/after` retain dated Wi-Fi, CPU, interface deltas and allowlisted power settings. Wi-Fi readings are normally every 60 seconds, with a 30-second minimum refresh during slow router pings, plus before/after close-ups. The `query.wifi` object has its own freshness. BSSID can remain unavailable under macOS privacy controls; do not infer a station from RSSI, channel, DHCP MAC or a dated inventory. Clean loopback does not rule out a Wi-Fi driver/radio fault. Satellite management replies are not backhaul-throughput measurements. These extra journal fields remain local unless explicitly exported; automatic peer sharing includes latest state/Wi-Fi, not close-up histories.

Use read-only `investigate status` (latest saved episode of each type) and `investigate history --limit 5` (raw bounded tool evidence). The ordinary query includes investigation summaries. Episodes are historical, not current health; compare host/time/interface, actual attempts and missed replies. Nominal one-second close-ups can slow on timeouts. Their median/p10/p95 summarize successful replies only. Load-comparison phases are before/during/after a networkQuality test, not idle/download/upload isolation or RRUL. Route-hop ICMP nonresponse is not forwarding-loss proof. `investigate capture` and `routes` are active low-traffic diagnostics; `lan --confirm-load` and `serve --confirm-listener` require the user's explicit approval for load/listening. Never add those flags merely to bypass the guard. See [INVESTIGATIONS.md](INVESTIGATIONS.md). Investigation reports export with dashboard snapshots but are not automatically peer-synchronized.
