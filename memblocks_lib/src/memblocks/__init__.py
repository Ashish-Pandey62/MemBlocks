"""memBlocks - Intelligent modular memory management system for LLMs.

Public API surface — import from here for convenience:

    from memblocks import MemBlocksClient, MemBlocksConfig
    from memblocks import Block, Session, RetrievalResult
    from memblocks import LLMSettings, LLMTaskSettings
    from memblocks.models import MemoryBlock, SemanticMemoryUnit, CoreMemoryUnit
    from memblocks.llm.base import LLMProvider
    from memblocks.llm.groq_provider import GroqLLMProvider
    from memblocks.llm.gemini_provider import GeminiLLMProvider
    from memblocks.llm.ollama_provider import OllamaLLMProvider
    from memblocks.prompts import PS1_SEMANTIC_PROMPT
"""

__version__ = "0.1.0"

# Core entry-point (import last to avoid circular issues — client imports all others)
from memblocks.config import MemBlocksConfig
from memblocks.client import MemBlocksClient

# LLM abstractions
from memblocks.llm.base import LLMProvider
from memblocks.llm.groq_provider import GroqLLMProvider
from memblocks.llm.gemini_provider import GeminiLLMProvider
from memblocks.llm.ollama_provider import OllamaLLMProvider
from memblocks.llm.task_settings import LLMTaskSettings, LLMSettings

# Stateful objects returned by the client
from memblocks.services.block import Block
from memblocks.services.session import Session

# Key model types users commonly type-hint against
from memblocks.models import (
    MemoryBlock,
    MemoryBlockMetaData,
    RetrievalResult,
    SemanticMemoryUnit,
    CoreMemoryUnit,
    ResourceMemoryUnit,
    MemoryOperation,
)

__all__ = [
    "__version__",
    # Client
    "MemBlocksClient",
    "MemBlocksConfig",
    # LLM
    "LLMProvider",
    "GroqLLMProvider",
    "GeminiLLMProvider",
    "OllamaLLMProvider",
    "LLMTaskSettings",
    "LLMSettings",
    # Stateful objects
    "Block",
    "Session",
    # Models
    "MemoryBlock",
    "MemoryBlockMetaData",
    "RetrievalResult",
    "SemanticMemoryUnit",
    "CoreMemoryUnit",
    "ResourceMemoryUnit",
    "MemoryOperation",
]
