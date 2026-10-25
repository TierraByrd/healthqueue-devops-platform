# Supply-Chain Security — HealthQueue

**Author:** Maya Chen, CTO · HealthQueue  
**Pipeline commit ref:** `aa90b49` (latest successful CI build on `main`)

---

## 1. SLSA Compliance Map

[SLSA](https://slsa.dev) (Supply-chain Levels for Software Artifacts) defines four levels of build integrity assurance. The HealthQueue pipeline currently meets **SLSA Build Level 2**.

### Level 1 — Scripted Build ✅ Met

| Requirement | How it is satisfied |
|---|---|
| Build process is fully scripted | GitHub Actions workflow (`.github/workflows/ci-cd.yml`) drives every step from checkout through Cosign attestation. No manual build steps exist. |
| Build provenance is available | `actions/attest-build-provenance@v4.2.2` generates a SLSA Build Level 2 provenance statement and uploads it to the GitHub attestation store. |

### Level 2 — Build Service ✅ Met

| Requirement | How it is satisfied |
|---|---|
| Builds run on a hosted build service | All jobs run on `ubuntu-latest` GitHub-hosted runners. No self-hosted or developer-machine builds are in the pipeline. |
| Provenance is authenticated | The provenance statement is signed by GitHub's OIDC-based Sigstore Fulcio CA, bound to this repository's workflow identity. |
| Provenance can be verified | `gh attestation verify` against the image digest confirms the signature chain. Example: `gh attestation verify oci://index.docker.io/tierrab/healthqueue-platform:aa90b49 --repo TierraByrd/TierraB-Week8CareerPortfolio` |

**Verification output (reference):**
```
Loaded digest: sha256:<digest>
Verified 1 attestation(s) against the repository policy.
  * Subject: index.docker.io/tierrab/healthqueue-platform@sha256:<digest>
  * Predicate type: https://slsa.dev/provenance/v1
```

### Level 3 — Hardened Builds — Gaps

SLSA Level 3 requires the build environment itself to be hardened and reproducible. The following gaps currently prevent Level 3:

| Requirement | Current state | Gap |
|---|---|---|
| **Hermetic builds** | The Docker build fetches `python:3.12-slim` from Docker Hub at build time; `pip install` downloads packages from PyPI. | Build inputs are not fully pinned by digest; a compromised upstream package or base image could silently alter the artifact. |
| **Reproducible builds** | Two builds from the same commit SHA produce functionally equivalent images but not bit-for-bit identical ones (Python `.pyc` timestamps differ). | Build is not provably reproducible; an attacker with runner access could substitute a malicious artifact. |
| **Isolated build environment** | GitHub Actions runners are ephemeral and re-provisioned per job, providing good isolation. However, there is no network egress control. | Unrestricted outbound network access during the build step means a compromised dependency could exfiltrate secrets or pull additional payloads. |
| **Two-party review of build configuration** | CI workflow changes require only one approver. | SLSA L3 expects the build configuration itself to be protected by at least two-person review or a separate CODEOWNERS-enforced policy. |

**Path to Level 3:** Pin `FROM python:3.12-slim` by digest in the Dockerfile; use `pip install --require-hashes` with a locked `requirements.txt`; add a GitHub branch protection rule requiring two reviewers for changes to `.github/workflows/`.

---

## 2. Vulnerability Scanning — Trivy

**Tool:** `aquasecurity/trivy-action@v0.36.0`  
**Scope:** OS packages and Python libraries in the final image (`tierrab/healthqueue-platform:aa90b49`)

### Blocking vs. Non-Blocking Strategy

The pipeline runs two Trivy scans:

**Scan 1 — blocking gate:** CRITICAL and HIGH, fixable only (`ignore-unfixed: true`). Exits non-zero if any fixable CVE is found.

**Scan 2 — full audit (non-blocking):** All severities, unfixed included. Output is saved to `trivy-full-report.txt` and uploaded as a workflow artifact (`retention-days: 30`).

### Why `ignore-unfixed: true`

The first CI run (commit `5e392b5`) produced 44 HIGH CVEs in Debian OS packages bundled with `python:3.12-slim`. Every one of those findings had status `affected` with no patched version available from Debian. Blocking on unfixed vulnerabilities would have made all merges impossible with no actionable remediation path — the only option is switching base images, not patching individual packages. Meanwhile, the Python application dependencies (Flask, Werkzeug, gunicorn, prometheus-client, pytest) were clean.

The decision: **block only on fixable CVEs**. This ensures the pipeline will catch vulnerabilities that can actually be remediated while not creating permanent pipeline gridlock for upstream OS findings. The full report artifact provides accepted-risk visibility for auditors.

---

## 3. Software Bill of Materials — Syft

**Tool:** `anchore/sbom-action@v0.24.3`  
**Format:** SPDX JSON (`healthqueue-sbom.spdx.json`)

The SBOM is generated from the built container image (not the source tree) and:
1. Uploaded as a GitHub Actions workflow artifact for 30 days.
2. Attached to the image digest as a Cosign in-toto attestation (see Section 4).

The SBOM lists every package in the image layer — OS packages from Debian slim and Python packages from the virtualenv — enabling downstream consumers (auditors, dependency scanners) to verify the image's exact composition without pulling it.

---

## 4. Image Signing — Cosign Keyless

**Tool:** `sigstore/cosign-installer@v4.1.2`  
**Method:** Keyless signing via GitHub OIDC (Sigstore Fulcio + Rekor)

### Signing Process

1. The runner presents its GitHub OIDC token to Sigstore Fulcio.
2. Fulcio issues a short-lived X.509 certificate bound to the workflow identity (`repo:TierraByrd/TierraB-Week8CareerPortfolio:ref:refs/heads/main`).
3. Cosign signs the image **by digest** (not by tag) and records the signature in the Rekor transparency log.
4. The SBOM is attached as a separate Cosign attestation on the same digest.

### Why by Digest, Not by Tag

Tags are mutable. `tierrab/healthqueue-platform:aa90b49` could be overwritten by another `docker push` command. Signing by digest (`sha256:...`) pins the signature to the exact immutable byte sequence of the image. The signature is meaningless if the image bytes change — this is the guarantee.

### No Long-Lived Secrets

There is no signing private key stored in GitHub Secrets or anywhere else. The ephemeral Fulcio certificate expires after 10 minutes. The only persistent artifact is the Rekor transparency log entry, which is public and tamper-evident.

---

## 5. Pinned Action Versions

All GitHub Actions are pinned to exact semantic versions (e.g., `actions/checkout@v7.0.1`), not to floating tags like `@v7` or `@main`. Floating tags can be silently updated by the action author to inject malicious code.

Pinning to a semver release tag is a best-practice compromise: it is human-readable (unlike a full SHA pin) and covers the common supply-chain threat of a compromised action publisher silently backdating a major/minor tag. A full SHA pin (e.g., `actions/checkout@11bd71901bbe5b1630ceea73d27597364c9af683`) would be more rigorous and is recommended for production systems.

---

## 6. Non-Root Containers

The Dockerfile creates a system user `appuser` with UID 1001 and switches to it before the `CMD`:

```dockerfile
RUN useradd --system --create-home --uid 1001 appuser
...
USER appuser
```

The Kubernetes Deployment enforces this at the cluster level:

```yaml
securityContext:
  runAsNonRoot: true
  runAsUser: 1001
  allowPrivilegeEscalation: false
  readOnlyRootFilesystem: true
```

Even if an attacker achieves arbitrary code execution inside the container, they cannot write to the root filesystem, escalate to root, or affect other containers on the same node through UID 0.

---

## Sources

- SLSA specification — <https://slsa.dev/spec/v1.0/>
- SLSA levels explained — <https://slsa.dev/spec/v1.0/levels>
- GitHub Actions `actions/attest-build-provenance` — <https://github.com/actions/attest-build-provenance>
- Sigstore Cosign documentation — <https://docs.sigstore.dev/cosign/overview/>
- Sigstore Fulcio (ephemeral CA) — <https://docs.sigstore.dev/certificate_authority/overview/>
- Rekor transparency log — <https://docs.sigstore.dev/logging/overview/>
- Trivy documentation — <https://trivy.dev/latest/>
- Syft / Anchore SBOM action — <https://github.com/anchore/sbom-action>
- OWASP Top 10 CI/CD Security Risks — <https://owasp.org/www-project-top-10-ci-cd-security-risks/>
