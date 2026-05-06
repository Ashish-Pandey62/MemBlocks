---
phase: 2-rewrite-readme-with-clear-folder-descrip
plan: 1
type: execute
wave: 1
depends_on: []
files_modified: [README.md]
autonomous: true
requirements: []
user_setup: []
must_haves:
  truths:
    - "README clearly states memblocks_lib is the core library"
    - "Each important folder has a clear purpose description"
    - "Demos (backend, FE, MCP, evaluation) are positioned as usage examples"
    - "Links to docs/ for further information are present"
  artifacts:
    - path: "README.md"
      provides: "Project documentation"
  key_links:
    - from: "README.md"
      to: "docs/memblockslib_docs/"
      via: "markdown link"
---

<objective>
Rewrite the README.md to clearly present memblocks_lib as the core library, with other folders (backend, frontend, mcp_server, evaluation) positioned as demonstrations of how to use it.

Purpose: Clarify the project's focus and help users understand what each folder does
Output: Updated README.md with clear folder descriptions
</objective>

<context>
@README.md (current - needs restructuring)
@docs/memblockslib_docs/01_SETUP_GUIDE.md (library setup reference)
</context>

<tasks>

<task type="auto">
  <name>Task 1: Rewrite README with clear folder descriptions</name>
  <files>README.md</files>
  <action>
Rewrite README.md with the following structural changes:

1. **Opening section**: Make it clear that MemBlocks is a Python library first, and the other folders are demos:
   - Lead with: "MemBlocks is a Python library for modular memory management in LLM applications"
   - Subtitle: "...with demo integrations for REST API, MCP server, CLI, and React frontend"

2. **Project Structure section**: Replace the current tree with a detailed description for each folder:

   - **memblocks_lib/** — THE CORE. The Python library that provides MemBlocksClient for programmatic memory management. Start here for any integration.
   
   - **mcp_server/** — DEMO: MCP server integration. Shows how to expose memory operations via the Model Context Protocol (for Claude Desktop, OpenCode, Cline).
   
   - **backend/** — DEMO: FastAPI REST API. Example web service wrapping the library with auth (Clerk) for building web apps.
   
   - **frontend/** — DEMO: React web interface. Simple workspace UI demonstrating how to build a memory-enabled chat app.
   
   - **evaluation/** — DEMO: Evaluation scripts. Scripts for benchmarking retrieval quality and testing the library.
   
   - **docs/** — Documentation. Detailed guides including:
     - docs/memblockslib_docs/01_SETUP_GUIDE.md — Library installation and configuration
     - docs/memblockslib_docs/02_METHODS_AND_INTERFACES.md — API reference
     - docs/memblockslib_docs/03_TECHNICAL_OVERVIEW.md — Architecture deep-dive
   
   - **tests/** — Test suite for the library
   
   - **docker-compose.yml** — Infrastructure (MongoDB, Qdrant, Ollama) required by the library

3. **Quick Start section**: Update to emphasize the library first, then show the three usage options as equivalent approaches

4. **Keep**: The conceptual explanation (memory blocks as cartridges, layered memory, intelligent retrieval) — these are the core concepts

5. **Add**: At the end of Project Structure, add a sentence: "For detailed library documentation, see docs/memblockslib_docs/"
  </action>
  <verify>
    <automated>grep -c "memblocks_lib/" README.md && grep -c "DEMO:" README.md</automated>
  </verify>
  <done>
    - README states memblocks_lib is the core library in opening paragraph
    - Each folder has a clear one-line description with (DEMO) or (THE CORE) tags
    - Links to docs/memblockslib_docs/ are present
    - Backend, frontend, MCP, evaluation are positioned as usage demonstrations
  </done>
</task>

</tasks>

<verification>
- README.md exists and contains "memblocks_lib" references
- Folder descriptions include "(DEMO)" or "(THE CORE)" tags
- Link to docs/memblockslib_docs/ exists
</verification>

<success_criteria>
README.md clearly communicates:
1. MemBlocks is a Python library first
2. What each folder is and how it connects
3. Where to go for detailed documentation
</success_criteria>

<output>
After completion, create `.planning/quick/2-rewrite-readme-with-clear-folder-descrip/2-SUMMARY.md`
</output>
