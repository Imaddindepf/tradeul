"""
TradeUL Insights Routes
=======================

Endpoints unificados para todos los reportes de TradeUL Insights:
- Morning News Call (7:30 AM ET)
- Mid-Morning Update (12:30 PM ET)
- Evening Report (4:30 PM ET) - futuro
- Weekly Summary (Sundays) - futuro
"""

import json
from datetime import date, datetime, timedelta
from typing import List, Literal, Optional
from zoneinfo import ZoneInfo

from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel

from shared.utils.redis_client import RedisClient
from shared.utils.logger import get_logger

logger = get_logger(__name__)

router = APIRouter(prefix="/insights", tags=["Insights"])

# Cliente Redis (inyectado desde main.py)
_redis_client: Optional[RedisClient] = None

NY_TZ = ZoneInfo("America/New_York")

# Tipos de insight disponibles
InsightType = Literal["morning", "midmorning", "evening", "weekly"]


def set_redis_client(client: RedisClient):
    """Inyectar cliente Redis"""
    global _redis_client
    _redis_client = client


# ============================================================================
# Models
# ============================================================================

class InsightResponse(BaseModel):
    """Respuesta de un Insight"""
    success: bool
    type: InsightType
    date: str
    date_formatted: str
    report: str
    generated_at: str
    generation_time_seconds: Optional[float] = None
    lang: str = 'es'


class InsightListItem(BaseModel):
    """Item de lista de Insights disponibles"""
    id: str
    type: InsightType
    date: str
    date_formatted: str
    generated_at: str
    title: str
    preview: str


class InsightStatusResponse(BaseModel):
    """Estado del sistema de Insights"""
    current_time_et: str
    available_insights: List[dict]
    next_scheduled: dict


# ============================================================================
# Helper Functions
# ============================================================================

def get_redis_key(insight_type: InsightType, report_date: str, lang: str) -> str:
    """Generar clave Redis para un insight"""
    if insight_type == "morning":
        return f"morning_news:{report_date}:{lang}"
    elif insight_type == "midmorning":
        return f"midmorning_update:{report_date}:{lang}"
    elif insight_type == "evening":
        return f"evening_report:{report_date}:{lang}"
    elif insight_type == "weekly":
        return f"weekly_summary:{report_date}:{lang}"
    return f"insight:{insight_type}:{report_date}:{lang}"


def get_insight_title(insight_type: InsightType, lang: str) -> str:
    """Obtener título del insight según tipo e idioma"""
    titles = {
        "morning": {
            "es": "Morning News Call",
            "en": "Morning News Call"
        },
        "midmorning": {
            "es": "Mid-Morning Update",
            "en": "Mid-Morning Update"
        },
        "evening": {
            "es": "Evening Report",
            "en": "Evening Report"
        },
        "weekly": {
            "es": "Resumen Semanal",
            "en": "Weekly Summary"
        }
    }
    return titles.get(insight_type, {}).get(lang, "Insight")


# ============================================================================
# Endpoints
# ============================================================================

