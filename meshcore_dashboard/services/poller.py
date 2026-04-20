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
    StatsSnapshot,
)
from meshcore_dashboard.routers import websocket as ws_router
from meshcore_dashboard.routers.status import update_last_poll
from meshcore_dashboard.serial.connection import RepeaterConnection
from meshcore_dashboard.serial.parser import ParseError

logger = logging.getLogger(__name__)


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
            # Try to reconnect
            try:
                await self._connection.connect()
            except ConnectionError:
                return

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

        # Check for reboot
        uptime = stats_data.get("uptime_secs")
        if uptime is not None and self._connection.check_reboot(
            uptime
        ):
            logger.info("Reboot detected! Re-reading config.")
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
        # This would read known config keys and update DB
        # For now, broadcast connection status change
        await ws_router.broadcast(
            {
                "type": "connection_status",
                "data": {
                    "state": self._connection.state.value
                },
            }
        )
