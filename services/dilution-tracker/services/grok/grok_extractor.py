"""
Grok Extractor
==============
Servicio para extracción de datos de dilución usando Grok API.

Este módulo contiene:
- Extracción multipass (múltiples pasadas enfocadas)
- Procesamiento paralelo de chunks
- Upload/cleanup de archivos en Grok
- Prompt building para extracción

ARQUITECTURA:
- Pass 1: SKIP (datos de SEC-API/FMP)
- Pass 2: S-3/S-1/F-3/F-1 (shelf registrations)
- Pass 3: 424B (prospectus supplements) - PARALELO
- Pass 4a: Warrant exercises from 10-Q
- Pass 4b: ATM usage from 10-Q
- Pass 5: S-8 (employee stock plans)
- Pass 6: 8-K/6-K (current reports)
- Pass 7: DEF 14A (proxy statements)
"""

import asyncio
import json
import os
import re
import tempfile
from typing import Any, Dict, List, Optional

from bs4 import BeautifulSoup
from xai_sdk import Client
from xai_sdk.chat import user, system, file

from shared.config.settings import settings
from shared.utils.logger import get_logger

from services.grok.grok_normalizers import (
    normalize_grok_extraction_fields,
    normalize_grok_value,
    safe_get_for_key,
)
from services.analysis.deduplication_service import (
    deduplicate_warrants,
    deduplicate_atm,
    deduplicate_shelfs,
    deduplicate_completed,
    deduplicate_s1,
    deduplicate_convertible_notes,
    deduplicate_convertible_preferred,
    deduplicate_equity_lines,
    filter_summary_warrants,
    impute_missing_exercise_prices,
    classify_warrant_status,
    classify_atm_status,
    classify_shelf_status,
    calculate_remaining_warrants,
)
from services.extraction.html_section_extractor import HTMLSectionExtractor
from services.data.enhanced_data_fetcher import quick_dilution_scan

logger = get_logger(__name__)


