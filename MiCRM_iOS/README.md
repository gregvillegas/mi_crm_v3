# MiCRM for iOS

SwiftUI client for the MI CRM API, at feature parity with the Android app.

## Building

There is no `.xcodeproj` in the repo — it is generated, so the source tree stays
the single source of truth and project files never conflict in review.

```bash
brew install xcodegen      # once
cd MiCRM_iOS
xcodegen generate          # writes MiCRM.xcodeproj
open MiCRM.xcodeproj
```

Set your team ID in `project.yml` (`DEVELOPMENT_TEAM`) before archiving.
Deployment target is iOS 17 — the app uses the Observation framework
(`@Observable`) and `NavigationStack`.

## Verifying without Xcode

`Verify/run.sh` compiles every source file except the `@main` entry point
against the **macOS** SDK and runs assertions over the app's pure logic. It
needs only Command Line Tools, so it works on a machine with no Xcode and no
iOS simulator:

```bash
./Verify/run.sh
```

It checks server-address normalisation, currency and date formatting, status
mapping — and then decodes real API responses (see below).

### Contract fixtures

The most useful part. Dump live responses from the Django test suite, then
decode them with the app's own `Codable` models:

```bash
cd ..                      # repo root
MICRM_DUMP_CONTRACT=1 python manage.py test crm_project.tests_api.ContractFixtureTests
cd MiCRM_iOS && ./Verify/run.sh
```

If a DRF serializer changes shape, this fails at build time instead of at
runtime on a salesperson's phone. Worth running whenever
`crm_project/serializers.py` changes.

A few SwiftUI modifiers are UIKit-only (`keyboardType`,
`navigationBarTitleDisplayMode`, …). They are wrapped in
`DesignSystem/Platform.swift` so feature code stays free of `#if os(...)` and
the whole app remains type-checkable on macOS.

## Layout

```
MiCRM/
  App/            entry point, Session (auth state machine)
  Core/           APIClient, Codable models, keychain, formatters
  DesignSystem/   palette, type scale, shared components
  Features/       one folder per tab / flow
```

`Session` is the only place that knows whether someone is signed in. It holds a
four-state machine — `loading → signedOut → awaitingCode → signedIn` — because
MFA makes sign-in two-legged.

## Design notes

The accent system is Micro Image's own vocabulary: the CRM names its pipeline
stages Pink, Yellow, Green and Blue Funnel, so those four colours identify a
deal's stage everywhere it appears. Brand red (`#A11313`) is reserved for
identity and primary actions, so colour always carries meaning — stage colour
says where the money is, red says act.

The home screen's one bold element is the pipeline rail: the whole funnel as a
single bar segmented by peso value. Everything around it is deliberately quiet —
flat rows with hairline separators rather than a card per item — and elevation
is reserved for things that want a decision, so a raised surface always means
"this needs you".

Figures use monospaced digits throughout. This app is mostly numbers stacked
vertically, and aligned digits are materially easier to scan in a column.

## Security

The API token lives in the keychain (`kSecAttrAccessibleAfterFirstUnlockThisDeviceOnly`
— not synced, not restored onto new hardware), never in `UserDefaults`. Only the
server address is stored in defaults.

Sign-in is two-legged when the account has an authenticator enrolled: the
password step returns a short-lived signed challenge, and only the TOTP (or
recovery code) step returns an API token. The interim challenge authenticates
nothing on its own.

`NSAllowsLocalNetworking` is enabled because the on-premise server runs plain
HTTP on the office LAN. Traffic to `micrm.microimageph.com` still requires TLS —
arbitrary cleartext loads are *not* permitted.
