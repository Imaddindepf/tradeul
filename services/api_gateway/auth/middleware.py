"""
Middleware de autenticación PASIVO.

Este middleware:
- Lee el token Authorization si existe
- Verifica y extrae el usuario
- Lo pone en request.state.user
- NUNCA bloquea - si hay error, request.state.user = None

Esto permite que los endpoints funcionen con o sin autenticación
mientras hacemos la transición gradual.
"""
import logging
import time
from typing import Optional

from fastapi import Request
from starlette.middleware.base import BaseHTTPMiddleware

from .clerk_jwt import clerk_jwt_verifier, ClerkJWTError
from .models import AuthenticatedUser

logger = logging.getLogger("api_gateway.auth")


class PassiveAuthMiddleware(BaseHTTPMiddleware):
    """
    Middleware que intenta autenticar pero NUNCA bloquea.
    
    - Si hay token válido: request.state.user = AuthenticatedUser
    - Si no hay token o es inválido: request.state.user = None
    - NUNCA lanza excepciones
    """
    
    def __init__(self, app, enabled: bool = True):
        super().__init__(app)
        self.enabled = enabled
    
    async def dispatch(self, request: Request, call_next):
        # Inicializar user como None
        request.state.user = None
        
        if not self.enabled:
            return await call_next(request)
        
        # Extraer token del header Authorization
        auth_header = request.headers.get("Authorization", "")
        
        if auth_header.startswith("Bearer "):
            token = auth_header[7:]  # Quitar "Bearer "
            
            try:
                start = time.perf_counter()
                user = await clerk_jwt_verifier.verify_token(token)
                elapsed_ms = (time.perf_counter() - start) * 1000
                
                request.state.user = user
                
                # Log solo en debug para no saturar logs
                logger.debug(
                    f"auth_success user_id={user.id} "
                    f"email={user.email} elapsed_ms={elapsed_ms:.2f}"
                )
                
            except ClerkJWTError as e:
                # Token inválido - no bloqueamos, solo logueamos
                logger.debug(f"auth_failed reason={e}")
            except Exception as e:
                # Error inesperado - no bloqueamos
                logger.warning(f"auth_error unexpected={e}")
        
        # Continuar con la request (autenticado o no)
        response = await call_next(request)
        
        return response


def get_user_from_request(request: Request) -> Optional[AuthenticatedUser]:
    """
    Helper para obtener el usuario de una request.
    Retorna None si no está autenticado.
    """
    return getattr(request.state, "user", None)

