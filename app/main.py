import copy
import threading
import time
import uuid
from datetime import datetime, timezone

from flask import Flask, jsonify, request
from prometheus_client import CONTENT_TYPE_LATEST, Counter, Histogram, generate_latest

app = Flask(__name__)

_lock = threading.Lock()

# ---------------------------------------------------------------------------
# Prometheus metrics
# ---------------------------------------------------------------------------
REQUEST_COUNT = Counter(
    "healthqueue_requests_total",
    "Total HTTP requests",
    ["method", "endpoint", "status_code"],
)
REQUEST_LATENCY = Histogram(
    "healthqueue_request_latency_seconds",
    "Request latency in seconds",
    ["method", "endpoint"],
)
ERROR_COUNT = Counter(
    "healthqueue_errors_total",
    "Total HTTP errors (4xx/5xx)",
    ["endpoint"],
)

# ---------------------------------------------------------------------------
# In-memory store — seed data uses fictional patients only
# ---------------------------------------------------------------------------
_SEED_DATA: dict = {
    "apt-001": {
        "id": "apt-001",
        "patient_name": "Alex Johnson",
        "doctor_name": "Dr. Maria Chen",
        "specialty": "Cardiology",
        "date": "2026-11-01",
        "time": "09:00",
        "status": "scheduled",
        "created_at": "2026-10-15T10:00:00+00:00",
    },
    "apt-002": {
        "id": "apt-002",
        "patient_name": "Sam Rivera",
        "doctor_name": "Dr. James Okafor",
        "specialty": "Neurology",
        "date": "2026-11-02",
        "time": "14:30",
        "status": "scheduled",
        "created_at": "2026-10-16T09:15:00+00:00",
    },
    "apt-003": {
        "id": "apt-003",
        "patient_name": "Taylor Kim",
        "doctor_name": "Dr. Priya Sharma",
        "specialty": "Dermatology",
        "date": "2026-11-05",
        "time": "11:00",
        "status": "scheduled",
        "created_at": "2026-10-17T14:30:00+00:00",
    },
}

_appointments: dict = copy.deepcopy(_SEED_DATA)

_REQUIRED_FIELDS = frozenset({"patient_name", "doctor_name", "specialty", "date", "time"})

# ---------------------------------------------------------------------------
# Request lifecycle hooks — record Prometheus metrics on every response
# ---------------------------------------------------------------------------

@app.before_request
def _start_timer() -> None:
    from flask import g
    g._req_start = time.perf_counter()


@app.after_request
def _record_metrics(response):
    from flask import g
    endpoint = request.endpoint or "unknown"
    elapsed = time.perf_counter() - getattr(g, "_req_start", time.perf_counter())
    REQUEST_COUNT.labels(
        method=request.method,
        endpoint=endpoint,
        status_code=str(response.status_code),
    ).inc()
    REQUEST_LATENCY.labels(method=request.method, endpoint=endpoint).observe(elapsed)
    if response.status_code >= 400:
        ERROR_COUNT.labels(endpoint=endpoint).inc()
    return response


# ---------------------------------------------------------------------------
# Routes
# ---------------------------------------------------------------------------

@app.get("/health")
def health():
    return jsonify({"status": "ok", "service": "HealthQueue"}), 200


@app.get("/metrics")
def metrics():
    return generate_latest(), 200, {"Content-Type": CONTENT_TYPE_LATEST}


@app.get("/appointments")
def list_appointments():
    with _lock:
        items = list(_appointments.values())
    return jsonify({"appointments": items, "total": len(items)}), 200


@app.post("/appointments")
def book_appointment():
    if not request.is_json:
        return jsonify({"error": "Content-Type must be application/json"}), 415

    body = request.get_json(silent=True)
    if body is None:
        return jsonify({"error": "Invalid or missing JSON body"}), 400

    missing = _REQUIRED_FIELDS - set(body.keys())
    if missing:
        return jsonify({"error": "Missing required fields", "fields": sorted(missing)}), 400

    for field in _REQUIRED_FIELDS:
        if not isinstance(body[field], str) or not body[field].strip():
            return jsonify({"error": f"Field '{field}' must be a non-empty string"}), 400

    apt_id = str(uuid.uuid4())
    appointment = {
        "id": apt_id,
        "patient_name": body["patient_name"].strip(),
        "doctor_name": body["doctor_name"].strip(),
        "specialty": body["specialty"].strip(),
        "date": body["date"].strip(),
        "time": body["time"].strip(),
        "status": "scheduled",
        "created_at": datetime.now(timezone.utc).isoformat(),
    }

    with _lock:
        _appointments[apt_id] = appointment

    return jsonify({"appointment": appointment}), 201


@app.delete("/appointments/<apt_id>")
def cancel_appointment(apt_id: str):
    with _lock:
        if apt_id not in _appointments:
            return jsonify({"error": f"Appointment '{apt_id}' not found"}), 404
        if _appointments[apt_id]["status"] == "cancelled":
            return jsonify({"error": "Appointment is already cancelled"}), 409
        _appointments[apt_id] = {**_appointments[apt_id], "status": "cancelled"}
        return jsonify({"appointment": _appointments[apt_id]}), 200


if __name__ == "__main__":
    app.run(debug=False, host="0.0.0.0", port=5000)
