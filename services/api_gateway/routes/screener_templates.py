"""
Screener Templates Router
Endpoints para gestionar plantillas del Screener por usuario
"""

import json
from datetime import datetime
from typing import Optional, List, Any, Dict
from pydantic import BaseModel, Field

from fastapi import APIRouter, HTTPException, Depends
import structlog
from auth import get_current_user, AuthenticatedUser

logger = structlog.get_logger(__name__)

router = APIRouter(prefix="/api/v1/screener/templates", tags=["screener-templates"])


# ============================================================================
# Pydantic Models
# ============================================================================

class IndicatorParams(BaseModel):
    """Parámetros de un indicador"""
    period: Optional[int] = None
    multiplier: Optional[float] = None
    std_dev: Optional[float] = None
    fast: Optional[int] = None
    slow: Optional[int] = None
    signal: Optional[int] = None


class FilterCondition(BaseModel):
    """Condición de filtro con parámetros dinámicos"""
    field: str = Field(..., description="Campo/indicador (sma, rsi, price, etc.)")
    params: Optional[IndicatorParams] = Field(None, description="Parámetros del indicador")
    operator: str = Field(..., description="Operador (gt, gte, lt, lte, eq, between)")
    value: Optional[Any] = Field(None, description="Valor a comparar")
    # Para comparaciones entre indicadores (ej: SMA(10) > SMA(50))
    compare_field: Optional[str] = Field(None, description="Campo para comparar")
    compare_params: Optional[IndicatorParams] = Field(None, description="Parámetros del campo a comparar")


class TemplateCreate(BaseModel):
    """Modelo para crear una plantilla"""
    name: str = Field(..., max_length=100, description="Nombre de la plantilla")
    description: Optional[str] = Field(None, description="Descripción")
    filters: List[FilterCondition] = Field(default_factory=list, description="Filtros")
    sort_by: str = Field("relative_volume", description="Campo para ordenar")
    sort_order: str = Field("desc", description="Orden (asc/desc)")
    limit_results: int = Field(50, ge=1, le=500, description="Límite de resultados")
    is_favorite: bool = Field(False, description="Marcar como favorita")
    color: Optional[str] = Field(None, max_length=20, description="Color de la plantilla")
    icon: Optional[str] = Field(None, max_length=50, description="Icono")


class TemplateUpdate(BaseModel):
    """Modelo para actualizar una plantilla"""
    name: Optional[str] = Field(None, max_length=100)
    description: Optional[str] = None
    filters: Optional[List[FilterCondition]] = None
    sort_by: Optional[str] = None
    sort_order: Optional[str] = None
    limit_results: Optional[int] = Field(None, ge=1, le=500)
    is_favorite: Optional[bool] = None
    color: Optional[str] = Field(None, max_length=20)
    icon: Optional[str] = Field(None, max_length=50)


class TemplateResponse(BaseModel):
    """Respuesta de una plantilla"""
    id: int
    userId: str
    name: str
    description: Optional[str]
    filters: List[Dict[str, Any]]
    sortBy: str
    sortOrder: str
    limitResults: int
    isFavorite: bool
    color: Optional[str]
    icon: Optional[str]
    useCount: int
    lastUsedAt: Optional[str]
    isShared: bool
    isPublic: bool
    createdAt: str
    updatedAt: str


class TemplateListResponse(BaseModel):
    """Respuesta de lista de plantillas"""
    templates: List[TemplateResponse]
    total: int


# ============================================================================
# Dependencies
# ============================================================================

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


def parse_jsonb(val):
    """Parsear JSONB"""
    if isinstance(val, str):
        return json.loads(val)
    return val


# ============================================================================
# Endpoints
# ============================================================================

