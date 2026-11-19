# Security policy

## Supported versions

No public version has been released. During initial review, maintainers evaluate fixes against the current main branch; no support commitment is made for the unrelated version numbers from the repository template. A version support policy must accompany the first release.

## Reporting a vulnerability

Follow [IBM's shared open-source security policy](https://github.com/IBM/.github/blob/main/SECURITY.md). Do not report vulnerabilities in public GitHub issues, discussions or pull requests.

IBM recommends private GitHub vulnerability reporting where available. The feature was disabled at initial inspection of this repository, so use the private reporting options provided by [IBM Security Vulnerability Management / PSIRT](https://www.ibm.com/support/pages/ibm-security-vulnerability-management) until a private GitHub reporting channel is enabled. Include the affected commit/version, impact, reproducible steps and any safe proof of concept. Do not include unrelated credentials or customer data.

The project follows IBM's coordinated reporting route; no project-specific response-time or disclosure-timeline promise is invented here.

## Handling data and credentials

Public examples must use synthetic data, explicit opt-in for live calls and approved environment/secret-manager credentials. Do not copy operational notebooks, customer/prospect data, configuration exports or private model outputs into this repository. Keep credentials out of cells, saved outputs, prompts, logs and commit history. If a key was exposed, revoke or rotate it with the provider and coordinate history remediation; deleting a value does not invalidate it.

Live endpoints require verified TLS, bounded timeouts, validated response contracts and managed client cleanup. Only execute reviewed source; the notebook validator's socket guard is not a security sandbox for arbitrary notebooks. Source outputs and attachments must remain clear unless separately reviewed.

## Verification

Run all checks in CONTRIBUTING.md before submitting changes. Public advisory scans and Mend must cover runtime, development and optional dependencies. Confirm inventory coverage and resolve critical/high findings rather than suppressing them. Maintain the interpreter, native libraries, operating system, model artifacts and deployed images separately. A clean scan is time-specific and does not prove absence of unknown vulnerabilities.
