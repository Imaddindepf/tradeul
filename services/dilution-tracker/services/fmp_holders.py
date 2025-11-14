"""
FMP Holders Service
Obtiene institutional holders (13F filings) desde FMP
"""

import sys
sys.path.append('/app')

from typing import Optional, List, Dict
from datetime import date, datetime
from decimal import Decimal

from shared.utils.logger import get_logger
from .base_fmp_service import BaseFMPService
from ..models.holder_models import InstitutionalHolderCreate

logger = get_logger(__name__)


class FMPHoldersService(BaseFMPService):
    """
    Servicio para obtener institutional holders desde FMP
    """
    
    async def get_institutional_holders(
        self,
        ticker: str
    ) -> Optional[List[InstitutionalHolderCreate]]:
        """
        Obtener institutional holders (13F)
        
        Args:
            ticker: Símbolo del ticker
        
        Returns:
            Lista de holders o None
        """
        try:
            # Endpoint v3 para institutional holders
            endpoint = f"institutional-holder/{ticker}"
            
            result = await self._get(endpoint)
            
            if not result:
                logger.warning("no_institutional_holders", ticker=ticker)
                return None
            
            # Convertir a modelos
            holders = []
            for holder_data in result:
                holder = self._build_holder(ticker, holder_data)
                if holder:
                    holders.append(holder)
            
            logger.info(
                "institutional_holders_fetched",
                ticker=ticker,
                count=len(holders)
            )
            
            return holders
            
        except Exception as e:
            logger.error(
                "get_institutional_holders_failed",
                ticker=ticker,
                error=str(e)
            )
            return None
    
    async def get_institutional_ownership_by_symbol(
        self,
        ticker: str
    ) -> Optional[List[InstitutionalHolderCreate]]:
        """
        Obtener institutional ownership desde v4 endpoint (más detallado)
        
        Args:
            ticker: Símbolo del ticker
        
        Returns:
            Lista de holders o None
        """
        try:
            # V4 endpoint con más detalles
            endpoint = f"institutional-ownership/symbol-ownership"
            params = {"symbol": ticker}
            
            result = await self._get(endpoint, params, version="v4")
            
            if not result:
                # Fallback a v3 si v4 falla
                return await self.get_institutional_holders(ticker)
            
            # Convertir a modelos
            holders = []
            for holder_data in result:
                holder = self._build_holder_v4(ticker, holder_data)
                if holder:
                    holders.append(holder)
            
            logger.info(
                "institutional_ownership_fetched",
                ticker=ticker,
                count=len(holders)
            )
            
            return holders
            
        except Exception as e:
            logger.error(
                "get_institutional_ownership_failed",
                ticker=ticker,
                error=str(e)
            )
            # Fallback a v3
            return await self.get_institutional_holders(ticker)
    
    def _build_holder(
        self,
        ticker: str,
        data: Dict
    ) -> Optional[InstitutionalHolderCreate]:
        """
        Construir InstitutionalHolderCreate desde data de FMP v3
        
        Campos v3:
        - holder: nombre
        - shares: shares held
        - dateReported: fecha de reporte
        - change: cambio vs anterior
        """
        try:
            holder_name = data.get('holder')
            if not holder_name:
                return None
            
            # Parse fecha de reporte
            date_reported = data.get('dateReported')
            report_date = None
            if date_reported:
                try:
                    report_date = datetime.strptime(date_reported, "%Y-%m-%d").date()
                except:
                    report_date = datetime.now().date()
            else:
                report_date = datetime.now().date()
            
            # Shares held
            shares = self._safe_int(data.get('shares'))
            
            # Position change
            change = self._safe_int(data.get('change'))
            
            # Calculate ownership percentage (needs shares outstanding)
            # Will be calculated later when we have ticker metadata
            
            holder = InstitutionalHolderCreate(
                ticker=ticker,
                holder_name=holder_name,
                report_date=report_date,
                shares_held=shares,
                position_change=change,
                filing_date=report_date,  # Same as report date in v3
                form_type="13F"
            )
            
            return holder
            
        except Exception as e:
            logger.error(
                "build_holder_failed",
                ticker=ticker,
                error=str(e)
            )
            return None
    
    def _build_holder_v4(
        self,
        ticker: str,
        data: Dict
    ) -> Optional[InstitutionalHolderCreate]:
        """
        Construir InstitutionalHolderCreate desde data de FMP v4
        
        Campos v4:
        - investorName: nombre
        - shares: shares held
        - reportDate: fecha de reporte
        - changeInShares: cambio
        - percentageOfPortfolio: % del portfolio del holder
        """
        try:
            holder_name = data.get('investorName')
            if not holder_name:
                return None
            
            # Parse fecha
            report_date_str = data.get('reportDate')
            report_date = None
            if report_date_str:
                try:
                    report_date = datetime.strptime(report_date_str, "%Y-%m-%d").date()
                except:
                    report_date = datetime.now().date()
            else:
                report_date = datetime.now().date()
            
            # Shares
            shares = self._safe_int(data.get('shares'))
            change = self._safe_int(data.get('changeInShares'))
            
            # Position value
            position_value = self._safe_float(data.get('marketValue'))
            
            holder = InstitutionalHolderCreate(
                ticker=ticker,
                holder_name=holder_name,
                report_date=report_date,
                shares_held=shares,
                position_value=Decimal(str(position_value)) if position_value else None,
                position_change=change,
                filing_date=report_date,
                form_type="13F-HR"
            )
            
            return holder
            
        except Exception as e:
            logger.error(
                "build_holder_v4_failed",
                ticker=ticker,
                error=str(e)
            )
            return None
    
    async def enrich_holders_with_ownership_pct(
        self,
        holders: List[InstitutionalHolderCreate],
        shares_outstanding: int
    ) -> List[InstitutionalHolderCreate]:
        """
        Enriquecer holders con ownership percentage
        
        Args:
            holders: Lista de holders
            shares_outstanding: Shares outstanding del ticker
        
        Returns:
            Lista de holders con ownership_percent calculado
        """
        if not shares_outstanding or shares_outstanding == 0:
            return holders
        
        enriched = []
        for holder in holders:
            if holder.shares_held:
                ownership_pct = (holder.shares_held / shares_outstanding) * 100
                holder.ownership_percent = Decimal(str(round(ownership_pct, 2)))
            
            enriched.append(holder)
        
        return enriched
    
    async def calculate_position_changes(
        self,
        current_holders: List[InstitutionalHolderCreate],
        previous_holders: Optional[List[InstitutionalHolderCreate]]
    ) -> List[InstitutionalHolderCreate]:
        """
        Calcular cambios de posición vs reporte anterior
        
        Args:
            current_holders: Holders actuales
            previous_holders: Holders del reporte anterior
        
        Returns:
            Lista con position_change calculado
        """
        if not previous_holders:
            return current_holders
        
        # Crear map de holders anteriores
        previous_map = {
            holder.holder_name: holder.shares_held
            for holder in previous_holders
            if holder.shares_held is not None
        }
        
        # Calcular cambios
        updated = []
        for holder in current_holders:
            if holder.holder_name in previous_map:
                previous_shares = previous_map[holder.holder_name]
                current_shares = holder.shares_held or 0
                
                change = current_shares - previous_shares
                holder.position_change = change
                
                # Calculate percentage change
                if previous_shares > 0:
                    change_pct = (change / previous_shares) * 100
                    holder.position_change_percent = Decimal(str(round(change_pct, 2)))
            else:
                # New position
                holder.position_change = holder.shares_held
                holder.position_change_percent = None
            
            updated.append(holder)
        
        return updated
    
    async def get_13f_search(
        self,
        cik: Optional[str] = None,
        name: Optional[str] = None,
        date: Optional[str] = None
    ) -> Optional[List[Dict]]:
        """
        Buscar 13F filings
        
        Args:
            cik: CIK del institutional investor
            name: Nombre del investor
            date: Fecha (YYYY-MM-DD)
        
        Returns:
            Lista de filings
        """
        try:
            endpoint = "form-thirteen"
            params = {}
            
            if cik:
                params['cik'] = cik
            if name:
                params['name'] = name
            if date:
                params['date'] = date
            
            result = await self._get(endpoint, params, version="v3")
            
            return result if result else None
            
        except Exception as e:
            logger.error("get_13f_search_failed", error=str(e))
            return None

