# Optional sharing between two Minis

The project supplies a Whole home dashboard and an independent summary worker. No sharing account, Finder mount, macOS account password, cloud service, or router change is required. Cross-Mac transfer is **disabled by default** until explicitly paired and enabled.

**Compatibility limit:** this transport currently supports Macs whose LocalHostNames are `Mini-One` and `Mini-Two`, on `10.0.0.0/24` only. General host/subnet configuration is not implemented. Keep it disabled on other networks and use snapshot export/import instead.

## Prepare

First install and verify local monitoring on both Macs using the [README](README.md#first-installation). Confirm each Mac's identity with `scutil --get LocalHostName`; do not rename a machine just to bypass this transport's restriction.

Use the same stable Python interpreter as the recorder. From the matching release checkout on each Mac, install the optional summary worker:

```sh
python3 scripts/install_sync.py
```

For an upgrade, update the recorder and dashboard using [DEPLOYMENT.md](DEPLOYMENT.md), then rerun this summary-worker installer. Installing the worker alone does not pair or enable cross-Mac transfer.

The worker is a per-user LaunchAgent named `com.crispierry.network-monitor.sync`. It runs independently of the dashboard after the existing macOS user session starts. Headless means no attached display; it does not remove macOS login/FileVault requirements after reboot. This installer does not change automatic login, FileVault or account passwords.

## Exchange and pair public identities

On each Mac, run `python3 scripts/configure_sync.py identity`. This generates a private key locally and prints only its **public** certificate, host ID and SHA-256 fingerprint. Keys live in `~/Library/Application Support/NetworkMonitor/Sync/keys/`, with owner-only directory/file permissions (0700/0600). Private keys never leave their source Mac. Do not put keys, actual evidence or pairing bundles in Git or chat.

Transfer each public JSON bundle through the existing authenticated Screen Sharing/file-transfer connection. Verify the printed fingerprint on the source Mac. On the destination, run:

```sh
python3 scripts/configure_sync.py pair --bundle /private/tmp/peer-public.json --fingerprint VERIFIED_PUBLIC_SHA256
```

Pairing refuses an unexpected host, mismatched fingerprint or silently replacing a different paired certificate. It remains disabled after pairing.

## Enable sharing

Run `python3 scripts/configure_sync.py enable` on both Macs only after approval to enable the LAN listener. Mini-One listens on **TCP 19443**, bound only to its recorded `10.0.0.x` interface. Mini-Two initiates connections to `Mini-One.local` on that port. TLS 1.3 verifies certificates on **both** ends, with exact certificate pinning; a LAN IP or Bonjour name alone cannot authenticate a peer. No public/internet binding, HTTP interface, commands or remote monitoring controls are exposed. Only compact monitoring summaries are exchanged. The protocol has a fixed filename allowlist, message/byte limits and connection deadlines. The server accepts one transfer at a time.

The worker publishes and exchanges compact updates about every 10 seconds, with backoff after failures. This keeps peer observations within the recorder’s freshness window during normal operation. Connection failure does not stop either recorder. A disposable client process has a 25-second total deadline; accepted server connections have a 20-second deadline. A LAN address change causes the listener to rebind; the client resolves the peer name again each attempt. Existing macOS firewall or Local Network permission may require user authorization; never disable the firewall to make this work.

For a configured peer, the native app opens **Whole home** by default. Both expected observers remain visible before the first exchange and during disconnections. Separate cards show each observer's health and observation time; missing or stale evidence means current health is unknown. The sidebar distinguishes sharing configuration, disconnection, and stale observations. Synchronization freshness is separate from observation freshness. `network-monitor query --all-hosts --hours 24` reads the same validated local cache without networking. ChatGPT/Dots on either Mac can run it with local command access. Closing the dashboard leaves recording and synchronization running.

## Storage, deletion and recovery

Each source keeps its authoritative raw journals in `~/Library/Logs/NetworkMonitor/`. Compact exports live under `Sync/outbox/`, validated peer snapshots under `Sync/peer/`. Transfer uses manifest-declared journal prefixes with byte counts and SHA-256 checksums. Cached prefixes are reused and only new tail bytes cross the network; a fully validated generation is selected atomically. A failed, corrupt, incomplete or replayed transfer preserves the previous good cache. Retention gaps stay gaps.

Compact exports are limited to less than **16 MiB**, targeting seven days of samples and 180 days of speeds/notes. Byte caps can shorten retention. The peer cache, transfer staging and one prior recording generation are limited to less than **64 MiB** in aggregate. Raw journal budgets total 324 MiB plus state and bounded service errors; see the [retention table](README.md#storage-and-retention). The 512 MiB per-Mac design envelope includes operational reserve; user exports, source/build files, Trash and pre-existing checkpoint archives are outside it. The app reports measured local evidence and Sync allocation. This release does not create 30-day rollups; incident summaries retain the latest 20 incidents and raw diagnostic history remains on its source Mac.

**Stop monitoring** also stops/disables the local sync job. **Resume** restarts both. **Delete history** removes local active evidence and the outbound summary, rotates the recording generation and leaves monitoring stopped. It does not erase a historical copy already retained by the other Mini. **Clear peer cache** removes only the reconstructable local peer copy; enabled sync will refill it. Neither action silently removes source evidence on the other Mac.

To disable transfer alone: `python3 scripts/configure_sync.py disable`. The worker stops its listener/client on the next five-second tick, retaining caches and local summary publication. The recorder's normal uninstall removes both LaunchAgents while retaining evidence. Certificates are valid for ten years; a lost/expired key requires deliberate re-pairing through the trusted connection, not bypassing certificate checks.

## Verify sharing before relying on it

Automated tests exercise real TLS through local socket pairs (no LAN listener): mutual authentication, unpaired/missing certificate rejection, exact pinning, bounded framing, allowed paths/operations, intact publication and preservation after corruption. Pipeline tests cover duplicate/replayed records, stale samples, retention gaps and generation changes. Deployment must also verify bidirectional convergence, reconnection, GUI-closed operation and current resource use on both Macs before calling synchronization operational.

After enabling sharing on both Macs, check all of the following:

1. **Whole home** shows both observers with recent observation times.
2. `~/.local/bin/network-monitor query --all-hosts --hours 24` reports the same sources and freshness on each Mac.
3. Closing the dashboards does not stop collection or transfer.
4. After a naturally occurring interruption, transfer resumes and the original observation gaps remain visible.

Do not disrupt the network to force a test. If the other observer remains missing, inspect pairing, worker status, and permissions before interpreting its absence as a network outage. These are deployment checks, not claims that the automated suite verified your LAN.
