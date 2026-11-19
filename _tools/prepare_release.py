# Copyright IBM Corp. 2026
# SPDX-License-Identifier: Apache-2.0
# Modified for open-source preparation on 2026-10-23.
# AI assistance: may include Anthropic Claude Opus 4+, Sonnet 3.7+, and
# OpenAI GPT-4+ model contributions; exact per-file provenance is unverified.
# See AI_DISCLOSURE.md and NOTICE.md at the collection root.

"""Package verified public files; never follow links or include excluded state.

Run all checks first. This builds a local review artifact and never publishes it.
"""

import hashlib
import json
import subprocess
import sys
import zipfile
from datetime import datetime, timezone
from pathlib import Path, PurePosixPath

from public_files import checked_files
from release_evidence import (
    EXECUTION_INPUTS,
    OPTIONAL_INPUTS,
    OPTIONAL_NOTEBOOKS,
    OPTIONAL_VERIFIERS,
    require_hashes,
    verify_audit,
)

ROOT = Path(__file__).resolve().parents[1]


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def write_archive(root, files):
    """Build the archive after verification; checksum only distribution sources."""
    files = sorted(files)
    names = ["notebooks/" + path.relative_to(root).as_posix() for path in files]
    names.append("notebooks/SHA256SUMS.txt")
    folded_names = {name.casefold() for name in names}
    if len(names) != len(folded_names):
        raise RuntimeError("Archive contains duplicate or case-conflicting member names")
    if any(".." in PurePosixPath(name).parts or name.startswith("/") for name in names):
        raise RuntimeError("Unsafe archive path")
    if any(
        parent.as_posix().casefold() in folded_names
        for name in names
        for parent in PurePosixPath(name).parents
    ):
        raise RuntimeError("Archive contains file/directory namespace collisions")
    build = root / ".build"
    build.mkdir(exist_ok=True)
    target = build / "public-notebooks.zip"
    staging = build / "public-notebooks.staging.zip"
    hashes = []
    with zipfile.ZipFile(staging, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        for path in files:
            name = path.relative_to(root).as_posix()
            archive.write(path, "notebooks/" + name)
            hashes.append(f"{digest(path)}  {name}")
        archive.writestr("notebooks/SHA256SUMS.txt", "\n".join(hashes) + "\n")
    with zipfile.ZipFile(staging) as archive:
        if archive.namelist() != names:
            raise RuntimeError("Archive members differ from the verified distribution names")
        if archive.testzip() is not None:
            raise RuntimeError("Archive integrity check failed")
    staging.replace(target)
    return target


def main():
    for script in ["check_public.py", "check_links.py"]:
        subprocess.run([sys.executable, str(ROOT / "_tools" / script)], check=True)
    execution = json.loads((ROOT / "reports/execution.json").read_text())
    require_hashes(ROOT, execution.get("input_sha256"), EXECUTION_INPUTS)
    notebooks = {p.relative_to(ROOT).as_posix(): p for p in (ROOT / "examples").rglob("*.ipynb")}
    rows = execution["results"]
    if len(notebooks) != 29 or len(rows) != 29 or {r["path"] for r in rows} != set(notebooks):
        raise RuntimeError("Execution coverage does not exactly match all 29 tutorials")
    for row in rows:
        if row["status"] != "passed" or row["source_sha256"] != digest(notebooks[row["path"]]):
            raise RuntimeError("A tutorial changed or failed since its recorded execution")
    catalog = json.loads((ROOT / "publication.json").read_text())["notebooks"]
    catalog_hashes = {row["path"]: row["source_sha256"] for row in catalog}
    if len(catalog) != len(catalog_hashes):
        raise RuntimeError("Duplicate publication catalog entries")
    require_hashes(ROOT, catalog_hashes, notebooks)
    review_path = ROOT / "reports/review.json"
    if review_path.exists():
        review = json.loads(review_path.read_text())
        if (
            review.get("status") != "review_complete_verified"
            or review.get("unresolved_code_findings") != []
        ):
            raise RuntimeError("Additional review is incomplete")
        reviewed = review["notebooks"]
        reviewed_hashes = {row["path"]: row["source_sha256"] for row in reviewed}
        if len(reviewed) != len(reviewed_hashes):
            raise RuntimeError("Duplicate additional-review entries")
        require_hashes(ROOT, reviewed_hashes, notebooks)
    audit = json.loads((ROOT / "reports/dependency-audit.json").read_text())
    age = datetime.now(timezone.utc) - datetime.fromisoformat(audit["audited_at"])
    if age.total_seconds() > 86400 or age.total_seconds() < 0:
        raise RuntimeError("Dependency evidence must be from the past 24 hours")
    verify_audit(ROOT, audit)
    # Optional SDK evidence may be omitted when those profiles are not installed,
    # but stale evidence must never be distributed as current verification.
    optional_report = ROOT / "reports/optional-contracts.json"
    if optional_report.exists():
        optional = json.loads(optional_report.read_text())
        if optional["status"] != "passed":
            raise RuntimeError("Optional contract checks did not pass")
        if digest(ROOT / "_tools/test_optional_contracts.py") != optional["test_script_sha256"]:
            raise RuntimeError("Optional contract test script changed since verification")
        require_hashes(ROOT, optional.get("input_sha256"), OPTIONAL_INPUTS)
        require_hashes(ROOT, optional.get("verifier_sha256"), OPTIONAL_VERIFIERS)
        require_hashes(ROOT, optional.get("source_sha256"), OPTIONAL_NOTEBOOKS)
        for name, expected in optional["source_sha256"].items():
            if digest(ROOT / name) != expected:
                raise RuntimeError("Optional notebook changed since contract verification")
    files = checked_files(ROOT)
    target = write_archive(ROOT, files)
    print(
        f"Prepared local review archive: {target.name}; {len(files)} public files; SHA256 {digest(target)}"
    )


if __name__ == "__main__":
    main()
