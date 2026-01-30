"""
User Scanner Filters Router
Endpoints para gestionar filtros personalizados del scanner por usuario

ARQUITECTURA MULTI-USUARIO:
- Cada usuario puede crear/modificar/eliminar sus propios scans
- Los scans se almacenan en PostgreSQL y se procesan por RETE engine
- La ownership se guarda en Redis para validacion rapida en WebSocket
- Se notifica al Scanner y WebSocket Server en cambios
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
    description: Optional[str] = Field(None, description="Descripcion del filtro")
    enabled: bool = Field(True, description="Si el filtro esta habilitado")
    filter_type: str = Field(..., description="Tipo de filtro (rvol, price, volume, custom)")
    parameters: FilterParameters = Field(..., description="Parametros del filtro")
    priority: int = Field(0, description="Prioridad (mayor = se aplica primero)")


class UserFilterUpdate(BaseModel):
    """Modelo para actualizar un filtro existente"""
    name: Optional[str] = Field(None, max_length=100, description="Nombre del filtro")
    description: Optional[str] = Field(None, description="Descripcion del filtro")
    enabled: Optional[bool] = Field(None, description="Si el filtro esta habilitado")
    filter_type: Optional[str] = Field(None, description="Tipo de filtro")
    parameters: Optional[FilterParameters] = Field(None, description="Parametros del filtro")
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

_timescale_client = None
_redis_client = None


def set_timescale_client(client):
    """Inyectar el cliente de TimescaleDB"""
    global _timescale_client
    _timescale_client = client


def set_redis_client(client):
    """Inyectar el cliente de Redis"""
    global _redis_client
    _redis_client = client


def get_timescale():
    """Dependency para obtener el cliente de TimescaleDB"""
    if _timescale_client is None:
        raise HTTPException(status_code=503, detail="Database not available")
    return _timescale_client


# ============================================================================
# Notification Functions
# ============================================================================

async def notify_scanner_rules_changed():
    """Notifica al scanner que las reglas han cambiado via Redis Pub/Sub"""
    if _redis_client is None:
        logger.warning("redis_not_available_for_notification")
        return
    try:
        await _redis_client.publish("scanner:rules:changed", "reload")
        logger.info("scanner_rules_change_notified")
    except Exception as e:
        logger.error("notify_scanner_error", error=str(e))


async def notify_websocket_scan_change(action: str, scan_id: int, user_id: str, name: str = ""):
    """
    Notifica al WebSocket Server sobre cambios en user scans.
    
    Actions: created, updated, deleted
    """
    if _redis_client is None:
        logger.warning("redis_not_available_for_ws_notification")
        return
    try:
        message = json.dumps({
            "action": action,
            "scan_id": scan_id,
            "user_id": user_id,
            "name": name,
            "category": f"uscan_{scan_id}",
            "timestamp": datetime.utcnow().isoformat()
        })
        await _redis_client.publish("ws:user_scans:changed", message)
        logger.info("websocket_scan_change_notified", action=action, scan_id=scan_id)
    except Exception as e:
        logger.error("notify_websocket_error", action=action, scan_id=scan_id, error=str(e))


async def save_scan_owner_to_redis(scan_id: int, user_id: str):
    """
    Guarda la ownership del scan en Redis para validacion rapida en WebSocket.
    TTL de 7 dias (se renueva en cada update).
    """
    if _redis_client is None:
        return
    try:
        key = f"user_scan:owner:{scan_id}"
        await _redis_client.set(key, user_id, ttl=604800)  # 7 dias
        logger.debug("scan_owner_saved", scan_id=scan_id, user_id=user_id)
    except Exception as e:
        logger.error("save_scan_owner_error", scan_id=scan_id, error=str(e))


async def delete_scan_from_redis(scan_id: int):
    """
    Elimina todos los datos del scan de Redis:
    - Ownership
    - Category snapshot
    - Sequence number
    """
    if _redis_client is None:
        return
    try:
        category_name = f"uscan_{scan_id}"
        keys_to_delete = [
            f"user_scan:owner:{scan_id}",
            f"scanner:category:{category_name}",
            f"scanner:sequence:{category_name}"
        ]
        for key in keys_to_delete:
            await _redis_client.delete(key)
        logger.info("scan_redis_data_deleted", scan_id=scan_id, keys=keys_to_delete)
    except Exception as e:
        logger.error("delete_scan_redis_error", scan_id=scan_id, error=str(e))


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
    Retorna lista vacia si no tiene filtros.
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
    Obtiene un filtro especifico del usuario.
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
    
    1. Inserta en PostgreSQL
    2. Guarda ownership en Redis
    3. Notifica al Scanner (reload rules)
    4. Notifica al WebSocket Server (nuevo scan disponible)
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
        
        scan_id = result['id']
        logger.info("user_filter_created", user_id=user_id, filter_id=scan_id, name=filter_data.name)
        
        # 1. Guardar ownership en Redis
        await save_scan_owner_to_redis(scan_id, user_id)
        
        # 2. Notificar al scanner para que recargue las reglas
        await notify_scanner_rules_changed()
        
        # 3. Notificar al WebSocket Server
        await notify_websocket_scan_change("created", scan_id, user_id, filter_data.name)
        
        return UserFilterResponse(
            id=scan_id,
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
    
    1. Actualiza en PostgreSQL
    2. Renueva ownership TTL en Redis
    3. Notifica al Scanner (reload rules)
    4. Notifica al WebSocket Server (scan modificado)
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
        
        # Construir query de actualizacion dinamica
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
        
        updates.append("updated_at = NOW()")
        
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
        
        # 1. Renovar ownership TTL en Redis
        await save_scan_owner_to_redis(filter_id, user_id)
        
        # 2. Notificar al scanner para que recargue las reglas
        await notify_scanner_rules_changed()
        
        # 3. Notificar al WebSocket Server
        await notify_websocket_scan_change("updated", filter_id, user_id, row['name'])
        
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
    
    1. Elimina de PostgreSQL
    2. Borra datos de Redis (ownership, category, sequence)
    3. Notifica al Scanner (reload rules)
    4. Notifica al WebSocket Server (desuscribir clientes)
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
        
        # 1. Borrar todos los datos de Redis
        await delete_scan_from_redis(filter_id)
        
        # 2. Notificar al scanner para que recargue las reglas
        await notify_scanner_rules_changed()
        
        # 3. Notificar al WebSocket Server para desuscribir clientes
        await notify_websocket_scan_change("deleted", filter_id, user_id)
        
        return None
    
    except HTTPException:
        raise
    except Exception as e:
        logger.error("delete_user_filter_error", user_id=user_id, filter_id=filter_id, error=str(e))
        raise HTTPException(status_code=500, detail=str(e))
