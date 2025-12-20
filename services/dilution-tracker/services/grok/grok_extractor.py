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
            
            # Pass 4c: Extract Convertible Notes from 10-K/10-Q (primary source - has full details)
            # 10-K/10-Q have complete debt footnotes with total/remaining principal, conversion rates, etc.
            filings_10k = [f for f in filing_contents if f['form_type'] in ['10-K', '10-K/A']]
            filings_annual_quarterly = filings_10q[:3] + filings_10k[:2]  # Recent 10-Qs and 10-Ks
            
            if filings_annual_quarterly:
                logger.info("pass4c_convertible_notes_start", ticker=ticker, 
                           filings=len(filings_annual_quarterly))
                
                # Extract convertible notes with FULL details from 10-K/10-Q
                result = await self._extract_pass_focused(
                    ticker, company_name, filings_annual_quarterly,
                    focus="""CRITICAL: Extract ALL CONVERTIBLE NOTES from Debt/Long-Term Debt footnotes.

SEARCH FOR these exact phrases in the financial statement notes:
- "Convertible Notes" or "Convertible Senior Notes" or "Senior Convertible Notes"
- "Notes due [year]" (e.g., "1.25% Convertible Senior Notes due 2025")
- "conversion rate" (e.g., "107.2113 shares per $1,000 principal")
- "aggregate principal amount"

EXTRACT these specific values:
- series_name: EXACT name like "1.25% Convertible Senior Notes due 2025"
- total_principal_amount: Original issuance amount in DOLLARS (e.g., $143,800,000)
- remaining_principal_amount: Current outstanding amount (total minus repurchases/conversions)
- conversion_rate: Shares per $1,000 principal (e.g., 107.2113)
- conversion_price: Calculate as $1000 / conversion_rate (e.g., $9.33)
- interest_rate: Coupon rate as percentage (e.g., 1.25)
- issue_date: When notes were originally issued
- maturity_date: When notes are due

DO NOT return 0 for amounts - extract the ACTUAL numbers from the text.
If notes were partially repurchased, remaining = total - repurchased amount."""
                )
                
                # Log what Grok returned
                logger.info("pass4c_grok_response", ticker=ticker, 
                           has_result=bool(result),
                           convertible_notes_count=len(result.get('convertible_notes', [])) if result else 0,
                           raw_notes=result.get('convertible_notes', [])[:2] if result else None)
                
                if result and result.get('convertible_notes'):
                    for note in result.get('convertible_notes', []):
                        # Log each note's raw data
                        logger.debug("pass4c_note_raw", ticker=ticker, note=note)
                        
                        # Calculate conversion_price from rate if not directly provided
                        conv_rate = note.get('conversion_rate') or note.get('conversion_ratio')
                        if conv_rate and float(conv_rate) > 0:
                            if not note.get('conversion_price') or float(note.get('conversion_price', 0)) == 0:
                                note['conversion_price'] = 1000.0 / float(conv_rate)
                        
                        # Add ALL notes with series_name, even if principal is 0
                        # (Grok might have the note but missed the amounts)
                        total_principal = note.get('total_principal_amount', 0) or 0
                        series_name = note.get('series_name')
                        
                        if series_name or total_principal > 0:
                            all_convertible_notes.append(note)
                            logger.info("convertible_note_extracted", ticker=ticker,
                                       series=series_name,
                                       total=total_principal,
                                       remaining=note.get('remaining_principal_amount'),
                                       conv_price=note.get('conversion_price'),
                                       conv_rate=conv_rate)
                else:
                    logger.warning("pass4c_no_convertible_notes", ticker=ticker, 
                                  result_keys=list(result.keys()) if result else None)
            
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
                    client, _, pool_idx = await self._grok_pool.get_client()
                
                if not client:
                    client = Client(api_key=self.grok_api_key, timeout=120)
                
                def _make_request():
                    chat = client.chat.create(model="grok-3-fast", temperature=0.1, max_tokens=4000)
                    chat.append(user(prompt))
                    return chat.sample()
                
                response = await asyncio.get_event_loop().run_in_executor(None, _make_request)
                
                if self._grok_pool and pool_idx is not None:
                    self._grok_pool.release(pool_idx, success=True)
                
                response_text = response.content
                
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
                client, _, pool_idx = await self._grok_pool.get_client()
            
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
            
            # Build user message with file references as additional arguments
            # According to xAI SDK docs: user(prompt, file(id1), file(id2), ...)
            file_refs = [file(fid) for fid in uploaded_file_ids]
            user_message = user(prompt, *file_refs)
            
            # Use grok-4-fast for Files API (requires agentic model)
            chat = client.chat.create(model="grok-4-fast", temperature=0.1)
            chat.append(user_message)
            
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
You are an ELITE forensic financial analyst extracting dilution data from SEC EDGAR filings for {company_name} (Ticker: {ticker}).

