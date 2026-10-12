from fastapi.testclient import TestClient

from app.main import app

client = TestClient(app)


def test_root_returns_minimal_status_response() -> None:
    response = client.get("/")

    assert response.status_code == 200
    assert response.json() == {
        "success": True,
        "data": {"status": "healthy"},
        "message": "VoltStop API is ready",
    }


def test_health_returns_standard_envelope() -> None:
    response = client.get("/api/v1/health")
    assert response.status_code == 200
    assert response.json() == {
        "success": True,
        "data": {"status": "healthy"},
        "message": "API is ready",
    }
