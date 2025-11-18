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
from services.sec_dilution_service import SECDilutionService

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
        self.sec_dilution = SECDilutionService(db, redis)
        
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
            
            # 3.5. Obtener dilución SEC (warrants, ATM, shelfs, etc.)
            sec_dilution_profile = await self.sec_dilution.get_dilution_profile(ticker, force_refresh=force_refresh)
            sec_dilution_data = None
            if sec_dilution_profile:
                # Convertir a dict para JSON serialization (Pydantic v2)
                try:
                    # Intentar model_dump (Pydantic v2)
                    sec_dilution_data = sec_dilution_profile.model_dump()
                    # Convertir Decimal a float y date a string
                    sec_dilution_data = self._make_json_serializable(sec_dilution_data)
                    # Agregar análisis de dilución
                    sec_dilution_data["dilution_analysis"] = sec_dilution_profile.calculate_potential_dilution()
                except AttributeError:
                    # Fallback a dict() (Pydantic v1)
                    sec_dilution_data = {
                        "ticker": sec_dilution_profile.ticker,
                        "company_name": sec_dilution_profile.company_name,
                        "cik": sec_dilution_profile.cik,
                        "warrants": [w.model_dump() if hasattr(w, 'model_dump') else w.dict() for w in sec_dilution_profile.warrants],
                        "atm_offerings": [a.model_dump() if hasattr(a, 'model_dump') else a.dict() for a in sec_dilution_profile.atm_offerings],
                        "shelf_registrations": [s.model_dump() if hasattr(s, 'model_dump') else s.dict() for s in sec_dilution_profile.shelf_registrations],
                        "completed_offerings": [c.model_dump() if hasattr(c, 'model_dump') else c.dict() for c in sec_dilution_profile.completed_offerings],
                        "s1_offerings": [s1.model_dump() if hasattr(s1, 'model_dump') else s1.dict() for s1 in sec_dilution_profile.s1_offerings],
                        "convertible_notes": [cn.model_dump() if hasattr(cn, 'model_dump') else cn.dict() for cn in sec_dilution_profile.convertible_notes],
                        "convertible_preferred": [cp.model_dump() if hasattr(cp, 'model_dump') else cp.dict() for cp in sec_dilution_profile.convertible_preferred],
                        "equity_lines": [el.model_dump() if hasattr(el, 'model_dump') else el.dict() for el in sec_dilution_profile.equity_lines],
                        "current_price": float(sec_dilution_profile.current_price) if sec_dilution_profile.current_price else None,
                        "shares_outstanding": sec_dilution_profile.shares_outstanding,
                        "float_shares": sec_dilution_profile.float_shares,
                        "dilution_analysis": sec_dilution_profile.calculate_potential_dilution(),
                        "last_scraped_at": sec_dilution_profile.metadata.last_scraped_at.isoformat() if sec_dilution_profile.metadata.last_scraped_at else None
                    }
                    sec_dilution_data = self._make_json_serializable(sec_dilution_data)
            
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
                "dilution": sec_dilution_data,  # Agregar dilución SEC
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
                "dilution_3y": float(dilution_data.get('dilution_pct_3y')) if dilution_data.get('dilution_pct_3y') else None,
                "dilution_5y": float(dilution_data.get('dilution_pct_5y')) if dilution_data.get('dilution_pct_5y') else None,
            }
            
        except Exception as e:
            logger.error("calculate_dilution_history_failed", error=str(e))
            return None
    
    def _format_financials_for_response(self, financials: List[Dict]) -> List[Dict]:
        """
        Formatear financials para frontend con TODOS los campos disponibles
        """
        formatted = []
        for f in financials:
            # Calcular total cash
            cash = f.get('cash_and_equivalents') or 0
            investments = f.get('short_term_investments') or 0
            total_cash = cash + investments if (cash or investments) else None
            
            # Calcular ratios
            current_ratio = None
            if f.get('total_current_assets') and f.get('total_current_liabilities'):
                if f['total_current_liabilities'] != 0:
                    current_ratio = float(f['total_current_assets']) / float(f['total_current_liabilities'])
            
            debt_to_equity = None
            if f.get('total_debt') and f.get('stockholders_equity'):
                if f['stockholders_equity'] != 0:
                    debt_to_equity = float(f['total_debt']) / float(f['stockholders_equity'])
            
            working_capital = None
            if f.get('total_current_assets') is not None and f.get('total_current_liabilities') is not None:
                working_capital = float(f['total_current_assets']) - float(f['total_current_liabilities'])
            
            formatted.append({
                "period_date": f['period_date'].isoformat() if hasattr(f['period_date'], 'isoformat') else str(f['period_date']),
                "period_type": f.get('period_type'),
                "fiscal_year": f.get('fiscal_year'),
                
                # Balance Sheet - Assets (SUPER COMPLETO)
                "total_assets": float(f['total_assets']) if f.get('total_assets') else None,
                "total_current_assets": float(f['total_current_assets']) if f.get('total_current_assets') else None,
                "cash_and_equivalents": float(f['cash_and_equivalents']) if f.get('cash_and_equivalents') else None,
                "short_term_investments": float(f['short_term_investments']) if f.get('short_term_investments') else None,
                "total_cash": float(total_cash) if total_cash else None,
                "receivables": float(f['receivables']) if f.get('receivables') else None,
                "inventories": float(f['inventories']) if f.get('inventories') else None,
                "other_current_assets": float(f['other_current_assets']) if f.get('other_current_assets') else None,
                "property_plant_equipment_net": float(f['property_plant_equipment_net']) if f.get('property_plant_equipment_net') else None,
                "goodwill": float(f['goodwill']) if f.get('goodwill') else None,
                "intangible_assets_net": float(f['intangible_assets_net']) if f.get('intangible_assets_net') else None,
                "other_noncurrent_assets": float(f['other_noncurrent_assets']) if f.get('other_noncurrent_assets') else None,
                
                # Balance Sheet - Liabilities (SUPER COMPLETO)
                "total_liabilities": float(f['total_liabilities']) if f.get('total_liabilities') else None,
                "total_current_liabilities": float(f['total_current_liabilities']) if f.get('total_current_liabilities') else None,
                "accounts_payable": float(f['accounts_payable']) if f.get('accounts_payable') else None,
                "debt_current": float(f['debt_current']) if f.get('debt_current') else None,
                "accrued_liabilities": float(f['accrued_liabilities']) if f.get('accrued_liabilities') else None,
                "deferred_revenue_current": float(f['deferred_revenue_current']) if f.get('deferred_revenue_current') else None,
                "long_term_debt": float(f['long_term_debt']) if f.get('long_term_debt') else None,
                "other_noncurrent_liabilities": float(f['other_noncurrent_liabilities']) if f.get('other_noncurrent_liabilities') else None,
                "total_debt": float(f['total_debt']) if f.get('total_debt') else None,
                
                # Balance Sheet - Equity (SUPER COMPLETO)
                "stockholders_equity": float(f['stockholders_equity']) if f.get('stockholders_equity') else None,
                "common_stock": float(f['common_stock']) if f.get('common_stock') else None,
                "additional_paid_in_capital": float(f['additional_paid_in_capital']) if f.get('additional_paid_in_capital') else None,
                "treasury_stock": float(f['treasury_stock']) if f.get('treasury_stock') else None,
                "retained_earnings": float(f['retained_earnings']) if f.get('retained_earnings') else None,
                "accumulated_other_comprehensive_income": float(f['accumulated_other_comprehensive_income']) if f.get('accumulated_other_comprehensive_income') else None,
                
                # Income Statement (SUPER COMPLETO)
                "revenue": float(f['revenue']) if f.get('revenue') else None,
                "cost_of_revenue": float(f['cost_of_revenue']) if f.get('cost_of_revenue') else None,
                "gross_profit": float(f['gross_profit']) if f.get('gross_profit') else None,
                "research_development": float(f['research_development']) if f.get('research_development') else None,
                "selling_general_administrative": float(f['selling_general_administrative']) if f.get('selling_general_administrative') else None,
                "other_operating_expenses": float(f['other_operating_expenses']) if f.get('other_operating_expenses') else None,
                "total_operating_expenses": float(f['total_operating_expenses']) if f.get('total_operating_expenses') else None,
                "operating_income": float(f['operating_income']) if f.get('operating_income') else None,
                "interest_expense": float(f['interest_expense']) if f.get('interest_expense') else None,
                "interest_income": float(f['interest_income']) if f.get('interest_income') else None,
                "other_income_expense": float(f['other_income_expense']) if f.get('other_income_expense') else None,
                "income_before_taxes": float(f['income_before_taxes']) if f.get('income_before_taxes') else None,
                "income_taxes": float(f['income_taxes']) if f.get('income_taxes') else None,
                "net_income": float(f['net_income']) if f.get('net_income') else None,
                "eps_basic": float(f['eps_basic']) if f.get('eps_basic') else None,
                "eps_diluted": float(f['eps_diluted']) if f.get('eps_diluted') else None,
                "ebitda": float(f['ebitda']) if f.get('ebitda') else None,
                
                # Cash Flow Statement (SUPER COMPLETO)
                "operating_cash_flow": float(f['operating_cash_flow']) if f.get('operating_cash_flow') else None,
                "depreciation_amortization": float(f['depreciation_amortization']) if f.get('depreciation_amortization') else None,
                "stock_based_compensation": float(f['stock_based_compensation']) if f.get('stock_based_compensation') else None,
                "change_in_working_capital": float(f['change_in_working_capital']) if f.get('change_in_working_capital') else None,
                "other_operating_activities": float(f['other_operating_activities']) if f.get('other_operating_activities') else None,
                "investing_cash_flow": float(f['investing_cash_flow']) if f.get('investing_cash_flow') else None,
                "capital_expenditures": float(f['capital_expenditures']) if f.get('capital_expenditures') else None,
                "acquisitions": float(f['acquisitions']) if f.get('acquisitions') else None,
                "other_investing_activities": float(f['other_investing_activities']) if f.get('other_investing_activities') else None,
                "financing_cash_flow": float(f['financing_cash_flow']) if f.get('financing_cash_flow') else None,
                "debt_issuance_repayment": float(f['debt_issuance_repayment']) if f.get('debt_issuance_repayment') else None,
                "dividends_paid": float(f['dividends_paid']) if f.get('dividends_paid') else None,
                "stock_repurchased": float(f['stock_repurchased']) if f.get('stock_repurchased') else None,
                "other_financing_activities": float(f['other_financing_activities']) if f.get('other_financing_activities') else None,
                "change_in_cash": float(f['change_in_cash']) if f.get('change_in_cash') else None,
                "free_cash_flow": float(f['free_cash_flow']) if f.get('free_cash_flow') else None,
                
                # Shares
                "shares_outstanding": f.get('shares_outstanding'),
                "weighted_avg_shares_basic": f.get('weighted_avg_shares_basic'),
                "weighted_avg_shares_diluted": f.get('weighted_avg_shares_diluted'),
                
                # Ratios y Métricas
                "current_ratio": round(current_ratio, 2) if current_ratio else None,
                "debt_to_equity_ratio": round(debt_to_equity, 2) if debt_to_equity else None,
                "working_capital": round(working_capital, 2) if working_capital else None,
            })
        
        return formatted

