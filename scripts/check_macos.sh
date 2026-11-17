#!/bin/sh
set -eu
cd "$(dirname "$0")/.."
monitor_test_dir="$(mktemp -d /tmp/network-monitor-tests.XXXXXX)"
trap 'rm -rf "$monitor_test_dir"' EXIT
xcrun swiftc -swift-version 5 -parse-as-library -module-cache-path "$monitor_test_dir/cache" macos/DashboardData.swift tests/DashboardDataTests.swift -o "$monitor_test_dir/tests"
"$monitor_test_dir/tests"
