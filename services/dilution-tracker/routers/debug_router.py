"""
Debug Router - Endpoints para debugging del pipeline de extracción
===================================================================
Permite ver el estado de cada etapa del proceso de extracción.
"""

import httpx
from fastapi import APIRouter, Query, HTTPException
from typing import Dict, List, Optional
import structlog

from services.extraction.contextual_extractor import ContextualDilutionExtractor, SECAPIClient
from services.extraction.semantic_deduplicator import SemanticDeduplicator, _create_fingerprint
from shared.config.settings import settings

logger = structlog.get_logger(__name__)

router = APIRouter(prefix="/api/debug", tags=["debug"])


async def _get_cik_for_ticker(ticker: str) -> Optional[str]:
    """Helper para obtener CIK de un ticker usando SEC.gov"""
    async with httpx.AsyncClient(timeout=30) as client:
        # Método 1: SEC.gov company tickers JSON
        try:
            response = await client.get(
                "https://www.sec.gov/files/company_tickers.json",
                headers={"User-Agent": "Tradeul Research contact@tradeul.com"}
            )
            if response.status_code == 200:
                data = response.json()
                for entry in data.values():
                    if entry.get('ticker', '').upper() == ticker.upper():
                        cik = str(entry.get('cik_str', ''))
                        return cik.zfill(10)  # Pad to 10 digits
        except Exception as e:
            logger.error("cik_lookup_error", ticker=ticker, error=str(e))
    
    return None


