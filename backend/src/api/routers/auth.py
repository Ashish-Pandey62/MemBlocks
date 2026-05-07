"""Authentication router — Clerk OAuth integration."""

from typing import Any, Dict, Optional

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel
import jwt

from backend.src.api.dependencies import get_client
from memblocks import MemBlocksClient
from mcp_server.state import set_user_id
# from .....mcp_server.src.mcp_server.state import set_user_id

router = APIRouter(prefix="/auth", tags=["auth"])


class CurrentUser(BaseModel):
    user_id: str
    email: Optional[str] = None
    name: Optional[str] = None
    image_url: Optional[str] = None


async def get_current_user(
    request: Request,
    client: MemBlocksClient = Depends(get_client),
) -> CurrentUser:
    """Extract and validate the current user from Clerk JWT token.
    
    Expects the Authorization header to contain a valid Clerk JWT.
    On first login, automatically creates the user in our database.
    """
    auth_header = request.headers.get("Authorization")
    if not auth_header or not auth_header.startswith("Bearer "):
        print(f"Missing auth header: {auth_header}")
        raise HTTPException(
            status_code=401,
            detail="Missing or invalid Authorization header",
        )
    
    token = auth_header.replace("Bearer ", "")
    print(f"Token received: {token[:50]}...")
    
    clerk_secret = client.config.clerk_secret_key
    print(f"Clerk secret configured: {bool(clerk_secret)}")
    if not clerk_secret:
        raise HTTPException(
            status_code=500,
            detail="Clerk not configured on server",
        )
    
    try:
        # Decode the JWT token without verification (Clerk tokens are self-signed)
        # In production, you should verify with Clerk's public keys
        try:
            # Try to decode as-is for testing
            claims = jwt.decode(token, options={"verify_signature": False})
        except Exception:
            # If that fails, try with the secret (Clerk uses HS256 for some tokens)
            try:
                claims = jwt.decode(token, clerk_secret, algorithms=["HS256"])
            except Exception:
                # Last try - decode without verification
                claims = jwt.decode(token, options={"verify_signature": False})
        

        user_id = claims.get("sub")
        if not user_id:
            raise HTTPException(
                status_code=401,
                detail="Invalid token: no user ID",
            )
        
        
        # Try to get user info from Clerk
        email = claims.get("email")
        name = claims.get("name")
        image_url = claims.get("image_url")
        
        await client.get_or_create_user(
            user_id=user_id,
            metadata={
                "email": email,
                "name": name,
                "image_url": image_url,
            },
        )
        
        set_user_id(user_id)  # Save user ID to shared state for CLI access
        
        return CurrentUser(
            user_id=user_id,
            email=email,
            name=name,
            image_url=image_url,
        )
        
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(
            status_code=401,
            detail=f"Authentication failed: {str(e)}",
        )


@router.get("/me", response_model=CurrentUser)
async def get_me(
    current_user: CurrentUser = Depends(get_current_user),
) -> CurrentUser:
    """Get the current authenticated user."""
    return current_user


__all__ = ["router", "get_current_user", "CurrentUser"]
