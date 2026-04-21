"""Tests for poller parse-health tracking."""

from datetime import UTC, datetime

from meshcore_dashboard.services.poller import Poller


def test_poller_starts_not_stale():
    """Fresh poller has no parse errors."""
    poller = Poller(connection=None, session_factory=None)  # type: ignore[arg-type]
    assert poller.is_stale is False
    assert poller.last_parse_error is None


def test_poller_mark_stale():
    """Recording a parse error makes poller stale."""
    poller = Poller(connection=None, session_factory=None)  # type: ignore[arg-type]
    poller.record_parse_error("stats-core", "Invalid JSON: ...")
    assert poller.is_stale is True
    assert poller.last_parse_error == "stats-core: Invalid JSON: ..."


def test_poller_clear_stale_on_success():
    """Successful poll clears stale state."""
    poller = Poller(connection=None, session_factory=None)  # type: ignore[arg-type]
    poller.record_parse_error("stats-core", "bad data")
    assert poller.is_stale is True
    poller.clear_parse_error()
    assert poller.is_stale is False
    assert poller.last_parse_error is None


def test_poller_tracks_partial_stats_health():
    poller = Poller(connection=None, session_factory=None)  # type: ignore[arg-type]
    now = datetime.now(UTC)
    poller.record_stats_success("stats-packets", now)
    poller.record_parse_error("stats-core", "Invalid JSON")

    assert poller.stats_freshness == "partial"
    assert poller.stats_health["stats-packets"]["ok"] is True
    assert poller.stats_health["stats-packets"]["last_success_at"] == now
    assert poller.stats_health["stats-core"]["ok"] is False
    assert poller.stats_health["stats-core"]["last_error"] == "Invalid JSON"