@router.get("/{ticker}/pipeline")
async def debug_full_pipeline(
    ticker: str,
    cik: Optional[str] = None
) -> Dict:
    """
    Ejecuta el pipeline completo con debug en cada etapa.
    Retorna información detallada de cada paso.
    
    ETAPAS:
    1. Búsqueda de filings
    2. Categorización (chains vs transactions)
    3. Procesamiento de chains
    4. Procesamiento de transactions
    5. Extracción cruda (antes de deduplicar)
    6. Deduplicación semántica
    7. Resultado final
    """
    debug_output = {
        "ticker": ticker,
        "stages": {}
    }
    
    try:
        # Resolver CIK si no se proporciona
        if not cik:
            cik = await _get_cik_for_ticker(ticker)
            if not cik:
                raise HTTPException(status_code=404, detail=f"No se encontró CIK para {ticker}")
        
        debug_output["cik"] = cik
        
        extractor = ContextualDilutionExtractor(
            sec_api_key=settings.SEC_API_IO_KEY,
            gemini_api_key=settings.GOOGL_API_KEY_V2
        )
        
        # ==========================================
        # ETAPA 1: Búsqueda de filings
        # ==========================================
        all_filings = await extractor.sec_client.search_filings(cik, limit=300)
        
        debug_output["stages"]["1_filing_search"] = {
            "description": "Búsqueda de filings en SEC-API",
            "total_filings": len(all_filings),
            "sample": [
                {
                    "form": f.get('formType'),
                    "date": f.get('filedAt', '')[:10],
                    "accession": f.get('accessionNo', '')[:20]
                }
                for f in all_filings[:10]
            ]
        }
        
        # ==========================================
        # ETAPA 2: Categorización
        # ==========================================
        registration_chains, transaction_filings, financials = extractor._categorize_filings(all_filings)
        
        debug_output["stages"]["2_categorization"] = {
            "description": "Categorización de filings",
            "registration_chains": {
                "count": len(registration_chains),
                "file_numbers": list(registration_chains.keys())[:10],
                "detail": {
                    file_no: [f.get('formType') for f in filings]
                    for file_no, filings in list(registration_chains.items())[:5]
                }
            },
            "transaction_filings": {
                "count": len(transaction_filings),
                "forms": [f.get('formType') for f in transaction_filings[:20]]
            },
            "financials": {
                "count": len(financials)
            }
        }
        
        # ==========================================
        # ETAPA 3: Procesamiento de Chains (simulado - sin llamar a Gemini)
        # ==========================================
        debug_output["stages"]["3_chains_preview"] = {
            "description": "Preview de chains a procesar",
            "chains": []
        }
        
        for file_no, chain_filings in list(registration_chains.items())[:5]:
            chain_filings.sort(key=lambda x: x.get('filedAt', ''))
            forms = [f.get('formType', '').upper() for f in chain_filings]
            
            chain_type = "Unknown"
            if any('S-1' in f or 'F-1' in f for f in forms):
                chain_type = "IPO/Follow-on"
            elif any('S-3' in f or 'F-3' in f for f in forms):
                chain_type = "Shelf/ATM"
            
            debug_output["stages"]["3_chains_preview"]["chains"].append({
                "file_no": file_no,
                "chain_type": chain_type,
                "forms": forms,
                "dates": [f.get('filedAt', '')[:10] for f in chain_filings]
            })
        
        # ==========================================
        # ETAPA 4: Preview de Transactions
        # ==========================================
        from datetime import datetime, timedelta
        cutoff = (datetime.now() - timedelta(days=1095)).isoformat()
        recent_transactions = [e for e in transaction_filings if (e.get('filedAt') or '') >= cutoff]
        recent_transactions.sort(key=lambda x: x.get('filedAt', ''))
        
        debug_output["stages"]["4_transactions_preview"] = {
            "description": "Preview de transactions a procesar",
            "total": len(transaction_filings),
            "recent_count": len(recent_transactions),
            "recent_forms": [
                {
                    "form": f.get('formType'),
                    "date": f.get('filedAt', '')[:10],
                    "accession": f.get('accessionNo', '')[:24]
                }
                for f in recent_transactions[:15]
            ]
        }
        
        # ==========================================
        # ETAPA 5: Nota sobre extracción real
        # ==========================================
        debug_output["stages"]["5_extraction_note"] = {
            "description": "La extracción real requiere llamadas a Gemini",
            "note": "Usa /api/extraction/{ticker}/extract para ejecutar extracción completa",
            "estimated_gemini_calls": len(registration_chains) + len(recent_transactions)
        }
        
        return debug_output
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error("debug_pipeline_error", ticker=ticker, error=str(e))
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/{ticker}/extract-with-debug")
async def extract_with_debug(
    ticker: str,
    cik: Optional[str] = None,
    max_transactions: int = Query(default=10, description="Máximo de transactions a procesar")
) -> Dict:
    """
    Ejecuta extracción REAL con debug detallado en cada etapa.
    NOTA: Hace llamadas reales a Gemini (tiene costo).
    """
    debug_output = {
        "ticker": ticker,
        "stages": {}
    }
    
    try:
        # Resolver CIK
        if not cik:
            cik = await _get_cik_for_ticker(ticker)
            if not cik:
                raise HTTPException(status_code=404, detail=f"No se encontró CIK para {ticker}")
        
        debug_output["cik"] = cik
        
        extractor = ContextualDilutionExtractor(
            sec_api_key=settings.SEC_API_IO_KEY,
            gemini_api_key=settings.GOOGL_API_KEY_V2
        )
        
        # ETAPA 1: Obtener filings
        all_filings = await extractor.sec_client.search_filings(cik, limit=300)
        debug_output["stages"]["1_filings"] = {
            "total": len(all_filings)
        }
        
        # ETAPA 2: Categorizar
        registration_chains, transaction_filings, _ = extractor._categorize_filings(all_filings)
        debug_output["stages"]["2_categorized"] = {
            "chains": len(registration_chains),
            "transactions": len(transaction_filings)
        }
        
        # ETAPA 3: Ejecutar extracción completa
        from services.extraction.contextual_extractor import ExtractionContext
        context = ExtractionContext(ticker=ticker)
        
        # Procesar chains
        chains_processed = 0
        for file_no, chain_filings in registration_chains.items():
            await extractor._process_registration_chain(file_no, chain_filings, context)
            chains_processed += 1
        
        debug_output["stages"]["3_chains_processed"] = {
            "count": chains_processed,
            "warrants_after_chains": len(context.warrants),
            "shelf_after_chains": len(context.shelf_registrations),
            "atm_after_chains": len(context.atm_offerings)
        }
        
        # Snapshot antes de transactions
        warrants_before_tx = [dict(w) for w in context.warrants]
        
        # Procesar transactions (limitado)
        from datetime import datetime, timedelta
        cutoff = (datetime.now() - timedelta(days=1095)).isoformat()
        recent = [e for e in transaction_filings if (e.get('filedAt') or '') >= cutoff]
        recent.sort(key=lambda x: x.get('filedAt', ''))
        recent = recent[:max_transactions]  # Limitar
        
        for idx, filing in enumerate(recent):
            await extractor._process_single_transaction_filing(filing, context, idx=idx+1, total=len(recent))
        
        debug_output["stages"]["4_transactions_processed"] = {
            "count": len(recent),
            "warrants_after_tx": len(context.warrants),
            "new_warrants": len(context.warrants) - len(warrants_before_tx)
        }
        
        # ETAPA 5: Datos crudos antes de deduplicación
        raw_warrants = [dict(w) for w in context.warrants]
        debug_output["stages"]["5_raw_extraction"] = {
            "warrants_count": len(raw_warrants),
            "warrants": [
                {
                    "name": w.get('series_name'),
                    "type": w.get('warrant_type'),
                    "price": w.get('exercise_price'),
                    "issued": w.get('total_issued'),
                    "source": w.get('_source')
                }
                for w in raw_warrants
            ]
        }
        
        # ETAPA 6: Deduplicación semántica
        from services.extraction.semantic_deduplicator import SemanticDeduplicator
        deduplicator = SemanticDeduplicator(similarity_threshold=0.85)
        
        dedup_result = deduplicator.deduplicate(raw_warrants, 'warrant')
        
        debug_output["stages"]["6_deduplication"] = {
            "original": dedup_result.original_count,
            "deduplicated": dedup_result.deduplicated_count,
            "clusters": len(dedup_result.merged_clusters),
            "cluster_sizes": [len(c) for c in dedup_result.merged_clusters],
            "fingerprints": dedup_result.debug_info.get('fingerprints', []),
            "similarity_sample": dedup_result.debug_info.get('similarity_matrix_sample', [])
        }
        
        # ETAPA 7: Resultado final
        final_warrants = dedup_result.final_instruments
        
        # Filtrar underwriter/placement agent
        filtered_warrants = extractor._filter_warrants(final_warrants)
        
        debug_output["stages"]["7_final_result"] = {
            "after_dedup": len(final_warrants),
            "after_filter": len(filtered_warrants),
            "warrants": [
                {
                    "name": w.get('series_name'),
                    "type": w.get('warrant_type'),
                    "price": w.get('exercise_price'),
                    "issued": w.get('total_issued'),
                    "sources": w.get('_sources'),
                    "merged_from": w.get('_merged_from')
                }
                for w in filtered_warrants
            ]
        }
        
        return debug_output
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error("extract_with_debug_error", ticker=ticker, error=str(e))
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/{ticker}/test-dedup")
async def test_deduplication(
    ticker: str,
    threshold: float = Query(default=0.85, ge=0.5, le=1.0)
) -> Dict:
    """
    Prueba la deduplicación semántica con datos de prueba.
    """
    # Datos de prueba simulando lo que extraemos de VMAR
    test_warrants = [
        {"series_name": "December 2025 Common Warrants", "warrant_type": "Common", "exercise_price": 0.375, "total_issued": 16000000, "_source": "424B4:2025-12-18"},
        {"series_name": "Dec 2025 Warrants", "warrant_type": "common", "exercise_price": 0.38, "total_issued": None, "_source": "chain:333-291917"},
        {"series_name": "December 2025 Common Warrants", "warrant_type": "Common", "exercise_price": 0.37, "total_issued": 16000000, "_source": "6-K:2025-12-19"},
        {"series_name": "December 2025 Pre-Funded Warrants", "warrant_type": "Pre-Funded", "exercise_price": 0.001, "total_issued": 12750000, "_source": "424B4:2025-12-18"},
        {"series_name": "Dec 2025 Pre-funded Warrants", "warrant_type": "pre-funded", "exercise_price": 0.001, "total_issued": None, "_source": "chain:333-291917"},
        {"series_name": "January 2025 Common Warrants", "warrant_type": "Common", "exercise_price": 1.5, "total_issued": 2353200, "_source": "424B5:2025-01-15"},
    ]
    
    # Crear fingerprints
    fingerprints = [_create_fingerprint(w, 'warrant') for w in test_warrants]
    
    # Deduplicar
    deduplicator = SemanticDeduplicator(similarity_threshold=threshold)
    result = deduplicator.deduplicate(test_warrants, 'warrant')
    
    return {
        "ticker": ticker,
        "test_description": "Simulación de deduplicación con datos de prueba VMAR",
        "threshold": threshold,
        "input": {
            "count": len(test_warrants),
            "warrants": [
                {"name": w["series_name"], "source": w["_source"]}
                for w in test_warrants
            ]
        },
        "fingerprints": fingerprints,
        "output": {
            "deduplicated_count": result.deduplicated_count,
            "clusters": [
                {
                    "size": len(cluster),
                    "members": [w.get('series_name') for w in cluster]
                }
                for cluster in result.merged_clusters
            ],
            "final_warrants": [
                {
                    "name": w.get('series_name'),
                    "price": w.get('exercise_price'),
                    "issued": w.get('total_issued'),
                    "merged_from": w.get('_merged_from'),
                    "sources": w.get('_sources')
                }
                for w in result.final_instruments
            ]
        }
    }


