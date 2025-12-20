"""
SEC Filing Fetcher
==================
Funciones para obtener y descargar filings de SEC EDGAR.

Este módulo maneja:
- Obtención de CIK y company name
- Búsqueda de filings via SEC-API.io y FMP
- Descarga de contenido HTML de filings
- Filtrado de filings relevantes para dilución
"""

import asyncio
import json
import re
from datetime import datetime, date
from typing import Dict, List, Optional, Tuple

from bs4 import BeautifulSoup
import httpx

from shared.config.settings import settings
from shared.utils.logger import get_logger
from shared.utils.timescale_client import TimescaleClient
from http_clients import http_clients

logger = get_logger(__name__)


class SECFilingFetcher:
    """
    Servicio para obtener filings de SEC EDGAR.
    """
    
    SEC_EDGAR_BASE_URL = "https://data.sec.gov"
    SEC_RATE_LIMIT_DELAY = 0.2  # 200ms entre requests
    
    def __init__(self, db: Optional[TimescaleClient] = None):
        self.db = db
    
    async def get_cik_and_company_name(self, ticker: str) -> Tuple[Optional[str], Optional[str]]:
        """
        Obtener CIK desde SEC EDGAR usando el ticker
        
        Returns:
            Tuple (cik, company_name)
        """
        try:
            # Primero intentar desde nuestra BD (ticker_metadata)
            if self.db:
                query = """
                SELECT cik, company_name
                FROM ticker_metadata
                WHERE symbol = $1
                """
                result = await self.db.fetchrow(query, ticker)
                
                if result and result['cik']:
                    return result['cik'], result['company_name']
            
            # Si no está en BD, usar SEC EDGAR API
            url = f"{self.SEC_EDGAR_BASE_URL}/submissions/CIK{ticker}.json"
            
            content = await http_clients.sec_gov.get_filing_content(url)
            if content:
                try:
                    data = json.loads(content)
                    cik = data.get('cik')
                    company_name = data.get('name')
                    return str(cik).zfill(10), company_name
                except json.JSONDecodeError:
                    pass
            
            # Fallback: usar SEC company tickers JSON
            data = await http_clients.sec_gov.get_company_tickers()
            if data:
                for key, company in data.items():
                    if company.get('ticker') == ticker:
                        cik = str(company.get('cik_str')).zfill(10)
                        company_name = company.get('title')
                        return cik, company_name
            
            return None, None
            
        except Exception as e:
            logger.error("get_cik_failed", ticker=ticker, error=str(e))
            return None, None
    
    async def fetch_all_filings_from_sec_api_io(
        self, 
        ticker: str, 
        cik: Optional[str] = None
    ) -> List[Dict]:
        """
        Buscar TODOS los filings usando SEC-API.io Query API (FUENTE DE VERDAD)
        
        Args:
            ticker: Ticker symbol (solo para logging)
            cik: CIK de la empresa (fuente de precisión)
            
        Returns:
            Lista COMPLETA de todos los filings desde 2010
        """
        try:
            sec_api_key = settings.SEC_API_IO_KEY
            
            if not sec_api_key:
                logger.warning("sec_api_io_key_missing_using_fmp_fallback")
                return await self.fetch_all_filings_from_fmp(ticker)
            
            # Query por CIK para precisión
            if cik:
                cik_normalized = cik.lstrip('0') if cik else None
                query_str = f'cik:{cik_normalized} AND filedAt:[2010-01-01 TO *]'
            else:
                query_str = f'ticker:{ticker} AND filedAt:[2010-01-01 TO *]'
            
            query = {
                "query": {
                    "query_string": {
                        "query": query_str
                    }
                },
                "from": "0",
                "size": "200",
                "sort": [{"filedAt": {"order": "desc"}}]
            }
            
            all_filings = []
            from_index = 0
            max_filings = 1000
            
            logger.info("sec_api_io_search_started", ticker=ticker)
            
            while len(all_filings) < max_filings:
                query["from"] = str(from_index)
                
                data = await http_clients.sec_api.query_api(query) if http_clients.sec_api else None
                
                if not data:
                    logger.warning("sec_api_io_error", ticker=ticker)
                    break
                
                filings_batch = data.get('filings', [])
                
                if not filings_batch:
                    break
                
                for filing in filings_batch:
                    all_filings.append({
                        'form_type': filing.get('formType', ''),
                        'filing_date': filing.get('filedAt', '')[:10],
                        'accession_number': filing.get('accessionNo', ''),
                        'primary_document': '',
                        'url': filing.get('linkToFilingDetails', filing.get('linkToTxt', ''))
                    })
                
                logger.info("sec_api_io_batch_processed", ticker=ticker, 
                           from_index=from_index, count=len(filings_batch))
                
                if len(filings_batch) < 200:
                    break
                
                from_index += 200
            
            logger.info("sec_api_io_search_completed", ticker=ticker, total=len(all_filings))
            
            return all_filings
            
        except Exception as e:
            logger.error("fetch_sec_api_io_failed", ticker=ticker, error=str(e))
            logger.info("falling_back_to_fmp", ticker=ticker)
            return await self.fetch_all_filings_from_fmp(ticker)
    
    async def fetch_all_filings_from_fmp(self, ticker: str) -> List[Dict]:
        """
        Buscar TODOS los filings desde 2010 usando FMP API (FALLBACK)
        """
        try:
            fmp_api_key = settings.FMP_API_KEY
            
            if not fmp_api_key:
                logger.warning("fmp_api_key_missing")
                return []
            
            all_filings = []
            page = 0
            max_pages = 10
            
            logger.info("fmp_filings_search_started", ticker=ticker)
            
            while page < max_pages:
                filings_batch = await http_clients.fmp.get(
                    f"sec_filings/{ticker}",
                    params={"page": page}
                )
                
                if filings_batch is None:
                    logger.warning("fmp_api_error", ticker=ticker, page=page)
                    break
                
                if not filings_batch or len(filings_batch) == 0:
                    break
                
                for filing in filings_batch:
                    filing_date = filing.get('fillingDate', filing.get('acceptedDate', ''))
                    if filing_date and filing_date >= '2010-01-01':
                        form_type = self.normalize_form_type(filing.get('type', ''))
                        all_filings.append({
                            'form_type': form_type,
                            'filing_date': filing_date,
                            'accession_number': filing.get('accessionNumber', ''),
                            'primary_document': '',
                            'url': filing.get('finalLink', filing.get('link', ''))
                        })
                
                logger.info("fmp_page_processed", ticker=ticker, page=page, 
                           filings_in_page=len(filings_batch))
                
                if len(filings_batch) < 100:
                    break
                
                page += 1
            
            logger.info("fmp_filings_search_completed", ticker=ticker, 
                       total_filings=len(all_filings), pages=page+1)
            
            return all_filings
            
        except Exception as e:
            logger.error("fetch_fmp_filings_failed", ticker=ticker, error=str(e))
            return []
    
    async def fetch_recent_filings(self, cik: str) -> List[Dict]:
        """
        Buscar filings recientes del CIK desde SEC EDGAR
        """
        try:
            url = f"{self.SEC_EDGAR_BASE_URL}/submissions/CIK{cik}.json"
            
            content = await http_clients.sec_gov.get_filing_content(url)
            
            if not content:
                logger.error("sec_api_error", cik=cik)
                return []
            
            try:
                data = json.loads(content)
            except json.JSONDecodeError:
                logger.error("sec_json_parse_error", cik=cik)
                return []
            
            filings_data = data.get('filings', {}).get('recent', {})
            
            if not filings_data:
                return []
            
            filings = []
            
            form_types = filings_data.get('form', [])
            filing_dates = filings_data.get('filingDate', [])
            accession_numbers = filings_data.get('accessionNumber', [])
            primary_documents = filings_data.get('primaryDocument', [])
            
            for i in range(len(form_types)):
                filings.append({
                    'form_type': form_types[i],
                    'filing_date': filing_dates[i],
                    'accession_number': accession_numbers[i],
                    'primary_document': primary_documents[i],
                    'url': self.construct_filing_url(cik, accession_numbers[i], primary_documents[i])
                })
            
            return filings
                
        except Exception as e:
            logger.error("fetch_recent_filings_failed", cik=cik, error=str(e))
            return []
    
    async def fetch_424b_filings(self, cik: str, max_count: int = 100) -> List[Dict]:
        """
        Buscar TODOS los 424B (prospectus supplements) usando búsqueda avanzada
        """
        try:
            url = "https://www.sec.gov/cgi-bin/browse-edgar"
            
            params = {
                "action": "getcompany",
                "CIK": cik,
                "type": "424",
                "dateb": "",
                "owner": "exclude",
                "count": max_count,
                "output": "atom"
            }
            
            query_string = "&".join(f"{k}={v}" for k, v in params.items())
            full_url = f"{url}?{query_string}"
            
            content = await http_clients.sec_gov.get_filing_content(full_url)
            
            if not content:
                logger.warning("sec_424b_search_failed", cik=cik)
                return []
            
            soup = BeautifulSoup(content, 'xml')
            entries = soup.find_all('entry')
            
            filings_424b = []
            
            for entry in entries:
                title_elem = entry.find('title')
                updated_elem = entry.find('updated')
                link_elem = entry.find('link', {'type': 'text/html'})
                
                if not title_elem or not link_elem:
                    continue
                
                title = title_elem.text.strip()
                filing_url = link_elem.get('href', '')
                filing_date = updated_elem.text.split('T')[0] if updated_elem else None
                
                form_match = re.search(r'(424B\d+)', title)
                form_type = form_match.group(1) if form_match else '424B5'
                
                url_parts = filing_url.split('/')
                if len(url_parts) >= 3:
                    accession_number = url_parts[-2] if len(url_parts) > 2 else ''
                    primary_document = url_parts[-1] if len(url_parts) > 1 else ''
                    
                    if accession_number and len(accession_number) == 18:
                        accession_number = f"{accession_number[:10]}-{accession_number[10:12]}-{accession_number[12:]}"
                    
                    filings_424b.append({
                        'form_type': form_type,
                        'filing_date': filing_date,
                        'accession_number': accession_number,
                        'primary_document': primary_document,
                        'url': filing_url
                    })
            
            logger.info("424b_search_completed", cik=cik, found=len(filings_424b))
            
            return filings_424b
                
        except Exception as e:
            logger.error("fetch_424b_filings_failed", cik=cik, error=str(e))
            return []
    
    def normalize_form_type(self, form_type: str) -> str:
        """
        Normalizar tipo de filing de FMP al formato estándar SEC
        """
        if not form_type:
            return ''
        
        form_type = form_type.strip().upper()
        
        normalization_map = {
            # US Domestic
            '10K': '10-K', '10-K': '10-K',
            '10KA': '10-K/A', '10-K/A': '10-K/A',
            '10Q': '10-Q', '10-Q': '10-Q',
            '10QA': '10-Q/A', '10-Q/A': '10-Q/A',
            '8K': '8-K', '8-K': '8-K',
            '8KA': '8-K/A', '8-K/A': '8-K/A',
            'S3': 'S-3', 'S-3': 'S-3',
            'S3A': 'S-3/A', 'S-3/A': 'S-3/A',
            'S1': 'S-1', 'S-1': 'S-1',
            'S1A': 'S-1/A', 'S-1/A': 'S-1/A',
            'S8': 'S-8', 'S-8': 'S-8',
            'S11': 'S-11', 'S-11': 'S-11',
            # Foreign Private Issuer
            '20F': '20-F', '20-F': '20-F',
            '20FA': '20-F/A', '20-F/A': '20-F/A',
            '6K': '6-K', '6-K': '6-K',
            '6KA': '6-K/A', '6-K/A': '6-K/A',
            'F1': 'F-1', 'F-1': 'F-1',
            'F1A': 'F-1/A', 'F-1/A': 'F-1/A',
            'F3': 'F-3', 'F-3': 'F-3',
            'F3A': 'F-3/A', 'F-3/A': 'F-3/A',
        }
        
        if form_type in normalization_map:
            return normalization_map[form_type]
        
        if '-' in form_type:
            return form_type
        
        match = re.match(r'^(\d+)([A-Z]+)(.*)$', form_type)
        if match:
            number = match.group(1)
            letters = match.group(2)
            rest = match.group(3)
            normalized = f"{number}-{letters}{rest}"
            if normalized in normalization_map:
                return normalization_map[normalized]
            return normalized
        
        return form_type
    
    def construct_filing_url(self, cik: str, accession_number: str, primary_document: str) -> str:
        """Construir URL del filing"""
        accession_no_dashes = accession_number.replace('-', '')
        return f"https://www.sec.gov/Archives/edgar/data/{cik}/{accession_no_dashes}/{primary_document}"
    
    def filter_relevant_filings(self, filings: List[Dict]) -> List[Dict]:
        """
        Filtrar filings relevantes para análisis de dilución.
        """
        result = []
        forms_used = set()
        form_type_counts = {}
        unknown_types = set()
        
        year_cutoff = date(2010, 1, 1)
        
        # Tipos relevantes para dilución
        relevant_types = {
            # Tier 1: Shelf Registrations (US + Foreign)
            'S-3', 'S-3/A', 'S-3ASR', 'S-1', 'S-1/A', 'S-8', 'S-11',
            'F-1', 'F-1/A', 'F-3', 'F-3/A', 'F-4', 'F-4/A',
            
            # Tier 2: Annual/Quarterly Reports (US + Foreign)
            '10-K', '10-K/A', '10-Q', '10-Q/A',
            '20-F', '20-F/A', '6-K', '6-K/A',
            
            # Tier 3: Prospectus Supplements
            '424B5', '424B3', '424B4', '424B7', '424B2', 'FWP',
            
            # Tier 4: Current Reports
            '8-K', '8-K/A',
            
            # Tier 5: Proxy & Ownership
            'DEF 14A', 'DEFM14A', 'DEFR14A', 'DEFA14A',
            'SC 13D', 'SC 13G', 'SC 13D/A', 'SC 13G/A',
            
            # Tier 6: Others
            'SC TO-I', 'SC TO-T', 'SC 14D9',
        }
        
        for f in filings:
            form_type = f['form_type']
            form_type_counts[form_type] = form_type_counts.get(form_type, 0) + 1
            
            try:
                filing_date_str = f['filing_date']
                if ' ' in filing_date_str:
                    filing_date_str = filing_date_str.split(' ')[0]
                
                filing_date = datetime.strptime(filing_date_str, '%Y-%m-%d').date()
                
                if filing_date < year_cutoff:
                    continue
            except:
                continue
            
            # Filtering optimization
            if form_type in ['8-K', '8-K/A', '6-K', '6-K/A']:
                three_years_ago = date.today().replace(year=date.today().year - 3)
                if filing_date < three_years_ago:
                    continue

            if form_type.startswith('SC 13') or form_type.startswith('SCHEDULE 13'):
                two_years_ago = date.today().replace(year=date.today().year - 2)
                if filing_date < two_years_ago:
                    continue

            if form_type == 'S-8':
                five_years_ago = date.today().replace(year=date.today().year - 5)
                if filing_date < five_years_ago:
                    continue
            
            if form_type in relevant_types:
                result.append(f)
                forms_used.add(form_type)
            else:
                unknown_types.add(form_type)
        
        logger.info("filings_filtered_for_dilution", 
                   total_input=len(filings), 
                   total_output=len(result), 
                   excluded_count=len(filings) - len(result),
                   forms_used=sorted(list(forms_used)),
                   has_20f='20-F' in forms_used or '20-F/A' in forms_used,
                   has_6k='6-K' in forms_used or '6-K/A' in forms_used)
        
        return result
    
    async def download_filings(self, filings: List[Dict]) -> List[Dict]:
        """
        Descargar contenido HTML de filings con rate limiting
        """
        results = []
        
        headers = {
            "User-Agent": "TradeulApp contact@tradeul.com"
        }
        
        async with httpx.AsyncClient(timeout=60.0, follow_redirects=True) as client:
            consecutive_429s = 0
            for idx, filing in enumerate(filings):
                try:
                    if idx > 0:
                        await asyncio.sleep(self.SEC_RATE_LIMIT_DELAY)
                    
                    response = await client.get(filing['url'], headers=headers)
                    
                    if response.status_code == 200:
                        results.append({
                            'form_type': filing['form_type'],
                            'filing_date': filing['filing_date'],
                            'url': filing['url'],
                            'content': response.text
                        })
                        
                        logger.info("filing_downloaded", 
                                   form_type=filing['form_type'], 
                                   url=filing['url'])
                        consecutive_429s = 0
                    elif response.status_code == 429:
                        consecutive_429s += 1
                        retry_after = response.headers.get('Retry-After')
                        wait_time = float(retry_after) if retry_after and retry_after.isdigit() else (2.0 * consecutive_429s)
                        wait_time = min(wait_time, 10.0)
                        
                        logger.warning("filing_rate_limited", url=filing['url'], 
                                     retry_after=retry_after, 
                                     consecutive=consecutive_429s,
                                     wait_seconds=wait_time)
                        await asyncio.sleep(wait_time)
                    else:
                        logger.warning("filing_download_failed", 
                                     url=filing['url'], 
                                     status=response.status_code)
                        consecutive_429s = 0
                    
                except Exception as e:
                    logger.error("filing_download_error", url=filing['url'], error=str(e))
                    consecutive_429s = 0
        
        return results
    
    # =========================================================================
    # EXHIBITS DOWNLOAD - Para extracción precisa con Gemini
    # =========================================================================
    
    async def download_filings_with_exhibits(
        self, 
        filings: List[Dict],
        download_exhibits: bool = True
    ) -> List[Dict]:
        """
        Descarga filings Y sus exhibits asociados.
        
        Los exhibits contienen datos exactos (conversion_price, terms, etc.)
        que no están en el filing principal.
        
        Args:
            filings: Lista de filings [{url, form_type, filing_date}]
            download_exhibits: Si True, también descarga exhibits
        
        Returns:
            Lista con estructura extendida:
            [{
                "url": "...",
                "form_type": "6-K",
                "filing_date": "2025-09-19",
                "content": "...",
                "exhibits": [
                    {"name": "ex99-1.htm", "url": "...", "content": "..."},
                    {"name": "ex4-1.htm", "url": "...", "content": "..."}
                ]
            }]
        """
        results = []
        
        headers = {
            "User-Agent": "TradeulApp contact@tradeul.com"
        }
        
        async with httpx.AsyncClient(timeout=60.0, follow_redirects=True) as client:
            for idx, filing in enumerate(filings):
                try:
                    if idx > 0:
                        await asyncio.sleep(self.SEC_RATE_LIMIT_DELAY)
                    
                    # 1. Descargar filing principal
                    response = await client.get(filing['url'], headers=headers)
                    
                    if response.status_code != 200:
                        logger.warning("filing_download_failed", 
                                     url=filing['url'], 
                                     status=response.status_code)
                        continue
                    
                    filing_data = {
                        'form_type': filing['form_type'],
                        'filing_date': filing['filing_date'],
                        'url': filing['url'],
                        'content': response.text,
                        'exhibits': []
                    }
                    
                    # 2. Buscar y descargar exhibits si está habilitado
                    if download_exhibits:
                        exhibits = await self._download_exhibits(
                            client, 
                            filing['url'], 
                            headers
                        )
                        filing_data['exhibits'] = exhibits
                        
                        if exhibits:
                            logger.info("exhibits_downloaded",
                                      form_type=filing['form_type'],
                                      filing_url=filing['url'],
                                      exhibit_count=len(exhibits),
                                      exhibit_names=[e['name'] for e in exhibits])
                    
                    results.append(filing_data)
                    
                    logger.info("filing_with_exhibits_downloaded", 
                               form_type=filing['form_type'], 
                               url=filing['url'],
                               has_exhibits=len(filing_data['exhibits']) > 0)
                    
                except Exception as e:
                    logger.error("filing_download_error", 
                               url=filing['url'], 
                               error=str(e))
        
        return results
    
    async def _download_exhibits(
        self,
        client: httpx.AsyncClient,
        filing_url: str,
        headers: Dict
    ) -> List[Dict]:
        """
        Descarga exhibits de un filing.
        
        Busca en el index.html del filing para encontrar exhibits.
        """
        exhibits = []
        
        try:
            # Obtener URL base del filing
            base_url = filing_url.rsplit('/', 1)[0] + "/"
            
            # Intentar descargar index.html
            index_url = base_url + "index.html"
            await asyncio.sleep(0.15)  # Rate limit
            
            response = await client.get(index_url, headers=headers)
            
            if response.status_code != 200:
                # Fallback: intentar index.json
                index_url = base_url + "index.json"
                await asyncio.sleep(0.15)
                response = await client.get(index_url, headers=headers)
                
                if response.status_code == 200:
                    exhibits = await self._parse_exhibits_from_json(
                        client, response.text, base_url, headers
                    )
                return exhibits
            
            # Parsear index.html para encontrar exhibits
            exhibits = await self._parse_exhibits_from_html(
                client, response.text, base_url, headers
            )
            
        except Exception as e:
            logger.warning("exhibit_download_error", 
                         filing_url=filing_url, 
                         error=str(e))
        
        return exhibits
    
    async def _parse_exhibits_from_html(
        self,
        client: httpx.AsyncClient,
        index_html: str,
        base_url: str,
        headers: Dict
    ) -> List[Dict]:
        """Parsea index.html para extraer y descargar exhibits."""
        exhibits = []
        
        soup = BeautifulSoup(index_html, 'html.parser')
        
        # Buscar todos los links a exhibits
        for link in soup.find_all('a', href=True):
            href = link.get('href', '')
            name = href.split('/')[-1].lower()
            
            if self._is_relevant_exhibit(name):
                exhibit_url = base_url + name
                
                await asyncio.sleep(0.15)  # Rate limit
                
                try:
                    response = await client.get(exhibit_url, headers=headers)
                    
                    if response.status_code == 200 and len(response.text) > 500:
                        exhibits.append({
                            'name': name,
                            'url': exhibit_url,
                            'content': response.text,
                            'description': link.get_text()[:100].strip()
                        })
                except Exception as e:
                    logger.warning("exhibit_file_download_failed",
                                 exhibit_url=exhibit_url,
                                 error=str(e))
        
        return exhibits
    
    async def _parse_exhibits_from_json(
        self,
        client: httpx.AsyncClient,
        index_json: str,
        base_url: str,
        headers: Dict
    ) -> List[Dict]:
        """Parsea index.json para extraer y descargar exhibits."""
        exhibits = []
        
        try:
            import json
            data = json.loads(index_json)
            
            items = data.get('directory', {}).get('item', [])
            
            for item in items:
                name = item.get('name', '').lower()
                
                if self._is_relevant_exhibit(name):
                    exhibit_url = base_url + name
                    
                    await asyncio.sleep(0.15)
                    
                    try:
                        response = await client.get(exhibit_url, headers=headers)
                        
                        if response.status_code == 200 and len(response.text) > 500:
                            exhibits.append({
                                'name': name,
                                'url': exhibit_url,
                                'content': response.text,
                                'description': item.get('description', '')[:100]
                            })
                    except:
                        pass
        except:
            pass
        
        return exhibits
    
    def _is_relevant_exhibit(self, filename: str) -> bool:
        """
        Determina si un archivo es un exhibit relevante para dilución.
        
        Exhibits importantes:
        - ex4-X.htm: Form of warrant, note, securities
        - ex10-X.htm: Securities Purchase Agreement, SPA
        - ex99-X.htm: Press releases con detalles de offerings
        """
        if not filename:
            return False
        
        name = filename.lower()
        
        # Debe terminar en .htm o .html
        if not (name.endswith('.htm') or name.endswith('.html')):
            return False
        
        # Patrones de exhibits relevantes
        import re
        relevant_patterns = [
            r'^ex4[-_]?\d*\.htm',      # Form of Note, Warrant, Certificate of Designation
            r'^ex10[-_]?\d*\.htm',     # Securities Purchase Agreement, SPA
            r'^ex99[-_]?\d*\.htm',     # Press release, announcement
        ]
        
        for pattern in relevant_patterns:
            if re.match(pattern, name):
                return True
        
        return False


# Singleton instance
_fetcher: Optional[SECFilingFetcher] = None


def get_sec_filing_fetcher(db: Optional[TimescaleClient] = None) -> SECFilingFetcher:
    """Get or create SEC filing fetcher instance"""
    global _fetcher
    if _fetcher is None:
        _fetcher = SECFilingFetcher(db)
    return _fetcher

