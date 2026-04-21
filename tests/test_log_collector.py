"""Tests for LogCollector service."""

from __future__ import annotations

from meshcore_dashboard.services.log_collector import LogCollector


def _make_buffer(lines: list[str]) -> str:
    """Simulate device log output."""
    body = "\r\n".join(lines)
    return f"log\r\n{body}\r\n  ->    EOF\r\n"


def test_first_snapshot_inserts_all():
    """First collection with no prior state inserts all lines."""
    collector = LogCollector()
    lines = [
        "02:28:25 - 16/5/2024 U: RX, len=37 (type=0, route=F, payload_len=20) SNR=12 RSSI=-22 score=1000",
        "02:28:26 - 16/5/2024 U: TX, len=37 (type=0, route=F, payload_len=20)",
    ]
    result = collector.process_buffer(_make_buffer(lines), prior_fingerprints=set())
    assert result.lines_seen == 2
    assert result.inserted == 2
    assert result.duplicates_skipped == 0
    assert result.buffer_changed is True
    assert len(result.parsed_lines) == 2


def test_unchanged_buffer_inserts_none():
    """Same buffer twice inserts nothing the second time."""
    collector = LogCollector()
    lines = [
        "02:28:25 - 16/5/2024 U: RX, len=37 (type=0, route=F, payload_len=20) SNR=12 RSSI=-22 score=1000",
    ]
    raw = _make_buffer(lines)
    r1 = collector.process_buffer(raw, prior_fingerprints=set())
    r2 = collector.process_buffer(
        raw,
        prior_fingerprints={p.fingerprint for p in r1.parsed_lines},
    )
    assert r2.inserted == 0
    assert r2.duplicates_skipped == 1
    assert r2.buffer_changed is False


def test_partial_overlap_inserts_new_only():
    """Circular buffer with overlap inserts only new entries."""
    collector = LogCollector()
    old_lines = [
        "02:28:25 - 16/5/2024 U: RX, len=37 (type=0, route=F, payload_len=20) SNR=12 RSSI=-22 score=1000",
        "02:28:26 - 16/5/2024 U: TX, len=37 (type=0, route=F, payload_len=20)",
    ]
    r1 = collector.process_buffer(_make_buffer(old_lines), prior_fingerprints=set())
    prior = {p.fingerprint for p in r1.parsed_lines}

    new_lines = [
        "02:28:26 - 16/5/2024 U: TX, len=37 (type=0, route=F, payload_len=20)",
        "02:28:30 - 16/5/2024 U: RX, len=50 (type=5, route=F, payload_len=35) SNR=11 RSSI=-19 score=960",
    ]
    r2 = collector.process_buffer(_make_buffer(new_lines), prior_fingerprints=prior)
    assert r2.inserted == 1
    assert r2.duplicates_skipped == 1


def test_buffer_hash_changes():
    """Different buffers produce different hashes."""
    collector = LogCollector()
    buf1 = _make_buffer([
        "02:28:25 - 16/5/2024 U: RX, len=37 (type=0, route=F, payload_len=20) SNR=12 RSSI=-22 score=1000"
    ])
    buf2 = _make_buffer([
        "02:28:26 - 16/5/2024 U: TX, len=37 (type=0, route=F, payload_len=20)"
    ])
    r1 = collector.process_buffer(buf1, prior_fingerprints=set())
    r2 = collector.process_buffer(buf2, prior_fingerprints=set())
    assert r1.buffer_hash != r2.buffer_hash
