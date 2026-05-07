"""
Active block state module.

Reads and writes shared CLI/server state via ~/.config/memblocks/active_block.json.

Schema: {"user_id": "<str>", "block_id": "<str>", "mcp_locked": <bool>}

The MCP server writes user_id on startup. The CLI reads it for all commands that
need to identify the current user. Both sides read/write block_id and mcp_locked.
Uses only stdlib — no external dependencies.
"""

import json
from pathlib import Path

STATE_FILE = Path.home() / ".config" / "memblocks" / "active_block.json"


def _read_state() -> dict:
    """Read raw state dict from file. Returns {} on any error."""
    try:
        return json.loads(STATE_FILE.read_text(encoding="utf-8"))
    except (FileNotFoundError, json.JSONDecodeError, OSError):
        return {}


def _write_state(data: dict) -> None:
    """Write state dict to file, creating parent dirs as needed."""
    STATE_FILE.parent.mkdir(parents=True, exist_ok=True)
    STATE_FILE.write_text(json.dumps(data), encoding="utf-8")


def get_user_id() -> str | None:
    """Read the user ID written by the MCP server on startup.

    Returns None if the server has never started (state file missing or no user_id key).
    """
    return _read_state().get("user_id")


def set_user_id(user_id: str) -> None:
    """Write the user ID to the shared state file.

    Called by the MCP server on startup so the CLI can resolve the correct user
    without duplicating environment variable / config file lookup logic.
    """
    data = _read_state()
    data["user_id"] = user_id
    _write_state(data)


def get_active_block_id() -> str | None:
    """Read active block ID from shared state file.

    Returns None if the file does not exist or cannot be parsed.
    Never raises — always returns str or None.
    """
    return _read_state().get("block_id")


def set_active_block_id(block_id: str) -> None:
    """Write active block ID to shared state file.

    Preserves any other keys already in the state (e.g. mcp_locked, user_id).
    """
    data = _read_state()
    data["block_id"] = block_id
    _write_state(data)


def get_mcp_lock() -> bool:
    """Return True if the MCP is locked from creating or switching blocks.

    Defaults to False (unlocked) when not set.
    """
    return bool(_read_state().get("mcp_locked", False))


def set_mcp_lock(locked: bool) -> None:
    """Set the MCP lock flag.

    When locked=True, memblocks_create_block and memblocks_set_block will
    return an error instead of executing. Store/retrieve tools are unaffected.
    """
    data = _read_state()
    data["mcp_locked"] = locked
    _write_state(data)
