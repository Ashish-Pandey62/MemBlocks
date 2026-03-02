"""EmbeddingProvider — config-injected wrapper around Ollama embeddings API."""

import requests
from concurrent.futures import ThreadPoolExecutor
from typing import List, TYPE_CHECKING, Dict, Any

from fastembed.sparse.sparse_text_embedding import SparseTextEmbedding

if TYPE_CHECKING:
    from memblocks.config import MemBlocksConfig


class EmbeddingProvider:
    """
    Provides text embeddings via Ollama.

    Replaces: ``vector_db/embeddings.py`` → ``OllamaEmbeddings``

    Changes from OllamaEmbeddings:
    - Constructor takes ``MemBlocksConfig`` instead of reading the global
      ``settings`` object (embeddings.py:9 used ``settings`` as default arg,
      which evaluated at import time).
    - No module-level side-effects — safe to import without Ollama running.
    """

    def __init__(self, config: "MemBlocksConfig") -> None:
        """
        Args:
            config: Library configuration instance. Reads
                    ``config.embeddings_model`` and ``config.ollama_base_url``.
        """
        self._model: str = config.embeddings_model
        self._sparse_model: str = config.sparse_embeddings_model
        self._base_url: str = config.ollama_base_url
        self._endpoint: str = f"{config.ollama_base_url}/api/embeddings"

        # Initialize fastembed sparse model
        self._sparse_embedder = SparseTextEmbedding(model_name=self._sparse_model)

    # ------------------------------------------------------------------
    # Public interface
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
            print(f"Error generating embedding: {e}")
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

    def embed_sparse_text(self, text: str) -> Dict[str, Any]:
        """
        Embed a single text string into a sparse vector using fastembed.

        Args:
            text: Text to embed.

        Returns:
            Dictionary containing 'indices' and 'values' for the sparse vector.
        """
        # fastembed returns a generator of SparseEmbedding objects
        embeddings = list(self._sparse_embedder.embed([text]))
        if not embeddings:
            return {"indices": [], "values": []}
        
        # Access the first item (since we passed a single text)
        sparse_obj = embeddings[0]
        # fastembed returns indices as ints and values as floats
        return {
            "indices": sparse_obj.indices.tolist(),
            "values": sparse_obj.values.tolist(),
        }

    def embed_sparse_documents(self, texts: List[str]) -> List[Dict[str, Any]]:
        """
        Embed multiple texts into sparse vectors in parallel.

        Args:
            texts: List of texts to embed.

        Returns:
            List of dictionaries containing 'indices' and 'values'.
        """
        # fastembed handles batch natively
        embeddings = list(self._sparse_embedder.embed(texts))
        
        result = []
        for sparse_obj in embeddings:
            result.append({
                "indices": sparse_obj.indices.tolist(),
                "values": sparse_obj.values.tolist(),
            })
            
        return result