class GrokExtractor:
    """
    Extractor de datos de dilución usando Grok API.
    """
    
    def __init__(self, grok_pool: Any = None, grok_api_key: str = None):
        """
        Args:
            grok_pool: Pool de clientes Grok para procesamiento paralelo
            grok_api_key: API key de Grok (fallback)
        """
        self._grok_pool = grok_pool
        self.grok_api_key = grok_api_key or settings.GROK_API_KEY
        self.html_extractor = HTMLSectionExtractor(grok_pool, grok_api_key)
        
        # Stats for optimization
        self._stats = {
            "grok_calls": 0,
            "grok_calls_parallel": 0,
            "skipped_prescreening": 0,
        }
    
    def calculate_optimal_chunk_size(
        self, 
        filings: List[Dict], 
        form_type_hint: str = ""
    ) -> int:
        """
        Calcular el tamaño óptimo de chunk basado en el tamaño promedio de los filings.
        """
        if not filings:
            return 5
        
        # Calcular tamaño promedio
        total_size = sum(len(f.get('content', '')) for f in filings)
        avg_size = total_size / len(filings)
        
        # Ajustar chunk size basado en tamaño promedio
        if avg_size > 500_000:  # >500KB
            return 2
        elif avg_size > 200_000:  # >200KB
            return 3
        elif avg_size > 100_000:  # >100KB
            return 5
        else:
            return 8
    
    async def extract_with_multipass_grok(
        self,
        ticker: str,
        company_name: str,
        filing_contents: List[Dict],
        parsed_tables: Optional[Dict] = None
    ) -> Optional[Dict]:
        """
        MULTI-PASS EXTRACTION: Analizar en múltiples pasadas enfocadas.
        
        Returns:
            Dict combinado con warrants, atm_offerings, shelf_registrations, etc.
        """
        try:
            all_warrants = []
            all_atm = []
            all_shelfs = []
            all_completed = []
            all_s1 = []
            all_convertible_notes = []
            all_convertible_preferred = []
            all_equity_lines = []
            
            logger.info("multipass_extraction_start", ticker=ticker, total_filings=len(filing_contents))
            
            # Pass 2: S-3/S-1/F-3/F-1 (Shelf Registrations)
            filings_s3 = [f for f in filing_contents if f['form_type'] in [
                'S-3', 'S-3/A', 'S-1', 'S-1/A', 'S-11', 'F-3', 'F-3/A', 'F-1', 'F-1/A'
            ]]
            if filings_s3:
                logger.info("pass2_s3_start", ticker=ticker, count=len(filings_s3))
                chunk_size = 5
                for i in range(0, len(filings_s3), chunk_size):
                    chunk = filings_s3[i:i+chunk_size]
                    self._stats["grok_calls"] += 1
                    result = await self._extract_pass_focused(
                        ticker, company_name, chunk,
                        focus="Extract SHELF REGISTRATIONS with TOTAL_CAPACITY, registration_statement type (S-3, S-1, F-3, F-1), effect_date, expiration_date. Also extract ATM agreements."
                    )
                    if result:
                        all_shelfs.extend(result.get('shelf_registrations', []))
                        all_s1.extend(result.get('s1_offerings', []))
                        all_atm.extend(result.get('atm_offerings', []))
            
            # Pass 3: 424B (Prospectus Supplements) - PARALELO
            filings_424b = [f for f in filing_contents if f['form_type'] in ['424B5', '424B3', '424B7', '424B4']]
            if filings_424b:
                chunk_size = self.calculate_optimal_chunk_size(filings_424b, "424B")
                logger.info("pass3_424b_start", ticker=ticker, count=len(filings_424b), chunk_size=chunk_size)
                
                chunks = [filings_424b[i:i+chunk_size] for i in range(0, len(filings_424b), chunk_size)]
                
                use_parallel = self._grok_pool and self._grok_pool.num_keys > 1 and len(chunks) > 2
                
                if use_parallel:
                    results = await self._process_chunks_parallel(
                        ticker, company_name, chunks,
                        focus="Extract ATM offerings with TOTAL_CAPACITY and REMAINING_CAPACITY, placement_agent. Extract warrants with exercise_price, outstanding, expiration. Extract completed offerings."
                    )
                    for result in results:
                        if result:
                            all_warrants.extend(result.get('warrants', []))
                            all_atm.extend(result.get('atm_offerings', []))
                            all_shelfs.extend(result.get('shelf_registrations', []))
                            all_completed.extend(result.get('completed_offerings', []))
                            all_s1.extend(result.get('s1_offerings', []))
                            all_convertible_notes.extend(result.get('convertible_notes', []))
                            all_equity_lines.extend(result.get('equity_lines', []))
                else:
                    for chunk in chunks:
                        self._stats["grok_calls"] += 1
                        result = await self._extract_pass_focused(
                            ticker, company_name, chunk,
                            focus="Extract ATM offerings with TOTAL_CAPACITY and REMAINING_CAPACITY, placement_agent. Extract warrants with exercise_price, outstanding, expiration."
                        )
                        if result:
                            all_warrants.extend(result.get('warrants', []))
                            all_atm.extend(result.get('atm_offerings', []))
                            all_completed.extend(result.get('completed_offerings', []))
            
            # Pass 4a: Warrant exercises from 10-Q
            filings_10q = [f for f in filing_contents if f['form_type'] in ['10-Q', '10-Q/A', '10-K', '10-K/A']]
            if filings_10q:
                filings_10q_recent = sorted(filings_10q, key=lambda x: x.get('filing_date', ''), reverse=True)[:4]
                
                warrant_sections = []
                for f in filings_10q_recent:
                    section = self.html_extractor.extract_warrant_section(f.get('content', ''))
                    if section:
                        warrant_sections.append({
                            'form_type': f['form_type'],
                            'filing_date': f['filing_date'],
                            'content': section
                        })
                
                if warrant_sections:
                    exercises = await self.html_extractor.extract_warrant_exercises(
                        ticker, company_name, warrant_sections
                    )
                    if exercises:
                        all_warrants.extend(exercises)
            
            # Pass 4b: ATM usage from 10-Q
            atm_usage_total = 0
            if filings_10q:
                filings_10q_recent = sorted(filings_10q, key=lambda x: x.get('filing_date', ''), reverse=True)[:4]
                
                for f in filings_10q_recent[:2]:
                    atm_section = self.html_extractor.extract_atm_section(f.get('content', ''))
                    if atm_section:
                        usage = await self.html_extractor.extract_atm_usage_from_section(
                            ticker, atm_section, f['filing_date']
                        )
                        if usage and usage > 0:
                            atm_usage_total = max(atm_usage_total, usage)
                
                if atm_usage_total > 0:
                    for atm in all_atm:
                        total = atm.get('total_capacity')
                        if total:
                            remaining = max(0, float(total) - atm_usage_total)
                            atm['remaining_capacity'] = remaining
                            atm['_usage_from_10q'] = atm_usage_total
            
            # Pass 5: 6-K (Foreign reports)
            filings_6k = [f for f in filing_contents if f['form_type'] in ['6-K', '6-K/A']]
            if filings_6k:
                filings_6k_filtered = []
                for f in filings_6k:
                    has_dilution, _ = quick_dilution_scan(f.get('content', ''), f['form_type'])
                    if has_dilution:
                        filings_6k_filtered.append(f)
                
                self._stats["skipped_prescreening"] += len(filings_6k) - len(filings_6k_filtered)
                
                if filings_6k_filtered:
                    chunk_size = 5
                    for i in range(0, len(filings_6k_filtered), chunk_size):
                        chunk = filings_6k_filtered[i:i+chunk_size]
                        self._stats["grok_calls"] += 1
                        result = await self._extract_pass_focused(
                            ticker, company_name, chunk,
                            focus="Foreign company reports (6-K) - extract ATM offerings, warrant issuances, shelf registration updates."
                        )
                        if result:
                            all_warrants.extend(result.get('warrants', []))
                            all_atm.extend(result.get('atm_offerings', []))
                            all_convertible_notes.extend(result.get('convertible_notes', []))
            
            # Pass 6: 8-K (Current reports)
            filings_8k = [f for f in filing_contents if f['form_type'] in ['8-K', '8-K/A']]
            if filings_8k:
                filings_8k_filtered = []
                for f in filings_8k:
                    has_dilution, _ = quick_dilution_scan(f.get('content', ''))
                    if has_dilution:
                        filings_8k_filtered.append(f)
                
                self._stats["skipped_prescreening"] += len(filings_8k) - len(filings_8k_filtered)
                
                if filings_8k_filtered:
                    chunk_size = self.calculate_optimal_chunk_size(filings_8k_filtered, "8-K")
                    chunks = [filings_8k_filtered[i:i+chunk_size] for i in range(0, len(filings_8k_filtered), chunk_size)]
                    
                    results = await self._process_chunks_parallel(
                        ticker, company_name, chunks,
                        focus="Current reports - extract convertible notes, equity lines, ATM agreements, warrant issuances."
                    )
                    
                    for result in results:
                        if result:
                            all_warrants.extend(result.get('warrants', []))
                            all_atm.extend(result.get('atm_offerings', []))
                            all_convertible_notes.extend(result.get('convertible_notes', []))
                            all_equity_lines.extend(result.get('equity_lines', []))
            
            # Pre-dedup logging
            logger.info("pre_dedup_counts", ticker=ticker,
                       raw_warrants=len(all_warrants), raw_atm=len(all_atm),
                       raw_shelfs=len(all_shelfs), raw_completed=len(all_completed))
            
            # Process warrants
            warrants_deduped = deduplicate_warrants(all_warrants)
            warrants_filtered = filter_summary_warrants(warrants_deduped)
            warrants_imputed = impute_missing_exercise_prices(warrants_filtered)
            warrants_classified = classify_warrant_status(warrants_imputed, ticker)
            warrants_final = deduplicate_warrants(warrants_classified)
            warrants_final = calculate_remaining_warrants(warrants_final)
            
            # Process ATM and Shelfs
            atm_deduped = deduplicate_atm(all_atm, ticker=ticker)
            atm_classified = classify_atm_status(atm_deduped, ticker)
            
            shelfs_deduped = deduplicate_shelfs(all_shelfs, ticker=ticker)
            shelfs_classified = classify_shelf_status(shelfs_deduped, ticker)
            
            combined_data = {
                'warrants': warrants_final,
                'atm_offerings': atm_classified,
                'shelf_registrations': shelfs_classified,
                'completed_offerings': deduplicate_completed(all_completed, ticker=ticker),
                's1_offerings': deduplicate_s1(all_s1),
                'convertible_notes': deduplicate_convertible_notes(all_convertible_notes),
                'convertible_preferred': deduplicate_convertible_preferred(all_convertible_preferred),
                'equity_lines': deduplicate_equity_lines(all_equity_lines)
            }
            
            logger.info("multipass_completed", ticker=ticker,
                       total_warrants=len(combined_data['warrants']),
                       total_atm=len(combined_data['atm_offerings']),
                       total_shelfs=len(combined_data['shelf_registrations']),
                       grok_calls=self._stats["grok_calls"],
                       skipped=self._stats["skipped_prescreening"])
            
            return combined_data
            
        except Exception as e:
            logger.error("multipass_extraction_failed", ticker=ticker, error=str(e))
            return None
    
    async def _process_chunks_parallel(
        self,
        ticker: str,
        company_name: str,
        chunks: List[List[Dict]],
        focus: str,
        parsed_tables: Optional[Dict] = None,
        max_concurrent: Optional[int] = None
    ) -> List[Optional[Dict]]:
        """
        Procesar múltiples chunks en paralelo usando GrokPool.
        """
        if not chunks:
            return []
        
        if not self._grok_pool or self._grok_pool.num_keys < 2:
            # Fallback secuencial
            results = []
            for chunk in chunks:
                self._stats["grok_calls"] += 1
                result = await self._extract_pass_focused(
                    ticker, company_name, chunk, focus, parsed_tables
                )
                results.append(result)
            return results
        
        max_concurrent = max_concurrent or min(self._grok_pool.num_keys * 2, len(chunks))
        
        async def process_chunk(chunk_idx: int, chunk: List[Dict]) -> Optional[Dict]:
            try:
                self._stats["grok_calls_parallel"] += 1
                result = await self._extract_pass_focused(
                    ticker, company_name, chunk, focus, parsed_tables
                )
                logger.debug("chunk_processed", ticker=ticker, chunk_idx=chunk_idx, 
                           success=result is not None)
                return result
            except Exception as e:
                logger.warning("chunk_process_error", ticker=ticker, chunk_idx=chunk_idx, error=str(e))
                return None
        
        # Process in batches
        all_results = []
        for batch_start in range(0, len(chunks), max_concurrent):
            batch_end = min(batch_start + max_concurrent, len(chunks))
            batch = chunks[batch_start:batch_end]
            
            tasks = [
                process_chunk(batch_start + i, chunk)
                for i, chunk in enumerate(batch)
            ]
            
            batch_results = await asyncio.gather(*tasks, return_exceptions=True)
            
            for result in batch_results:
                if isinstance(result, Exception):
                    logger.warning("parallel_chunk_exception", error=str(result))
                    all_results.append(None)
                else:
                    all_results.append(result)
        
        logger.info("chunk_processor_completed", ticker=ticker, 
                   total_chunks=len(chunks), successful=sum(1 for r in all_results if r))
        
        return all_results
    
    async def _extract_pass_focused(
        self,
        ticker: str,
        company_name: str,
        filings: List[Dict],
        focus: str,
        parsed_tables: Optional[Dict] = None
    ) -> Optional[Dict]:
        """
        Extraer datos de un conjunto de filings con un focus específico.
        """
        total_size = sum(len(f.get('content', '')) for f in filings)
        
        critical_forms = {'F-3', 'F-3/A', 'S-3', 'S-3/A', 'F-1', 'F-1/A', 'S-1', 'S-1/A'}
        has_critical = any(f.get('form_type', '') in critical_forms for f in filings)
        
        if total_size < 300_000 and not has_critical:
            return await self._extract_pass_direct_prompt(
                ticker, company_name, filings, focus, parsed_tables
            )
        
        return await self._extract_pass_with_files_api(
            ticker, company_name, filings, focus, parsed_tables
        )
    
    async def _extract_pass_direct_prompt(
        self,
        ticker: str,
        company_name: str,
        filings: List[Dict],
        focus: str,
        parsed_tables: Optional[Dict] = None,
        max_retries: int = 3
    ) -> Optional[Dict]:
        """
        Extraer usando prompt directo (para filings pequeños).
        """
        try:
            # Build prompt with filing content
            filings_text = ""
            for f in filings:
                content = f.get('content', '')[:50000]  # Limit per filing
                filings_text += f"\n=== {f['form_type']} filed {f['filing_date']} ===\n"
                # Basic HTML cleanup
                content = re.sub(r'<[^>]+>', ' ', content)
                content = re.sub(r'\s+', ' ', content)
                filings_text += content[:40000]
            
            prompt = self._build_extraction_prompt(ticker, company_name, filings_text, focus)
            
            client = None
            pool_idx = None
            
            try:
                if self._grok_pool:
                    client, pool_idx = self._grok_pool.get_client()
                
                if not client:
                    client = Client(api_key=self.grok_api_key, timeout=120)
                
                response = await asyncio.get_event_loop().run_in_executor(
                    None,
                    lambda: client.chat.completions.create(
                        model="grok-3-fast",
                        messages=[{"role": "user", "content": prompt}],
                        temperature=0.1,
                        max_tokens=4000
                    )
                )
                
                if self._grok_pool and pool_idx is not None:
                    self._grok_pool.release(pool_idx, success=True)
                
                response_text = response.choices[0].message.content
                
                # Parse JSON
                json_match = re.search(r'\{[\s\S]*\}', response_text)
                if json_match:
                    data = json.loads(json_match.group(0))
                    return normalize_grok_extraction_fields(data)
                
                return None
                
            except Exception as e:
                logger.warning("direct_prompt_error", ticker=ticker, error=str(e))
                if self._grok_pool and pool_idx is not None:
                    self._grok_pool.release(pool_idx, success=False, error=str(e))
                return None
                
        except Exception as e:
            logger.error("extract_pass_direct_prompt_failed", ticker=ticker, error=str(e))
            return None
    
    async def _extract_pass_with_files_api(
        self,
        ticker: str,
        company_name: str,
        filings: List[Dict],
        focus: str,
        parsed_tables: Optional[Dict] = None,
        max_retries: int = 3
    ) -> Optional[Dict]:
        """
        Extraer usando Grok Files API (para filings grandes).
        """
        uploaded_file_ids = []
        client = None
        pool_idx = None
        
        try:
            if self._grok_pool:
                client, pool_idx = self._grok_pool.get_client()
            
            if not client:
                client = Client(api_key=self.grok_api_key, timeout=180)
            
            # Upload filings
            for f in filings:
                file_id = await self._upload_filing_to_grok(
                    ticker, f['form_type'], f['filing_date'], f.get('content', ''), client
                )
                if file_id:
                    uploaded_file_ids.append(file_id)
            
            if not uploaded_file_ids:
                logger.warning("no_files_uploaded", ticker=ticker)
                return await self._extract_pass_direct_prompt(
                    ticker, company_name, filings, focus, parsed_tables
                )
            
            prompt = self._build_extraction_prompt(ticker, company_name, "", focus)
            
            # Build messages with file references
            messages = [user(prompt)]
            for file_id in uploaded_file_ids:
                messages.append(file(file_id))
            
            chat = client.chat.create(model="grok-3-fast", temperature=0.1)
            for msg in messages:
                chat.append(msg)
            
            response = await asyncio.get_event_loop().run_in_executor(
                None, chat.sample
            )
            
            if self._grok_pool and pool_idx is not None:
                self._grok_pool.release(pool_idx, success=True)
            
            # Parse response
            response_text = response.content if hasattr(response, 'content') else str(response)
            
            json_match = re.search(r'\{[\s\S]*\}', response_text)
            if json_match:
                data = json.loads(json_match.group(0))
                return normalize_grok_extraction_fields(data)
            
            return None
            
        except Exception as e:
            logger.error("extract_pass_files_api_failed", ticker=ticker, error=str(e))
            if self._grok_pool and pool_idx is not None:
                self._grok_pool.release(pool_idx, success=False, error=str(e))
            return None
            
        finally:
            # Cleanup uploaded files
            if uploaded_file_ids and client:
                await self._cleanup_grok_files(uploaded_file_ids, client)
    
    async def _upload_filing_to_grok(
        self,
        ticker: str,
        form_type: str,
        filing_date: str,
        filing_content: str,
        grok_client: Client
    ) -> Optional[str]:
        """Upload a filing to Grok Files API."""
        try:
            temp_file = tempfile.NamedTemporaryFile(
                mode='w', suffix='.html', 
                prefix=f'{ticker}_{form_type}_{filing_date}_',
                delete=False, encoding='utf-8'
            )
            
            try:
                temp_file.write(filing_content)
                temp_file.close()
                
                uploaded_file = grok_client.files.upload(temp_file.name)
                
                logger.info("filing_uploaded", ticker=ticker, form_type=form_type, 
                           file_id=uploaded_file.id, size=uploaded_file.size)
                
                return uploaded_file.id
                
            finally:
                try:
                    os.unlink(temp_file.name)
                except:
                    pass
                    
        except Exception as e:
            logger.error("upload_filing_failed", ticker=ticker, form_type=form_type, error=str(e))
            return None
    
    async def _cleanup_grok_files(self, file_ids: List[str], grok_client: Client):
        """Cleanup uploaded files from Grok."""
        for file_id in file_ids:
            try:
                grok_client.files.delete(file_id)
            except:
                pass
    
    def _build_extraction_prompt(
        self,
        ticker: str,
        company_name: str,
        filings_text: str,
        focus: str
    ) -> str:
        """Build the extraction prompt for Grok."""
        return f"""
You are an EXPERT financial data extraction specialist analyzing SEC EDGAR filings for {company_name} (Ticker: {ticker}).

YOUR MISSION: Extract COMPREHENSIVE dilution data with MAXIMUM detail and accuracy.

FOCUS: {focus}

{f"FILINGS CONTENT:{filings_text}" if filings_text else "Analyze the uploaded files."}

=== EXTRACT THE FOLLOWING (JSON only, no markdown) ===

{{
  "warrants": [
    {{"outstanding": number, "exercise_price": number, "expiration_date": "YYYY-MM-DD", "issue_date": "YYYY-MM-DD", "notes": "description"}}
  ],
  "atm_offerings": [
    {{"total_capacity": number, "remaining_capacity": number, "placement_agent": "string", "agreement_date": "YYYY-MM-DD", "filing_date": "YYYY-MM-DD"}}
  ],
  "shelf_registrations": [
    {{"total_capacity": number, "remaining_capacity": number, "registration_statement": "S-3/S-1/F-3/F-1", "effect_date": "YYYY-MM-DD", "expiration_date": "YYYY-MM-DD", "is_baby_shelf": boolean}}
  ],
  "completed_offerings": [
    {{"offering_type": "string", "shares_issued": number, "price_per_share": number, "amount_raised": number, "offering_date": "YYYY-MM-DD"}}
  ],
  "s1_offerings": [],
  "convertible_notes": [],
  "convertible_preferred": [],
  "equity_lines": []
}}

RULES:
1. Convert dollar amounts to numbers: "$75 million" = 75000000
2. Dates in YYYY-MM-DD format
3. Return EMPTY ARRAYS [] if no data found
4. Be thorough - search entire document
"""


# Singleton instance
_extractor: Optional[GrokExtractor] = None


def get_grok_extractor(grok_pool: Any = None, grok_api_key: str = None) -> GrokExtractor:
    """Get or create Grok extractor instance"""
    global _extractor
    if _extractor is None:
        _extractor = GrokExtractor(grok_pool, grok_api_key)
    return _extractor

