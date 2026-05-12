"""
FastMCP server for MemBlocks.

Exposes MemBlocks memory tools to AI agents via stdio or HTTP MCP transports.
"""

import argparse
import asyncio
import json
import logging
import os
import sys
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Optional

from fastmcp import FastMCP, Context
from fastmcp.exceptions import ToolError
from pydantic import BaseModel, Field, ConfigDict
from starlette.middleware import Middleware
from starlette.middleware.cors import CORSMiddleware
from starlette.responses import JSONResponse
import uvicorn

from memblocks import MemBlocksClient, MemBlocksConfig
from memblocks.llm.task_settings import LLMSettings, LLMTaskSettings
from mcp_server.state import (
    get_active_block_id,
    get_mcp_lock,
    get_user_id,
    set_active_block_id,
    set_user_id,
)

# --- Logging setup ---
# stdout is reserved for MCP stdio protocol — all logging goes to stderr + file.
LOG_DIR = Path("memblocks_mcp_logs")
LOG_DIR.mkdir(exist_ok=True)


class FlushingFileHandler(logging.FileHandler):
    """FileHandler that flushes to disk after every emitted record."""

    def emit(self, record: logging.LogRecord) -> None:
        super().emit(record)
        self.flush()


def setup_logging() -> None:
    fmt = "%(asctime)s [%(name)s] %(levelname)s %(message)s"

    # Root logger - only server logs go here
    root = logging.getLogger()
    root.setLevel(logging.DEBUG)
    root.handlers.clear()

    # stderr handler (MCP host may surface this)
    stderr_handler = logging.StreamHandler(sys.stderr)
    stderr_handler.setFormatter(logging.Formatter(fmt))
    stderr_handler.addFilter(lambda r: not r.name.startswith("memblocks"))
    root.addHandler(stderr_handler)

    # mcp_server.log - server + MCP framework logs
    server_file = FlushingFileHandler(LOG_DIR / "mcp_server.log")
    server_file.setFormatter(logging.Formatter(fmt))
    server_file.addFilter(lambda r: not r.name.startswith("memblocks"))
    root.addHandler(server_file)

    # memblocks library — dedicated file for deep inspection
    mb_logger = logging.getLogger("memblocks")
    mb_logger.setLevel(logging.DEBUG)
    mb_logger.handlers.clear()
    mb_file = FlushingFileHandler(LOG_DIR / "memblocks.log")
    mb_file.setFormatter(logging.Formatter(fmt))
    mb_logger.addHandler(mb_file)

    # Suppress noisy third-party loggers
    for name in ("httpx", "httpcore", "groq", "pymongo", "urllib3", "openinference"):
        logging.getLogger(name).setLevel(logging.WARNING)


setup_logging()
logger = logging.getLogger(__name__)
logger.info(f"MCP server starting — logs at {LOG_DIR.absolute()}")


# --- Lifespan — singleton client initialization ---
@asynccontextmanager
async def app_lifespan(server: FastMCP):
    # Resolve user_id: env var > state file > default
    if env_user := os.environ.get("MEMBLOCKS_USER_ID"):
        user_id = env_user
        logger.info(f"Using user_id from MEMBLOCKS_USER_ID env var: {user_id}")
    elif state_user := get_user_id():
        user_id = state_user
        logger.info(f"Using user_id from state file: {user_id}")
    else:
        user_id = "default_user"
        logger.info(f"Using default user_id: {user_id}")
    config = MemBlocksConfig(
        llm_settings=LLMSettings(
            default=LLMTaskSettings(
                provider="groq", model="qwen/qwen3-32b"
            ),
            retrieval=LLMTaskSettings(provider="groq", model="openai/gpt-oss-20b"),
            ps1_semantic_extraction=LLMTaskSettings(
                provider="groq", model="openai/gpt-oss-120b"
            ),
            ps2_conflict_resolution=LLMTaskSettings(
                provider="groq", model="openai/gpt-oss-120b"
            ),
            core_memory_extraction=LLMTaskSettings(
                provider="groq", model="openai/gpt-oss-20b"
            ),
            recursive_summary=LLMTaskSettings(
                provider="groq", model="openai/gpt-oss-20b"
            ),
        )
    )
    client = MemBlocksClient(config)
    # Ensure user exists
    await client.get_or_create_user(user_id)
    # Persist user_id for components that share this state file.
    set_user_id(user_id)

    # Ensure there is always an active block for this user.
    active_id = get_active_block_id()
    active_block = None
    if active_id:
        active_block = await client.get_block(active_id)
        if active_block is None or active_block.user_id != user_id:
            logger.warning(
                "Active block %s is missing or belongs to another user; selecting a default block",
                active_id,
            )
            active_block = None

    if active_block is None:
        blocks = await client.get_user_blocks(user_id)
        if blocks:
            active_block = blocks[0]
            logger.info(
                "Selected existing block as active default: %s", active_block.id
            )
        else:
            active_block = await client.create_block(
                user_id=user_id,
                name="Default Memory",
                description="Auto-created default memory block for agent sessions",
            )
            logger.info("Created default active block: %s", active_block.id)
        set_active_block_id(active_block.id)

    logger.info(f"MemBlocksClient ready, user_id written to state file")
    yield {"client": client, "user_id": user_id}
    logger.info("Shutting down MemBlocksClient")
    await client.close()


