# ADR 0004 — Commit-SHA Image Tags Instead of `latest`

**Date:** 2026-10-25  
**Status:** Accepted  
**Author:** Maya Chen, CTO · HealthQueue

---

## Context

When the CI pipeline pushes the container image to Docker Hub, it must choose how to tag it. The two most common patterns are:
- **`latest` tag only:** every push overwrites the same tag
- **Immutable SHA tag:** every push creates a new tag derived from the commit SHA

The Kubernetes Deployment manifest and the Argo CD Application must reference an image tag. Argo CD detects changes to the manifest and syncs when the tag changes.

The team experienced an issue during initial setup where two builds from different commits both produced the `:latest` tag. Argo CD saw no manifest change (the tag string did not change) and did not sync the new image. The running pods continued serving the old code until the Deployment was manually restarted.

---

## Decision

Tag every pushed image with the 7-character short commit SHA (e.g., `tierrab/healthqueue-api:aa90b49`) using the `${{ github.sha }}` expression:

```yaml
- name: Resolve short commit SHA
  id: meta
  run: echo "short_sha=${GITHUB_SHA::7}" >> "$GITHUB_OUTPUT"

- name: Build and push
  uses: docker/build-push-action@v7.4.0
  with:
    tags: |
      index.docker.io/tierrab/healthqueue-api:${{ steps.meta.outputs.short_sha }}
      index.docker.io/tierrab/healthqueue-api:latest
```

The `latest` tag is still pushed as a convenience for humans pulling the image manually (`docker pull tierrab/healthqueue-api`). However, the `k8s/deployment.yaml` manifest references the SHA tag, not `latest`:

```yaml
image: tierrab/healthqueue-api:aa90b49
```

Argo CD watches the manifest in Git. When a new commit is merged, CI pushes a new SHA-tagged image, a subsequent step (or a developer) updates the `image:` field in `k8s/deployment.yaml`, and Argo CD syncs the change.

---

## Alternatives Considered

| Alternative | Reason not chosen |
|---|---|
| **`latest` tag only in the Deployment manifest** | Argo CD does not detect a change when the tag string is unchanged; pods are not rolled over to the new image without a manual restart. Violates the GitOps principle that the Git state fully describes what is running. |
| **`imagePullPolicy: Always` + `latest` tag** | Forces the kubelet to pull on every pod start, but Argo CD still does not trigger a rollout on a new push; this only helps when a pod is manually restarted or rescheduled. |
| **Digest-only references in the Deployment** | Using `image: tierrab/healthqueue-api@sha256:...` is the most immutable option and is used by Cosign for signing. However, updating a 64-character digest in a YAML file every deploy is error-prone; the SHA tag is a human-readable compromise that maps uniquely to a commit. |
| **Semantic version tags (e.g., `v1.2.3`)** | Requires a versioning decision and a Git tag step; adds overhead for a project that ships on every merge. SemVer is more appropriate when the API has external consumers with compatibility requirements. |

---

## Consequences

**Positive:**
- Every tag is globally unique and traces directly to a commit in Git history.
- `git log --oneline` and `docker pull tierrab/healthqueue-api:<sha>` give a deterministic audit trail.
- Argo CD reliably detects changes: updating the `image:` field in `k8s/deployment.yaml` is a diff that triggers a sync.
- Old images are preserved on Docker Hub under their SHA tags; rollback is `git revert` + `ci` without needing a rebuild.

**Negative / Trade-offs:**
- The Deployment manifest must be updated with the new SHA tag on each merge, either manually or by an automated step. Currently this is done manually; a CI post-push step that opens a PR updating `k8s/deployment.yaml` would close this gap.
- Old SHA-tagged images accumulate on Docker Hub and consume storage. A periodic Docker Hub retention policy or `docker manifest rm` cron job would be needed for long-running projects.

---

## Sources

- Kubernetes `imagePullPolicy` — <https://kubernetes.io/docs/concepts/containers/images/#image-pull-policy>
- Argo CD image update automation — <https://argocd-image-updater.readthedocs.io/en/stable/>
- Docker Hub image tag best practices — <https://docs.docker.com/develop/dev-best-practices/>
