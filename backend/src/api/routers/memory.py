"""Memory router — core memory and semantic memory search endpoints."""

from typing import Any, Dict, List, Optional

from fastapi import APIRouter, Depends, HTTPException

from backend.src.api.dependencies import get_client
from backend.src.api.models.requests import (
    SearchMemoriesRequest,
    UpdateCoreMemoryRequest,
)
from memblocks import MemBlocksClient

router = APIRouter(prefix="/memory", tags=["memory"])


# ---- Core Memory ----


@router.get("/core/{block_id}", response_model=Dict[str, Any])
async def get_core_memory(
    block_id: str,
    client: MemBlocksClient = Depends(get_client),
) -> Dict[str, Any]:
    """Retrieve the core memory (persona + human facts) for a block."""
    block = await client.get_block(block_id)
    if not block:
        raise HTTPException(status_code=404, detail=f"Block '{block_id}' not found")
    core = await block.core_retrieve()
    if not core or not core.core:
        raise HTTPException(
            status_code=404, detail=f"Core memory for block '{block_id}' not found"
        )
    return core.core.model_dump()


@router.patch("/core/{block_id}", response_model=Dict[str, Any])
async def update_core_memory(
    block_id: str,
    body: UpdateCoreMemoryRequest,
    client: MemBlocksClient = Depends(get_client),
) -> Dict[str, Any]:
    """Partially update the core memory for a block.

    Only the provided fields (persona_content, human_content) are updated;
    omitted fields are left unchanged.
    """
    block = await client.get_block(block_id)
    if not block:
        raise HTTPException(status_code=404, detail=f"Block '{block_id}' not found")

    core = await block.core_retrieve()
    if not core or not core.core:
        raise HTTPException(
            status_code=404, detail=f"Core memory for block '{block_id}' not found"
        )

    persona = (
        body.persona_content
        if body.persona_content is not None
        else core.core.persona_content
    )
    human = (
        body.human_content
        if body.human_content is not None
        else core.core.human_content
    )

    # Use the internal core service to update
    from memblocks.models.units import CoreMemoryUnit

    updated = CoreMemoryUnit(persona_content=persona, human_content=human)
    # Store back via the block's core service
    await block._core.save(block_id, updated)

    return updated.model_dump()


# ---- Semantic Memory ----


@router.post("/semantic/{block_id}/search", response_model=List[Dict[str, Any]])
async def search_semantic_memories(
    block_id: str,
    body: SearchMemoriesRequest,
    client: MemBlocksClient = Depends(get_client),
) -> List[Dict[str, Any]]:
    """Search semantic memories in a block's Qdrant collection.

    Returns a flat list of SemanticMemoryUnit dicts ordered by relevance.
    """
    block = await client.get_block(block_id)
    if not block:
        raise HTTPException(status_code=404, detail=f"Block '{block_id}' not found")

    # Use the block's semantic retrieval directly
    context = await block.retrieve(body.query)
    flat: List[Dict[str, Any]] = [mem.model_dump() for mem in context.semantic]
    return flat
