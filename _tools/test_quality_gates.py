# Copyright IBM Corp. 2026
# SPDX-License-Identifier: Apache-2.0
# Modified for open-source preparation on 2026-10-23.
# AI assistance: may include Anthropic Claude Opus 4+, Sonnet 3.7+, and
# OpenAI GPT-4+ model contributions; exact per-file provenance is unverified.
# See AI_DISCLOSURE.md and NOTICE.md at the collection root.

"""Regression tests for false passes in privacy and lockfile checks."""

import contextlib
import hashlib
import io
import json
import tempfile
import unittest
import zipfile
from pathlib import Path
from unittest.mock import patch

import audit_dependencies
import check_public
import nbformat
import prepare_release
import release_evidence
import validate
from public_files import checked_files

ROOT = Path(__file__).resolve().parents[1]


class QualityGateTests(unittest.TestCase):
    def setUp(self):
        scratch = ROOT / ".build/gate-tests"
        scratch.mkdir(parents=True, exist_ok=True)
        self.temporary = tempfile.TemporaryDirectory(dir=scratch)
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name)

    def scan(self, denylist=None):
        args = ["check_public.py"]
        if denylist:
            path = self.root / "denylist.json"
            path.write_text(json.dumps(denylist))
            args += ["--denylist", str(path)]
        with (
            patch.object(check_public, "ROOT", self.root),
            patch("sys.argv", args),
            contextlib.redirect_stdout(io.StringIO()),
        ):
            status = check_public.main()
        return status, json.loads((self.root / "reports/public-content.json").read_text())

    def complete_audit_report(self):
        for name in (*release_evidence.LOCKS, *release_evidence.INPUTS):
            path = self.root / name
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(
                "package==1.2 --hash=sha256:" + "a" * 64 + "\n"
                if name in release_evidence.LOCKS
                else "package\n"
            )
        for name in ("_tools/audit_dependencies.py", "_tools/release_evidence.py"):
            path = self.root / name
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text("# Original verification implementation\n")
        return {
            "lock_sha256": release_evidence.hashes(self.root, release_evidence.LOCKS),
            "input_sha256": release_evidence.hashes(self.root, release_evidence.INPUTS),
            "verifier_sha256": release_evidence.hashes(self.root, release_evidence.AUDIT_VERIFIERS),
            "results": {
                name: {"registry_versions": 1, "advisories": [], "unknown": []}
                for name in (*release_evidence.LOCKS, "installed-environment")
            },
            "top_level_freshness": [
                {
                    "package": "package",
                    "locked": "1.2",
                    "latest_pypi": "1.2",
                    "matches_latest": True,
                }
            ],
        }

    def test_rejects_unreviewed_binary_and_symlink(self):
        (self.root / "image.png").write_bytes(b"not a reviewed synthetic image")
        (self.root / "link.json").symlink_to("image.png")
        status, result = self.scan()
        self.assertTrue(status)
        self.assertEqual(
            {x["kind"] for x in result["findings"]}, {"unreviewed_file_type", "symlink"}
        )
        with self.assertRaises(ValueError):
            checked_files(self.root)

    def test_public_identity_allowance_is_exact_and_document_scoped(self):
        address = "devin.bost" + "@" + "ibm.com"
        findings = []
        check_public.inspect_text(address, "MAINTAINERS.md", findings)
        self.assertEqual(findings, [])
        check_public.inspect_text(address, "customer-data.txt", findings)
        self.assertEqual(findings[-1]["kind"], "non_example_email")
        findings = []
        check_public.inspect_text("different-" + address, "MAINTAINERS.md", findings)
        self.assertEqual(findings[-1]["kind"], "non_example_email")

    def test_notebook_attachments_fail(self):
        notebook = nbformat.v4.new_notebook(cells=[nbformat.v4.new_markdown_cell("image")])
        notebook.cells[0]["attachments"] = {"image.png": {"image/png": "aGVsbG8="}}
        nbformat.write(notebook, self.root / "example.ipynb")
        status, result = self.scan()
        self.assertTrue(status)
        self.assertIn("unreviewed_notebook_attachment", {x["kind"] for x in result["findings"]})

    def test_decodes_private_text_and_scans_filenames(self):
        word = "PrivateFixtureOrganization"
        notebook = nbformat.v4.new_notebook(cells=[nbformat.v4.new_markdown_cell(word)])
        source = json.dumps(notebook).replace(
            word, "".join("\\u" + format(ord(c), "04x") for c in word)
        )
        (self.root / "example.ipynb").write_text(source)
        (self.root / (word + ".md")).write_text("fixture")
        status, result = self.scan([word])
        self.assertTrue(status)
        paths = {x["path"] for x in result["findings"] if x["kind"] == "source_specific_identifier"}
        self.assertIn("example.ipynb", paths)
        self.assertIn(word + ".md", paths)

    def test_distribution_does_not_copy_generated_or_environment_files(self):
        (self.root / "tutorial.py").write_text("print(1)")
        (self.root / ".whitesource").write_text('{"settingsInheritedFrom": "example/config@main"}')
        (self.root / ".python-version").write_text("3.12.16\n")
        for name in ["artifacts", ".venv", ".build"]:
            directory = self.root / name
            directory.mkdir()
            (directory / ".env").write_text("fixture")
        for name in ("SHA256SUMS.txt", "sha256sums.txt", "Sha256Sums.txt", "SHA256SUMS.TXT"):
            with self.subTest(manifest=name):
                manifest = self.root / name
                manifest.write_text("Generated by an extracted bundle\n")
                self.assertEqual(
                    {p.name for p in checked_files(self.root)},
                    {"tutorial.py", ".whitesource", ".python-version"},
                )
                manifest.unlink()

    def test_generated_manifest_directory_is_rejected(self):
        (self.root / "tutorial.py").write_text("print(1)")
        for name in ("SHA256SUMS.txt", "sha256sums.txt", "Sha256Sums.txt", "SHA256SUMS.TXT"):
            with self.subTest(manifest=name):
                directory = self.root / name
                directory.mkdir()
                child = directory / "fixture.txt"
                child.write_text("An actual directory would conflict with the generated file\n")
                with self.assertRaises(ValueError):
                    checked_files(self.root)
                child.unlink()
                directory.rmdir()

    def test_generated_manifest_symlink_is_rejected(self):
        (self.root / "tutorial.py").write_text("print(1)")
        (self.root / "target_directory").mkdir()
        for name in ("SHA256SUMS.txt", "sha256sums.txt", "Sha256Sums.txt", "SHA256SUMS.TXT"):
            for target in ("tutorial.py", "missing.txt", "target_directory"):
                with self.subTest(manifest=name, target=target):
                    manifest = self.root / name
                    manifest.symlink_to(target)
                    with self.assertRaises(ValueError):
                        checked_files(self.root)
                    manifest.unlink()

    def test_archive_round_trip_regenerates_one_valid_checksum_manifest(self):
        expected = {
            "README.md": b"Synthetic round-trip fixture\n",
            "examples/data.txt": b"Public example data\n",
            # Only the generated root manifest is excluded; tutorial data stays.
            "examples/SHA256SUMS.txt": b"An ordinary nested example fixture\n",
        }
        for name, content in expected.items():
            path = self.root / name
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(content)
        first = prepare_release.write_archive(self.root, checked_files(self.root))
        extracted = self.root / "extracted"
        with zipfile.ZipFile(first) as archive:
            archive.extractall(extracted)
        collection = extracted / "notebooks"
        self.assertTrue((collection / "SHA256SUMS.txt").is_file())
        second = prepare_release.write_archive(collection, checked_files(collection))
        for path in (first, second):
            with self.subTest(archive=path.name), zipfile.ZipFile(path) as archive:
                names = archive.namelist()
                self.assertEqual(len(names), len(set(names)))
                self.assertEqual(names.count("notebooks/SHA256SUMS.txt"), 1)
                self.assertEqual(
                    set(names),
                    {"notebooks/" + name for name in expected} | {"notebooks/SHA256SUMS.txt"},
                )
                manifest = archive.read("notebooks/SHA256SUMS.txt").decode()
                recorded = {
                    name: digest
                    for digest, name in (line.split("  ", 1) for line in manifest.splitlines())
                }
                self.assertEqual(set(recorded), set(expected))
                self.assertNotIn("SHA256SUMS.txt", recorded)
                for name, content in expected.items():
                    self.assertEqual(archive.read("notebooks/" + name), content)
                    self.assertEqual(
                        recorded[name],
                        hashlib.sha256(archive.read("notebooks/" + name)).hexdigest(),
                    )
                self.assertIsNone(archive.testzip())

    def test_archive_namespace_collisions_preserve_prior_target(self):
        tutorial = self.root / "tutorial.py"
        tutorial.write_text("print(1)\n")
        prior = prepare_release.write_archive(self.root, checked_files(self.root))
        prior_bytes = prior.read_bytes()
        alias = self.root / "Tutorial.PY"
        if not alias.exists():
            alias.write_text("print(2)\n")
        reserved = self.root / "sha256sums.txt"
        reserved.mkdir()
        child = reserved / "fixture.txt"
        child.write_text("A file/parent namespace collision\n")
        # Exercise the builder directly as well as the checked boundary: no
        # failed candidate may replace a previously verified archive.
        for files in ([tutorial, tutorial], [tutorial, alias], [tutorial, child]):
            with self.subTest(names=[path.relative_to(self.root).as_posix() for path in files]):
                with self.assertRaises(RuntimeError):
                    prepare_release.write_archive(self.root, files)
                self.assertEqual(prior.read_bytes(), prior_bytes)
                self.assertFalse((self.root / ".build/public-notebooks.staging.zip").exists())

    def test_lock_requires_exact_pins_and_hashes(self):
        path = self.root / "lock.txt"
        digest = "a" * 64
        for entry in [
            "package>=1",
            "-r extra.txt",
            "package @ https://example.invalid/a.whl",
            "package==1.*",
        ]:
            path.write_text(entry + " --hash=sha256:" + digest)
            with self.subTest(entry=entry), self.assertRaises(ValueError):
                audit_dependencies.locked_versions(path)
        path.write_text("package==1.2")
        with self.assertRaises(ValueError):
            audit_dependencies.locked_versions(path)
        path.write_text("package==1.2 \\\n --hash=sha256:" + digest + "\n")
        self.assertEqual(audit_dependencies.locked_versions(path), [("package", "1.2")])

    def test_advisory_response_requires_complete_package_inventory(self):
        packages = [("test-package", "1.2"), ("other-package", "3.4")]
        complete = {"dependencies": [{"name": n, "version": v, "vulns": []} for n, v in packages]}
        self.assertEqual(len(audit_dependencies.verify_audit_coverage(complete, packages)), 2)
        for rows in ([], complete["dependencies"][:1], complete["dependencies"] * 2):
            with self.subTest(rows=len(rows)), self.assertRaises(RuntimeError):
                audit_dependencies.verify_audit_coverage({"dependencies": rows}, packages)

    def test_advisory_rows_require_explicit_results(self):
        package = {"name": "synthetic-package", "version": "1.0"}
        for row in (package, {**package, "vulns": None}, {**package, "vulns": {}}):
            with self.subTest(row=row), self.assertRaises(RuntimeError):
                audit_dependencies.verify_audit_coverage(
                    {"dependencies": [row]}, [("synthetic-package", "1.0")]
                )

    def test_evidence_requires_exact_hash_coverage_and_current_inputs(self):
        (self.root / "runtime.txt").write_text("version-one")
        recorded = release_evidence.hashes(self.root, ["runtime.txt"])
        release_evidence.require_hashes(self.root, recorded, ["runtime.txt"])
        for invalid in ({}, {**recorded, "extra.txt": "unused"}):
            with self.assertRaises(RuntimeError):
                release_evidence.require_hashes(self.root, invalid, ["runtime.txt"])
        (self.root / "runtime.txt").write_text("version-two")
        with self.assertRaises(RuntimeError):
            release_evidence.require_hashes(self.root, recorded, ["runtime.txt"])

    def test_release_rejects_empty_or_partial_audit_cases(self):
        report = self.complete_audit_report()
        complete = report["results"]
        report["results"] = {}
        with self.assertRaises(RuntimeError):
            release_evidence.verify_audit(self.root, report)
        report["results"] = complete
        release_evidence.verify_audit(self.root, report)
        report["top_level_freshness"] = []
        with self.assertRaises(RuntimeError):
            release_evidence.verify_audit(self.root, report)

    def test_audit_verifier_changes_invalidate_clean_evidence(self):
        report = self.complete_audit_report()
        release_evidence.verify_audit(self.root, report)
        for name in ("_tools/audit_dependencies.py", "_tools/release_evidence.py"):
            path = self.root / name
            original = path.read_text()
            with self.subTest(verifier=name):
                path.write_text(original + "# Updated verification implementation\n")
                with self.assertRaises(RuntimeError):
                    release_evidence.verify_audit(self.root, report)
            path.write_text(original)
        for invalid in ({}, {**report["verifier_sha256"], "unexpected.py": "unused"}):
            with self.assertRaises(RuntimeError):
                release_evidence.verify_audit(self.root, {**report, "verifier_sha256": invalid})

    def test_execution_evidence_tracks_its_imported_lock_parser(self):
        self.complete_audit_report()
        for name in release_evidence.EXECUTION_INPUTS:
            path = self.root / name
            path.parent.mkdir(parents=True, exist_ok=True)
            if not path.exists():
                path.write_text("# Verification fixture\n")
        recorded = release_evidence.hashes(self.root, release_evidence.EXECUTION_INPUTS)
        path = self.root / "_tools/audit_dependencies.py"
        path.write_text(path.read_text() + "# Updated lock parser\n")
        with self.assertRaises(RuntimeError):
            release_evidence.require_hashes(self.root, recorded, release_evidence.EXECUTION_INPUTS)

    def test_optional_evidence_tracks_imported_verification_helpers(self):
        self.complete_audit_report()
        recorded = release_evidence.hashes(self.root, release_evidence.OPTIONAL_VERIFIERS)
        for name in ("_tools/audit_dependencies.py", "_tools/release_evidence.py"):
            path = self.root / name
            original = path.read_text()
            with self.subTest(verifier=name):
                path.write_text(original + "# Updated verification helper\n")
                with self.assertRaises(RuntimeError):
                    release_evidence.require_hashes(
                        self.root, recorded, release_evidence.OPTIONAL_VERIFIERS
                    )
            path.write_text(original)

    def test_installed_version_must_match_current_lock(self):
        path = self.root / "requirements.txt"
        path.write_text("package==1.2 --hash=sha256:" + "a" * 64 + "\n")
        with patch.object(release_evidence, "installed_versions", return_value={"package": "1.1"}):
            with self.assertRaises(RuntimeError):
                release_evidence.verify_installed_lock(self.root)
        with patch.object(release_evidence, "installed_versions", return_value={"package": "1.2"}):
            release_evidence.verify_installed_lock(self.root)


