"""Tests for app settings."""

import os

import pytest

from meshcore_dashboard.config import Settings


@pytest.fixture(autouse=True)
def _clean_env():
    """Clean auth env vars before each test."""
    for key in (
        "BASIC_AUTH_USER",
        "BASIC_AUTH_PASS",
        "AUTH_DISABLED",
        "READ_ONLY",
    ):
        os.environ.pop(key, None)
    yield
    for key in (
        "BASIC_AUTH_USER",
        "BASIC_AUTH_PASS",
        "AUTH_DISABLED",
        "READ_ONLY",
    ):
        os.environ.pop(key, None)


def test_settings_defaults():
    os.environ["BASIC_AUTH_USER"] = "admin"
    os.environ["BASIC_AUTH_PASS"] = "secret"
    s = Settings()
    assert s.serial_port == "/dev/ttyACM0"
    assert s.serial_baud == 115200
    assert s.poll_interval_default == 60
    assert s.poll_interval_live == 10
    assert s.live_mode_ttl == 30
    assert s.read_only is False
    assert s.auth_disabled is False


def test_settings_fail_closed_no_auth():
    with pytest.raises(ValueError, match="BASIC_AUTH_USER"):
        Settings()


def test_settings_auth_disabled_explicit():
    os.environ["AUTH_DISABLED"] = "1"
    s = Settings()
    assert s.auth_disabled is True
