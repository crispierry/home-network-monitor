# Release review — 2.6.0

Review scope: incident semantics, configuration/install lifecycle, file and TLS boundaries, storage bounds, worker isolation, native evidence parsing, memory retention, UI readability and public-source privacy.

Fixed findings include private installed settings being overwritten by upgrades; predictable checkpoint temporary paths; an unclosed wrapped socket after TLS pin rejection; unbounded configuration/state reads; malformed journal names and oversized lines interrupting evidence processing; nonfinite/deeply nested JSON acceptance; native state-file size checks and snapshot timestamp limits; cached speed/observation retention while stopped; unreadably small supporting labels; static colors with poor dark-mode readability; and household inventory in public-facing examples/docs/tests.

Regression coverage includes simulated incident failures/recoveries, observation gaps, storage rotation/torn writes, optional collector failures, paused load guards, peer framing/authentication/replay rejection, local-settings preservation, bounded JSON, private atomic writes, native chart gaps and imported-data validation. Validation results and any deployment limitations are recorded in the release handoff. No disruption of the monitored network is required by the automated suite.

Architectural limits: each Mac must be logged in; clean public probes do not clear specific applications; gateway diagnostics are contextual; sharing requires separate explicit setup; no notarized binary release or independent penetration test is provided. The MIT source license does not relicense external diagnostic tools. No review can establish an absence of all vulnerabilities or memory leaks; bounded caches and regression/memory tests cover the implemented paths.

## Release validation

- 105 offline Python regression tests pass.
- Native evidence/reader tests pass, including gaps, torn records, chart reduction and snapshot validation.
- Apple Silicon macOS 14 target builds and passes local code-signature verification.
- Synthetic native UI review verified navigation, chart zoom, recent-range menus and expanded diagnostic disclosures in dark mode.
- Seven-day synthetic reader benchmark: 40,320 samples, zero malformed records, 49,889,280 bytes peak RSS (about 47.6 MiB), 86.2 seconds for cold load plus five refreshes on the review machine. This excludes the full GUI and is not a guarantee for all hardware.
- Public tracked-source scan found no original household inventory values. Release history must start from sanitized files; pre-release history remains private.

Light-mode colors are implemented with native appearance-aware values; this review did not change the user's system appearance. Actual reboot recovery and cross-Mac synchronization require separate deployment tests; neither is implied by passing offline tests.
