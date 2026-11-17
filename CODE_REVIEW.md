# Release review — 2.6.0

Review scope: incident semantics, configuration/install lifecycle, file and TLS boundaries, storage bounds, worker isolation, native evidence parsing, memory retention, UI readability and public-source privacy.

## Findings addressed

- **Upgrades:** preserve installed private settings and device inventory.
- **File handling:** replace predictable checkpoint temporary paths with private, unique files and atomic replacement.
- **Input validation:** bound configuration/state reads; reject nonfinite or deeply nested JSON; tolerate malformed journal names and oversized records.
- **Connections:** close the wrapped socket when TLS certificate pinning rejects a peer.
- **Native data handling:** validate state size and snapshot timestamps; prune cached speed/observation records even while monitoring is stopped.
- **Readability:** enlarge supporting labels and use appearance-aware status colors.
- **Public-source privacy:** remove household inventory from examples, documentation, and tests; keep earlier private history out of the public repository.

## Coverage and limits

Regression coverage includes simulated incident failures/recoveries, observation gaps, storage rotation/torn writes, optional collector failures, paused load guards, peer framing/authentication/replay rejection, local-settings preservation, bounded JSON, private atomic writes, native chart gaps and imported-data validation. Validation results and any deployment limitations are recorded in the release handoff. No disruption of the monitored network is required by the automated suite.

Architectural limits: each Mac must be logged in; clean public probes do not clear specific applications; gateway diagnostics are contextual; sharing requires separate explicit setup; no notarized binary release or independent penetration test is provided. The MIT source license does not relicense external diagnostic tools. No review can establish an absence of all vulnerabilities or memory leaks; bounded caches and regression/memory tests cover the implemented paths.

## Release validation

- 105 offline Python regression tests pass.
- Native evidence/reader tests pass, including gaps, torn records, chart reduction and snapshot validation.
- Apple Silicon macOS 14 target builds and passes local code-signature verification.
- Synthetic native UI review verified navigation, chart zoom, recent-range menus and expanded diagnostic disclosures in dark mode.
- Seven-day synthetic reader benchmark: 40,320 samples, zero malformed records, 49,889,280 bytes peak RSS (about 47.6 MiB), 86.2 seconds for cold load plus five refreshes on the review machine. This excludes the full GUI and is not a guarantee for all hardware.
- Public tracked-source scan found no original household inventory values. Release history must start from sanitized files; pre-release history remains private.

Light-mode colors are implemented with native appearance-aware values; this review did not change the user's system appearance. Actual reboot recovery and cross-Mac synchronization require separate [deployment tests](DEPLOYMENT.md); neither is implied by passing offline tests. This report records the 2.6.0 review, not a live health report for an installed network.


## 2.6.1 single-computer follow-up

The default configuration now omits the optional peer probe. Explicit peer settings survive upgrades. Single-observer regression coverage checks healthy operation, internet failure/recovery, local agent queries, invalid peer values, and preservation of an existing peer. Native tests verify that unconfigured peer/satellite lanes are hidden while configured failing paths remain visible.

Validation: 110 offline Python tests and the native data tests pass. The native app builds and passes local signature verification. An isolated single-computer fixture displayed 14/14 passing checks, no peer comparison controls, and only the four configured core timeline lanes. Existing live configurations were not switched to single-computer mode.

## 2.6.3 cross-observer integration review

Reviewed publication/cursor commits, mutual TLS push/pull, generation changes, cache rotation, native incremental reads, agent query semantics, freshness and ownership of monitoring controls.

Findings fixed:

