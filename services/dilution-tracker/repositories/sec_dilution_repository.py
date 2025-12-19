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
                shares_outstanding, float_shares,
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
                float_shares=profile_row['float_shares'],
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
                shares_outstanding, float_shares,
                last_scraped_at, source_filings,
                scrape_success, scrape_error
            )
            VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10)
            ON CONFLICT (ticker) DO UPDATE SET
                cik = EXCLUDED.cik,
                company_name = EXCLUDED.company_name,
                current_price = EXCLUDED.current_price,
                shares_outstanding = EXCLUDED.shares_outstanding,
                float_shares = EXCLUDED.float_shares,
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
                profile.float_shares,
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
        """Obtener warrants de un ticker con todos los campos"""
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
        """Obtener convertible notes de un ticker (si existe tabla)"""
        try:
            query = """
            SELECT id, ticker, total_principal_amount, remaining_principal_amount,
                   conversion_price, total_shares_when_converted, remaining_shares_when_converted,
                   issue_date, convertible_date, maturity_date, underwriter_agent,
                   filing_url, notes
            FROM sec_convertible_notes
            WHERE ticker = $1
            ORDER BY maturity_date DESC NULLS LAST
            """
            rows = await self.db.fetch(query, ticker)
            return [
                ConvertibleNoteModel(
                    id=row['id'],
                    ticker=row['ticker'],
                    total_principal_amount=row['total_principal_amount'],
                    remaining_principal_amount=row['remaining_principal_amount'],
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
        """Insertar un warrant con todos los campos incluyendo split adjustment y ejercicios"""
        query = """
        INSERT INTO sec_warrants (
            ticker, issue_date, outstanding, exercise_price,
            expiration_date, potential_new_shares, notes,
            status, is_summary_row, exclude_from_dilution, imputed_fields,
            split_adjusted, split_factor, original_exercise_price, original_outstanding,
            total_issued, exercised, expired, remaining, last_update_date
        )
        VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10, $11, $12, $13, $14, $15, $16, $17, $18, $19, $20)
        """
        
        # Convert imputed_fields list to string
        imputed_str = ','.join(warrant.imputed_fields) if warrant.imputed_fields else None
        
        await self.db.execute(
            query,
            ticker,
            warrant.issue_date,
            warrant.outstanding,
            warrant.exercise_price,
            warrant.expiration_date,
            warrant.potential_new_shares,
            warrant.notes,
            warrant.status,
            warrant.is_summary_row,
            warrant.exclude_from_dilution,
            imputed_str,
            warrant.split_adjusted,
            warrant.split_factor,
            warrant.original_exercise_price,
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
        """Insertar un convertible note (si existe tabla)"""
        try:
            query = """
            INSERT INTO sec_convertible_notes (
                ticker, total_principal_amount, remaining_principal_amount,
                conversion_price, total_shares_when_converted, remaining_shares_when_converted,
                issue_date, convertible_date, maturity_date, underwriter_agent,
                filing_url, notes
            )
            VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10, $11, $12)
            """
            await self.db.execute(
                query,
                ticker,
                cn.total_principal_amount,
                cn.remaining_principal_amount,
                cn.conversion_price,
                cn.total_shares_when_converted,
                cn.remaining_shares_when_converted,
                cn.issue_date,
                cn.convertible_date,
                cn.maturity_date,
                cn.underwriter_agent,
                cn.filing_url,
                cn.notes
            )
        except Exception:
            # Tabla no existe aún, ignorar
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

