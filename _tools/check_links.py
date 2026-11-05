# Copyright IBM Corp. 2026
# SPDX-License-Identifier: Apache-2.0
# Modified for open-source preparation on 2026-10-23.
# AI assistance: may include Anthropic Claude Opus 4+, Sonnet 3.7+, and
# OpenAI GPT-4+ model contributions; exact per-file provenance is unverified.
# See AI_DISCLOSURE.md and NOTICE.md at the collection root.

"""Check that relative documentation links stay inside this public collection."""

import json
import re
from pathlib import Path
from urllib.parse import unquote, urlsplit

from public_files import checked_files

ROOT = Path(__file__).resolve().parents[1]
LINK = re.compile(r"!?\[[^\]]*\]\(([^)]+)\)")


def main():
    failures = []
    for path in checked_files(ROOT):
        if path.suffix == ".md":
            texts = [path.read_text()]
        elif path.suffix == ".ipynb":
            texts = [
                "".join(c["source"])
                for c in json.loads(path.read_text())["cells"]
                if c["cell_type"] == "markdown"
            ]
        else:
            continue
        for text in texts:
            for match in LINK.finditer(text):
                href = match[1].strip().split(' "')[0].strip("<>")
                parsed = urlsplit(href)
                if parsed.scheme or not parsed.path:
                    continue
                target = (path.parent / unquote(parsed.path)).resolve()
                if (ROOT != target and ROOT not in target.parents) or not target.exists():
                    failures.append({"path": path.relative_to(ROOT).as_posix(), "href": href})
    (ROOT / "reports/links.json").write_text(
        json.dumps({"broken_relative_links": failures}, indent=2) + "\n"
    )
    print(f"Broken or escaping relative links: {len(failures)}")
    for item in failures:
        print(item)
    return bool(failures)


if __name__ == "__main__":
    raise SystemExit(main())
