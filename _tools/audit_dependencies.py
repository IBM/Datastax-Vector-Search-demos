# Copyright IBM Corp. 2026
# SPDX-License-Identifier: Apache-2.0
# Modified for open-source preparation on 2026-10-23.
# AI assistance: may include Anthropic Claude Opus 4+, Sonnet 3.7+, and
# OpenAI GPT-4+ model contributions; exact per-file provenance is unverified.
# See AI_DISCLOSURE.md and NOTICE.md at the collection root.

"""Audit every locked version (including platform alternatives) and this environment.

Requires requirements-dev.txt. Queries public PyPI advisory/package metadata.
No package is installed by this script and no advisory is ignored.
"""

import argparse
import hashlib
import importlib.metadata
import json
import re
import sqlite3
import ssl
import subprocess
import sys
import urllib.request
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
from pathlib import Path

from packaging.requirements import Requirement
from packaging.utils import canonicalize_name
from release_evidence import AUDIT_VERIFIERS, INPUTS, LOCKS, hashes

ROOT = Path(__file__).resolve().parents[1]


def read_locked_requirements(path):
    entries, pending = [], ""
    for raw in path.read_text().splitlines():
        line = raw.strip()
        if not line or line.startswith("#"):
            continue
        continuation = line.endswith("\\")
        pending += " " + (line[:-1] if continuation else line)
        if continuation:
            continue
        hashes = re.findall(r"--hash=sha256:[0-9a-f]{64}\b", pending)
        requirement = re.sub(r"--hash=sha256:[0-9a-f]{64}\b", "", pending).strip()
        if requirement.startswith("-") or not hashes:
            raise ValueError(f"{path.name}: only hashed exact registry pins are supported")
        parsed = Requirement(requirement)
        specs = list(parsed.specifier)
        if parsed.url or len(specs) != 1 or specs[0].operator != "==" or "*" in specs[0].version:
            raise ValueError(f"{path.name}: unpinned or non-registry dependency")
        entries.append(parsed)
        pending = ""
    if pending or not entries:
        raise ValueError(f"{path.name}: empty or incomplete lock")
    return entries


def locked_versions(path):
    return sorted(
        {
            (canonicalize_name(r.name), next(iter(r.specifier)).version)
            for r in read_locked_requirements(path)
        }
    )


