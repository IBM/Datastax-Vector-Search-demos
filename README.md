# DataStax vector search demos

Reproducible Python notebooks for learning retrieval, reranking, agent evaluation, data preparation and quantum simulation. The examples use small synthetic fixtures and executable checks. They support exploration of techniques relevant to DataStax and watsonx.data vector search; the default workflows do not connect to a DataStax database or establish production product performance.

This initial publication is under review. [Publication status](PUBLICATION_STATUS.md) identifies approval, review and scan-coverage items that must be resolved before release.

## Start here

The collection has 29 tutorials: 10 [local data workflows](examples/local), 9 [science and retrieval examples](examples/science), and 10 [agent/service workflows](examples/services). The [tutorial catalog](publication.json) lists every notebook and its scope. Start with `examples/local/reproducible-environment/tutorial.ipynb`, then choose a topic. Quantum tutorials are a separate educational section rather than a claim of quantum-backed DataStax search.

Use a currently patched Python 3.12 distribution (3.12.16 or newer) and create an isolated environment from the repository root:

```sh
python3.12 -m venv .venv
source .venv/bin/activate
python -m pip install --require-hashes -r requirements-dev.txt
python -m jupyterlab
```

On Windows activate with `.venv\Scripts\Activate.ps1`. Select this environment's kernel and use **Restart Kernel and Run All Cells**. The notebooks do not install packages while running. `requirements.txt` is the smaller runtime/execution profile; the development lock also includes JupyterLab, lint and audit tools. Keep the interpreter, native libraries and operating system patched independently of Python package scans. Universal lock resolution alone does not verify every platform.

## Data and model boundaries

[DATA.md](DATA.md) describes the embedded and generated synthetic fixtures. There are no customer records, source prospect accounts, real personnel records, downloaded benchmark datasets, model weights or checkpoints. The examples are authored teaching cases, not evidence of deployment accuracy or representative benchmark quality. Some fixtures were prepared with AI assistance; exact historical model provenance is unverified. See [AI_DISCLOSURE.md](AI_DISCLOSURE.md).

Default workflows run locally without provider credentials, model downloads or hosted requests. Eighteen are standalone local tutorials, nine include an explicitly disabled optional provider/model branch, and two demonstrate preparation/validation before an operational handoff. Optional API/model behavior, licensing, costs, training, deployment and GPU/hardware need separate live verification.

## Optional integrations

For provider-backed examples, install `_requirements/optional-services.lock.txt`; for neural retrieval use `_requirements/optional-retrieval.lock.txt`. Both are complete hashed profiles constrained by the runtime. Read the chosen notebook before setting its opt-in flag. Supply credentials through an approved environment or secret manager; never paste them into cells, committed files or saved outputs. Use only synthetic inputs and resources you control. No external model weights are redistributed.

After installing both optional profiles in a separate environment, `python _tools/test_optional_contracts.py` exercises actual SDK/HTTP contracts against synthetic responses with external sockets denied. This verifies serialization, parsing and failure handling, not authentication or live service compatibility. Missing optional SDKs fail rather than silently skip coverage.

## Verify changes

```sh
python -m ruff check _tools examples
python -m ruff format --check _tools examples
python _tools/check_public.py
python _tools/check_links.py
python _tools/test_quality_gates.py
python _tools/validate.py
python _tools/audit_dependencies.py
```

The validator copies only reviewed public files into an isolated working directory, clears inherited credentials, uses an empty home directory, and starts a fresh kernel for each notebook. Its Python socket guard is a regression check, not an operating-system sandbox for untrusted code. Run only reviewed notebooks. Disposable executed copies are under `.build/executed/`; distributed source outputs stay clear. Input/verifier/source hashes bind the [execution](reports/execution.json), [optional-contract](reports/optional-contracts.json) and [dependency audit](reports/dependency-audit.json) evidence. Rerun checks after changes and immediately before release.

GitHub Actions runs local execution and optional contracts without provider secrets. Mend uses this public repository's IBM-managed configuration; a successful public advisory audit or a prior internal scan is not a substitute for full Mend inventory verification.

## Contribute and report issues

Read [CONTRIBUTING.md](CONTRIBUTING.md), [MAINTAINERS.md](MAINTAINERS.md), [CODE_OF_CONDUCT.md](CODE_OF_CONDUCT.md), and [SECURITY.md](SECURITY.md). Use [GitHub issues](https://github.com/IBM/Datastax-Vector-Search-demos/issues) for nonsensitive bugs and feature discussions. Do not post credentials, private prompts or vulnerability details publicly.

Source code is licensed under [Apache License 2.0](LICENSE). Owned sources carry IBM copyright/SPDX notices; third-party notices retain their own terms. See [NOTICE.md](NOTICE.md), [science attribution](examples/science/ATTRIBUTION.md), and [DCO.txt](DCO.txt). Each new contribution needs the responsible human's DCO sign-off; repository files do not replace commit certification.
