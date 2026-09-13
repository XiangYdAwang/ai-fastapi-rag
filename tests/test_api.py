from fastapi.testclient import TestClient

from app.main import app


def test_health_endpoint() -> None:
    client = TestClient(app)
    response = client.get("/health")

    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


def test_openapi_contains_expected_routes() -> None:
    client = TestClient(app)
    response = client.get("/openapi.json")

    assert response.status_code == 200
    paths = response.json()["paths"]

    assert "/api/documents/upload" in paths
    assert "/api/documents/{document_id}/embed" in paths
    assert "/api/search" in paths
    assert "/api/chat" in paths
    assert "/api/chat/stream" in paths