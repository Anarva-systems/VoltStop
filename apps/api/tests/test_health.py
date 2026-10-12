from fastapi.testclient import TestClient

from app.main import app

client = TestClient(app)


def test_health_returns_standard_envelope() -> None:
    response = client.get("/api/v1/health")
    assert response.status_code == 200
    assert response.json() == {
        "success": True,
        "data": {"status": "healthy"},
        "message": "API is ready",
    }
