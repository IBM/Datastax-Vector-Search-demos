# Initial publication review status

This is an initial import for IBM/Datastax-Vector-Search-demos. The notebook content is prepared for public review; merge and release remain subject to the items below. Repository creation, DCO sign-off or passing tests do not replace IBM release approval.

## Maintainer and approval items

- Obtain the two maintainer LGTMs required by CONTRIBUTING.md. Devin Bost and Kiyu are listed at the owner's direction; their reviews have not yet been recorded.
- Security reporting follows IBM's shared PSIRT/private reporting policy. Conduct reports use Devin Bost's IBM address with the owner's authorization; verify these routes remain current at release.
- The project owner confirmed on 2026-11-04 that all required release/data approvals have been obtained. Approval documents and reference identifiers were not supplied in this chat and are not reproduced here; retain them in the approved internal system. This owner confirmation does not stand in for GitHub maintainer reviews or scan evidence.
- Verify public-repository DCO/Mend checks and required-check settings; the inherited configuration is retained rather than replaced with Enterprise-only settings.
- Verify Mend package-level inventory against all four locks, including optional and development packages and platform alternatives. A check summary alone does not establish coverage; retain sanitized evidence and fix critical/high findings before release.

## Local verification

Current source-bound results are in [execution](reports/execution.json), [SDK contracts](reports/optional-contracts.json), [dependency audit](reports/dependency-audit.json), [public-content review](reports/public-content.json), and [relative links](reports/links.json). On 2026-11-03, all 29 notebooks (125 code cells), 20 quality-gate tests and eight optional SDK contract tests passed locally on Python 3.12.16/macOS arm64. All four locks and both environments passed a fresh public advisory audit with zero advisories or unknown packages; all 26 direct dependencies matched current PyPI releases. Eleven synthetic plots/images were inspected. See the [publication review record](reports/publication-review.json). Rerun source-bound reports after any applicable input changes. [Publication metadata](publication.json) distinguishes local demonstrations from optional integrations and preparation-only handoffs.

Python numerical simulations, parsers and fixtures run locally. Optional live providers, local neural weights, GPU hardware, training, remote deployment and actual service resources are not validated by synthetic HTTP tests. Linux/Windows support requires actual runs on those platforms; universal dependency resolution alone is insufficient. GitHub Actions results for this PR provide their own platform evidence.

## Release artifacts

Do not include private operational originals, old development manifests, internal scan support tokens, private reports, model weights, local environments, caches or saved notebook outputs. A release archive must follow the reviewed distribution boundary and include only current evidence. Keep any generated package/SBOM inventory and license review associated with the exact release commit.
