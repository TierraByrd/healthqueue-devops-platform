# Observability Plan — HealthQueue Appointment API

**Author:** Maya Chen, CTO · HealthQueue  
**Status key:** `[Implemented]` = present in the current codebase · `[Proposed]` = planned, not yet deployed

---

## 1. Service-Level Indicators (SLIs)

SLIs are the measurable signals we track. Two SLIs are defined for the appointment API.

### SLI 1 — Availability

**Definition:** Proportion of HTTP requests to `/appointments`, `/health`, and `/metrics` that return a non-5xx response, measured over a rolling 30-day window.

```
availability = (total_requests - 5xx_responses) / total_requests
```

**Prometheus expression `[Proposed]`:**
```promql
sum(rate(healthqueue_requests_total{status_code!~"5.."}[5m]))
  /
sum(rate(healthqueue_requests_total[5m]))
```

The counter `healthqueue_requests_total` with label `status_code` is already exported by the app. `[Implemented]`

### SLI 2 — Latency

**Definition:** The 95th-percentile HTTP response latency for `POST /appointments` (the only write path), measured over a rolling 30-day window.

```
latency_sli = histogram_quantile(0.95, healthqueue_request_latency_seconds_bucket)
```

**Prometheus expression `[Proposed]`:**
```promql
histogram_quantile(
  0.95,
  sum(rate(healthqueue_request_latency_seconds_bucket{endpoint="book_appointment"}[5m]))
  by (le)
)
```

The histogram `healthqueue_request_latency_seconds` is already exported. `[Implemented]`

---

## 2. Service-Level Objectives (SLOs)

### SLO 1 — Availability: 99.9 % over 30 days

| Parameter | Value |
|---|---|
| Target | 99.9 % of requests return non-5xx |
| Window | 30 rolling days |
| SLI | `healthqueue_requests_total` |

### SLO 2 — Latency: p95 < 500 ms over 30 days

| Parameter | Value |
|---|---|
| Target | p95 response time for `POST /appointments` < 500 ms |
| Window | 30 rolling days |
| SLI | `healthqueue_request_latency_seconds` |

---

## 3. Error Budget Math

### Availability Error Budget

```
30-day window     = 30 × 24 × 60 = 43,200 minutes
Allowed downtime  = 43,200 × 0.001 = 43.2 minutes / 30 days
```

Assuming a steady request rate of ~100 requests/minute (synthetic baseline):

```
Total requests per 30 days = 100 req/min × 43,200 min = 4,320,000 requests
Allowed failures           = 4,320,000 × 0.001        = 4,320 failed requests
```

**Availability error budget: 43.2 minutes of full outage (or 4,320 failed requests at 100 req/min).**

### Latency Error Budget

The latency SLO allows 5 % of `POST /appointments` requests to exceed 500 ms (i.e., 95th-percentile must stay below 500 ms). In practice this means:

```
Allowed slow requests = 4,320,000 × 0.05 = 216,000 requests/month may exceed 500 ms
```

Exceeding this budget indicates a systemic regression, not noise.

---

## 4. Error Budget Policy

The policy governs how the team responds at different burn levels. Burn rate is how fast we consume the error budget relative to the budget replenishment rate.

| Burn Rate | Budget Consumed in… | Action |
|---|---|---|
| 1× | 30 days (normal) | No action required — within normal operation |
| 5× | 6 days | Engineering team notified via Slack; investigate root cause before next deploy |
| 14.4× | 2 hours | **Page on-call engineer**; freeze non-critical deploys; start incident runbook |
| 100× | < 30 min | Declare incident; roll back most recent deploy immediately; all-hands engineering |

When the 30-day error budget is more than 50 % consumed before day 15, the team shifts sprint capacity from features to reliability work until the budget is restored. `[Proposed]`

---

## 5. Multi-Window Burn-Rate Alerting `[Proposed]`

Single-window burn-rate alerts can fire too late (slow burns) or recover too quickly (fast spikes). The Google SRE Workbook recommends a two-window approach: a long window to detect sustained burns and a short window to confirm the burn is still active.

### Alert 1 — Page (critical, fast burn)

```yaml
# Fires if the error budget burns > 14.4× over 1 h AND > 14.4× over 5 min.
# Catches complete outages; should page within ~2 minutes of failure onset.
- alert: HealthQueueHighErrorBudgetBurn
  expr: |
    (
      job:healthqueue_availability_error_rate:ratio_rate1h > (14.4 * 0.001)
      and
      job:healthqueue_availability_error_rate:ratio_rate5m > (14.4 * 0.001)
    )
  for: 2m
  labels:
    severity: page
  annotations:
    summary: "Fast error budget burn — availability SLO at risk"
```