@router.get("/{ticker}/filing-content/{accession_no}")
async def get_filing_content(
    ticker: str,
    accession_no: str,
    max_chars: int = Query(default=50000)
) -> Dict:
    """
    Obtiene el contenido de un filing específico para debug.
    """
    try:
        # Buscar CIK
        cik = await _get_cik_for_ticker(ticker)
        if not cik:
            raise HTTPException(status_code=404, detail=f"No se encontró CIK para {ticker}")
        
        # Construir URL del filing
        cik_clean = cik.lstrip('0')
        acc_formatted = accession_no.replace('-', '')
        url = f"https://www.sec.gov/Archives/edgar/data/{cik_clean}/{acc_formatted}/{accession_no}.txt"
        
        # Obtener contenido
        sec_client = SECAPIClient(settings.SEC_API_IO_KEY)
        content = await sec_client.fetch_filing_content(url)
        
        if not content:
            return {
                "ticker": ticker,
                "accession_no": accession_no,
                "error": "No se pudo obtener contenido",
                "url_tried": url
            }
        
        return {
            "ticker": ticker,
            "accession_no": accession_no,
            "url": url,
            "content_length": len(content),
            "content_preview": content[:max_chars]
        }
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error("filing_content_error", ticker=ticker, error=str(e))
        raise HTTPException(status_code=500, detail=str(e))

