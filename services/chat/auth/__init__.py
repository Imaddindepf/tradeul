# Re-export from api_gateway auth module for consistency
# In production, this would import from shared module

from .clerk_jwt import ClerkJWTVerifier, clerk_jwt_verifier, ClerkJWTError
from .models import AuthenticatedUser, ClerkClaims
from .middleware import PassiveAuthMiddleware
from .dependencies import get_current_user, get_current_user_optional, require_admin

__all__ = [
    'ClerkJWTVerifier',
    'clerk_jwt_verifier', 
    'ClerkJWTError',
    'AuthenticatedUser',
    'ClerkClaims',
    'PassiveAuthMiddleware',
    'get_current_user',
    'get_current_user_optional',
    'require_admin',
]

