# Comparative scope

Network Monitor is a small local recorder for evidence during intermittent outages. It borrows established diagnostic approaches, with attribution in ACKNOWLEDGMENTS.md, rather than trying to replace enterprise monitoring suites.

SmokePing motivates latency distributions, loss denominators and multiple observers. iperf3 supplies a separately installed controlled LAN test. MTR supplies an optional repeated-route engine, with macOS traceroute fallback. Flent motivates measuring latency alongside deliberate load; our before/during/after networkQuality observations are not RRUL or a bufferbloat score.

The product focuses on fresh local evidence, readable incident timelines, bounded retention and local agent access. It does not measure every room, diagnose encrypted application traffic, collect Zoom media statistics, infer current satellite association from historical inventory or guarantee remote camera availability. Those limits should remain visible where a user might otherwise overinterpret a result.
