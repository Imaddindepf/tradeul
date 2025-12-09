"""
Modelos para autenticación con Clerk.
"""
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional


@dataclass
class ClerkClaims:
    """
    Claims extraídos del JWT de Clerk.
    
    Estructura típica de un JWT de Clerk:
    {
        "azp": "https://tu-app.com",
        "exp": 1234567890,
        "iat": 1234567830,
        "iss": "https://clerk.tu-app.com",
        "nbf": 1234567825,
        "sid": "sess_abc123",
        "sub": "user_abc123",
        "email": "user@example.com",
        "email_verified": true,
        "first_name": "John",
        "last_name": "Doe",
        "image_url": "https://...",
        "public_metadata": {},
        "private_metadata": {},
        "unsafe_metadata": {}
    }
    """
    sub: str  # User ID (ej: "user_2abc123...")
    sid: str  # Session ID
    iss: str  # Issuer
    exp: int  # Expiration timestamp
    iat: int  # Issued at timestamp
    nbf: int  # Not before timestamp
    azp: Optional[str] = None  # Authorized party
    email: Optional[str] = None
    email_verified: bool = False
    first_name: Optional[str] = None
    last_name: Optional[str] = None
    image_url: Optional[str] = None
    public_metadata: Dict[str, Any] = field(default_factory=dict)
    
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "ClerkClaims":
        """Crear ClerkClaims desde un diccionario de claims JWT."""
        return cls(
            sub=data.get("sub", ""),
            sid=data.get("sid", ""),
            iss=data.get("iss", ""),
            exp=data.get("exp", 0),
            iat=data.get("iat", 0),
            nbf=data.get("nbf", 0),
            azp=data.get("azp"),
            email=data.get("email"),
            email_verified=data.get("email_verified", False),
            first_name=data.get("first_name"),
            last_name=data.get("last_name"),
            image_url=data.get("image_url"),
            public_metadata=data.get("public_metadata", {}),
        )


@dataclass
class AuthenticatedUser:
    """
    Usuario autenticado extraído del JWT de Clerk.
    
    Esta es la representación simplificada que usaremos en los endpoints.
    """
    id: str  # User ID de Clerk (ej: "user_2abc123...")
    session_id: str  # Session ID
    email: Optional[str] = None
    first_name: Optional[str] = None
    last_name: Optional[str] = None
    image_url: Optional[str] = None
    roles: List[str] = field(default_factory=list)
    metadata: Dict[str, Any] = field(default_factory=dict)
    
    @property
    def user_id(self) -> str:
        """Alias para id (compatibilidad con routers)."""
        return self.id
    
    @property
    def name(self) -> str:
        """Nombre del usuario."""
        # 1. Priorizar username de metadata (si está configurado en Clerk)
        username_from_meta = self.metadata.get("username")
        if username_from_meta:
            return username_from_meta
        # 2. Usar email (sin dominio)
        if self.email:
            return self.email.split("@")[0]
        # 3. Usar first_name
        if self.first_name:
            if self.last_name:
                return f"{self.first_name} {self.last_name}"
            return self.first_name
        # 4. Fallback a ID legible
        if self.id:
            short_id = self.id.replace("user_", "").replace("-", "")[:8]
            return f"user_{short_id}"
        return "anon"
    
    @property
    def username(self) -> Optional[str]:
        """Username."""
        # Priorizar username de metadata
        username_from_meta = self.metadata.get("username")
        if username_from_meta:
            return username_from_meta
        if self.email:
            return self.email.split("@")[0]
        return None
    
    @property
    def avatar(self) -> Optional[str]:
        """URL del avatar."""
        return self.image_url
    
    @property
    def is_admin(self) -> bool:
        """Verificar si el usuario tiene rol de admin."""
        return "admin" in self.roles or self.metadata.get("role") == "admin"
    
    @property
    def is_premium(self) -> bool:
        """Verificar si el usuario tiene plan premium."""
        return "premium" in self.roles or self.metadata.get("plan") == "premium"
    
    @property
    def display_name(self) -> str:
        """Nombre para mostrar del usuario."""
        return self.name
    
    @classmethod
    def from_claims(cls, claims: ClerkClaims) -> "AuthenticatedUser":
        """Crear AuthenticatedUser desde ClerkClaims."""
        # Extraer roles desde public_metadata
        roles = claims.public_metadata.get("roles", [])
        if isinstance(roles, str):
            roles = [roles]
        
        return cls(
            id=claims.sub,
            session_id=claims.sid,
            email=claims.email,
            first_name=claims.first_name,
            last_name=claims.last_name,
            image_url=claims.image_url,
            roles=roles,
            metadata=claims.public_metadata,
        )

