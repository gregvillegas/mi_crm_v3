# MiCRM Android — Build Guide (Debug & Signed Release APK)

Step-by-step, **copy-paste-into-Terminal** instructions to build the MiCRM Android app on this Mac.

- **Debug APK** — for your own testing / quick installs.
- **Signed Release APK** — the one you upload to the file server for colleagues.

> This project has **no `gradlew` wrapper** and uses a **cached Gradle 9.3.1** plus **OpenJDK 17** that isn't registered with macOS's `java_home`. So every build must set `JAVA_HOME` and call the cached `gradle` launcher directly. The commands below do that for you.

---

## 0. One-time setup of shell shortcuts (copy-paste once per Terminal window)

Paste this block first in any new Terminal session. It points at the JDK and the cached Gradle, and defines a `GRADLE` shortcut used by the rest of the guide.

```bash
# JDK 17 (Homebrew) — required; this machine's `java_home` doesn't see it.
export JAVA_HOME=/opt/homebrew/opt/openjdk@17/libexec/openjdk.jdk/Contents/Home
export PATH="$JAVA_HOME/bin:$PATH"

# Locate the cached Gradle 9.3.1 launcher (the hashed folder name can vary).
GRADLE="$(ls "$HOME"/.gradle/wrapper/dists/gradle-9.3.1-bin/*/gradle-9.3.1/bin/gradle 2>/dev/null | head -1)"
echo "Using Gradle at: $GRADLE"

# Project directory
cd /Users/greg/Documents/mi_crm_v2/MiCRM_Android
```

Sanity check (optional):

```bash
java -version        # should print openjdk 17.x
"$GRADLE" --version  # should print Gradle 9.3.1
```

> **If `Using Gradle at:` is empty** (cache was cleared), install the wrapper distribution once:
> ```bash
> brew install gradle          # if you don't have any gradle on PATH
> gradle wrapper --gradle-version 9.3.1   # creates ./gradlew; then use ./gradlew below
> ```
> After that you can use `./gradlew` in place of `"$GRADLE"` everywhere.

---

## 1. Build the DEBUG APK

```bash
"$GRADLE" :app:assembleDebug --console=plain
```

Output:

```
app/build/outputs/apk/debug/app-debug.apk
```

Install to a connected device/emulator (optional):

```bash
adb install -r app/build/outputs/apk/debug/app-debug.apk
```

---

## 2. Build the SIGNED RELEASE APK

### 2a. Confirm the signing keystore is present (one-time check)

The release build is signed automatically using `keystore.properties` + `upload-keystore.jks` (already in the project).

```bash
cat keystore.properties        # should list storePassword / keyPassword / keyAlias / storeFile
ls -la upload-keystore.jks     # the signing key must exist
```

> ⚠️ **Keep `upload-keystore.jks` safe and backed up.** Every future update MUST be signed with this same key, or users can't update (they'd have to uninstall/reinstall). Never lose it.

### 2b. Bump the version (do this for EVERY new release you distribute)

Edit `app/build.gradle.kts` and increase the version so phones recognise the new APK as an **update**:

```kotlin
versionCode = 4        // must be HIGHER than the last released build (was 3)
versionName = "1.3"    // user-facing version
```

- `versionCode` **must increase** every release or the update won't install over the old one.
- Open the file quickly from Terminal if you like: `open -e app/build.gradle.kts`

### 2c. Build it

```bash
"$GRADLE" :app:assembleRelease --console=plain
```

Output:

```
app/build/outputs/apk/release/app-release.apk
```

This runs R8/resource optimisation, lint-vital, and **signs** the APK with your release key — all in one step.

### 2d. Verify the result (optional but recommended)

```bash
# Version baked into the APK:
"$(ls "$HOME"/Library/Android/sdk/build-tools/*/aapt2 | sort -V | tail -1)" \
  dump badging app/build/outputs/apk/release/app-release.apk | grep "package:"

# Signature (should show CN=Greg Villegas ... MIIC):
"$(ls "$HOME"/Library/Android/sdk/build-tools/*/apksigner | sort -V | tail -1)" \
  verify --print-certs app/build/outputs/apk/release/app-release.apk | grep "DN:"
```

---

## 3. Share the release APK (file server)

Copy `app/build/outputs/apk/release/app-release.apk` to your web/file server.

- Serve it with the correct MIME type so phones install it rather than download a blob:
  ```
  Content-Type: application/vnd.android.package-archive
  ```
  (nginx example — add to the server/location config:)
  ```nginx
  types { application/vnd.android.package-archive apk; }
  ```
- Colleagues tap the link; Android asks them to allow "Install unknown apps" from the browser the first time (normal for sideloaded apps).

---

## 4. Quick reference (TL;DR)

```bash
# Setup (once per Terminal window)
export JAVA_HOME=/opt/homebrew/opt/openjdk@17/libexec/openjdk.jdk/Contents/Home
export PATH="$JAVA_HOME/bin:$PATH"
GRADLE="$(ls "$HOME"/.gradle/wrapper/dists/gradle-9.3.1-bin/*/gradle-9.3.1/bin/gradle | head -1)"
cd /Users/greg/Documents/mi_crm_v2/MiCRM_Android

# Debug
"$GRADLE" :app:assembleDebug --console=plain
#  -> app/build/outputs/apk/debug/app-debug.apk

# Release (after bumping versionCode/versionName in app/build.gradle.kts)
"$GRADLE" :app:assembleRelease --console=plain
#  -> app/build/outputs/apk/release/app-release.apk
```

---

## 5. Common issues

| Symptom | Fix |
|---|---|
| `Unable to locate a Java Runtime` / `JAVA_HOME is not set` | Re-run the `export JAVA_HOME=...` + `export PATH=...` lines (Step 0). This JDK isn't auto-detected on this Mac. |
| `Using Gradle at:` prints empty | The cached Gradle was cleared. Install Gradle (`brew install gradle`) then `gradle wrapper --gradle-version 9.3.1` and use `./gradlew`. |
| Release build fails on signing | Check `keystore.properties` values and that `upload-keystore.jks` exists (Step 2a). |
| Update won't install over the old app on a phone | `versionCode` wasn't increased, or it was signed with a different key. Bump `versionCode` and always use the same `upload-keystore.jks`. |
| `adb: command not found` | Add platform-tools to PATH: `export PATH="$HOME/Library/Android/sdk/platform-tools:$PATH"`. |
| Build hangs / stale cache | Add `--offline` to the gradle command to force use of the local cache, or `"$GRADLE" --stop` to kill a stuck daemon, then retry. |

---

## Notes

- The web backend is deployed separately (`deploy2.sh`), which **excludes `MiCRM_Android`** — building/distributing the mobile app is independent of the server deploy. Features that call new API endpoints (e.g. global search, the login quote) only work once the backend change is live on the server.
- Current released version at time of writing: **versionCode 3 / versionName 1.2**. The next release should be **4 / 1.3** (shown in the examples above).
- For a Play Store upload you'd build an App Bundle instead (`"$GRADLE" :app:bundleRelease` → `app/build/outputs/bundle/release/app-release.aab`). Not needed for self-hosted file-server distribution.
