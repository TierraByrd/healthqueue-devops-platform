# HealthQueue Platform: Case Study

**Tierra Byrd** · DevOps and Data Platform Engineering
Repository: https://github.com/TierraByrd/healthqueue-devops-platform

---

## Project Summary

HealthQueue Platform is a complete DevOps pipeline for a patient appointment scheduling API at a fictional health-tech startup. Every code change is tested, scanned for security problems, packaged, signed, and deployed to Kubernetes through Git. The cloud resources the app depends on are created from code, and the project includes reliability goals, a delivery performance baseline, and documentation a new engineer could use on day one.

All data in this project is fake.

## Problem Statement

A health-tech company handles patient data, so it has to answer two questions at any moment: what is running in production, and can we prove where it came from? Many small teams deploy by hand, which makes those questions hard to answer and makes mistakes easy. One missed server or one manual change during an outage can take an app down or leave a security hole nobody notices.

The goal was to build a pipeline where:

- nothing reaches production without passing the same automated checks
- every running image can be traced to the exact commit and build that made it
- infrastructure is rebuilt the same way every time
- the team has clear numbers for reliability and delivery speed

## Technologies Used

| Area | Tools |
|---|---|
| Application | Python, Flask, pytest, Gunicorn |
| Containers | Docker, Docker Hub |
| CI/CD | GitHub Actions |
| Security and supply chain | Trivy (vulnerability scanning), Syft (SBOM), Cosign and Sigstore (keyless signing), GitHub build provenance (SLSA Level 2) |
| Infrastructure as code | OpenTofu, LocalStack (local AWS: S3, DynamoDB, SQS) |
| Orchestration and GitOps | Kubernetes (kind), Argo CD |
| Observability | Prometheus metrics endpoint, structured logs, OpenTelemetry (planned) |
| Analysis | Python script for synthetic DORA data |

## Architecture Overview

```
Developer opens a pull request
  → GitHub Actions: test → build and scan → SBOM
     (pull requests stop here, nothing is published)

Pull request is merged to main
  → GitHub Actions: test → build and scan → SBOM → push → sign and attest
  → Signed image stored on Docker Hub, tagged with the commit ID
  → Kubernetes file updated to the new tag through a pull request
  → Argo CD sees the change in Git and syncs the cluster

OpenTofu (separate)
  → creates audit log storage (S3), appointments table (DynamoDB),
    and reminder queue with a dead-letter queue (SQS)
  → stores its state remotely in S3 with locking
```

A full diagram is in [docs/architecture.md](architecture.md).

## Key Design Decisions

**Git is the only way to change production.** Argo CD keeps the cluster matched to the repo, and self-heal reverses manual changes. This gives a full audit trail. The trade-off is that emergency fixes are slower, since even a hotfix goes through a pull request.

**The security scan blocks only vulnerabilities that have a fix.** The first full scan found 44 high-severity vulnerabilities, all in Debian system packages from the base image, and none had a fix released. Blocking them would have stopped every release with no way to fix it. The pipeline now blocks anything fixable and saves a full report of everything else with every build. The trade-off is knowingly running with unfixed risks, which is reduced by the container running as a non-root user and the app never using those system tools.

**Images are signed without storing a key.** Cosign keyless signing uses GitHub's identity system, so there's no private key to store or leak. GitHub also creates a signed provenance record for each image, which meets SLSA Level 2.

**Images are tagged with the commit ID, not `latest`.** Every deployment points at one exact image. This makes rollbacks clear and means Argo CD sees a real change whenever a new version ships.

**Pull requests never publish.** Only merged code on `main` gets pushed and signed, so nothing unreviewed can reach Docker Hub.

**Least privilege everywhere.** Each pipeline job gets only the permissions it needs, the container runs as a non-root user with a read-only file system, and the audit log bucket blocks all public access.

## Challenges and How I Solved Them

**A pipeline tool version that didn't exist.** The first run failed because the Trivy action was pinned to a version name that didn't exist. Instead of fixing only that one, I checked every action in the workflow against its real releases and found most were one to four major versions behind. All ten were updated and pinned to current versions.

