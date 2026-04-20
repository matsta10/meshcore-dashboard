"""Command definitions, whitelist, and timeout tiers."""

from __future__ import annotations

from enum import Enum


class CommandTier(Enum):
    """Timeout tiers for serial commands."""

    FAST = 1.0
    NORMAL = 3.0
    SLOW = 10.0


FAST_COMMANDS = {
    "ver",
    "board",
    "clock",
    "stats-core",
    "stats-radio",
    "stats-packets",
    "neighbors",
    "region",
    "region list",
    "log",
}

NORMAL_COMMANDS = {
    "advert",
    "advert.zerohop",
    "discover.neighbors",
    "log start",
    "log stop",
}

SLOW_COMMANDS = {"reboot", "clear stats", "log erase"}

COMMAND_WHITELIST = FAST_COMMANDS | NORMAL_COMMANDS | SLOW_COMMANDS

DESTRUCTIVE_COMMANDS = {"reboot", "clear stats", "log erase"}

BLOCKED_PREFIXES = ("set ", "get ", "password", "erase")
BLOCKED_EXACT = {"set prv.key", "erase"}


def is_command_allowed(cmd: str) -> bool:
    """Check if a command is in the whitelist and not blocked."""
    cmd_lower = cmd.strip().lower()
    if cmd_lower in BLOCKED_EXACT:
        return False
    for prefix in BLOCKED_PREFIXES:
        if cmd_lower.startswith(prefix):
            return False
    return cmd_lower in COMMAND_WHITELIST


def is_destructive(cmd: str) -> bool:
    """Check if a command requires confirmation."""
    return cmd.strip().lower() in DESTRUCTIVE_COMMANDS


def get_timeout(cmd: str) -> float:
    """Get the appropriate timeout for a command."""
    cmd_lower = cmd.strip().lower()
    if cmd_lower in FAST_COMMANDS:
        return CommandTier.FAST.value
    if cmd_lower in SLOW_COMMANDS:
        return CommandTier.SLOW.value
    return CommandTier.NORMAL.value
