# python:3.12-slim omits compilers, man pages, and most Debian tooling, cutting
# the attack surface compared to the full image while keeping pip and the C
# runtime libraries that gunicorn needs.
FROM python:3.12-slim

# /srv is convention for application data; avoids collision with OS-owned dirs
# like /app or /home that some base images already populate.
WORKDIR /srv/healthqueue

# Explicit UID 1001 so the Kubernetes securityContext.runAsUser: 1001 in
# k8s/deployment.yaml matches exactly — no implicit mapping required.
RUN useradd --system --create-home --uid 1001 appuser

# --no-cache-dir prevents pip from storing the download cache inside the image
# layer, keeping the final image smaller without affecting install correctness.
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy only app/ — not tests/, scripts/, infra/, or docs/ — so those files
# never end up in the published image and cannot be read if the container is
# compromised.
COPY app/ ./app/

# chown must run as root (before USER); once we drop to appuser we can no
# longer change ownership of files that root created.
RUN chown -R appuser:appuser /srv/healthqueue

# Drop root privileges for everything that follows.  If an attacker achieves
# code execution inside the container, they are UID 1001 with no sudo rights.
USER appuser

EXPOSE 5000

# Python buffers stdout by default; disabling buffering ensures log lines
# appear in `docker logs` immediately rather than being held in a buffer that
# may never flush before the container exits.
ENV PYTHONUNBUFFERED=1

# 2 workers: standard starting point for a single-CPU container — enough to
# handle concurrent requests without excessive memory overhead.
# 30 s timeout: long enough to cover slow in-memory operations without holding
# a worker slot open indefinitely if a request hangs.
CMD ["gunicorn", "--bind", "0.0.0.0:5000", "--workers", "2", "--timeout", "30", "app.main:app"]
