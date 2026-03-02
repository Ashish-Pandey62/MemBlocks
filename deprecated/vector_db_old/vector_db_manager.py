from uuid import uuid4

from qdrant_client import QdrantClient
from qdrant_client.models import Filter, PointStruct, PointIdsList

from vector_db.embeddings import OllamaEmbeddings


class VectorDBManager:
    """Manages connections and operations with the Qdrant vector database."""

    client = QdrantClient(host="localhost", port=6333, prefer_grpc=True)
    embedder = OllamaEmbeddings()
    vector_size = embedder.get_dimension()

    @staticmethod
    def get_client():
        return VectorDBManager.client

    @staticmethod
    def get_embedder():
        return VectorDBManager.embedder

    @staticmethod
    def get_vector_size():
        return VectorDBManager.vector_size

    @staticmethod
    def create_collection(collection_name: str) -> bool:
        """Create a new Qdrant collection.

        Args:
            collection_name (str): Name of the collection to create.

        Returns:
            bool: True if successful, False otherwise.
        """
        from qdrant_client.models import Distance, VectorParams

        client = VectorDBManager.get_client()
        try:
            # Check if collection already exists
            collections = client.get_collections().collections
            if any(col.name == collection_name for col in collections):
                print(f"Collection '{collection_name}' already exists.")
                return True

            # Create new collection
            client.create_collection(
                collection_name=collection_name,
                vectors_config=VectorParams(
                    size=VectorDBManager.get_vector_size(), distance=Distance.COSINE
                ),
            )
            return True
        except Exception as e:
            print(f"Error creating collection: {e}")
            return False

    @staticmethod
    def store_vector(
        collection_name: str, vector: list, payload: dict, point_id: str | None = None
    ) -> bool:
        """Store a vector in the specified collection.

        Args:
            collection_name (str): Name of the Qdrant collection.
            vector (list): The vector to store.
            payload (dict): Additional metadata to store with the vector.
            point_id (str, optional): Specific ID for the point. If None, Qdrant will auto-generate.
        Returns:
            bool: True if successful, False otherwise.
        """
        client = VectorDBManager.get_client()
        try:
            resolved_id = point_id or str(uuid4())
            client.upsert(
                collection_name=collection_name,
                points=[PointStruct(id=resolved_id, vector=vector, payload=payload)],
                wait=False,
            )
            return True
        except Exception as e:
            print(f"Error storing vector: {e}")
            return False

    @staticmethod
    def retrieve_from_vector(
        collection_name: str, query_vector: list, top_k: int = 5
    ) -> list:
        """Retrieve top_k similar vectors from the specified collection.

        Args:
            collection_name (str): Name of the Qdrant collection.
            query_vector (list): The vector to query against.
            top_k (int): Number of top similar vectors to retrieve.
        Returns:
            list: List of retrieved points with their metadata.
        """
        client = VectorDBManager.get_client()
        try:
            results = client.query_points(
                collection_name=collection_name, query=query_vector, limit=top_k
            )
            return results.points
        except Exception as e:
            print(f"Error retrieving vectors: {e}")
            return []

    @staticmethod
    def retrieve_from_payload(
        collection_name: str, payload_filter: Filter, top_k: int = 5
    ) -> list:
        """Retrieve vectors based on payload filtering.

        Args:
            collection_name (str): Name of the Qdrant collection.
            payload_filter (dict): The payload filter to apply.
            top_k (int): Number of top vectors to retrieve.
        Returns:
            list: List of retrieved points with their metadata.
        """
        client = VectorDBManager.get_client()
        try: 
            if hasattr(client, "scroll"):
                points, _ = client.scroll(
                    collection_name=collection_name,
                    scroll_filter=payload_filter,
                    limit=top_k,
                    with_vectors=False,
                )
                return points

            results = client.query_points(
                collection_name=collection_name,
                query_filter=payload_filter,
                limit=top_k,
                with_vectors=False,
            )
            return results.points
        except Exception as e:
            print(f"Error retrieving vectors by payload: {e}")
            return []

    @staticmethod
    def delete_vector(collection_name: str, point_id: str) -> bool:
        """Delete a vector by ID from collection.

        Args:
            collection_name: Name of the Qdrant collection
            point_id: ID of the point to delete

        Returns:
            bool: True if successful, False otherwise
        """
        from qdrant_client.models import PointIdsList

        client = VectorDBManager.get_client()
        try:
            client.delete(
                collection_name=collection_name,
                points_selector=PointIdsList(points=[point_id]),
            )
            print(f"✓ Deleted vector {point_id} from {collection_name}")
            return True
        except Exception as e:
            print(f"⚠️ Error deleting vector {point_id}: {e}")
            return False
