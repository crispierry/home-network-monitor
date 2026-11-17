# Architecture

The recorder is authoritative; the dashboard and optional synchronization worker are readers. Each observer writes its own evidence independently, so a network outage does not interrupt local persistence. There is no database server or cloud control plane.

## Components and data flow

| Component | Responsibility |
| --- | --- |
| `monitor.py` | Validate configuration, run probes in a limited thread pool, detect incidents, and write journals/checkpoints |
| `devices.py` | Track a small, explicitly configured device list |
| `diagnostics.py`, `host_metrics.py` | Collect supplemental context with separate timestamps and failure handling |
| `performance.py` | Schedule and serialize load tests by observer slot |
| `investigation.py` | Run bounded close-ups and optional command-line tools without stopping primary collection on failure |
| `analysis.py`, `agent_query.py` | Produce read-only summaries of saved evidence |
| `manage.py` | Install/control per-user jobs while preserving private settings |
| `macos/DashboardData.swift` | Decode and validate evidence |
| `macos/DashboardStore.swift` | Load data in the background and handle user actions |
| `macos/DashboardView.swift`, `macos/NetworkMonitorApp.swift` | Present the native interface and start the application |
| `sync.py`, `peer_transport.py` | Produce/validate compact summaries and optionally transfer them using mutually authenticated TLS |

The recorder writes locally even when network checks fail. The dashboard loads files off the main thread; incremental offsets avoid rereading the full journal on every refresh. Rotation removes old offsets, and explicit gaps prevent charts from implying continuous coverage.

Publishing uses a private pending marker before appending compact records. If a process exits before committing its cursor, the next publication rebuilds compact summaries from retained raw journals in a new recording generation. The peer preserves its previous generation separately. This avoids counting replayed appends twice; a rebuild cannot recover raw history that retention has already removed.

Raw logs remain on their source observer. Optional sharing transfers compact summaries; a failed transfer preserves the last valid cache. The time the peer observed a result is distinct from the time that result arrived. Cache swaps hold an exclusive file lock; native readers use a nonblocking shared lock and keep the last complete snapshot during a transfer. Agent queries hold a shared lock while reading the selected cache generation. A corrupt or unavailable peer cache does not prevent returning local evidence. The transport supports only the [documented two-observer profile](SYNC_SETUP.md); general discovery and automatic pairing are not implemented.

## Bounds and failure isolation

| Journal | Segment budget |
| --- | --- |
| Primary samples | 32 × 8 MiB |
| Events | 16 × 1 MiB |
| Speed tests | 8 × 1 MiB |
| Human observations | 4 × 1 MiB |
| Diagnostics | 16 × 2 MiB |
| Investigations | 8 × 4 MiB |

[Age limits](README.md#storage-and-retention) can shorten these size ceilings. Journals use writer locks, flush/fsync, bounded records and torn-tail recovery. Checkpoint writes use unique owner-only temporary files followed by atomic replacement. Configuration, cache and imported evidence have size/shape limits.

The dashboard retains seven days of compact samples and 180 days of speed/observation records, pruning even when monitoring stops. UI refresh is five seconds and slows while hidden. Import size and record-count limits bound accidental memory use. Summary transfer has byte/count limits and deadlines. Backups and user exports are intentional separate files, not subject to automatic deletion.

The recorder is not a privileged daemon. It runs with the logged-in user's permissions. Reboot without login, sleep, full disks and missing system tools can create observation gaps. A journal/checkpoint pair is not a transactional database: sudden failure can leave a journal record newer than the checkpoint. Gaps and restart evidence must be considered when interpreting incident boundaries. No automatic router reset or network reconfiguration is performed.
