from __future__ import annotations

from fastapi.testclient import TestClient

from jarvis_home.main import create_app


def test_login_and_memory_api(settings):
    app = create_app(settings)
    with TestClient(app) as client:
        assert client.get("/api/health").status_code == 200
        login = client.post(
            "/api/auth/login",
            json={"username": "admin", "password": "correct-horse-battery-staple"},
        )
        assert login.status_code == 200
        token = login.json()["token"]
        headers = {"Authorization": f"Bearer {token}"}
        created = client.post(
            "/api/memory",
            headers=headers,
            json={"content": "api memory", "importance": 7, "tags": ["api"]},
        )
        assert created.status_code == 200
        found = client.get("/api/memory?q=api", headers=headers)
        assert found.status_code == 200
        assert found.json()[0]["content"] == "api memory"


def test_unauthenticated_api_rejected(settings):
    app = create_app(settings)
    with TestClient(app) as client:
        assert client.get("/api/memory").status_code == 401
