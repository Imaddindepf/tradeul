"""
User Scanner Filters Router
Endpoints para gestionar filtros personalizados del scanner por usuario
"""

import json
from datetime import datetime
from typing import Optional, List
from pydantic import BaseModel, Field

from fastapi import APIRouter, HTTPException, Depends
import structlog
from auth import get_current_user, AuthenticatedUser

# Reutilizar modelos existentes
from shared.models.scanner import FilterParameters

logger = structlog.get_logger(__name__)

router = APIRouter(prefix="/api/v1/user/filters", tags=["user-filters"])


# ============================================================================
# Pydantic Models (Request/Response)
# ============================================================================

class UserFilterCreate(BaseModel):
    """Modelo para crear un nuevo filtro"""
    name: str = Field(..., max_length=100, description="Nombre del filtro")
    description: Optional[str] = Field(None, description="Descripción del filtro")
    enabled: bool = Field(True, description="Si el filtro está habilitado")
    filter_type: str = Field(..., description="Tipo de filtro (rvol, price, volume, custom)")
    parameters: FilterParameters = Field(..., description="Parámetros del filtro")
    priority: int = Field(0, description="Prioridad (mayor = se aplica primero)")


class UserFilterUpdate(BaseModel):
    """Modelo para actualizar un filtro existente"""
    name: Optional[str] = Field(None, max_length=100, description="Nombre del filtro")
    description: Optional[str] = Field(None, description="Descripción del filtro")
    enabled: Optional[bool] = Field(None, description="Si el filtro está habilitado")
    filter_type: Optional[str] = Field(None, description="Tipo de filtro")
    parameters: Optional[FilterParameters] = Field(None, description="Parámetros del filtro")
    priority: Optional[int] = Field(None, description="Prioridad")


class UserFilterResponse(BaseModel):
    """Modelo de respuesta para un filtro"""
    id: int
    userId: str
    name: str
    description: Optional[str]
    enabled: bool
    filter_type: str
    parameters: FilterParameters
    priority: int
    isShared: bool
    isPublic: bool
    createdAt: str
    updatedAt: str


# ============================================================================
# Dependencies
# ============================================================================

# Referencia al cliente de TimescaleDB (se inyecta desde main.py)
_timescale_client = None


def set_timescale_client(client):
    """Inyectar el cliente de TimescaleDB"""
    global _timescale_client
    _timescale_client = client


def get_timescale():
    """Dependency para obtener el cliente de TimescaleDB"""
    if _timescale_client is None:
        raise HTTPException(status_code=503, detail="Database not available")
    return _timescale_client


# ============================================================================
# Helper Functions
# ============================================================================

def parse_jsonb(val):
    """Parsear JSONB - asyncpg puede devolver str o dict"""
    if isinstance(val, str):
        return json.loads(val)
    return val


# ============================================================================
# Endpoints
# ============================================================================

