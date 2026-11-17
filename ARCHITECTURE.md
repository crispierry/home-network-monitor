# Architecture

The recorder is authoritative; the dashboard and optional synchronization worker are readers. Each observer writes its own evidence independently, so a network outage does not interrupt local persistence. There is no database server or cloud control plane.

`monitor.py` validates configuration, runs bounded probes in a limited thread pool, maintains the incident detector and writes rotating journals plus an atomic checkpoint. `devices.py` maintains a small explicit watch list. `diagnostics.py` and `host_metrics.py` collect supplemental context with independent timestamps and failure handling. `performance.py` serializes load tests and schedules them by observer slot. `investigation.py` runs bounded close-ups and optional command-line tools; its failure does not stop primary collection.

`analysis.py` and `agent_query.py` provide read-only summaries. `manage.py` installs and controls the per-user LaunchAgent while preserving installed private settings. The native dashboard separates evidence decoding/validation (`DashboardData.swift`), background loading and actions (`DashboardStore.swift`), views, and the AppKit entry point. File parsing runs off the main thread. Incremental journal offsets avoid repeated full-history reads; rotation removes old offsets. Explicit gaps prevent charts from implying continuous coverage.

`sync.py` produces compact summaries and validates peer generations. `peer_transport.py` implements an opt-in mutually authenticated TLS transport. Raw logs stay on their source observer. Sharing is not needed for local recording, and a failed transfer preserves the last good cache. Peer capture age is distinct from transfer age. The current transport is restricted to its documented two-observer profile; general discovery and automatic pairing are not implemented.

## Bounds and failure isolation

Primary sample segments: 32 × 8 MiB. Events: 16 × 1 MiB. Speeds: 8 × 1 MiB. Observations: 4 × 1 MiB. Diagnostics: 16 × 2 MiB. Investigations: 4 × 2 MiB. Retention ages can shorten those size ceilings. Journals use writer locks, flush/fsync, bounded records and torn-tail recovery. Checkpoint writes use unique owner-only temporary files followed by atomic replacement. Configuration, cache and imported evidence have size/shape limits.

The dashboard retains seven days of compact samples and 180 days of speed/observation records, pruning even when monitoring stops. UI refresh is five seconds and slows while hidden. Import size and record-count limits bound accidental memory use. Summary transfer has byte/count limits and deadlines. Backups and user exports are intentional separate files, not subject to automatic deletion.

The recorder is not a privileged daemon. It runs with the logged-in user's permissions. Reboot without login, sleep, full disks and missing system tools can create observation gaps. A journal/checkpoint pair is not a transactional database: sudden failure can leave a journal record newer than the checkpoint. Gaps and restart evidence must be considered when interpreting incident boundaries. No automatic router reset or network reconfiguration is performed.
