"""
Earnings Calendar Collector
============================

Recopila datos de earnings usando Gemini 3 con Google Search:
1. Calendario de earnings programados (scheduled)
2. Resultados de earnings reportados (actuals + guidance)

Se ejecuta diariamente en múltiples horarios:
- 4:00 AM ET: Recopilar calendario del día (qué empresas reportan hoy)
- 10:00 AM ET: Actualizar con resultados BMO (Before Market Open)
- 5:00 PM ET: Actualizar con resultados AMC (After Market Close)

Usa Gemini 3 Flash con:
- Google Search (grounding) para datos en tiempo real
- Structured outputs (Pydantic) para respuestas tipadas
"""

import os
import asyncio
from datetime import datetime, date, time as dt_time, timedelta
from zoneinfo import ZoneInfo
from typing import List, Optional, Dict, Any
from decimal import Decimal

from pydantic import BaseModel, Field
from google import genai
from google.genai import types

from shared.utils.logger import get_logger
from shared.utils.redis_client import RedisClient
from shared.utils.timescale_client import TimescaleClient
from shared.config.settings import settings

logger = get_logger(__name__)

NY_TZ = ZoneInfo("America/New_York")


# =============================================================================
# PYDANTIC MODELS PARA STRUCTURED OUTPUTS
# =============================================================================

class ScheduledEarning(BaseModel):
    """Earnings programado (aún no reportado)"""
    symbol: str = Field(..., description="Ticker symbol (e.g., AAPL)")
    company_name: str = Field(..., description="Full company name")
    report_date: str = Field(..., description="Report date YYYY-MM-DD")
    time_slot: str = Field(..., description="BMO, AMC, DURING, or TBD")
    earnings_call_time: Optional[str] = Field(None, description="Call time HH:MM ET if known")
    fiscal_quarter: Optional[str] = Field(None, description="e.g., Q4 2025")
    eps_estimate: Optional[float] = Field(None, description="Consensus EPS estimate")
    revenue_estimate_millions: Optional[float] = Field(None, description="Revenue estimate in millions USD")
    market_cap_billions: Optional[float] = Field(None, description="Market cap in billions USD")
    sector: Optional[str] = Field(None, description="Company sector")


class ReportedEarning(BaseModel):
    """Earnings ya reportado con resultados"""
    symbol: str = Field(..., description="Ticker symbol")
    company_name: str = Field(..., description="Full company name")
    report_date: str = Field(..., description="Report date YYYY-MM-DD")
    time_slot: str = Field(..., description="BMO, AMC, or DURING")
    fiscal_quarter: Optional[str] = Field(None, description="e.g., Q4 2025")
    
    # Resultados
    eps_estimate: Optional[float] = Field(None, description="EPS estimate (consensus)")
    eps_actual: Optional[float] = Field(None, description="Actual EPS reported")
    eps_surprise_pct: Optional[float] = Field(None, description="EPS surprise percentage")
    beat_eps: Optional[bool] = Field(None, description="True if beat EPS estimate")
    
    revenue_estimate_millions: Optional[float] = Field(None, description="Revenue estimate in millions")
    revenue_actual_millions: Optional[float] = Field(None, description="Actual revenue in millions")
    revenue_surprise_pct: Optional[float] = Field(None, description="Revenue surprise percentage")
    beat_revenue: Optional[bool] = Field(None, description="True if beat revenue estimate")
    
    # Guidance
    guidance_direction: Optional[str] = Field(None, description="raised, lowered, maintained, or none")
    guidance_commentary: Optional[str] = Field(None, description="Key guidance comments")
    
    # Key highlights
    key_highlights: Optional[List[str]] = Field(None, description="Key points from earnings report")


class EarningsCalendarResponse(BaseModel):
    """Respuesta del calendario de earnings"""
    date: str = Field(..., description="Calendar date YYYY-MM-DD")
    scheduled: List[ScheduledEarning] = Field(default_factory=list)
    total_bmo: int = Field(0, description="Total reporting BMO")
    total_amc: int = Field(0, description="Total reporting AMC")


class ReportedEarningsResponse(BaseModel):
    """Respuesta de earnings reportados"""
    date: str = Field(..., description="Report date YYYY-MM-DD")
    reported: List[ReportedEarning] = Field(default_factory=list)


