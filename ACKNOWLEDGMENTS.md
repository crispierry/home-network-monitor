# Open-source acknowledgments

Network Monitor benefits from the work and published methods of these projects. These acknowledgments distinguish independent implementation of ideas from distribution of third-party software. No SmokePing, iperf3, MTR or Flent source code or binaries are bundled in this release. Their names do not imply endorsement.

| Project and contributors | Contribution to our approach | Upstream license/source |
| --- | --- | --- |
| SmokePing — Tobias Oetiker, Niko Tyni and contributors | Latency distributions, loss denominators, observer comparison and bounded close-ups. This is not a continuous SmokePing deployment. | [Project and GPL-2.0 license](https://github.com/oetiker/SmokePing); [graph methodology](https://oss.oetiker.ch/smokeping/doc/reading.en.html). |
| iperf3 — ESnet / Lawrence Berkeley National Laboratory and contributors | Controlled LAN throughput tests with machine-readable results through the external executable; installed separately. | [Project](https://software.es.net/iperf/); [license and third-party notices](https://github.com/esnet/iperf/blob/master/LICENSE), primarily BSD-3-Clause with additional component notices. |
| MTR — Matt Kimball, Roger Wolff and contributors, maintained in traviscross/mtr | Optional external engine for repeated route reports. The default native traceroute fallback does not use MTR. | [Project](https://github.com/traviscross/mtr); [GPL-2.0 license](https://github.com/traviscross/mtr/blob/master/COPYING). |
| Flent — Toke Høiland-Jørgensen and contributors | Controlled comparison of latency and throughput under load, and preservation of test results. Our speed-test tags and before/during/after captures are not RRUL. | [Project](https://flent.org/intro.html); [GPL-3.0 license](https://github.com/tohojo/flent/blob/main/LICENSE). |
| curl — Daniel Stenberg and contributors | The macOS-provided curl executable performs HTTPS probes and supplies cumulative transfer timings. No curl binary or source is distributed here. | [Project](https://curl.se/); [copyright/license](https://curl.se/docs/copyright.html); [timing documentation](https://curl.se/docs/manpage.html#-w). |

For a future integration, pin the actual tool version, keep its provenance and full applicable license/notices, and review redistribution requirements before bundling code or binaries. A credit line is not a substitute for satisfying the selected version's license. External diagnostic results should include tool version, command parameters, observer/interface, timestamps and test limitations, with secrets omitted.

TMOG also informed our passive host-context design. We have not verified an open-source license for TMOG, copied its implementation, or included it as a dependency. See [diagnostic research](DIAGNOSTIC_RESEARCH.md) for the diagnostic rationale.

## How the integrations work

`investigation.py` and native investigation views independently implement bounded repeated-ping distributions inspired by SmokePing and before/during/after latency observations inspired by Flent. They are not ports of either project's source and are not equivalent to SmokePing's continuous deployment or Flent RRUL. MTR is an optional external executable; the default fallback uses macOS traceroute. iperf3 is installed separately and invoked for explicitly requested LAN tests. The repository/app bundle still contains none of those projects' binaries or source. Upstream license notices remain with the separately installed packages. [iperf3 manual](https://software.es.net/iperf/invoking.html), [MTR manual](https://github.com/traviscross/mtr/blob/master/man/mtr.8.in).