mcp = FastMCP("memblocks_mcp", lifespan=app_lifespan)


@mcp.custom_route("/health", methods=["GET"])
async def health_check(request):
    return JSONResponse({"status": "healthy", "service": "memblocks_mcp"})


# --- Helper — active block guard ---
def _active_block_id_or_error() -> tuple[str | None, str | None]:
    """Returns (block_id, None) on success or (None, error_message) if not set."""
    block_id = get_active_block_id()
    if not block_id:
        return None, (
            "No active block is set. "
            "Call `memblocks_list_blocks` to see available blocks, "
            "then call `memblocks_set_block` with the desired block ID to activate one."
        )
    return block_id, None


# --- Helper — background task dispatch with exception logging ---
def _dispatch_background_task(
    coro,
    task_name: str,
    error_logger,
):
    """Dispatch a coroutine as a background task with exception logging.

    Args:
        coro: The coroutine to run in background
        task_name: Descriptive name for logging
        error_logger: Logger instance for error reporting
    """

    async def run_with_logging():
        try:
            await coro
        except Exception as e:
            error_logger.exception(f"Background task '{task_name}' failed: {e}")

    asyncio.create_task(run_with_logging())


# --- Tool 1 — memblocks_list_blocks ---
@mcp.tool(
    name="memblocks_list_blocks",
    annotations={
        "title": "List Memory Blocks",
        "readOnlyHint": True,
        "destructiveHint": False,
        "idempotentHint": True,
        "openWorldHint": False,
    },
)
async def memblocks_list_blocks(ctx: Context) -> str:
    """List all memory blocks for the configured user, flagging which is currently active.

    Returns a JSON array of block objects. Each object includes:
      - id (str): block ID
      - name (str): human-readable block name
      - description (str): optional block description
      - is_active (bool): true if this is the currently active block

    Returns an empty array if the user has no blocks.
    """
    logger.info("memblocks_list_blocks: called")
    client: MemBlocksClient = ctx.request_context.lifespan_context["client"]
    user_id: str = ctx.request_context.lifespan_context["user_id"]
    active_id = get_active_block_id()

    blocks = await client.get_user_blocks(user_id)
    result = [
        {
            "id": b.id,
            "name": b.name,
            "description": b.description,
            "is_active": b.id == active_id,
        }
        for b in blocks
    ]
    logger.info(
        f"memblocks_list_blocks: returning {len(result)} block(s), active_id={active_id}"
    )
    return json.dumps(result, indent=2)


# --- Tool 2 — memblocks_create_block ---
class CreateBlockInput(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True, extra="forbid")
    name: str = Field(
        ...,
        description="Human-readable name for the new block",
        min_length=1,
        max_length=100,
    )
    description: str = Field(
        default="",
        description="Optional description of the block's purpose",
        max_length=500,
    )


@mcp.tool(
    name="memblocks_create_block",
    annotations={
        "title": "Create Memory Block",
        "readOnlyHint": False,
        "destructiveHint": False,
        "idempotentHint": False,
        "openWorldHint": False,
    },
)
async def memblocks_create_block(params: CreateBlockInput, ctx: Context) -> str:
    """Create a new memory block for the configured user.

    Creates a block with semantic and core memory collections initialized.
    The new block is NOT automatically set as active — call
    `memblocks_set_block` with the returned block ID to activate it.

    Returns a JSON object with the created block's details:
      - id (str): new block ID
      - name (str): block name
      - description (str): block description
      - message (str): success confirmation
    """
    logger.info(f"memblocks_create_block: name={params.name!r}")

    if get_mcp_lock():
        logger.warning("memblocks_create_block: blocked — MCP lock enabled")
        raise ToolError(
            "MCP lock is enabled: block creation is not permitted for this session."
        )

    client: MemBlocksClient = ctx.request_context.lifespan_context["client"]
    user_id: str = ctx.request_context.lifespan_context["user_id"]

    block = await client.create_block(
        user_id=user_id,
        name=params.name,
        description=params.description,
    )
    result = {
        "id": block.id,
        "name": block.name,
        "description": block.description,
        "message": (
            f"Block '{block.name}' created successfully. "
            f"Call `memblocks_set_block` with block_id='{block.id}' to activate it."
        ),
    }
    logger.info(f"memblocks_create_block: created block id={block.id}")
    return json.dumps(result, indent=2)


