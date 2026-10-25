# On-Call Runbook — HealthQueue Appointment API

**Author:** Maya Chen, CTO · HealthQueue  
**Applies to:** `healthqueue` namespace, `kind` cluster, LocalStack infrastructure  
**Last updated:** 2026-10-25

> **Manual step** labels mark actions that require human decision or direct cluster/shell access and are not currently automated.

---

## 1. Orientation: What Is Running?

| Layer | Location | How to check |
|---|---|---|
| Application | `healthqueue` namespace, 2 pods | `kubectl get pods -n healthqueue` |
| GitOps | Argo CD `argocd` namespace | `kubectl get app healthqueue -n argocd` or Argo CD UI |
| Image registry | Docker Hub `tierrab/healthqueue-api` | Docker Hub web or `docker pull tierrab/healthqueue-api:<sha>` |
| State backend | LocalStack S3 `healthqueue-tofu-state` | `aws --endpoint-url http://localhost:4566 s3 ls` |
| App infrastructure | LocalStack S3/DynamoDB/SQS | `aws --endpoint-url http://localhost:4566 s3 ls`, `dynamodb list-tables`, `sqs list-queues` |

---

## 2. First-Response Health Checks

Run these in order when paged.

### 2.1 Check Argo CD Application Status

```bash
kubectl get application healthqueue -n argocd
```

Expected output:
```
NAME          SYNC STATUS   HEALTH STATUS
healthqueue   Synced        Healthy
```

If `SYNC STATUS` is `OutOfSync` or `HEALTH STATUS` is `Degraded`, see Section 4 (sync failures) or Section 5 (crash loops).

### 2.2 Check Pod Health

```bash
kubectl get pods -n healthqueue
```

Expected: 2 pods in `Running` state, both showing `1/1` ready.

```bash
kubectl describe pod -n healthqueue -l app=healthqueue-api
```

Look for: `Readiness probe failed`, `CrashLoopBackOff`, `OOMKilled`, or `Error` events at the bottom of the describe output.

### 2.3 Check the /health Endpoint

```bash
kubectl port-forward svc/healthqueue-api 8080:80 -n healthqueue &
curl -s http://localhost:8080/health
```

Expected:
```json
{"service": "HealthQueue", "status": "ok"}
```

Kill the port-forward when done: `kill %1`

### 2.4 Check Recent Logs

```bash
kubectl logs -n healthqueue -l app=healthqueue-api --tail=50
```

Look for Python tracebacks, gunicorn worker timeouts (`[CRITICAL] WORKER TIMEOUT`), or repeated 5xx lines.

---

## 3. Rolling Back a Bad Deploy

Use this procedure when a recent deploy has degraded the service and you need to revert to the last known-good image.

**Trigger:** the Argo CD `HEALTH STATUS` is `Degraded` immediately after a sync, or error rate has spiked after the most recent merge to `main`.

### Step 1 — Identify the last known-good commit

```bash
git log --oneline k8s/deployment.yaml
```

Note the commit SHA of the previous working `image:` tag. Cross-reference with Docker Hub to confirm the image exists:

```bash
# Manual step: check Docker Hub for the previous tag
# Example: curl -s https://hub.docker.com/v2/repositories/tierrab/healthqueue-api/tags/<sha>
```

### Step 2 — Revert the Deployment manifest **[Manual step]**

```bash
git revert HEAD --no-edit
git push origin main
```

This creates a new revert commit. Argo CD will detect the manifest change (the `image:` tag reverts to the previous SHA) and sync automatically within ~3 minutes.

**Do not** use `git reset --hard` or `git push --force`; the revert commit preserves audit history.

### Step 3 — Confirm the rollback synced

```bash
kubectl get application healthqueue -n argocd
kubectl get pods -n healthqueue -w
```

Wait until both pods show `1/1 Running` and the application shows `Synced / Healthy`.

### Step 4 — Validate the endpoint