# =============================================================================
# EARNINGS COLLECTOR TASK
# =============================================================================

class EarningsCollectorTask:
    """
    Tarea para recopilar earnings usando Gemini + Google Search.
    
    Flujo:
    1. collect_scheduled_earnings: Obtener calendario del día
    2. collect_reported_earnings: Obtener resultados de empresas que ya reportaron
    3. Guardar/actualizar en earnings_calendar
    """
    
    def __init__(self, redis: RedisClient, db: TimescaleClient):
        self.redis = redis
        self.db = db
        self._genai_client = None
    
    @property
    def genai_client(self):
        """Lazy initialization del cliente Gemini"""
        if self._genai_client is None:
            api_key = settings.GOOGL_API_KEY_V2 or os.getenv('GOOGL_API_KEY')
            if not api_key:
                raise ValueError("GOOGL_API_KEY es requerido para EarningsCollector")
            self._genai_client = genai.Client(api_key=api_key)
        return self._genai_client
    
    # =========================================================================
    # COLLECT SCHEDULED EARNINGS (Calendario)
    # =========================================================================
    
    async def collect_scheduled_earnings(self, target_date: date) -> Dict[str, Any]:
        """
        Recopila el calendario de earnings para una fecha específica.
        
        Args:
            target_date: Fecha para buscar earnings programados
            
        Returns:
            Dict con resultados y estadísticas
        """
        logger.info("📅 collecting_scheduled_earnings", date=target_date.isoformat())
        
        date_str = target_date.strftime("%B %d, %Y")  # e.g., "January 15, 2026"
        
        prompt = f"""
Search for the COMPLETE earnings calendar for {date_str}.

Find ALL major US companies SCHEDULED to report earnings on {target_date.isoformat()}.

Focus on:
1. Companies with market cap > $1 billion (prioritize large caps)
2. Well-known companies from major indices (S&P 500, Nasdaq 100)
3. Banks and financial institutions if it's earnings season

For EACH company provide:
- Exact ticker symbol (verify it's correct)
- Full company name
- Report date: {target_date.isoformat()}
- Time slot: BMO (before market open 4am-9:30am), AMC (after market close 4pm+), or TBD
- Earnings call time if available (in ET timezone)
- Fiscal quarter (e.g., Q4 2025, Q1 2026)
- Consensus EPS estimate from analysts
- Revenue estimate in MILLIONS USD
- Market cap in BILLIONS USD
- Sector

Search for "earnings calendar {date_str}" and "companies reporting earnings {date_str}".
Be thorough but accurate - only include companies actually scheduled for this specific date.
"""

        try:
            response = self.genai_client.models.generate_content(
                model='gemini-3-flash-preview',
                contents=prompt,
                config=types.GenerateContentConfig(
                    tools=[types.Tool(google_search=types.GoogleSearch())],
                    response_mime_type='application/json',
                    response_schema=EarningsCalendarResponse,
                    temperature=0.1,  # Baja temperatura para más precisión
                )
            )
            
            calendar = EarningsCalendarResponse.model_validate_json(response.text)
            
            # Extraer fuentes de grounding
            grounding_sources = self._extract_grounding_sources(response)
            
            # Guardar en BD
            inserted = 0
            for earning in calendar.scheduled:
                try:
                    await self._upsert_scheduled_earning(earning, grounding_sources)
                    inserted += 1
                except Exception as e:
                    logger.warning("failed_to_insert_scheduled", symbol=earning.symbol, error=str(e))
            
            # Guardar en Redis para acceso rápido
            cache_key = f"earnings:calendar:{target_date.isoformat()}"
            await self.redis.set(
                cache_key,
                response.text,
                ttl=86400 * 3  # 3 días
            )
            
            logger.info(
                "✅ scheduled_earnings_collected",
                date=target_date.isoformat(),
                total_found=len(calendar.scheduled),
                inserted=inserted,
                bmo=calendar.total_bmo,
                amc=calendar.total_amc
            )
            
            return {
                "success": True,
                "date": target_date.isoformat(),
                "total_found": len(calendar.scheduled),
                "inserted": inserted,
                "bmo": calendar.total_bmo,
                "amc": calendar.total_amc
            }
            
        except Exception as e:
            logger.error("scheduled_earnings_error", date=target_date.isoformat(), error=str(e))
            return {"success": False, "error": str(e), "date": target_date.isoformat()}
    
    # =========================================================================
    # COLLECT REPORTED EARNINGS (Resultados)
    # =========================================================================
    
    async def collect_reported_earnings(
        self, 
        target_date: date,
        time_slot: Optional[str] = None
    ) -> Dict[str, Any]:
        """
        Recopila resultados de earnings ya reportados.
        
        Args:
            target_date: Fecha de los reportes
            time_slot: Filtrar por BMO o AMC (None = ambos)
            
        Returns:
            Dict con resultados y estadísticas
        """
        slot_filter = f" ({time_slot})" if time_slot else ""
        logger.info(
            "📊 collecting_reported_earnings", 
            date=target_date.isoformat(),
            time_slot=time_slot or "all"
        )
        
        date_str = target_date.strftime("%B %d, %Y")
        
        # Primero obtener qué empresas estaban programadas
        scheduled_symbols = await self._get_scheduled_symbols(target_date, time_slot)
        
        if not scheduled_symbols:
            # Si no hay scheduled, buscar de forma general
            prompt = f"""
Search for US companies that ALREADY REPORTED earnings on {date_str}{slot_filter}.

Find companies that have RELEASED their quarterly earnings results for {target_date.isoformat()}.
Focus on major companies (market cap > $500M) that reported {time_slot or 'today'}.

For EACH company that HAS ALREADY REPORTED, provide:
- Ticker symbol
- Company name
- Report date: {target_date.isoformat()}
- Time slot when they reported (BMO or AMC)
- Fiscal quarter

RESULTS:
- EPS estimate (what analysts expected)
- Actual EPS reported
- EPS surprise % (positive = beat, negative = miss)
- Did they beat EPS? (true/false)

- Revenue estimate in MILLIONS
- Actual revenue in MILLIONS
- Revenue surprise %
- Did they beat revenue? (true/false)

GUIDANCE:
- Direction: raised, lowered, maintained, or none
- Key guidance commentary

KEY HIGHLIGHTS:
- 2-3 most important points from the earnings report/call

Search for "earnings results {date_str}" and "{time_slot + ' ' if time_slot else ''}earnings reports {date_str}".
Only include companies that have ACTUALLY REPORTED (not scheduled).
"""
        else:
            # Buscar resultados específicos para los tickers programados
            symbols_str = ", ".join(scheduled_symbols[:30])  # Limitar a 30
            prompt = f"""
Search for earnings RESULTS for these companies that were scheduled to report on {date_str}{slot_filter}:
{symbols_str}

For EACH company that HAS REPORTED, provide the actual results:
- Ticker symbol
- Company name
- Report date: {target_date.isoformat()}
- Time slot (BMO or AMC)
- Fiscal quarter

RESULTS:
- EPS estimate (consensus)
- Actual EPS reported
- EPS surprise percentage
- Beat EPS? (true/false)

- Revenue estimate in MILLIONS USD
- Actual revenue in MILLIONS USD
- Revenue surprise percentage
- Beat revenue? (true/false)

GUIDANCE:
- Direction: raised, lowered, maintained, or none
- Key commentary about forward guidance

KEY HIGHLIGHTS:
- 2-3 most important takeaways from earnings

Search for specific earnings results for each ticker.
Only include companies that have ACTUALLY REPORTED their results.
"""

        try:
            response = self.genai_client.models.generate_content(
                model='gemini-3-flash-preview',
                contents=prompt,
                config=types.GenerateContentConfig(
                    tools=[types.Tool(google_search=types.GoogleSearch())],
                    response_mime_type='application/json',
                    response_schema=ReportedEarningsResponse,
                    temperature=0.1,
                )
            )
            
            reported = ReportedEarningsResponse.model_validate_json(response.text)
            
            # Extraer fuentes
            grounding_sources = self._extract_grounding_sources(response)
            
            # Actualizar en BD
            updated = 0
            for earning in reported.reported:
                try:
                    await self._update_reported_earning(earning, grounding_sources)
                    updated += 1
                except Exception as e:
                    logger.warning("failed_to_update_reported", symbol=earning.symbol, error=str(e))
            
            # Cache de resultados
            cache_key = f"earnings:reported:{target_date.isoformat()}:{time_slot or 'all'}"
            await self.redis.set(
                cache_key,
                response.text,
                ttl=86400 * 3
            )
            
            logger.info(
                "✅ reported_earnings_collected",
                date=target_date.isoformat(),
                time_slot=time_slot or "all",
                total_found=len(reported.reported),
                updated=updated
            )
            
            return {
                "success": True,
                "date": target_date.isoformat(),
                "time_slot": time_slot,
                "total_found": len(reported.reported),
                "updated": updated
            }
            
        except Exception as e:
            logger.error("reported_earnings_error", date=target_date.isoformat(), error=str(e))
            return {"success": False, "error": str(e), "date": target_date.isoformat()}
    
    # =========================================================================
    # DATABASE OPERATIONS
    # =========================================================================
    
    async def _upsert_scheduled_earning(
        self, 
        earning: ScheduledEarning,
        grounding_sources: List[str]
    ):
        """Insertar o actualizar un earning programado"""
        
        # Parsear earnings_call_time si existe
        call_time = None
        if earning.earnings_call_time:
            try:
                call_time = datetime.strptime(earning.earnings_call_time, "%H:%M").time()
            except:
                pass
        
        # Convertir revenue de millones a valor absoluto
        revenue_estimate = None
        if earning.revenue_estimate_millions:
            revenue_estimate = int(earning.revenue_estimate_millions * 1_000_000)
        
        # Market cap de billions a valor absoluto
        market_cap = None
        if earning.market_cap_billions:
            market_cap = int(earning.market_cap_billions * 1_000_000_000)
        
        query = """
            INSERT INTO earnings_calendar (
                symbol, company_name, report_date, time_slot, earnings_call_time,
                fiscal_quarter, eps_estimate, revenue_estimate,
                market_cap, sector, status, source, grounding_sources, confidence
            ) VALUES (
                $1, $2, $3, $4, $5, $6, $7, $8, $9, $10, $11, $12, $13, $14
            )
            ON CONFLICT (symbol, report_date) DO UPDATE SET
                company_name = COALESCE(EXCLUDED.company_name, earnings_calendar.company_name),
                time_slot = COALESCE(EXCLUDED.time_slot, earnings_calendar.time_slot),
                earnings_call_time = COALESCE(EXCLUDED.earnings_call_time, earnings_calendar.earnings_call_time),
                fiscal_quarter = COALESCE(EXCLUDED.fiscal_quarter, earnings_calendar.fiscal_quarter),
                eps_estimate = COALESCE(EXCLUDED.eps_estimate, earnings_calendar.eps_estimate),
                revenue_estimate = COALESCE(EXCLUDED.revenue_estimate, earnings_calendar.revenue_estimate),
                market_cap = COALESCE(EXCLUDED.market_cap, earnings_calendar.market_cap),
                sector = COALESCE(EXCLUDED.sector, earnings_calendar.sector),
                source = EXCLUDED.source,
                grounding_sources = EXCLUDED.grounding_sources,
                updated_at = NOW()
        """
        
        await self.db.execute(
            query,
            earning.symbol.upper(),
            earning.company_name,
            date.fromisoformat(earning.report_date),
            earning.time_slot.upper() if earning.time_slot else 'TBD',
            call_time,
            earning.fiscal_quarter,
            earning.eps_estimate,
            revenue_estimate,
            market_cap,
            earning.sector,
            'scheduled',
            'google_search',
            grounding_sources[:10] if grounding_sources else None,  # Limitar a 10 fuentes
            0.85  # Confianza base para Google Search
        )
    
    async def _update_reported_earning(
        self,
        earning: ReportedEarning,
        grounding_sources: List[str]
    ):
        """Actualizar un earning con resultados reportados"""
        
        # Convertir revenues de millones a valor absoluto
        revenue_estimate = None
        if earning.revenue_estimate_millions:
            revenue_estimate = int(earning.revenue_estimate_millions * 1_000_000)
        
        revenue_actual = None
        if earning.revenue_actual_millions:
            revenue_actual = int(earning.revenue_actual_millions * 1_000_000)
        
        query = """
            INSERT INTO earnings_calendar (
                symbol, company_name, report_date, time_slot, fiscal_quarter,
                eps_estimate, eps_actual, eps_surprise_pct, beat_eps,
                revenue_estimate, revenue_actual, revenue_surprise_pct, beat_revenue,
                guidance_direction, guidance_commentary, key_highlights,
                status, source, grounding_sources, confidence
            ) VALUES (
                $1, $2, $3, $4, $5, $6, $7, $8, $9, $10, $11, $12, $13, $14, $15, $16, $17, $18, $19, $20
            )
            ON CONFLICT (symbol, report_date) DO UPDATE SET
                company_name = COALESCE(EXCLUDED.company_name, earnings_calendar.company_name),
                time_slot = COALESCE(EXCLUDED.time_slot, earnings_calendar.time_slot),
                fiscal_quarter = COALESCE(EXCLUDED.fiscal_quarter, earnings_calendar.fiscal_quarter),
                eps_estimate = COALESCE(EXCLUDED.eps_estimate, earnings_calendar.eps_estimate),
                eps_actual = EXCLUDED.eps_actual,
                eps_surprise_pct = EXCLUDED.eps_surprise_pct,
                beat_eps = EXCLUDED.beat_eps,
                revenue_estimate = COALESCE(EXCLUDED.revenue_estimate, earnings_calendar.revenue_estimate),
                revenue_actual = EXCLUDED.revenue_actual,
                revenue_surprise_pct = EXCLUDED.revenue_surprise_pct,
                beat_revenue = EXCLUDED.beat_revenue,
                guidance_direction = EXCLUDED.guidance_direction,
                guidance_commentary = EXCLUDED.guidance_commentary,
                key_highlights = EXCLUDED.key_highlights,
                status = 'reported',
                source = EXCLUDED.source,
                grounding_sources = EXCLUDED.grounding_sources,
                confidence = EXCLUDED.confidence,
                updated_at = NOW()
        """
        
        await self.db.execute(
            query,
            earning.symbol.upper(),
            earning.company_name,
            date.fromisoformat(earning.report_date),
            earning.time_slot.upper() if earning.time_slot else 'TBD',
            earning.fiscal_quarter,
            earning.eps_estimate,
            earning.eps_actual,
            earning.eps_surprise_pct,
            earning.beat_eps,
            revenue_estimate,
            revenue_actual,
            earning.revenue_surprise_pct,
            earning.beat_revenue,
            earning.guidance_direction,
            earning.guidance_commentary,
            earning.key_highlights,
            'reported',
            'google_search',
            grounding_sources[:10] if grounding_sources else None,
            0.90  # Mayor confianza para resultados reportados
        )
    
    async def _get_scheduled_symbols(
        self,
        target_date: date,
        time_slot: Optional[str] = None
    ) -> List[str]:
        """Obtener símbolos programados para una fecha"""
        
        if time_slot:
            query = """
                SELECT symbol FROM earnings_calendar
                WHERE report_date = $1 AND time_slot = $2
            """
            rows = await self.db.fetch(query, target_date, time_slot.upper())
        else:
            query = """
                SELECT symbol FROM earnings_calendar
                WHERE report_date = $1
            """
            rows = await self.db.fetch(query, target_date)
        
        return [row['symbol'] for row in rows]
    
    # =========================================================================
    # HELPERS
    # =========================================================================
    
    def _extract_grounding_sources(self, response) -> List[str]:
        """Extraer URLs de las fuentes de grounding de Google Search"""
        sources = []
        try:
            if hasattr(response, 'candidates') and response.candidates:
                candidate = response.candidates[0]
                if hasattr(candidate, 'grounding_metadata') and candidate.grounding_metadata:
                    metadata = candidate.grounding_metadata
                    # Intentar obtener grounding_chunks
                    if hasattr(metadata, 'grounding_chunks') and metadata.grounding_chunks:
                        for chunk in metadata.grounding_chunks:
                            if hasattr(chunk, 'web') and chunk.web and hasattr(chunk.web, 'uri'):
                                sources.append(chunk.web.uri)
                    # También intentar search_entry_point si está disponible
                    if hasattr(metadata, 'search_entry_point') and metadata.search_entry_point:
                        if hasattr(metadata.search_entry_point, 'rendered_content'):
                            # El rendered_content puede contener URLs útiles
                            pass  # Por ahora solo logueamos que existe
        except Exception as e:
            # Solo loguear si es un error real, no si simplemente no hay metadata
            if "NoneType" not in str(e):
                logger.warning("grounding_extraction_error", error=str(e))
        
        return list(set(sources))  # Eliminar duplicados
    
    # =========================================================================
    # MAIN EXECUTE METHOD
    # =========================================================================
    
    async def execute(self, target_date: date, mode: str = "full") -> Dict[str, Any]:
        """
        Ejecutar la recopilación de earnings.
        
        Args:
            target_date: Fecha objetivo
            mode: 
                - "calendar": Solo calendario (scheduled)
                - "bmo": Solo resultados BMO
                - "amc": Solo resultados AMC
                - "full": Calendario + todos los resultados
                
        Returns:
            Dict con resultados consolidados
        """
        results = {
            "date": target_date.isoformat(),
            "mode": mode,
            "success": True,
            "calendar": None,
            "reported_bmo": None,
            "reported_amc": None
        }
        
        try:
            if mode in ("calendar", "full"):
                results["calendar"] = await self.collect_scheduled_earnings(target_date)
            
            if mode in ("bmo", "full"):
                results["reported_bmo"] = await self.collect_reported_earnings(target_date, "BMO")
            
            if mode in ("amc", "full"):
                results["reported_amc"] = await self.collect_reported_earnings(target_date, "AMC")
            
            # Verificar si todo fue exitoso
            for key in ["calendar", "reported_bmo", "reported_amc"]:
                if results[key] and not results[key].get("success", True):
                    results["success"] = False
                    break
            
            return results
            
        except Exception as e:
            logger.error("earnings_collector_execute_error", error=str(e))
            results["success"] = False
            results["error"] = str(e)
            return results