# --- Tool 3 — memblocks_set_block ---
class SetBlockInput(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True, extra="forbid")
    block_id: str = Field(
        ...,
        description="ID of the block to activate",
        min_length=1,
    )


@mcp.tool(
    name="memblocks_set_block",
    annotations={
        "title": "Set Active Memory Block",
        "readOnlyHint": False,
        "destructiveHint": False,
        "idempotentHint": True,
        "openWorldHint": False,
    },
)
async def memblocks_set_block(params: SetBlockInput, ctx: Context) -> str:
    """Activate a memory block, making it the target for all subsequent memory operations.

    Validates that the block exists and belongs to the configured user before
    activating it.

    Returns a JSON object with:
      - block_id (str): the newly activated block ID
      - name (str): human-readable block name
      - message (str): confirmation message
    """
    logger.info(f"memblocks_set_block: block_id={params.block_id!r}")

    if get_mcp_lock():
        logger.warning("memblocks_set_block: blocked — MCP lock enabled")
        raise ToolError(
            "MCP lock is enabled: switching active blocks is not permitted for this session."
        )

    client: MemBlocksClient = ctx.request_context.lifespan_context["client"]
    user_id: str = ctx.request_context.lifespan_context["user_id"]

    block = await client.get_block(params.block_id)
    if block is None:
        logger.warning(f"memblocks_set_block: block not found: {params.block_id}")
        raise ToolError(
            f"Block '{params.block_id}' not found. "
            "Call `memblocks_list_blocks` to see available block IDs."
        )
    if block.user_id != user_id:
        logger.warning(
            f"memblocks_set_block: block {params.block_id} belongs to {block.user_id}, not {user_id}"
        )
        raise ToolError(
            f"Block '{params.block_id}' does not belong to the current user."
        )

    set_active_block_id(params.block_id)
    logger.info(f"memblocks_set_block: active block set to {params.block_id}")

    return json.dumps(
        {
            "block_id": block.id,
            "name": block.name,
            "message": f"Block '{block.name}' ({block.id}) is now active.",
        }
    )


# # --- Tool 4 — memblocks_store_semantic ---
# class StoreSemanticInput(BaseModel):
#     model_config = ConfigDict(str_strip_whitespace=True, extra="forbid")
#     fact: str = Field(
#         ...,
#         description="The fact or knowledge to store in semantic memory",
#         min_length=1,
#     )


# @mcp.tool(
#     name="memblocks_store_semantic",
#     annotations={
#         "title": "Store to Semantic Memory",
#         "readOnlyHint": False,
#         "destructiveHint": False,
#         "idempotentHint": False,
#         "openWorldHint": False,
#     },
# )
# async def memblocks_store_semantic(params: StoreSemanticInput, ctx: Context) -> str:
#     """Store a fact or knowledge to semantic memory (searchable via vector search).

#     PREFER `memblocks_store` OVER THIS TOOL:
#     Unless you specifically need semantic-only storage, call `memblocks_store`
#     instead — it stores to both semantic and core memory in one call and is the
#     recommended default.

#     PROACTIVE STORAGE — MANDATORY BEHAVIOR:
#     You MUST call a store tool proactively whenever a conversation turn contains
#     information worth remembering, WITHOUT waiting for the user to ask you to save it.

#     Use this tool specifically for factual, topic-retrievable knowledge:
#       - Technical facts, code patterns, or implementation details
#       - Domain knowledge or research findings from the conversation
#       - Task-specific data (e.g. API keys discussed, endpoints found, configs)
#       - Any fact best retrieved by topic keyword in a future session


#     Input:
#       - fact (str): Plain text fact or knowledge to store

#     Returns a JSON object with:
#       - status (str): "accepted" - storage is scheduled, not yet complete
#       - message (str): Confirmation that storage was accepted
#     """
#     logger.info(f"memblocks_store_semantic: fact={params.fact[:80]!r}")
#     client: MemBlocksClient = ctx.request_context.lifespan_context["client"]

#     # Check for active block (synchronous validation)
#     block_id, error = _active_block_id_or_error()
#     if error:
#         logger.warning(f"memblocks_store_semantic: no active block — {error}")
#         raise ToolError(error)

