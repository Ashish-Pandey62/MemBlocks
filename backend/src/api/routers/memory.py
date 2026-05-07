"""Memory router — core memory and semantic memory search endpoints."""

from typing import Any, Dict, List, Optional

from fastapi import APIRouter, Depends, HTTPException

from backend.src.api.dependencies import get_client
from backend.src.api.models.requests import (
    SearchMemoriesRequest,
    UpdateCoreMemoryRequest,
)
from backend.src.api.routers.auth import CurrentUser, get_current_user
from memblocks import MemBlocksClient
from memblocks.models.units import CoreMemoryUnit, SemanticMemoryUnit

router = APIRouter(prefix="/memory", tags=["memory"])


async def _get_block_with_auth(
    block_id: str,
    current_user: CurrentUser,
    client: MemBlocksClient,
):
    """Helper to get block and verify ownership."""
    block = await client.get_block(block_id)
    if not block:
        raise HTTPException(status_code=404, detail=f"Block '{block_id}' not found")
    if block.user_id != current_user.user_id:
        raise HTTPException(
            status_code=403,
            detail="Cannot access another user's block",
        )
    return block


# ---- Core Memory ----


@router.get("/core/{block_id}", response_model=Dict[str, Any])
async def get_core_memory(
    block_id: str,
    current_user: CurrentUser = Depends(get_current_user),
    client: MemBlocksClient = Depends(get_client),
) -> Dict[str, Any]:
    """Retrieve the core memory (persona + human facts) for a block."""
    block = await _get_block_with_auth(block_id, current_user, client)
    core = await client._core.get(block.core_memory_block_id or block_id)
    if not core:
        raise HTTPException(
            status_code=404, detail=f"Core memory for block '{block_id}' not found"
        )
    return core.model_dump()


@router.patch("/core/{block_id}", response_model=Dict[str, Any])
async def update_core_memory(
    block_id: str,
    body: UpdateCoreMemoryRequest,
    current_user: CurrentUser = Depends(get_current_user),
    client: MemBlocksClient = Depends(get_client),
) -> Dict[str, Any]:
    """Partially update the core memory for a block.

    Only the provided fields (persona_content, human_content) are updated;
    omitted fields are left unchanged.
    """
    block = await _get_block_with_auth(block_id, current_user, client)
    core = await client._core.get(block.core_memory_block_id or block_id)
    if not core:
        raise HTTPException(
            status_code=404, detail=f"Core memory for block '{block_id}' not found"
        )

    persona = (
        body.persona_content
        if body.persona_content is not None
        else core.persona_content
    )
    human = body.human_content if body.human_content is not None else core.human_content

    updated = await client._core.save(
        block_id=block.core_memory_block_id or block_id,
        memory_unit=CoreMemoryUnit(persona_content=persona, human_content=human),
    )
    return {"persona_content": persona, "human_content": human}


# ---- Semantic Memory ----


@router.post("/semantic/{block_id}/search", response_model=List[Dict[str, Any]])
async def search_semantic_memories(
    block_id: str,
    body: SearchMemoriesRequest,
    current_user: CurrentUser = Depends(get_current_user),
    client: MemBlocksClient = Depends(get_client),
) -> List[Dict[str, Any]]:
    """Search semantic memories in a block's Qdrant collection.

    Returns a flat list of SemanticMemoryUnit dicts ordered by relevance.
    """
    block = await _get_block_with_auth(block_id, current_user, client)

    block._top_k = body.top_k
    results = await block.semantic_retrieve(body.query)
    return [mem.model_dump() for mem in results.semantic]


# ---- All Memories with Pagination ----


@router.get("/all/{block_id}", response_model=Dict[str, Any])
async def get_all_block_memories(
    block_id: str,
    semantic_limit: int = 10,
    semantic_offset: int = 0,
    current_user: CurrentUser = Depends(get_current_user),
    client: MemBlocksClient = Depends(get_client),
) -> Dict[str, Any]:
    """Get all memories for a block with pagination.

    Returns core memory, semantic memories (paginated), and block metadata.
    Excludes embedding vectors and internal IDs for user-friendly display.
    """
    block = await _get_block_with_auth(block_id, current_user, client)

    core = await client._core.get(block.core_memory_block_id or block_id)
    core_memory = None
    if core:
        core_memory = {
            "persona_content": core.persona_content,
            "human_content": core.human_content,
        }

    block._top_k = semantic_limit + semantic_offset
    results = await block.semantic_retrieve(" ")
    all_semantic = results.semantic if results.semantic else []

    total_semantic = len(all_semantic)
    paginated_semantic = all_semantic[
        semantic_offset : semantic_offset + semantic_limit
    ]

    semantic_memories = []
    for mem in paginated_semantic:
        mem_dict = mem.model_dump()
        semantic_memories.append(
            {
                "id": mem_dict.get("memory_id"),
                "content": mem_dict.get("content", "")[:300],
                "memory_time": mem_dict.get("memory_time"),
                "source": mem_dict.get("source"),
                "type": mem_dict.get("type"),
                "keywords": mem_dict.get("keywords", [])[:5],
            }
        )

    return {
        "block_id": block.id,
        "block_name": block.name,
        "block_description": block.description,
        "core_memory": core_memory,
        "semantic_memories": semantic_memories,
        "pagination": {
            "total_semantic": total_semantic,
            "loaded": len(semantic_memories),
            "offset": semantic_offset,
            "limit": semantic_limit,
            "has_more": (semantic_offset + len(semantic_memories)) < total_semantic,
        },
    }


# ---- Search Within Block ----


@router.post("/{block_id}/search", response_model=Dict[str, Any])
async def search_block_memory(
    block_id: str,
    query: str = "",
    search_type: str = "all",
    limit: int = 10,
    current_user: CurrentUser = Depends(get_current_user),
    client: MemBlocksClient = Depends(get_client),
) -> Dict[str, Any]:
    """Search within a block's memories.

    Args:
        block_id: Block ID to search in
        query: Search query string
        search_type: "core" | "semantic" | "all" (default: "all")
        limit: Max results to return (default: 10)
    """
    block = await _get_block_with_auth(block_id, current_user, client)

    results = {
        "core_matches": [],
        "semantic_matches": [],
    }

    if search_type in ("core", "all"):
        core = await client._core.get(block.core_memory_block_id or block_id)
        if core:
            core_data = {
                "persona_content": core.persona_content,
                "human_content": core.human_content,
            }
            if (
                query.lower() in (core.persona_content or "").lower()
                or query.lower() in (core.human_content or "").lower()
            ):
                results["core_matches"] = {
                    "persona_match": query.lower()
                    in (core.persona_content or "").lower(),
                    "human_match": query.lower() in (core.human_content or "").lower(),
                    "persona_content": core.persona_content,
                    "human_content": core.human_content,
                }
            elif not query:
                results["core_matches"] = core_data

    if search_type in ("semantic", "all"):
        block._top_k = limit
        semantic_results = await block.semantic_retrieve(query or "")
        results["semantic_matches"] = [
            {
                "id": mem.memory_id,
                "content": mem.content[:200] if mem.content else "",
                "type": mem.type,
                "memory_time": mem.memory_time,
                "source": mem.source,
            }
            for mem in (semantic_results.semantic or [])[:limit]
        ]

    return results
