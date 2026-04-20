"""Tests for read-only middleware."""

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from meshcore_dashboard.middleware.readonly import ReadOnlyMiddleware


@pytest.fixture
def app_readonly():
    app = FastAPI()
    app.add_middleware(ReadOnlyMiddleware)

    @app.get("/api/stats")
    def stats():
        return {"data": []}

    @app.put("/api/config/name")
    def set_config():
        return {"ok": True}

    @app.post("/api/command")
    def command():
        return {"output": ""}

    return app


def test_get_allowed(app_readonly):
    client = TestClient(app_readonly)
    assert client.get("/api/stats").status_code == 200


def test_put_blocked(app_readonly):
    client = TestClient(app_readonly)
    r = client.put("/api/config/name", json={"value": "x"})
    assert r.status_code == 403


def test_post_blocked(app_readonly):
    client = TestClient(app_readonly)
    r = client.post("/api/command", json={"command": "ver"})
    assert r.status_code == 403