#     # Get the block (synchronous precondition)
#     block = await client.get_block(block_id)
#     if block is None:
#         logger.warning(f"memblocks_store_semantic: block not found: {block_id}")
#         raise ToolError(f"Block '{block_id}' not found.")

#     # Wrap fact as messages for extraction
#     messages = [{"role": "user", "content": params.fact}]

#     # Dispatch background task using extract_and_store convenience method
#     _dispatch_background_task(
#         block._semantic.extract_and_store(messages),
#         task_name=f"semantic_extract_and_store(block={block_id})",
#         error_logger=logger,
#     )

#     # Return immediate accepted response
#     result = {
#         "status": "accepted",
#         "message": "Semantic memory storage accepted - processing in background",
#     }
#     logger.info(
#         f"memblocks_store_semantic: dispatched background task for block {block_id}"
#     )
#     return json.dumps(result, indent=2)


# # --- Tool 5 — memblocks_store_to_core ---
# class StoreToCoreInput(BaseModel):
#     model_config = ConfigDict(str_strip_whitespace=True, extra="forbid")
#     fact: str = Field(
#         ...,
#         description="The fact or knowledge to add/update in core memory",
#         min_length=1,
#     )


# @mcp.tool(
#     name="memblocks_store_to_core",
#     annotations={
#         "title": "Store to Core Memory",
#         "readOnlyHint": False,
#         "destructiveHint": False,
#         "idempotentHint": False,
#         "openWorldHint": False,
#     },
# )
# async def memblocks_store_to_core(params: StoreToCoreInput, ctx: Context) -> str:
#     """Store a fact or knowledge to core memory (always-on persona and human context).

#     PREFER `memblocks_store` OVER THIS TOOL:
#     Unless you specifically need core-only storage, call `memblocks_store`
#     instead — it stores to both semantic and core memory in one call and is the
#     recommended default.

#     PROACTIVE STORAGE — MANDATORY BEHAVIOR:
#     You MUST call a store tool proactively whenever a conversation turn contains
#     information worth remembering, WITHOUT waiting for the user to ask you to save it.

#     Use this tool specifically for stable, identity-level facts about the user:
#       - The user's name, role, location, or organization
#       - Long-term goals or ongoing projects
#       - Persistent preferences about how the user wants you to behave
#       - Any fact that should always be present in every future conversation

#     Gets existing core memory, combines it with the new fact via LLM extraction,
#     and saves the updated core memory (persona + human sections).

#     Input:
#       - fact (str): Plain text fact or knowledge to add/update in core memory

#     Returns a JSON object with:
#       - status (str): "accepted" - storage is scheduled, not yet complete
#       - message (str): Confirmation that storage was accepted
#     """
#     logger.info(f"memblocks_store_to_core: fact={params.fact[:80]!r}")
#     client: MemBlocksClient = ctx.request_context.lifespan_context["client"]

#     # Check for active block (synchronous validation)
#     block_id, error = _active_block_id_or_error()
#     if error:
#         logger.warning(f"memblocks_store_to_core: no active block — {error}")
#         raise ToolError(error)

#     # Get the block (synchronous precondition)
#     block = await client.get_block(block_id)
#     if block is None:
#         logger.warning(f"memblocks_store_to_core: block not found: {block_id}")
#         raise ToolError(f"Block '{block_id}' not found.")

#     # Determine core_block_id
#     core_block_id = block.core_memory_block_id or block.id
#     logger.debug(f"memblocks_store_to_core: core_block_id={core_block_id}")

#     # Wrap fact as messages for extraction
#     messages = [{"role": "user", "content": params.fact}]

#     # Dispatch background task using update convenience method
#     _dispatch_background_task(
#         block._core.update(block_id=core_block_id, messages=messages),
#         task_name=f"core_update(block={core_block_id})",
#         error_logger=logger,
#     )

#     # Return immediate accepted response
#     result = {
#         "status": "accepted",
#         "message": "Core memory update accepted - processing in background",
#     }
#     logger.info(
#         f"memblocks_store_to_core: dispatched background task for block {core_block_id}"
#     )
#     return json.dumps(result, indent=2)


# --- Tool 6 — memblocks_store (STOR-03) ---
class StoreInput(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True, extra="forbid")
    fact: str = Field(
        ...,
        description="The fact or knowledge to store in both semantic and core memory",
        min_length=1,
    )


