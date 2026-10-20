import json


# ---------------------------------------------------------------------------
# /health
# ---------------------------------------------------------------------------

class TestHealth:
    def test_returns_200(self, client):
        resp = client.get("/health")
        assert resp.status_code == 200

    def test_body_fields(self, client):
        data = client.get("/health").get_json()
        assert data["status"] == "ok"
        assert data["service"] == "HealthQueue"


# ---------------------------------------------------------------------------
# /metrics
# ---------------------------------------------------------------------------

class TestMetrics:
    def test_returns_200(self, client):
        assert client.get("/metrics").status_code == 200

    def test_content_contains_counter_name(self, client):
        resp = client.get("/metrics")
        assert b"healthqueue_requests_total" in resp.data

    def test_content_type_is_prometheus_text(self, client):
        resp = client.get("/metrics")
        assert "text/plain" in resp.content_type


# ---------------------------------------------------------------------------
# GET /appointments
# ---------------------------------------------------------------------------

class TestListAppointments:
    def test_returns_200(self, client):
        assert client.get("/appointments").status_code == 200

    def test_returns_seed_count(self, client):
        data = client.get("/appointments").get_json()
        assert data["total"] == 3
        assert len(data["appointments"]) == 3

    def test_response_has_required_keys(self, client):
        data = client.get("/appointments").get_json()
        assert "appointments" in data
        assert "total" in data

    def test_each_appointment_has_expected_fields(self, client):
        data = client.get("/appointments").get_json()
        required = {"id", "patient_name", "doctor_name", "specialty", "date", "time", "status"}
        for apt in data["appointments"]:
            assert required <= apt.keys()


# ---------------------------------------------------------------------------
# POST /appointments
# ---------------------------------------------------------------------------

_VALID_BODY = {
    "patient_name": "Jordan Lee",
    "doctor_name": "Dr. Sofia Patel",
    "specialty": "Orthopedics",
    "date": "2026-12-01",
    "time": "10:00",
}


class TestBookAppointment:
    def test_valid_request_returns_201(self, client):
        resp = client.post("/appointments", json=_VALID_BODY)
        assert resp.status_code == 201

    def test_response_contains_appointment(self, client):
        data = client.post("/appointments", json=_VALID_BODY).get_json()
        apt = data["appointment"]
        assert apt["patient_name"] == "Jordan Lee"
        assert apt["status"] == "scheduled"
        assert "id" in apt
        assert "created_at" in apt

    def test_booked_appointment_appears_in_list(self, client):
        client.post("/appointments", json=_VALID_BODY)
        data = client.get("/appointments").get_json()
        assert data["total"] == 4

    def test_missing_one_field_returns_400(self, client):
        body = {k: v for k, v in _VALID_BODY.items() if k != "doctor_name"}
        resp = client.post("/appointments", json=body)
        assert resp.status_code == 400
        assert "doctor_name" in resp.get_json()["fields"]

    def test_missing_all_fields_returns_400(self, client):
        resp = client.post("/appointments", json={})
        assert resp.status_code == 400

    def test_malformed_json_returns_400(self, client):
        resp = client.post(
            "/appointments",
            data="{ this is : not valid json }",
            content_type="application/json",
        )
        assert resp.status_code == 400

    def test_empty_body_returns_400(self, client):
        resp = client.post(
            "/appointments",
            data="",
            content_type="application/json",
        )
        assert resp.status_code == 400

    def test_wrong_content_type_returns_415(self, client):
        resp = client.post(
            "/appointments",
            data=json.dumps(_VALID_BODY),
            content_type="text/plain",
        )
        assert resp.status_code == 415

    def test_whitespace_only_field_returns_400(self, client):
        resp = client.post("/appointments", json={**_VALID_BODY, "patient_name": "   "})
        assert resp.status_code == 400

    def test_non_string_field_returns_400(self, client):
        resp = client.post("/appointments", json={**_VALID_BODY, "date": 20261201})
        assert resp.status_code == 400

    def test_extra_fields_are_ignored(self, client):
        body = {**_VALID_BODY, "insurance_id": "XYZ-999", "notes": "bring records"}
        resp = client.post("/appointments", json=body)
        assert resp.status_code == 201
        apt = resp.get_json()["appointment"]
        assert "insurance_id" not in apt
        assert "notes" not in apt

    def test_leading_trailing_whitespace_is_trimmed(self, client):
        body = {**_VALID_BODY, "patient_name": "  Jordan Lee  "}
        apt = client.post("/appointments", json=body).get_json()["appointment"]
        assert apt["patient_name"] == "Jordan Lee"

    def test_multiple_books_get_unique_ids(self, client):
        id1 = client.post("/appointments", json=_VALID_BODY).get_json()["appointment"]["id"]
        id2 = client.post("/appointments", json=_VALID_BODY).get_json()["appointment"]["id"]
        assert id1 != id2


# ---------------------------------------------------------------------------
# DELETE /appointments/<apt_id>
# ---------------------------------------------------------------------------

class TestCancelAppointment:
    def test_cancel_existing_returns_200(self, client):
        resp = client.delete("/appointments/apt-001")
        assert resp.status_code == 200

    def test_cancel_sets_status_to_cancelled(self, client):
        data = client.delete("/appointments/apt-001").get_json()
        assert data["appointment"]["status"] == "cancelled"

    def test_cancelled_status_persists_in_list(self, client):
        client.delete("/appointments/apt-001")
        appointments = client.get("/appointments").get_json()["appointments"]
        apt = next(a for a in appointments if a["id"] == "apt-001")
        assert apt["status"] == "cancelled"

    def test_cancel_nonexistent_id_returns_404(self, client):
        assert client.delete("/appointments/does-not-exist").status_code == 404

    def test_cancel_already_cancelled_returns_409(self, client):
        client.delete("/appointments/apt-002")
        resp = client.delete("/appointments/apt-002")
        assert resp.status_code == 409

    def test_cancel_random_string_id_returns_404(self, client):
        assert client.delete("/appointments/not-a-valid-id-xyz").status_code == 404

    def test_cancel_does_not_remove_from_list(self, client):
        client.delete("/appointments/apt-003")
        data = client.get("/appointments").get_json()
        assert data["total"] == 3
