#!/usr/bin/env python3
"""Resolve stable upstream releases and verify the artifacts before publication."""
import hashlib
import json
import os
from pathlib import Path
import re
import subprocess
import sys

ABIS = {"arm64-v8a": (2, 183), "armeabi-v7a": (1, 40), "x86_64": (2, 62)}
ASSETS = {f"libmihomo-{abi}.so" for abi in ABIS} | {"SHA256SUMS", "manifest.json", "manifest.json.sig"}


def api(path, missing_ok=False):
    result = subprocess.run(["gh", "api", path], capture_output=True, text=True, check=False)
    if result.returncode:
        if missing_ok and "HTTP 404" in result.stderr:
            return None
        raise RuntimeError(f"GitHub API failed for {path}: {result.stderr.strip()}")
    return json.loads(result.stdout)


def stable_version(tag):
    if not re.fullmatch(r"v[0-9]+\.[0-9]+\.[0-9]+", tag):
        raise ValueError("Only stable upstream vX.Y.Z tags are accepted")
    return tuple(int(part) for part in tag[1:].split("."))


def plan(upstream, existing, requested_core_tag="", scheduled=False):
    version = upstream["tag_name"]
    stable_version(version)
    if upstream.get("draft") or upstream.get("prerelease"):
        raise ValueError("Draft and prerelease upstream versions are not published")
    core_tag = requested_core_tag or f"core-{version}-mihomet.1"
    if not re.fullmatch(r"core-" + re.escape(version) + r"-mihomet\.[0-9]+", core_tag):
        raise ValueError("Core tag must match the resolved upstream version")
    complete = existing and not existing.get("draft") and not existing.get("prerelease") and ASSETS <= {
        asset["name"] for asset in existing.get("assets", []) if asset.get("state") == "uploaded"
    }
    if existing and not complete:
        raise ValueError("An incomplete release already exists; refusing to replace its binaries")
    return {"upstream": version, "tag": core_tag, "version": core_tag.removeprefix("core-"),
            "build": not (scheduled and complete)}


def resolve():
    event = os.environ.get("GITHUB_EVENT_NAME", "workflow_dispatch")
    ref = os.environ.get("GITHUB_REF", "")
    requested = os.environ.get("INPUT_UPSTREAM_TAG", "").strip()
    core_tag = ""
    if event == "push":
        core_tag = ref.removeprefix("refs/tags/")
        match = re.fullmatch(r"core-(v[0-9]+\.[0-9]+\.[0-9]+)-mihomet\.[0-9]+", core_tag)
        if not match:
            raise ValueError("A core tag push must use core-vX.Y.Z-mihomet.N")
        requested = match[1]
    if requested:
        stable_version(requested)
    upstream = api("repos/MetaCubeX/mihomo/releases/" + (f"tags/{requested}" if requested else "latest"))
    version = upstream["tag_name"]
    stable_version(version)
    wanted_tag = core_tag or f"core-{version}-mihomet.1"
    existing = api(f"repos/mihomet/core/releases/tags/{wanted_tag}", missing_ok=True)
    output = plan(upstream, existing, core_tag, scheduled=event == "schedule")
    obj = api(f"repos/MetaCubeX/mihomo/git/ref/tags/{version}")["object"]
    while obj["type"] == "tag":
        obj = api(f"repos/MetaCubeX/mihomo/git/tags/{obj['sha']}")["object"]
    if obj["type"] != "commit" or not re.fullmatch(r"[0-9a-f]{40}", obj["sha"]):
        raise ValueError("Upstream tag must resolve to an immutable commit")
    output["commit"] = obj["sha"]
    output["publish"] = event in {"schedule", "push"} or os.environ.get("INPUT_PUBLISH") == "true"
    if existing and output["publish"]:
        output["build"] = False
    # Schedule only advances the stable upstream version; it never rolls it back.
    if event == "schedule":
        latest = api("repos/mihomet/core/releases/latest", missing_ok=True)
        match = re.fullmatch(r"core-(v[0-9]+\.[0-9]+\.[0-9]+)-mihomet\.[0-9]+", (latest or {}).get("tag_name", ""))
        if match and stable_version(match[1]) > stable_version(version):
            output["build"] = False
    with open(os.environ["GITHUB_OUTPUT"], "a", encoding="utf-8") as handle:
        for key, value in output.items():
            handle.write(f"{key}={str(value).lower() if isinstance(value, bool) else value}\n")
    print(json.dumps(output, indent=2))


def verify(directory, expected_tag):
    directory = Path(directory)
    manifest_path = directory / "manifest.json"
    manifest = json.loads(manifest_path.read_text())
    if manifest.get("schema") != 1 or manifest.get("version") != expected_tag:
        raise ValueError("Manifest version must equal the release tag")
    if set(manifest.get("artifacts", {})) != set(ABIS):
        raise ValueError("All three Android ABIs must be present")
    for abi, (elf_class, machine) in ABIS.items():
        artifact = manifest["artifacts"][abi]
        filename = f"libmihomo-{abi}.so"
        data = (directory / filename).read_bytes()
        if artifact["file"] != filename or artifact["size"] != len(data) or artifact["sha256"] != hashlib.sha256(data).hexdigest():
            raise ValueError(f"Invalid checksum, size or file name: {abi}")
        if data[:6] != b"\x7fELF" + bytes([elf_class, 1]) or int.from_bytes(data[18:20], "little") != machine:
            raise ValueError(f"Wrong ELF architecture: {abi}")
    if os.environ.get("REQUIRE_SIGNATURE") == "true" or (directory / "manifest.json.sig").exists():
        subprocess.run(["openssl", "dgst", "-sha256", "-verify", str(Path(__file__).with_name("core-update-public-key.pem")),
                        "-signature", str(directory / "manifest.json.sig"), str(manifest_path)], check=True)
    print(f"Verified {expected_tag}: all ABI hashes, sizes, ELF architectures and required signature")


if __name__ == "__main__":
    if sys.argv[1:] == ["resolve"]:
        resolve()
    elif len(sys.argv) == 4 and sys.argv[1] == "verify":
        verify(sys.argv[2], sys.argv[3])
    else:
        raise SystemExit("Usage: upstream.py resolve | verify DIST RELEASE_TAG")
