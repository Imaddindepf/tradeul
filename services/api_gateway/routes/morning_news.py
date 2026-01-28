"""
Morning News Call Routes
========================

Endpoints para obtener el Morning News Call diario.
"""

import json
from datetime import date, datetime
from typing import Optional
from zoneinfo import ZoneInfo

from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel

from shared.utils.redis_client import RedisClient
from shared.utils.logger import get_logger

logger = get_logger(__name__)

router = APIRouter(prefix="/morning-news", tags=["Morning News"])

# Cliente Redis (inyectado desde main.py)
_redis_client: Optional[RedisClient] = None

NY_TZ = ZoneInfo("America/New_York")


def set_redis_client(client: RedisClient):
    """Inyectar cliente Redis"""
    global _redis_client
    _redis_client = client


# ============================================================================
# Models
# ============================================================================

class MorningNewsResponse(BaseModel):
    """Respuesta del Morning News Call"""
    success: bool
    date: str
    date_formatted: str
    report: str
    generated_at: str
    generation_time_seconds: Optional[float] = None
    lang: Optional[str] = 'es'


class MorningNewsListItem(BaseModel):
    """Item de lista de Morning News disponibles"""
    date: str
    date_formatted: str
    generated_at: str


# ============================================================================
# Endpoints
# ============================================================================

