"""Tests for auth middleware."""

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from meshcore_dashboard.middleware.auth import BasicAuthMiddleware


@pytest.fixture
def app_with_auth():
    app = FastAPI()
    app.add_middleware(BasicAuthMiddleware, username="admin", password="secret")

    @app.get("/api/health")
    def health():
        return {"status": "ok"}

    @app.get("/api/stats")
    def stats():
        return {"data": []}

    return app


def test_health_no_auth_required(app_with_auth):
    client = TestClient(app_with_auth)
    r = client.get("/api/health")
    assert r.status_code == 200


def test_protected_route_no_creds(app_with_auth):
    client = TestClient(app_with_auth)
    r = client.get("/api/stats")
    assert r.status_code == 401


def test_protected_route_valid_creds(app_with_auth):
    client = TestClient(app_with_auth)
    r = client.get("/api/stats", auth=("admin", "secret"))
    assert r.status_code == 200


def test_protected_route_wrong_creds(app_with_auth):
    client = TestClient(app_with_auth)
    r = client.get("/api/stats", auth=("admin", "wrong"))
    assert r.status_code == 401
