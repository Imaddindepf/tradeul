"""
User Preferences Router
Endpoints para gestionar preferencias de usuario (colores, fuentes, layouts)
"""

import json
from datetime import datetime
from typing import Optional, Dict, Any, List
from pydantic import BaseModel, Field

from fastapi import APIRouter, HTTPException, Header, Depends
import structlog

logger = structlog.get_logger(__name__)

router = APIRouter(prefix="/api/v1/user", tags=["user"])


# ============================================================================
# Pydantic Models
# ============================================================================

class ColorPreferences(BaseModel):
    tickUp: str = Field(default="#10b981", description="Color para precios al alza")
    tickDown: str = Field(default="#ef4444", description="Color para precios a la baja")
    background: str = Field(default="#ffffff", description="Color de fondo del dashboard")
    primary: str = Field(default="#3b82f6", description="Color primario/acento")


class ThemePreferences(BaseModel):
    font: str = Field(default="jetbrains-mono", description="Fuente monospace seleccionada")
    colorScheme: str = Field(default="light", description="Esquema de color: light/dark/system")


class WindowLayout(BaseModel):
    id: str
    type: str
    title: str
    position: Dict[str, int]  # {x, y}
    size: Dict[str, int]  # {width, height}
    isMinimized: bool = False
    zIndex: int = 0


class UserPreferencesRequest(BaseModel):
    colors: Optional[ColorPreferences] = None
    theme: Optional[ThemePreferences] = None
    windowLayouts: Optional[List[WindowLayout]] = None
    savedFilters: Optional[Dict[str, Any]] = None
    columnVisibility: Optional[Dict[str, Dict[str, bool]]] = None
    columnOrder: Optional[Dict[str, List[str]]] = None


class UserPreferencesResponse(BaseModel):
    userId: str
    colors: ColorPreferences
    theme: ThemePreferences
    windowLayouts: List[WindowLayout]
    savedFilters: Dict[str, Any]
    columnVisibility: Dict[str, Dict[str, bool]]
    columnOrder: Dict[str, List[str]]
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


async def get_user_id(authorization: Optional[str] = Header(None)) -> str:
    """
    Extrae el user_id del header Authorization.
    En producción, esto validaría el JWT de Clerk.
    Por ahora, aceptamos el user_id directamente en un header custom.
    """
    # Header custom: X-User-ID (para desarrollo)
    # En producción: validar JWT de Clerk
    return authorization or "anonymous"


# ============================================================================
# Endpoints
# ============================================================================

@router.get("/preferences", response_model=UserPreferencesResponse)
async def get_preferences(
    user_id: str = Header(..., alias="X-User-ID"),
    db=Depends(get_timescale)
):
    """
    Obtiene las preferencias del usuario.
    Si no existen, retorna valores por defecto.
    """
    try:
        query = """
            SELECT 
                user_id,
                colors,
                theme,
                window_layouts,
                saved_filters,
                column_visibility,
                column_order,
                updated_at
            FROM user_preferences
            WHERE user_id = $1
        """
        
        result = await db.fetchrow(query, user_id)
        
        if result:
            # Parsear JSONB - asyncpg puede devolver str o dict
            def parse_jsonb(val):
                if isinstance(val, str):
                    return json.loads(val)
                return val
            
            colors_data = parse_jsonb(result['colors'])
            theme_data = parse_jsonb(result['theme'])
            layouts_data = parse_jsonb(result['window_layouts'])
            
            return UserPreferencesResponse(
                userId=result['user_id'],
                colors=ColorPreferences(**colors_data),
                theme=ThemePreferences(**theme_data),
                windowLayouts=[WindowLayout(**w) for w in layouts_data],
                savedFilters=parse_jsonb(result['saved_filters']),
                columnVisibility=parse_jsonb(result['column_visibility']),
                columnOrder=parse_jsonb(result['column_order']),
                updatedAt=result['updated_at'].isoformat()
            )
        
        # Usuario nuevo: retornar defaults
        logger.info("user_preferences_not_found_returning_defaults", user_id=user_id)
        return UserPreferencesResponse(
            userId=user_id,
            colors=ColorPreferences(),
            theme=ThemePreferences(),
            windowLayouts=[],
            savedFilters={},
            columnVisibility={},
            columnOrder={},
            updatedAt=datetime.now().isoformat()
        )
    
    except Exception as e:
        logger.error("get_preferences_error", user_id=user_id, error=str(e))
        raise HTTPException(status_code=500, detail=str(e))


