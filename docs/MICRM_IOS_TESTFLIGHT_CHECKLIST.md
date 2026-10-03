# MiCRM iOS — TestFlight Distribution & Signing Checklist

**Goal:** share the MiCRM iOS app with colleagues so they install it **without Developer Mode** and without a cable — via Apple **TestFlight**.

**Who this is for:** the person who holds (or will hold) the Apple Developer Program account and does the Xcode Archive + upload.

**App facts (from `MiCRM_iOS/project.yml`):**

| Setting | Value |
|---|---|
| Bundle ID | `com.microimage.crm` |
| Display name | `MiCRM` |
| Current marketing version | `1.0` (`MARKETING_VERSION`) |
| Current build number | `1` (`CURRENT_PROJECT_VERSION`) |
| Deployment target | iOS 17.0 |
| Project generator | **XcodeGen** (`.xcodeproj` is generated, not committed) |
| `DEVELOPMENT_TEAM` | **empty — must be set (Step 2)** |

> ⚠️ **Bundle ID note:** `com.microimage.crm` is also the Android `applicationId`. That is fine — iOS and Android are separate namespaces. But the iOS bundle ID must be **unique within Apple**. If someone has already registered `com.microimage.crm` on another Apple account, you'll need a different ID (e.g. `com.microimage.crm.ios`). See Step 3.

---

## Why TestFlight (and why not just host an .ipa)

Unlike Android — where we host the signed `.apk` on the file server and anyone sideloads it — **iOS has no equivalent for a normal developer account.** Apple requires every install to go through its signing/distribution system. With the **paid Apple Developer Program ($99/year)**, **TestFlight** is the sanctioned "install without Developer Mode" path:

- Testers install Apple's **TestFlight** app, tap your invite link, and install MiCRM. No cable, no Xcode, no Developer Mode.
- **Internal testers:** up to 100 people who are members of your App Store Connect team. Builds are available almost immediately (no Apple review for internal testing).
- **External testers:** up to 10,000 via email or a public link; the **first** build for external testing needs a quick Beta App Review (usually a day).
- Builds expire **90 days** after upload (vs. the 7-day expiry of a free personal-team build).

The free personal team you used to run it on your own phone **cannot** do this (7-day expiry, Developer-Mode-only, no sharing). The $99/year program is the unlock.

---

## Phase 0 — Prerequisites (one-time)

- [ ] **Apple Developer Program membership** is approved for the account that will distribute (`$99/year`). Enroll at <https://developer.apple.com/programme/>. Approval can take hours to a few days; a company enrollment may ask for a D-U-N-S number.
- [ ] A Mac with **full Xcode** installed (not just Command Line Tools). Confirm with:
  ```bash
  xcode-select -p        # should print /Applications/Xcode.app/Contents/Developer
  ```
  If it prints `/Library/Developer/CommandLineTools`, point it at Xcode:
  ```bash
  sudo xcode-select -s /Applications/Xcode.app/Contents/Developer
  ```
