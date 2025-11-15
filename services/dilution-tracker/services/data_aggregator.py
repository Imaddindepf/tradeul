"""
Data Aggregator Service
Orquesta la obtención, cálculo y persistencia de todos los datos
"""

import sys
sys.path.append('/app')

from typing import Optional, Dict, Any, List
from datetime import datetime, date
from decimal import Decimal

from shared.utils.timescale_client import TimescaleClient
from shared.utils.redis_client import RedisClient
from shared.utils.logger import get_logger
from shared.config.settings import settings

from services.polygon_financials import PolygonFinancialsService
from services.fmp_financials import FMPFinancialsService
from services.fmp_holders import FMPHoldersService
from services.fmp_filings import FMPFilingsService

from repositories.financial_repository import FinancialRepository
from repositories.holder_repository import HolderRepository
from repositories.filing_repository import FilingRepository

from calculators.cash_runway import CashRunwayCalculator
from calculators.dilution_calculator import DilutionCalculator
from calculators.risk_scorer import RiskScorer

logger = get_logger(__name__)


class DataAggregator:
    """
    Servicio principal que agrega todos los datos de un ticker
    """
    
    def __init__(
        self,
        db: TimescaleClient,
        redis: RedisClient
    ):
        self.db = db
        self.redis = redis
        
        # Inicializar servicios - Polygon como primary, FMP como fallback
        self.polygon_financials = PolygonFinancialsService(settings.POLYGON_API_KEY)
        self.fmp_financials = FMPFinancialsService(settings.FMP_API_KEY)
        self.fmp_holders = FMPHoldersService(settings.FMP_API_KEY)
        self.fmp_filings = FMPFilingsService(settings.FMP_API_KEY)
        
        # Inicializar repositories
        self.financial_repo = FinancialRepository(db)
        self.holder_repo = HolderRepository(db)
        self.filing_repo = FilingRepository(db)
        
        # Inicializar calculadores
        self.cash_calc = CashRunwayCalculator()
        self.dilution_calc = DilutionCalculator()
        self.risk_scorer = RiskScorer()
    
    async def get_ticker_analysis(
        self,
        ticker: str,
        force_refresh: bool = False
    ) -> Optional[Dict[str, Any]]:
        """
        Obtener análisis completo de un ticker
        
        Flujo:
        1. Verificar ticker existe en universo
        2. Buscar en cache
        3. Si no existe o force_refresh, buscar en BD
        4. Si BD vacía o vieja, fetch desde FMP + guardar
        5. Calcular métricas
        6. Cachear y retornar
        """
        try:
            ticker = ticker.upper()
            
            # 1. Verificar que ticker existe en universo
            ticker_exists = await self._validate_ticker(ticker)
            if not ticker_exists:
                logger.warning("ticker_not_in_universe", ticker=ticker)
                return None
            
            # 2. Intentar desde cache
            if not force_refresh:
                cached = await self._get_from_cache(ticker)
                if cached:
                    logger.info("cache_hit", ticker=ticker)
                    return cached
            
            # 3. Obtener o fetch datos
            summary = await self._get_or_fetch_summary(ticker)
            financials = await self._get_or_fetch_financials(ticker)
            holders = await self._get_or_fetch_holders(ticker)
            filings = await self._get_or_fetch_filings(ticker)
            
            if not summary:
                logger.warning("no_summary_data", ticker=ticker)
                return None
            
            # 4. Calcular métricas
            risk_scores = self._calculate_risk_scores(financials, filings)
            cash_runway = self._calculate_cash_runway(financials)
            dilution_history = self._calculate_dilution_history(financials)
            
            # 5. Construir respuesta con formato correcto
            # Formatear financials para frontend (últimos 20 quarters = ~5 años)
            formatted_financials = self._format_financials_for_response(financials[:20])
            
            analysis = {
                "summary": summary,
                "risk_scores": risk_scores,
                "cash_runway": cash_runway,
                "dilution_history": dilution_history,
                "holders": holders,
                "filings": filings[:50],  # Limitar a 50 más recientes
                "financials": formatted_financials,
            }
            
            # 6. Cachear
            await self._save_to_cache(ticker, analysis)
            
            logger.info("ticker_analysis_completed", ticker=ticker)
            return analysis
            
        except Exception as e:
            logger.error("get_ticker_analysis_failed", ticker=ticker, error=str(e))
            return None
    
    async def _validate_ticker(self, ticker: str) -> bool:
        """Verificar que ticker existe en ticker_metadata"""
        try:
            query = """
            SELECT 1 FROM ticker_metadata
            WHERE symbol = $1 AND is_actively_trading = TRUE
            LIMIT 1
            """
            result = await self.db.fetchval(query, ticker)
            return result is not None
        except Exception as e:
            logger.error("validate_ticker_failed", ticker=ticker, error=str(e))
            return False
    
    async def _get_from_cache(self, ticker: str) -> Optional[Dict]:
        """Obtener desde Redis cache"""
        try:
            key = f"dilution:analysis:{ticker}"
            return await self.redis.get(key)
        except Exception as e:
            logger.error("cache_get_failed", ticker=ticker, error=str(e))
            return None
    
    async def _save_to_cache(self, ticker: str, data: Dict, ttl: int = 3600):
        """Guardar en Redis cache (TTL: 1 hora)"""
        try:
            key = f"dilution:analysis:{ticker}"
            # Convertir Decimals a float para JSON serialization
            serializable_data = self._make_json_serializable(data)
            await self.redis.set(key, serializable_data, ttl=ttl)
        except Exception as e:
            logger.error("cache_save_failed", ticker=ticker, error=str(e))
    
    def _make_json_serializable(self, obj):
        """Convertir Decimals y otros tipos no serializables a JSON-safe"""
        if isinstance(obj, Decimal):
            return float(obj)
        elif isinstance(obj, dict):
            return {k: self._make_json_serializable(v) for k, v in obj.items()}
        elif isinstance(obj, list):
            return [self._make_json_serializable(item) for item in obj]
        elif isinstance(obj, date):
            return obj.isoformat()
        return obj
    
    async def _get_or_fetch_summary(self, ticker: str) -> Optional[Dict]:
        """Obtener summary desde ticker_metadata (ya existe)"""
        try:
            query = """
            SELECT 
                symbol as ticker,
                company_name,
                sector,
                industry,
                market_cap,
                float_shares,
                shares_outstanding,
                description,
                homepage_url,
                exchange,
                total_employees,
                list_date
            FROM ticker_metadata
            WHERE symbol = $1
            """
            
            result = await self.db.fetchrow(query, ticker)
            if not result:
                return None
            
            # Calcular institutional ownership desde holders
            inst_ownership_query = """
            SELECT SUM(ownership_percent) as total
            FROM institutional_holders
            WHERE ticker = $1
            AND report_date = (
                SELECT MAX(report_date)
                FROM institutional_holders
                WHERE ticker = $1
            )
            """
            inst_result = await self.db.fetchrow(inst_ownership_query, ticker)
            institutional_ownership = inst_result['total'] if inst_result else None
            
            return {
                **dict(result),
                "institutional_ownership": institutional_ownership
            }
            
        except Exception as e:
            logger.error("get_summary_failed", ticker=ticker, error=str(e))
            return None
    
    async def _get_or_fetch_financials(self, ticker: str) -> List[Dict]:
        """
        Obtener financials con estrategia dual:
        1. Try BD (si reciente)
        2. Try Polygon (primary source - más completo)
        3. Try FMP (fallback)
        """
        try:
            # Intentar desde BD
            db_financials = await self.financial_repo.get_by_ticker(ticker, limit=20)
            
            # Si tiene datos recientes (< 7 días), usar BD
            if db_financials:
                latest = db_financials[0]
                days_old = (datetime.now().date() - latest['period_date']).days
                
                if days_old < 7:
                    logger.debug("using_db_financials", ticker=ticker, source=latest.get('source'))
                    return db_financials
            
            # Try Polygon FIRST (más completo)
            logger.info("fetching_financials_from_polygon", ticker=ticker)
            polygon_financials = await self.polygon_financials.get_financial_statements(
                ticker,
                timeframe="quarterly",
                limit=20
            )
            
            if polygon_financials:
                logger.info(
                    "polygon_financials_success",
                    ticker=ticker,
                    count=len(polygon_financials)
                )
                # Guardar en BD
                await self.financial_repo.save_batch(polygon_financials)
                
                # Retornar desde BD
                return await self.financial_repo.get_by_ticker(ticker, limit=20)
            
            # Fallback a FMP si Polygon falla
            logger.warning("polygon_failed_trying_fmp", ticker=ticker)
            fmp_financials = await self.fmp_financials.get_financial_statements(
                ticker,
                period="quarter",
                limit=20
            )
            
            if fmp_financials:
                logger.info(
                    "fmp_financials_fallback_success",
                    ticker=ticker,
                    count=len(fmp_financials)
                )
                await self.financial_repo.save_batch(fmp_financials)
                return await self.financial_repo.get_by_ticker(ticker, limit=20)
            
            # Si ambos fallan, retornar lo que hay en BD (aunque viejo)
            if db_financials:
                logger.warning("using_stale_db_financials", ticker=ticker)
                return db_financials
            
            return []
            
        except Exception as e:
            logger.error("get_financials_failed", ticker=ticker, error=str(e))
            return []
    
    async def _get_or_fetch_holders(self, ticker: str) -> List[Dict]:
        """Obtener holders (BD o fetch desde FMP)"""
        try:
            # Intentar desde BD
            db_holders = await self.holder_repo.get_by_ticker(ticker)
            
            # Si tiene datos recientes (< 30 días), usar BD
            if db_holders:
                latest_date = db_holders[0]['report_date']
                days_old = (datetime.now().date() - latest_date).days
                
                if days_old < 30:
                    logger.debug("using_db_holders", ticker=ticker)
                    # Filtrar holders con shares_held = 0
                    filtered = [h for h in db_holders if h.get('shares_held', 0) > 0]
                    return filtered
            
            # Fetch desde FMP
            logger.info("fetching_holders_from_fmp", ticker=ticker)
            fmp_holders = await self.fmp_holders.get_institutional_holders(ticker)
            
            if fmp_holders:
                # Filtrar holders con shares = 0 ANTES de guardar
                fmp_holders = [h for h in fmp_holders if h.shares_held and h.shares_held > 0]
                
                if not fmp_holders:
                    logger.warning("no_valid_holders", ticker=ticker)
                    return []
                
                # Enriquecer con ownership %
                shares_outstanding = await self._get_shares_outstanding(ticker)
                if shares_outstanding:
                    fmp_holders = await self.fmp_holders.enrich_holders_with_ownership_pct(
                        fmp_holders,
                        shares_outstanding
                    )
                
                # Guardar en BD
                await self.holder_repo.save_batch(fmp_holders)
                
                result = await self.holder_repo.get_by_ticker(ticker)
                # Filtrar de nuevo por si acaso
                return [h for h in result if h.get('shares_held', 0) > 0]
            
            # Si BD tenía datos pero viejos, retornarlos filtrados
            if db_holders:
                return [h for h in db_holders if h.get('shares_held', 0) > 0]
            
            return []
            
        except Exception as e:
            logger.error("get_holders_failed", ticker=ticker, error=str(e))
            return []
    
    async def _get_or_fetch_filings(self, ticker: str) -> List[Dict]:
        """Obtener filings (BD o fetch desde FMP)"""
        try:
            # Intentar desde BD
            db_filings = await self.filing_repo.get_by_ticker(ticker, limit=100)
            
            # Si tiene datos recientes (< 7 días), usar BD
            if db_filings and len(db_filings) > 10:
                latest_date = db_filings[0]['filing_date']
                days_old = (datetime.now().date() - latest_date).days
                
                if days_old < 7:
                    logger.debug("using_db_filings", ticker=ticker)
                    return db_filings
            
            # Fetch desde FMP
            logger.info("fetching_filings_from_fmp", ticker=ticker)
            fmp_filings = await self.fmp_filings.get_sec_filings(ticker, limit=100)
            
            if fmp_filings:
                # Guardar en BD
                await self.filing_repo.save_batch(fmp_filings)
                
                return await self.filing_repo.get_by_ticker(ticker, limit=100)
            
            return db_filings or []
            
        except Exception as e:
            logger.error("get_filings_failed", ticker=ticker, error=str(e))
            return []
    
    async def _get_shares_outstanding(self, ticker: str) -> Optional[int]:
        """Obtener shares outstanding desde ticker_metadata"""
        try:
            query = "SELECT shares_outstanding FROM ticker_metadata WHERE symbol = $1"
            result = await self.db.fetchval(query, ticker)
            return result
        except:
            return None
    
    def _calculate_risk_scores(self, financials: List[Dict], filings: List[Dict]) -> Dict:
        """Calcular risk scores"""
        try:
            if not financials or len(financials) < 2:
                return {
                    "overall_risk_score": None,
                    "cash_need_score": None,
                    "dilution_risk_score": None,
                    "risk_level": "unknown"
                }
            
            # Cash runway metrics
            latest = financials[0]
            cash = latest.get('cash_and_equivalents') or 0
            investments = latest.get('short_term_investments') or 0
            total_cash = cash + investments
            
            # Burn rate
            cash_flows = [
                {'period_date': f['period_date'], 'operating_cash_flow': f.get('operating_cash_flow')}
                for f in financials[:4]
                if f.get('operating_cash_flow') is not None
            ]
            
            quarterly_burn = self.cash_calc.calculate_quarterly_burn_rate(cash_flows)
            
            runway_months = None
            if quarterly_burn:
                runway_months = self.cash_calc.calculate_runway(total_cash, quarterly_burn)
            
            # Dilution metrics
            dilution_data = self.dilution_calc.calculate_historical_dilution([
                {'period_date': f['period_date'], 'shares_outstanding': f.get('shares_outstanding')}
                for f in financials
                if f.get('shares_outstanding')
            ])
            
            # Count dilutive filings
            dilutive_count = len([f for f in filings if f.get('is_dilutive')])
            
            # Calculate scores
            cash_need_score = self.cash_calc.calculate_cash_need_score(
                runway_months,
                "stable",
                latest.get('current_ratio'),
                latest.get('debt_to_equity_ratio')
            )
            
            dilution_risk_score = self.dilution_calc.calculate_dilution_risk_score(
                dilution_data.get('dilution_pct_1y'),
                dilution_data.get('dilution_pct_2y'),
                dilutive_count,
                False  # TODO: Detectar active shelf
            )
            
            overall_risk_score = self.risk_scorer.calculate_overall_risk_score(
                cash_need_score,
                dilution_risk_score,
                latest.get('market_cap'),
                latest.get('float_shares'),
                dilutive_count
            )
            
            risk_level = self.risk_scorer.get_risk_level_label(overall_risk_score)
            
            return {
                "overall_risk_score": overall_risk_score,
                "cash_need_score": cash_need_score,
                "dilution_risk_score": dilution_risk_score,
                "risk_level": risk_level
            }
            
        except Exception as e:
            logger.error("calculate_risk_scores_failed", error=str(e))
            return {
                "overall_risk_score": None,
                "cash_need_score": None,
                "dilution_risk_score": None,
                "risk_level": "unknown"
            }
    
    def _calculate_cash_runway(self, financials: List[Dict]) -> Optional[Dict]:
        """Calcular cash runway"""
        try:
            if not financials:
                return None
            
            latest = financials[0]
            
            # Obtener cash - puede ser Decimal
            cash_value = latest.get('cash_and_equivalents')
            investments_value = latest.get('short_term_investments')
            
            cash = float(cash_value) if cash_value else 0
            investments = float(investments_value) if investments_value else 0
            total_cash = cash + investments
            
            # Si no hay cash ni investments, no podemos calcular runway
            if total_cash == 0:
                logger.warning("no_cash_data_for_runway", ticker=latest.get('ticker'))
                return None
            
            # Burn rate
            cash_flows = [
                {'period_date': f['period_date'], 'operating_cash_flow': f.get('operating_cash_flow')}
                for f in financials[:4]
                if f.get('operating_cash_flow') is not None
            ]
            
            quarterly_burn = self.cash_calc.calculate_quarterly_burn_rate(cash_flows)
            
            if not quarterly_burn:
                return None
            
            runway_months = self.cash_calc.calculate_runway(Decimal(str(total_cash)), quarterly_burn)
            
            # Si genera cash (burn positivo), runway es infinito y risk es low
            if quarterly_burn > 0 or runway_months is None:
                risk_level = "low"
            else:
                risk_level = self.cash_calc.get_runway_risk_level(runway_months)
            
            projection = self.cash_calc.project_cash_position(
                total_cash,
                quarterly_burn,
                months=12
            )
            
            # Build historical cash position (últimos quarters reales)
            cash_history = []
            for f in financials[:20]:  # Últimos 20 quarters
                cash_val = f.get('cash_and_equivalents')
                investments_val = f.get('short_term_investments')
                
                if cash_val or investments_val:
                    total = (float(cash_val) if cash_val else 0) + (float(investments_val) if investments_val else 0)
                    cash_history.append({
                        "date": f['period_date'].isoformat() if isinstance(f['period_date'], date) else str(f['period_date']),
                        "cash": total
                    })
            
            # Ordenar del más viejo al más nuevo para consistencia
            cash_history.sort(key=lambda x: x['date'])
            
            return {
                "current_cash": float(total_cash),
                "quarterly_burn_rate": float(quarterly_burn),
                "estimated_runway_months": float(runway_months) if runway_months else None,
                "runway_risk_level": risk_level,
                "projection": projection,
                "history": cash_history  # Nuevo: historial real
            }
            
        except Exception as e:
            logger.error("calculate_cash_runway_failed", error=str(e))
            return None
    
    def _calculate_dilution_history(self, financials: List[Dict]) -> Optional[Dict]:
        """Calcular dilution history"""
        try:
            if not financials:
                return None
            
            # Usar weighted_avg_shares_diluted (más preciso) o shares_outstanding como fallback
            financials_with_shares = []
            for f in financials:
                shares = (
                    f.get('weighted_avg_shares_diluted') or 
                    f.get('weighted_avg_shares_basic') or 
                    f.get('shares_outstanding')
                )
                if shares:
                    financials_with_shares.append({
                        'period_date': f['period_date'],
                        'shares_outstanding': shares
                    })
            
            if not financials_with_shares:
                logger.warning("no_shares_data_for_dilution")
                return None
            
            dilution_data = self.dilution_calc.calculate_historical_dilution(financials_with_shares)
            
            # Build history chart data
            history = [
                {
                    "date": f['period_date'].isoformat() if isinstance(f['period_date'], date) else str(f['period_date']),
                    "shares": f['shares_outstanding']
                }
                for f in reversed(financials_with_shares)
            ]
            
            return {
                "history": history,
                "dilution_1y": float(dilution_data.get('dilution_pct_1y')) if dilution_data.get('dilution_pct_1y') else None,
                "dilution_3y": float(dilution_data.get('dilution_pct_2y')) if dilution_data.get('dilution_pct_2y') else None,
            }
            
        except Exception as e:
            logger.error("calculate_dilution_history_failed", error=str(e))
            return None
    
    def _format_financials_for_response(self, financials: List[Dict]) -> List[Dict]:
        """
        Formatear financials para frontend con nombres esperados
        """
        formatted = []
        for f in financials:
            # Calcular total cash
            cash = f.get('cash_and_equivalents') or 0
            investments = f.get('short_term_investments') or 0
            total_cash = cash + investments if (cash or investments) else None
            
            # Calcular ratios si tenemos datos
            current_ratio = None
            if f.get('total_current_assets') and f.get('total_current_liabilities'):
                if f['total_current_liabilities'] != 0:
                    current_ratio = float(f['total_current_assets']) / float(f['total_current_liabilities'])
            
            debt_to_equity = None
            if f.get('total_debt') and f.get('stockholders_equity'):
                if f['stockholders_equity'] != 0:
                    debt_to_equity = float(f['total_debt']) / float(f['stockholders_equity'])
            
            formatted.append({
                "period_date": f['period_date'].isoformat() if hasattr(f['period_date'], 'isoformat') else str(f['period_date']),
                "period_type": f.get('period_type'),
                "fiscal_year": f.get('fiscal_year'),
                "cash": float(f['cash_and_equivalents']) if f.get('cash_and_equivalents') else None,
                "total_cash": float(total_cash) if total_cash else None,
                "debt": float(f['total_debt']) if f.get('total_debt') else None,
                "equity": float(f['stockholders_equity']) if f.get('stockholders_equity') else None,
                "revenue": float(f['revenue']) if f.get('revenue') else None,
                "net_income": float(f['net_income']) if f.get('net_income') else None,
                "operating_cash_flow": float(f['operating_cash_flow']) if f.get('operating_cash_flow') else None,
                "free_cash_flow": float(f['free_cash_flow']) if f.get('free_cash_flow') else None,
                "shares_outstanding": f.get('weighted_avg_shares_diluted') or f.get('weighted_avg_shares_basic') or f.get('shares_outstanding'),
                "current_ratio": round(current_ratio, 2) if current_ratio else None,
                "debt_to_equity_ratio": round(debt_to_equity, 2) if debt_to_equity else None,
            })
        
        return formatted