FOCUS: {focus}

{f"FILINGS CONTENT:{filings_text}" if filings_text else "Analyze the uploaded files thoroughly."}

=== EXTRACT ALL FIELDS FOR EACH INSTRUMENT (JSON only, no markdown) ===

{{
  "warrants": [
    {{
      "series_name": "August 2025 Warrants / Series A Warrants / etc.",
      "outstanding": number,
      "total_issued": number,
      "exercise_price": number,
      "original_exercise_price": number,
      "expiration_date": "YYYY-MM-DD",
      "issue_date": "YYYY-MM-DD",
      "exercisable_date": "YYYY-MM-DD",
      "is_registered": true/false,
      "registration_type": "EDGAR/Not Registered",
      "is_prefunded": true/false,
      "has_cashless_exercise": true/false,
      "warrant_coverage_ratio": number,
      "known_owners": "Mateo Financing, Cavalry, etc. or null",
      "underwriter_agent": "H.C. Wainwright or null",
      "price_protection": "Full Ratchet/Reset/Customary Anti-Dilution/None",
      "price_protection_clause": "Exact text from filing or null",
      "anti_dilution_provision": true/false,
      "notes": "Pre-funded, callable, penny warrants, etc."
    }}
  ],
  "convertible_notes": [
    {{
      "series_name": "November 2020 Convertible Notes Due 2025 / 1.25% Senior Notes / etc.",
      "total_principal_amount": number,
      "remaining_principal_amount": number,
      "conversion_price": number,
      "original_conversion_price": number,
      "conversion_ratio": number,
      "total_shares_when_converted": number,
      "remaining_shares_when_converted": number,
      "interest_rate": number,
      "issue_date": "YYYY-MM-DD",
      "convertible_date": "YYYY-MM-DD",
      "maturity_date": "YYYY-MM-DD",
      "is_registered": true/false,
      "registration_type": "EDGAR/Not Registered",
      "known_owners": "names or null",
      "underwriter_agent": "name or null",
      "price_protection": "Full Ratchet/Variable Rate (TOXIC)/Customary Anti-Dilution/None",
      "price_protection_clause": "Exact text: If stock trades below $X for Y days... or null",
      "variable_rate_adjustment": true/false,
      "floor_price": number,
      "is_toxic": true/false,
      "notes": "1.25% Convertible Senior Notes, repurchase program, etc."
    }}
  ],
  "convertible_preferred": [
    {{
      "series_name": "Series A/B/C Convertible Preferred",
      "total_shares_issued": number,
      "remaining_shares": number,
      "total_dollar_amount": number,
      "remaining_dollar_amount": number,
      "conversion_price": number,
      "original_conversion_price": number,
      "conversion_ratio": number,
      "total_shares_when_converted": number,
      "remaining_shares_when_converted": number,
      "liquidation_preference": number,
      "dividend_rate": number,
      "is_cumulative": true/false,
      "issue_date": "YYYY-MM-DD",
      "convertible_date": "YYYY-MM-DD",
      "maturity_date": "YYYY-MM-DD or null",
      "is_registered": true/false,
      "known_owners": "C/M Capital, WVP or null",
      "underwriter_agent": "Thinkequity, Benchmark or null",
      "price_protection": "Full Ratchet/Customary Anti-Dilution/None",
      "price_protection_clause": "Exact text or null",
      "exchange_cap_19_99_pct": true/false,
      "notes": "description"
    }}
  ],
  "atm_offerings": [
    {{
      "series_name": "January 2023 Cantor ATM / H.C. Wainwright ATM / etc.",
      "total_capacity": number,
      "remaining_capacity": number,
      "amount_raised_to_date": number,
      "registered_shares": number,
      "placement_agent": "H.C. Wainwright/Cantor/BTIG/etc.",
      "broker_dealer": "name or null",
      "agreement_date": "YYYY-MM-DD",
      "expiration_date": "YYYY-MM-DD or null",
      "last_update_date": "YYYY-MM-DD",
      "is_baby_shelf_limited": true/false,
      "remaining_capacity_without_baby_shelf": number,
      "commission_rate": number,
      "notes": "pricing terms, status, etc."
    }}
  ],
  "shelf_registrations": [
    {{
      "series_name": "October 2024 Shelf / November 2021 Shelf / etc.",
      "total_capacity": number,
      "remaining_capacity": number,
      "current_raisable_amount": number,
      "amount_raised": number,
      "amount_raised_last_12_months": number,
      "registration_statement": "S-3/S-1/F-3/F-1/S-3ASR",
      "effect_date": "YYYY-MM-DD",
      "expiration_date": "YYYY-MM-DD",
      "last_update_date": "YYYY-MM-DD",
      "is_baby_shelf": true/false,
      "shares_outstanding": number,
      "public_float": number,
      "highest_60_day_close": number,
      "ib6_float_value": number,
      "price_to_exceed_baby_shelf": number,
      "last_banker": "underwriter name or null",
      "is_mixed_shelf": true/false,
      "is_primary_offering": true/false,
      "is_resale": true/false,
      "notes": "description"
    }}
  ],
  "equity_lines": [
    {{
      "series_name": "Lincoln Park ELOC / Keystone Purchase Agreement / etc.",
      "total_commitment": number,
      "remaining_commitment": number,
      "amount_used": number,
      "estimated_shares_remaining": number,
      "partner": "Lincoln Park Capital/Keystone Capital/etc.",
      "agreement_date": "YYYY-MM-DD",
      "expiration_date": "YYYY-MM-DD",
      "last_update_date": "YYYY-MM-DD",
      "nasdaq_20_pct_limit_shares": number,
      "pricing_discount": number,
      "daily_purchase_limit": number,
      "notes": "description"
    }}
  ],
  "s1_offerings": [
    {{
      "series_name": "IPO / Follow-On / Resale Registration",
      "offering_type": "IPO/Follow-On/Resale/Secondary",
      "total_shares": number,
      "price_per_share": number,
      "total_amount": number,
      "underwriter": "name or null",
      "filing_date": "YYYY-MM-DD",
      "effect_date": "YYYY-MM-DD",
      "is_resale": true/false,
      "selling_shareholders": "names or null",
      "notes": "description"
    }}
  ],
  "completed_offerings": [
    {{
      "offering_type": "Private Placement/Underwritten/ATM/PIPE/Direct/Registered Direct",
      "method": "S-1/S-3/Direct/Private",
      "shares_issued": number,
      "price_per_share": number,
      "amount_raised": number,
      "warrants_issued": number,
      "warrant_exercise_price": number,
      "underwriter": "bank name or null",
      "investors": "names if disclosed or null",
      "offering_date": "YYYY-MM-DD",
      "notes": "description"
    }}
  ]
}}

CRITICAL EXTRACTION RULES:
1. Convert ALL dollar amounts: "$143.8 million" = 143800000, "$93.8M" = 93800000
2. ALL dates in YYYY-MM-DD format
3. Return EMPTY ARRAYS [] ONLY if NO data found
4. EXTRACT ALL FIELDS even if some are null
5. For CONVERTIBLE NOTES: Search "Debt", "Notes Payable", "Convertible Securities" in 10-K/10-Q
6. For WARRANTS: Search "Stockholders' Equity", "Warrant" footnotes
7. For ATM/SHELF: Search 8-K "Distribution Agreement", S-3/424B5 filings
8. Extract HISTORICAL instruments even if converted/repaid/expired
9. Include series_name with date and type (e.g., "November 2020 1.25% Convertible Notes Due 2025")
10. BE THOROUGH - search entire document including ALL footnotes
"""


# Singleton instance
_extractor: Optional[GrokExtractor] = None


def get_grok_extractor(grok_pool: Any = None, grok_api_key: str = None) -> GrokExtractor:
    """Get or create Grok extractor instance"""
    global _extractor
    if _extractor is None:
        _extractor = GrokExtractor(grok_pool, grok_api_key)
    return _extractor

