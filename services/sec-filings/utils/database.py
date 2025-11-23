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
                    filing.accession_no,
                    filing.form_type,
                    filing.filed_at,
                    filing.ticker,
                    filing.cik,
                    filing.company_name,
                    filing.company_name_long,
                    filing.period_of_report,
                    filing.description,
                    filing.items or [],
                    filing.group_members or [],
                    filing.link_to_filing_details,
                    filing.link_to_txt,
                    filing.link_to_html,
                    filing.link_to_xbrl,
                    filing.effectiveness_date,
                    filing.effectiveness_time,
                    filing.registration_form,
                    filing.reference_accession_no,
                    orjson.dumps([e.model_dump() for e in (filing.entities or [])]).decode() if filing.entities else None,
                    orjson.dumps([d.model_dump() for d in (filing.document_format_files or [])]).decode() if filing.document_format_files else None,
                    orjson.dumps([d.model_dump() for d in (filing.data_files or [])]).decode() if filing.data_files else None,
                    orjson.dumps([s.model_dump() for s in (filing.series_and_classes_contracts_information or [])]).decode() if filing.series_and_classes_contracts_information else None,
                )
                return True
        except Exception as e:
            print(f"❌ Error inserting filing {filing.accession_no}: {e}")
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
            # Convertir date a datetime para comparar con timestamptz
            # date_from a las 00:00:00 UTC
            where_clauses.append(f"filed_at >= ${param_count}::date")
            params.append(filters.date_from)
            param_count += 1
        
        if filters.date_to:
            # date_to a las 23:59:59 UTC (incluir todo el día)
            where_clauses.append(f"filed_at < (${param_count}::date + interval '1 day')")
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
            
            # Convertir a diccionarios y parsear campos JSONB
            filings = []
            for row in rows:
                filing_dict = dict(row)
                # Parsear campos JSONB (PostgreSQL los devuelve como strings)
                if filing_dict.get('entities') and isinstance(filing_dict['entities'], str):
                    filing_dict['entities'] = orjson.loads(filing_dict['entities'])
                if filing_dict.get('document_format_files') and isinstance(filing_dict['document_format_files'], str):
                    filing_dict['document_format_files'] = orjson.loads(filing_dict['document_format_files'])
                if filing_dict.get('data_files') and isinstance(filing_dict['data_files'], str):
                    filing_dict['data_files'] = orjson.loads(filing_dict['data_files'])
                if filing_dict.get('series_and_classes_contracts_information') and isinstance(filing_dict['series_and_classes_contracts_information'], str):
                    filing_dict['series_and_classes_contracts_information'] = orjson.loads(filing_dict['series_and_classes_contracts_information'])
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
                # Parsear campos JSONB
                if filing_dict.get('entities') and isinstance(filing_dict['entities'], str):
                    filing_dict['entities'] = orjson.loads(filing_dict['entities'])
                if filing_dict.get('document_format_files') and isinstance(filing_dict['document_format_files'], str):
                    filing_dict['document_format_files'] = orjson.loads(filing_dict['document_format_files'])
                if filing_dict.get('data_files') and isinstance(filing_dict['data_files'], str):
                    filing_dict['data_files'] = orjson.loads(filing_dict['data_files'])
                if filing_dict.get('series_and_classes_contracts_information') and isinstance(filing_dict['series_and_classes_contracts_information'], str):
                    filing_dict['series_and_classes_contracts_information'] = orjson.loads(filing_dict['series_and_classes_contracts_information'])
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

