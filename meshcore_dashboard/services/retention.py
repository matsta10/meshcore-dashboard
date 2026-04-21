"""Stats downsampling and backup service."""

from __future__ import annotations

import asyncio
import logging
import subprocess
from contextlib import suppress
from datetime import UTC, datetime, timedelta

from sqlalchemy import delete, func, select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from meshcore_dashboard.models import (
    StatsDaily,
    StatsHourly,
    StatsSnapshot,
)

logger = logging.getLogger(__name__)

# Gauge columns: averaged during downsampling
GAUGE_COLUMNS = [
    "battery_mv",
    "queue_len",
    "errors",
    "noise_floor",
    "last_rssi",
    "last_snr",
]

# Counter columns: take last value in window
COUNTER_COLUMNS = [
    "packets_recv",
    "packets_sent",
    "flood_rx",
    "flood_tx",
    "direct_rx",
    "direct_tx",
    "recv_errors",
    "tx_air_secs",
    "rx_air_secs",
    "uptime_secs",
]


class RetentionService:
    """Runs daily to downsample stats and backup DB."""

    def __init__(
        self,
        session_factory: async_sessionmaker[AsyncSession],
        db_path: str,
        backup_path: str | None = None,
    ) -> None:
        self._session_factory = session_factory
        self._db_path = db_path
        self._backup_path = backup_path
        self._task: asyncio.Task | None = None  # type: ignore[type-arg]

    def start(self) -> None:
        """Start the retention scheduler."""
        self._task = asyncio.create_task(self._schedule_loop())

    async def stop(self) -> None:
        """Stop the retention scheduler."""
        if self._task:
            self._task.cancel()
            with suppress(asyncio.CancelledError):
                await self._task

    async def _schedule_loop(self) -> None:
        """Run retention daily at 03:00 UTC."""
        while True:
            now = datetime.now(UTC)
            # Calculate next 03:00 UTC
            next_run = now.replace(
                hour=3, minute=0, second=0, microsecond=0
            )
            if next_run <= now:
                next_run += timedelta(days=1)

            wait_seconds = (next_run - now).total_seconds()
            await asyncio.sleep(wait_seconds)

            try:
                await self.run_retention()
            except Exception as e:
                logger.error("Retention job failed: %s", e)

    async def run_retention(self) -> None:
        """Execute the full retention cycle."""
        logger.info("Starting retention job")

        now = datetime.now(UTC)
        seven_days_ago = now - timedelta(days=7)
        ninety_days_ago = now - timedelta(days=90)

        # Downsample raw -> hourly (older than 7 days)
        await self._downsample_to_hourly(seven_days_ago)

        # Downsample hourly -> daily (older than 90 days)
        await self._downsample_to_daily(ninety_days_ago)

        # Delete old raw data
        async with self._session_factory() as session:
            await session.execute(
                delete(StatsSnapshot).where(
                    StatsSnapshot.timestamp < seven_days_ago
                )
            )
            await session.execute(
                delete(StatsHourly).where(
                    StatsHourly.timestamp < ninety_days_ago
                )
            )
            await session.commit()

        # Backup
        if self._backup_path:
            self._run_backup()

        logger.info("Retention job complete")

    async def _downsample_to_hourly(
        self, before: datetime
    ) -> None:
        """Average gauges, take last value for counters."""
        async with self._session_factory() as session:
            # Get distinct hours that need downsampling
            result = await session.execute(
                select(
                    func.strftime(
                        "%Y-%m-%d %H:00:00",
                        StatsSnapshot.timestamp,
                    ).label("hour")
                )
                .where(StatsSnapshot.timestamp < before)
                .group_by("hour")
            )
            hours = [row[0] for row in result.all()]

            for hour_str in hours:
                hour_start = datetime.strptime(
                    hour_str, "%Y-%m-%d %H:%M:%S"
                ).replace(tzinfo=UTC)
                hour_end = hour_start + timedelta(hours=1)

                # Get all snapshots in this hour
                snap_result = await session.execute(
                    select(StatsSnapshot)
                    .where(
                        StatsSnapshot.timestamp >= hour_start
                    )
                    .where(StatsSnapshot.timestamp < hour_end)
                    .order_by(StatsSnapshot.timestamp.asc())
                )
                snapshots = snap_result.scalars().all()
                if not snapshots:
                    continue

                # Build hourly record
                hourly = StatsHourly(timestamp=hour_start)

                # Gauges: average
                for col in GAUGE_COLUMNS:
                    values = [
                        getattr(s, col)
                        for s in snapshots
                        if getattr(s, col) is not None
                    ]
                    if values:
                        avg = (
                            sum(values) // len(values)
                            if col != "last_snr"
                            else sum(values) / len(values)
                        )
                        setattr(hourly, col, avg)

                # Counters: last value
                for col in COUNTER_COLUMNS:
                    last = snapshots[-1]
                    setattr(hourly, col, getattr(last, col))

                session.add(hourly)

            await session.commit()

    async def _downsample_to_daily(
        self, before: datetime
    ) -> None:
        """Downsample hourly to daily."""
        async with self._session_factory() as session:
            result = await session.execute(
                select(
                    func.strftime(
                        "%Y-%m-%d", StatsHourly.timestamp
                    ).label("day")
                )
                .where(StatsHourly.timestamp < before)
                .group_by("day")
            )
            days = [row[0] for row in result.all()]

            for day_str in days:
                day_start = datetime.strptime(
                    day_str, "%Y-%m-%d"
                ).replace(tzinfo=UTC)
                day_end = day_start + timedelta(days=1)

                hourly_result = await session.execute(
                    select(StatsHourly)
                    .where(StatsHourly.timestamp >= day_start)
                    .where(StatsHourly.timestamp < day_end)
                    .order_by(StatsHourly.timestamp.asc())
                )
                hourlies = hourly_result.scalars().all()
                if not hourlies:
                    continue

                daily = StatsDaily(timestamp=day_start)

                for col in GAUGE_COLUMNS:
                    values = [
                        getattr(h, col)
                        for h in hourlies
                        if getattr(h, col) is not None
                    ]
                    if values:
                        avg = (
                            sum(values) // len(values)
                            if col != "last_snr"
                            else sum(values) / len(values)
                        )
                        setattr(daily, col, avg)

                for col in COUNTER_COLUMNS:
                    last = hourlies[-1]
                    setattr(daily, col, getattr(last, col))

                session.add(daily)

            await session.commit()

    def _run_backup(self) -> None:
        """Run sqlite3 .backup command."""
        try:
            date_str = datetime.now(UTC).strftime(
                "%Y%m%d"
            )
            backup_file = (
                f"{self._backup_path}/meshcore-{date_str}.db"
            )
            subprocess.run(
                [
                    "sqlite3",
                    self._db_path,
                    f".backup {backup_file}",
                ],
                check=True,
                capture_output=True,
            )
            logger.info("Backup written to %s", backup_file)
        except subprocess.CalledProcessError as e:
            logger.error("Backup failed: %s", e.stderr)
