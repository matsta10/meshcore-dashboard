"""Command execution API route with whitelist and reboot cooldown."""

from __future__ import annotations

import time

from fastapi import APIRouter, HTTPException

from meshcore_dashboard.schemas import (
    AdminActionResponse,
    ClockSetRequest,
    CommandRequest,
    CommandResponse,
)
from meshcore_dashboard.serial.commands import (
    get_timeout,
    is_command_allowed,
    is_destructive,
)
from meshcore_dashboard.serial.connection import RepeaterConnection

router = APIRouter()

_connection_ref: RepeaterConnection | None = None
_last_reboot_time: float = 0.0
REBOOT_COOLDOWN = 60  # seconds


def set_dependencies(connection: RepeaterConnection) -> None:
    global _connection_ref
    _connection_ref = connection


@router.post("/api/command")
async def execute_command(body: CommandRequest) -> CommandResponse:
    """Execute a whitelisted CLI command."""
    global _last_reboot_time
    assert _connection_ref

    cmd = body.command.strip()

    # Whitelist check
    if not is_command_allowed(cmd):
        raise HTTPException(
            status_code=403,
            detail=f"Command '{cmd}' is not allowed",
        )

    # Destructive commands require confirmation
    if is_destructive(cmd) and not body.confirm:
        raise HTTPException(
            status_code=400,
            detail="Destructive command requires confirm=true",
        )

    # Reboot cooldown
    if cmd.lower() == "reboot":
        elapsed = time.time() - _last_reboot_time
        if elapsed < REBOOT_COOLDOWN:
            remaining = int(REBOOT_COOLDOWN - elapsed)
            raise HTTPException(
                status_code=429,
                detail=f"Reboot cooldown: {remaining}s remaining",
            )

    # Execute
    timeout = get_timeout(cmd)
    output = await _connection_ref.send_command(cmd, timeout=timeout)

    # Track reboot time
    if cmd.lower() == "reboot":
        _last_reboot_time = time.time()

    return CommandResponse(output=output)


@router.post("/api/admin/clock/read")
async def read_clock() -> CommandResponse:
    """Read the repeater clock."""
    assert _connection_ref
    output = await _connection_ref.send_command("clock", timeout=1.0)
    return CommandResponse(output=output)


@router.post("/api/admin/clock/sync")
async def sync_clock() -> AdminActionResponse:
    """Sync the repeater clock to the operator system."""
    assert _connection_ref
    await _connection_ref.send_command("clock sync", timeout=3.0)
    return AdminActionResponse(detail="Clock sync requested")


@router.post("/api/admin/clock/set")
async def set_clock(body: ClockSetRequest) -> AdminActionResponse:
    """Set the repeater clock to an explicit epoch time."""
    assert _connection_ref
    await _connection_ref.send_command(f"time {body.epoch_seconds}", timeout=3.0)
    return AdminActionResponse(detail="Clock set requested")