- [ ] **XcodeGen** installed: `brew install xcodegen`.
- [ ] You can sign in to **App Store Connect** (<https://appstoreconnect.apple.com>) with the developer account.

---

## Phase 1 — Signing config in the project

The project ships with `DEVELOPMENT_TEAM: ""`. Set your **Team ID** so Xcode can sign.

- [ ] **Find your Team ID.** App Store Connect / developer.apple.com → **Membership** → "Team ID" (a 10-character string like `AB12CD34EF`).
- [ ] **Set it in `MiCRM_iOS/project.yml`.** Edit the `settings.base` block:
  ```yaml
  settings:
    base:
      SWIFT_VERSION: "5.9"
      DEVELOPMENT_TEAM: "AB12CD34EF"   # <-- your 10-char Team ID
      CODE_SIGN_STYLE: Automatic
      MARKETING_VERSION: "1.0"
      CURRENT_PROJECT_VERSION: "1"
  ```
  (Ask the dev team to make this edit, or do it yourself — it's one line.)
- [ ] **Regenerate the project** so the change takes effect:
  ```bash
  cd MiCRM_iOS
  xcodegen generate
  open MiCRM.xcodeproj
  ```
- [ ] In Xcode: select the **MiCRM** target → **Signing & Capabilities** → verify
  - **Automatically manage signing** is ON,
  - **Team** shows your team,
  - **Bundle Identifier** = `com.microimage.crm` (or your chosen unique ID),
  - no red signing errors.

> `CODE_SIGN_STYLE: Automatic` lets Xcode create and manage the signing certificate and provisioning profile for you — the simplest path. Manual signing is not needed for TestFlight.

---

## Phase 2 — Register the App ID & create the app record

- [ ] **App ID (identifier):** developer.apple.com → **Certificates, Identifiers & Profiles** → **Identifiers** → register `com.microimage.crm` if it isn't already. (With automatic signing, Xcode often registers it for you on first archive.)
- [ ] **App record in App Store Connect:** <https://appstoreconnect.apple.com> → **My Apps** → **+** → **New App**:
  - Platform: **iOS**
  - Name: **MiCRM** (must be unique across the App Store; if taken, use e.g. "MiCRM — Micro Image")
  - Primary language, Bundle ID (`com.microimage.crm`), SKU (any internal string, e.g. `micrm-ios`)
  - User access: Full or limited — your choice.

---

## Phase 3 — Pre-upload hygiene

- [ ] **Bump the build number for every upload.** App Store Connect rejects a re-used build number. For the first upload `1` is fine; for the next, raise `CURRENT_PROJECT_VERSION` (and `MARKETING_VERSION` when it's a user-facing new version) in `project.yml`, then `xcodegen generate` again.
  ```yaml
  MARKETING_VERSION: "1.0"          # user-facing version, bump for releases
  CURRENT_PROJECT_VERSION: "2"       # build number, bump EVERY upload
  ```
- [ ] **App icon present** — already done: `MiCRM/Resources/Assets.xcassets/AppIcon.appiconset/AppIcon.png` (1024×1024, no alpha). TestFlight/App Store require a 1024 icon with no transparency. ✓
- [ ] **Encryption declaration** — already set in `project.yml`: `ITSAppUsesNonExemptEncryption: false`. This avoids the export-compliance prompt on every build. (The app only uses standard HTTPS/TLS, which is exempt.) ✓
- [ ] **Server reachability:** TestFlight testers are off the office LAN, so they must reach the **public** server `https://micrm.microimageph.com` (the app's `NSAllowsLocalNetworking` only helps on the LAN). Make sure testers either use the public host or are on the office network/VPN.
- [ ] Pick the **Release** configuration for the archive (Xcode archives Release by default).

---

## Phase 4 — Archive & upload from Xcode

- [ ] In Xcode, set the run destination to **Any iOS Device (arm64)** — *not* a simulator. (Archive is disabled when a simulator is selected.)
- [ ] **Product → Archive.** Wait for the build; the **Organizer** window opens with your archive.
- [ ] In Organizer, select the archive → **Distribute App** → **App Store Connect** → **Upload**.
  - Let Xcode manage signing / "Automatically manage signing".
  - Accept the defaults (symbols included, etc.) and upload.
- [ ] Wait for **"Upload Successful."** Processing in App Store Connect then takes a few minutes to ~1 hour (you'll get an email when the build is ready, or it may show "Processing" then clear).

> No full Xcode / Mac with Xcode? There is no supported way to archive and upload an iOS app without Xcode (or Xcode Cloud / a CI mac). The `Verify/run.sh` script in the repo only *type-checks* logic on macOS — it cannot produce a shippable build.

---

## Phase 5 — Set up TestFlight testers

In App Store Connect → **My Apps → MiCRM → TestFlight**:

**Internal testing (fastest, up to 100 people, no Apple review):**
- [ ] Add colleagues as **Users** (App Store Connect → **Users and Access**) with at least the **App Manager** or **Developer** (or **Customer Support/Marketing**) role, or add them specifically as **internal testers**. They must have an Apple ID.
- [ ] Under **TestFlight → Internal Testing**, create a group, add those users, and attach the processed build.
- [ ] They get an email + a link; they install **TestFlight** from the App Store, then install MiCRM from within it.

**External testing (if you need people who aren't on your team):**
- [ ] Create an **External** group, add the build, fill **Test Information** (what to test, a contact email).
- [ ] First external build goes through a short **Beta App Review** (usually within a day).
- [ ] Share the **public link** or invite by email (up to 10,000 testers).

- [ ] Provide testers brief instructions (see Appendix A).

---

## Phase 6 — Updating the app later

Every time you ship a change:
1. [ ] Edit code.
2. [ ] Bump `CURRENT_PROJECT_VERSION` (build number) — and `MARKETING_VERSION` for a user-facing version change — in `project.yml`.
3. [ ] `xcodegen generate`.
4. [ ] Archive → Distribute → upload.
5. [ ] Add the new build to the tester group. Testers get an update notification in TestFlight.

Builds auto-expire 90 days after upload; just upload a fresh one before then.

---

## Troubleshooting

| Symptom | Likely cause / fix |
|---|---|
| "No account for team" / signing errors in Xcode | Set `DEVELOPMENT_TEAM` (Phase 1), re-run `xcodegen generate`, sign in to the account in Xcode → Settings → Accounts. |
| Archive menu greyed out | Destination is a Simulator — switch to **Any iOS Device (arm64)**. |
| Upload rejected: "redundant binary / build already exists" | Build number re-used — bump `CURRENT_PROJECT_VERSION` and regenerate. |
| "Invalid bundle — app icon missing / has alpha" | Must be 1024×1024 **no transparency**. Ours is correct; if you regenerate the icon keep it opaque. |
| Build stuck "Processing" for hours | Occasionally slow on Apple's side; usually clears. A missing-compliance/ITSAppUsesNonExemptEncryption issue can also hold it — ours is pre-declared `false`. |
| Testers can't log in | They're off-LAN hitting the on-prem host. Use the public `micrm.microimageph.com` or put them on the office network/VPN. |
| `xcode-select` points at CommandLineTools | `sudo xcode-select -s /Applications/Xcode.app/Contents/Developer`. |

---

## Appendix A — Message to send colleagues

> **Installing MiCRM (iOS beta)**
> 1. Install **TestFlight** from the App Store (free, by Apple).
> 2. Open the invite link I sent (or the email invite) and tap **Accept** → **Install**.
> 3. Launch MiCRM. In Settings, make sure the server is `micrm.microimageph.com`.
> 4. Sign in with your CRM username and password.
> No "Developer Mode" or cable needed. If the app says a newer build is available, update it from TestFlight.

---

## Appendix B — Alternatives (if the $99 program is NOT approved yet)

- **Android app** — already shareable today: the signed `app-release.apk` is hosted on the file server; colleagues sideload it (serve it with MIME type `application/vnd.android.package-archive`).
- **Web CRM "Add to Home Screen"** — iPhone colleagues can open `https://micrm.microimageph.com` in **Safari → Share → Add to Home Screen** for an app-like icon and launch, with no Apple account required. This is the fastest stop-gap for iPhone users until TestFlight is live.
- **Ad Hoc distribution** (also needs the $99 program) — register each tester's device UDID, build a device-limited `.ipa`, distribute via link/MDM. More manual than TestFlight; only worth it if you specifically can't use TestFlight.

---

## Quick reference — commands

```bash
# One-time
brew install xcodegen

# After editing project.yml (team ID / version bump)
cd MiCRM_iOS
xcodegen generate
open MiCRM.xcodeproj

# In Xcode:
#   Destination: Any iOS Device (arm64)
#   Product → Archive → Distribute App → App Store Connect → Upload
```