### Alert 2 — Ticket (warning, slow burn)

```yaml
# Fires if error budget burns > 6× over 6 h AND > 6× over 30 min.
# Catches slow regressions that would exhaust the budget in ~5 days.
- alert: HealthQueueSlowErrorBudgetBurn
  expr: |
    (
      job:healthqueue_availability_error_rate:ratio_rate6h > (6 * 0.001)
      and
      job:healthqueue_availability_error_rate:ratio_rate30m > (6 * 0.001)
    )
  for: 15m
  labels:
    severity: ticket
  annotations:
    summary: "Slow error budget burn — investigate before next deploy"
```

Thresholds follow the multi-window model described in the Google SRE Workbook, Chapter 5.

---

## 6. Metrics Plan

### Prometheus `[Implemented — /metrics endpoint live]`

The app exports metrics via `prometheus_client` on `GET /metrics`. The Kubernetes Deployment manifest includes pod-level annotations:

```yaml
annotations:
  prometheus.io/scrape: "true"
  prometheus.io/path: /metrics
  prometheus.io/port: "5000"
```

A Prometheus server configured with `kubernetes_sd_configs` targeting `role: pod` will discover and scrape the pods automatically. `[Proposed — Prometheus not yet deployed to the cluster]`

**Key metrics exported today:**

| Metric | Type | Labels | Purpose |
|---|---|---|---|
| `healthqueue_requests_total` | Counter | `method`, `endpoint`, `status_code` | SLI availability numerator/denominator |
| `healthqueue_request_latency_seconds` | Histogram | `method`, `endpoint` | SLI latency (p95) |
| `healthqueue_errors_total` | Counter | `endpoint` | Error budget burn visibility |

**Rationale:** Prometheus is the de facto standard for Kubernetes-native metrics. The `/metrics` endpoint was built into the app from day one so no sidecar is needed, and the existing histogram buckets are sufficient for p95 SLO tracking.

---

## 7. Logs Plan `[Proposed]`

**Approach:** Structured JSON logs to stdout. The container runtime captures stdout and forwards to whatever log aggregation system is deployed (e.g., Loki, CloudWatch, Datadog).

**Implementation sketch:**

```python
import logging, json, sys

class JsonFormatter(logging.Formatter):
    def format(self, record):
        return json.dumps({
            "ts": self.formatTime(record),
            "level": record.levelname,
            "msg": record.getMessage(),
            "logger": record.name,
        })

handler = logging.StreamHandler(sys.stdout)
handler.setFormatter(JsonFormatter())
logging.getLogger().addHandler(handler)
```

**Fields to include on every request log:** `method`, `path`, `status_code`, `duration_ms`, `appointment_id` (where applicable).

**Rationale:** Structured logs are queryable by machines, not just humans. Writing to stdout (The Twelve-Factor App, Factor XI) keeps the app unaware of the log destination and allows infrastructure to route logs without changing application code.

---

## 8. Traces Plan `[Proposed]`

**Approach:** OpenTelemetry SDK + OTLP exporter → Jaeger or Tempo (operator's choice).

**Implementation sketch:**

```python
from opentelemetry import trace
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import BatchSpanProcessor
from opentelemetry.exporter.otlp.proto.grpc.trace_exporter import OTLPSpanExporter
from opentelemetry.instrumentation.flask import FlaskInstrumentor

provider = TracerProvider()
provider.add_span_processor(BatchSpanProcessor(OTLPSpanExporter()))
trace.set_tracer_provider(provider)
FlaskInstrumentor().instrument_app(app)
```

`FlaskInstrumentor` auto-instruments every route, adding `http.method`, `http.route`, `http.status_code`, and `http.url` span attributes with no manual changes to route handlers.

**Rationale:** Traces answer questions that metrics and logs cannot: "which code path inside `book_appointment` is slow for specific specialties?" The `FlaskInstrumentor` auto-instruments all existing routes with zero changes to business logic, keeping the implementation cost low.

---

## Sources

- Google SRE Book — Service Level Objectives — <https://sre.google/sre-book/service-level-objectives/>
- Google SRE Workbook — Alerting on SLOs (multi-window burn-rate) — <https://sre.google/workbook/alerting-on-slos/>
- Prometheus documentation — <https://prometheus.io/docs/introduction/overview/>
- OpenTelemetry Python SDK — <https://opentelemetry.io/docs/languages/python/>
- The Twelve-Factor App, Factor XI (Logs) — <https://12factor.net/logs>
