# Diagnostic approach and references

[SmokePing](https://oss.oetiker.ch/smokeping/doc/reading.en.html) informs latency distributions and loss interpretation. [iperf3](https://software.es.net/iperf/invoking.html) provides controlled throughput between observers. [MTR](https://github.com/traviscross/mtr) offers repeated route measurements. [Flent](https://flent.org/intro.html) motivates simultaneous latency and traffic observations. No source or binaries from those projects are bundled. See [ACKNOWLEDGMENTS.md](ACKNOWLEDGMENTS.md) for license references.

[TMOG](https://tmog.org/) informed the value of host-context evidence; its implementation is not copied or included as a dependency. The recorder collects passive observer CPU/memory/interface context with standard macOS facilities. These readings cannot clear another meeting computer.

The diagnostic sequence is: preserve timestamped symptoms, compare fresh wired/wireless evidence, distinguish router/gateway/public endpoint and DNS/HTTPS failures, inspect bounded close-ups and route context, then run an explicitly authorized controlled LAN/load experiment if needed. Correlation supports hypotheses; it does not prove router hardware failure. High-resolution collection begins after its trigger and cannot recover preceding packets.
