"""Tests for poller log persistence edge cases."""

from __future__ import annotations

import json
from datetime import UTC, datetime

import pytest
from sqlalchemy import select

from meshcore_dashboard.database import create_engine_and_tables
from meshcore_dashboard.models import LogCollectionState, PacketLog
from meshcore_dashboard.routers import websocket as ws_router
from meshcore_dashboard.serial.parser import parse_log_line
from meshcore_dashboard.services.poller import Poller


def _make_buffer(lines: list[str]) -> str:
    body = "\r\n".join(lines)
    return f"log\r\n{body}\r\n  ->    EOF\r\n"


class _FakeConnection:
    def __init__(self, raw: str) -> None:
        self.raw = raw

    async def send_command(self, cmd: str, timeout: float = 1.0) -> str:
        assert cmd == "log"
        return self.raw


@pytest.mark.anyio
async def test_collect_logs_survives_batch_collision_and_persists_new_rows(monkeypatch):
    engine, session_factory = await create_engine_and_tables("sqlite+aiosqlite://")
    duplicate_line = (
        "19:20:24 - 21/4/2026 U: RX, len=64 (type=8, route=F, payload_len=36) "
        "SNR=13 RSSI=-20 score=1000 [E9 -> 04]"
    )
    new_line = (
        "19:20:42 - 21/4/2026 U: TX, len=76 (type=8, route=F, payload_len=36) "
        "[E9 -> 04]"
    )
    raw = _make_buffer([duplicate_line, new_line])
    duplicate = parse_log_line(duplicate_line)

    async with session_factory() as session:
        session.add(
            PacketLog(
                collected_at=datetime.now(UTC),
                raw_line=duplicate.raw_line,
                fingerprint=duplicate.fingerprint,
                parse_status=duplicate.parse_status,
                direction=duplicate.direction,
                packet_type=duplicate.packet_type,
                route=duplicate.route,
                payload_len=duplicate.payload_len,
                total_len=duplicate.total_len,
                snr=duplicate.snr,
                rssi=duplicate.rssi,
                score=duplicate.score,
                src_addr=duplicate.src_addr,
                dst_addr=duplicate.dst_addr,
                device_time_text=duplicate.device_time_text,
                device_date_text=duplicate.device_date_text,
            )
        )
        session.add(
            LogCollectionState(
                id=1,
                last_polled_at=datetime.now(UTC),
                last_snapshot_json=json.dumps([]),
                unchanged_buffer_count=0,
            )
        )
        await session.commit()

    async def _noop_broadcast(_: object) -> None:
        return None

    monkeypatch.setattr(ws_router, "broadcast", _noop_broadcast)

    poller = Poller(connection=_FakeConnection(raw), session_factory=session_factory)
    await poller._collect_logs()

    async with session_factory() as session:
        result = await session.execute(
            select(PacketLog).order_by(PacketLog.collected_at.asc())
        )
        rows = result.scalars().all()
        assert len(rows) == 2
        assert {row.raw_line for row in rows} == {duplicate_line, new_line}

        state = await session.get(LogCollectionState, 1)
        assert state is not None
        assert state.last_new_entry_at is not None
        assert state.unchanged_buffer_count == 0

    await engine.dispose()
