"""UserManager — extracted from services/user_service.py UserService."""

from typing import Any, Dict, List, Optional, TYPE_CHECKING

if TYPE_CHECKING:
    from memblocks.storage.mongo import MongoDBAdapter


class UserManager:
    """
    Manages user creation and retrieval.

    Replaces: UserService (user_service.py:7-65).

    Changes from UserService:
    - Dependency-injected MongoDBAdapter (no global mongo_manager singleton).
    - No static methods — regular instance methods.
    """

    def __init__(self, mongo_adapter: "MongoDBAdapter") -> None:
        """
        Args:
            mongo_adapter: MongoDB persistence layer.
        """
        self._mongo = mongo_adapter

    async def create_user(
        self,
        user_id: str,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        """
        Create a new user, or return the existing one if already present.

        Mirrors UserService.create_user() (user_service.py:11-30).

        Args:
            user_id: Unique user identifier.
            metadata: Optional extra fields to attach to the user document.

        Returns:
            User document dict.
        """
        existing = await self._mongo.get_user(user_id)
        if existing:
            print(f"[WARN] User {user_id} already exists")
            return existing

        user_doc = await self._mongo.create_user(user_id, metadata)
        print(f"[OK] Created user: {user_id}")
        return user_doc

    async def get_user(self, user_id: str) -> Optional[Dict[str, Any]]:
        """
        Retrieve a user by ID.

        Mirrors UserService.get_user() (user_service.py:32-43).

        Args:
            user_id: User identifier.

        Returns:
            User document or None.
        """
        return await self._mongo.get_user(user_id)

    async def list_users(self) -> List[Dict[str, Any]]:
        """
        Return all users.

        Mirrors UserService.list_users() (user_service.py:45-47).
        """
        return await self._mongo.list_users()

    async def get_or_create_user(
        self,
        user_id: str,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        """
        Return an existing user or create a new one.

        Mirrors UserService.get_or_create_user() (user_service.py:49-65).

        Args:
            user_id: User identifier.
            metadata: Optional metadata (used only on creation).

        Returns:
            User document dict.
        """
        user = await self._mongo.get_user(user_id)
        if not user:
            user = await self._mongo.create_user(user_id, metadata)
            print(f"[OK] Created new user: {user_id}")
        return user
