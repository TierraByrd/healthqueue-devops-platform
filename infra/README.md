# HealthQueue Infrastructure

OpenTofu infrastructure targeting LocalStack for local development.

## Structure

```
infra/
├── bootstrap/   # One-time setup: creates the S3 remote-state bucket (local state)
└── main/        # All application resources: S3, DynamoDB, SQS (S3 remote state)
```

## Prerequisites

- [OpenTofu](https://opentofu.org) ≥ 1.13
- [LocalStack](https://localstack.cloud) running on `http://localhost:4566`

## Bootstrap order

**You must apply `bootstrap` before `main`.**  
`main` uses an S3 backend that points at the bucket `bootstrap` creates.
Running `main` before `bootstrap` will fail with a "no such bucket" error.

### 1 — Bootstrap (run once)

```bash
cd infra/bootstrap
tofu init
tofu apply
```

This creates:
- `healthqueue-tofu-state` S3 bucket with versioning and AES-256 encryption
- Local state stored in `infra/bootstrap/terraform.tfstate` (committed to git for the bootstrap module only)

### 2 — Main

```bash
cd infra/main
tofu init    # configures the S3 remote backend
tofu apply
```

This creates:
- `healthqueue-audit-logs-dev` S3 bucket (versioned, encrypted, all public access blocked)
- `healthqueue-appointments-dev` DynamoDB table (on-demand, hash key `appointment_id`)
- `healthqueue-reminders-dev` SQS queue with a `healthqueue-reminders-dlq-dev` dead-letter queue

State is stored remotely in `s3://healthqueue-tofu-state/healthqueue/main/terraform.tfstate`  
with native S3 locking (OpenTofu 1.8+ `use_lockfile`).

## Re-applying

Variables `project` and `environment` default to `healthqueue` and `dev`.
Override them for other environments:

```bash
tofu apply -var="environment=staging"
```

## Teardown

```bash
# Destroy application resources first
cd infra/main && tofu destroy

# Then remove the state bucket
cd infra/bootstrap && tofu destroy
```
