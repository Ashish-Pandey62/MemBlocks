"""Analytics router — LLM usage and performance metrics (persistent)."""

import asyncio
from datetime import datetime, timedelta
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, Depends, HTTPException

from backend.src.api.dependencies import get_client
from backend.src.api.routers.auth import CurrentUser, get_current_user
from memblocks import MemBlocksClient

router = APIRouter(prefix="/analytics", tags=["analytics"])

_last_sync_time: Optional[datetime] = None
_sync_interval_seconds = 60


async def _sync_llm_usage_to_db(client: MemBlocksClient) -> int:
    """Sync in-memory LLM usage records to MongoDB.

    Returns the number of records synced.
    """
    global _last_sync_time

    records = client.llm_usage.get_records(limit=500)
    if not records:
        return 0

    records_to_save = []
    for rec in records:
        records_to_save.append(
            {
                "timestamp": rec.timestamp.isoformat(),
                "call_type": rec.call_type.value,
                "block_id": rec.block_id,
                "user_id": rec.block_id.split("_")[0] if rec.block_id else None,
                "model": rec.model,
                "provider": rec.provider,
                "input_tokens": rec.input_tokens,
                "output_tokens": rec.output_tokens,
                "total_tokens": rec.total_tokens,
                "latency_ms": rec.latency_ms,
                "success": rec.success,
                "error": rec.error,
            }
        )

    if records_to_save:
        count = await client.mongo.save_llm_usage_records(records_to_save)
        _last_sync_time = datetime.utcnow()
        return count

    return 0


async def _ensure_synced(client: MemBlocksClient) -> None:
    """Ensure recent records are synced to DB."""
    global _last_sync_time

    if (
        _last_sync_time is None
        or (datetime.utcnow() - _last_sync_time).seconds > _sync_interval_seconds
    ):
        await _sync_llm_usage_to_db(client)


@router.get("/token-usage/per-block", response_model=Dict[str, Any])
async def get_token_usage_per_block(
    days: int = 7,
    current_user: CurrentUser = Depends(get_current_user),
    client: MemBlocksClient = Depends(get_client),
) -> Dict[str, Any]:
    """Get token usage statistics per block for the user (persistent).

    Returns aggregated LLM usage grouped by block for the specified number of days.
    Data is persisted to MongoDB for historical tracking.

    Args:
        days: Number of days to look back (default: 7)
    """
    await _ensure_synced(client)

    blocks = await client.get_user_blocks(current_user.user_id)
    cutoff_time = datetime.utcnow() - timedelta(days=days)
    block_ids = [b.id for b in blocks]

    block_usage = {}
    overall = {
        "total_input_tokens": 0,
        "total_output_tokens": 0,
        "total_tokens": 0,
        "total_requests": 0,
        "total_latency_ms": 0.0,
        "by_call_type": {},
    }

    if not block_ids:
        return {
            "period_days": days,
            "generated_at": datetime.utcnow().isoformat(),
            "total_blocks_with_usage": 0,
            "blocks": {},
            "overall": overall,
        }

    for block in blocks:
        block_id = block.id

        records = await client.mongo.get_llm_usage_by_block(
            block_id=block_id,
            since=cutoff_time,
            limit=5000,
        )

        call_type_stats: Dict[str, Dict[str, int]] = {}
        block_input = 0
        block_output = 0
        block_total = 0
        block_requests = 0
        block_latency = 0.0

        for rec in records:
            call_type = rec.get("call_type", "unknown")
            if call_type not in call_type_stats:
                call_type_stats[call_type] = {
                    "request_count": 0,
                    "input_tokens": 0,
                    "output_tokens": 0,
                    "total_tokens": 0,
                    "total_latency_ms": 0,
                }

            stats = call_type_stats[call_type]
            stats["request_count"] += 1
            stats["input_tokens"] += rec.get("input_tokens", 0)
            stats["output_tokens"] += rec.get("output_tokens", 0)
            stats["total_tokens"] += rec.get("total_tokens", 0)
            stats["total_latency_ms"] += rec.get("latency_ms", 0)

            block_input += rec.get("input_tokens", 0)
            block_output += rec.get("output_tokens", 0)
            block_total += rec.get("total_tokens", 0)
            block_requests += 1
            block_latency += rec.get("latency_ms", 0)

        if block_requests > 0:
            call_type_breakdown = {}
            for ct, stats in call_type_stats.items():
                call_type_breakdown[ct] = {
                    "request_count": stats["request_count"],
                    "input_tokens": stats["input_tokens"],
                    "output_tokens": stats["output_tokens"],
                    "total_tokens": stats["total_tokens"],
                    "avg_latency_ms": round(
                        stats["total_latency_ms"] / stats["request_count"], 2
                    ),
                }

            block_usage[block_id] = {
                "block_name": block.name,
                "block_description": block.description,
                "request_count": block_requests,
                "input_tokens": block_input,
                "output_tokens": block_output,
                "total_tokens": block_total,
                "total_latency_ms": round(block_latency, 2),
                "avg_latency_ms": round(block_latency / block_requests, 2),
                "by_call_type": call_type_breakdown,
            }

            overall["total_input_tokens"] += block_input
            overall["total_output_tokens"] += block_output
            overall["total_tokens"] += block_total
            overall["total_requests"] += block_requests
            overall["total_latency_ms"] += block_latency

            for ct, ct_data in call_type_breakdown.items():
                if ct not in overall["by_call_type"]:
                    overall["by_call_type"][ct] = {
                        "request_count": 0,
                        "input_tokens": 0,
                        "output_tokens": 0,
                        "total_tokens": 0,
                    }
                overall["by_call_type"][ct]["request_count"] += ct_data["request_count"]
                overall["by_call_type"][ct]["input_tokens"] += ct_data["input_tokens"]
                overall["by_call_type"][ct]["output_tokens"] += ct_data["output_tokens"]
                overall["by_call_type"][ct]["total_tokens"] += ct_data["total_tokens"]

    if overall["total_requests"] > 0:
        overall["avg_latency_ms"] = round(
            overall["total_latency_ms"] / overall["total_requests"], 2
        )

    return {
        "period_days": days,
        "generated_at": datetime.utcnow().isoformat(),
        "total_blocks_with_usage": len(block_usage),
        "blocks": block_usage,
        "overall": overall,
    }


