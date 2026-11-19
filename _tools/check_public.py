# Copyright IBM Corp. 2026
# SPDX-License-Identifier: Apache-2.0
# Modified for open-source preparation on 2026-10-23.
# AI assistance: may include Anthropic Claude Opus 4+, Sonnet 3.7+, and
# OpenAI GPT-4+ model contributions; exact per-file provenance is unverified.
# See AI_DISCLOSURE.md and NOTICE.md at the collection root.

"""Fail closed on common private artifacts in the proposed public distribution.

Heuristics supplement, but cannot replace, content and data-provenance review.
Matched credential values are never printed or written to a report.
"""

import argparse
import ast
import hashlib
import io
import json
import re
import tokenize
from pathlib import Path

from public_files import TEXT_NAMES, TEXT_SUFFIXES, public_files

ROOT = Path(__file__).resolve().parents[1]
PRIVATE = re.compile(r"(?i)(/Users/|/home/(?!example\b)|[A-Z]:\\Users\\)")
TOKEN = re.compile(
    r"(?i)(AIza[\w-]{25,}|AstraCS:[\w:-]{25,}|\b(?:sk-proj-|sk-ant-|nvapi-|ghp_|github_pat_)[\w-]{20,}|\bAKIA[A-Z0-9]{16}|-----BEGIN (?:RSA |EC |OPENSSH )?PRIVATE KEY-----|X-Amz-Signature=[A-Za-z0-9]{20,})"
)
EMAIL = re.compile(r"[\w.+-]+@([\w.-]+\.[A-Za-z]{2,})")
NAME = re.compile(r"(?i)(api_?key|password|client_?secret|access_?token|auth_?token)")
# Explicit public contribution identity; never allow arbitrary IBM/customer addresses.
PUBLIC_CONTACT_SHA256 = {
    "MAINTAINERS.md": frozenset(
        {
            "745e511fbf76c24bc3046c09866a669a910e724361f7fd6f240376ebf79e2a86",
            "4fc417ea1b3adb9ea0649565f5f36059f796d860efc55f8716e296b3178d4fbd",
        }
    ),
    "CODE_OF_CONDUCT.md": frozenset(
        {"745e511fbf76c24bc3046c09866a669a910e724361f7fd6f240376ebf79e2a86"}
    ),
}