@router.get("/latest", response_model=MorningNewsResponse)
async def get_latest_morning_news(
    lang: str = Query(default='es', description="Idioma del reporte: 'es' o 'en'")
):
    """
    Obtener el Morning News Call más reciente.
    
    Este reporte se genera automáticamente a las 7:30 AM ET cada día de trading.
    
    Args:
        lang: Idioma del reporte ('es' para español, 'en' para inglés)
    """
    if not _redis_client:
        raise HTTPException(status_code=503, detail="Redis no disponible")
    
    # Validar idioma
    if lang not in ['es', 'en']:
        lang = 'es'
    
    try:
        # Buscar el reporte más reciente en el idioma solicitado
        data = await _redis_client.get(f"morning_news:latest:{lang}")
        
        # Fallback al idioma por defecto si no existe
        if not data:
            data = await _redis_client.get("morning_news:latest")
        
        if not data:
            # No hay reporte disponible
            raise HTTPException(
                status_code=404, 
                detail="No hay Morning News disponible. Se genera a las 7:30 AM ET."
            )
        
        # Parsear JSON
        if isinstance(data, str):
            report = json.loads(data)
        else:
            report = data
        
        # Añadir idioma si no existe
        if 'lang' not in report:
            report['lang'] = lang
        
        return MorningNewsResponse(**report)
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error("get_latest_morning_news_error", error=str(e))
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/date/{report_date}", response_model=MorningNewsResponse)
async def get_morning_news_by_date(report_date: str):
    """
    Obtener el Morning News Call de una fecha específica.
    
    Args:
        report_date: Fecha en formato YYYY-MM-DD
    """
    if not _redis_client:
        raise HTTPException(status_code=503, detail="Redis no disponible")
    
    try:
        # Validar formato de fecha
        try:
            parsed_date = date.fromisoformat(report_date)
        except ValueError:
            raise HTTPException(status_code=400, detail="Formato de fecha inválido. Use YYYY-MM-DD")
        
        # Buscar el reporte
        data = await _redis_client.get(f"morning_news:{report_date}")
        
        if not data:
            raise HTTPException(
                status_code=404, 
                detail=f"No hay Morning News para la fecha {report_date}"
            )
        
        # Parsear JSON
        if isinstance(data, str):
            report = json.loads(data)
        else:
            report = data
        
        return MorningNewsResponse(**report)
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error("get_morning_news_by_date_error", date=report_date, error=str(e))
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/generate")
async def generate_morning_news_now(
    force: bool = Query(default=False, description="Forzar regeneración aunque ya exista")
):
    """
    Generar el Morning News Call manualmente (para testing/admin).
    
    Este endpoint es útil para:
    - Testing del sistema
    - Regenerar si hubo un error
    - Generar fuera del horario normal
    
    Args:
        force: Si True, regenera aunque ya exista uno para hoy
    """
    if not _redis_client:
        raise HTTPException(status_code=503, detail="Redis no disponible")
    
    try:
        today = datetime.now(NY_TZ).date()
        
        # Verificar si ya existe (a menos que se force)
        if not force:
            existing = await _redis_client.get(f"morning_news:{today.isoformat()}")
            if existing:
                return {
                    "success": True,
                    "message": "Morning News ya existe para hoy",
                    "date": today.isoformat(),
                    "regenerated": False
                }
        
        # Importar el generador
        from tasks.morning_news_call import generate_morning_news_call
        
        # Generar el reporte
        result = await generate_morning_news_call(today)
        
        if result.get("success"):
            # Guardar en Redis (30 días para histórico)
            report_key = f"morning_news:{today.isoformat()}"
            await _redis_client.set(
                report_key,
                json.dumps(result, ensure_ascii=False),
                ex=86400 * 30  # 30 días
            )
            
            await _redis_client.set(
                "morning_news:latest",
                json.dumps(result, ensure_ascii=False),
                ex=86400 * 30  # 30 días
            )
            
            # Notificar via Pub/Sub
            await _redis_client.client.publish(
                "notifications:morning_news",
                json.dumps({
                    "event": "morning_news_call",
                    "date": today.isoformat(),
                    "title": "Tradeul.com MORNING NEWS CALL",
                    "manual": True
                }, ensure_ascii=False)
            )
            
            return {
                "success": True,
                "message": "Morning News generado exitosamente",
                "date": today.isoformat(),
                "regenerated": force,
                "report_length": len(result.get("report", "")),
                "generation_time_seconds": result.get("generation_time_seconds")
            }
        else:
            raise HTTPException(
                status_code=500, 
                detail=f"Error generando reporte: {result.get('error')}"
            )
            
    except HTTPException:
        raise
    except ImportError as e:
        logger.error("morning_news_import_error", error=str(e))
        raise HTTPException(
            status_code=501, 
            detail="Generador de Morning News no disponible en este servicio"
        )
    except Exception as e:
        logger.error("generate_morning_news_error", error=str(e))
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/status")
async def get_morning_news_status():
    """
    Obtener el estado del sistema de Morning News.
    
    Incluye:
    - Si hay un reporte disponible para hoy
    - Fecha del último reporte
    - Próxima generación programada
    """
    if not _redis_client:
        raise HTTPException(status_code=503, detail="Redis no disponible")
    
    try:
        now_et = datetime.now(NY_TZ)
        today = now_et.date()
        
        # Verificar si hay reporte de hoy
        today_report = await _redis_client.get(f"morning_news:{today.isoformat()}")
        has_today_report = today_report is not None
        
        # Obtener fecha del último reporte
        latest = await _redis_client.get("morning_news:latest")
        last_report_date = None
        if latest:
            try:
                latest_data = json.loads(latest) if isinstance(latest, str) else latest
                last_report_date = latest_data.get("date")
            except:
                pass
        
        # Calcular próxima generación
        if now_et.hour < 7 or (now_et.hour == 7 and now_et.minute < 30):
            next_generation = now_et.replace(hour=7, minute=30, second=0, microsecond=0)
        else:
            # Mañana a las 7:30
            from datetime import timedelta
            next_generation = (now_et + timedelta(days=1)).replace(hour=7, minute=30, second=0, microsecond=0)
        
        return {
            "current_time_et": now_et.strftime("%Y-%m-%d %H:%M:%S ET"),
            "has_today_report": has_today_report,
            "last_report_date": last_report_date,
            "next_scheduled_generation": next_generation.strftime("%Y-%m-%d %H:%M:%S ET"),
            "generation_time": "7:30 AM ET (días de trading)"
        }
        
    except Exception as e:
        logger.error("morning_news_status_error", error=str(e))
        raise HTTPException(status_code=500, detail=str(e))

