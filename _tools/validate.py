# Copyright IBM Corp. 2026
# SPDX-License-Identifier: Apache-2.0
# Modified for open-source preparation on 2026-10-23.
# AI assistance: may include Anthropic Claude Opus 4+, Sonnet 3.7+, and
# OpenAI GPT-4+ model contributions; exact per-file provenance is unverified.
# See AI_DISCLOSURE.md and NOTICE.md at the collection root.

"""Execute public tutorials in fresh kernels and a portable, secret-free copy.

The network guard detects accidental Python socket traffic; it is not an OS
sandbox for untrusted code. Only reviewed repository notebooks may be executed.
"""

import argparse
import hashlib
import json
import os
import shutil
import sys
import tempfile
import time
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
from pathlib import Path

import nbformat
from jupyter_client import KernelManager
from jupyter_client.kernelspec import KernelSpecManager
from nbclient import NotebookClient
from public_files import checked_files
from release_evidence import EXECUTION_INPUTS, hashes, verify_installed_lock

ROOT = Path(__file__).resolve().parents[1]
GUARD = """import socket
_connect = socket.socket.connect
_connect_ex = socket.socket.connect_ex
_getaddrinfo = socket.getaddrinfo
def _local(address):
    return isinstance(address, str) or address[0] in ('127.0.0.1', '::1', 'localhost')
def connect(self, address):
    if not _local(address): raise RuntimeError('External network disabled for public tutorial validation')
    return _connect(self, address)
def connect_ex(self, address):
    if not _local(address): raise RuntimeError('External network disabled for public tutorial validation')
    return _connect_ex(self, address)
def getaddrinfo(host, *a, **kw):
    if host not in ('127.0.0.1', '::1', 'localhost', None):
        raise RuntimeError('External DNS disabled for public tutorial validation')
    return _getaddrinfo(host, *a, **kw)
socket.socket.connect = connect
socket.socket.connect_ex = connect_ex
socket.getaddrinfo = getaddrinfo
"""