@router.get("", response_model=TemplateListResponse)
async def list_templates(
    user: AuthenticatedUser = Depends(get_current_user),
    db=Depends(get_timescale)
):
    """
    Lista todas las plantillas del usuario.
    Ordenadas por: favoritas primero, luego por último uso.
    """
    try:
        user_id = user.id
        query = """
            SELECT 
                id, user_id, name, description, filters, sort_by, sort_order,
                limit_results, is_favorite, color, icon, use_count, last_used_at,
                is_shared, is_public, created_at, updated_at
            FROM user_screener_templates
            WHERE user_id = $1
            ORDER BY is_favorite DESC, last_used_at DESC NULLS LAST, created_at DESC
        """
        
        rows = await db.fetch(query, user_id)
        
        templates = []
        for row in rows:
            filters = parse_jsonb(row['filters'])
            templates.append(TemplateResponse(
                id=row['id'],
                userId=row['user_id'],
                name=row['name'],
                description=row['description'],
                filters=filters,
                sortBy=row['sort_by'],
                sortOrder=row['sort_order'],
                limitResults=row['limit_results'],
                isFavorite=row['is_favorite'],
                color=row['color'],
                icon=row['icon'],
                useCount=row['use_count'],
                lastUsedAt=row['last_used_at'].isoformat() if row['last_used_at'] else None,
                isShared=row['is_shared'],
                isPublic=row['is_public'],
                createdAt=row['created_at'].isoformat(),
                updatedAt=row['updated_at'].isoformat()
            ))
        
        logger.info("templates_listed", user_id=user_id, count=len(templates))
        return TemplateListResponse(templates=templates, total=len(templates))
    
    except Exception as e:
        logger.error("list_templates_error", user_id=user_id, error=str(e))
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/{template_id}", response_model=TemplateResponse)
async def get_template(
    template_id: int,
    user: AuthenticatedUser = Depends(get_current_user),
    db=Depends(get_timescale)
):
    """Obtiene una plantilla específica"""
    try:
        user_id = user.id
        query = """
            SELECT 
                id, user_id, name, description, filters, sort_by, sort_order,
                limit_results, is_favorite, color, icon, use_count, last_used_at,
                is_shared, is_public, created_at, updated_at
            FROM user_screener_templates
            WHERE id = $1 AND user_id = $2
        """
        
        row = await db.fetchrow(query, template_id, user_id)
        
        if not row:
            raise HTTPException(status_code=404, detail="Template not found")
        
        filters = parse_jsonb(row['filters'])
        return TemplateResponse(
            id=row['id'],
            userId=row['user_id'],
            name=row['name'],
            description=row['description'],
            filters=filters,
            sortBy=row['sort_by'],
            sortOrder=row['sort_order'],
            limitResults=row['limit_results'],
            isFavorite=row['is_favorite'],
            color=row['color'],
            icon=row['icon'],
            useCount=row['use_count'],
            lastUsedAt=row['last_used_at'].isoformat() if row['last_used_at'] else None,
            isShared=row['is_shared'],
            isPublic=row['is_public'],
            createdAt=row['created_at'].isoformat(),
            updatedAt=row['updated_at'].isoformat()
        )
    
    except HTTPException:
        raise
    except Exception as e:
        logger.error("get_template_error", template_id=template_id, error=str(e))
        raise HTTPException(status_code=500, detail=str(e))


@router.post("", response_model=TemplateResponse, status_code=201)
async def create_template(
    data: TemplateCreate,
    user: AuthenticatedUser = Depends(get_current_user),
    db=Depends(get_timescale)
):
    """Crea una nueva plantilla"""
    try:
        user_id = user.id
        
        # Verificar nombre único
        check = await db.fetchrow(
            "SELECT id FROM user_screener_templates WHERE user_id = $1 AND name = $2",
            user_id, data.name
        )
        if check:
            raise HTTPException(status_code=400, detail=f"Template '{data.name}' already exists")
        
        # Serializar filtros
        filters_json = json.dumps([f.model_dump() for f in data.filters])
        
        query = """
            INSERT INTO user_screener_templates (
                user_id, name, description, filters, sort_by, sort_order,
                limit_results, is_favorite, color, icon
            )
            VALUES ($1, $2, $3, $4::jsonb, $5, $6, $7, $8, $9, $10)
            RETURNING id, created_at, updated_at
        """
        
        result = await db.fetchrow(
            query,
            user_id, data.name, data.description, filters_json,
            data.sort_by, data.sort_order, data.limit_results,
            data.is_favorite, data.color, data.icon
        )
        
        logger.info("template_created", user_id=user_id, template_id=result['id'], name=data.name)
        
        return TemplateResponse(
            id=result['id'],
            userId=user_id,
            name=data.name,
            description=data.description,
            filters=[f.model_dump() for f in data.filters],
            sortBy=data.sort_by,
            sortOrder=data.sort_order,
            limitResults=data.limit_results,
            isFavorite=data.is_favorite,
            color=data.color,
            icon=data.icon,
            useCount=0,
            lastUsedAt=None,
            isShared=False,
            isPublic=False,
            createdAt=result['created_at'].isoformat(),
            updatedAt=result['updated_at'].isoformat()
        )
    
    except HTTPException:
        raise
    except Exception as e:
        logger.error("create_template_error", user_id=user_id, error=str(e))
        raise HTTPException(status_code=500, detail=str(e))


