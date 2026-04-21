"""Background polling service with adaptive rate and reboot detection."""

from __future__ import annotations

import asyncio
import logging
from datetime import datetime, timezone

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from meshcore_dashboard.models import (
    ConfigChangelog,
    ConfigCurrent,
    Neighbor,
    PacketLog,
    StatsSnapshot,
)
from meshcore_dashboard.routers import websocket as ws_router
from meshcore_dashboard.routers.status import update_last_poll
from meshcore_dashboard.serial.connection import RepeaterConnection
from meshcore_dashboard.serial.parser import ParseError, parse_response_lines

logger = logging.getLogger(__name__)

# Map device JSON field names → DB column names
FIELD_REMAP = {
    "recv": "packets_recv",
    "sent": "packets_sent",
}

# How often to poll neighbors (every N poll cycles)
NEIGHBOR_POLL_INTERVAL = 10


class Poller:
    """Background task that polls the repeater at adaptive intervals."""

    def __init__(
        self,
        connection: RepeaterConnection,
        session_factory: async_sessionmaker[AsyncSession],
    ) -> None:
        self._connection = connection
        self._session_factory = session_factory
        self._task: asyncio.Task | None = None  # type: ignore[type-arg]
        self._poll_count = 0
        self._log_started = False

    def start(self) -> None:
        """Start the polling loop."""
        self._task = asyncio.create_task(self._poll_loop())

    async def stop(self) -> None:
        """Stop the polling loop."""
        if self._task:
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass

    async def _poll_loop(self) -> None:
        """Main polling loop with adaptive interval."""
        while True:
            try:
                await self._do_poll()
            except asyncio.CancelledError:
                raise
            except Exception as e:
                logger.error("Poll error: %s", e)

            interval = await ws_router.get_active_poll_interval()
            await asyncio.sleep(interval)

    async def _do_poll(self) -> None:
        """Execute one poll cycle."""
        if self._connection.state.value == "disconnected":
            try:
                await self._connection.connect()
            except ConnectionError:
                return

        self._poll_count += 1

        # Ensure packet logging is started
        if not self._log_started:
            await self._ensure_log_started()

        now = datetime.now(timezone.utc)
        stats_data: dict = {}

        # Collect stats from all three commands
        for cmd in ("stats-core", "stats-radio", "stats-packets"):
            try:
                data = await self._connection.get_stats_json(cmd)
                stats_data.update(data)
            except ParseError as e:
                logger.warning(
                    "Parse error for %s: %s (raw: %s)",
                    cmd,
                    e,
                    e.raw,
                )
            except (ConnectionError, TimeoutError) as e:
                logger.warning("Command %s failed: %s", cmd, e)
                return

        if not stats_data:
            return

        # Remap device field names → DB column names
        for old_key, new_key in FIELD_REMAP.items():
            if old_key in stats_data:
                stats_data[new_key] = stats_data.pop(old_key)

        # Check for reboot
        uptime = stats_data.get("uptime_secs")
        if uptime is not None and self._connection.check_reboot(
            uptime
        ):
            logger.info("Reboot detected! Re-reading config.")
            self._log_started = False  # Re-start logging after reboot
            await self._log_reboot(uptime)
            await self._read_full_config()

        # Write stats to DB
        snapshot = StatsSnapshot(
            timestamp=now,
            battery_mv=stats_data.get("battery_mv"),
            uptime_secs=stats_data.get("uptime_secs"),
            queue_len=stats_data.get("queue_len"),
            errors=stats_data.get("errors"),
            noise_floor=stats_data.get("noise_floor"),
            last_rssi=stats_data.get("last_rssi"),
            last_snr=stats_data.get("last_snr"),
            tx_air_secs=stats_data.get("tx_air_secs"),
            rx_air_secs=stats_data.get("rx_air_secs"),
            packets_recv=stats_data.get("packets_recv"),
            packets_sent=stats_data.get("packets_sent"),
            flood_rx=stats_data.get("flood_rx"),
            flood_tx=stats_data.get("flood_tx"),
            direct_rx=stats_data.get("direct_rx"),
            direct_tx=stats_data.get("direct_tx"),
            recv_errors=stats_data.get("recv_errors"),
        )

        async with self._session_factory() as session:
            session.add(snapshot)
            await session.commit()

        update_last_poll()

        # Broadcast to WebSocket clients
        await ws_router.broadcast(
            {"type": "stats_update", "data": stats_data}
        )

        # Collect packet logs every cycle
        await self._collect_logs()

        # Poll neighbors periodically
        if self._poll_count % NEIGHBOR_POLL_INTERVAL == 0:
            await self._poll_neighbors()

    async def _log_reboot(self, new_uptime: int) -> None:
        """Log reboot event to config_changelog."""
        async with self._session_factory() as session:
            entry = ConfigChangelog(
                timestamp=datetime.now(timezone.utc),
                key="_meta.reboot",
                old_value=str(
                    self._connection._last_uptime or "unknown"
                ),
                new_value=str(new_uptime),
                source="detected",
            )
            session.add(entry)
            await session.commit()

    async def _read_full_config(self) -> None:
        """Read all config from device and detect drift."""
        # For now, broadcast connection status change
        await ws_router.broadcast(
            {
                "type": "connection_status",
                "data": {
                    "state": self._connection.state.value
                },
            }
        )

    async def _ensure_log_started(self) -> None:
        """Send 'log start' to enable packet logging on device."""
        try:
            await self._connection.send_command(
                "log start", timeout=3.0
            )
            self._log_started = True
            logger.info("Packet logging started on device")
        except (ConnectionError, TimeoutError) as e:
            logger.warning("Failed to start logging: %s", e)

    async def _collect_logs(self) -> None:
        """Fetch log buffer from device and store new entries."""
        try:
            raw = await self._connection.send_command(
                "log", timeout=1.0
            )
        except (ConnectionError, TimeoutError):
            return

        now = datetime.now(timezone.utc)
        entries: list[PacketLog] = []

        for line in raw.splitlines():
            # Skip command echo, EOF markers, and response prefixes
            stripped = line.strip()
            if (
                not stripped
                or stripped == "log"
                or stripped == "EOF"
                or stripped.startswith("  ->")
            ):
                # Check if it's an EOF line
                if stripped.startswith("  ->") and "EOF" in stripped:
                    continue
                # Skip response prefix lines that aren't log data
                if stripped.startswith("  ->"):
                    continue
                continue
            # Log lines look like: "HH:MM:SS - DD/M/YYYY U: ..."
            # or just any non-prefix line with actual data
            if " U: " in line or " D: " in line:
                entries.append(
                    PacketLog(timestamp=now, raw_line=stripped)
                )

        if entries:
            async with self._session_factory() as session:
                session.add_all(entries)
                await session.commit()
            logger.debug("Stored %d log entries", len(entries))

    async def _poll_neighbors(self) -> None:
        """Fetch neighbors and upsert into DB."""
        try:
            raw = await self._connection.send_command(
                "neighbors", timeout=1.0
            )
        except (ConnectionError, TimeoutError):
            return

        now = datetime.now(timezone.utc)
        lines = parse_response_lines(raw)

        for line in lines:
            line = line.strip()
            if not line or line == "-none-":
                continue

            # Format: "PUBKEY:RSSI:SNR" e.g. "02ED23CC:9381:54"
            parts = line.split(":")
            if len(parts) < 1:
                continue

            pub_key = parts[0]
            rssi = None
            snr = None
            if len(parts) >= 2:
                try:
                    rssi = int(parts[1])
                except ValueError:
                    pass
            if len(parts) >= 3:
                try:
                    snr = float(parts[2])
                except ValueError:
                    pass

            async with self._session_factory() as session:
                result = await session.execute(
                    select(Neighbor).where(
                        Neighbor.public_key == pub_key
                    )
                )
                existing = result.scalar_one_or_none()
                if existing:
                    existing.last_seen = now
                    existing.last_rssi = rssi
                    existing.last_snr = snr
                else:
                    session.add(
                        Neighbor(
                            public_key=pub_key,
                            first_seen=now,
                            last_seen=now,
                            last_rssi=rssi,
                            last_snr=snr,
                        )
                    )
                await session.commit()

        # Broadcast neighbor update
        await ws_router.broadcast(
            {"type": "neighbors_update", "data": {}}
        )
