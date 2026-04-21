"""Parse repeater serial responses."""

from __future__ import annotations

import hashlib
import json
import re
from dataclasses import dataclass


class ParseError(Exception):
    """Raised when a serial response cannot be parsed."""

    def __init__(self, message: str, raw: str = ""):
        super().__init__(message)
        self.raw = raw


RESPONSE_PREFIX = "  -> "
CONFIG_PREFIX = "  -> > "


def parse_response_lines(raw: str) -> list[str]:
    """Extract data lines from serial response."""
    lines = []
    for line in raw.splitlines():
        if line.startswith(RESPONSE_PREFIX):
            lines.append(line[len(RESPONSE_PREFIX) :])
    return lines


def parse_stats_json(raw: str) -> dict:
    """Parse a JSON stats response from the repeater."""
    lines = parse_response_lines(raw)
    if not lines:
        raise ParseError("No response lines found", raw)
    combined = " ".join(lines)
    try:
        return json.loads(combined)
    except json.JSONDecodeError as e:
        raise ParseError(f"Invalid JSON: {e}", raw) from e


def parse_config_value(raw: str) -> str:
    """Extract a config value from a 'get' response."""
    for line in raw.splitlines():
        if line.startswith(CONFIG_PREFIX):
            return line[len(CONFIG_PREFIX) :]
    raise ParseError("No config value line found", raw)


def parse_log_lines(raw: str) -> list[str]:
    """Extract packet log lines from a log dump response."""
    lines: list[str] = []
    for line in raw.splitlines():
        stripped = line.strip()
        if (
            not stripped
            or stripped == "log"
            or "EOF" in stripped
            or stripped.startswith(RESPONSE_PREFIX)
        ):
            continue
        if " U: " in stripped or " D: " in stripped:
            lines.append(stripped)
    return lines


@dataclass
class ParsedLogLine:
    """Structured representation of a device packet log line."""

    raw_line: str
    fingerprint: str
    parse_status: str  # "parsed" | "raw_only"
    device_time_text: str | None = None
    device_date_text: str | None = None
    direction: str | None = None  # "RX" | "TX"
    packet_type: int | None = None
    route: str | None = None
    payload_len: int | None = None
    total_len: int | None = None
    snr: float | None = None
    rssi: int | None = None
    score: int | None = None
    src_addr: str | None = None
    dst_addr: str | None = None


# Pattern: "HH:MM:SS - DD/M/YYYY U: RX|TX, len=N (type=N, route=X, payload_len=N) ..."
_LOG_LINE_RE = re.compile(
    r"(?P<time>\d{2}:\d{2}:\d{2})\s*-\s*"
    r"(?P<date>\d{1,2}/\d{1,2}/\d{4})\s+"
    r"[UD]:\s*(?P<dir>RX|TX),\s*len=(?P<totlen>\d+)\s*"
    r"\(type=(?P<type>\d+),\s*route=(?P<route>\w+),"
    r"\s*payload_len=(?P<plen>\d+)\)"
    r"(?:\s+SNR=(?P<snr>[-\d.]+))?"
    r"(?:\s+RSSI=(?P<rssi>[-\d]+))?"
    r"(?:\s+score=(?P<score>\d+))?"
    r"(?:\s+\[(?P<src>[A-Fa-f0-9]+)\s*->\s*(?P<dst>[A-Fa-f0-9]+)\])?"
)


def _compute_fingerprint(raw_line: str) -> str:
    """SHA-256 hex digest of the raw line."""
    return hashlib.sha256(raw_line.encode()).hexdigest()


def parse_log_line(raw_line: str) -> ParsedLogLine:
    """Parse a single device log line into structured fields."""
    fp = _compute_fingerprint(raw_line)
    m = _LOG_LINE_RE.search(raw_line)
    if not m:
        return ParsedLogLine(
            raw_line=raw_line,
            fingerprint=fp,
            parse_status="raw_only",
        )
    return ParsedLogLine(
        raw_line=raw_line,
        fingerprint=fp,
        parse_status="parsed",
        device_time_text=m.group("time"),
        device_date_text=m.group("date"),
        direction=m.group("dir"),
        packet_type=int(m.group("type")),
        route=m.group("route"),
        payload_len=int(m.group("plen")),
        total_len=int(m.group("totlen")),
        snr=float(m.group("snr")) if m.group("snr") else None,
        rssi=int(m.group("rssi")) if m.group("rssi") else None,
        score=int(m.group("score")) if m.group("score") else None,
        src_addr=m.group("src"),
        dst_addr=m.group("dst"),
    )
