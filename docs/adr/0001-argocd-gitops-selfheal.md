# ADR 0001 — Argo CD GitOps with selfHeal

**Date:** 2026-10-25  
**Status:** Accepted  
**Author:** Maya Chen, CTO · HealthQueue

---

## Context

HealthQueue needs a delivery mechanism to apply Kubernetes manifests after the CI pipeline pushes a new image to Docker Hub. Two broad models exist: push-based delivery (the CI pipeline authenticates to the cluster and applies manifests directly) and pull-based GitOps (a controller running inside the cluster watches the Git repository and reconciles state).

The pipeline already stores Kubernetes manifests in `k8s/` within the repository. The team is small (two engineers) and cannot afford to monitor for cluster drift manually. Two past incidents were caused by a manual `kubectl apply` that deviated from the committed manifest.

---

## Decision

Use Argo CD with `automated` sync enabled, and set both `prune: true` and `selfHeal: true` in `argocd/healthqueue-app.yaml`.

```yaml
syncPolicy:
  automated:
    prune: true
    selfHeal: true
  syncOptions:
    - CreateNamespace=true
```

- **prune: true** — resources deleted from `k8s/` in Git are deleted from the cluster; no orphaned objects accumulate.
- **selfHeal: true** — if any resource in the `healthqueue` namespace is modified outside Git (e.g., a `kubectl edit deployment`), Argo CD reverts it to the Git-defined state within ~3 minutes.

---

## Alternatives Considered

| Alternative | Reason not chosen |
|---|---|
| **`kubectl apply` in CI job 6** | Requires a long-lived `KUBECONFIG` secret stored in GitHub Secrets; the CI pipeline gains write access to the cluster, expanding the blast radius of a compromised workflow. |
| **Helm + Argo CD** | Helm adds templating complexity; with only three manifests (Namespace, Deployment, Service), raw YAML is simpler and more readable. Helm would be revisited if the manifest count grows above ~10. |
| **Flux CD** | Functionally equivalent to Argo CD for this use case; Argo CD was chosen for its UI and `gh` CLI integration (`gh` supports Argo CD application status). |
| **selfHeal: false** | Without selfHeal, a manual `kubectl scale deployment healthqueue-api --replicas=1` during an on-call incident would persist indefinitely; the next merge would not restore 2 replicas until the next image change triggered a sync. |

---

## Consequences

**Positive:**
- The cluster state is always derivable from the Git history; `git log k8s/` is the full audit trail.
- Eliminates the push-credential attack surface from the CI pipeline.
- Drift detected and self-healed automatically, removing an entire class of incidents.

**Negative / Trade-offs:**
- `selfHeal: true` means that temporary scaling adjustments (e.g., `kubectl scale --replicas=0` to stop the API for maintenance) will be immediately reverted. Maintenance windows require a Git commit to disable the Deployment, or a temporary Argo CD sync suspension (`argocd app set healthqueue --sync-policy none`).
- Argo CD must itself be operational for deploys to proceed. It becomes a shared dependency.

---

## Sources

- Argo CD automated sync — <https://argo-cd.readthedocs.io/en/stable/user-guide/auto_sync/>
- GitOps principles — <https://opengitops.dev/>