@router.put("/{template_id}", response_model=TemplateResponse)
async def update_template(
    template_id: int,
    data: TemplateUpdate,
    user: AuthenticatedUser = Depends(get_current_user),
    db=Depends(get_timescale)
):
    """Actualiza una plantilla existente"""
    try:
        user_id = user.id
        
        # Verificar existencia
        check = await db.fetchrow(
            "SELECT id FROM user_screener_templates WHERE id = $1 AND user_id = $2",
            template_id, user_id
        )
        if not check:
            raise HTTPException(status_code=404, detail="Template not found")
        
        # Verificar nombre único si se actualiza
        if data.name:
            name_check = await db.fetchrow(
                "SELECT id FROM user_screener_templates WHERE user_id = $1 AND name = $2 AND id != $3",
                user_id, data.name, template_id
            )
            if name_check:
                raise HTTPException(status_code=400, detail=f"Template '{data.name}' already exists")
        
        # Build dynamic update
        updates = []
        values = []
        idx = 1
        
        if data.name is not None:
            updates.append(f"name = ${idx}")
            values.append(data.name)
            idx += 1
        
        if data.description is not None:
            updates.append(f"description = ${idx}")
            values.append(data.description)
            idx += 1
        
        if data.filters is not None:
            updates.append(f"filters = ${idx}::jsonb")
            values.append(json.dumps([f.model_dump() for f in data.filters]))
            idx += 1
        
        if data.sort_by is not None:
            updates.append(f"sort_by = ${idx}")
            values.append(data.sort_by)
            idx += 1
        
        if data.sort_order is not None:
            updates.append(f"sort_order = ${idx}")
            values.append(data.sort_order)
            idx += 1
        
        if data.limit_results is not None:
            updates.append(f"limit_results = ${idx}")
            values.append(data.limit_results)
            idx += 1
        
        if data.is_favorite is not None:
            updates.append(f"is_favorite = ${idx}")
            values.append(data.is_favorite)
            idx += 1
        
        if data.color is not None:
            updates.append(f"color = ${idx}")
            values.append(data.color)
            idx += 1
        
        if data.icon is not None:
            updates.append(f"icon = ${idx}")
            values.append(data.icon)
            idx += 1
        
        if not updates:
            raise HTTPException(status_code=400, detail="No fields to update")
        
        values.extend([template_id, user_id])
        
        query = f"""
            UPDATE user_screener_templates
            SET {', '.join(updates)}
            WHERE id = ${idx} AND user_id = ${idx + 1}
            RETURNING *
        """
        
        row = await db.fetchrow(query, *values)
        
        filters = parse_jsonb(row['filters'])
        logger.info("template_updated", user_id=user_id, template_id=template_id)
        
        return TemplateResponse(
            id=row['id'],
            userId=row['user_id'],
            name=row['name'],
            description=row['description'],
            filters=filters,
            sortBy=row['sort_by'],
            sortOrder=row['sort_order'],
            limitResults=row['limit_results'],
            isFavorite=row['is_favorite'],
            color=row['color'],
            icon=row['icon'],
            useCount=row['use_count'],
            lastUsedAt=row['last_used_at'].isoformat() if row['last_used_at'] else None,
            isShared=row['is_shared'],
            isPublic=row['is_public'],
            createdAt=row['created_at'].isoformat(),
            updatedAt=row['updated_at'].isoformat()
        )
    
    except HTTPException:
        raise
    except Exception as e:
        logger.error("update_template_error", template_id=template_id, error=str(e))
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/{template_id}/use", response_model=TemplateResponse)
async def use_template(
    template_id: int,
    user: AuthenticatedUser = Depends(get_current_user),
    db=Depends(get_timescale)
):
    """
    Registra el uso de una plantilla.
    Incrementa use_count y actualiza last_used_at.
    """
    try:
        user_id = user.id
        
        query = """
            UPDATE user_screener_templates
            SET use_count = use_count + 1, last_used_at = NOW()
            WHERE id = $1 AND user_id = $2
            RETURNING *
        """
        
        row = await db.fetchrow(query, template_id, user_id)
        
        if not row:
            raise HTTPException(status_code=404, detail="Template not found")
        
        filters = parse_jsonb(row['filters'])
        logger.info("template_used", user_id=user_id, template_id=template_id, use_count=row['use_count'])
        
        return TemplateResponse(
            id=row['id'],
            userId=row['user_id'],
            name=row['name'],
            description=row['description'],
            filters=filters,
            sortBy=row['sort_by'],
            sortOrder=row['sort_order'],
            limitResults=row['limit_results'],
            isFavorite=row['is_favorite'],
            color=row['color'],
            icon=row['icon'],
            useCount=row['use_count'],
            lastUsedAt=row['last_used_at'].isoformat() if row['last_used_at'] else None,
            isShared=row['is_shared'],
            isPublic=row['is_public'],
            createdAt=row['created_at'].isoformat(),
            updatedAt=row['updated_at'].isoformat()
        )
    
    except HTTPException:
        raise
    except Exception as e:
        logger.error("use_template_error", template_id=template_id, error=str(e))
        raise HTTPException(status_code=500, detail=str(e))


