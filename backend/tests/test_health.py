from fastapi.testclient import TestClient

from main import app

client = TestClient(app)


def test_health_returns_ok_without_api_keys():
    response = client.get("/health")
    assert response.status_code == 200
    body = response.json()
    assert isinstance(body.get("request_id"), str) and body["request_id"]
    assert body.get("data") == {"status": "ok"}
