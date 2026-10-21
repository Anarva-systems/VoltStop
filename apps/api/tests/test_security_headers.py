from fastapi.testclient import TestClient

from app.main import app


def test_security_headers_apply_to_success_and_error_responses():
    with TestClient(app) as client:
        success = client.get("/api/v1/health")
        error = client.get("/api/v1/bookings")

    assert success.status_code == 200
    for response in (success, error):
        assert response.headers.get("X-Content-Type-Options") == "nosniff"
        assert response.headers.get("X-Frame-Options") == "DENY"
        assert response.headers.get("Referrer-Policy") == "no-referrer"
        assert "camera=()" in response.headers.get("Permissions-Policy", "")
        assert "Strict-Transport-Security" not in response.headers


def test_hsts_is_emitted_only_over_https():
    with TestClient(app, base_url="https://voltstop.test") as client:
        response = client.get("/api/v1/health")
    assert response.status_code == 200
    assert response.headers.get("Strict-Transport-Security") == "max-age=31536000; includeSubDomains"
