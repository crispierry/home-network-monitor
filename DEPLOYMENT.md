# Deployment checklist

1. Run offline Python and native tests; build the dashboard and inspect synthetic healthy, failed and stale states.
2. Preserve private installed configuration, inventory and evidence. Never copy household settings into public source.
3. Verify the actual host and intended wired/wireless interface. Quit the dashboard, run `python3 manage.py install` for an upgrade, then `python3 scripts/build_macos.py --install`.
4. Open `~/Applications/Network Monitor.app`. Run `python3 scripts/verify_install.py --compact` and verify source hashes, signature, version, a running LaunchAgent, fresh samples and fresh supplemental diagnostics. Failed network checks are evidence, not automatically an installation failure.
5. Verify each observer independently. Do not claim the other observer is current based on this one's state. Confirm old dashboard bundles were retired; retain the separate service launcher.
6. Keep sharing disabled unless explicitly paired/enabled and tested end to end. Reboot/login behavior is provided by launchd; an actual reboot test is a separate approved action.

A source release and local deployment are separate deliverables. This project does not publish notarized prebuilt macOS binaries. Record private deployment evidence outside the repository.
