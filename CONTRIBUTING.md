# Contributing

Keep each tutorial focused on a concrete learning outcome. Explain inputs, assumptions, expected outputs, failure cases, cleanup, and what the example does not prove. New datasets must be synthetic or have documented redistribution rights and a privacy review. Do not import operational files from outside the repository.

Before proposing a change, restart and execute the notebook from beginning to end, run `_tools/check_public.py`, `_tools/validate.py`, and `_tools/audit_dependencies.py`, and inspect generated plots/tables. Add meaningful assertions for important invariants and error behavior. Do not turn an error into a passing test by swallowing exceptions, silently substituting a mock, or dropping the behavior under test.

For dependencies, edit `_requirements/runtime.in` or `_requirements/dev.in`, then regenerate the hashed universal locks with a current `uv` release:

```sh
uv pip compile --python 3.12 --universal --generate-hashes --no-header _requirements/runtime.in -o requirements.txt
uv pip compile --python 3.12 --universal --generate-hashes --no-header _requirements/dev.in -c requirements.txt -o requirements-dev.txt
uv pip compile --python 3.12 --universal --generate-hashes --no-header _requirements/optional-services.in -c requirements.txt -o _requirements/optional-services.lock.txt
uv pip compile --python 3.12 --universal --generate-hashes --no-header _requirements/optional-retrieval.in -c requirements.txt -o _requirements/optional-retrieval.lock.txt
```

Recreate the environment from the new development lock, run the full checks, and compare API behavior. After installing both optional profiles in a separate environment, run `_tools/test_optional_contracts.py` and pass its interpreter to `_tools/audit_dependencies.py --extra-python <optional-python>`. Inspect generated lockfile comments for machine-specific paths before committing. A clean package audit does not scan every native runtime component; keep Python, TLS libraries, operating systems, and deployed images patched as well.

Provide live integration evidence only for calls you actually ran. Record the provider/model/version, sanitized input fixture, expected assertions, date, and cleanup outcome. Never commit actual credentials or private prompts/responses. Platform support requires a run on that platform, not merely a successful dependency resolution.

Source notebooks should have cleared outputs and no trusted-cell metadata. Use the executed copies under `.build/executed/` for local editorial inspection, then clear outputs in anything submitted publicly. Confirm the destination repository's license and required attribution before submitting a pull request.

Execution, contract and dependency-audit reports record hashes of the applicable locks and verifier source, including imported lock-parsing helpers. Changing an input invalidates its prior evidence; rerun checks before packaging. Dependency freshness covers direct runtime, development and optional packages, and advisory coverage must include the full package inventory. CI runs default notebook execution and a separate optional-contract job; the latter uses synthetic HTTP fixtures and needs no provider credentials.

## License, DCO and AI assistance

Submit source contributions under Apache License 2.0 and retain existing copyright, attribution and modification notices. Read the unmodified [Developer Certificate of Origin 1.1](DCO.txt). For every contribution, the person with the right to submit it must personally certify the DCO and add a `Signed-off-by: Your Name <your-address>` trailer, normally with `git commit -s`. Use your actual contribution identity. The trailer is a certification, not a claim that adding this document automatically certifies existing work. The initial public import uses a fresh signed-off commit; the internal development history is not imported. A separate attestation file does not replace a required commit trailer. Employer authorization and upstream rights still need to be established by the contributor.

Disclose AI assistance using [AI_DISCLOSURE.md](AI_DISCLOSURE.md), preserve file notices, and update [reports/ai-provenance.json](reports/ai-provenance.json) after source changes. Record exact providers/models only when known. AI-generated code must receive the same correctness, security, provenance and license review as other code; a DCO sign-off must come from a responsible human.

## Contribution workflow and review

Discuss substantial features in the [issue tracker](https://github.com/IBM/Datastax-Vector-Search-demos/issues) before implementation. Create a topic branch, keep changes focused, run the checks above, inspect generated results, and open a [pull request](https://github.com/IBM/Datastax-Vector-Search-demos/pulls). A fork is useful for external contributors; maintainers may use a topic branch in this repository. Do not push directly to main to bypass review. Include a `Signed-off-by` trailer matching your commit author identity on each authored commit, normally with `git commit -s`.

Follow the [Code of Conduct](CODE_OF_CONDUCT.md). Maintainer acceptance is expressed with LGTM reviews. The repository's review policy requires two maintainer LGTMs for each affected component. The initial publication must remain a draft until the required maintainer reviews and the open items in [PUBLICATION_STATUS.md](PUBLICATION_STATUS.md) are resolved. See [MAINTAINERS.md](MAINTAINERS.md) for the current responsible maintainers; public GitHub issues and PRs are the project discussion channels.

The code style is enforced by the repository's Ruff configuration. Preserve explicit failure behavior, synthetic-data provenance, source attribution and accessibility of text/tables/plots. Numerical assertions should use justified tolerances. Default tests must not require secrets, live providers, downloaded models or GPU hardware. Integration claims need separate sanitized live evidence.
