# ADR 0002 — Trivy: Block Only Fixable Vulnerabilities

**Date:** 2026-10-25  
**Status:** Accepted  
**Author:** Maya Chen, CTO · HealthQueue

---

## Context

The first CI run after adding Trivy (commit `5e392b5`) failed the pipeline because Trivy reported 44 HIGH-severity CVEs in the `python:3.12-slim` base image. Investigation showed every one of those findings:

- Was in a Debian OS package (not a Python application dependency)
- Had status `affected` — Debian had acknowledged the vulnerability but had not yet released a patched version
- Had no available fix (`--ignore-unfixed` would exclude them)

The Python application packages (Flask 3.0.3, Werkzeug 3.0.3, gunicorn 22.0.0, prometheus-client 0.20.0, pytest 8.2.2) had zero CVEs.

With the default `ignore-unfixed: false` setting, every merge to `main` was blocked with no path to remediation except switching base images. The team could not ship the feature work that motivated the pipeline.

---

## Decision

Run **two** Trivy scans in CI job 2:

1. **Blocking scan** (`exit-code: "1"`, `ignore-unfixed: true`): fails the pipeline if any CRITICAL or HIGH CVE has a fix available. This is actionable — the team can upgrade a package or change the base image.

2. **Non-blocking full scan** (`exit-code: "0"`, all severities, unfixed included, `if: always()`): runs even when the blocking scan fails; writes `trivy-full-report.txt` and uploads it as a 30-day workflow artifact.

```yaml
- name: Scan with Trivy (block on fixable CRITICAL or HIGH)
  uses: aquasecurity/trivy-action@v0.36.0
  with:
    ignore-unfixed: true
    exit-code: "1"

- name: Scan with Trivy (full report — non-blocking)
  if: always()
  uses: aquasecurity/trivy-action@v0.36.0
  with:
    exit-code: "0"
    output: trivy-full-report.txt
```

---

## Alternatives Considered

| Alternative | Reason not chosen |
|---|---|
| **Block on all CVEs including unfixed** | No actionable remediation path for unfixed OS CVEs; permanently blocks all merges. |
| **Remove Trivy entirely** | Eliminates the security gate; any future fixable CVE introduced by a `pip upgrade` would ship undetected. |
| **Switch to `python:3.12-alpine`** | Alpine-based images have a different CVE surface; however, the Flask + gunicorn stack has known issues with Alpine's `musl` libc. This is tracked as a future investigation, not an immediate fix. |
| **Accept all HIGH CVEs as exceptions** | A manual exception list becomes stale as CVEs are patched; `ignore-unfixed` is self-updating (when Debian releases a fix, the CVE reappears in the blocking scan). |

---

## Consequences

**Positive:**
- The pipeline is unblocked while the team awaits upstream Debian patches.
- Fixable vulnerabilities — the ones the team can actually remediate — still block deploys.
- The full-report artifact keeps the unfixed CVEs visible for auditors and accepted-risk review without silently ignoring them.
- When Debian releases patches, `ignore-unfixed` will automatically surface them in the blocking scan.

**Negative / Trade-offs:**
- The 44 unfixed HIGH CVEs in the OS layer remain in production images until either the base image is updated or Debian publishes patches.
- Reviewers must distinguish "this failed because of a new fixable CVE" from "this failed because of something else" — the two-scan structure makes this explicit in the job output.

---

## Sources

- Trivy `--ignore-unfixed` documentation — <https://trivy.dev/latest/docs/scanner/vulnerability/#unfixed-vulnerabilities>
- NIST NVD CVE status definitions — <https://nvd.nist.gov/vuln/categories>
- Debian security tracker — <https://security-tracker.debian.org/tracker/>
