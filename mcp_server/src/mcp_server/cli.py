"""CLI for MemBlocks - manage active memory block and MCP permissions.

Commands:
  whoami               Show the current user ID and where it comes from
  set-user <id>        Set the user ID in state file
  list-blocks          List all blocks with name and ID
  set-block <id>       Activate a block
  get-block            Show the current active block
  lock                 Prevent the MCP from creating or switching blocks
  unlock               Restore MCP create/switch permissions (default)
"""

import argparse
import asyncio
import os
import sys

from mcp_server.state import (
    get_active_block_id,
    get_mcp_lock,
    get_user_id,
    set_active_block_id,
    set_mcp_lock,
    set_user_id,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _resolve_user_id() -> str:
    """Return the active user ID.

    Preference order:
      1. MEMBLOCKS_USER_ID environment variable (explicit override)
      2. user_id written to state file by the MCP server on startup
      3. "default_user" fallback
    """
    if val := os.environ.get("MEMBLOCKS_USER_ID"):
        return val
    if val := get_user_id():
        return val
    return "default_user"


def _resolve_user_id_with_source() -> tuple[str, str]:
    """Return (user_id, source) where source describes where the value came from."""
    if val := os.environ.get("MEMBLOCKS_USER_ID"):
        return val, "MEMBLOCKS_USER_ID environment variable"
    if val := get_user_id():
        return val, "state file (written by MCP server on startup)"
    return "default_user", "default (MCP server has not started yet)"


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _build_client():
    """Construct a MemBlocksClient with default config (mirrors server lifespan)."""
    from memblocks import MemBlocksClient, MemBlocksConfig
    from memblocks.llm.task_settings import LLMSettings, LLMTaskSettings

    config = MemBlocksConfig(
        llm_settings=LLMSettings(
            default=LLMTaskSettings(
                provider="groq", model="moonshotai/kimi-k2-instruct-0905"
            ),
            retrieval=LLMTaskSettings(provider="groq", model="openai/gpt-oss-20b"),
            ps1_semantic_extraction=LLMTaskSettings(
                provider="groq", model="openai/gpt-oss-120b"
            ),
            ps2_conflict_resolution=LLMTaskSettings(
                provider="groq", model="moonshotai/kimi-k2-instruct-0905"
            ),
            core_memory_extraction=LLMTaskSettings(
                provider="groq", model="openai/gpt-oss-120b"
            ),
            recursive_summary=LLMTaskSettings(
                provider="groq", model="openai/gpt-oss-120b"
            ),
        )
    )
    return MemBlocksClient(config)


# ---------------------------------------------------------------------------
# Command handlers
# ---------------------------------------------------------------------------


def cmd_whoami(args: argparse.Namespace) -> None:
    """Handle whoami command — show the current user ID and its source."""
    user_id, source = _resolve_user_id_with_source()
    print(f"User ID: {user_id}")
    print(f"Source:  {source}")
    sys.exit(0)


def cmd_set_user(args: argparse.Namespace) -> None:
    """Handle set-user command — set the user ID in state file."""
    set_user_id(args.user_id)
    print(f"User ID set to: {args.user_id}")
    sys.exit(0)


def cmd_list_blocks(args: argparse.Namespace) -> None:
    """Handle list-blocks command."""
    user_id = _resolve_user_id()

    async def _fetch():
        client = _build_client()
        try:
            await client.get_or_create_user(user_id)
            return await client.get_user_blocks(user_id)
        finally:
            await client.close()

    try:
        blocks = asyncio.run(_fetch())
    except Exception as exc:
        print(f"Error fetching blocks: {exc}", file=sys.stderr)
        sys.exit(1)

    if not blocks:
        print("No blocks found.")
        sys.exit(0)

    active_id = get_active_block_id()
    print(f"{'ID':<26}  {'Name'}")
    print("-" * 50)
    for block in blocks:
        marker = " *" if block.id == active_id else "  "
        print(f"{block.id:<26}{marker} {block.name}")

    if active_id:
        print(f"\n* = active block")
    sys.exit(0)


def cmd_set_block(args: argparse.Namespace) -> None:
    """Handle set-block command."""
    set_active_block_id(args.block_id)
    print(f"Active block set to: {args.block_id}")
    sys.exit(0)


def cmd_get_block(args: argparse.Namespace) -> None:
    """Handle get-block command."""
    block_id = get_active_block_id()
    if block_id:
        print(f"Active block: {block_id}")
    else:
        print("No active block set.")
    sys.exit(0)


def cmd_lock(args: argparse.Namespace) -> None:
    """Handle lock command — prevent MCP from creating or switching blocks."""
    set_mcp_lock(True)
    print("MCP locked: create-block and set-block are now blocked.")
    print("Store and retrieve tools are unaffected.")
    print("Run 'memblocks-cli unlock' to restore permissions.")
    sys.exit(0)


def cmd_unlock(args: argparse.Namespace) -> None:
    """Handle unlock command — restore MCP create/switch permissions."""
    set_mcp_lock(False)
    locked = get_mcp_lock()  # read back to confirm
    if not locked:
        print("MCP unlocked: create-block and set-block are permitted again.")
    sys.exit(0)


# ---------------------------------------------------------------------------
# Argument parser
# ---------------------------------------------------------------------------


def main() -> None:
    """Main entry point for the memblocks-cli CLI."""
    parser = argparse.ArgumentParser(
        prog="memblocks-cli",
        description="MemBlocks CLI - Manage active memory blocks and MCP permissions",
    )
    subparsers = parser.add_subparsers(dest="command", required=True)

    # whoami
    p_whoami = subparsers.add_parser(
        "whoami",
        help="Show the current user ID and where it comes from",
    )
    p_whoami.set_defaults(func=cmd_whoami)

    # set-user
    p_set_user = subparsers.add_parser(
        "set-user",
        help="Set the user ID in state file",
    )
    p_set_user.add_argument("user_id", help="User ID to set")
    p_set_user.set_defaults(func=cmd_set_user)

    # list-blocks
    p_list = subparsers.add_parser(
        "list-blocks",
        help="List all blocks with name and ID",
    )
    p_list.set_defaults(func=cmd_list_blocks)

    # set-block
    p_set = subparsers.add_parser(
        "set-block",
        help="Set the active memory block",
    )
    p_set.add_argument("block_id", help="Block ID to activate")
    p_set.set_defaults(func=cmd_set_block)

    # get-block
    p_get = subparsers.add_parser(
        "get-block",
        help="Show the current active block",
    )
    p_get.set_defaults(func=cmd_get_block)

    # lock
    p_lock = subparsers.add_parser(
        "lock",
        help="Prevent the MCP from creating or switching blocks",
    )
    p_lock.set_defaults(func=cmd_lock)

    # unlock
    p_unlock = subparsers.add_parser(
        "unlock",
        help="Restore MCP create/switch permissions (default state)",
    )
    p_unlock.set_defaults(func=cmd_unlock)

    args = parser.parse_args()
    args.func(args)


if __name__ == "__main__":
    main()