@mcp.tool(
    name="memblocks_store",
    annotations={
        "title": "Store to Both Memories",
        "readOnlyHint": False,
        "destructiveHint": False,
        "idempotentHint": False,
        "openWorldHint": False,
    },
)
async def memblocks_store(params: StoreInput, ctx: Context) -> str:
    """Store a fact or knowledge to both semantic and core memory in a single call.

    THIS IS THE DEFAULT STORE TOOL. When in doubt about which store tool to use,
    always call this one — it covers both semantic and core memory in one call.

    PROACTIVE STORAGE — MANDATORY BEHAVIOR:
    You MUST call this tool proactively whenever a conversation turn contains
    information worth remembering, WITHOUT waiting for the user to ask you to save it.
    Storing memory is part of being a good assistant. Never skip storage because the
    user did not explicitly say "remember this."

    ALWAYS call this tool when you encounter ANY of the following:
      - User preferences, opinions, or personal style choices
      - Facts about the user (name, role, location, background, skills)
      - Project names, goals, tech stack, architecture, or constraints
      - Decisions made or conclusions reached during the conversation
      - Task outcomes: code written, bugs fixed, configurations set
      - Repeated questions or topics (signals long-term relevance)
      - Explicit instructions about how the user wants you to behave
      - Any fact the user would want you to remember in a future session

    Call this tool IMMEDIATELY after the relevant information appears — do not
    batch multiple facts into one call; store each meaningful piece separately
    so retrieval stays precise.


    Input:
      - fact (str): Plain text fact or knowledge to store

    Returns a JSON object with:
      - status (str): "accepted" - storage is scheduled, not yet complete
      - message (str): Confirmation that storage was accepted
    """
    logger.info(f"memblocks_store: fact={params.fact[:80]!r}")
    client: MemBlocksClient = ctx.request_context.lifespan_context["client"]

    # Check for active block (synchronous validation)
    block_id, error = _active_block_id_or_error()
    if error:
        logger.warning(f"memblocks_store: no active block — {error}")
        raise ToolError(error)

    # Get the block (synchronous precondition)
    block = await client.get_block(block_id)
    if block is None:
        logger.warning(f"memblocks_store: block not found: {block_id}")
        raise ToolError(f"Block '{block_id}' not found.")

    # Wrap fact as messages for both extractions
    messages = [{"role": "user", "content": params.fact}]

    # Determine core_block_id for core update
    core_block_id = block.core_memory_block_id or block.id
    logger.debug(f"memblocks_store: core_block_id={core_block_id}")

    # Dispatch background task for semantic storage
    _dispatch_background_task(
        block._semantic.extract_and_store(messages),
        task_name=f"semantic_extract_and_store(block={block_id})",
        error_logger=logger,
    )

    # Dispatch background task for core update
    _dispatch_background_task(
        block._core.update(block_id=core_block_id, messages=messages),
        task_name=f"core_update(block={core_block_id})",
        error_logger=logger,
    )

    # Return immediate accepted response
    result = {
        "status": "accepted",
        "message": "Storage to both semantic and core memory accepted - processing in background",
    }
    logger.info(f"memblocks_store: dispatched background tasks for block {block_id}")
    return json.dumps(result, indent=2)


# --- Tool 7 — memblocks_retrieve (RETR-01) ---
class RetrieveInput(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True, extra="forbid")
    query: str = Field(
        ...,
        description="The query string to search semantic memory for",
        min_length=1,
    )


@mcp.tool(
    name="memblocks_retrieve",
    annotations={
        "title": "Retrieve from Memory",
        "readOnlyHint": True,
        "destructiveHint": False,
        "idempotentHint": True,
        "openWorldHint": False,
    },
)
async def memblocks_retrieve(params: RetrieveInput, ctx: Context) -> str:
    """Retrieve memories from the active block using semantic search.

    This tool performs a combined retrieval from both core memory (full content)
    and semantic memory (vector search). Returns formatted context ready for
    LLM injection.

    Always use this tool for retrieval unless you specifically need core-only or semantic-only results — it provides the most complete context in one call.

    Input:
      - query (str): Search query for semantic memory retrieval

    Returns a string formatted for LLM injection, containing:
      - Core memory (persona + stable human facts)
      - Semantically relevant memories matching the query
    """
    logger.info(f"memblocks_retrieve: query={params.query[:80]!r}")
    client: MemBlocksClient = ctx.request_context.lifespan_context["client"]

    # Check for active block
    block_id, error = _active_block_id_or_error()
    if error:
        logger.warning(f"memblocks_retrieve: no active block — {error}")
        raise ToolError(error)

    # Get the block
    block = await client.get_block(block_id)
    if block is None:
        logger.warning(f"memblocks_retrieve: block not found: {block_id}")
        raise ToolError(f"Block '{block_id}' not found.")

    # Combined retrieval (core + semantic)
    result = await block.retrieve(params.query)
    logger.info(
        f"memblocks_retrieve: done — core={result.core is not None}, semantic={len(result.semantic)}"
    )
    return result.to_prompt_string()


