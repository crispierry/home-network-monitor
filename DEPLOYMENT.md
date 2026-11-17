# Deploy and verify

Use the [README](README.md#first-installation) for first-time setup and configuration. This checklist is for installing or upgrading a release on an actual monitoring Mac. A successful build does not establish that the background recorder is collecting evidence.

## Before installing

1. Confirm the Mac, intended user account, and wired/wireless interface. Use a stable Python interpreter path.
2. Preserve installed settings, device inventory, and evidence privately. Never copy household settings into the public checkout's tracked files.
3. Run the offline checks from the checkout:

```sh
sh scripts/check.sh
sh scripts/check_macos.sh
python3 scripts/build_macos.py
```

For a release, also inspect synthetic healthy, failed, and stale views using the [contributor workflow](CONTRIBUTING.md#check-the-interface).

## Install or upgrade

Quit the dashboard. For a first installation, supply your private configuration and device file as described in the README. For an upgrade:

```sh
python3 manage.py install
python3 scripts/build_macos.py --install
open "$HOME/Applications/Network Monitor.app"
```

An upgrade without `--config` or `--devices` preserves installed settings and inventory. Installing starts the recorder, including when it was previously paused. If an optional summary worker is installed, update it with `python3 scripts/install_sync.py` and verify its state separately; see [sharing setup](SYNC_SETUP.md).

## Verify each Mac independently

Run from the same release checkout:

```sh
python3 scripts/verify_install.py --compact
```

Check the output rather than relying on the app opening:

| Field | Expected result |
| --- | --- |
| `host`, `interface` | The intended Mac and network path |
| `dashboard_version`, `dashboard_build` | The release you installed |
| `service_running` | `true` |
| `sample_age_seconds` | Less than three recording intervals |
| `diagnostics_fresh` | `true` |
| `installed_files_match` | Every entry is `true` |
| `app_signature_valid`, `dashboard_signature_valid`, `dashboard_sources_match` | `true` |
| `devices`, `speed_hours`, `speed_minute` | The intended inventory and schedule |

The verifier returns a nonzero exit status when its installation/freshness checks fail. It does not require every network probe to pass: failures may be the evidence you are trying to capture. Compare `checks_passing`, `failed_checks`, and the actual network symptoms separately.

Open the dashboard and confirm that its version, recorder status, and sample time agree with the verifier. Check that previous dashboard bundles were moved to Trash. Keep the runtime's separate service launcher.

Do not report the second Mac as verified based on the first Mac's results. Run the checks on both. Sharing also needs its own bidirectional transfer/reconnection tests before it can be called operational.

## Record the result

Keep deployment evidence outside Git: release commit, app version/build, observer/interface, verification time, verifier output, schedule, and any unresolved failures. Do not publish raw household evidence.

LaunchAgents are configured to restart after user login. An actual reboot/login test is a separate action; passing offline tests or restarting a job does not verify reboot recovery. A public source release is also separate from a notarized binary release, which this project does not currently provide.
