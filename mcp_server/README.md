## Quick Start

### Prerequisites

- Python 3.11+
- UV package manager installed
- Docker running (for Qdrant and Ollama)
- MCP-compatible client (Claude Desktop, OpenCode, Cline, etc.)

### Installation

1. **Install project dependencies**:
   ```bash
   uv sync --all-packages
   ```

2. **Install MCP server package** (optional but recommended):
   ```bash
   uv pip install -e mcp_server
   ```

3. **Verify installation**:
   ```bash
   memblocks-mcp --help
   memblocks-cli --help
   ```

   If commands aren't found, use UV to run them:
   ```bash
   uv run memblocks-mcp --help
   uv run memblocks-cli --help
   ```

### Running the Server

**Default (stdio transport)**:
```bash
memblocks-mcp
```

**Streamable HTTP transport** (recommended for web/external access):
```bash
memblocks-mcp --transport streamable-http --port 8002
```
Server will be available at `http://localhost:8002/mcp`

**Streamable HTTP with CORS** (for browser-based MCP clients):
```bash
memblocks-mcp --transport streamable-http --port 8002 --cors
```
Allow specific origins instead of all:
```bash
memblocks-mcp --transport streamable-http --port 8002 --cors-origins "https://example.com,https://app.example.com"
```
**Custom path** (default: `/mcp`):
```bash
memblocks-mcp --transport streamable-http --port 8002 --path /api/mcp
```

**SSE transport** (legacy, for backward compatibility):
```bash
memblocks-mcp --transport sse --port 8002
```
Server will be available at `http://localhost:8002/sse`

**Bind to specific host** (default: `0.0.0.0` for all interfaces):
```bash
memblocks-mcp --transport streamable-http --host 127.0.0.1 --port 8002
```

---

## Configuration

### For OpenCode CLI (stdio)

Add to your `opencode.json` (or create it in your project root):

```json
{
  "$schema": "https://opencode.ai/config.json",
  "mcp": {
    "memblocks": {
      "type": "local",
      "command": ["uv", "run", "python", "-m", "mcp_server.server"],
      "environment": {
        "MEMBLOCKS_USER_ID": "your_user_id"
      },
      "enabled": true
    }
  }
}
```

**Important**: Replace `"your_user_id"` with your actual user ID (from MemBlocks backend registration).

### For OpenCode CLI (HTTP/SSE)

```json
{
  "$schema": "https://opencode.ai/config.json",
  "mcp": {
    "memblocks": {
      "type": "url",
      "url": "http://localhost:8002/mcp",
      "enabled": true
    }
  }
}
```

If you change the server path, update the URL accordingly:

```json
{
  "$schema": "https://opencode.ai/config.json",
  "mcp": {
    "memblocks": {
      "type": "url",
      "url": "http://localhost:8002/api/mcp",
      "enabled": true
    }
  }
}
```

### For Claude Desktop (stdio)

Add to your Claude Desktop config (`~/Library/Application Support/Claude/claude_desktop_config.json` on macOS, `%APPDATA%\Claude\claude_desktop_config.json` on Windows):

```json
{
  "mcpServers": {
    "memblocks": {
      "command": "uv",
      "args": ["run", "--directory", "/path/to/MemBlocks/mcp_server", "memblocks-mcp"],
      "env": {
        "MEMBLOCKS_USER_ID": "your_user_id"
      }
    }
  }
}
```

### For Claude Desktop (HTTP/SSE)

```json
{
  "mcpServers": {
    "memblocks": {
      "url": "http://localhost:8002/mcp",
      "transport": "http"
    }
  }
}
```

If you change the server path, update the URL accordingly:

```json
{
  "mcpServers": {
    "memblocks": {
      "url": "http://localhost:8002/api/mcp",
      "transport": "http"
    }
  }
}
```

### For Cline (VS Code Extension - stdio)

Add to Cline's MCP settings:

```json
{
  "mcpServers": {
    "memblocks": {
      "command": "uv",
      "args": ["run", "python", "-m", "mcp_server.server"],
      "cwd": "/path/to/MemBlocks",
      "env": {
        "MEMBLOCKS_USER_ID": "your_user_id"
      }
    }
  }
}
```

### For Browser-Based MCP Clients

Enable CORS on the server:

```bash
memblocks-mcp --transport streamable-http --port 8002 --cors
```

Use the same HTTP URL in your client:
```text
http://localhost:8002/mcp
```


---

## CLI Commands

MemBlocks provides a CLI for managing the active memory block outside of AI assistant interactions.

### View User Info

```bash
memblocks-cli whoami
```

Shows your current user ID.

### List Memory Blocks

```bash
memblocks-cli list-blocks
```

Lists all memory blocks accessible to your user.

### Set Active Block

```bash
memblocks-cli set-block <block_id>
```

Sets which memory block the MCP server should use for subsequent operations.

### Get Active Block

```bash
memblocks-cli get-block
```

Shows the currently active memory block ID.

### Lock/Unlock MCP

