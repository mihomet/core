#!/usr/bin/env python3
"""Use candidate binaries in an isolated app checkout, leaving production pins alone."""
import base64
import json
from pathlib import Path
import re
import shutil
import sys
from upstream import verify

if __name__ == "__main__":
    dist, app = map(Path, sys.argv[1:])
    manifest = json.loads((dist / "manifest.json").read_text())
    verify(dist, manifest["version"])
    constants = (app / "app/src/main/kotlin/org/mihomet/app/core/CoreConstants.kt").read_text()
    key = re.search(r'CORE_UPDATE_PUBLIC_KEY_B64\s*=\s*"([^"]+)"', constants)[1]
    trusted = Path(__file__).with_name("core-update-public-key.pem").read_text()
    if base64.b64decode(key) != base64.b64decode("".join(trusted.splitlines()[1:-1])):
        raise ValueError("Smoke app and release verifier must trust the same signing key")
    lines = ["# Isolated candidate for core smoke tests", f"version={manifest['version']}"]
    for abi, artifact in manifest["artifacts"].items():
        lines.extend([f"checksum.{abi}={artifact['sha256']}", f"size.{abi}={artifact['size']}"])
        target = app / "app/src/main/jniLibs" / abi / "libmihomo.so"
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(dist / artifact["file"], target)
    (app / "gradle/mihomo-core.properties").write_text("\n".join(lines) + "\n")
