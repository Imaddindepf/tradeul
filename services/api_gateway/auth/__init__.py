# Auth module for Clerk JWT verification
from .models import AuthenticatedUser, ClerkClaims
from .clerk_jwt import ClerkJWTVerifier, clerk_jwt_verifier
from .dependencies import (
    get_current_user_optional,
    get_current_user,
    require_admin,
)
from .middleware import PassiveAuthMiddleware, get_user_from_request

__all__ = [
    "AuthenticatedUser",
    "ClerkClaims",
    "ClerkJWTVerifier",
    "clerk_jwt_verifier",
    "get_current_user_optional",
    "get_current_user",
    "require_admin",
    "PassiveAuthMiddleware",
    "get_user_from_request",
]