@router.get("", response_model=List[UserFilterResponse])
async def get_user_filters(
    user: AuthenticatedUser = Depends(get_current_user),
    db=Depends(get_timescale)
):
    """
    Obtiene todos los filtros del usuario.
    Retorna lista vacía si no tiene filtros.
    """
    try:
        user_id = user.id
        query = """
            SELECT 
                id,
                user_id,
                name,
                description,
                enabled,
                filter_type,
                parameters,
                priority,
                is_shared,
                is_public,
                created_at,
                updated_at
            FROM user_scanner_filters
            WHERE user_id = $1
            ORDER BY priority DESC, created_at DESC
        """
        
        rows = await db.fetch(query, user_id)
        
        filters = []
        for row in rows:
            params = parse_jsonb(row['parameters'])
            filters.append(UserFilterResponse(
                id=row['id'],
                userId=row['user_id'],
                name=row['name'],
                description=row['description'],
                enabled=row['enabled'],
                filter_type=row['filter_type'],
                parameters=FilterParameters(**params),
                priority=row['priority'],
                isShared=row['is_shared'],
                isPublic=row['is_public'],
                createdAt=row['created_at'].isoformat(),
                updatedAt=row['updated_at'].isoformat()
            ))
        
        logger.info("user_filters_retrieved", user_id=user_id, count=len(filters))
        return filters
    
    except Exception as e:
        logger.error("get_user_filters_error", user_id=user_id, error=str(e))
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/{filter_id}", response_model=UserFilterResponse)
async def get_user_filter(
    filter_id: int,
    user: AuthenticatedUser = Depends(get_current_user),
    db=Depends(get_timescale)
):
    """
    Obtiene un filtro específico del usuario.
    """
    try:
        user_id = user.id
        query = """
            SELECT 
                id,
                user_id,
                name,
                description,
                enabled,
                filter_type,
                parameters,
                priority,
                is_shared,
                is_public,
                created_at,
                updated_at
            FROM user_scanner_filters
            WHERE id = $1 AND user_id = $2
        """
        
        row = await db.fetchrow(query, filter_id, user_id)
        
        if not row:
            raise HTTPException(status_code=404, detail="Filter not found")
        
        params = parse_jsonb(row['parameters'])
        return UserFilterResponse(
            id=row['id'],
            userId=row['user_id'],
            name=row['name'],
            description=row['description'],
            enabled=row['enabled'],
            filter_type=row['filter_type'],
            parameters=FilterParameters(**params),
            priority=row['priority'],
            isShared=row['is_shared'],
            isPublic=row['is_public'],
            createdAt=row['created_at'].isoformat(),
            updatedAt=row['updated_at'].isoformat()
        )
    
    except HTTPException:
        raise
    except Exception as e:
        logger.error("get_user_filter_error", user_id=user_id, filter_id=filter_id, error=str(e))
        raise HTTPException(status_code=500, detail=str(e))


@router.post("", response_model=UserFilterResponse, status_code=201)
async def create_user_filter(
    filter_data: UserFilterCreate,
    user: AuthenticatedUser = Depends(get_current_user),
    db=Depends(get_timescale)
):
    """
    Crea un nuevo filtro para el usuario.
    """
    try:
        user_id = user.id
        
        # Verificar que no exista un filtro con el mismo nombre
        check_query = """
            SELECT id FROM user_scanner_filters
            WHERE user_id = $1 AND name = $2
        """
        existing = await db.fetchrow(check_query, user_id, filter_data.name)
        if existing:
            raise HTTPException(
                status_code=400,
                detail=f"Filter with name '{filter_data.name}' already exists"
            )
        
        # Insertar nuevo filtro
        insert_query = """
            INSERT INTO user_scanner_filters (
                user_id, name, description, enabled, filter_type,
                parameters, priority, is_shared, is_public
            )
            VALUES ($1, $2, $3, $4, $5, $6::jsonb, $7, $8, $9)
            RETURNING id, created_at, updated_at
        """
        
        result = await db.fetchrow(
            insert_query,
            user_id,
            filter_data.name,
            filter_data.description,
            filter_data.enabled,
            filter_data.filter_type,
            json.dumps(filter_data.parameters.model_dump()),
            filter_data.priority,
            False,  # is_shared
            False   # is_public
        )
        
        logger.info("user_filter_created", user_id=user_id, filter_id=result['id'], name=filter_data.name)
        
        return UserFilterResponse(
            id=result['id'],
            userId=user_id,
            name=filter_data.name,
            description=filter_data.description,
            enabled=filter_data.enabled,
            filter_type=filter_data.filter_type,
            parameters=filter_data.parameters,
            priority=filter_data.priority,
            isShared=False,
            isPublic=False,
            createdAt=result['created_at'].isoformat(),
            updatedAt=result['updated_at'].isoformat()
        )
    
    except HTTPException:
        raise
    except Exception as e:
        logger.error("create_user_filter_error", user_id=user_id, error=str(e))
        raise HTTPException(status_code=500, detail=str(e))