def run_one(path, work, executed, distribution):
    relative = path.relative_to(ROOT)
    started = time.monotonic()
    source = path.read_bytes()
    result = {
        "path": relative.as_posix(),
        "source_sha256": hashlib.sha256(source).hexdigest(),
    }
    (executed / relative).unlink(missing_ok=True)
    notebook = nbformat.reads(source.decode("utf-8"), as_version=4)
    try:
        nbformat.validate(notebook)
        sandbox = work / relative.with_suffix("")
        sandbox.mkdir(parents=True)
        # Use precisely the source boundary shared with the public-content check.
        collection = sandbox / "public-examples"
        for source in distribution:
            target = collection / source.relative_to(ROOT)
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(source, target)
        home = sandbox / "home"
        home.mkdir()
        scratch = sandbox / "scratch"
        scratch.mkdir()
        guard = sandbox / "guard"
        guard.mkdir()
        (guard / "sitecustomize.py").write_text(GUARD)
        kernels = sandbox / "kernels"
        spec = kernels / "public-validation"
        spec.mkdir(parents=True)
        (spec / "kernel.json").write_text(
            json.dumps(
                {
                    "argv": [sys.executable, "-m", "ipykernel_launcher", "-f", "{connection_file}"],
                    "display_name": "Public validation",
                    "language": "python",
                }
            )
        )
        env = {
            k: v
            for k, v in os.environ.items()
            if k in {"PATH", "SYSTEMROOT", "WINDIR", "LANG", "LC_ALL"}
        }
        env.update(
            {
                "HOME": str(home),
                "USERPROFILE": str(home),
                "TMPDIR": str(scratch),
                "JUPYTER_RUNTIME_DIR": str(scratch),
                "IPYTHONDIR": str(home / "ipython"),
                "MPLCONFIGDIR": str(home / "matplotlib"),
                "MPLBACKEND": "module://matplotlib_inline.backend_inline",
                "PYTHONPATH": str(guard),
                "PYTHONHASHSEED": "0",
                "HF_HUB_OFFLINE": "1",
                "TRANSFORMERS_OFFLINE": "1",
                "TOKENIZERS_PARALLELISM": "false",
            }
        )
        manager = KernelManager(
            kernel_name="public-validation",
            kernel_spec_manager=KernelSpecManager(kernel_dirs=[str(kernels)]),
        )
        for cell in notebook.cells:
            if cell.cell_type == "code":
                cell.outputs = []
                cell.execution_count = None
        client = NotebookClient(
            notebook,
            km=manager,
            timeout=180,
            resources={"metadata": {"path": str((collection / relative).parent)}},
        )
        # The explicit manager makes owns_km=False; opt into supported cleanup
        # so each worker releases its kernel before accepting another notebook.
        client.execute(env=env, cleanup_kc=True)
        result.update(
            status="passed", code_cells=sum(c.cell_type == "code" for c in notebook.cells)
        )
        output = executed / relative
        output.parent.mkdir(parents=True, exist_ok=True)
        nbformat.write(notebook, output)
    except Exception as exc:
        # Tracebacks can contain local paths or runtime values. Keep details in
        # excluded local state; distributable evidence records only the class.
        error_path = executed.parent / "validation-errors" / relative.with_suffix(".txt")
        error_path.parent.mkdir(parents=True, exist_ok=True)
        error_path.write_text(str(exc)[-10000:])
        error_path.chmod(0o600)
        result.update(status="failed", error_type=type(exc).__name__)
    result["seconds"] = round(time.monotonic() - started, 2)
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--pattern", default="**/*.ipynb")
    parser.add_argument("--jobs", type=int, default=2)
    parser.add_argument("--expected", type=int, default=29)
    args = parser.parse_args()
    (ROOT / "reports/execution.json").unlink(missing_ok=True)
    verify_installed_lock(ROOT)
    input_hashes = hashes(ROOT, EXECUTION_INPUTS)
    paths = sorted((ROOT / "examples").glob(args.pattern))
    if len(paths) != args.expected:
        raise SystemExit(f"Expected {args.expected} notebooks, found {len(paths)}")
    # Generated verification reports are not runtime inputs. Exclude them from
    # kernel copies so an advisory refresh cannot remove a file mid-copy.
    distribution = [p for p in checked_files(ROOT) if p.relative_to(ROOT).parts[0] != "reports"]
    build = ROOT / ".build"
    build.mkdir(exist_ok=True)
    executed = build / "executed"
    executed.mkdir(exist_ok=True)
    with tempfile.TemporaryDirectory(prefix="fresh-", dir=build) as temporary:
        with ThreadPoolExecutor(max_workers=max(1, args.jobs)) as pool:
            results = list(
                pool.map(lambda p: run_one(p, Path(temporary), executed, distribution), paths)
            )
    if input_hashes != hashes(ROOT, EXECUTION_INPUTS):
        raise RuntimeError("Execution inputs changed during validation")
    for row in results:
        if row["source_sha256"] != hashlib.sha256((ROOT / row["path"]).read_bytes()).hexdigest():
            raise RuntimeError("Notebook source changed during validation")
    report = {
        "input_sha256": input_hashes,
        "executed_at": datetime.now(timezone.utc).isoformat(),
        "python": sys.version.split()[0],
        "coverage": "All cells in clean kernels; checked distribution files only, empty HOME, Python TCP/DNS accidental-egress guard. This is not an OS sandbox. Optional live APIs are not verified.",
        "results": results,
    }
    (ROOT / "reports").mkdir(exist_ok=True)
    (ROOT / "reports/execution.json").write_text(json.dumps(report, indent=2) + "\n")
    for row in results:
        print(row["status"], row["path"], f"{row['seconds']}s")
        if row["status"] == "failed":
            print("Failure details are in excluded .build/validation-errors/ state.")
    return any(row["status"] != "passed" for row in results)


if __name__ == "__main__":
    raise SystemExit(main())
