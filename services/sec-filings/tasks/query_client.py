"""
Cliente para SEC Query API (backfill histórico)
Carga filings históricos y los guarda en BD
"""
import asyncio
import httpx
from datetime import datetime, date, timedelta
from typing import Optional, List, Dict, Any
from models import SECFiling
from utils.database import db_client
from config import settings


class SECQueryClient:
    """Cliente HTTP para SEC Query API"""
    
    def __init__(self):
        self.client: Optional[httpx.AsyncClient] = None
        self.stats = {
            "is_running": False,
            "total_processed": 0,
            "total_inserted": 0,
            "total_updated": 0,
            "total_errors": 0,
            "current_date": None,
            "started_at": None,
            "completed_at": None,
        }
    
    async def connect(self):
        """Crear cliente HTTP"""
        if not self.client:
            self.client = httpx.AsyncClient(
                timeout=30.0,
                headers={"Authorization": settings.SEC_API_IO}
            )
            print("✅ Query API client created")
    
    async def disconnect(self):
        """Cerrar cliente HTTP"""
        if self.client:
            await self.client.aclose()
            self.client = None
            print("✅ Query API client closed")
    
    def parse_filing(self, filing_data: dict) -> Optional[SECFiling]:
        """
        Parsear datos raw del Query API a modelo SECFiling
        
        Args:
            filing_data: Dict con datos raw del filing
            
        Returns:
            Objeto SECFiling o None si hay error
        """
        try:
            # El Query API envía filedAt como string, necesitamos parsearlo
            if 'filedAt' in filing_data and isinstance(filing_data['filedAt'], str):
                filing_data['filedAt'] = datetime.fromisoformat(
                    filing_data['filedAt'].replace('Z', '+00:00')
                )
            
            # Crear objeto SECFiling
            filing = SECFiling(**filing_data)
            return filing
        except Exception as e:
            print(f"❌ Error parsing filing: {e}")
            return None
    
    async def query_filings(
        self,
        query: str,
        from_index: int = 0,
        size: int = 50
    ) -> Optional[Dict[str, Any]]:
        """
        Hacer query al SEC Query API
        
        Args:
            query: Lucene query string (e.g., "formType:8-K AND filedAt:[2024-01-01 TO 2024-01-31]")
            from_index: Índice de inicio para paginación
            size: Tamaño de página (max 50)
            
        Returns:
            Dict con response del API o None si hay error
        """
        url = f"{settings.SEC_QUERY_URL}/v1/filings"
        
        payload = {
            "query": query,
            "from": str(from_index),
            "size": str(size),
            "sort": [{"filedAt": {"order": "desc"}}]
        }
        
        try:
            response = await self.client.post(url, json=payload)
            response.raise_for_status()
            return response.json()
        except Exception as e:
            print(f"❌ Query API error: {e}")
            return None
    
    async def backfill_date_range(
        self,
        start_date: date,
        end_date: date,
        form_types: Optional[List[str]] = None
    ) -> int:
        """
        Hacer backfill de filings para un rango de fechas
        
        Args:
            start_date: Fecha inicial
            end_date: Fecha final
            form_types: Lista de form types a filtrar (opcional)
            
        Returns:
            Número de filings procesados
        """
        total_processed = 0
        
        # Iterar por cada fecha en el rango
        current_date = start_date
        while current_date <= end_date:
            self.stats["current_date"] = current_date
            
            # Construir query para esta fecha
            date_str = current_date.strftime("%Y-%m-%d")
            query = f"filedAt:[{date_str} TO {date_str}]"
            
            # Agregar filtro de form types si se especifica
            if form_types:
                form_filter = " OR ".join([f'formType:"{ft}"' for ft in form_types])
                query = f"({form_filter}) AND {query}"
            
            print(f"📅 Backfilling {current_date} | Query: {query}")
            
            # Paginar a través de todos los resultados
            from_index = 0
            while True:
                response = await self.query_filings(query, from_index, settings.BACKFILL_BATCH_SIZE)
                
                if not response or 'filings' not in response:
                    break
                
                filings_data = response['filings']
                if not filings_data:
                    break
                
                # Procesar cada filing
                for filing_data in filings_data:
                    filing = self.parse_filing(filing_data)
                    if filing:
                        success = await db_client.insert_filing(filing)
                        if success:
                            self.stats["total_inserted"] += 1
                        else:
                            self.stats["total_errors"] += 1
                        
                        self.stats["total_processed"] += 1
                        total_processed += 1
                
                # Log progreso
                print(
                    f"   Processed {len(filings_data)} filings "
                    f"(total: {total_processed})"
                )
                
                # Siguiente página
                from_index += settings.BACKFILL_BATCH_SIZE
                
                # Si recibimos menos de lo solicitado, ya terminamos
                if len(filings_data) < settings.BACKFILL_BATCH_SIZE:
                    break
                
                # Small delay para no saturar API
                await asyncio.sleep(0.5)
            
            # Siguiente fecha
            current_date += timedelta(days=1)
            await asyncio.sleep(0.2)  # Delay entre fechas
        
        return total_processed
    
    async def backfill_recent(self, days_back: int = 30) -> int:
        """
        Hacer backfill de los últimos N días
        
        Args:
            days_back: Número de días hacia atrás
            
        Returns:
            Número de filings procesados
        """
        end_date = date.today()
        start_date = end_date - timedelta(days=days_back)
        
        print(f"🔄 Starting backfill from {start_date} to {end_date}")
        
        self.stats["is_running"] = True
        self.stats["started_at"] = datetime.now()
        
        total = await self.backfill_date_range(start_date, end_date)
        
        self.stats["is_running"] = False
        self.stats["completed_at"] = datetime.now()
        
        print(f"✅ Backfill complete: {total} filings processed")
        
        return total
    
    async def backfill_specific_forms(
        self,
        form_types: List[str],
        start_date: date,
        end_date: date
    ) -> int:
        """
        Hacer backfill de form types específicos
        
        Args:
            form_types: Lista de form types (e.g., ["8-K", "10-K", "10-Q"])
            start_date: Fecha inicial
            end_date: Fecha final
            
        Returns:
            Número de filings procesados
        """
        print(f"🔄 Starting backfill for {form_types} from {start_date} to {end_date}")
        
        self.stats["is_running"] = True
        self.stats["started_at"] = datetime.now()
        
        total = await self.backfill_date_range(start_date, end_date, form_types)
        
        self.stats["is_running"] = False
        self.stats["completed_at"] = datetime.now()
        
        print(f"✅ Backfill complete: {total} filings processed")
        
        return total
    
    def get_status(self) -> dict:
        """Obtener estado del backfill"""
        return {
            "is_running": self.stats["is_running"],
            "total_processed": self.stats["total_processed"],
            "total_inserted": self.stats["total_inserted"],
            "total_updated": self.stats["total_updated"],
            "total_errors": self.stats["total_errors"],
            "current_date": (
                self.stats["current_date"].isoformat()
                if self.stats["current_date"]
                else None
            ),
            "started_at": (
                self.stats["started_at"].isoformat()
                if self.stats["started_at"]
                else None
            ),
            "completed_at": (
                self.stats["completed_at"].isoformat()
                if self.stats["completed_at"]
                else None
            ),
        }


# Singleton
query_client = SECQueryClient()