# --- Tool 8 — memblocks_retrieve_core (RETR-02) ---
# @mcp.tool(
#     name="memblocks_retrieve_core",
#     annotations={
#         "title": "Retrieve Core Memory Only",
#         "readOnlyHint": True,
#         "destructiveHint": False,
#         "idempotentHint": True,
#         "openWorldHint": False,
#     },
# )
# async def memblocks_retrieve_core(ctx: Context) -> str:
#     """Retrieve only the core memory from the active block.

#     Core memory contains persona (AI's perspective on the human) and stable
#     human facts. This returns the full core memory contents regardless of any
#     query - useful when you need the complete context about the human.

#     Returns a string containing the full core memory, formatted for LLM injection.
#     No input parameters needed.
#     """
#     logger.info("memblocks_retrieve_core: called")
#     client: MemBlocksClient = ctx.request_context.lifespan_context["client"]

#     # Check for active block
#     block_id, error = _active_block_id_or_error()
#     if error:
#         logger.warning(f"memblocks_retrieve_core: no active block — {error}")
#         raise ToolError(error)

#     # Get the block
#     block = await client.get_block(block_id)
#     if block is None:
#         logger.warning(f"memblocks_retrieve_core: block not found: {block_id}")
#         raise ToolError(f"Block '{block_id}' not found.")

#     # Core-only retrieval (no query needed)
#     result = await block.core_retrieve()
#     logger.info(f"memblocks_retrieve_core: done — core={result.core is not None}")
#     return result.to_prompt_string()


# --- Tool 9 — memblocks_retrieve_semantic (RETR-03) ---
# @mcp.tool(
#     name="memblocks_retrieve_semantic",
#     annotations={
#         "title": "Retrieve Semantic Memory Only",
#         "readOnlyHint": True,
#         "destructiveHint": False,
#         "idempotentHint": True,
#         "openWorldHint": False,
#     },
# )
# async def memblocks_retrieve_semantic(params: RetrieveInput, ctx: Context) -> str:
#     """Retrieve only semantic memories from the active block.

#     Semantic memory contains facts, knowledge, and learned information retrieved
#     via vector search. This excludes core memory - useful when you only need
#     facts/knowledge without persona or human context.

#     Input:
#       - query (str): Search query for semantic memory retrieval

#     Returns a string containing only semantically relevant memories, formatted
#     for LLM injection.
#     """
#     logger.info(f"memblocks_retrieve_semantic: query={params.query[:80]!r}")
#     client: MemBlocksClient = ctx.request_context.lifespan_context["client"]

#     # Check for active block
#     block_id, error = _active_block_id_or_error()
#     if error:
#         logger.warning(f"memblocks_retrieve_semantic: no active block — {error}")
#         raise ToolError(error)

#     # Get the block
#     block = await client.get_block(block_id)
#     if block is None:
#         logger.warning(f"memblocks_retrieve_semantic: block not found: {block_id}")
#         raise ToolError(f"Block '{block_id}' not found.")

#     # Semantic-only retrieval
#     result = await block.semantic_retrieve(params.query)
#     logger.info(f"memblocks_retrieve_semantic: done — semantic={len(result.semantic)}")
#     return result.to_prompt_string()


