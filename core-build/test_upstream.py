import hashlib
import json
import os
from pathlib import Path
import subprocess
import tempfile
import unittest
from unittest.mock import patch

from sign_manifest import sign_manifest
from upstream import ABIS, ASSETS, plan, stable_version, verify


class ReleasePlanTest(unittest.TestCase):
    def setUp(self):
        self.upstream = {"tag_name": "v1.19.34", "draft": False, "prerelease": False}
        self.complete = {"draft": False, "assets": [{"name": name, "state": "uploaded"} for name in ASSETS]}

    def test_stable_release_uses_matching_core_version_and_tag(self):
        result = plan(self.upstream, None)
        self.assertEqual("core-v1.19.34-mihomet.1", result["tag"])
        self.assertEqual("v1.19.34-mihomet.1", result["version"])
        self.assertTrue(result["build"])

    def test_schedule_skips_completed_release_but_manual_smoke_can_rebuild(self):
        self.assertFalse(plan(self.upstream, self.complete, scheduled=True)["build"])
        self.assertTrue(plan(self.upstream, self.complete)["build"])

    def test_never_replaces_partial_existing_release(self):
        with self.assertRaises(ValueError):
            plan(self.upstream, {"draft": False, "assets": []}, scheduled=True)

    def test_no_prereleases_drafts_or_shell_fragments(self):
        for tag in ("v1.19.34-beta.1", "main", "v1.19.34\nnext=true", "v1.19.34;echo x"):
            with self.assertRaises(ValueError):
                stable_version(tag)
        for field in ("draft", "prerelease"):
            with self.assertRaises(ValueError):
                plan(dict(self.upstream, **{field: True}), None)
        with self.assertRaises(ValueError):
            plan(self.upstream, None, "core-v1.19.33-mihomet.3")


class ArtifactVerifierTest(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.dist = Path(self.temp.name)
        self.manifest = {"schema": 1, "version": "core-v1.19.34-mihomet.1", "artifacts": {}}
        for abi, (elf_class, machine) in ABIS.items():
            data = bytearray(64)
            data[:6] = b"\x7fELF" + bytes([elf_class, 1])
            data[18:20] = machine.to_bytes(2, "little")
            filename = f"libmihomo-{abi}.so"
            (self.dist / filename).write_bytes(data)
            self.manifest["artifacts"][abi] = {"file": filename, "sha256": hashlib.sha256(data).hexdigest(), "size": len(data)}
        self.write_manifest()

    def write_manifest(self):
        (self.dist / "manifest.json").write_text(json.dumps(self.manifest))

    def test_complete_unsigned_candidate_is_allowed_only_for_smoke(self):
        with patch.dict(os.environ, {"REQUIRE_SIGNATURE": "false"}):
            verify(self.dist, self.manifest["version"])

    def test_corruption_is_rejected(self):
        with (self.dist / "libmihomo-arm64-v8a.so").open("ab") as handle:
            handle.write(b"corruption")
        with self.assertRaises(ValueError):
            verify(self.dist, self.manifest["version"])

    def test_wrong_architecture_is_rejected_even_with_matching_checksum(self):
        filename = self.dist / "libmihomo-x86_64.so"
        data = bytearray(filename.read_bytes())
        data[18:20] = (183).to_bytes(2, "little")
        filename.write_bytes(data)
        self.manifest["artifacts"]["x86_64"]["sha256"] = hashlib.sha256(data).hexdigest()
        self.write_manifest()
        with self.assertRaises(ValueError):
            verify(self.dist, self.manifest["version"])

    def test_manifest_must_match_release_tag(self):
        with self.assertRaises(ValueError):
            verify(self.dist, "core-v1.19.33-mihomet.3")

    def test_publishing_requires_a_signature(self):
        with patch.dict(os.environ, {"REQUIRE_SIGNATURE": "true"}), patch("upstream.subprocess.run") as openssl:
            openssl.side_effect = FileNotFoundError("missing signature")
            with self.assertRaises(FileNotFoundError):
                verify(self.dist, self.manifest["version"])
            self.assertIn("-verify", openssl.call_args[0][0])


class ManifestSignerTest(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.directory = Path(self.temp.name)
        self.key = self.directory / "encrypted-key.pem"
        self.public_key = self.directory / "public-key.pem"
        self.manifest = self.directory / "manifest.json"
        self.signature = self.directory / "manifest.json.sig"
        self.manifest.write_text('{"version":"test"}\n')
        self.password = "test-only-passphrase"
        subprocess.run(
            ["openssl", "genpkey", "-algorithm", "RSA", "-pkeyopt", "rsa_keygen_bits:2048",
             "-aes-256-cbc", "-pass", "env:TEST_KEY_PASSWORD", "-out", str(self.key)],
            env=dict(os.environ, TEST_KEY_PASSWORD=self.password),
            check=True,
            capture_output=True,
        )
        subprocess.run(
            ["openssl", "pkey", "-in", str(self.key), "-passin", "env:TEST_KEY_PASSWORD",
             "-pubout", "-out", str(self.public_key)],
            env=dict(os.environ, TEST_KEY_PASSWORD=self.password),
            check=True,
            capture_output=True,
        )

    def test_signs_encrypted_key_and_verifies_signature(self):
        with patch.dict(os.environ, {"CORE_MANIFEST_KEY_PASSWORD": self.password}):
            sign_manifest(self.key, self.manifest, self.signature)
        subprocess.run(
            ["openssl", "dgst", "-sha256", "-verify", str(self.public_key), "-signature",
             str(self.signature), str(self.manifest)], check=True, capture_output=True,
        )

    def test_missing_or_wrong_password_fails_without_echoing_it(self):
        for password in (None, "incorrect-test-passphrase"):
            environment = os.environ.copy()
            environment.pop("CORE_MANIFEST_KEY_PASSWORD", None)
            if password is not None:
                environment["CORE_MANIFEST_KEY_PASSWORD"] = password
            with patch.dict(os.environ, environment, clear=True):
                with self.assertRaisesRegex(ValueError, "CORE_MANIFEST_KEY_PASSWORD") as error:
                    sign_manifest(self.key, self.manifest, self.signature)
            self.assertNotIn("incorrect-test-passphrase", str(error.exception))


if __name__ == "__main__":
    unittest.main()
