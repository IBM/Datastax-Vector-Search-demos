# Copyright IBM Corp. 2026
# SPDX-License-Identifier: Apache-2.0
# Modified for open-source preparation on 2026-10-23.
# AI assistance: may include Anthropic Claude Opus 4+, Sonnet 3.7+, and
# OpenAI GPT-4+ model contributions; exact per-file provenance is unverified.
# See AI_DISCLOSURE.md and NOTICE.md at the collection root.

"""Validate the completeness and freshness of publication evidence."""

import hashlib
import importlib.metadata

from packaging.utils import canonicalize_name

LOCKS = (
    "requirements.txt",
    "requirements-dev.txt",
    "_requirements/optional-services.lock.txt",
    "_requirements/optional-retrieval.lock.txt",
)
INPUTS = (
    "_requirements/runtime.in",
    "_requirements/dev.in",
    "_requirements/optional-services.in",
    "_requirements/optional-retrieval.in",
)
AUDIT_VERIFIERS = (
    "_tools/audit_dependencies.py",
    "_tools/release_evidence.py",
)
EXECUTION_INPUTS = (
    "requirements.txt",
    "requirements-dev.txt",
    "_tools/validate.py",
    "_tools/public_files.py",
    "_tools/release_evidence.py",
    "_tools/audit_dependencies.py",
)

OPTIONAL_INPUTS = (
    "requirements.txt",
    "_requirements/optional-services.lock.txt",
    "_requirements/optional-retrieval.lock.txt",
)
OPTIONAL_VERIFIERS = (
    "_tools/release_evidence.py",
    "_tools/audit_dependencies.py",
)
OPTIONAL_NOTEBOOKS = (
    "examples/services/tool_agent_evaluation.ipynb",
    "examples/science/ensemble-retrieval/tutorial.ipynb",
    "examples/science/knowledge-graph/tutorial.ipynb",
    "examples/services/watsonx_orchestrate_evaluation.ipynb",
    "examples/services/watsonx_runtime_context.ipynb",
    "examples/services/workflow_agent_evaluation.ipynb",
    "examples/services/evaluation_experiments.ipynb",
)


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def hashes(root, names):
    return {name: digest(root / name) for name in names}


def require_hashes(root, recorded, expected):
    if not isinstance(recorded, dict) or set(recorded) != set(expected):
        raise RuntimeError("Evidence does not cover the exact required input files")
    if recorded != hashes(root, expected):
        raise RuntimeError("An input file changed after verification")


def installed_versions():
    return {
        canonicalize_name(d.metadata["Name"]): d.version for d in importlib.metadata.distributions()
    }


def verify_installed_lock(root, lock="requirements.txt"):
    from audit_dependencies import read_locked_requirements

    installed = installed_versions()
    for requirement in read_locked_requirements(root / lock):
        if requirement.marker is not None and not requirement.marker.evaluate():
            continue
        name = canonicalize_name(requirement.name)
        version = next(iter(requirement.specifier)).version
        if installed.get(name) != version:
            raise RuntimeError(f"Installed {name} does not match the tested lock")
    return installed


def verify_audit(root, audit):
    from audit_dependencies import locked_versions

    require_hashes(root, audit.get("verifier_sha256"), AUDIT_VERIFIERS)
    require_hashes(root, audit.get("lock_sha256"), LOCKS)
    require_hashes(root, audit.get("input_sha256"), INPUTS)
    results = audit.get("results", {})
    if not set(LOCKS).union({"installed-environment"}) <= set(results):
        raise RuntimeError("Dependency report is missing required audit cases")
    for name, result in results.items():
        if result.get("advisories") != [] or result.get("unknown") != []:
            raise RuntimeError("Dependency advisories or unknown packages remain")
        if not isinstance(result.get("registry_versions"), int) or result["registry_versions"] <= 0:
            raise RuntimeError("Dependency report has empty package coverage")
        if name in LOCKS and result["registry_versions"] != len(locked_versions(root / name)):
            raise RuntimeError("Dependency report package coverage differs from lock")
    freshness = audit.get("top_level_freshness", [])
    from packaging.requirements import Requirement

    expected = set()
    for name in INPUTS:
        for line in (root / name).read_text().splitlines():
            line = line.strip()
            if line and not line.startswith(("#", "-")):
                expected.add(canonicalize_name(Requirement(line).name))
    observed = [canonicalize_name(row["package"]) for row in freshness]
    if len(observed) != len(set(observed)) or set(observed) != expected:
        raise RuntimeError("Freshness evidence does not cover every direct dependency")
    for row in freshness:
        if not row.get("matches_latest") or row.get("locked") != row.get("latest_pypi"):
            raise RuntimeError("A direct dependency is not at the reviewed latest release")