class KernelLifecycleTests(unittest.TestCase):
    def setUp(self):
        scratch = ROOT / ".build/gate-tests"
        scratch.mkdir(parents=True, exist_ok=True)
        self.temporary = tempfile.TemporaryDirectory(dir=scratch)
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name)

    def assert_kernel_stopped(self, code, expected_status):
        path = self.root / "examples/fixture.ipynb"
        path.parent.mkdir()
        nbformat.write(nbformat.v4.new_notebook(cells=[nbformat.v4.new_code_cell(code)]), path)
        work = self.root / "work"
        work.mkdir()
        managers, clients = [], []

        class ObservedKernelManager(validate.KernelManager):
            def __init__(self, *args, **kwargs):
                super().__init__(*args, **kwargs)
                managers.append(self)

            def start_kernel(self, *args, **kwargs):
                result = super().start_kernel(*args, **kwargs)
                self.observed_process = self.provisioner.process
                return result

        class ObservedNotebookClient(validate.NotebookClient):
            def __init__(self, *args, **kwargs):
                super().__init__(*args, **kwargs)
                clients.append(self)

        try:
            with (
                patch.object(validate, "ROOT", self.root),
                patch.object(validate, "KernelManager", ObservedKernelManager),
                patch.object(validate, "NotebookClient", ObservedNotebookClient),
            ):
                result = validate.run_one(path, work, self.root / "executed", [path])
            self.assertEqual(result["status"], expected_status)
            self.assertEqual(len(managers), 1)
            manager = managers[0]
            process = manager.observed_process
            self.assertGreater(process.pid, 0)
            self.assertFalse(manager.is_alive(), "Notebook completion left a live kernel")
            self.assertIsNotNone(process.poll(), "Kernel child process did not exit")
        finally:
            # Also release real resources when this regression detects a leak.
            for client in clients:
                if client.kc is not None:
                    client.kc.stop_channels()
            for manager in managers:
                if manager.has_kernel:
                    manager.shutdown_kernel(now=True)
                manager.cleanup_resources()

    def test_successful_notebook_releases_real_kernel_process(self):
        self.assert_kernel_stopped("assert 2 + 2 == 4", "passed")

    def test_failed_notebook_releases_real_kernel_process(self):
        self.assert_kernel_stopped('raise RuntimeError("Synthetic notebook failure")', "failed")


if __name__ == "__main__":
    unittest.main()
