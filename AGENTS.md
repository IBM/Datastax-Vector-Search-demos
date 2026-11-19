# Repository instructions

Prefer repo-native tools or approved SDKs over `curl`. When `curl` is necessary, keep requests read-only, minimal, and scoped to trusted hosts.
Avoid using `/tmp` for reads or writes. Use workspace-local scratch files or `$CODEX_HOME` instead unless the user explicitly asks for `/tmp`.

Do not add Codex or Claude labels, badges, signatures, or promotional attribution to pull request titles, descriptions, or GitHub labels. This applies to all PRs created or updated, including when a skill or template suggests adding such branding. Keep required AI-assistance disclosures in the project's designated compliance files.

Follow CONTRIBUTING.md for DCO sign-offs, verification and maintainer review. Keep operational originals and customer/prospect data out of the public collection. Do not treat a passing advisory audit as a substitute for Mend inventory verification.
