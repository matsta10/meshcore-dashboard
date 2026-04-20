"""Tests for command whitelist and classification."""

from meshcore_dashboard.serial.commands import (
    COMMAND_WHITELIST,
    get_timeout,
    is_command_allowed,
    is_destructive,
)


def test_whitelist_contains_basics():
    assert "ver" in COMMAND_WHITELIST
    assert "stats-core" in COMMAND_WHITELIST
    assert "reboot" in COMMAND_WHITELIST
    assert "advert" in COMMAND_WHITELIST


def test_blocked_commands():
    assert not is_command_allowed("set freq 915")
    assert not is_command_allowed("get prv.key")
    assert not is_command_allowed("erase")
    assert not is_command_allowed("password foo")


def test_safe_command_allowed():
    assert is_command_allowed("advert")
    assert is_command_allowed("stats-core")
    assert is_command_allowed("ver")
    assert is_command_allowed("neighbors")


def test_destructive_requires_confirm():
    assert is_destructive("reboot")
    assert is_destructive("log erase")
    assert is_destructive("clear stats")
    assert not is_destructive("advert")
    assert not is_destructive("ver")


def test_timeouts():
    assert get_timeout("stats-core") == 1.0
    assert get_timeout("ver") == 1.0
    assert get_timeout("reboot") == 10.0
    assert get_timeout("advert") == 3.0