@router.put("/{filter_id}", response_model=UserFilterResponse)
async def update_user_filter(
    filter_id: int,
    filter_data: UserFilterUpdate,
    user: AuthenticatedUser = Depends(get_current_user),
    db=Depends(get_timescale)
):
    """
    Actualiza un filtro existente del usuario.
    Solo actualiza los campos proporcionados.
    """
    try:
        user_id = user.id
        
        # Verificar que el filtro existe y pertenece al usuario
        check_query = """
            SELECT id FROM user_scanner_filters
            WHERE id = $1 AND user_id = $2
        """
        existing = await db.fetchrow(check_query, filter_id, user_id)
        if not existing:
            raise HTTPException(status_code=404, detail="Filter not found")
        
        # Si se actualiza el nombre, verificar que no exista otro con el mismo nombre
        if filter_data.name:
            name_check_query = """
                SELECT id FROM user_scanner_filters
                WHERE user_id = $1 AND name = $2 AND id != $3
            """
            name_exists = await db.fetchrow(name_check_query, user_id, filter_data.name, filter_id)
            if name_exists:
                raise HTTPException(
                    status_code=400,
                    detail=f"Filter with name '{filter_data.name}' already exists"
                )
        
        # Construir query de actualización dinámica
        updates = []
        values = []
        param_idx = 1
        
        if filter_data.name is not None:
            updates.append(f"name = ${param_idx}")
            values.append(filter_data.name)
            param_idx += 1
        
        if filter_data.description is not None:
            updates.append(f"description = ${param_idx}")
            values.append(filter_data.description)
            param_idx += 1
        
        if filter_data.enabled is not None:
            updates.append(f"enabled = ${param_idx}")
            values.append(filter_data.enabled)
            param_idx += 1
        
        if filter_data.filter_type is not None:
            updates.append(f"filter_type = ${param_idx}")
            values.append(filter_data.filter_type)
            param_idx += 1
        
        if filter_data.parameters is not None:
            updates.append(f"parameters = ${param_idx}::jsonb")
            values.append(json.dumps(filter_data.parameters.model_dump()))
            param_idx += 1
        
        if filter_data.priority is not None:
            updates.append(f"priority = ${param_idx}")
            values.append(filter_data.priority)
            param_idx += 1
        
        if not updates:
            raise HTTPException(status_code=400, detail="No fields to update")
        
        # Agregar updated_at automático (trigger)
        updates.append("updated_at = NOW()")
        
        # Agregar WHERE clause
        values.append(filter_id)
        values.append(user_id)
        
        update_query = f"""
            UPDATE user_scanner_filters
            SET {', '.join(updates)}
            WHERE id = ${param_idx} AND user_id = ${param_idx + 1}
            RETURNING 
                id, user_id, name, description, enabled, filter_type,
                parameters, priority, is_shared, is_public, created_at, updated_at
        """
        
        row = await db.fetchrow(update_query, *values)
        
        params = parse_jsonb(row['parameters'])
        logger.info("user_filter_updated", user_id=user_id, filter_id=filter_id)
        
        return UserFilterResponse(
            id=row['id'],
            userId=row['user_id'],
            name=row['name'],
            description=row['description'],
            enabled=row['enabled'],
            filter_type=row['filter_type'],
            parameters=FilterParameters(**params),
            priority=row['priority'],
            isShared=row['is_shared'],
            isPublic=row['is_public'],
            createdAt=row['created_at'].isoformat(),
            updatedAt=row['updated_at'].isoformat()
        )
    
    except HTTPException:
        raise
    except Exception as e:
        logger.error("update_user_filter_error", user_id=user_id, filter_id=filter_id, error=str(e))
        raise HTTPException(status_code=500, detail=str(e))


@router.delete("/{filter_id}", status_code=204)
async def delete_user_filter(
    filter_id: int,
    user: AuthenticatedUser = Depends(get_current_user),
    db=Depends(get_timescale)
):
    """
    Elimina un filtro del usuario.
    """
    try:
        user_id = user.id
        
        query = """
            DELETE FROM user_scanner_filters
            WHERE id = $1 AND user_id = $2
            RETURNING id
        """
        
        result = await db.fetchrow(query, filter_id, user_id)
        
        if not result:
            raise HTTPException(status_code=404, detail="Filter not found")
        
        logger.info("user_filter_deleted", user_id=user_id, filter_id=filter_id)
        return None
    
    except HTTPException:
        raise
    except Exception as e:
        logger.error("delete_user_filter_error", user_id=user_id, filter_id=filter_id, error=str(e))
        raise HTTPException(status_code=500, detail=str(e))

