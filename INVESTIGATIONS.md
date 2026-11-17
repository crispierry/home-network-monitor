# Connection investigations — version 2.6.0

Open **Performance → Connection investigation**. The panel names the observing Mini. Reports describe saved episodes, not current health. Whole home's panel uses this Mac's local report; choose an imported snapshot to inspect exported reports from the other Mini. Automatic sharing of investigation reports is not implemented.

## Catch a short stall

**Capture 1 minute** sends small pings to the main Orbi, Cloudflare and Google in nominal one-second rounds for 60 seconds. Each target has a one-second reply timeout; process scheduling and timeouts can reduce actual cadence. There is no catch-up burst. The chart preserves timestamps, shows replies as points and misses as dashed amber lines. It does not connect across missing evidence or turn missing latency into zero.

Choose a path and enable **15-second detail**. Move the Earlier/Later slider and click or drag on the plot to inspect individual replies. The statistics beneath the chart always cover the full episode: attempted/missed probes, median, and 10th–95th percentile. Small sample counts and filtered ICMP limit conclusions.

The recorder automatically requests a close-up after a newly failing primary check, or a new successful Orbi ping above 30 ms / public ping above 150 ms. These thresholds trigger investigation, not incident diagnoses. At most one automatic capture starts per five minutes; an ongoing investigation takes precedence and requests are not queued. A report cannot reconstruct the time before its trigger. Continuous 15-second, multi-protocol recording remains independent.

## Latency during the hourly speed tests

An available diagnostic worker captures a five-second before period, about one ping round per second during the already scheduled internet test, and five seconds afterward. Reports separate target, phase and interface. The :15 / :45 speed schedule remains unchanged. These small probes add no separate bandwidth test.

The before period is not guaranteed idle: other devices may be busy. The during period combines networkQuality's download and upload work. The phase label is taken when a probe round begins, so a reply can arrive after a phase boundary. Interface changes make the report incomplete. This is inspired by Flent's simultaneous latency/load methodology; it is not RRUL, Zoom jitter, or a causal bufferbloat score. An unavailable/busy diagnostic worker does not prevent the scheduled speed test; its absence is noted in the speed record.

## Inspect routes

**Inspect routes** saves repeated route evidence toward Cloudflare and Google, with a hard duration bound. If MTR is available in a standard Homebrew location, it runs ten report cycles per destination, without reverse DNS, with a 16-hop limit and 25-second deadline per target. No privileges are granted or changed. A permissions error is retained as an incomplete result.

Without MTR, the app uses macOS traceroute: three sequential passes per destination, six hops, one query per hop and a nine-second deadline per pass (54 seconds maximum plus small overhead). The panel summarizes replies and addresses per observed hop. The hop limit may end before the destination. **Missing or slow replies at an intermediate hop do not prove it is dropping forwarded traffic.** Correlate with destination HTTPS/TCP/DNS evidence. Full bounded output, tool version where available, arguments and timestamps remain in raw history.

## Controlled test between the Minis

This is a manual experiment, not a scheduled feature. Use it outside meetings and outside :14–:20 and :44–:50 Pacific, which are reserved for internet speed tests. It may temporarily slow the LAN and transfer substantial data. The test measures these two paths, not every room or AT&T capacity.

Install the official Homebrew `iperf3` package on both Minis if needed:

```sh
brew install iperf3
```

The wrapper uses stable iperf3 options documented in its manual; unsupported options or malformed output produce an incomplete result. No third-party binary is embedded in this repository or app bundle.

1. Verify Mini-One is using its direct Ethernet connection to the main Orbi. Read its current address locally with `ipconfig getifaddr en0`; check the interface in Network Monitor. Do not assume a historical DHCP address is still correct.
2. On Mini-One, start a receiver, replacing `MINI_ONE_LAN_IP` with that numeric private IPv4 address:

```sh
~/.local/bin/network-monitor investigate serve --bind MINI_ONE_LAN_IP --confirm-listener
```

The receiver is foreground, bound to that address on TCP port 5201, accepts at most one client, and exits within 60 seconds. Client duration is capped at 20 seconds. It is unauthenticated: another LAN device could connect during that window. Do not forward the port or leave a separate iperf server running. Starting this command explicitly authorizes the temporary listener; agents must obtain the user's approval before doing so.

3. Within that minute, on Mini-Two, run a 15-second send test:

```sh
~/.local/bin/network-monitor investigate lan --peer MINI_ONE_LAN_IP --direction send --confirm-load
```

4. Allow the network to settle, start a new receiver on Mini-One, then run the reverse test from Mini-Two:

```sh
~/.local/bin/network-monitor investigate lan --peer MINI_ONE_LAN_IP --direction receive --confirm-load
```

The client captures before/during/after ping evidence, saves receiver throughput and sender TCP retransmissions where present, and retains raw JSON. The receiver saves its own bounded result. LAN and scheduled speed tests share a local lock. The receiver's load tag covers the waiting period too, so it is a conservative session flag rather than exact traffic timing.

Compare directions and repeat under comparable conditions. Poor local throughput while wired internet remains healthy supports investigating Wi-Fi/local load; good local throughput during shared public-endpoint failures supports investigating the shared uplink. Neither proves an Orbi hardware defect. A hostname/IP does not identify the satellite association; verify that separately in Orbi.

## Agents, raw evidence and retention

These commands are read-only and never run a test:

```sh
~/.local/bin/network-monitor investigate status
~/.local/bin/network-monitor investigate history --limit 5
~/.local/bin/network-monitor query --hours 24
```

The versioned JSON schema is `network-monitor.investigation.v1`. Status and the ordinary query include the latest saved report of each of four types. History includes raw tool output. Names, local IPs and route hops are private operational evidence; do not commit them to Git or publish them automatically.

Raw reports are `~/Library/Logs/NetworkMonitor/investigations-*.jsonl`, limited to four 2 MiB segments (8 MiB) with a 30-day age ceiling. Size can shorten retention. `investigation-latest.json` is a bounded summary cache (reader limit 512 KiB), excluding raw external-tool output. The dashboard export includes these recent summaries and close-up points; it does not export the full raw journal. Reports are not included in automatic peer synchronization in this version.

There is at most one investigation per Mac, at most three concurrent ping workers, and no new always-on probe stream or listener. An active capture briefly creates ping subprocesses; idle overhead is a small scheduling check and bounded report reads. Actual CPU/RAM depends on the Mac and is visible under Monitoring & storage. Stop monitoring cancels close-ups/route/iperf work through the pause marker; bounded subprocess deadlines also limit work. Delete history includes investigation journals/cache after work stops. No router credentials are used.

Design credits and upstream license references are in [ACKNOWLEDGMENTS.md](ACKNOWLEDGMENTS.md).
