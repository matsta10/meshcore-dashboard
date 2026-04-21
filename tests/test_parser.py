"""Tests for serial response parser."""

import pytest

from meshcore_dashboard.serial.parser import (
    ParseError,
    parse_config_value,
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
