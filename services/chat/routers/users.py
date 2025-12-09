"""
User endpoints - Search users for invitations
"""

import os
from typing import List, Optional
from fastapi import APIRouter, HTTPException, Depends, Query
from pydantic import BaseModel
import httpx
import structlog

from auth.dependencies import get_current_user
from auth.models import AuthenticatedUser

logger = structlog.get_logger(__name__)
router = APIRouter(prefix="/users", tags=["users"])

CLERK_SECRET_KEY = os.getenv("CLERK_SECRET_KEY", "")


class UserSearchResult(BaseModel):
    id: str
    username: str
    avatar: Optional[str] = None


@router.get("/search", response_model=List[UserSearchResult])
async def search_users(
    q: str = Query(..., min_length=1, max_length=50),
    user: AuthenticatedUser = Depends(get_current_user)
):
    """
    Search for users by username using Clerk API.
    """
    if not CLERK_SECRET_KEY:
        logger.warning("clerk_secret_key_not_set")
        return []
    
    try:
        async with httpx.AsyncClient() as client:
            # Search users in Clerk
            response = await client.get(
                "https://api.clerk.com/v1/users",
                params={
                    "query": q,
                    "limit": 10,
                },
                headers={
                    "Authorization": f"Bearer {CLERK_SECRET_KEY}",
                    "Content-Type": "application/json",
                },
                timeout=5.0
            )
            
            if response.status_code != 200:
                logger.error("clerk_search_error", status=response.status_code, body=response.text[:200])
                return []
            
            data = response.json()
            
            results = []
            for u in data:
                # Skip current user
                if u.get("id") == user.user_id:
                    continue
                
                # Get username (priority: username > email prefix > id)
                username = u.get("username")
                if not username:
                    email = u.get("email_addresses", [{}])[0].get("email_address", "")
                    username = email.split("@")[0] if email else u.get("id", "")[:8]
                
                results.append(UserSearchResult(
                    id=u.get("id"),
                    username=username,
                    avatar=u.get("image_url")
                ))
            
            return results
            
    except httpx.TimeoutException:
        logger.warning("clerk_search_timeout")
        return []
    except Exception as e:
        logger.error("clerk_search_error", error=str(e))
        return []


@router.get("/me", response_model=UserSearchResult)
async def get_current_user_info(
    user: AuthenticatedUser = Depends(get_current_user)
):
    """
    Get current user's chat profile.
    """
    return UserSearchResult(
        id=user.user_id,
        username=user.name or user.username or "User",
        avatar=user.avatar
    )