```bash
kubectl port-forward svc/healthqueue-api 8080:80 -n healthqueue &
curl -s http://localhost:8080/health
curl -s http://localhost:8080/appointments
kill %1
```

---

## 4. Argo CD Sync Failures

**Symptom:** `kubectl get application healthqueue -n argocd` shows `SYNC STATUS: OutOfSync` and/or Argo CD UI shows a sync error.

### 4.1 Read the Sync Error

```bash
kubectl describe application healthqueue -n argocd | grep -A 20 "Sync Status"
```

Common causes:

| Error message | Cause | Fix |
|---|---|---|
| `namespaces "healthqueue" not found` | Namespace was deleted or never created | `kubectl apply -f k8s/namespace.yaml` — then force a sync |
| `image pull error` | Image tag does not exist on Docker Hub | Verify the tag exists; check whether the CI push job succeeded |
| `failed to sync` + RBAC error | Argo CD service account lacks permissions | Check `ClusterRoleBinding` for the Argo CD application controller |

### 4.2 Force a Manual Sync **[Manual step]**

```bash
# Requires argocd CLI or access to the Argo CD UI
argocd app sync healthqueue --force
```

Or via `kubectl`:
```bash
kubectl patch application healthqueue -n argocd \
  -p '{"operation": {"sync": {"revision": "HEAD", "prune": true}}}' \
  --type merge
```

### 4.3 Temporarily Suspend Auto-Sync **[Manual step]**

If sync is looping or causing repeated pod restarts:

```bash
argocd app set healthqueue --sync-policy none
```

Restore auto-sync after the issue is resolved:
```bash
argocd app set healthqueue --sync-policy automated
```

---

## 5. Pod Crash Loops

**Symptom:** `kubectl get pods -n healthqueue` shows `CrashLoopBackOff` or a pod restart count > 2.

### 5.1 Read the Crash Logs

```bash
kubectl logs -n healthqueue <pod-name> --previous
```

`--previous` reads the terminated container's log, which shows the actual error before the crash.

### 5.2 Common Crash Causes and Fixes

**`readOnlyRootFilesystem` write failure:**  
Any code that tries to write outside `/tmp` will fail with a `Read-only file system` error. Gunicorn's temp files go to `/tmp` (covered by the `emptyDir` volume mount). If a new dependency tries to write to `/app` or `/srv`, it must be redirected to `/tmp` via an environment variable or config.

**OOMKilled (`reason: OOMKilled`):**  
The container exceeded the 256 Mi memory limit. **[Manual step]** Update `resources.limits.memory` in `k8s/deployment.yaml`, commit, and push.

**`runAsNonRoot` failure:**  
If the Dockerfile was changed to run as root (UID 0), the pod will fail the `runAsNonRoot` check. Verify the `USER` directive in the Dockerfile is `appuser` (UID 1001).

**Liveness probe failure loop:**  
If `/health` returns non-2xx for more than `failureThreshold × periodSeconds` = 3 × 15 s = 45 s, the kubelet will restart the container. Check whether the app is starting up slowly; if so, increase `initialDelaySeconds` in `k8s/deployment.yaml`.

### 5.3 Cordon and Drain a Node (if node-level issue) **[Manual step]**

```bash
kubectl cordon <node-name>
kubectl drain <node-name> --ignore-daemonsets --delete-emptydir-data
```

The two replicas will reschedule to remaining nodes. Argo CD will reconcile the pod count.

---

## 6. Restoring LocalStack Infrastructure

LocalStack is ephemeral — its state is lost when the Docker container restarts. This procedure recreates all HealthQueue infrastructure.

> **These are all manual steps.** The `tofu apply` commands are not automated in CI.

### Prerequisites

- LocalStack running: `docker run -d -p 4566:4566 localstack/localstack`
- OpenTofu ≥ 1.13 installed: `tofu --version`
- AWS CLI configured with dummy creds (or `AWS_ACCESS_KEY_ID=test AWS_SECRET_ACCESS_KEY=test`)

