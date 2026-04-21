"""Shared log collection service with snapshot-diff ingestion."""

from __future__ import annotations

import hashlib
from dataclasses import dataclass, field

from meshcore_dashboard.serial.parser import (
    ParsedLogLine,
    parse_log_line,
    parse_log_lines,
)


@dataclass
class LogCollectionResult:
    """Result of a single log collection cycle."""

    lines_seen: int = 0
    parsed_lines: list[ParsedLogLine] = field(default_factory=list)
    all_fingerprints: list[str] = field(default_factory=list)
    inserted: int = 0
    duplicates_skipped: int = 0
    buffer_changed: bool = False
    buffer_hash: str = ""


class LogCollector:
    """Stateless processor for device log buffers.

    Parses raw device output into structured entries and determines
    which are new vs already-seen based on fingerprint comparison.
    """

    def process_buffer(
        self,
        raw: str,
        prior_fingerprints: set[str],
    ) -> LogCollectionResult:
        """Process a raw device log buffer.

        Args:
            raw: Raw serial output from the ``log`` command.
            prior_fingerprints: Set of fingerprints already stored
                or from the last snapshot.

        Returns:
            LogCollectionResult with parsed lines and insert/skip counts.
        """
        raw_lines = parse_log_lines(raw)
        buffer_hash = hashlib.sha256("\n".join(raw_lines).encode()).hexdigest()

        new_entries: list[ParsedLogLine] = []
        all_fps: list[str] = []
        duplicates = 0

        for line in raw_lines:
            entry = parse_log_line(line)
            all_fps.append(entry.fingerprint)
            if entry.fingerprint in prior_fingerprints:
                duplicates += 1
            else:
                new_entries.append(entry)

        return LogCollectionResult(
            lines_seen=len(raw_lines),
            parsed_lines=new_entries,
            all_fingerprints=all_fps,
            inserted=len(new_entries),
            duplicates_skipped=duplicates,
            buffer_changed=len(new_entries) > 0,
            buffer_hash=buffer_hash,
        )
