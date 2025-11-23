"""
Cliente de base de datos para SEC Filings
"""
import asyncpg
import orjson
from typing import List, Optional, Dict, Any
from datetime import datetime, date
from config import settings
from models import SECFiling, FilingFilter


class DatabaseClient:
    """Cliente para interactuar con PostgreSQL/TimescaleDB"""
    
    def __init__(self):
        self.pool: Optional[asyncpg.Pool] = None
    
    async def connect(self):
        """Conectar al pool de PostgreSQL"""
        if self.pool is None:
            self.pool = await asyncpg.create_pool(
                host=settings.POSTGRES_HOST,
                port=settings.POSTGRES_PORT,
                user=settings.POSTGRES_USER,
                password=settings.POSTGRES_PASSWORD,
                database=settings.POSTGRES_DB,
                min_size=2,
                max_size=10,
                command_timeout=60
            )
            print(f"✅ Database pool created (min=2, max=10)")
    
    async def disconnect(self):
        """Cerrar el pool de conexiones"""
        if self.pool:
            await self.pool.close()
            self.pool = None
            print("✅ Database pool closed")
    
    async def insert_filing(self, filing: SECFiling) -> bool:
        """
        Insertar o actualizar un filing en la base de datos
        
        Args:
            filing: Objeto SECFiling con los datos
            
        Returns:
            True si se insertó correctamente
        """
        query = """
            INSERT INTO sec_filings (
                id, accession_no, form_type, filed_at, ticker, cik,
                company_name, company_name_long, period_of_report, description,
                items, group_members,
                link_to_filing_details, link_to_txt, link_to_html, link_to_xbrl,
                effectiveness_date, effectiveness_time, registration_form, reference_accession_no,
                entities, document_format_files, data_files, series_and_classes_contracts,
                created_at, updated_at
            ) VALUES (
                $1, $2, $3, $4, $5, $6, $7, $8, $9, $10,
                $11, $12, $13, $14, $15, $16, $17, $18, $19, $20,
                $21, $22, $23, $24, NOW(), NOW()
            )
            ON CONFLICT (accession_no) DO UPDATE SET
                ticker = EXCLUDED.ticker,
                form_type = EXCLUDED.form_type,
                filed_at = EXCLUDED.filed_at,
                company_name = EXCLUDED.company_name,
                company_name_long = EXCLUDED.company_name_long,
                items = EXCLUDED.items,
                link_to_filing_details = EXCLUDED.link_to_filing_details,
                updated_at = NOW()
        """
        
        try:
            async with self.pool.acquire() as conn:
                await conn.execute(
                    query,
                    filing.id,
                    filing.accessionNo,
                    filing.formType,
                    filing.filedAt,
                    filing.ticker,
                    filing.cik,
                    filing.companyName,
                    filing.companyNameLong,
                    filing.periodOfReport,
                    filing.description,
                    filing.items or [],
                    filing.groupMembers or [],
                    filing.linkToFilingDetails,
                    filing.linkToTxt,
                    filing.linkToHtml,
                    filing.linkToXbrl,
                    filing.effectivenessDate,
                    filing.effectivenessTime,
                    filing.registrationForm,
                    filing.referenceAccessionNo,
                    orjson.dumps([e.model_dump() for e in (filing.entities or [])]).decode() if filing.entities else None,
                    orjson.dumps([d.model_dump() for d in (filing.documentFormatFiles or [])]).decode() if filing.documentFormatFiles else None,
                    orjson.dumps([d.model_dump() for d in (filing.dataFiles or [])]).decode() if filing.dataFiles else None,
                    orjson.dumps([s.model_dump() for s in (filing.seriesAndClassesContractsInformation or [])]).decode() if filing.seriesAndClassesContractsInformation else None,
                )
                return True
        except Exception as e:
            print(f"❌ Error inserting filing {filing.accessionNo}: {e}")
            return False
    
    async def get_filings(
        self,
        filters: FilingFilter
    ) -> tuple[List[Dict[str, Any]], int]:
        """
        Obtener filings con filtros
        
        Args:
            filters: Filtros de búsqueda
            
        Returns:
            Tupla (lista de filings, total count)
        """
        # Construir query WHERE dinámicamente
        where_clauses = []
        params = []
        param_count = 1
        
        if filters.ticker:
            where_clauses.append(f"ticker = ${param_count}")
            params.append(filters.ticker)
            param_count += 1
        
        if filters.form_type:
            where_clauses.append(f"form_type = ${param_count}")
            params.append(filters.form_type)
            param_count += 1
        
        if filters.cik:
            where_clauses.append(f"cik = ${param_count}")
            params.append(filters.cik)
            param_count += 1
        
        if filters.date_from:
            where_clauses.append(f"filed_at >= ${param_count}")
            params.append(filters.date_from)
            param_count += 1
        
        if filters.date_to:
            where_clauses.append(f"filed_at <= ${param_count}")
            params.append(filters.date_to)
            param_count += 1
        
        if filters.items:
            where_clauses.append(f"items && ${param_count}")
            params.append(filters.items)
            param_count += 1
        
        where_sql = " AND ".join(where_clauses) if where_clauses else "1=1"
        
        # Query para contar total
        count_query = f"SELECT COUNT(*) FROM sec_filings WHERE {where_sql}"
        
        # Query para obtener datos
        offset = (filters.page - 1) * filters.page_size
        data_query = f"""
            SELECT 
                id, accession_no, form_type, filed_at, ticker, cik,
                company_name, company_name_long, period_of_report, description,
                items, link_to_filing_details, link_to_txt, link_to_html,
                entities, document_format_files, data_files
            FROM sec_filings
            WHERE {where_sql}
            ORDER BY filed_at DESC
            LIMIT ${param_count} OFFSET ${param_count + 1}
        """
        
        async with self.pool.acquire() as conn:
            # Obtener total
            total = await conn.fetchval(count_query, *params)
            
            # Obtener datos
            rows = await conn.fetch(data_query, *params, filters.page_size, offset)
            
            filings = []
            for row in rows:
                filing_dict = dict(row)
                # Convertir datetime a string ISO
                if filing_dict.get('filed_at'):
                    filing_dict['filed_at'] = filing_dict['filed_at'].isoformat()
                if filing_dict.get('period_of_report'):
                    filing_dict['period_of_report'] = filing_dict['period_of_report'].isoformat()
                filings.append(filing_dict)
            
            return filings, total
    
    async def get_latest_filing_date(self) -> Optional[datetime]:
        """Obtener la fecha del último filing en la BD"""
        query = "SELECT MAX(filed_at) FROM sec_filings"
        async with self.pool.acquire() as conn:
            result = await conn.fetchval(query)
            return result
    
    async def get_filing_by_accession(self, accession_no: str) -> Optional[Dict[str, Any]]:
        """Obtener filing por accession number"""
        query = """
            SELECT 
                id, accession_no, form_type, filed_at, ticker, cik,
                company_name, company_name_long, period_of_report, description,
                items, group_members,
                link_to_filing_details, link_to_txt, link_to_html, link_to_xbrl,
                entities, document_format_files, data_files,
                created_at, updated_at
            FROM sec_filings
            WHERE accession_no = $1
        """
        async with self.pool.acquire() as conn:
            row = await conn.fetchrow(query, accession_no)
            if row:
                filing_dict = dict(row)
                if filing_dict.get('filed_at'):
                    filing_dict['filed_at'] = filing_dict['filed_at'].isoformat()
                if filing_dict.get('period_of_report'):
                    filing_dict['period_of_report'] = filing_dict['period_of_report'].isoformat()
                return filing_dict
            return None
    
    async def get_stats(self) -> Dict[str, Any]:
        """Obtener estadísticas de la base de datos"""
        queries = {
            "total_filings": "SELECT COUNT(*) FROM sec_filings",
            "total_tickers": "SELECT COUNT(DISTINCT ticker) FROM sec_filings WHERE ticker IS NOT NULL",
            "latest_filing": "SELECT MAX(filed_at) FROM sec_filings",
            "oldest_filing": "SELECT MIN(filed_at) FROM sec_filings",
            "total_8k": "SELECT COUNT(*) FROM sec_filings WHERE form_type LIKE '8-K%'",
            "total_10k": "SELECT COUNT(*) FROM sec_filings WHERE form_type LIKE '10-K%'",
            "total_10q": "SELECT COUNT(*) FROM sec_filings WHERE form_type LIKE '10-Q%'",
            "total_form4": "SELECT COUNT(*) FROM sec_filings WHERE form_type = '4'",
        }
        
        stats = {}
        async with self.pool.acquire() as conn:
            for key, query in queries.items():
                result = await conn.fetchval(query)
                if isinstance(result, datetime):
                    stats[key] = result.isoformat()
                else:
                    stats[key] = result
        
        return stats


# Singleton
db_client = DatabaseClient()

