#!/usr/bin/env python3
"""Sign a core manifest without exposing an optional key passphrase in argv."""
import os
from pathlib import Path
import subprocess
import sys


def sign_manifest(key_path, manifest_path, signature_path):
    command = ["openssl", "dgst", "-sha256", "-passin", "env:CORE_MANIFEST_KEY_PASSWORD"]
    command.extend(["-sign", str(key_path), "-out", str(signature_path), str(manifest_path)])
    environment = os.environ.copy()
    environment.setdefault("CORE_MANIFEST_KEY_PASSWORD", "")
    result = subprocess.run(command, capture_output=True, text=True, check=False, env=environment)
    if result.returncode:
        raise ValueError(
            "OpenSSL could not sign with CORE_MANIFEST_KEY. If the key is encrypted, "
            "set the CORE_MANIFEST_KEY_PASSWORD GitHub secret to its existing passphrase."
        )


if __name__ == "__main__":
    if len(sys.argv) != 4:
        raise SystemExit("Usage: sign_manifest.py PRIVATE_KEY MANIFEST SIGNATURE")
    try:
        sign_manifest(Path(sys.argv[1]), Path(sys.argv[2]), Path(sys.argv[3]))
    except ValueError as error:
        print(f"::error::{error}", file=sys.stderr)
        raise SystemExit(1) from None