# --- Prompt 1 — memblocks_storage_policy ---
@mcp.prompt(
    name="memblocks_storage_policy",
    description=(
        "Mandatory behavioral policy for proactive memory storage. "
        "Inject this into your system context to ensure you store "
        "all worthwhile information without waiting to be asked."
    ),
)
async def prompt_storage_policy() -> str:
    """Returns the mandatory storage policy that governs when to call store tools.

    Agents should load this prompt to receive explicit behavioral instructions
    about proactive memory storage. It defines WHEN to call memblocks_store*
    tools and which tool to prefer.
    """
    return """\
MEMBLOCKS MEMORY STORAGE POLICY — MANDATORY

You have access to persistent memory tools. You MUST follow this policy at all times.

## PRIMARY RULE

After EVERY conversation turn, ask yourself:
  "Did I learn anything in this turn that is worth remembering?"

If the answer is YES — call `memblocks_store` immediately, before your next response.
Do NOT wait for the user to say "save this", "remember this", or "store this."
Storing memory proactively is a core part of your job.

## DEFAULT TOOL: memblocks_store

When in doubt, ALWAYS use `memblocks_store` — it stores to BOTH semantic and core
memory in one call. Only use the specialized tools when you have a specific reason:
  - `memblocks_store_semantic` → only for purely factual/technical data you want
    retrieved by topic, not identity-level user context
  - `memblocks_store_to_core` → only for stable user identity facts when you
    specifically do NOT want semantic indexing

## MANDATORY STORAGE TRIGGERS

You MUST call `memblocks_store` immediately when you encounter ANY of the following:

  USER IDENTITY & PREFERENCES
  - The user's name, role, job title, location, or organization
  - Personal preferences (coding style, language preferences, communication style)
  - Opinions or values the user expresses
  - How the user wants you to behave (e.g., "always be concise", "use TypeScript")

  PROJECT & TECHNICAL CONTEXT
  - Project name, description, or goals
  - Tech stack, frameworks, languages, or tools in use
  - Architecture decisions or design patterns chosen
  - Repository structure, key file paths, or module organization
  - Environment details (OS, editor, cloud provider, etc.)

  DECISIONS & OUTCOMES
  - Conclusions reached during problem-solving
  - Bugs fixed and what caused them
  - Code written, configurations set, or commands that worked
  - Anything the user confirmed as correct or approved

  RECURRING TOPICS
  - A topic the user has asked about multiple times (signals long-term importance)
  - Ongoing tasks or projects that will continue across sessions

## RULES FOR CALLING STORE TOOLS

1. Store IMMEDIATELY when the trigger appears — do not wait until end of conversation
2. Store each meaningful piece SEPARATELY — do not batch unrelated facts into one call
3. Write the `fact` parameter as a clear, self-contained sentence that will make
   sense when retrieved in a future session with no surrounding context
4. After storing, continue with your normal response — do not announce that you stored
   unless the user asks

## WHAT NOT TO STORE

- Casual greetings or small talk with no durable information
- Temporary or throwaway data the user explicitly says is one-off
- Information that is already stored (check retrieval first if unsure)

## RETRIEVAL BEFORE TASKS

Before starting any substantive task, call `memblocks_retrieve` with a relevant
query to load context from previous sessions. This prevents re-asking for
information the user already told you.
"""


# --- Resource 1 — memblocks://active-block (RES-01) ---
@mcp.resource(
    uri="memblocks://active-block",
    name="Active Memory Block",
    description="Current active memory block name, ID, and description",
    mime_type="text/plain",
)
async def resource_active_block(ctx: Context) -> str:
    """Exposes the current active memory block metadata.

    Returns block name, ID, and description so agents can read block context
    without making a tool call. Returns a helpful message if no block is active.
    """
    logger.info("resource_active_block: called")
    block_id = get_active_block_id()
    if not block_id:
        return (
            "No active memory block is set.\n"
            "Call `memblocks_list_blocks` to see available blocks and then\n"
            "call `memblocks_set_block` with the desired block ID."
        )
    client: MemBlocksClient = ctx.request_context.lifespan_context["client"]
    block = await client.get_block(block_id)
    if block is None:
        return f"Active block ID '{block_id}' was not found. It may have been deleted."
    lines = [
        f"Active Memory Block",
        f"  Name: {block.name}",
        f"  ID:   {block.id}",
    ]
    if block.description:
        lines.append(f"  Description: {block.description}")
    return "\n".join(lines)


