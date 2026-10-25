# ADR 0003 — Cosign Keyless Signing + SLSA Provenance

**Date:** 2026-10-25  
**Status:** Accepted  
**Author:** Maya Chen, CTO · HealthQueue

---

## Context

After a container image is built and pushed to Docker Hub, a consumer of that image (the Argo CD controller, a developer, or an auditor) has no way to verify that the image at tag `aa90b49` was produced by the HealthQueue CI pipeline and has not been tampered with. Tags are mutable; anyone with Docker Hub push credentials could overwrite the image.

Additionally, software supply-chain attacks have increased. The team wants to meet SLSA Build Level 2 and provide cryptographic proof of origin for every image pushed to production.

Two questions need answers at verification time:
1. Did the HealthQueue CI pipeline produce this exact byte sequence?
2. Which source commit, workflow, and GitHub Actions run produced it?

---

## Decision

**Cosign keyless signing** (CI job 5, `sigstore/cosign-installer@v4.1.2`) combined with **SLSA provenance** (`actions/attest-build-provenance@v4.2.2`):

1. Cosign requests an ephemeral signing certificate from Sigstore Fulcio, bound to the GitHub Actions OIDC identity (`repo:TierraByrd/TierraB-Week8CareerPortfolio:ref:refs/heads/main`).
2. The image is signed **by digest** (`sha256:...`), not by tag.
3. The SBOM from job 3 is attached as a separate Cosign in-toto attestation on the same digest.
4. `actions/attest-build-provenance` generates a SLSA Build Level 2 provenance statement — recording the source repository, commit SHA, workflow ref, and runner environment — and uploads it to both the GitHub attestation store and Docker Hub as an OCI referrer.

Verification command:
```
gh attestation verify oci://index.docker.io/tierrab/healthqueue-platform:aa90b49 \
  --repo TierraByrd/TierraB-Week8CareerPortfolio
```

---

## Alternatives Considered

| Alternative | Reason not chosen |
|---|---|
| **Cosign with a long-lived key pair stored in GitHub Secrets** | Requires managing key rotation, access controls, and revocation. A leaked `COSIGN_PRIVATE_KEY` secret silently compromises all past and future signatures; keyless signing has no private key to leak. |
| **No signing at all** | Provides no answer to the supply-chain tamper question; insufficient for SLSA L2. |
| **Notation (CNCF)** | Functionally similar but has less GitHub Actions integration than Cosign; the `gh attestation verify` command is specific to the GitHub/Sigstore stack. |
| **SLSA provenance only, no Cosign signing** | `actions/attest-build-provenance` satisfies SLSA L2 on its own for GitHub-hosted images, but Cosign adds an independent signature in the Rekor transparency log that is verifiable without GitHub-specific tooling. |

---

## Consequences

**Positive:**
- No private key to manage, rotate, or revoke.
- Every signature is recorded in the Rekor public transparency log; any attempt to forge a signature would be detectable.
- `gh attestation verify` gives auditors a single command to confirm provenance.
- SLSA Build Level 2 is met (see `docs/supply-chain-security.md`).

**Negative / Trade-offs:**
- Keyless signing requires the GitHub Actions OIDC token, which is only available on GitHub-hosted runners. This signing step cannot be reproduced locally without a real runner environment.
- The Rekor entry is permanent and public. The image digest and workflow identity are visible to anyone querying Rekor. This is intentional for a public repository and acceptable for synthetic health data; it would need review for a private repository containing sensitive provenance metadata.
- Does not achieve SLSA Level 3 (hermetic builds, reproducible outputs) — see `docs/supply-chain-security.md` for the gap analysis.

---

## Sources

- Sigstore Cosign keyless signing — <https://docs.sigstore.dev/cosign/signing/overview/>
- Rekor transparency log — <https://docs.sigstore.dev/logging/overview/>
- GitHub `actions/attest-build-provenance` — <https://github.com/actions/attest-build-provenance>
- SLSA Build Level 2 requirements — <https://slsa.dev/spec/v1.0/levels#build-l2>
- `gh attestation verify` — <https://cli.github.com/manual/gh_attestation_verify>