**44 vulnerabilities with no fix.** The scan correctly blocked the release. I looked at where the findings came from, confirmed the Python packages were clean, and changed the gate to block only fixable problems while keeping a full report. That decision is recorded in an architecture decision record.

**Kubernetes timing out.** After a restart, the cluster stopped responding. Docker had only about 3.8 GB of memory, and an older Kubernetes cluster and LocalStack had restarted automatically alongside it. I stopped the extra containers, turned off their auto-restart, and gave Docker more memory.

**Infrastructure disappearing on restart.** LocalStack doesn't save anything between restarts by default. I documented the rebuild order in the runbook: create the state bucket first, then the main resources.

**Keeping two versions of the project separate.** When this portfolio repo was copied from the original, both would have pushed to the same Docker Hub image. I renamed the image so each repo publishes and signs its own builds, and confirmed it by verifying the new image's provenance.

## Outcomes and Metrics

| What | Result |
|---|---|
| Automated tests | 29, including malformed and missing input |
| Pipeline | 5 jobs, about 3 minutes end to end |
| Security gate | Blocked a real release on first run (44 findings); now blocks only fixable issues with a full report saved |
| Supply chain | SLSA Level 2 provenance, verified with `gh attestation verify` |
| Infrastructure | 10 resources created from code, with remote, locked state |
| GitOps | Changes deployed through pull requests; Argo CD synced and healthy |
| Availability goal | 99.9% over 30 days (about 43 minutes of allowed downtime) |
| Speed goal | 95% of booking requests under 500 ms |

**DORA baseline** (90 days of synthetic data):

| Metric | Result | Tier |
|---|---|---|
| Deployment frequency | 1.48 per week | High |
| Lead time for changes | 37.8 minutes | Elite |
| Change failure rate | 31.6% | Low |
| Time to restore | 4.03 hours | High |
| **Overall** | | **Medium** |

Change failure rate is the clear thing to improve, and it shapes the plan below.

## How This Connects to What I Learned

- **Generative culture (Westrum):** the pipeline makes information easy to see. Scan reports, provenance, and Git history are open to everyone, not hidden in one person's inbox.
- **Declarative thinking:** Kubernetes files, OpenTofu, and Argo CD all describe the end state and let the system make it happen, instead of running steps by hand.
- **Short-lived branches and pull requests:** every change in this repo went through a small branch and a reviewed pull request.
- **Supply chain security:** scanning, SBOMs, signing, and provenance turn the pipeline into a trust boundary, not just automation.
- **Infrastructure as code:** remote state and locking prevent two people from changing infrastructure at once, and `tofu plan` showing no changes proves nothing drifted.
- **SRE practices:** SLOs and an error budget policy decide when to pause features and focus on reliability.
- **DORA metrics:** the baseline gives an objective starting point and points to the weakest area.

## Improvement Plan

**Next steps for the pipeline**

1. **Lower the change failure rate.** Add smoke tests right after each deploy, and use Argo Rollouts for canary releases that roll back on their own when health checks fail.
2. **Shrink the base image.** Move to a minimal base image (distroless or Chainguard) to cut most of the 44 unfixed system package findings.
3. **Check signatures inside the cluster.** Add a policy (Kyverno or the Sigstore policy controller) so Kubernetes refuses to run any image that isn't signed by this pipeline.
4. **Deploy the monitoring stack.** Run Prometheus and Grafana in the cluster with burn-rate alerts tied to the SLOs.
5. **Automate image updates.** Have a tool like Argo CD Image Updater or Renovate open the pull request that bumps the image tag after each build.
6. **Work toward SLSA Level 3.** Move builds to isolated runners so other jobs can't affect them.

**Next steps toward MLOps**

The same pipeline can ship machine learning models, not just app code. The plan is to add a small data pipeline that prepares appointment data (for example, predicting no-shows), train a simple model, track it with MLflow, and serve it as a new endpoint through the same test, scan, sign, and GitOps flow. Monitoring would then add model-specific signals like prediction accuracy and data drift next to the existing latency and error rate goals.

## Target Role

This project is aimed at **DevOps and data platform engineering roles at cloud-native companies, with a path toward MLOps**. Those teams need people who can build secure, automated pipelines and keep production traceable, and the same skills carry over directly to shipping and monitoring machine learning models.