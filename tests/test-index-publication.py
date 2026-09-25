#!/usr/bin/env python3
"""Real dpkg/GPG regression checks; all keys and packages are disposable fixtures."""
import contextlib
import gzip
import getpass
import io
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tarfile
import tempfile
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
import index_all_staged as indexer
from audit_repository import audit


class PublicationTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.workspace = tempfile.TemporaryDirectory(prefix="ocean-index-tests-")
        cls.home = Path(cls.workspace.name) / "gnupg"
        cls.home.mkdir(mode=0o700)
        cls.env = {**os.environ, "GNUPGHOME": str(cls.home)}
        subprocess.run([
            "gpg", "--batch", "--pinentry-mode", "loopback", "--passphrase", "",
            "--quick-generate-key", "Ocean fixture <test@example.invalid>", "ed25519", "sign", "0",
        ], env=cls.env, check=True, capture_output=True)
        cls.public_key = subprocess.check_output(["gpg", "--batch", "--export"], env=cls.env)

    @classmethod
    def tearDownClass(cls):
        subprocess.run(["gpgconf", "--kill", "gpg-agent"], env=cls.env, capture_output=True)
        cls.workspace.cleanup()

    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(dir=self.workspace.name)
        self.root = Path(self.temp.name)
        self.dists = self.root / "apt/dists/stable"
        (self.dists / indexer.INDEX).parent.mkdir(parents=True)
        (self.dists / indexer.INDEX).write_text("")
        (self.root / "apt/ocean.gpg").write_bytes(self.public_key)
        (self.root / "staging").mkdir()
        self.environment = patch.dict(os.environ, {"GNUPGHOME": str(self.home)})
        self.environment.start()
        self.publish()

    def tearDown(self):
        self.environment.stop()
        self.temp.cleanup()

    def publish(self):
        with contextlib.redirect_stdout(io.StringIO()):
            indexer.run_indexing(root=self.root)

    def build(self, version="1.0-1", group="one", content="working\n", name="ocean-fixture", arch="all"):
        directory = self.root / ("source-" + group)
        (directory / "DEBIAN").mkdir(parents=True, exist_ok=True)
        (directory / "DEBIAN/control").write_text(
            f"Package: {name}\nVersion: {version}\nArchitecture: {arch}\n"
            "Maintainer: Ocean Test <test@example.invalid>\nDescription: real indexing fixture\n"
        )
        (directory / "payload").write_text(content)
        destination = self.root / f"staging/{group}/pool/main/{name}_{version}_{arch}.deb"
        destination.parent.mkdir(parents=True, exist_ok=True)
        subprocess.run(["dpkg-deb", "-Zxz", "--root-owner-group", "--build", str(directory), str(destination)],
                       check=True, capture_output=True)
        return destination

    def records(self):
        return [indexer.fields(s) for s in indexer.stanzas((self.dists / indexer.INDEX).read_text())]

    def test_complete_signed_snapshot_and_all_staged_coverage(self):
        self.build()
        self.publish()
        report = audit(self.root)
        self.assertEqual(report["errors"], [])
        self.assertEqual(report["indexedEntries"], 1)
        self.assertEqual(report["stagedFiles"], 1)
        self.assertFalse(report["runtimeTested"])

    def test_duplicate_copies_do_not_duplicate_index_entries(self):
        source = self.build()
        duplicate = self.root / "staging/two/pool/main" / source.name
        duplicate.parent.mkdir(parents=True)
        shutil.copyfile(source, duplicate)
        self.publish()
        self.assertEqual(len(self.records()), 1)
        self.assertEqual(audit(self.root)["stagedFiles"], 2)
        self.assertEqual(audit(self.root)["errors"], [])

    def control_archive(self, duplicate=False):
        path = self.build()
        original, _ = indexer.parse_deb(path)
        stream = io.BytesIO()
        with tarfile.open(fileobj=stream, mode="w:gz") as archive:
            for _ in range(2 if duplicate else 1):
                member = tarfile.TarInfo("./control")
                member.uid = member.gid = 10629
                member.size = len(original.encode())
                member.mode = 0o644
                archive.addfile(member, io.BytesIO(original.encode()))
        members = {"debian-binary": b"2.0\n", "control.tar.gz": stream.getvalue(),
                   "data.tar.xz": subprocess.check_output(["ar", "p", str(path), "data.tar.xz"])}
        output = bytearray(b"!<arch>\n")
        for name, data in members.items():
            output.extend(f"{name + '/':<16}{0:<12}{0:<6}{0:<6}{'100644':<8}{len(data):<10}`\n".encode())
            output.extend(data)
            if len(data) % 2: output.extend(b"\n")
        path.write_bytes(output)
        return path

    def test_android_owned_control_is_read_without_host_ownership_changes(self):
        path = self.control_archive()
        control, _ = indexer.parse_deb(path)
        self.assertEqual(indexer.fields(control)["Package"], "ocean-fixture")

    def test_duplicate_control_members_are_rejected(self):
        path = self.control_archive(duplicate=True)
        with self.assertRaisesRegex(ValueError, "one regular control"):
            indexer.parse_deb(path)

    def test_immutable_indexes_survive_later_publication(self):
        self.build()
        self.publish()
        previous = (self.dists / (str(indexer.INDEX) + ".gz")).read_bytes()
        digest = indexer.hashlib.sha256(previous).hexdigest()
        self.build("2.0", group="new")
        self.publish()
        self.assertIn("Acquire-By-Hash: yes", (self.dists / "Release").read_text())
        retained = self.dists / indexer.INDEX.parent / "by-hash/SHA256" / digest
        self.assertEqual(retained.read_bytes(), previous)
        self.assertEqual(audit(self.root)["errors"], [])

    def test_older_staging_cannot_downgrade_live_version(self):
        self.build("1.10-1", group="a-new")
        self.publish()
        self.build("1.9-1", group="z-old")
        self.publish()
        self.assertEqual(self.records()[0]["Version"], "1.10-1")
        self.assertEqual(audit(self.root)["errors"], [])

    def test_conflicting_same_version_rejected_without_live_mutation(self):
        self.build(group="first")
        self.publish()
        before = self.snapshot()
        self.build(group="second", content="changed\n")
        with self.assertRaisesRegex(ValueError, "Conflicting bytes"):
            self.publish()
        self.assertEqual(self.snapshot(), before)

    def test_missing_private_key_leaves_all_live_files_untouched(self):
        self.build()
        before = self.snapshot()
        empty_home = self.root / "empty-gnupg"
        empty_home.mkdir(mode=0o700)
        with patch.dict(os.environ, {"GNUPGHOME": str(empty_home)}):
            with self.assertRaisesRegex(ValueError, "private signing key unavailable"):
                self.publish()
        self.assertEqual(self.snapshot(), before)

    def test_stale_inrelease_is_detected(self):
        stale = (self.dists / "InRelease").read_bytes()
        self.build()
        self.publish()
        (self.dists / "InRelease").write_bytes(stale)
        self.assertTrue(any("different metadata" in e for e in audit(self.root)["errors"]))

    def test_stale_detached_signature_is_detected(self):
        stale = (self.dists / "Release.gpg").read_bytes()
        self.build()
        self.publish()
        (self.dists / "Release.gpg").write_bytes(stale)
        with self.assertRaises(subprocess.CalledProcessError):
            indexer.verify_release(self.dists, self.root / "apt/ocean.gpg")

    def test_equal_size_damaged_live_blob_is_repaired_by_hash(self):
        source = self.build()
        self.publish()
        live = self.root / "apt" / self.records()[0]["Filename"]
        data = live.read_bytes()
        live.write_bytes(data[:-1] + bytes([data[-1] ^ 1]))
        self.assertEqual(live.stat().st_size, source.stat().st_size)
        self.publish()
        self.assertEqual(live.read_bytes(), source.read_bytes())

    def test_preserves_architectures_and_legacy_names(self):
        self.build(name="glslangValidator", arch="all", group="all")
        self.build(name="glslangValidator", arch="aarch64", group="arm")
        self.publish()
        self.assertEqual({r["Architecture"] for r in self.records()}, {"all", "aarch64"})

    def test_pool_alias_does_not_create_another_package(self):
        self.build()
        self.publish()
        live = self.root / "apt" / self.records()[0]["Filename"]
        live.with_name("alias.deb").symlink_to(live.name)
        self.assertEqual(len(audit(self.root)["poolSymlinks"]), 1)
        self.publish()
        self.assertEqual(len(self.records()), 1)

    def test_indexing_does_not_claim_functional_validation(self):
        status = self.root / "staging/functional-repair-status.json"
        status.write_text('{"remainingPlaceholderPackages": 123}\n')
        before = status.read_bytes()
        self.build()
        self.publish()
        self.assertEqual(status.read_bytes(), before)

    def test_unindexed_pool_package_and_newer_pool_version_are_promoted(self):
        self.build(version="1.0")
        self.publish()
        for name, version in (("ocean-fixture", "1:2.0"), ("pool-only", "1.0")):
            built = self.build(version=version, name=name, group=name)
            pool = self.root / "apt/pool/extra" / built.name
            pool.parent.mkdir(parents=True, exist_ok=True)
            built.rename(pool)
        self.publish()
        records = {r["Package"]: r for r in self.records()}
        self.assertEqual(records["ocean-fixture"]["Version"], "1:2.0")
        self.assertEqual(records["pool-only"]["Filename"], "pool/extra/pool-only_1.0_all.deb")
        self.assertEqual(audit(self.root)["errors"], [])

    def test_historical_pool_conflict_retains_published_build_and_reports_it(self):
        self.build()
        self.publish()
        canonical = self.records()[0]["SHA256"]
        conflict = self.build(group="conflict", content="different bytes\n")
        historical = self.root / "apt/pool/main/conflicting-alias.deb"
        conflict.rename(historical)
        self.publish()
        self.assertEqual(self.records()[0]["SHA256"], canonical)
        self.assertTrue(historical.is_file())
        _, plan = indexer.select_packages(self.root)
        self.assertEqual(plan["retainedPoolConflicts"][0]["path"], "apt/pool/main/conflicting-alias.deb")

    def test_missing_live_file_fails_before_new_metadata_is_written(self):
        self.build()
        self.publish()
        shutil.rmtree(self.root / "staging")
        (self.root / "apt" / self.records()[0]["Filename"]).unlink()
        before = self.snapshot()
        with self.assertRaises(subprocess.CalledProcessError):
            self.publish()
        self.assertEqual(self.snapshot(), before)

    def test_real_apt_accepts_signed_index_and_sees_the_package(self):
        self.build()
        self.publish()
        client = self.root / "apt-client"
        (client / "lists/partial").mkdir(parents=True)
        (client / "cache/archives/partial").mkdir(parents=True)
        (client / "status").write_text("")
        (client / "sources.list").write_text(
            f"deb [arch=aarch64 signed-by={self.root}/apt/ocean.gpg] "
            f"file:{self.root}/apt stable main\n"
        )
        options = [
            "-o", f"Dir::Etc::sourcelist={client}/sources.list",
            "-o", "Dir::Etc::sourceparts=-",
            "-o", f"Dir::State::lists={client}/lists",
            "-o", f"Dir::State::status={client}/status",
            "-o", f"Dir::Cache={client}/cache",
            "-o", "APT::Architecture=aarch64",
            "-o", f"APT::Sandbox::User={getpass.getuser()}",
            "-o", "Debug::NoLocking=true",
        ]
        result = subprocess.run(["apt-get", *options, "update"], text=True,
                                capture_output=True, timeout=30)
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        result = subprocess.run(["apt-cache", *options, "policy", "ocean-fixture"],
                                text=True, capture_output=True, check=True)
        self.assertIn("Candidate: 1.0-1", result.stdout)

    def snapshot(self):
        return {str(p.relative_to(self.root)): p.read_bytes()
                for p in (self.root / "apt").rglob("*") if p.is_file()}


if __name__ == "__main__":
    unittest.main()
