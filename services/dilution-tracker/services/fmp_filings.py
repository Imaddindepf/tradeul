"""
FMP Filings Service
Obtiene SEC filings desde FMP
"""

import sys
sys.path.append('/app')

from typing import Optional, List, Dict
from datetime import datetime

from shared.utils.logger import get_logger
from services.base_fmp_service import BaseFMPService
from models.filing_models import SECFilingCreate, FilingType

logger = get_logger(__name__)


class FMPFilingsService(BaseFMPService):
    """
    Servicio para obtener SEC filings desde FMP
    """
    
    async def get_sec_filings(
        self,
        ticker: str,
        filing_type: Optional[str] = None,
        limit: int = 100
    ) -> Optional[List[SECFilingCreate]]:
        """
        Obtener SEC filings para un ticker
        
        Args:
            ticker: Símbolo del ticker
            filing_type: Tipo de filing (opcional, ej: '10-K', '10-Q', '8-K')
            limit: Límite de resultados
        
        Returns:
            Lista de filings o None
        """
        try:
            endpoint = f"sec_filings/{ticker}"
            params = {"limit": limit}
            
            if filing_type:
                params['type'] = filing_type
            
            result = await self._get(endpoint, params)
            
            if not result:
                logger.warning("no_sec_filings", ticker=ticker)
                return None
            
            # Convertir a modelos
            filings = []
            for filing_data in result:
                filing = self._build_filing(ticker, filing_data)
                if filing:
                    filings.append(filing)
            
            logger.info(
                "sec_filings_fetched",
                ticker=ticker,
                count=len(filings),
                filing_type=filing_type
            )
            
            return filings
            
        except Exception as e:
            logger.error(
                "get_sec_filings_failed",
                ticker=ticker,
                error=str(e)
            )
            return None
    
    async def get_filings_by_type(
        self,
        ticker: str,
        filing_types: List[str],
        limit_per_type: int = 50
    ) -> Optional[List[SECFilingCreate]]:
        """
        Obtener múltiples tipos de filings
        
        Args:
            ticker: Símbolo del ticker
            filing_types: Lista de tipos ['10-K', '10-Q', '8-K']
            limit_per_type: Límite por tipo
        
        Returns:
            Lista combinada de filings
        """
        all_filings = []
        
        for filing_type in filing_types:
            filings = await self.get_sec_filings(ticker, filing_type, limit_per_type)
            if filings:
                all_filings.extend(filings)
        
        # Ordenar por fecha descendente
        all_filings.sort(key=lambda x: x.filing_date, reverse=True)
        
        return all_filings if all_filings else None
    
    async def get_offering_filings(
        self,
        ticker: str,
        limit: int = 50
    ) -> Optional[List[SECFilingCreate]]:
        """
        Obtener filings relacionados con offerings
        
        Args:
            ticker: Símbolo del ticker
            limit: Límite de resultados
        
        Returns:
            Lista de offering filings
        """
        # Tipos de filings relacionados con offerings
        offering_types = ['S-3', '424B5', '424B3', 'S-1', 'S-8']
        
        return await self.get_filings_by_type(ticker, offering_types, limit // len(offering_types))
    
    async def get_financial_filings(
        self,
        ticker: str,
        limit: int = 50
    ) -> Optional[List[SECFilingCreate]]:
        """
        Obtener filings financieros (10-K, 10-Q)
        
        Args:
            ticker: Símbolo del ticker
            limit: Límite de resultados
        
        Returns:
            Lista de financial filings
        """
        financial_types = ['10-K', '10-Q']
        
        return await self.get_filings_by_type(ticker, financial_types, limit // 2)
    
    async def get_ownership_filings(
        self,
        ticker: str,
        limit: int = 50
    ) -> Optional[List[SECFilingCreate]]:
        """
        Obtener filings de ownership (SC 13D, SC 13G)
        
        Args:
            ticker: Símbolo del ticker
            limit: Límite de resultados
        
        Returns:
            Lista de ownership filings
        """
        ownership_types = ['SC 13D', 'SC 13D/A', 'SC 13G', 'SC 13G/A']
        
        return await self.get_filings_by_type(ticker, ownership_types, limit // 4)
    
    def _build_filing(
        self,
        ticker: str,
        data: Dict
    ) -> Optional[SECFilingCreate]:
        """
        Construir SECFilingCreate desde data de FMP
        
        Campos FMP:
        - type: Tipo de filing
        - date: Fecha de filing
        - link: URL al filing
        - reportDate: Fecha del reporte (opcional)
        - acceptanceDateTime: Timestamp de aceptación
        - cik: CIK del company
        - accessionNumber: Accession number único
        - title: Título del filing (opcional)
        """
        try:
            filing_type = data.get('type')
            if not filing_type:
                return None
            
            # Parse filing date
            filing_date_str = data.get('date') or data.get('fillingDate')
            if not filing_date_str:
                return None
            
            try:
                filing_date = datetime.strptime(filing_date_str, "%Y-%m-%d").date()
            except:
                logger.warning("invalid_filing_date", date=filing_date_str)
                return None
            
            # Parse report date (optional)
            report_date = None
            report_date_str = data.get('reportDate')
            if report_date_str:
                try:
                    report_date = datetime.strptime(report_date_str, "%Y-%m-%d").date()
                except:
                    pass
            
            # Accession number
            accession_number = data.get('accessionNumber')
            if not accession_number:
                # Generate a fallback accession number if not provided
                accession_number = f"{ticker}-{filing_type}-{filing_date_str}"
            
            # Build URL
            url = data.get('link') or data.get('finalLink')
            
            # Title
            title = data.get('title')
            if not title:
                # Generate default title
                title = f"{filing_type} Filing"
            
            # Description (optional)
            description = data.get('description')
            
            # Create filing
            filing = SECFilingCreate(
                ticker=ticker,
                filing_type=filing_type,
                filing_date=filing_date,
                report_date=report_date,
                accession_number=accession_number,
                title=title,
                description=description,
                url=url,
                # category, is_offering_related, is_dilutive se auto-calculan en el modelo
            )
            
            return filing
            
        except Exception as e:
            logger.error(
                "build_filing_failed",
                ticker=ticker,
                error=str(e)
            )
            return None
    
    async def get_rss_feed(
        self,
        page: int = 0,
        limit: int = 100
    ) -> Optional[List[Dict]]:
        """
        Obtener feed de filings recientes (todos los tickers)
        
        Args:
            page: Página
            limit: Límite por página
        
        Returns:
            Lista de filings recientes
        """
        try:
            endpoint = "rss_feed"
            params = {
                "page": page,
                "limit": limit
            }
            
            result = await self._get(endpoint, params, version="v4")
            
            return result if result else None
            
        except Exception as e:
            logger.error("get_rss_feed_failed", error=str(e))
            return None
    
    async def search_dilutive_events(
        self,
        ticker: str,
        days_back: int = 365
    ) -> Optional[List[SECFilingCreate]]:
        """
        Buscar eventos potencialmente dilutivos en el último período
        
        Args:
            ticker: Símbolo del ticker
            days_back: Días hacia atrás
        
        Returns:
            Lista de filings potencialmente dilutivos
        """
        try:
            # Obtener todos los filings
            all_filings = await self.get_sec_filings(ticker, limit=200)
            
            if not all_filings:
                return None
            
            # Filtrar por fecha y tipos dilutivos
            cutoff_date = datetime.now().date()
            from datetime import timedelta
            cutoff_date = cutoff_date - timedelta(days=days_back)
            
            dilutive_filings = [
                filing for filing in all_filings
                if filing.filing_date >= cutoff_date and filing.is_dilutive
            ]
            
            logger.info(
                "dilutive_events_found",
                ticker=ticker,
                count=len(dilutive_filings),
                days_back=days_back
            )
            
            return dilutive_filings if dilutive_filings else None
            
        except Exception as e:
            logger.error(
                "search_dilutive_events_failed",
                ticker=ticker,
                error=str(e)
            )
            return None