- Cache rotation could remove a directory while a query or dashboard was reading it. Transfers now hold an exclusive cache lock. Queries use a shared lock; the dashboard keeps its previous complete snapshot during a transfer without blocking the UI.
- A process exit after compact journal append but before cursor commit could replay records. A pending-publication marker now triggers a rebuild from retained raw journals in a new generation. Queries also deduplicate observation timestamps before computing attempts and coverage.
- Replay protection covered sequence numbers within one generation but allowed a retired generation to replace the current one. Transfers now reject older publication times and the archived retired generation.
- Peer queries ignored the requested window for speeds, incidents and notes, omitted an open incident, and exposed different primary history keys from local queries. Peer results now provide windowed `incidents`, `speed_tests` and `coverage`, while retaining the previous aliases for compatibility.
- A missing/corrupt peer cache or unreadable sync status could prevent returning a useful local briefing. Peer failures are now isolated and explicitly reported.
- Local pause/error state could incorrectly mark a selected peer as stopped or unreadable. Status now follows the selected observer; peer resume guidance points to that Mac.
- Malformed local journal objects could crash publication. They are skipped before compact export, and outgoing records are validated before append. Device/note timestamps and peer slot symlinks have additional validation.
- The summary-worker installer always claimed sharing was disabled. It now reports the preserved enabled setting accurately.

Validation: 117 offline Python tests and native data tests pass. Added tests exercise real bidirectional TLS over socket pairs, reader/writer exclusion, interrupted cursor commits, generation replay, query windows, deduplication, malformed rows, independent pause states and native cache swaps. No network listener, speed test, router change or live-history deletion is needed for these tests. The native app builds and passes local code-signature verification.

Deployment note: upgrade the summary worker and dashboard together on both Macs so readers and writers share the cache-lock protocol. This review changes source/build artifacts; it does not install the release on the running Minis. The existing monitoring settings, pairing, schedules and evidence remain intact. Raw diagnostics still stay on their source Mac; compact queries do not offer every field available in local raw history. An interrupted-publication rebuild cannot recreate raw records already removed by retention; the prior peer generation remains archived.

## 2.7.0 incident visibility and observer selection

The unified view had retained the incident list but omitted the graphical path timeline. Overview and Incidents now expose a shared, zoomable internet-access timeline with per-observer counts. A visible selector switches all content between either Mini and both. The individual Incidents view also retains the detailed path timeline.

The interruption calculation intersects confirmed HTTPS failure episodes for the two independent destinations. Single-destination failures, isolated protocol failures, non-overlapping failures, unconfirmed samples and out-of-window recoveries do not qualify. Open recovery and observation-gap uncertainty are preserved. Counts describe retained per-observer episodes, not distinct household outages or continuous uptime. Raw incidents are unchanged and remain available for drill-down.

Visual switching verification exposed repeated full-history filtering inside the older path Canvas drawing loop. Bounds and spans are now captured once per render rather than rescanned for every drawn segment. Latency chart captions explicitly disclose peak-preserving reduction; zoom still shows original measurements.

Validation: 117 offline Python tests and native data tests pass, including new interruption timing and classification cases. The Apple Silicon app builds and passes local signature verification. Deployment preserves recorder settings, history, pairing and speed-test schedules; no bandwidth test or router change is part of this update.

## 2.7.1 wireless latency evidence

Close-up rounds now include local loopback plus configured satellite and peer ICMP checks. Raw points include round timestamps, worker dispatch delays and subprocess elapsed time. Before/after context retains dated Wi-Fi state, host metrics, interface counters and allowlisted power settings. The native path selector and evidence validation accept the bounded additional targets. These are diagnostic episodes; they do not change incident thresholds or imply an equipment diagnosis.

A locally compiled, signed CoreWLAN helper reads current interface metrics without scanning or changing settings. BSSID remains explicitly unavailable when macOS withholds it. The installer refuses helper/marker symlinks and replaces the executable atomically before restarting collection. The helper normally runs once per minute, with a 30-second minimum during slow router pings; it adds no launch job or listener. Latest-state agent queries report independent Wi-Fi freshness.

Investigation raw retention is capped at eight 4 MiB segments with a 30-day age ceiling; size may shorten that period. Latest summaries have a 1 MiB read limit. Automatic capture cooldown, primary 15-second cadence, original schedules and pairing are preserved. Raw close-up context stays on its source Mac unless explicitly exported.

Validation: 122 offline Python tests and native evidence tests pass. Added checks cover optional control targets, timing fields, failed Wi-Fi providers, stale/malformed Wi-Fi readings, safe power-output filtering, and dashboard target allowlisting. The helper and native dashboard compile and pass local code-signature verification. Foreground helper runs on the deployment Mac took roughly 14–16 ms elapsed in three measurements; this is not a CPU benchmark or guarantee for other hardware.
