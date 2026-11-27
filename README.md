# mihomet core

Patched [mihomo](https://github.com/MetaCubeX/mihomo) builds for
[Mihomet](https://github.com/mihomet/mihomet) — the Android client in this
organization.

## Why this exists

Stock mihomo Android binaries fail to start their TUN listener without root:
the sing-tun Android integration reads `/data/system/packages.xml`, which is
unreadable to non-root apps ("Start TUN listening error: build android rules:
read packages list: ... permission denied"). Mihomet handles per-app routing
at the Android `VpnService.Builder` layer instead, so this repository ships
cores with a narrow patch: when no `include-package`/`exclude-package` filters
are configured and the package list cannot be read, TUN setup proceeds without
the android rules. With root (or when filters ARE configured) the stock
behavior is preserved.

Patch idea credited to [Tropa](https://github.com/nvsbunny/tropa)
(`tools/mihomo-android-nonroot.patch` @ v0.2.5), adapted for mihomo v1.19.33.

## Layout

- `core-patch/mihomo-android-nonroot.patch` — the patch (GPL-3.0)
- `core-build/build-core.sh` — reproducible build: clones mihomo at the pinned
  tag, applies the patch, cross-compiles for arm64-v8a / armeabi-v7a / x86_64
  via the Android NDK (targeting android-26 — Mihomet's minSdk), prints sha256

## Reproduce

```sh
ANDROID_NDK_HOME=/path/to/ndk ./core-build/build-core.sh
# artifacts + SHA256SUMS in core-build/dist/
```

Requires Docker (golang:1.26) and the Android NDK. The GitHub Actions
workflow builds the same artifacts on tag push (`core-*`).

## License

mihomo is GPL-3.0; this patch is GPL-3.0. The complete corresponding source
for any released binary is this repository (patch) plus the upstream mihomo
source at the pinned tag.

## Automatic stable upstream updates

The Build core workflow checks MetaCubeX/mihomo's latest **stable release** every
six hours. For a new version it resolves the immutable upstream commit, applies
the existing patch with `git apply --check`, and builds all three Android ABIs at
API 26. A patch conflict fails the run; the workflow never edits or weakens the
patch to force it through.

Before publication it checks exact binary hashes, sizes and ELF architectures,
then builds an isolated Mihomet **v1.3.8** smoke app with the candidate binaries.
The app's instrumented integration suites run on Android API 26 and 35 (x86_64),
including native core configuration and probe checks. These tests do not certify
physical ARM devices or root/TProxy hardware.

Only after both device jobs succeed does the publish job load the existing
`CORE_MANIFEST_KEY` secret, sign the manifest and verify it against the public key
already trusted by the app. Encrypted PEM keys use the optional
`CORE_MANIFEST_KEY_PASSWORD` secret. A missing password, missing key, or mismatched
signing key fails publication with a diagnostic that does not reveal the password.
The signed manifest records the upstream commit, build commit, patch SHA-256 and
Android API. Releases include all `.so` files, `SHA256SUMS`, `manifest.json` and
`manifest.json.sig`. The manifest version equals the `core-vX.Y.Z-mihomet.N` tag;
the executable's version omits only the leading `core-`, as expected by Mihomet.

The workflow creates an annotated source tag and an immutable release. It refuses
to replace an existing or incomplete release, and a scheduled check never rolls
back to an older upstream version. The app's production `mihomo-core.properties`
pin is unchanged: users obtain a published candidate through the existing signed
core-update flow; bundling it in an APK remains a separate verified version bump.

For a dry run, dispatch Build core with `upstream_tag=vX.Y.Z` and `publish=false`
(the default). To publish a tested candidate manually, set `publish=true` or push
a matching `core-vX.Y.Z-mihomet.N` tag. Schedule activation requires this workflow
to be present on the default branch. No signing key is available to pull-request
or build/smoke jobs.

Local release-planning and trust-boundary tests:

```sh
python3 -m unittest discover -s core-build -p 'test_*.py' -v
bash -n core-build/build-core.sh
```
