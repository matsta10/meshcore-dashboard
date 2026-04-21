"""Parse repeater serial responses."""

from __future__ import annotations

import json


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
