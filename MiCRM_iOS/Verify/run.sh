#!/bin/bash
# Compiles the app's logic (everything except the @main App entry point) together
# with Verify/main.swift and runs the assertions. Works with Command Line Tools
# only — no Xcode or iOS SDK required.
set -euo pipefail
cd "$(dirname "$0")/.."
SOURCES=$(find MiCRM -name "*.swift" ! -name "MiCRMApp.swift")
swiftc -target arm64-apple-macos14.0 -o /tmp/micrm-verify $SOURCES Verify/contract.swift Verify/main.swift
/tmp/micrm-verify
