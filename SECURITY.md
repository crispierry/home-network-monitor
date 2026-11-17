# Security

Report vulnerabilities through [GitHub private vulnerability reporting](https://github.com/crispierry/home-network-monitor/security/advisories/new). If that feature is unavailable, contact the maintainer privately. Do not attach household logs, keys or credentials to a public issue. Include affected version, reproduction with synthetic data, impact and suggested mitigation.

## Trust boundary

The normal installation is local-only and opens no network listener. It sends diagnostic requests to configured LAN devices and independent public endpoints. HTTPS certificate validation remains enabled. Router passwords are never collected. Private runtime/evidence directories and files use owner-only permissions. The application runs as the user without sudo, router control or a hosted dashboard.

Configuration, snapshots and peer payloads are treated as data, not code. External commands use argument lists, bounded deadlines and validated targets. Peer synchronization is disabled by default; its optional listener requires explicit setup, TLS 1.3 mutual authentication, pinned certificates, allowed operations/filenames, byte limits and timeouts. It has no remote command or monitoring-control endpoint. Do not expose it through a router port forward.

A manually authorized iperf3 receiver is different: it is unauthenticated, binds one private LAN address, accepts one client and expires within 60 seconds. Other LAN clients can reach it while active. It is never started automatically. External diagnostic packages are installed separately and retain their own security/update lifecycle.

## Private data

Device names, MAC/IP addresses, manual room/attachment labels, diagnostic routes, observations and exported snapshots are private operational data. Keep them outside Git and review exports before sharing. `config.local.json`, `devices.local.json`, logs, captures, key files and `local-data/` are ignored. Ignore rules do not scrub files already committed or historical commits.

The design assumes the current macOS account and installed runtime are trusted. It does not defend against malware with the same user's file access, a compromised OS, a malicious paired observer, or hostile replacement of system tools. Local symlink checks reduce accidental unsafe writes but are not a complete same-user race defense. Gateway HTTP status is unauthenticated contextual evidence, not trusted proof. A reachable address may belong to a different device after DHCP reassignment.

This release received a code review and automated regression checks, not an independent penetration test or formal security certification. Source builds are locally signed; notarized binary distribution is not provided. Keep macOS, Python and separately installed tools updated. Certificate/key rotation requires deliberate re-pairing; never bypass verification to restore sharing.