@router.put("/preferences")
async def save_preferences(
    prefs: UserPreferencesRequest,
    user_id: str = Header(..., alias="X-User-ID"),
    db=Depends(get_timescale)
):
    """
    Guarda las preferencias del usuario (upsert).
    Solo actualiza los campos proporcionados.
    """
    try:
        # Construir query de upsert dinámico
        updates = []
        values = [user_id]
        param_idx = 2
        
        # Mapeo de campos
        field_mapping = {
            'colors': prefs.colors,
            'theme': prefs.theme,
            'window_layouts': prefs.windowLayouts,
            'saved_filters': prefs.savedFilters,
            'column_visibility': prefs.columnVisibility,
            'column_order': prefs.columnOrder
        }
        
        for field, value in field_mapping.items():
            if value is not None:
                updates.append(f"{field} = ${param_idx}")
                # Convertir Pydantic models a dict para JSONB
                if hasattr(value, 'model_dump'):
                    values.append(json.dumps(value.model_dump()))
                elif isinstance(value, list):
                    values.append(json.dumps([
                        v.model_dump() if hasattr(v, 'model_dump') else v 
                        for v in value
                    ]))
                else:
                    values.append(json.dumps(value))
                param_idx += 1
        
        if not updates:
            raise HTTPException(status_code=400, detail="No preferences to update")
        
        # Upsert query
        query = f"""
            INSERT INTO user_preferences (user_id, {', '.join(field_mapping.keys())})
            VALUES ($1, 
                COALESCE($2::jsonb, '{{}}'::jsonb),
                COALESCE($3::jsonb, '{{}}'::jsonb),
                COALESCE($4::jsonb, '[]'::jsonb),
                COALESCE($5::jsonb, '{{}}'::jsonb),
                COALESCE($6::jsonb, '{{}}'::jsonb),
                COALESCE($7::jsonb, '{{}}'::jsonb)
            )
            ON CONFLICT (user_id) DO UPDATE SET
                {', '.join(updates)},
                updated_at = NOW()
            RETURNING updated_at
        """
        
        # Preparar todos los valores para el INSERT
        insert_values = [user_id]
        for field in ['colors', 'theme', 'window_layouts', 'saved_filters', 'column_visibility', 'column_order']:
            value = field_mapping.get(field.replace('_', ''))
            if field == 'window_layouts':
                value = prefs.windowLayouts
            elif field == 'saved_filters':
                value = prefs.savedFilters
            elif field == 'column_visibility':
                value = prefs.columnVisibility
            elif field == 'column_order':
                value = prefs.columnOrder
            else:
                value = getattr(prefs, field, None)
            
            if value is not None:
                if hasattr(value, 'model_dump'):
                    insert_values.append(json.dumps(value.model_dump()))
                elif isinstance(value, list):
                    insert_values.append(json.dumps([
                        v.model_dump() if hasattr(v, 'model_dump') else v 
                        for v in value
                    ]))
                else:
                    insert_values.append(json.dumps(value))
            else:
                insert_values.append(None)
        
        # Ejecutar upsert simplificado
        simple_query = """
            INSERT INTO user_preferences (user_id, colors, theme, window_layouts, saved_filters, column_visibility, column_order)
            VALUES ($1, 
                COALESCE($2::jsonb, '{"tickUp":"#10b981","tickDown":"#ef4444","background":"#ffffff","primary":"#3b82f6"}'::jsonb),
                COALESCE($3::jsonb, '{"font":"jetbrains-mono","colorScheme":"light"}'::jsonb),
                COALESCE($4::jsonb, '[]'::jsonb),
                COALESCE($5::jsonb, '{}'::jsonb),
                COALESCE($6::jsonb, '{}'::jsonb),
                COALESCE($7::jsonb, '{}'::jsonb)
            )
            ON CONFLICT (user_id) DO UPDATE SET
                colors = COALESCE($2::jsonb, user_preferences.colors),
                theme = COALESCE($3::jsonb, user_preferences.theme),
                window_layouts = COALESCE($4::jsonb, user_preferences.window_layouts),
                saved_filters = COALESCE($5::jsonb, user_preferences.saved_filters),
                column_visibility = COALESCE($6::jsonb, user_preferences.column_visibility),
                column_order = COALESCE($7::jsonb, user_preferences.column_order),
                updated_at = NOW()
            RETURNING updated_at
        """
        
        result = await db.fetchrow(simple_query, *insert_values)
        
        logger.info("preferences_saved", user_id=user_id)
        
        return {
            "success": True,
            "userId": user_id,
            "updatedAt": result['updated_at'].isoformat() if result else datetime.now().isoformat()
        }
    
    except HTTPException:
        raise
    except Exception as e:
        logger.error("save_preferences_error", user_id=user_id, error=str(e))
        raise HTTPException(status_code=500, detail=str(e))