### Step 1 — Bootstrap (creates the state bucket)

The bootstrap module must be applied first because the main module stores its state in the S3 bucket that bootstrap creates.

```bash
cd infra/bootstrap
AWS_ACCESS_KEY_ID=test AWS_SECRET_ACCESS_KEY=test \
  tofu init -reconfigure
AWS_ACCESS_KEY_ID=test AWS_SECRET_ACCESS_KEY=test \
  tofu apply -auto-approve
```

Expected: S3 bucket `healthqueue-tofu-state` created on LocalStack.

Verify:
```bash
aws --endpoint-url http://localhost:4566 \
  --region us-east-1 \
  s3 ls
```

### Step 2 — Apply Main Infrastructure

```bash
cd ../main
AWS_ACCESS_KEY_ID=test AWS_SECRET_ACCESS_KEY=test \
  tofu init -reconfigure
AWS_ACCESS_KEY_ID=test AWS_SECRET_ACCESS_KEY=test \
  tofu apply -auto-approve
```

Expected resources created:
- S3 bucket `healthqueue-audit-logs-dev` (versioned, AES256 encrypted, public access blocked)
- DynamoDB table `healthqueue-appointments-dev` (`appointment_id` hash key, PAY_PER_REQUEST)
- SQS queue `healthqueue-reminders-dev`
- SQS DLQ `healthqueue-reminders-dlq-dev` (maxReceiveCount 5)

Verify:
```bash
aws --endpoint-url http://localhost:4566 --region us-east-1 s3 ls
aws --endpoint-url http://localhost:4566 --region us-east-1 dynamodb list-tables
aws --endpoint-url http://localhost:4566 --region us-east-1 sqs list-queues
```

### Step 3 — Confirm OpenTofu State Lock

The main module uses native S3 state locking (`use_lockfile = true`). If a previous `tofu apply` was interrupted, a `.tflock` object may exist in the state bucket:

```bash
aws --endpoint-url http://localhost:4566 --region us-east-1 \
  s3 ls s3://healthqueue-tofu-state/healthqueue/main/
```

If `terraform.tfstate.tflock` is present and no other `tofu` process is running, delete it manually **[Manual step]**:

```bash
aws --endpoint-url http://localhost:4566 --region us-east-1 \
  s3 rm s3://healthqueue-tofu-state/healthqueue/main/terraform.tfstate.tflock
```

Then re-run `tofu apply`.

---

## 7. Quick Reference — Key Commands

```bash
# Argo CD app status
kubectl get application healthqueue -n argocd

# Pod status
kubectl get pods -n healthqueue

# Live logs
kubectl logs -n healthqueue -l app=healthqueue-api -f

# Port-forward for manual testing
kubectl port-forward svc/healthqueue-api 8080:80 -n healthqueue

# Check /health
curl http://localhost:8080/health

# Check /metrics
curl http://localhost:8080/metrics | grep healthqueue_

# Rollback: revert last commit
git revert HEAD --no-edit && git push origin main

# Rebuild LocalStack infra
cd infra/bootstrap && AWS_ACCESS_KEY_ID=test AWS_SECRET_ACCESS_KEY=test tofu apply -auto-approve
cd ../main       && AWS_ACCESS_KEY_ID=test AWS_SECRET_ACCESS_KEY=test tofu apply -auto-approve
```

---

## Sources

- Argo CD operations guide — <https://argo-cd.readthedocs.io/en/stable/operator-manual/troubleshooting/>
- Kubernetes pod debugging — <https://kubernetes.io/docs/tasks/debug/debug-application/>
- OpenTofu state management — <https://opentofu.org/docs/language/state/>
- LocalStack documentation — <https://docs.localstack.cloud/overview/>
- Google SRE Book — Being On-Call — <https://sre.google/sre-book/being-on-call/>