```bash
memblocks-cli lock
memblocks-cli unlock
```

Prevents the MCP server from switching blocks (useful during focused work sessions).

---

## Available MCP Tools

When connected to an AI assistant, the following tools become available:

### Memory Block Management

#### `memblocks_list_blocks`
List all memory blocks for the configured user.

**Parameters**: None

**Returns**: JSON array of block objects with id, name, description, and is_active flag

#### `memblocks_create_block`
Create a new memory block.

**Parameters**:
- `name` (string, required): Human-readable block name
- `description` (string, optional): Block description (max 500 chars)

**Returns**: Created block details

**Note**: New blocks are not automatically activated. Use `memblocks_set_block` to activate.

#### `memblocks_set_block`
Activate a memory block for subsequent operations.

**Parameters**:
- `block_id` (string, required): ID of the block to activate

**Returns**: Confirmation with block ID and name

---

### Memory Storage Tools

#### `memblocks_store` (Recommended)
Store a fact to BOTH semantic and core memory in one call.

**Parameters**:
- `fact` (string, required): The fact or knowledge to store

**Returns**: `{"status": "accepted"}` (processed in background)

**When to use**: Default choice for most storage needs. Proactively call this when conversation contains information worth remembering.

#### `memblocks_store_semantic`
Store a fact to semantic memory only (searchable via vector search).

**Parameters**:
- `fact` (string, required): The fact to store

**Returns**: `{"status": "accepted"}` (processed in background)

**When to use**: For factual knowledge best retrieved by topic keyword.

#### `memblocks_store_to_core`
Store a fact to core memory only (always-on persona and human context).

**Parameters**:
- `fact` (string, required): The fact to add/update in core memory

**Returns**: `{"status": "accepted"}` (processed in background)

**When to use**: For stable, identity-level facts about the user (name, role, location, preferences).

---

### Memory Retrieval Tools

#### `memblocks_retrieve` (Recommended)
Retrieve memories from both core and semantic memory.

**Parameters**:
- `query` (string, required): Search query for semantic memory

**Returns**: Formatted string with core memory + semantically relevant memories

**When to use**: Default choice for retrieval. Provides most complete context.

#### `memblocks_retrieve_semantic`
Retrieve only semantic memories.

**Parameters**:
- `query` (string, required): Search query

**Returns**: Semantically relevant memories formatted for LLM injection

#### `memblocks_retrieve_core`
Retrieve only core memory (full content, no query needed).

**Parameters**: None

**Returns**: Full core memory (persona + human sections)

---

### MCP Resources

- `memblocks://active-block` — Current active memory block info
- `memblocks://tools` — Usage guide for all MCP tools

---

### MCP Prompts

- `memblocks_storage_policy` — Mandatory behavioral policy for proactive memory storage

---

## Shared State Management

### Active Block State

The CLI and MCP server share state through a file:

```
~/.config/memblocks/active_block.json
```

**Contents**:
```json
{
  "user_id": "user_123",
  "block_id": "block_abc",
  "mcp_locked": false,
  "last_updated": "2024-03-15T10:30:00Z"
}
```

**Fields**:
- `user_id`: Current user ID
- `block_id`: Active memory block ID
- `mcp_locked`: Whether block switching is locked
- `last_updated`: Timestamp of last update

### Why This Matters

- Set a block via CLI: `memblocks-cli set-block block_abc`
- AI assistant automatically uses that block for all operations
- Lock prevents accidental block switching during focused sessions
- Persists across AI assistant restarts

---

## Usage Examples

### Example 1: Project-Specific Memory

```bash
# Create a memory block for a project
memblocks-cli list-blocks  # Find or create a block

# Set it as active
memblocks-cli set-block block_project_x

# Lock it to prevent switching
memblocks-cli lock

# Now use AI assistant normally
# All memories stored/retrieved from "Project X" block
```

### Example 2: Multi-Context Switching

```bash
# Morning: Work mode
memblocks-cli set-block block_work

# Ask AI about work projects
# Memories stored in work block

# Evening: Personal mode
memblocks-cli set-block block_personal

# Ask AI about personal topics
# Completely separate memory space
```

### Example 3: Team Collaboration

```bash
# Set team block (shared with colleagues)
memblocks-cli set-block block_team_docs

# AI assistant can now:
# - Access team-shared knowledge
# - Add information visible to whole team
# - Keep personal blocks separate
```

---

## Testing Your Setup

### 1. Verify MCP Server Starts (stdio)

```bash
uv run python -m mcp_server.server
```

Should start without errors. Press Ctrl+C to stop.

### 2. Verify HTTP Transport

```bash
# Start with streamable-http transport
memblocks-mcp --transport streamable-http --port 8002
```

If testing from a browser-based MCP client, enable CORS:
```bash
memblocks-mcp --transport streamable-http --port 8002 --cors
```

Test the endpoint:
```bash
curl http://localhost:8002/mcp
```

For SSE transport:
```bash
memblocks-mcp --transport sse --port 8002
curl http://localhost:8002/sse
```