@router.delete("/preferences")
async def delete_preferences(
    user_id: str = Header(..., alias="X-User-ID"),
    db=Depends(get_timescale)
):
    """
    Elimina todas las preferencias del usuario (reset a defaults).
    """
    try:
        query = "DELETE FROM user_preferences WHERE user_id = $1"
        await db.execute(query, user_id)
        
        logger.info("preferences_deleted", user_id=user_id)
        
        return {
            "success": True,
            "message": "Preferences reset to defaults"
        }
    
    except Exception as e:
        logger.error("delete_preferences_error", user_id=user_id, error=str(e))
        raise HTTPException(status_code=500, detail=str(e))


@router.patch("/preferences/colors")
async def update_colors(
    colors: ColorPreferences,
    user_id: str = Header(..., alias="X-User-ID"),
    db=Depends(get_timescale)
):
    """
    Actualiza solo los colores del usuario.
    """
    try:
        query = """
            INSERT INTO user_preferences (user_id, colors)
            VALUES ($1, $2::jsonb)
            ON CONFLICT (user_id) DO UPDATE SET
                colors = $2::jsonb,
                updated_at = NOW()
            RETURNING updated_at
        """
        
        result = await db.fetchrow(query, user_id, json.dumps(colors.model_dump()))
        
        return {
            "success": True,
            "colors": colors,
            "updatedAt": result['updated_at'].isoformat()
        }
    
    except Exception as e:
        logger.error("update_colors_error", user_id=user_id, error=str(e))
        raise HTTPException(status_code=500, detail=str(e))


@router.patch("/preferences/layout")
async def update_layout(
    layouts: List[WindowLayout],
    user_id: str = Header(..., alias="X-User-ID"),
    db=Depends(get_timescale)
):
    """
    Actualiza solo el layout de ventanas del usuario.
    """
    try:
        layouts_json = json.dumps([l.model_dump() for l in layouts])
        
        query = """
            INSERT INTO user_preferences (user_id, window_layouts)
            VALUES ($1, $2::jsonb)
            ON CONFLICT (user_id) DO UPDATE SET
                window_layouts = $2::jsonb,
                updated_at = NOW()
            RETURNING updated_at
        """
        
        result = await db.fetchrow(query, user_id, layouts_json)
        
        logger.info("layout_saved", user_id=user_id, window_count=len(layouts))
        
        return {
            "success": True,
            "windowCount": len(layouts),
            "updatedAt": result['updated_at'].isoformat()
        }
    
    except Exception as e:
        logger.error("update_layout_error", user_id=user_id, error=str(e))
        raise HTTPException(status_code=500, detail=str(e))

