# Mend scan handoff

## Current state

As of 2026-11-19, no Mend check or vulnerability issue is visible on the public publication PR. The presence of `.whitesource` does not establish that the app is installed, a scan ran, or the inventory is complete. The inherited IBM configuration is unchanged. The available GitHub credentials cannot enumerate app installations or read the inherited configuration repository, so installation and configuration coverage remain unverified.

The owner confirmed release/data approvals are complete. That confirmation and the public advisory audits do not replace the outstanding Mend evidence or maintainer reviews.

## Administrator actions

1. Confirm that IBM's approved Mend GitHub.com integration includes `IBM/Datastax-Vector-Search-demos`. An installation on `github.ibm.com` does not establish coverage for this separate GitHub.com repository.
2. Confirm the inherited `ibm-mend-config/mend-config@main` settings are accessible to the integration and include the intended Python manifests. Complete the approved onboarding flow if needed; do not merge the publication PR merely to make a scan run.
3. Scan the publication PR's latest commit, or use an approved CLI scan of that exact source if repository integration cannot scan it before merge. Record the commit, scan date, project identifier, result link and sanitized package inventory in the approved evidence system. Do not put credentials or internal support tokens in public evidence.
4. Compare the package-level export with [the expected inventory](reports/dependency-inventory.json). It includes the SHA-256 of each of the four locks and every pinned name/version, including platform alternatives. Verify each profile and relevant platform; do not infer coverage from only the runtime profile or a package count. Explain additional discovered components and any missing expected entries. This inventory is not itself an SBOM, a license review or scan evidence.
5. Resolve high/critical findings and errors, rerun on the corrected commit, and retain security and license-policy results. Inspect findings even if the configured check displays green; conclusion settings can affect that display. Confirm the intended required checks with the repository/organization owner rather than bypassing them.

Mend documents its onboarding, valid push triggers, result checks and configurable check conclusions in [Scan your open source components with Mend for GitHub.com](https://docs.mend.io/integrations/latest/scan-open-source-sca-with-mend-for-github). A dependency-file change is a valid trigger on an onboarded repository; this PR refreshes the dependency locks. If no Mend check appears, investigate onboarding/configuration with the integration administrator.

## Evidence still required

- Successful scan of the exact publication commit with no unresolved high/critical findings.
- Inventory coverage for runtime, development and both optional profiles, plus platform alternatives as applicable.
- Applicable dependency license-policy review and the supporting result references.
- Actual maintainer LGTMs under CONTRIBUTING.md. Do not record a proxy or automated approval as a human maintainer review.