@router.get("/latest", response_model=InsightResponse)
async def get_latest_insight(
    type: InsightType = Query(default="morning", description="Tipo de insight"),
    lang: str = Query(default='es', description="Idioma: 'es' o 'en'")
):
    """
    Obtener el insight más reciente del tipo especificado.
    
    Tipos disponibles:
    - morning: Morning News Call (7:30 AM ET)
    - midmorning: Mid-Morning Update (12:30 PM ET)
    - evening: Evening Report (4:30 PM ET) [próximamente]
    - weekly: Weekly Summary [próximamente]
    """
    if not _redis_client:
        raise HTTPException(status_code=503, detail="Redis no disponible")
    
    if lang not in ['es', 'en']:
        lang = 'es'
    
    try:
        # Buscar el insight más reciente
        latest_key = f"{type}_news:latest:{lang}" if type == "morning" else f"{type}_update:latest:{lang}"
        if type == "morning":
            latest_key = f"morning_news:latest:{lang}"
        elif type == "midmorning":
            latest_key = f"midmorning_update:latest:{lang}"
        
        data = await _redis_client.get(latest_key)
        
        if not data:
            raise HTTPException(
                status_code=404, 
                detail=f"No hay {get_insight_title(type, lang)} disponible."
            )
        
        if isinstance(data, str):
            report = json.loads(data)
        else:
            report = data
        
        # Asegurar campos requeridos
        report['type'] = type
        if 'lang' not in report:
            report['lang'] = lang
        
        return InsightResponse(**report)
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error("get_latest_insight_error", type=type, error=str(e))
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/list", response_model=List[InsightListItem])
async def list_insights(
    type: Optional[InsightType] = Query(default=None, description="Filtrar por tipo"),
    lang: str = Query(default='es', description="Idioma: 'es' o 'en'"),
    days: int = Query(default=7, ge=1, le=30, description="Días hacia atrás")
):
    """
    Listar insights disponibles.
    
    Devuelve todos los insights de los últimos N días, opcionalmente filtrados por tipo.
    """
    if not _redis_client:
        raise HTTPException(status_code=503, detail="Redis no disponible")
    
    if lang not in ['es', 'en']:
        lang = 'es'
    
    try:
        insights = []
        today = datetime.now(NY_TZ).date()
        
        types_to_check: List[InsightType] = [type] if type else ["morning", "midmorning"]
        
        for i in range(days):
            check_date = today - timedelta(days=i)
            date_str = check_date.isoformat()
            
            for insight_type in types_to_check:
                key = get_redis_key(insight_type, date_str, lang)
                data = await _redis_client.get(key)
                
                if data:
                    if isinstance(data, str):
                        report = json.loads(data)
                    else:
                        report = data
                    
                    report_text = report.get("report", "")
                    preview = report_text[:200] + "..." if len(report_text) > 200 else report_text
                    
                    insights.append(InsightListItem(
                        id=f"{insight_type}:{date_str}",
                        type=insight_type,
                        date=date_str,
                        date_formatted=report.get("date_formatted", date_str),
                        generated_at=report.get("generated_at", ""),
                        title=get_insight_title(insight_type, lang),
                        preview=preview
                    ))
        
        return insights
        
    except Exception as e:
        logger.error("list_insights_error", error=str(e))
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/date/{report_date}", response_model=InsightResponse)
async def get_insight_by_date(
    report_date: str,
    type: InsightType = Query(default="morning", description="Tipo de insight"),
    lang: str = Query(default='es', description="Idioma: 'es' o 'en'")
):
    """
    Obtener un insight específico por fecha y tipo.
    
    Args:
        report_date: Fecha en formato YYYY-MM-DD
        type: Tipo de insight
        lang: Idioma del reporte
    """
    if not _redis_client:
        raise HTTPException(status_code=503, detail="Redis no disponible")
    
    if lang not in ['es', 'en']:
        lang = 'es'
    
    try:
        try:
            parsed_date = date.fromisoformat(report_date)
        except ValueError:
            raise HTTPException(status_code=400, detail="Formato de fecha inválido. Use YYYY-MM-DD")
        
        key = get_redis_key(type, report_date, lang)
        data = await _redis_client.get(key)
        
        if not data:
            raise HTTPException(
                status_code=404, 
                detail=f"No hay {get_insight_title(type, lang)} para {report_date}"
            )
        
        if isinstance(data, str):
            report = json.loads(data)
        else:
            report = data
        
        report['type'] = type
        if 'lang' not in report:
            report['lang'] = lang
        
        return InsightResponse(**report)
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error("get_insight_by_date_error", date=report_date, type=type, error=str(e))
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/generate/{insight_type}")
async def generate_insight_now(
    insight_type: InsightType,
    force: bool = Query(default=False, description="Forzar regeneración")
):
    """
    Generar un insight manualmente (para testing/admin).
    
    Args:
        insight_type: Tipo de insight a generar
        force: Si True, regenera aunque ya exista
    """
    if not _redis_client:
        raise HTTPException(status_code=503, detail="Redis no disponible")
    
    try:
        today = datetime.now(NY_TZ).date()
        
        if insight_type == "morning":
            # Verificar si ya existe
            if not force:
                existing = await _redis_client.get(f"morning_news:{today.isoformat()}:es")
                if existing:
                    return {
                        "success": True,
                        "message": "Morning News ya existe para hoy",
                        "type": insight_type,
                        "date": today.isoformat(),
                        "regenerated": False
                    }
            
            from tasks.morning_news_call import generate_bilingual_morning_news_call
            result = await generate_bilingual_morning_news_call(today)
            
            if result.get("success"):
                # Guardar ambos idiomas
                for lang in ['es', 'en']:
                    report_data = result["reports"][lang]
                    await _redis_client.set(
                        f"morning_news:{today.isoformat()}:{lang}",
                        json.dumps(report_data, ensure_ascii=False),
                        ex=86400
                    )
                    await _redis_client.set(
                        f"morning_news:latest:{lang}",
                        json.dumps(report_data, ensure_ascii=False),
                        ex=86400
                    )
                
                return {
                    "success": True,
                    "message": "Morning News generado exitosamente",
                    "type": insight_type,
                    "date": today.isoformat(),
                    "regenerated": force
                }
        
        elif insight_type == "midmorning":
            # Verificar si ya existe
            if not force:
                existing = await _redis_client.get(f"midmorning_update:{today.isoformat()}:es")
                if existing:
                    return {
                        "success": True,
                        "message": "Mid-Morning Update ya existe para hoy",
                        "type": insight_type,
                        "date": today.isoformat(),
                        "regenerated": False
                    }
            
            from tasks.midmorning_update import generate_bilingual_midmorning_update
            result = await generate_bilingual_midmorning_update(today)
            
            if result.get("success"):
                # Guardar ambos idiomas
                for lang in ['es', 'en']:
                    report_data = result["reports"][lang]
                    await _redis_client.set(
                        f"midmorning_update:{today.isoformat()}:{lang}",
                        json.dumps(report_data, ensure_ascii=False),
                        ex=86400
                    )
                    await _redis_client.set(
                        f"midmorning_update:latest:{lang}",
                        json.dumps(report_data, ensure_ascii=False),
                        ex=86400
                    )
                
                # Notificar via Pub/Sub
                await _redis_client.client.publish(
                    "notifications:insight",
                    json.dumps({
                        "event": "insight_notification",
                        "type": "midmorning",
                        "date": today.isoformat(),
                        "title": "TradeUL Mid-Morning Update",
                        "manual": True
                    }, ensure_ascii=False)
                )
                
                return {
                    "success": True,
                    "message": "Mid-Morning Update generado exitosamente",
                    "type": insight_type,
                    "date": today.isoformat(),
                    "regenerated": force,
                    "report_length_es": len(result["reports"]["es"].get("report", "")),
                    "report_length_en": len(result["reports"]["en"].get("report", ""))
                }
            else:
                raise HTTPException(
                    status_code=500,
                    detail=f"Error generando Mid-Morning Update: {result.get('error')}"
                )
        
        else:
            raise HTTPException(
                status_code=501,
                detail=f"Tipo de insight '{insight_type}' aún no implementado"
            )
            
    except HTTPException:
        raise
    except ImportError as e:
        logger.error("insight_import_error", type=insight_type, error=str(e))
        raise HTTPException(
            status_code=501, 
            detail=f"Generador de {insight_type} no disponible en este servicio"
        )
    except Exception as e:
        logger.error("generate_insight_error", type=insight_type, error=str(e))
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/status", response_model=InsightStatusResponse)
async def get_insights_status():
    """
    Obtener el estado del sistema de Insights.
    
    Incluye:
    - Insights disponibles para hoy
    - Próximas generaciones programadas
    """
    if not _redis_client:
        raise HTTPException(status_code=503, detail="Redis no disponible")
    
    try:
        now_et = datetime.now(NY_TZ)
        today = now_et.date()
        
        # Verificar insights disponibles
        available = []
        
        for insight_type in ["morning", "midmorning"]:
            for lang in ["es", "en"]:
                key = get_redis_key(insight_type, today.isoformat(), lang)
                data = await _redis_client.get(key)
                if data:
                    available.append({
                        "type": insight_type,
                        "lang": lang,
                        "date": today.isoformat()
                    })
                    break  # Solo necesitamos saber que existe, no ambos idiomas
        
        # Calcular próximas generaciones
        next_scheduled = {}
        
        # Morning News: 7:30 AM ET
        if now_et.hour < 7 or (now_et.hour == 7 and now_et.minute < 30):
            next_morning = now_et.replace(hour=7, minute=30, second=0, microsecond=0)
        else:
            next_morning = (now_et + timedelta(days=1)).replace(hour=7, minute=30, second=0, microsecond=0)
        next_scheduled["morning"] = next_morning.strftime("%Y-%m-%d %H:%M ET")
        
        # Mid-Morning Update: 12:30 PM ET
        if now_et.hour < 12 or (now_et.hour == 12 and now_et.minute < 30):
            next_midmorning = now_et.replace(hour=12, minute=30, second=0, microsecond=0)
        else:
            next_midmorning = (now_et + timedelta(days=1)).replace(hour=12, minute=30, second=0, microsecond=0)
        next_scheduled["midmorning"] = next_midmorning.strftime("%Y-%m-%d %H:%M ET")
        
        return InsightStatusResponse(
            current_time_et=now_et.strftime("%Y-%m-%d %H:%M:%S ET"),
            available_insights=available,
            next_scheduled=next_scheduled
        )
        
    except Exception as e:
        logger.error("insights_status_error", error=str(e))
        raise HTTPException(status_code=500, detail=str(e))

