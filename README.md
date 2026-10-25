# HealthQueue Pipeline

This repo holds the system HealthQueue uses to get code from a developer's computer into production safely. HealthQueue is a made-up health-tech company with an app for booking patient appointments. All the data here is fake.

## Summary for Maya Chen, CTO

Every change to the app goes through the same automatic steps before it can go live. The code gets tested, checked for security problems, and signed so we can prove where it came from. The live system only runs what's saved in GitHub, so anyone can look back and see exactly which change is running and who approved it. That kind of record is what a healthcare auditor would want to see.

Here's what's working now:

- **Every change is tested.** 29 automatic tests run each time code is pushed.
- **Every change is checked for security problems.** A scanner called Trivy looks for known security holes. If it finds one that has a fix available, it stops the release.
- **Every release is signed.** Each release gets a digital signature and a record showing exactly how and where it was built. Nobody can swap in a fake version without it being noticed.
- **GitHub is the only way to change the live system.** A tool called Argo CD keeps the live app matched to what's in GitHub. If someone changes something by hand, it puts it back.
- **The cloud setup is written as code.** The storage for audit logs, the appointments database, and the reminder queue are all created from files in this repo, so they can be rebuilt the same way every time.
- **There's a clear reliability goal.** The appointment app should be up 99.9% of the time. That allows about 43 minutes of downtime per month. If we go past that, new features pause until reliability is fixed.

The biggest thing to improve is how often a release causes a problem. Based on 90 days of sample data, about 1 in 3 releases led to an issue. The DORA baseline doc explains three steps to bring that down.

## How It All Connects

```
A developer saves a change to GitHub
  → GitHub Actions tests it, scans it, packages it, and signs it
  → The signed package is stored on Docker Hub
  → Argo CD sees the change and updates the live app on Kubernetes

Separately, OpenTofu creates the cloud resources the app uses
(audit log storage, appointments database, reminder queue)
```

There's a more detailed diagram in [docs/architecture.md](docs/architecture.md).

## What's in This Repo

| Folder or file | What it is |
|---|---|
| `app/` | The appointment app |
| `tests/` | The automatic tests, including tests for bad or missing input |
| `Dockerfile` | Instructions for packaging the app. It runs without admin access. |
| `.github/workflows/ci-cd.yml` | The automatic test, scan, and release steps |
| `infra/` | OpenTofu files that create the cloud resources |
| `k8s/` | Files describing how the app runs on Kubernetes |
| `argocd/` | The Argo CD setup that keeps the live app matched to GitHub |
| `scripts/` and `data/` | The script that makes 90 days of sample release data, and its output |
| `docs/` | The design docs, reliability plan, security summary, and on-call guide |

## How to Run It

**Run the app and tests on your computer**

```bash
pip install -r requirements.txt
pytest
docker build -t healthqueue-api:local .
docker run -d -p 5050:5000 healthqueue-api:local
curl http://localhost:5050/health
```

**Create the cloud resources**

This uses LocalStack, which acts like AWS on your own computer, so nothing costs money. Run the `bootstrap` folder first, since it creates the storage the main setup depends on.

```bash
docker start localstack
cd infra/bootstrap && tofu init && tofu apply
cd ../main && tofu init && tofu apply
```

**Deploy the app with Argo CD**

```bash
kubectl apply -f argocd/healthqueue-app.yaml
kubectl get applications -n argocd
kubectl get pods -n healthqueue
```

**Check that a release is really ours**

This confirms the release was built by this repo's pipeline and hasn't been tampered with.

```bash
gh attestation verify oci://docker.io/tierrab/healthqueue-api:latest --owner TierraByrd
```

## Documents

- [Architecture](docs/architecture.md): how the pieces fit together and why each tool was picked
- [Reliability Plan](docs/observability-plan.md): uptime goals, the downtime budget, and how we'd monitor the app
- [DORA Baseline](docs/dora-baseline.md): how often we release, how fast, how often releases break, and how fast we recover
- [Security Summary](docs/supply-chain-security.md): how the pipeline protects releases from tampering
- [On-Call Guide](docs/runbook.md): what to do when something goes wrong
- Design decisions:
  - [Using Argo CD so GitHub controls the live app](docs/adr/0001-argocd-gitops-selfheal.md)
  - [Only blocking security problems that have a fix](docs/adr/0002-trivy-block-fixable-only.md)
  - [Signing releases without storing a secret key](docs/adr/0003-cosign-keyless-slsa-provenance.md)
  - [Labeling each release with its exact change ID](docs/adr/0004-commit-sha-image-tags.md)

## Sources

- DORA State of DevOps Report 2023: https://dora.dev/research/2023/dora-report/
- DORA State of DevOps Report 2024: https://dora.dev/research/2024/dora-report/
- SLSA Security Levels: https://slsa.dev/spec/v1.0/levels
- Google SRE Workbook: https://sre.google/workbook/table-of-contents/
- The Twelve-Factor App: https://12factor.net/
- Trivy: https://trivy.dev/
- Sigstore: https://docs.sigstore.dev/
- Argo CD: https://argo-cd.readthedocs.io/
- OpenTofu: https://opentofu.org/docs/

## AI Assistance: 

Claude Code was used alongside Python scripting as a supportive developer tool to assist with syntax formatting, debugging, and synthetic data generation. Specifically, Claude was used to help troubleshoot pipeline integration errors, resolve deployment issues, and format Markdown documentation templates. Additionally, Claude assisted in writing a Python script to generate the raw 90-day synthetic deployment data required for the DORA metrics analysis.