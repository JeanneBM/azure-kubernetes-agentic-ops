# Security scanning and vulnerability triage

The Security workflow runs on pull requests, pushes to main, weekly and manually.
It does not authenticate to Azure, publish images or deploy resources. Internet
access is required for packages and current vulnerability databases.

## Controls and thresholds

| Control | Tool | Failure condition |
| --- | --- | --- |
| Unit tests | pytest | Any failed test |
| Python SAST | Bandit | Medium/high severity AND medium/high confidence |
| Resolved dependencies, including transitive and dev tools | pip-audit | Any known vulnerability |
| Secrets in current checkout | Trivy | Any detected secret |
| Dockerfile and Kubernetes IaC | Trivy | High/critical misconfiguration |
| Built image OS and Python packages | Trivy | High/critical vulnerability, including unfixed |
| Inventory | Trivy CycloneDX | SBOM generation failure |

Scanner failures, missing dependencies and cancelled/skipped prerequisite jobs
fail the final Security gate. Reports are retained for 14 days as Actions artifacts,
even after failed scans. Secret matches are deliberately not uploaded or printed;
inspect suspected files locally, revoke exposed credentials and remove them.
The secret scan covers the current tree, not full Git history. No scanner proves
absence of vulnerabilities; authorization and agent policy need separate review.
Python dependencies currently use version ranges: each run records the resolved
inventory, but builds are not yet reproducible from a committed lockfile.
Dependabot proposes pip, Docker base-image and GitHub Actions updates.

## Required repository setting

A failed workflow alone DOES NOT block merging. After the first run, open
Settings > Rules > Rulesets and create/update the rule targeting main:

- Require a pull request before merging.
- Require status checks to pass: select **Security gate** from this workflow.
- Require the branch to be up to date before merging.
- Block force pushes and deletion; restrict bypasses deliberately.

Preserve existing protections. Check a deliberately failing PR cannot merge,
then fix it and verify the same check turns green. The connected integration
cannot administer branch protection; this setting must be completed by an owner.
Enable Dependabot alerts/security updates in Settings > Advanced Security where
available. Dependency update PRs still require review and passing checks.

## Triage process

1. Download artifacts from the exact workflow run and record its commit SHA.
2. Deduplicate by advisory/rule ID + component/version + affected location.
3. Validate the finding and affected runtime. Assess internet exposure, deployed
   version, privileges, reachability and business impact; do not infer that an
   installed dependency is necessarily reachable.
4. For CVEs, consult CVSS, FIRST EPSS and CISA KEV. KEV/active exploitation and
   reachable exposed components take priority over severity alone. These feeds
   are reviewed manually here; automated enrichment is not implemented.
5. Record a named owner, target date, decision and evidence in findings.csv.
   Suggested targets: actively exploited/exposed critical issues 24 hours,
   other high/critical issues 7 days; adjust explicitly to the actual risk.
6. Patch and rerun the same scans. Close as fixed only with passing-run evidence.
   Containment reduces exposure but does not mean the vulnerability is fixed.
   Risk acceptance needs an approver, justification, expiry and revisit date.
   This initial gate has no blanket exclusions or automated acceptance bypass.

Statuses: open, in-progress, fixed, contained, risk-accepted, false-positive.
Do not put secrets, customer data or exploit payloads in public tracking files.
There are no fabricated findings in the initial register.

## Demonstration and weekly reporting

Use a temporary branch and a harmless SAST fixture, e.g. a function calling
`subprocess.run(command, shell=True)` with a parameter. Confirm Bandit fails and
Security gate is red, replace it with an argument list and shell=False, and
confirm the finding disappears. Do not merge the unsafe fixture. For secrets,
use synthetic test fixtures locally only; never commit a real credential.
Record both run URLs and exact commits in the evidence log below.

| Finding | Before run / commit | Fix | After run / commit | Verified by |
| --- | --- | --- | --- | --- |

Weekly report: counts of open high/critical findings, overdue items, oldest item,
new versus fixed, expiring acceptances, scanner coverage and failed scans.
Report unique findings rather than adding scanner counts together. A green
scan is not a complete risk assessment. This project does not yet provide
DefectDojo aggregation, automated EPSS/KEV enrichment or enterprise-scale SLAs.
