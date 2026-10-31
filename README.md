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

Requires Docker (golang:1.23) and the Android NDK. The GitHub Actions
workflow builds the same artifacts on tag push (`core-*`).

## License

mihomo is GPL-3.0; this patch is GPL-3.0. The complete corresponding source
for any released binary is this repository (patch) plus the upstream mihomo
source at the pinned tag.