@router.get("/token-usage/block/{block_id}", response_model=Dict[str, Any])
async def get_token_usage_block(
    block_id: str,
    days: int = 7,
    current_user: CurrentUser = Depends(get_current_user),
    client: MemBlocksClient = Depends(get_client),
) -> Dict[str, Any]:
    """Get detailed token usage for a specific block (persistent).

    Returns per-call-type breakdown with latency metrics.
    """
    await _ensure_synced(client)

    block = await client.get_block(block_id)
    if not block:
        raise HTTPException(status_code=404, detail=f"Block '{block_id}' not found")
    if block.user_id != current_user.user_id:
        raise HTTPException(
            status_code=403, detail="Cannot access another user's block"
        )

    cutoff_time = datetime.utcnow() - timedelta(days=days)

    records = await client.mongo.get_llm_usage_by_block(
        block_id=block_id,
        since=cutoff_time,
        limit=5000,
    )

    call_types: Dict[str, Dict[str, Any]] = {}
    total_input = 0
    total_output = 0
    total_tokens = 0
    total_requests = 0
    total_latency = 0.0

    for rec in records:
        call_type = rec.get("call_type", "unknown")
        if call_type not in call_types:
            call_types[call_type] = {
                "request_count": 0,
                "input_tokens": 0,
                "output_tokens": 0,
                "total_tokens": 0,
                "total_latency_ms": 0,
            }

        ct = call_types[call_type]
        ct["request_count"] += 1
        ct["input_tokens"] += rec.get("input_tokens", 0)
        ct["output_tokens"] += rec.get("output_tokens", 0)
        ct["total_tokens"] += rec.get("total_tokens", 0)
        ct["total_latency_ms"] += rec.get("latency_ms", 0)

        total_input += rec.get("input_tokens", 0)
        total_output += rec.get("output_tokens", 0)
        total_tokens += rec.get("total_tokens", 0)
        total_requests += 1
        total_latency += rec.get("latency_ms", 0)

    for call_type, data in call_types.items():
        data["avg_latency_ms"] = (
            round(data["total_latency_ms"] / data["request_count"], 2)
            if data["request_count"] > 0
            else 0
        )

    return {
        "block_id": block_id,
        "block_name": block.name,
        "period_days": days,
        "generated_at": datetime.utcnow().isoformat(),
        "total_requests": total_requests,
        "total_input_tokens": total_input,
        "total_output_tokens": total_output,
        "total_tokens": total_tokens,
        "total_latency_ms": round(total_latency, 2),
        "avg_latency_ms": round(total_latency / total_requests, 2)
        if total_requests > 0
        else 0,
        "by_call_type": call_types,
    }


@router.get("/token-usage/recent", response_model=List[Dict[str, Any]])
async def get_recent_llm_calls(
    block_id: Optional[str] = None,
    limit: int = 20,
    current_user: CurrentUser = Depends(get_current_user),
    client: MemBlocksClient = Depends(get_client),
) -> List[Dict[str, Any]]:
    """Get recent LLM call records (from database).

    Returns individual LLM call records, optionally filtered by block.
    """
    await _ensure_synced(client)

    blocks = await client.get_user_blocks(current_user.user_id)
    allowed_block_ids = {b.id for b in blocks}

    if block_id:
        if block_id not in allowed_block_ids:
            raise HTTPException(
                status_code=403, detail="Cannot access another user's block"
            )
        records = await client.mongo.get_llm_usage_by_block(
            block_id=block_id,
            limit=limit,
        )
    else:
        records = await client.mongo.get_user_llm_usage(
            user_id=current_user.user_id,
            block_ids=list(allowed_block_ids),
            limit=limit,
        )

    return [
        {
            "timestamp": rec.get("timestamp"),
            "call_type": rec.get("call_type"),
            "block_id": rec.get("block_id"),
            "model": rec.get("model"),
            "provider": rec.get("provider"),
            "input_tokens": rec.get("input_tokens", 0),
            "output_tokens": rec.get("output_tokens", 0),
            "total_tokens": rec.get("total_tokens", 0),
            "latency_ms": round(rec.get("latency_ms", 0), 2),
            "success": rec.get("success", True),
        }
        for rec in records
    ]


@router.post("/token-usage/sync", response_model=Dict[str, Any])
async def sync_llm_usage(
    current_user: CurrentUser = Depends(get_current_user),
    client: MemBlocksClient = Depends(get_client),
) -> Dict[str, Any]:
    """Manually trigger sync of in-memory LLM usage records to database.

    Returns the number of records synced.
    """
    count = await _sync_llm_usage_to_db(client)
    return {
        "synced_records": count,
        "synced_at": datetime.utcnow().isoformat(),
    }