# =============================================================================
# CONVENIENCE FUNCTIONS
# =============================================================================

async def collect_earnings_for_today():
    """
    Función de conveniencia para recopilar earnings del día actual.
    Llamada por el scheduler.
    """
    from shared.utils.redis_client import RedisClient
    from shared.utils.timescale_client import TimescaleClient
    
    redis = RedisClient()
    db = TimescaleClient()
    
    try:
        await redis.connect()
        await db.connect()
        
        task = EarningsCollectorTask(redis, db)
        
        now_et = datetime.now(NY_TZ)
        today = now_et.date()
        
        # Determinar qué modo ejecutar según la hora
        hour = now_et.hour
        
        if hour < 9:
            # Antes de market open: calendario del día
            mode = "calendar"
        elif hour < 16:
            # Durante el día: actualizar con resultados BMO
            mode = "bmo"
        else:
            # Después del cierre: actualizar con resultados AMC
            mode = "amc"
        
        logger.info("🕐 collect_earnings_for_today", mode=mode, hour=hour)
        
        result = await task.execute(today, mode)
        
        return result
        
    finally:
        await db.disconnect()
        await redis.disconnect()


async def collect_earnings_calendar(target_date: date) -> Dict[str, Any]:
    """
    Recopilar solo el calendario de earnings para una fecha.
    """
    from shared.utils.redis_client import RedisClient
    from shared.utils.timescale_client import TimescaleClient
    
    redis = RedisClient()
    db = TimescaleClient()
    
    try:
        await redis.connect()
        await db.connect()
        
        task = EarningsCollectorTask(redis, db)
        return await task.collect_scheduled_earnings(target_date)
        
    finally:
        await db.disconnect()
        await redis.disconnect()


async def collect_earnings_results(target_date: date, time_slot: Optional[str] = None) -> Dict[str, Any]:
    """
    Recopilar resultados de earnings ya reportados.
    """
    from shared.utils.redis_client import RedisClient
    from shared.utils.timescale_client import TimescaleClient
    
    redis = RedisClient()
    db = TimescaleClient()
    
    try:
        await redis.connect()
        await db.connect()
        
        task = EarningsCollectorTask(redis, db)
        return await task.collect_reported_earnings(target_date, time_slot)
        
    finally:
        await db.disconnect()
        await redis.disconnect()
