# Hybrid Search Testing Guide

This document provides step-by-step commands to test the hybrid search functionality in memBlocks.

## What is Hybrid Search?

The hybrid search combines:
1. **BM25/Sparse Embeddings** - Keyword-based search using Qdrant's native hybrid search
2. **Dense Embeddings** - Semantic vector similarity search
3. **Manual Keyword/Entity** - Payload-based keyword and entity matching (combined with BM25 results)

## Test Options

### Option 1: Run the Python Test Script

```bash
# Navigate to project directory
cd C:\Study\Programming\qdrant_check

# Run the hybrid search test
uv run python test_hybrid.py
```

**Expected Output:**
```
[HybridRetrieve]
   Query    : 'Tell me about the app in San Francisco?'
   Keywords : ['tell', 'about', 'app', 'san', 'francisco']
   Entities : ['tell', 'san francisco']
   Native Hybrid Search -> 3 result(s) in 0.0065s
   Idle Manual Scroll    -> 2 result(s) in 0.0025s

--- Retrieved Results ---
- The user has a meeting in San Francisco regarding the new app delivery.
- San Francisco is a city in California.
- User deployed the application to production yesterday.
```

---

### Option 2: Test via API

#### Step 1: Start the Backend Server

```bash
# Terminal 1: Start the backend
cd C:\Study\Programming\qdrant_check
uv run python -m uvicorn backend.src.api.main:app --reload --port 8001
```

#### Step 2: Check Health Endpoint

```bash
# Terminal 2: Test health check
curl http://localhost:8001/health
```

**Response:**
```json
{"status": "ok"}
```

#### Step 3: Create a New Block

```bash
# Create a new memory block
curl -X POST http://localhost:8001/blocks \
  -H "Content-Type: application/json" \
  -d '{
    "user_id": "test_user",
    "name": "Hybrid Test Block",
    "description": "Testing hybrid search"
  }'
```

#### Step 4: Search Semantic Memories (Hybrid)

```bash
# Search memories using hybrid search
curl -X POST http://localhost:8001/memory/semantic/block_fd620a9f4b17/search \
  -H "Content-Type: application/json" \
  -d '{
    "query": "Tell me about the app in San Francisco?",
    "top_k": 5
  }'
```

Replace `<BLOCK_ID>` with the block ID returned from Step 3 (e.g., `block_xxxxxx`).

**Response:**
```json
[
  {
    "content": "The user has a meeting in San Francisco regarding the new app delivery.",
    "type": "event",
    ...
  },
  {
    "content": "San Francisco is a city in California.",
    "type": "fact",
    ...
  }
]
```

#### Step 5: Get Core Memory

```bash
# Get core memory for a block
curl http://localhost:8001/memory/core/<BLOCK_ID>
```

#### Step 6: Update Core Memory

```bash
# Update core memory
curl -X PATCH http://localhost:8001/memory/core/<BLOCK_ID> \
  -H "Content-Type: application/json" \
  -d '{
    "persona_content": "You are a helpful AI assistant.",
    "human_content": "User is a software developer."
  }'
```

---

### Option 3: Test via Python Script (Custom)

Create a custom test script:

```python
import asyncio
from memblocks.client import MemBlocksClient
from memblocks.config import MemBlocksConfig

async def test_hybrid():
    config = MemBlocksConfig()
    client = MemBlocksClient(config)
    
    # Subscribe to transparency events
    def log_retrieval(payload):
        print(f"[Transparency] Retrieved {payload['num_results']} via {payload['source']}")
    
    client.subscribe("on_memory_retrieved", log_retrieval)
    
    try:
        # Get or create user
        user = await client.get_or_create_user("test_user")
        
        # Get user's blocks
        blocks = await client.get_user_blocks("test_user")
        
        if blocks:
            block = blocks[0]
            
            # Perform hybrid search
            context = await block.retrieve("Tell me about the app in San Francisco?")
            
            print("\n--- Retrieved Memories ---")
            for mem in context.semantic:
                print(f"- {mem.content}")
                
            # Check retrieval log
            log = client.get_retrieval_log().get_last_retrieval()
            print(f"\nSource: {log.source}")
            print(f"Results: {log.num_results}")
            
    finally:
        await client.close()

asyncio.run(test_hybrid())
```

Save as `test_custom.py` and run:
```bash
uv run python test_custom.py
```

---

## Understanding the Transparency Output

When you run the test, you'll see:

| Field | Description |
|-------|-------------|
| `Query` | The search query text |
| `Keywords` | Extracted keywords from query (used for matching) |
| `Entities` | Extracted entities from query (used for matching) |
| `Native Hybrid Search` | BM25 + dense vector search results |
| `Idle Manual Scroll` | Manual keyword/entity search results (for benchmarking) |

### Performance Metrics

The transparency layer shows timing for both search methods:
- **Native Hybrid Search** - Time for BM25 + semantic vector search
- **Idle Manual Scroll** - Time for manual keyword/entity matching (can be used for performance comparison)

---

## API Endpoints Summary

| Endpoint | Method | Description |
|---------|--------|-------------|
| `/health` | GET | Health check |
| `/blocks` | GET | List all blocks |
| `/blocks` | POST | Create new block |
| `/blocks/{block_id}` | GET | Get block by ID |
| `/blocks/{block_id}` | DELETE | Delete block |
| `/memory/core/{block_id}` | GET | Get core memory |
| `/memory/core/{block_id}` | PATCH | Update core memory |
| `/memory/semantic/{block_id}/search` | POST | Search semantic memories (hybrid) |
| `/chat/chat` | POST | Chat with memory context |

---

## Troubleshooting

### Issue: UnicodeEncodeError on Windows

If you see encoding errors on Windows:
```bash
# Set UTF-8 encoding before running
set PYTHONIOENCODING=utf-8
uv run python test_hybrid.py
```

### Issue: Connection Errors

Make sure MongoDB and Qdrant are running:
```bash
# Check if services are accessible
curl http://localhost:6333/health  # Qdrant
```

### Issue: No Results Found

- Ensure memories are stored in the block first
- Check that the query matches stored keywords/entities
- Verify the block ID is correct
