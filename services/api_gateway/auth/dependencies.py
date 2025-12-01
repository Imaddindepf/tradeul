"""
FastAPI dependencies para autenticación con Clerk.

Uso en endpoints:

    from auth import get_current_user, require_admin, AuthenticatedUser

    @app.get("/api/v1/protected")
    async def protected_endpoint(
        user: AuthenticatedUser = Depends(get_current_user)
    ):
        return {"user_id": user.id}
    
    @app.get("/api/v1/admin-only")
    async def admin_endpoint(
        user: AuthenticatedUser = Depends(require_admin)
    ):
        return {"admin": user.id}
"""
import logging
from typing import Optional

from fastapi import Depends, HTTPException, Request, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

from .clerk_jwt import (
    ClerkJWTExpiredError,
    ClerkJWTInvalidError,
    clerk_jwt_verifier,
)
from .models import AuthenticatedUser

logger = logging.getLogger("api_gateway.auth")

# Security scheme para OpenAPI docs
bearer_scheme = HTTPBearer(auto_error=False)


async def get_current_user_optional(
    request: Request,
    credentials: Optional[HTTPAuthorizationCredentials] = Depends(bearer_scheme),
) -> Optional[AuthenticatedUser]:
    """
    Obtener el usuario actual si hay un token válido.
    
    NO lanza excepción si no hay token o es inválido.
    Retorna None en esos casos.
    
    Uso para endpoints que funcionan con o sin autenticación:
    
        @app.get("/api/v1/data")
        async def get_data(user: Optional[AuthenticatedUser] = Depends(get_current_user_optional)):
            if user:
                # Usuario autenticado - mostrar datos personalizados
                pass
            else:
                # Usuario anónimo - mostrar datos públicos
                pass
    """
    # Si ya hay un usuario en request.state (puesto por middleware), usarlo
    if hasattr(request.state, "user") and request.state.user:
        return request.state.user
    
    if not credentials:
        return None
    
    try:
        user = await clerk_jwt_verifier.verify_token(credentials.credentials)
        # Guardar en request.state para uso posterior
        request.state.user = user
        return user
    except (ClerkJWTExpiredError, ClerkJWTInvalidError) as e:
        logger.debug(f"auth_token_invalid reason={e}")
        return None
    except Exception as e:
        logger.warning(f"auth_unexpected_error error={e}")
        return None


async def get_current_user(
    request: Request,
    credentials: Optional[HTTPAuthorizationCredentials] = Depends(bearer_scheme),
) -> AuthenticatedUser:
    """
    Obtener el usuario actual REQUERIDO.
    
    Lanza 401 Unauthorized si no hay token o es inválido.
    
    Uso para endpoints que REQUIEREN autenticación:
    
        @app.get("/api/v1/protected")
        async def protected(user: AuthenticatedUser = Depends(get_current_user)):
            return {"user_id": user.id}
    """
    # Si ya hay un usuario en request.state (puesto por middleware), usarlo
    if hasattr(request.state, "user") and request.state.user:
        return request.state.user
    
    if not credentials:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Authentication required",
            headers={"WWW-Authenticate": "Bearer"},
        )
    
    try:
        user = await clerk_jwt_verifier.verify_token(credentials.credentials)
        # Guardar en request.state para uso posterior
        request.state.user = user
        return user
    except ClerkJWTExpiredError:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Token has expired",
            headers={"WWW-Authenticate": "Bearer"},
        )
    except ClerkJWTInvalidError as e:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail=f"Invalid token: {e}",
            headers={"WWW-Authenticate": "Bearer"},
        )
    except Exception as e:
        logger.error(f"auth_error error={e}")
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Authentication failed",
            headers={"WWW-Authenticate": "Bearer"},
        )


async def require_admin(
    user: AuthenticatedUser = Depends(get_current_user),
) -> AuthenticatedUser:
    """
    Requerir que el usuario sea administrador.
    
    Lanza 403 Forbidden si el usuario no es admin.
    
    Uso para endpoints de administración:
    
        @app.post("/api/v1/admin/reset")
        async def admin_reset(user: AuthenticatedUser = Depends(require_admin)):
            # Solo admins pueden ejecutar esto
            pass
    """
    if not user.is_admin:
        logger.warning(f"admin_access_denied user_id={user.id}")
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Admin access required",
        )
    return user


async def require_premium(
    user: AuthenticatedUser = Depends(get_current_user),
) -> AuthenticatedUser:
    """
    Requerir que el usuario tenga plan premium.
    
    Lanza 403 Forbidden si el usuario no es premium.
    """
    if not user.is_premium:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Premium subscription required",
        )
    return user

