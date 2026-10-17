from fastapi.testclient import TestClient

from src.main import create_app

client = TestClient(create_app())


def test_livez() -> None:
    assert client.get("/livez").json() == {"status": "ok"}


def test_metrics() -> None:
    assert client.get("/metrics").status_code == 200


def test_api_routes_are_registered() -> None:
    assert client.get("/api/agents").status_code == 501