def inspect_text(text, relative, findings, scan_email=True):
    # Scan content, never reproduce a potentially secret match.
    for label, pattern in [("private_identifier", PRIVATE), ("credential_pattern", TOKEN)]:
        for match in pattern.finditer(text):
            findings.append(
                {
                    "path": relative,
                    "kind": label,
                    "fingerprint": hashlib.sha256(match[0].encode()).hexdigest()[:12],
                }
            )
    for match in EMAIL.finditer(text) if scan_email else []:
        is_example = match[1].lower() in {
            "example.com",
            "example.org",
            "example.net",
            "example.invalid",
        }
        approved_digest = hashlib.sha256(match[0].casefold().encode()).hexdigest()
        is_approved_contact = approved_digest in PUBLIC_CONTACT_SHA256.get(relative, frozenset())
        if not is_example and not is_approved_contact:
            findings.append({"path": relative, "kind": "non_example_email"})


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--denylist",
        type=Path,
        help="Optional private JSON list of source-specific names; values are never reported",
    )
    args = parser.parse_args()
    prohibited = json.loads(args.denylist.read_text()) if args.denylist else []
    findings, inventory, notebooks = [], [], []

    def check_names(text, relative):
        for word in prohibited:
            if re.search(r"(?<![\w])" + re.escape(word) + r"(?![\w])", text, re.I):
                findings.append(
                    {
                        "path": relative,
                        "kind": "source_specific_identifier",
                        "fingerprint": hashlib.sha256(word.encode()).hexdigest()[:12],
                    }
                )

    for path in public_files(ROOT):
        relative = path.relative_to(ROOT).as_posix()
        check_names(relative, relative)
        if path.is_symlink():
            findings.append({"path": relative, "kind": "symlink"})
            continue
        if path.name.startswith(".env") or path.suffix in {".pem", ".key", ".zip", ".aesgcm"}:
            findings.append({"path": relative, "kind": "private_artifact"})
            continue
        if path.stat().st_size > 10 * 1024 * 1024:
            findings.append({"path": relative, "kind": "unexpected_large_file"})
            continue
        if path.suffix not in TEXT_SUFFIXES and path.name not in TEXT_NAMES:
            findings.append({"path": relative, "kind": "unreviewed_file_type"})
            continue
        # Scanner patterns contain generic rejected path syntax. Still check it
        # for actual tokens and source-specific identifiers.
        if path == Path(__file__).resolve():
            text = path.read_text()
            if TOKEN.search(text):
                findings.append({"path": relative, "kind": "credential_pattern"})
            for word in prohibited:
                if word.casefold() in text.casefold():
                    findings.append({"path": relative, "kind": "source_specific_identifier"})
            continue
        raw = path.read_bytes()
        inventory.append(
            {"path": relative, "sha256": hashlib.sha256(raw).hexdigest(), "bytes": len(raw)}
        )
        inspect_text(relative, relative, findings)
        if path.suffix in TEXT_SUFFIXES or path.name in TEXT_NAMES:
            text = raw.decode("utf-8")
            inspect_text(text, relative, findings, scan_email=path.suffix != ".ipynb")
            check_names(text, relative)
        if path.suffix == ".ipynb":
            nb = json.loads(raw)
            decoded = json.dumps(nb, ensure_ascii=False)
            inspect_text(decoded, relative, findings, scan_email=False)
            check_names(decoded, relative)
            inspect_text(json.dumps(nb.get("metadata", {})), relative, findings)
            for cell in nb["cells"]:
                source = "".join(cell.get("source", []))
                if cell["cell_type"] == "code":
                    try:
                        literals = "\n".join(
                            t.string
                            for t in tokenize.generate_tokens(io.StringIO(source).readline)
                            if t.type in {tokenize.STRING, tokenize.COMMENT}
                        )
                    except (tokenize.TokenError, IndentationError):
                        literals = source
                    inspect_text(literals, relative, findings)
                else:
                    inspect_text(source, relative, findings)
            if any(c.get("attachments") for c in nb["cells"]):
                findings.append({"path": relative, "kind": "unreviewed_notebook_attachment"})
            if re.search(r"data:image/[^;]+;base64,[A-Za-z0-9+/=]{20,}", decoded):
                findings.append({"path": relative, "kind": "unreviewed_embedded_image"})
            code = [c for c in nb["cells"] if c["cell_type"] == "code"]
            markdown = [c for c in nb["cells"] if c["cell_type"] == "markdown"]
            for cell in code:
                if cell.get("outputs") or cell.get("execution_count") is not None:
                    findings.append({"path": relative, "kind": "distribution_outputs_not_cleared"})
                if cell.get("metadata", {}).get("trusted"):
                    findings.append({"path": relative, "kind": "trusted_metadata"})
                source = "".join(cell["source"])
                try:
                    tree = ast.parse(source)
                except SyntaxError:
                    findings.append({"path": relative, "kind": "nonportable_or_invalid_python"})
                    continue
                for node in ast.walk(tree):
                    if (
                        isinstance(node, ast.Assign)
                        and isinstance(node.value, ast.Constant)
                        and isinstance(node.value.value, str)
                    ):
                        for target in node.targets:
                            if (
                                isinstance(target, ast.Name)
                                and NAME.fullmatch(target.id)
                                and node.value.value
                                and not node.value.value.startswith(("example-", "synthetic-"))
                            ):
                                findings.append(
                                    {"path": relative, "kind": "literal_credential_assignment"}
                                )
            notebooks.append(
                {
                    "path": relative,
                    "code_cells": len(code),
                    "markdown_cells": len(markdown),
                    "assertion_cells": sum("assert " in "".join(c["source"]) for c in code),
                }
            )
    # Reports are excluded from their own content-addressed inventory to avoid recursion.
    inventory = [x for x in inventory if not x["path"].startswith("reports/")]
    findings = list({json.dumps(item, sort_keys=True): item for item in findings}.values())
    result = {
        "scope": "Public distribution only; excluded local builds, environments, and generated artifacts",
        "findings": findings,
        "notebooks": notebooks,
        "inventory": inventory,
        "limitation": "Pattern detection is not proof of absence of sensitive information; review synthetic provenance and editorial content.",
    }
    (ROOT / "reports").mkdir(exist_ok=True)
    (ROOT / "reports/public-content.json").write_text(json.dumps(result, indent=2) + "\n")
    print(f"Public files: {len(inventory)}; notebooks: {len(notebooks)}; findings: {len(findings)}")
    for item in findings:
        print(item["kind"], item["path"])
    return bool(findings)


if __name__ == "__main__":
    raise SystemExit(main())