@router.delete("/{template_id}", status_code=204)
async def delete_template(
    template_id: int,
    user: AuthenticatedUser = Depends(get_current_user),
    db=Depends(get_timescale)
):
    """Elimina una plantilla"""
    try:
        user_id = user.id
        
        result = await db.fetchrow(
            "DELETE FROM user_screener_templates WHERE id = $1 AND user_id = $2 RETURNING id",
            template_id, user_id
        )
        
        if not result:
            raise HTTPException(status_code=404, detail="Template not found")
        
        logger.info("template_deleted", user_id=user_id, template_id=template_id)
        return None
    
    except HTTPException:
        raise
    except Exception as e:
        logger.error("delete_template_error", template_id=template_id, error=str(e))
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/{template_id}/duplicate", response_model=TemplateResponse, status_code=201)
async def duplicate_template(
    template_id: int,
    user: AuthenticatedUser = Depends(get_current_user),
    db=Depends(get_timescale)
):
    """Duplica una plantilla existente"""
    try:
        user_id = user.id
        
        # Obtener plantilla original
        original = await db.fetchrow(
            "SELECT * FROM user_screener_templates WHERE id = $1 AND user_id = $2",
            template_id, user_id
        )
        
        if not original:
            raise HTTPException(status_code=404, detail="Template not found")
        
        # Generar nombre único
        base_name = f"{original['name']} (copy)"
        new_name = base_name
        counter = 1
        
        while True:
            exists = await db.fetchrow(
                "SELECT id FROM user_screener_templates WHERE user_id = $1 AND name = $2",
                user_id, new_name
            )
            if not exists:
                break
            counter += 1
            new_name = f"{base_name} {counter}"
        
        # Crear copia
        query = """
            INSERT INTO user_screener_templates (
                user_id, name, description, filters, sort_by, sort_order,
                limit_results, is_favorite, color, icon
            )
            VALUES ($1, $2, $3, $4::jsonb, $5, $6, $7, $8, $9, $10)
            RETURNING *
        """
        
        filters_json = json.dumps(parse_jsonb(original['filters']))
        
        row = await db.fetchrow(
            query,
            user_id, new_name, original['description'], filters_json,
            original['sort_by'], original['sort_order'], original['limit_results'],
            False, original['color'], original['icon']
        )
        
        filters = parse_jsonb(row['filters'])
        logger.info("template_duplicated", user_id=user_id, original_id=template_id, new_id=row['id'])
        
        return TemplateResponse(
            id=row['id'],
            userId=row['user_id'],
            name=row['name'],
            description=row['description'],
            filters=filters,
            sortBy=row['sort_by'],
            sortOrder=row['sort_order'],
            limitResults=row['limit_results'],
            isFavorite=row['is_favorite'],
            color=row['color'],
            icon=row['icon'],
            useCount=0,
            lastUsedAt=None,
            isShared=False,
            isPublic=False,
            createdAt=row['created_at'].isoformat(),
            updatedAt=row['updated_at'].isoformat()
        )
    
    except HTTPException:
        raise
    except Exception as e:
        logger.error("duplicate_template_error", template_id=template_id, error=str(e))
        raise HTTPException(status_code=500, detail=str(e))