### 3. Test CLI Commands

```bash
# Check user ID
memblocks-cli whoami

# List blocks
memblocks-cli list-blocks

# Set a block (use actual block ID from list)
memblocks-cli set-block <block_id>

# Verify it's set
memblocks-cli get-block
```

### 4. Test MCP Integration (stdio)

In your AI assistant:

```
User: List my memory blocks
AI: [Should show your blocks via MCP tool call]

User: Remember that my favorite color is blue
AI: [Should store in semantic memory]

User: What's my favorite color?
AI: [Should retrieve from memory: "Your favorite color is blue"]
```

### 5. Test MCP Integration (HTTP/SSE)

Configure your MCP client to connect via HTTP:

```json
{
  "mcpServers": {
    "memblocks": {
      "url": "http://localhost:8002/mcp",
      "transport": "http"
    }
  }
}
```

---

## Troubleshooting

### "ModuleNotFoundError: No module named 'mcp_server'"

**Solution**:
```bash
uv pip install -e mcp_server
```

### "Command not found: memblocks-cli"

**Solution**: Use UV to run directly:
```bash
uv run memblocks-cli --help
```

Or ensure your UV virtual environment scripts are on `PATH`.

### MCP Server Not Connecting (stdio)

**Check**:
1. Is Docker running? (Qdrant and Ollama needed)
2. Is `MEMBLOCKS_USER_ID` set correctly in config?
3. Check MCP server logs for errors
4. Verify `.env` file has correct API keys

### MCP Server Not Connecting (HTTP/SSE)

**Check**:
1. Is the server running with `--transport streamable-http` or `--transport sse`?
2. Can you reach the URL via curl? `curl http://localhost:8002/mcp`
3. Check firewall isn't blocking the port
4. Verify the correct path (`/mcp` for streamable-http, `/sse` for SSE)

### Browser Client Fails with CORS Error

**Fix**:
1. Start the server with CORS enabled: `memblocks-mcp --transport streamable-http --port 8002 --cors`
2. If you need restricted origins, use: `--cors-origins "https://example.com"`
3. Ensure your client uses the correct URL path (`/mcp` by default)

### Active Block Not Persisting

**Check**:
1. Does `~/.config/memblocks/` directory exist?
2. Do you have write permissions?
3. Run `memblocks-cli get-block` to verify state file

### Memory Not Being Retrieved

**Check**:
1. Is a block set as active? (`memblocks-cli get-block`)
2. Does the block have memories? (Check via backend API)
3. Are Qdrant and Ollama services running? (`docker-compose ps`)

---

## Advanced Configuration

### Custom State File Location

Set environment variable:

```bash
export MEMBLOCKS_STATE_PATH=/custom/path/active_block.json
```

### Multiple User Profiles

Create separate state files for different users:

```bash
# User 1
MEMBLOCKS_STATE_PATH=~/.config/memblocks/user1.json memblocks-cli whoami

# User 2
MEMBLOCKS_STATE_PATH=~/.config/memblocks/user2.json memblocks-cli whoami
```

### Custom Port or Host

Use CLI arguments (no code changes needed):

```bash
# Custom port
memblocks-mcp --transport streamable-http --port 9000

# Bind to localhost only
memblocks-mcp --transport streamable-http --host 127.0.0.1 --port 8002

# Use SSE transport
memblocks-mcp --transport sse --port 8002
```

---

## MCP Server Architecture

```
┌─────────────────┐
│  AI Assistant   │
│ (Claude/OpenCode)│
└────────┬────────┘
         │
         ├─ stdio (default, local)
         ├─ streamable-http (recommended for web)
         └─ SSE (legacy)
         │
         ▼
┌─────────────────┐
│  MCP Server     │
│  (server.py)    │
│  :8002 /mcp     │
└────────┬────────┘
         │
         ▼
┌─────────────────┐
│ MemBlocks Lib   │
│  (Client API)   │
└────────┬────────┘
         │
         ▼
┌─────────────────┐
│  Infrastructure │
│ Qdrant/Ollama   │
└─────────────────┘
```

**Transports**:
- **stdio**: Default, runs as subprocess, ideal for local MCP clients
- **streamable-http**: HTTP-based, recommended for web/external access (port 8002)
- **SSE**: Server-Sent Events, legacy transport for backward compatibility

**Flow**:
1. AI assistant calls MCP tool via configured transport
2. MCP server validates and processes request
3. Calls MemBlocks library API
4. Library interacts with vector DB and LLMs
5. Results returned through MCP to AI assistant

---

## Additional Resources

- [Architecture Overview](../ARCHITECTURE.md)
- [Library Setup Guide](../memblockslib_docs/01_SETUP_GUIDE.md)
- [Library Methods and Interfaces](../memblockslib_docs/02_METHODS_AND_INTERFACES.md)
- [Backend REST API](../backend/API.md)
- [Deployment Guide](../backend/DEPLOYMENT.md)
- [MCP Protocol Specification](https://spec.modelcontextprotocol.io/)

---
