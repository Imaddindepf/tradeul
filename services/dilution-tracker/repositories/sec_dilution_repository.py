"""
SEC Dilution Repository
Acceso a datos de dilución SEC en PostgreSQL
"""

import sys
sys.path.append('/app')

import json
from typing import Optional, List, Dict, Any
from datetime import datetime, date

from shared.utils.timescale_client import TimescaleClient
from shared.utils.logger import get_logger
from models.sec_dilution_models import (
    SECDilutionProfile,
    WarrantModel,
    ATMOfferingModel,
    ShelfRegistrationModel,
    CompletedOfferingModel,
    S1OfferingModel,
    ConvertibleNoteModel,
    ConvertiblePreferredModel,
    EquityLineModel,
    DilutionProfileMetadata
)

logger = get_logger(__name__)


class SECDilutionRepository:
    """Repository para operaciones de SEC dilution profiles"""
    
    def __init__(self, db: TimescaleClient):
        self.db = db
    
    async def get_profile(self, ticker: str) -> Optional[SECDilutionProfile]:
        """
        Obtener perfil completo de dilución para un ticker
        
        Args:
            ticker: Ticker symbol
            
        Returns:
            SECDilutionProfile o None si no existe
        """
        try:
            ticker = ticker.upper()
            
            # 1. Obtener profile principal
            profile_query = """
            SELECT 
                ticker, cik, company_name, current_price, 
                shares_outstanding, free_float,
                last_scraped_at, source_filings, 
                scrape_success, scrape_error
            FROM sec_dilution_profiles
            WHERE ticker = $1
            """
            
            profile_row = await self.db.fetchrow(profile_query, ticker)
            
            if not profile_row:
                return None
            
            # 2. Obtener warrants
            warrants = await self._get_warrants(ticker)
            
            # 3. Obtener ATM offerings
            atm_offerings = await self._get_atm_offerings(ticker)
            
            # 4. Obtener shelf registrations
            shelf_registrations = await self._get_shelf_registrations(ticker)
            
            # 5. Obtener completed offerings
            completed_offerings = await self._get_completed_offerings(ticker)
            
            # 6. Obtener nuevos tipos (si existen tablas)
            s1_offerings = await self._get_s1_offerings(ticker)
            convertible_notes = await self._get_convertible_notes(ticker)
            convertible_preferred = await self._get_convertible_preferred(ticker)
            equity_lines = await self._get_equity_lines(ticker)
            
            # 7. Construir metadata
            # Parsear source_filings si viene como string JSON
            source_filings_raw = profile_row['source_filings']
            if isinstance(source_filings_raw, str):
                try:
                    source_filings = json.loads(source_filings_raw) if source_filings_raw else []
                except json.JSONDecodeError:
                    source_filings = []
            else:
                source_filings = source_filings_raw or []
            
            metadata = DilutionProfileMetadata(
                ticker=profile_row['ticker'],
                cik=profile_row['cik'],
                company_name=profile_row['company_name'],
                last_scraped_at=profile_row['last_scraped_at'],
                source_filings=source_filings,
                scrape_success=profile_row['scrape_success'],
                scrape_error=profile_row['scrape_error']
            )
            
            # 8. Construir profile completo
            profile = SECDilutionProfile(
                ticker=profile_row['ticker'],
                company_name=profile_row['company_name'],
                cik=profile_row['cik'],
                current_price=profile_row['current_price'],
                shares_outstanding=profile_row['shares_outstanding'],
                free_float=profile_row['free_float'],
                warrants=warrants,
                atm_offerings=atm_offerings,
                shelf_registrations=shelf_registrations,
                completed_offerings=completed_offerings,
                s1_offerings=s1_offerings,
                convertible_notes=convertible_notes,
                convertible_preferred=convertible_preferred,
                equity_lines=equity_lines,
                metadata=metadata
            )
            
            return profile
            
        except Exception as e:
            logger.error("get_profile_failed", ticker=ticker, error=str(e))
            return None
    
    async def save_profile(self, profile: SECDilutionProfile) -> bool:
        """
        Guardar perfil completo (insert o update)
        
        Args:
            profile: SECDilutionProfile completo
            
        Returns:
            True si se guardó correctamente
        """
        try:
            ticker = profile.ticker.upper()
            
            # 1. Upsert profile principal
            profile_query = """
            INSERT INTO sec_dilution_profiles (
                ticker, cik, company_name, current_price,
                shares_outstanding, free_float,
                last_scraped_at, source_filings,
                scrape_success, scrape_error
            )
            VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10)
            ON CONFLICT (ticker) DO UPDATE SET
                cik = EXCLUDED.cik,
                company_name = EXCLUDED.company_name,
                current_price = EXCLUDED.current_price,
                shares_outstanding = EXCLUDED.shares_outstanding,
                free_float = EXCLUDED.free_float,
                last_scraped_at = EXCLUDED.last_scraped_at,
                source_filings = EXCLUDED.source_filings,
                scrape_success = EXCLUDED.scrape_success,
                scrape_error = EXCLUDED.scrape_error,
                updated_at = NOW()
            """
            
            import json as json_module
            
            await self.db.execute(
                profile_query,
                ticker,
                profile.cik,
                profile.company_name,
                profile.current_price,
                profile.shares_outstanding,
                profile.free_float,
                profile.metadata.last_scraped_at,
                json_module.dumps(profile.metadata.source_filings),
                profile.metadata.scrape_success,
                profile.metadata.scrape_error
            )
            
            # 2. Borrar datos existentes de este ticker
            await self._delete_ticker_data(ticker)
            
            # 3. Insertar warrants
            for warrant in profile.warrants:
                await self._insert_warrant(ticker, warrant)
            
            # 4. Insertar ATM offerings
            for atm in profile.atm_offerings:
                await self._insert_atm_offering(ticker, atm)
            
            # 5. Insertar shelf registrations
            for shelf in profile.shelf_registrations:
                await self._insert_shelf_registration(ticker, shelf)
            
            # 6. Insertar completed offerings
            for offering in profile.completed_offerings:
                await self._insert_completed_offering(ticker, offering)
            
            # 7. Insertar nuevos tipos (si existen)
            for s1 in profile.s1_offerings:
                await self._insert_s1_offering(ticker, s1)
            
            for cn in profile.convertible_notes:
                await self._insert_convertible_note(ticker, cn)
            
            for cp in profile.convertible_preferred:
                await self._insert_convertible_preferred(ticker, cp)
            
            for el in profile.equity_lines:
                await self._insert_equity_line(ticker, el)
            
            logger.info("save_profile_success", ticker=ticker)
            return True
            
        except Exception as e:
            logger.error("save_profile_failed", ticker=ticker, error=str(e))
            return False
    
    async def profile_exists(self, ticker: str) -> bool:
        """Verificar si existe un profile para el ticker"""
        try:
            query = "SELECT 1 FROM sec_dilution_profiles WHERE ticker = $1"
            result = await self.db.fetchval(query, ticker.upper())
            return result is not None
        except Exception as e:
            logger.error("profile_exists_check_failed", ticker=ticker, error=str(e))
            return False
    
    async def delete_profile(self, ticker: str) -> bool:
        """Borrar profile completo (cascade delete)"""
        try:
            query = "DELETE FROM sec_dilution_profiles WHERE ticker = $1"
            await self.db.execute(query, ticker.upper())
            logger.info("delete_profile_success", ticker=ticker)
            return True
        except Exception as e:
            logger.error("delete_profile_failed", ticker=ticker, error=str(e))
            return False
    
    # ========================================================================
    # MÉTODOS PRIVADOS
    # ========================================================================
    
    async def _get_warrants(self, ticker: str) -> List[WarrantModel]:
        """Obtener warrants de un ticker con todos los campos incluido lifecycle v5"""
        # Query con todos los campos nuevos de lifecycle
        query = """
        SELECT id, ticker, series_name, issue_date, outstanding, exercise_price,
               expiration_date, potential_new_shares, notes,
               status, is_summary_row, exclude_from_dilution, imputed_fields,
               split_adjusted, split_factor, original_exercise_price, original_outstanding,
               total_issued, exercised, expired, remaining, last_update_date,
               known_owners, underwriter_agent, price_protection, pp_clause,
               exercisable_date, is_registered, registration_type, is_prefunded,
               has_cashless_exercise, warrant_coverage_ratio, anti_dilution_provision,
               source_filing, filing_url,
               -- v5 lifecycle fields
               warrant_type, underlying_type,
               ownership_blocker_pct, blocker_clause,
               potential_proceeds, actual_proceeds_to_date,
               warrant_agreement_exhibit, warrant_agreement_url,
               replaced_by_id, replaces_id, amendment_of_id,
               has_alternate_cashless, forced_exercise_provision,
               forced_exercise_price, forced_exercise_days,
               price_adjustment_count, original_issue_price, last_price_adjustment_date,
               exercise_events_count, last_exercise_date, last_exercise_quantity
        FROM sec_warrants
        WHERE ticker = $1
        ORDER BY expiration_date DESC NULLS LAST
        """
        
        try:
            rows = await self.db.fetch(query, ticker)
        except Exception:
            # Fallback sin campos nuevos de lifecycle v5 (para backwards compatibility)
            logger.debug("warrant_query_fallback_no_lifecycle", ticker=ticker)
            return await self._get_warrants_legacy(ticker)
        
        return [
            WarrantModel(
                id=row['id'],
                ticker=row['ticker'],
                series_name=row.get('series_name'),
                issue_date=row['issue_date'],
                outstanding=row['outstanding'],
                exercise_price=row['exercise_price'],
                expiration_date=row['expiration_date'],
                potential_new_shares=row['potential_new_shares'],
                notes=row['notes'],
                status=row.get('status'),
                is_summary_row=row.get('is_summary_row'),
                exclude_from_dilution=row.get('exclude_from_dilution'),
                imputed_fields=row.get('imputed_fields', '').split(',') if row.get('imputed_fields') else None,
                split_adjusted=row.get('split_adjusted'),
                split_factor=row.get('split_factor'),
                original_exercise_price=row.get('original_exercise_price'),
                original_outstanding=row.get('original_outstanding'),
                total_issued=row.get('total_issued'),
                exercised=row.get('exercised'),
                expired=row.get('expired'),
                remaining=row.get('remaining'),
                last_update_date=row.get('last_update_date'),
                known_owners=row.get('known_owners'),
                underwriter_agent=row.get('underwriter_agent'),
                price_protection=row.get('price_protection'),
                pp_clause=row.get('pp_clause'),
                exercisable_date=row.get('exercisable_date'),
                is_registered=row.get('is_registered'),
                registration_type=row.get('registration_type'),
                is_prefunded=row.get('is_prefunded'),
                has_cashless_exercise=row.get('has_cashless_exercise'),
                warrant_coverage_ratio=row.get('warrant_coverage_ratio'),
                anti_dilution_provision=row.get('anti_dilution_provision'),
                source_filing=row.get('source_filing'),
                filing_url=row.get('filing_url'),
                # v5 lifecycle fields
                warrant_type=row.get('warrant_type'),
                underlying_type=row.get('underlying_type'),
                ownership_blocker_pct=row.get('ownership_blocker_pct'),
                blocker_clause=row.get('blocker_clause'),
                potential_proceeds=row.get('potential_proceeds'),
                actual_proceeds_to_date=row.get('actual_proceeds_to_date'),
                warrant_agreement_exhibit=row.get('warrant_agreement_exhibit'),
                warrant_agreement_url=row.get('warrant_agreement_url'),
                replaced_by_id=row.get('replaced_by_id'),
                replaces_id=row.get('replaces_id'),
                amendment_of_id=row.get('amendment_of_id'),
                has_alternate_cashless=row.get('has_alternate_cashless'),
                forced_exercise_provision=row.get('forced_exercise_provision'),
                forced_exercise_price=row.get('forced_exercise_price'),
                forced_exercise_days=row.get('forced_exercise_days'),
                price_adjustment_count=row.get('price_adjustment_count'),
                original_issue_price=row.get('original_issue_price'),
                last_price_adjustment_date=row.get('last_price_adjustment_date'),
                exercise_events_count=row.get('exercise_events_count'),
                last_exercise_date=row.get('last_exercise_date'),
                last_exercise_quantity=row.get('last_exercise_quantity')
            )
            for row in rows
        ]
    
    async def _get_warrants_legacy(self, ticker: str) -> List[WarrantModel]:
        """Fallback para obtener warrants sin campos v5 lifecycle"""
        query = """
        SELECT id, ticker, issue_date, outstanding, exercise_price,
               expiration_date, potential_new_shares, notes,
               status, is_summary_row, exclude_from_dilution, imputed_fields,
               split_adjusted, split_factor, original_exercise_price, original_outstanding,
               total_issued, exercised, expired, remaining, last_update_date
        FROM sec_warrants
        WHERE ticker = $1
        ORDER BY expiration_date DESC NULLS LAST
        """
        
        rows = await self.db.fetch(query, ticker)
        
        return [
            WarrantModel(
                id=row['id'],
                ticker=row['ticker'],
                issue_date=row['issue_date'],
                outstanding=row['outstanding'],
                exercise_price=row['exercise_price'],
                expiration_date=row['expiration_date'],
                potential_new_shares=row['potential_new_shares'],
                notes=row['notes'],
                status=row.get('status'),
                is_summary_row=row.get('is_summary_row'),
                exclude_from_dilution=row.get('exclude_from_dilution'),
                imputed_fields=row.get('imputed_fields', '').split(',') if row.get('imputed_fields') else None,
                split_adjusted=row.get('split_adjusted'),
                split_factor=row.get('split_factor'),
                original_exercise_price=row.get('original_exercise_price'),
                original_outstanding=row.get('original_outstanding'),
                total_issued=row.get('total_issued'),
                exercised=row.get('exercised'),
                expired=row.get('expired'),
                remaining=row.get('remaining'),
                last_update_date=row.get('last_update_date')
            )
            for row in rows
        ]
    
    async def _get_atm_offerings(self, ticker: str) -> List[ATMOfferingModel]:
        """Obtener ATM offerings de un ticker"""
        try:
            query = """
            SELECT id, ticker, total_capacity, remaining_capacity,
                   placement_agent, status, agreement_start_date,
                   filing_date, filing_url, potential_shares_at_current_price, notes
            FROM sec_atm_offerings
            WHERE ticker = $1
            ORDER BY filing_date DESC NULLS LAST
            """
            rows = await self.db.fetch(query, ticker)
            return [
                ATMOfferingModel(
                    id=row['id'],
                    ticker=row['ticker'],
                    total_capacity=row['total_capacity'],
                    remaining_capacity=row['remaining_capacity'],
                    placement_agent=row['placement_agent'],
                    status=row.get('status'),
                    agreement_start_date=row.get('agreement_start_date'),
                    filing_date=row['filing_date'],
                    filing_url=row['filing_url'],
                    potential_shares_at_current_price=row['potential_shares_at_current_price'],
                    notes=row.get('notes')
                )
                for row in rows
            ]
        except Exception:
            # Si las columnas nuevas no existen, usar query sin ellas
            query = """
            SELECT id, ticker, total_capacity, remaining_capacity,
                   placement_agent, filing_date, filing_url,
                   potential_shares_at_current_price
            FROM sec_atm_offerings
            WHERE ticker = $1
            ORDER BY filing_date DESC NULLS LAST
            """
            rows = await self.db.fetch(query, ticker)
            return [
                ATMOfferingModel(
                    id=row['id'],
                    ticker=row['ticker'],
                    total_capacity=row['total_capacity'],
                    remaining_capacity=row['remaining_capacity'],
                    placement_agent=row['placement_agent'],
                    filing_date=row['filing_date'],
                    filing_url=row['filing_url'],
                    potential_shares_at_current_price=row['potential_shares_at_current_price']
                )
                for row in rows
            ]
    
    async def _get_shelf_registrations(self, ticker: str) -> List[ShelfRegistrationModel]:
        """Obtener shelf registrations de un ticker"""
        try:
            query = """
            SELECT id, ticker, total_capacity, remaining_capacity,
                   current_raisable_amount, total_amount_raised, total_amount_raised_last_12mo,
                   is_baby_shelf, baby_shelf_restriction, security_type,
                   filing_date, effect_date, registration_statement,
                   filing_url, expiration_date, last_banker, notes
            FROM sec_shelf_registrations
            WHERE ticker = $1
            ORDER BY filing_date DESC NULLS LAST
            """
            rows = await self.db.fetch(query, ticker)
            return [
                ShelfRegistrationModel(
                    id=row['id'],
                    ticker=row['ticker'],
                    total_capacity=row['total_capacity'],
                    remaining_capacity=row['remaining_capacity'],
                    current_raisable_amount=row.get('current_raisable_amount'),
                    total_amount_raised=row.get('total_amount_raised'),
                    total_amount_raised_last_12mo=row.get('total_amount_raised_last_12mo'),
                    is_baby_shelf=row['is_baby_shelf'],
                    baby_shelf_restriction=row.get('baby_shelf_restriction'),
                    security_type=row.get('security_type'),
                    filing_date=row['filing_date'],
                    effect_date=row.get('effect_date'),
                    registration_statement=row['registration_statement'],
                    filing_url=row['filing_url'],
                    expiration_date=row['expiration_date'],
                    last_banker=row.get('last_banker'),
                    notes=row.get('notes')
                )
                for row in rows
            ]
        except Exception:
            # Si las columnas nuevas no existen, usar query sin ellas
            query = """
            SELECT id, ticker, total_capacity, remaining_capacity,
                   is_baby_shelf, security_type, filing_date, registration_statement,
                   filing_url, expiration_date
            FROM sec_shelf_registrations
            WHERE ticker = $1
            ORDER BY filing_date DESC NULLS LAST
            """
            rows = await self.db.fetch(query, ticker)
            return [
                ShelfRegistrationModel(
                    id=row['id'],
                    ticker=row['ticker'],
                    total_capacity=row['total_capacity'],
                    remaining_capacity=row['remaining_capacity'],
                    is_baby_shelf=row['is_baby_shelf'],
                    security_type=row.get('security_type'),
                    filing_date=row['filing_date'],
                    registration_statement=row['registration_statement'],
                    filing_url=row['filing_url'],
                    expiration_date=row['expiration_date']
                )
                for row in rows
            ]
    
    async def _get_completed_offerings(self, ticker: str) -> List[CompletedOfferingModel]:
        """Obtener completed offerings de un ticker"""
        query = """
        SELECT id, ticker, offering_type, shares_issued,
               price_per_share, amount_raised, offering_date,
               filing_url, notes
        FROM sec_completed_offerings
        WHERE ticker = $1
        ORDER BY offering_date DESC NULLS LAST
        """
        
        rows = await self.db.fetch(query, ticker)
        
        return [
            CompletedOfferingModel(
                id=row['id'],
                ticker=row['ticker'],
                offering_type=row['offering_type'],
                shares_issued=row['shares_issued'],
                price_per_share=row['price_per_share'],
                amount_raised=row['amount_raised'],
                offering_date=row['offering_date'],
                filing_url=row['filing_url'],
                notes=row['notes']
            )
            for row in rows
        ]
    
    async def _get_s1_offerings(self, ticker: str) -> List[S1OfferingModel]:
        """Obtener S-1 offerings de un ticker (si existe tabla)"""
        try:
            query = """
            SELECT id, ticker, anticipated_deal_size, final_deal_size, final_pricing,
                   final_shares_offered, warrant_coverage, final_warrant_coverage,
                   exercise_price, underwriter_agent, s1_filing_date, status,
                   filing_url, last_update_date
            FROM sec_s1_offerings
            WHERE ticker = $1
            ORDER BY s1_filing_date DESC NULLS LAST
            """
            rows = await self.db.fetch(query, ticker)
            return [
                S1OfferingModel(
                    id=row['id'],
                    ticker=row['ticker'],
                    anticipated_deal_size=row['anticipated_deal_size'],
                    final_deal_size=row['final_deal_size'],
                    final_pricing=row['final_pricing'],
                    final_shares_offered=row['final_shares_offered'],
                    warrant_coverage=row['warrant_coverage'],
                    final_warrant_coverage=row['final_warrant_coverage'],
                    exercise_price=row['exercise_price'],
                    underwriter_agent=row['underwriter_agent'],
                    s1_filing_date=row['s1_filing_date'],
                    status=row['status'],
                    filing_url=row['filing_url'],
                    last_update_date=row['last_update_date']
                )
                for row in rows
            ]
        except Exception:
            # Tabla no existe aún, devolver vacío
            return []
    
    async def _get_convertible_notes(self, ticker: str) -> List[ConvertibleNoteModel]:
        """Obtener convertible notes de un ticker con todos los campos"""
        try:
            query = """
            SELECT id, ticker, series_name, total_principal_amount, remaining_principal_amount,
                   conversion_price, original_conversion_price, conversion_ratio,
                   total_shares_when_converted, remaining_shares_when_converted,
                   interest_rate, issue_date, convertible_date, maturity_date, 
                   underwriter_agent, filing_url, notes,
                   is_registered, registration_type, known_owners,
                   price_protection, pp_clause, variable_rate_adjustment,
                   floor_price, is_toxic, last_update_date
            FROM sec_convertible_notes
            WHERE ticker = $1
            ORDER BY issue_date DESC NULLS LAST
            """
            rows = await self.db.fetch(query, ticker)
            return [
                ConvertibleNoteModel(
                    id=row['id'],
                    ticker=row['ticker'],
                    series_name=row['series_name'],
                    total_principal_amount=row['total_principal_amount'],
                    remaining_principal_amount=row['remaining_principal_amount'],
                    conversion_price=row['conversion_price'],
                    original_conversion_price=row['original_conversion_price'],
                    conversion_ratio=row['conversion_ratio'],
                    total_shares_when_converted=row['total_shares_when_converted'],
                    remaining_shares_when_converted=row['remaining_shares_when_converted'],
                    interest_rate=row['interest_rate'],
                    issue_date=row['issue_date'],
                    convertible_date=row['convertible_date'],
                    maturity_date=row['maturity_date'],
                    underwriter_agent=row['underwriter_agent'],
                    filing_url=row['filing_url'],
                    notes=row['notes'],
                    is_registered=row['is_registered'],
                    registration_type=row['registration_type'],
                    known_owners=row['known_owners'],
                    price_protection=row['price_protection'],
                    pp_clause=row['pp_clause'],
                    variable_rate_adjustment=row['variable_rate_adjustment'],
                    floor_price=row['floor_price'],
                    is_toxic=row['is_toxic'],
                    last_update_date=row['last_update_date']
                )
                for row in rows
            ]
        except Exception as e:
            logger.warning("get_convertible_notes_failed", ticker=ticker, error=str(e))
            return []
    
    async def _get_convertible_preferred(self, ticker: str) -> List[ConvertiblePreferredModel]:
        """Obtener convertible preferred de un ticker (si existe tabla)"""
        try:
            query = """
            SELECT id, ticker, series, total_dollar_amount_issued, remaining_dollar_amount,
                   conversion_price, total_shares_when_converted, remaining_shares_when_converted,
                   issue_date, convertible_date, maturity_date, underwriter_agent,
                   filing_url, notes
            FROM sec_convertible_preferred
            WHERE ticker = $1
            ORDER BY issue_date DESC NULLS LAST
            """
            rows = await self.db.fetch(query, ticker)
            return [
                ConvertiblePreferredModel(
                    id=row['id'],
                    ticker=row['ticker'],
                    series=row['series'],
                    total_dollar_amount_issued=row['total_dollar_amount_issued'],
                    remaining_dollar_amount=row['remaining_dollar_amount'],
                    conversion_price=row['conversion_price'],
                    total_shares_when_converted=row['total_shares_when_converted'],
                    remaining_shares_when_converted=row['remaining_shares_when_converted'],
                    issue_date=row['issue_date'],
                    convertible_date=row['convertible_date'],
                    maturity_date=row['maturity_date'],
                    underwriter_agent=row['underwriter_agent'],
                    filing_url=row['filing_url'],
                    notes=row['notes']
                )
                for row in rows
            ]
        except Exception:
            return []
    
    async def _get_equity_lines(self, ticker: str) -> List[EquityLineModel]:
        """Obtener equity lines de un ticker (si existe tabla)"""
        try:
            query = """
            SELECT id, ticker, total_capacity, remaining_capacity,
                   agreement_start_date, agreement_end_date, filing_url, notes
            FROM sec_equity_lines
            WHERE ticker = $1
            ORDER BY agreement_start_date DESC NULLS LAST
            """
            rows = await self.db.fetch(query, ticker)
            return [
                EquityLineModel(
                    id=row['id'],
                    ticker=row['ticker'],
                    total_capacity=row['total_capacity'],
                    remaining_capacity=row['remaining_capacity'],
                    agreement_start_date=row['agreement_start_date'],
                    agreement_end_date=row['agreement_end_date'],
                    filing_url=row['filing_url'],
                    notes=row['notes']
                )
                for row in rows
            ]
        except Exception:
            return []
    
    async def _delete_ticker_data(self, ticker: str):
        """Borrar todos los datos secundarios de un ticker"""
        await self.db.execute("DELETE FROM sec_warrants WHERE ticker = $1", ticker)
        await self.db.execute("DELETE FROM sec_atm_offerings WHERE ticker = $1", ticker)
        await self.db.execute("DELETE FROM sec_shelf_registrations WHERE ticker = $1", ticker)
        await self.db.execute("DELETE FROM sec_completed_offerings WHERE ticker = $1", ticker)
        # Nuevos tipos (si existen tablas)
        try:
            await self.db.execute("DELETE FROM sec_s1_offerings WHERE ticker = $1", ticker)
        except: pass
        try:
            await self.db.execute("DELETE FROM sec_convertible_notes WHERE ticker = $1", ticker)
        except: pass
        try:
            await self.db.execute("DELETE FROM sec_convertible_preferred WHERE ticker = $1", ticker)
        except: pass
        try:
            await self.db.execute("DELETE FROM sec_equity_lines WHERE ticker = $1", ticker)
        except: pass
    
    async def _insert_warrant(self, ticker: str, warrant: WarrantModel):
        """Insertar un warrant con todos los campos incluyendo split adjustment, ejercicios y lifecycle v5"""
        
        # Validate exercise_price to avoid DB overflow (max 10^8 - 1)
        MAX_PRICE = 99_999_999.9999
        exercise_price = float(warrant.exercise_price or 0)
        if exercise_price > MAX_PRICE:
            logger.warning("warrant_price_overflow_capped", ticker=ticker,
                          original_price=exercise_price, capped_to=MAX_PRICE,
                          series=warrant.series_name)
            exercise_price = MAX_PRICE
        
        original_ex_price = float(warrant.original_exercise_price or 0)
        if original_ex_price > MAX_PRICE:
            original_ex_price = MAX_PRICE
        
        # Try with v5 lifecycle fields first
        try:
            await self._insert_warrant_v5(ticker, warrant, exercise_price, original_ex_price)
        except Exception as e:
            # Fallback to legacy insert if v5 columns don't exist yet
            logger.debug("warrant_insert_fallback_legacy", ticker=ticker, error=str(e)[:100])
            await self._insert_warrant_legacy(ticker, warrant, exercise_price, original_ex_price)
    
    async def _insert_warrant_v5(self, ticker: str, warrant: WarrantModel, exercise_price: float, original_ex_price: float):
        """Insert warrant with v5 lifecycle fields"""
        query = """
        INSERT INTO sec_warrants (
            ticker, series_name, issue_date, outstanding, exercise_price,
            expiration_date, potential_new_shares, notes,
            status, is_summary_row, exclude_from_dilution, imputed_fields,
            split_adjusted, split_factor, original_exercise_price, original_outstanding,
            total_issued, exercised, expired, remaining, last_update_date,
            known_owners, underwriter_agent, price_protection, pp_clause,
            exercisable_date, is_registered, registration_type, is_prefunded,
            has_cashless_exercise, warrant_coverage_ratio, anti_dilution_provision,
            source_filing, filing_url,
            warrant_type, underlying_type,
            ownership_blocker_pct, blocker_clause,
            potential_proceeds, actual_proceeds_to_date,
            warrant_agreement_exhibit, warrant_agreement_url,
            replaced_by_id, replaces_id, amendment_of_id,
            has_alternate_cashless, forced_exercise_provision,
            forced_exercise_price, forced_exercise_days,
            price_adjustment_count, original_issue_price, last_price_adjustment_date,
            exercise_events_count, last_exercise_date, last_exercise_quantity
        )
        VALUES (
            $1, $2, $3, $4, $5, $6, $7, $8, $9, $10, $11, $12, $13, $14, $15, $16, 
            $17, $18, $19, $20, $21, $22, $23, $24, $25, $26, $27, $28, $29, $30, 
            $31, $32, $33, $34, $35, $36, $37, $38, $39, $40, $41, $42, $43, $44,
            $45, $46, $47, $48, $49, $50, $51, $52, $53, $54, $55
        )
        """
        
        # Convert imputed_fields list to string
        imputed_str = ','.join(warrant.imputed_fields) if warrant.imputed_fields else None
        
        await self.db.execute(
            query,
            ticker,                                     # $1
            warrant.series_name,                        # $2
            warrant.issue_date,                         # $3
            warrant.outstanding,                        # $4
            exercise_price,                             # $5
            warrant.expiration_date,                    # $6
            warrant.potential_new_shares,               # $7
            warrant.notes,                              # $8
            warrant.status,                             # $9
            warrant.is_summary_row,                     # $10
            warrant.exclude_from_dilution,              # $11
            imputed_str,                                # $12
            warrant.split_adjusted,                     # $13
            warrant.split_factor,                       # $14
            original_ex_price,                          # $15
            warrant.original_outstanding,               # $16
            warrant.total_issued,                       # $17
            warrant.exercised,                          # $18
            warrant.expired,                            # $19
            warrant.remaining,                          # $20
            warrant.last_update_date,                   # $21
            warrant.known_owners,                       # $22
            warrant.underwriter_agent,                  # $23
            warrant.price_protection,                   # $24
            warrant.pp_clause,                          # $25
            warrant.exercisable_date,                   # $26
            warrant.is_registered,                      # $27
            warrant.registration_type,                  # $28
            warrant.is_prefunded,                       # $29
            warrant.has_cashless_exercise,              # $30
            float(warrant.warrant_coverage_ratio) if warrant.warrant_coverage_ratio else None,  # $31
            warrant.anti_dilution_provision,            # $32
            warrant.source_filing,                      # $33
            warrant.filing_url,                         # $34
            warrant.warrant_type,                       # $35
            warrant.underlying_type,                    # $36
            float(warrant.ownership_blocker_pct) if warrant.ownership_blocker_pct else None,  # $37
            warrant.blocker_clause,                     # $38
            float(warrant.potential_proceeds) if warrant.potential_proceeds else None,  # $39
            float(warrant.actual_proceeds_to_date) if warrant.actual_proceeds_to_date else None,  # $40
            warrant.warrant_agreement_exhibit,          # $41
            warrant.warrant_agreement_url,              # $42
            warrant.replaced_by_id,                     # $43
            warrant.replaces_id,                        # $44
            warrant.amendment_of_id,                    # $45
            warrant.has_alternate_cashless,             # $46
            warrant.forced_exercise_provision,          # $47
            float(warrant.forced_exercise_price) if warrant.forced_exercise_price else None,  # $48
            warrant.forced_exercise_days,               # $49
            warrant.price_adjustment_count,             # $50
            float(warrant.original_issue_price) if warrant.original_issue_price else None,  # $51
            warrant.last_price_adjustment_date,         # $52
            warrant.exercise_events_count,              # $53
            warrant.last_exercise_date,                 # $54
            warrant.last_exercise_quantity,             # $55
        )
    
    async def _insert_warrant_legacy(self, ticker: str, warrant: WarrantModel, exercise_price: float, original_ex_price: float):
        """Fallback insert for databases without v5 lifecycle columns"""
        query = """
        INSERT INTO sec_warrants (
            ticker, series_name, issue_date, outstanding, exercise_price,
            expiration_date, potential_new_shares, notes,
            status, is_summary_row, exclude_from_dilution, imputed_fields,
            split_adjusted, split_factor, original_exercise_price, original_outstanding,
            total_issued, exercised, expired, remaining, last_update_date
        )
        VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10, $11, $12, $13, $14, $15, $16, $17, $18, $19, $20, $21)
        """
        
        # Convert imputed_fields list to string
        imputed_str = ','.join(warrant.imputed_fields) if warrant.imputed_fields else None
        
        await self.db.execute(
            query,
            ticker,
            warrant.series_name,
            warrant.issue_date,
            warrant.outstanding,
            exercise_price,
            warrant.expiration_date,
            warrant.potential_new_shares,
            warrant.notes,
            warrant.status,
            warrant.is_summary_row,
            warrant.exclude_from_dilution,
            imputed_str,
            warrant.split_adjusted,
            warrant.split_factor,
            original_ex_price,
            warrant.original_outstanding,
            warrant.total_issued,
            warrant.exercised,
            warrant.expired,
            warrant.remaining,
            warrant.last_update_date
        )
    
    async def _insert_atm_offering(self, ticker: str, atm: ATMOfferingModel):
        """Insertar un ATM offering"""
        try:
            query = """
            INSERT INTO sec_atm_offerings (
                ticker, total_capacity, remaining_capacity,
                placement_agent, status, agreement_start_date,
                filing_date, filing_url, potential_shares_at_current_price, notes
            )
            VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10)
            """
            await self.db.execute(
                query,
                ticker,
                atm.total_capacity,
                atm.remaining_capacity,
                atm.placement_agent,
                atm.status,
                atm.agreement_start_date,
                atm.filing_date,
                atm.filing_url,
                atm.potential_shares_at_current_price,
                atm.notes
            )
        except Exception as e:
            # Si las columnas nuevas no existen, usar query sin ellas
            query = """
            INSERT INTO sec_atm_offerings (
                ticker, total_capacity, remaining_capacity,
                placement_agent, filing_date, filing_url,
                potential_shares_at_current_price
            )
            VALUES ($1, $2, $3, $4, $5, $6, $7)
            """
            await self.db.execute(
                query,
                ticker,
                atm.total_capacity,
                atm.remaining_capacity,
                atm.placement_agent,
                atm.filing_date,
                atm.filing_url,
                atm.potential_shares_at_current_price
            )
    
    async def _insert_shelf_registration(self, ticker: str, shelf: ShelfRegistrationModel):
        """Insertar una shelf registration"""
        try:
            query = """
            INSERT INTO sec_shelf_registrations (
                ticker, total_capacity, remaining_capacity,
                current_raisable_amount, total_amount_raised, total_amount_raised_last_12mo,
                is_baby_shelf, baby_shelf_restriction, security_type,
                filing_date, effect_date, registration_statement,
                filing_url, expiration_date, last_banker, notes
            )
            VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10, $11, $12, $13, $14, $15, $16)
            """
            await self.db.execute(
                query,
                ticker,
                shelf.total_capacity,
                shelf.remaining_capacity,
                shelf.current_raisable_amount,
                shelf.total_amount_raised,
                shelf.total_amount_raised_last_12mo,
                shelf.is_baby_shelf,
                shelf.baby_shelf_restriction,
                shelf.security_type,
                shelf.filing_date,
                shelf.effect_date,
                shelf.registration_statement,
                shelf.filing_url,
                shelf.expiration_date,
                shelf.last_banker,
                shelf.notes
            )
        except Exception:
            # Si las columnas nuevas no existen, usar query sin ellas
            query = """
            INSERT INTO sec_shelf_registrations (
                ticker, total_capacity, remaining_capacity,
                is_baby_shelf, security_type, filing_date, registration_statement,
                filing_url, expiration_date
            )
            VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9)
            """
            await self.db.execute(
                query,
                ticker,
                shelf.total_capacity,
                shelf.remaining_capacity,
                shelf.is_baby_shelf,
                shelf.security_type,
                shelf.filing_date,
                shelf.registration_statement,
                shelf.filing_url,
                shelf.expiration_date
            )
    
    async def _insert_completed_offering(self, ticker: str, offering: CompletedOfferingModel):
        """Insertar un completed offering"""
        query = """
        INSERT INTO sec_completed_offerings (
            ticker, offering_type, shares_issued,
            price_per_share, amount_raised, offering_date,
            filing_url, notes
        )
        VALUES ($1, $2, $3, $4, $5, $6, $7, $8)
        """
        
        await self.db.execute(
            query,
            ticker,
            offering.offering_type,
            offering.shares_issued,
            offering.price_per_share,
            offering.amount_raised,
            offering.offering_date,
            offering.filing_url,
            offering.notes
        )
    
    async def _insert_s1_offering(self, ticker: str, s1: S1OfferingModel):
        """Insertar un S-1 offering (si existe tabla)"""
        try:
            query = """
            INSERT INTO sec_s1_offerings (
                ticker, anticipated_deal_size, final_deal_size, final_pricing,
                final_shares_offered, warrant_coverage, final_warrant_coverage,
                exercise_price, underwriter_agent, s1_filing_date, status,
                filing_url, last_update_date
            )
            VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10, $11, $12, $13)
            """
            await self.db.execute(
                query,
                ticker,
                s1.anticipated_deal_size,
                s1.final_deal_size,
                s1.final_pricing,
                s1.final_shares_offered,
                s1.warrant_coverage,
                s1.final_warrant_coverage,
                s1.exercise_price,
                s1.underwriter_agent,
                s1.s1_filing_date,
                s1.status,
                s1.filing_url,
                s1.last_update_date
            )
        except Exception:
            # Tabla no existe aún, ignorar
            pass
    
    async def _insert_convertible_note(self, ticker: str, cn: ConvertibleNoteModel):
        """Insertar un convertible note con todos los campos"""
        try:
            query = """
            INSERT INTO sec_convertible_notes (
                ticker, series_name, total_principal_amount, remaining_principal_amount,
                conversion_price, original_conversion_price, conversion_ratio,
                total_shares_when_converted, remaining_shares_when_converted,
                interest_rate, issue_date, convertible_date, maturity_date, 
                underwriter_agent, filing_url, notes,
                is_registered, registration_type, known_owners,
                price_protection, pp_clause, variable_rate_adjustment,
                floor_price, is_toxic, last_update_date
            )
            VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10, $11, $12, $13, $14, $15, $16, $17, $18, $19, $20, $21, $22, $23, $24, $25)
            """
            await self.db.execute(
                query,
                ticker,
                cn.series_name,
                cn.total_principal_amount,
                cn.remaining_principal_amount,
                cn.conversion_price,
                cn.original_conversion_price,
                cn.conversion_ratio,
                cn.total_shares_when_converted,
                cn.remaining_shares_when_converted,
                cn.interest_rate,
                cn.issue_date,
                cn.convertible_date,
                cn.maturity_date,
                cn.underwriter_agent,
                cn.filing_url,
                cn.notes,
                cn.is_registered,
                cn.registration_type,
                cn.known_owners,
                cn.price_protection,
                cn.pp_clause,
                cn.variable_rate_adjustment,
                cn.floor_price,
                cn.is_toxic,
                cn.last_update_date
            )
        except Exception as e:
            logger.warning("insert_convertible_note_failed", ticker=ticker, error=str(e))
            pass
    
    async def _insert_convertible_preferred(self, ticker: str, cp: ConvertiblePreferredModel):
        """Insertar un convertible preferred (si existe tabla)"""
        try:
            query = """
            INSERT INTO sec_convertible_preferred (
                ticker, series, total_dollar_amount_issued, remaining_dollar_amount,
                conversion_price, total_shares_when_converted, remaining_shares_when_converted,
                issue_date, convertible_date, maturity_date, underwriter_agent,
                filing_url, notes
            )
            VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10, $11, $12, $13)
            """
            await self.db.execute(
                query,
                ticker,
                cp.series,
                cp.total_dollar_amount_issued,
                cp.remaining_dollar_amount,
                cp.conversion_price,
                cp.total_shares_when_converted,
                cp.remaining_shares_when_converted,
                cp.issue_date,
                cp.convertible_date,
                cp.maturity_date,
                cp.underwriter_agent,
                cp.filing_url,
                cp.notes
            )
        except Exception:
            # Tabla no existe aún, ignorar
            pass
    
    async def _insert_equity_line(self, ticker: str, el: EquityLineModel):
        """Insertar un equity line (si existe tabla)"""
        try:
            query = """
            INSERT INTO sec_equity_lines (
                ticker, total_capacity, remaining_capacity,
                agreement_start_date, agreement_end_date, filing_url, notes
            )
            VALUES ($1, $2, $3, $4, $5, $6, $7)
            """
            await self.db.execute(
                query,
                ticker,
                el.total_capacity,
                el.remaining_capacity,
                el.agreement_start_date,
                el.agreement_end_date,
                el.filing_url,
                el.notes
            )
        except Exception:
            # Tabla no existe aún, ignorar
            pass

