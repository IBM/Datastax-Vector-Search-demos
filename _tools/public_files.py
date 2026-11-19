# Copyright IBM Corp. 2026
# SPDX-License-Identifier: Apache-2.0
# Modified for open-source preparation on 2026-10-23.
# AI assistance: may include Anthropic Claude Opus 4+, Sonnet 3.7+, and
# OpenAI GPT-4+ model contributions; exact per-file provenance is unverified.
# See AI_DISCLOSURE.md and NOTICE.md at the collection root.

"""One explicit distribution boundary shared by checks, execution and packaging."""

import os
from pathlib import Path

EXCLUDED_DIRECTORIES = {
    ".build",
    ".venv",
    ".git",
    "__pycache__",
    ".ipynb_checkpoints",
    "artifacts",
    ".ruff_cache",
    ".pytest_cache",
    ".mypy_cache",
}
TEXT_SUFFIXES = {".ipynb", ".py", ".md", ".txt", ".json", ".yml", ".yaml", ".toml", ".in"}
TEXT_NAMES = {"LICENSE", ".gitignore", ".whitesource", ".python-version"}
# Reserve the generated manifest namespace on case-insensitive filesystems too.
GENERATED_TOP_LEVEL_FILES = {"sha256sums.txt"}


def public_files(root):
    """Yield distribution candidates, including forbidden links for rejection."""
    for base, directories, names in os.walk(root, followlinks=False):
        for name in directories:
            path = Path(base) / name
            if path.is_symlink():
                yield path
            elif Path(base) == root and name.casefold() in GENERATED_TOP_LEVEL_FILES:
                raise ValueError("A generated manifest path cannot be a directory")
        directories[:] = [
            name
            for name in directories
            if name not in EXCLUDED_DIRECTORIES and not (Path(base) / name).is_symlink()
        ]
        for name in names:
            path = Path(base) / name
            # Extracted bundles carry this generated manifest. Regenerate it
            # instead of copying it as a source file or hashing itself.
            if Path(base) == root and name.casefold() in GENERATED_TOP_LEVEL_FILES:
                if not path.is_symlink():
                    if not path.is_file():
                        raise ValueError("A generated manifest path must be a regular file")
                    continue
            yield path


def checked_files(root):
    paths = list(public_files(root))
    for path in paths:
        if path.is_symlink():
            raise ValueError("A public distribution candidate is a symbolic link")
        if path.suffix not in TEXT_SUFFIXES and path.name not in TEXT_NAMES:
            raise ValueError("A public distribution candidate has an unreviewed file type")
        if path.name.startswith(".env"):
            raise ValueError("Configuration credentials are not public distribution files")
    return paths