# --- Resource 2 — memblocks://tools (RES-02) ---
@mcp.resource(
    uri="memblocks://tools",
    name="MemBlocks Tool Guide",
    description="Usage guide for all available MemBlocks MCP tools",
    mime_type="text/plain",
)
async def resource_tools_guide(ctx: Context) -> str:
    """Usage guide listing all available MemBlocks tools.

    Returns a human-readable reference agents can inject into context
    to understand when and how to call each tool.
    """
    return """MemBlocks MCP Tool Reference
    =============================

    ## PROACTIVE STORAGE POLICY (READ THIS FIRST)

    You MUST call `memblocks_store` proactively — without being asked — whenever
    a conversation turn contains information worth remembering.

    DEFAULT TOOL: Always use `memblocks_store` when in doubt.
    It stores to BOTH semantic and core memory in a single call.

    MANDATORY STORAGE TRIGGERS — call `memblocks_store` when you encounter:
      - User name, role, location, or organization
      - User preferences, opinions, or behavioral instructions
      - Project name, goals, tech stack, or architecture decisions
      - Bugs fixed, code written, or configurations set
      - Decisions or conclusions reached during the conversation
      - Any fact the user would want remembered in a future session

    Load the `memblocks_storage_policy` prompt for the full mandatory policy.

    ## Block Management

    memblocks_list_blocks
      Purpose: List all memory blocks for the configured user
      Params:  none
      Returns: JSON array with id, name, description, is_active per block
      Use when: You need to discover available blocks or check which is active

    memblocks_create_block
      Purpose: Create a new memory block
      Params:  name (str, required), description (str, optional)
      Returns: JSON with new block id, name, description, confirmation message
      Use when: User wants a new isolated memory space

    memblocks_set_block
      Purpose: Activate a memory block for subsequent operations
      Params:  block_id (str, required)
      Returns: JSON with block_id, name, confirmation message
      Use when: Switching context to a different memory block

    ## Store Tools

    memblocks_store  ← DEFAULT — USE THIS WHEN IN DOUBT
      Purpose: Store to BOTH semantic and core memory in a single call
      Params:  fact (str, required) — plain text, self-contained sentence
      Returns: JSON with semantic count/operations and core memory previews
      Use when: ANY time you learn something worth remembering (proactively)

    memblocks_store_semantic
      Purpose: Store a fact to semantic memory only (searchable via vector search)
      Params:  fact (str, required) — plain text
      Returns: JSON with count of extracted memories and operations performed
      Use when: Purely technical/factual data, no need to update core identity

    memblocks_store_to_core
      Purpose: Update core memory only (always-on persona/human info)
      Params:  fact (str, required) — plain text
      Returns: JSON with persona and human preview of updated core memory
      Use when: Stable identity facts about the user, no semantic indexing needed

    ## Retrieve Tools

    memblocks_retrieve
      Purpose: Retrieve relevant context from both core and semantic memory
      Params:  query (str, required)
      Returns: Formatted string ready for LLM injection (core + semantic)
      Use when: Priming context before a task — call this BEFORE starting work

    memblocks_retrieve_core
      Purpose: Retrieve full core memory only (no query needed)
      Params:  none
      Returns: Formatted string with full core memory content
      Use when: You need stable persona/human facts without semantic search

    memblocks_retrieve_semantic
      Purpose: Retrieve only semantically relevant memories for a query
      Params:  query (str, required)
      Returns: Formatted string with matching semantic memories only
      Use when: You need topic-specific facts without the core memory overlay

    ## MCP Resources and Prompts (read without tool calls)

    memblocks://active-block    — Current block name, ID, description
    memblocks://tools           — This usage guide
    memblocks_storage_policy    — Full mandatory proactive storage policy (LOAD THIS)
    """


# --- Entry point ---
def main() -> None:
    """Entry point for `memblocks-mcp` CLI command."""
    parser = argparse.ArgumentParser(description="MemBlocks MCP Server")
    parser.add_argument(
        "--transport",
        choices=["stdio", "sse", "streamable-http", "http"],
        default="stdio",
        help="Transport protocol (default: stdio)",
    )
    parser.add_argument("--host", default="0.0.0.0", help="Host to bind (default: 0.0.0.0)")
    parser.add_argument("--port", type=int, default=8002, help="Port to bind (default: 8002)")
    parser.add_argument(
        "--path",
        default="/mcp",
        help="HTTP path for MCP endpoint (default: /mcp)",
    )
    parser.add_argument(
        "--cors",
        action="store_true",
        help="Enable CORS for browser-based MCP clients",
    )
    parser.add_argument(
        "--cors-origins",
        default="",
        help="Comma-separated list of allowed CORS origins (default: *)",
    )
    args = parser.parse_args()

    transport = "streamable-http" if args.transport == "http" else args.transport

    if transport == "stdio":
        mcp.run()
        return

    if transport == "sse":
        if args.cors or args.cors_origins:
            logger.warning("CORS middleware is only available for streamable-http transport")
        mcp.run(transport="sse", host=args.host, port=args.port)
        return

    cors_enabled = args.cors or bool(args.cors_origins)
    middleware = None
    if cors_enabled:
        origins = ["*"]
        if args.cors_origins.strip():
            origins = [o.strip() for o in args.cors_origins.split(",") if o.strip()]
        middleware = [
            Middleware(
                CORSMiddleware,
                allow_origins=origins,
                allow_methods=["GET", "POST", "DELETE", "OPTIONS"],
                allow_headers=[
                    "mcp-protocol-version",
                    "mcp-session-id",
                    "Authorization",
                    "Content-Type",
                ],
                expose_headers=["mcp-session-id"],
            )
        ]

    app = mcp.http_app(path=args.path, middleware=middleware)
    uvicorn.run(app, host=args.host, port=args.port)


if __name__ == "__main__":
    main()
