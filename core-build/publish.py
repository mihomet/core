#!/usr/bin/env python3
"""Publish only new, completely verified and signed artifacts; never overwrite a release."""
import json
import os
from pathlib import Path
import re
import subprocess
import sys
from upstream import api, verify

if __name__ == "__main__":
    tag = sys.argv[1]
    if not re.fullmatch(r"core-v[0-9]+\.[0-9]+\.[0-9]+-mihomet\.[0-9]+", tag):
        raise ValueError("Invalid release tag")
    os.environ["REQUIRE_SIGNATURE"] = "true"
    dist = Path("core-build/dist")
    verify(dist, tag)
    if api(f"repos/mihomet/core/releases/tags/{tag}", missing_ok=True):
        raise ValueError("Release already exists; refusing to replace signed artifacts")
    sha = os.environ["GITHUB_SHA"]
    ref = api(f"repos/mihomet/core/git/ref/tags/{tag}", missing_ok=True)
    if ref:
        obj = ref["object"]
        while obj["type"] == "tag":
            obj = api(f"repos/mihomet/core/git/tags/{obj['sha']}")["object"]
        if obj["type"] != "commit" or obj["sha"] != sha:
            raise ValueError("Existing tag points to different build sources")
    else:
        data = json.dumps({"tag": tag, "message": f"Mihomet patched core {tag}", "object": sha, "type": "commit"})
        obj = json.loads(subprocess.check_output(["gh", "api", "--method", "POST", "repos/mihomet/core/git/tags", "--input", "-"], input=data, text=True))
        data = json.dumps({"ref": f"refs/tags/{tag}", "sha": obj["sha"]})
        subprocess.run(["gh", "api", "--method", "POST", "repos/mihomet/core/git/refs", "--input", "-"], input=data, text=True, check=True)
    manifest = json.loads((dist / "manifest.json").read_text())
    source = manifest["source"]
    notes = Path(os.environ["RUNNER_TEMP"]) / "core-release-notes.md"
    notes.write_text(f"Patched upstream **{source['upstreamTag']}** (`{source['upstreamCommit']}`).\n\n"
        "Built for Android API 26, with arm64-v8a, armeabi-v7a and x86_64 artifacts. "
        "All ABI hashes, sizes and ELF architectures were verified. "
        "The candidate passed the Mihomet v1.3.8 Android integration suites on API 26 and 35 (x86_64).\n\n"
        "The RSA-signed manifest is verified against the public key trusted by Mihomet. "
        "The app checks it again before installation.\n\n"
        f"Build sources: https://github.com/mihomet/core/tree/{sha}\n\n"
        f"Upstream sources: https://github.com/MetaCubeX/mihomo/tree/{source['upstreamCommit']}\n\n"
        f"Patch SHA-256: `{source['patchSha256']}`.\n\n"
        "Physical ARM and root/TProxy hardware were not exercised by the emulator suites.\n")
    artifacts = [str(dist / f"libmihomo-{abi}.so") for abi in manifest["artifacts"]]
    artifacts += [str(dist / name) for name in ("SHA256SUMS", "manifest.json", "manifest.json.sig")]
    subprocess.run(["gh", "release", "create", tag, "--repo", "mihomet/core", "--verify-tag", "--title", tag,
                    "--notes-file", str(notes), *artifacts], check=True)
