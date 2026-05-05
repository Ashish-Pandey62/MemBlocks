"""EmbeddingProvider — config-injected wrapper around Ollama embeddings API."""

import requests
from concurrent.futures import ThreadPoolExecutor
from typing import Any, Dict, List, Optional, TYPE_CHECKING

from fastembed.sparse.sparse_text_embedding import SparseTextEmbedding

from memblocks.logger import get_logger

if TYPE_CHECKING:
    from memblocks.config import MemBlocksConfig

logger = get_logger(__name__)


class EmbeddingProvider:
    """
    Provides text embeddings via Ollama, and sparse embeddings via fastembed (SPLADE).

    Replaces: ``vector_db/embeddings.py`` → ``OllamaEmbeddings``

    Changes from OllamaEmbeddings:
    - Constructor takes ``MemBlocksConfig`` instead of reading the global
      ``settings`` object (embeddings.py:9 used ``settings`` as default arg,
      which evaluated at import time).
    - No module-level side-effects — safe to import without Ollama running.
    - Sparse (SPLADE) embedder is initialised lazily on first use to avoid
      the ~200 MB model download on cold starts when sparse is disabled.
    """

    def __init__(self, config: "MemBlocksConfig") -> None:
        """
        Args:
            config: Library configuration instance. Reads
                    ``config.embeddings_model``, ``config.ollama_base_url``,
                    and ``config.sparse_embeddings_model``.
        """
        self._model: str = config.embeddings_model
        self._base_url: str = config.ollama_base_url_embeddings
        self._endpoint: str = f"{config.ollama_base_url_embeddings}/api/embeddings"
        self._sparse_model: str = config.sparse_embeddings_model
        self._sparse_embedder: Optional[SparseTextEmbedding] = None

    # ------------------------------------------------------------------
    # Private helpers
    # ------------------------------------------------------------------

    def _get_sparse_embedder(self) -> SparseTextEmbedding:
        """Lazily initialise the SPLADE sparse embedder."""
        if self._sparse_embedder is None:
            logger.debug("Initialising SPLADE sparse embedder: %s", self._sparse_model)
            self._sparse_embedder = SparseTextEmbedding(model_name=self._sparse_model)
        return self._sparse_embedder

    # ------------------------------------------------------------------
    # Public interface — dense embeddings
    # ------------------------------------------------------------------

    def embed_text(self, text: str) -> List[float]:
        """
        Embed a single text string.

        Mirrors ``OllamaEmbeddings.embed_text()`` (embeddings.py:14-32).

        Args:
            text: Text to embed.

        Returns:
            Embedding vector as a list of floats.

        Raises:
            requests.HTTPError: If the Ollama API returns a non-2xx status.
            Exception: Re-raises any other network error.
        """
        payload = {
            "model": self._model,
            "prompt": text,
        }
        try:
            response = requests.post(
                self._endpoint,
                json=payload,
                timeout=30,
            )
            response.raise_for_status()
            result = response.json()
            return result.get("embedding")
        except Exception as e:
            logger.error("Error generating embedding: %s", e)
            raise

    def embed_documents(self, texts: List[str]) -> List[List[float]]:
        """
        Embed multiple texts in parallel.

        Mirrors ``OllamaEmbeddings.embed_documents()`` (embeddings.py:35-38).

        Args:
            texts: List of texts to embed.

        Returns:
            List of embedding vectors in the same order as ``texts``.
        """
        with ThreadPoolExecutor(max_workers=min(10, len(texts))) as executor:
            return list(executor.map(self.embed_text, texts))

    def get_dimension(self) -> int:
        """
        Return the dimension of the embedding model.

        Makes a single test embedding call to determine vector size.
        Mirrors ``OllamaEmbeddings.get_dimension()`` (embeddings.py:40-42).

        Returns:
            Integer dimension of the embedding vector.
        """
        sample = self.embed_text("test")
        return len(sample)

    # ------------------------------------------------------------------
    # Public interface — sparse embeddings (SPLADE via fastembed)
    # ------------------------------------------------------------------

    def embed_sparse_text(self, text: str) -> Dict[str, Any]:
        """
        Generate a sparse SPLADE embedding for a single text.

        Args:
            text: Text to embed.

        Returns:
            Dict with keys ``"indices"`` (List[int]) and ``"values"`` (List[float]).
        """
        embedder = self._get_sparse_embedder()
        embeddings = list(embedder.embed([text]))
        if not embeddings:
            return {"indices": [], "values": []}
        sparse_obj = embeddings[0]
        return {
            "indices": sparse_obj.indices.tolist(),
            "values": sparse_obj.values.tolist(),
        }

    def embed_sparse_documents(self, texts: List[str]) -> List[Dict[str, Any]]:
        """
        Generate sparse SPLADE embeddings for multiple texts.

        Args:
            texts: List of texts to embed.

        Returns:
            List of dicts, each with ``"indices"`` and ``"values"`` keys,
            in the same order as ``texts``.
        """
        embedder = self._get_sparse_embedder()
        embeddings = list(embedder.embed(texts))
        return [
            {"indices": s.indices.tolist(), "values": s.values.tolist()}
            for s in embeddings
        ]
