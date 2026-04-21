"""Tests for serial response parser."""

import pytest

from meshcore_dashboard.serial.parser import (
    ParseError,
    parse_config_value,
    parse_log_line,
    parse_log_lines,
    parse_response_lines,
    parse_stats_json,
)


def test_parse_response_lines():
    raw = "  -> line1\r\n  -> line2\r\nignored\r\n  -> line3\r\n"
    assert parse_response_lines(raw) == [
        "line1",
        "line2",
        "line3",
    ]


def test_parse_response_lines_empty():
    assert parse_response_lines("") == []
    assert parse_response_lines("no prefix here\r\n") == []


def test_parse_stats_json():
    raw = '  -> {"battery_mv": 4168, "uptime_secs": 120}\r\n'
    result = parse_stats_json(raw)
    assert result["battery_mv"] == 4168
    assert result["uptime_secs"] == 120


def test_parse_stats_json_multiline():
    raw = '  -> {"battery_mv": 4168,\r\n  -> "uptime_secs": 120}\r\n'
    result = parse_stats_json(raw)
    assert result["battery_mv"] == 4168


def test_parse_stats_json_invalid():
    with pytest.raises(ParseError):
        parse_stats_json("  -> not json\r\n")


def test_parse_stats_json_no_lines():
    with pytest.raises(ParseError):
        parse_stats_json("nothing here")


def test_parse_config_value():
    raw = "  -> > 915.0\r\n"
    assert parse_config_value(raw) == "915.0"


def test_parse_config_value_with_spaces():
    raw = "  -> > Blue Orchid\r\n"
    assert parse_config_value(raw) == "Blue Orchid"


def test_parse_config_value_missing():
    with pytest.raises(ParseError):
        parse_config_value("  -> no angle bracket\r\n")


def test_parse_log_lines():
    raw = (
        "log\r\n"
        "12:34:56 - 21/4/2026 U: packet one\r\n"
        "  -> ignored status\r\n"
        "12:34:57 - 21/4/2026 D: packet two\r\n"
        "EOF\r\n"
    )
    assert parse_log_lines(raw) == [
        "12:34:56 - 21/4/2026 U: packet one",
        "12:34:57 - 21/4/2026 D: packet two",
    ]


def test_parse_log_line_rx():
    """RX line with SNR/RSSI/score."""
    line = (
        "02:28:25 - 16/5/2024 U: RX, len=37"
        " (type=0, route=F, payload_len=20)"
        " SNR=12 RSSI=-22 score=1000 [5B -> 30]"
    )
    result = parse_log_line(line)
    assert result.direction == "RX"
    assert result.device_time_text == "02:28:25"
    assert result.device_date_text == "16/5/2024"
    assert result.packet_type == 0
    assert result.route == "F"
    assert result.payload_len == 20
    assert result.snr == 12.0
    assert result.rssi == -22
    assert result.parse_status == "parsed"
    assert result.raw_line == line


def test_parse_log_line_tx():
    """TX line without SNR/RSSI."""
    line = (
        "02:28:26 - 16/5/2024 U: TX, len=37"
        " (type=0, route=F, payload_len=20) [5B -> 30]"
    )
    result = parse_log_line(line)
    assert result.direction == "TX"
    assert result.snr is None
    assert result.rssi is None
    assert result.parse_status == "parsed"


def test_parse_log_line_no_routing():
    """Line without [src -> dst] routing info."""
    line = "05:53:08 - 16/5/2024 U: TX, len=60 (type=5, route=F, payload_len=35)"
    result = parse_log_line(line)
    assert result.direction == "TX"
    assert result.packet_type == 5
    assert result.payload_len == 35
    assert result.parse_status == "parsed"


def test_parse_log_line_raw_only():
    """Unparseable but plausible line is kept as raw_only."""
    line = "some weird device output that has U: in it"
    result = parse_log_line(line)
    assert result.parse_status == "raw_only"
    assert result.raw_line == line
    assert result.direction is None


def test_parse_log_line_fingerprint_deterministic():
    """Same input produces same fingerprint."""
    line = (
        "02:28:25 - 16/5/2024 U: RX, len=37"
        " (type=0, route=F, payload_len=20)"
        " SNR=12 RSSI=-22 score=1000"
    )
    r1 = parse_log_line(line)
    r2 = parse_log_line(line)
    assert r1.fingerprint == r2.fingerprint
    assert len(r1.fingerprint) == 64  # SHA-256 hex


def test_parse_log_line_different_lines_different_fingerprints():
    """Different inputs produce different fingerprints."""
    r1 = parse_log_line(
        "02:28:25 - 16/5/2024 U: RX, len=37"
        " (type=0, route=F, payload_len=20)"
        " SNR=12 RSSI=-22 score=1000"
    )
    r2 = parse_log_line(
        "02:28:26 - 16/5/2024 U: TX, len=37 (type=0, route=F, payload_len=20)"
    )
    assert r1.fingerprint != r2.fingerprint
