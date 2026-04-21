"""Config API routes with safety confirmation and changelog."""

from __future__ import annotations

from datetime import UTC, datetime

from fastapi import APIRouter, HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from meshcore_dashboard.models import ConfigChangelog, ConfigCurrent
from meshcore_dashboard.schemas import (
    ConfigChangelogEntry,
    ConfigEntry,
    ConfigSetRequest,
)
from meshcore_dashboard.serial.connection import RepeaterConnection

router = APIRouter()

_session_factory_ref: async_sessionmaker[AsyncSession] | None = None
_connection_ref: RepeaterConnection | None = None

# Critical params require typed confirmation
CRITICAL_PARAMS = {"freq", "bw", "sf", "cr", "tx_power"}

# Password keys are masked on read
PASSWORD_KEYS = {"password", "guest", "guest.password"}
MASKED_VALUE = "***"


def _mask_value(key: str, value: str | None) -> str | None:
    return MASKED_VALUE if key in PASSWORD_KEYS and value is not None else value


def _mask_changelog_entry(entry: ConfigChangelog) -> ConfigChangelogEntry:
    return ConfigChangelogEntry(
        id=entry.id,
        timestamp=entry.timestamp,
        key=entry.key,
        old_value=_mask_value(entry.key, entry.old_value),
        new_value=_mask_value(entry.key, entry.new_value),
        source=entry.source,
    )


def set_dependencies(
    connection: RepeaterConnection,
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    global _connection_ref, _session_factory_ref
    _connection_ref = connection
    _session_factory_ref = session_factory


@router.get("/api/config")
async def get_all_config() -> list[ConfigEntry]:
    """All config key/values. Password keys masked."""
    assert _session_factory_ref
    async with _session_factory_ref() as session:
        result = await session.execute(
            select(ConfigCurrent).order_by(ConfigCurrent.key)
        )
        rows = result.scalars().all()
        entries = []
        for row in rows:
            value = _mask_value(row.key, row.value)
            entries.append(
                ConfigEntry(
                    key=row.key,
                    value=value,
                    updated_at=row.updated_at,
                )
            )
        return entries


@router.get("/api/config/changelog")
async def get_changelog() -> list[ConfigChangelogEntry]:
    """Config change history."""
    assert _session_factory_ref
    async with _session_factory_ref() as session:
        result = await session.execute(
            select(ConfigChangelog).order_by(ConfigChangelog.timestamp.desc())
        )
        rows = result.scalars().all()
        return [_mask_changelog_entry(row) for row in rows]


@router.get("/api/config/{key}")
async def get_config_key(key: str) -> ConfigEntry:
    """Single key read from DB."""
    assert _session_factory_ref
    async with _session_factory_ref() as session:
        result = await session.execute(
            select(ConfigCurrent).where(ConfigCurrent.key == key)
        )
        row = result.scalar_one_or_none()
        if not row:
            raise HTTPException(status_code=404, detail=f"Key '{key}' not found")
        value = _mask_value(key, row.value)
        return ConfigEntry(key=row.key, value=value, updated_at=row.updated_at)


@router.put("/api/config/{key}")
async def set_config_key(key: str, body: ConfigSetRequest) -> ConfigChangelogEntry:
    """Set a config value. Critical params require confirm_value."""
    assert _connection_ref
    assert _session_factory_ref

    # Critical param safety check
    if key in CRITICAL_PARAMS and body.confirm_value != body.value:
        raise HTTPException(
            status_code=400,
            detail="Critical parameter requires confirm_value matching value",
        )

    # Read current value from device (pre-change snapshot)
    try:
        old_value = await _connection_ref.get_config_value(key)
    except Exception:
        old_value = None

    # Write new value to device
    await _connection_ref.set_config_value(key, body.value)

    now = datetime.now(UTC)

    # Update config_current and write changelog
    async with _session_factory_ref() as session:
        # Upsert config_current
        existing = await session.execute(
            select(ConfigCurrent).where(ConfigCurrent.key == key)
        )
        row = existing.scalar_one_or_none()
        if row:
            row.value = body.value
            row.updated_at = now
        else:
            session.add(ConfigCurrent(key=key, value=body.value, updated_at=now))

        # Write changelog
        changelog = ConfigChangelog(
            timestamp=now,
            key=key,
            old_value=old_value,
            new_value=body.value,
            source="user",
        )
        session.add(changelog)
        await session.commit()
        await session.refresh(changelog)

        return _mask_changelog_entry(changelog)


@router.post("/api/config/{key}/revert")
async def revert_config_key(key: str) -> ConfigChangelogEntry:
    """Revert to old_value from most recent changelog entry."""
    assert _connection_ref
    assert _session_factory_ref

    async with _session_factory_ref() as session:
        # Find most recent changelog for this key
        result = await session.execute(
            select(ConfigChangelog)
            .where(ConfigChangelog.key == key)
            .order_by(ConfigChangelog.timestamp.desc())
            .limit(1)
        )
        entry = result.scalar_one_or_none()
        if not entry or entry.old_value is None:
            raise HTTPException(
                status_code=404,
                detail=f"No revertible changelog for '{key}'",
            )

        # Write the old value back to device
        await _connection_ref.set_config_value(key, entry.old_value)

        now = datetime.now(UTC)

        # Update config_current
        cfg_result = await session.execute(
            select(ConfigCurrent).where(ConfigCurrent.key == key)
        )
        cfg = cfg_result.scalar_one_or_none()
        if cfg:
            cfg.value = entry.old_value
            cfg.updated_at = now

        # Write new changelog entry for the revert
        revert_entry = ConfigChangelog(
            timestamp=now,
            key=key,
            old_value=entry.new_value,
            new_value=entry.old_value,
            source="user",
        )
        session.add(revert_entry)
        await session.commit()
        await session.refresh(revert_entry)

        return _mask_changelog_entry(revert_entry)