def verify_audit_coverage(payload, packages):
    rows = payload.get("dependencies", [])
    expected = {(canonicalize_name(name), version) for name, version in packages}
    if not isinstance(rows, list):
        raise RuntimeError("Invalid advisory response package list")
    for row in rows:
        skipped = row.get("skip_reason")
        if skipped:
            if not isinstance(skipped, str):
                raise RuntimeError("Invalid skipped-package reason")
        elif "vulns" not in row or not isinstance(row["vulns"], list):
            raise RuntimeError("Package has no explicit vulnerability result")
    observed = [(canonicalize_name(row["name"]), row["version"]) for row in rows]
    if len(observed) != len(set(observed)) or set(observed) != expected:
        raise RuntimeError("Advisory response does not cover the requested package inventory")
    return rows


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--extra-python",
        action="append",
        default=[],
        help="Also audit an optional profile environment through its Python executable",
    )
    args = parser.parse_args()
    build = ROOT / ".build/audits"
    build.mkdir(parents=True, exist_ok=True)
    reports = ROOT / "reports"
    reports.mkdir(exist_ok=True)
    (reports / "dependency-audit.json").unlink(missing_ok=True)
    required = LOCKS
    for name in required:
        if not (ROOT / name).is_file():
            raise FileNotFoundError(f"Required lock missing: {name}")
    locks = [ROOT / name for name in LOCKS]
    lock_hashes = hashes(ROOT, LOCKS)
    input_hashes = hashes(ROOT, INPUTS)
    verifier_hashes = hashes(ROOT, AUDIT_VERIFIERS)
    cases = {str(p.relative_to(ROOT)): locked_versions(p) for p in locks}
    cases["installed-environment"] = sorted(
        {(d.metadata["Name"], d.version) for d in importlib.metadata.distributions()}
    )
    for index, executable in enumerate(args.extra_python):
        inventory = subprocess.run(
            [
                executable,
                "-c",
                "import importlib.metadata as m,json;print(json.dumps([(d.metadata['Name'],d.version) for d in m.distributions()]))",
            ],
            check=True,
            text=True,
            capture_output=True,
            timeout=30,
        )
        cases[f"optional-installed-environment-{index + 1}"] = sorted(
            set(map(tuple, json.loads(inventory.stdout)))
        )

    def audit(item):
        name, packages = item
        batches = []
        for package, version in packages:
            batch = next((b for b in batches if package.casefold() not in b), None)
            if batch is None:
                batch = {}
                batches.append(batch)
            batch[package.casefold()] = version
        issues, unknown = [], []
        for index, batch in enumerate(batches):
            label = re.sub(r"[^\w.-]", "-", name) + f"-{index}"
            inputs = build / (label + ".txt")
            output = build / (label + ".json")
            inputs.write_text("".join(f"{p}=={v}\n" for p, v in sorted(batch.items())))
            command = [
                sys.executable,
                "-m",
                "pip_audit",
                "-r",
                str(inputs),
                "--no-deps",
                "--disable-pip",
                "--strict",
                "--progress-spinner",
                "off",
                "--cache-dir",
                str(build / "cache"),
                "-f",
                "json",
                "-o",
                str(output),
            ]
            output.unlink(missing_ok=True)
            with (build / (label + ".log")).open("w") as log:
                result = subprocess.run(command, stdout=log, stderr=log, timeout=300)
            if not output.exists():
                raise RuntimeError(f"No audit result for {name}")
            rows = verify_audit_coverage(json.loads(output.read_text()), batch.items())
            for dependency in rows:
                if dependency.get("skip_reason"):
                    unknown.append(dependency)
                for issue in dependency.get("vulns", []):
                    issues.append(
                        {
                            "package": dependency["name"],
                            "version": dependency["version"],
                            "id": issue["id"],
                            "fix_versions": issue.get("fix_versions", []),
                        }
                    )
            if result.returncode and not issues and not unknown:
                raise RuntimeError(f"Audit failed without advisory output for {name}")
        return name, {"registry_versions": len(packages), "advisories": issues, "unknown": unknown}

    with ThreadPoolExecutor(max_workers=3) as pool:
        results = dict(pool.map(audit, cases.items()))
    latest = []
    direct = set()
    for name in INPUTS:
        for line in (ROOT / name).read_text().splitlines():
            line = line.strip()
            if line and not line.startswith(("#", "-")):
                direct.add(canonicalize_name(Requirement(line).name))
    resolved = {}
    for lock in locks:
        for requirement in read_locked_requirements(lock):
            if requirement.marker is None or requirement.marker.evaluate():
                name = canonicalize_name(requirement.name)
                version = next(iter(requirement.specifier)).version
                if name in resolved and resolved[name] != version:
                    raise RuntimeError(f"Profile version disagreement for {name}")
                resolved[name] = version
    for name in sorted(direct):
        with urllib.request.urlopen(f"https://pypi.org/pypi/{name}/json", timeout=30) as response:
            info = json.load(response)["info"]
        latest.append(
            {
                "package": name,
                "locked": resolved[name],
                "latest_pypi": info["version"],
                "matches_latest": resolved[name] == info["version"],
            }
        )
    report = {
        "audited_at": datetime.now(timezone.utc).isoformat(),
        "method": "pip-audit strict PyPI advisory lookup, all locked versions including alternative platforms, no ignored advisories",
        "results": results,
        "lock_sha256": lock_hashes,
        "input_sha256": input_hashes,
        "verifier_sha256": verifier_hashes,
        "top_level_freshness": latest,
        "runtime": {
            "python": sys.version.split()[0],
            "openssl": ssl.OPENSSL_VERSION,
            "sqlite": sqlite3.sqlite_version,
        },
        "limits": "Advisory databases and package versions do not prove absence of unknown vulnerabilities or cover every embedded native library. Live hosts and services require separate scans.",
    }
    if any(
        hashlib.sha256((ROOT / name).read_bytes()).hexdigest() != digest
        for name, digest in {**lock_hashes, **input_hashes, **verifier_hashes}.items()
    ):
        raise RuntimeError("A dependency or verifier input changed during its audit; rerun")
    (reports / "dependency-audit.json").write_text(json.dumps(report, indent=2) + "\n")
    failed = {k: v for k, v in results.items() if v["advisories"] or v["unknown"]}
    print(f"Audited {len(results)} locks/environments; failing audits: {len(failed)}")
    for name, data in failed.items():
        print(name, json.dumps(data))
    stale = [x for x in latest if not x["matches_latest"]]
    if stale:
        print("Compatibility/freshness review needed:", json.dumps(stale))
    return bool(failed or stale)


if __name__ == "__main__":
    raise SystemExit(main())
