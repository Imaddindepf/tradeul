"""
Extraction Router - Endpoints para extracción de dilución
==========================================================
Endpoint principal: /api/extraction/{ticker}/extract
- Extrae instrumentos dilutivos usando ContextualExtractor v4
- GUARDA resultados en Redis (TTL 24h)
- Para debug sin guardar usar: save=false
"""

import sys
sys.path.append('/app')

import json
from datetime import datetime
from fastapi import APIRouter, HTTPException, Query

from shared.utils.logger import get_logger
from shared.utils.redis_client import RedisClient
from services.sec.sec_filing_fetcher import SECFilingFetcher

logger = get_logger(__name__)

# UN solo router, UN solo prefijo
router = APIRouter(prefix="/api/extraction", tags=["extraction"])

# Cache key para resultados de extracción
EXTRACTION_CACHE_KEY = "sec_dilution:extraction:{ticker}"
EXTRACTION_CACHE_TTL = 86400  # 24 horas


@router.get("/{ticker}/extract")
async def extract_dilution(
    ticker: str,
    save: bool = Query(default=True, description="Guardar resultado en Redis cache"),
    force: bool = Query(default=False, description="Forzar re-extracción ignorando cache")
):
    """
    Extracción de instrumentos dilutivos usando ContextualExtractor v4.
    
    - Por defecto GUARDA en Redis (save=true)
    - Use force=true para re-extraer ignorando cache
    - Use save=false para debug sin guardar
    
    **Costo:** ~$0.10-0.50 USD por extracción (Gemini API)
    """
    ticker = ticker.upper()
    redis = None
    
    try:
        # Conectar a Redis
        redis = RedisClient()
        await redis.connect()
        cache_key = EXTRACTION_CACHE_KEY.format(ticker=ticker)
        
        # Verificar cache si no es force
        if not force:
            cached = await redis.get(cache_key, deserialize=True)
            if cached:
                logger.info("extraction_cache_hit", ticker=ticker)
                cached["_from_cache"] = True
                cached["_cache_key"] = cache_key
                return cached
        
        # Obtener CIK
        fetcher = SECFilingFetcher()
        cik, company_name = await fetcher.get_cik_and_company_name(ticker)
        if not cik:
            raise HTTPException(status_code=404, detail=f"CIK not found for {ticker}")

        # Obtener extractor
        from services.extraction.contextual_extractor import get_contextual_extractor
        extractor = get_contextual_extractor()
        if not extractor:
            raise HTTPException(
                status_code=503,
                detail="Contextual extractor not available (missing API keys)"
            )

        # Ejecutar extracción v4.4 con Gemini Pro Dedup
        logger.info("extraction_start", ticker=ticker, cik=cik, save=save, force=force,
                   use_gemini_pro_dedup=True)
        result = await extractor.extract_all(
            ticker=ticker,
            cik=cik,
            company_name=company_name,
            use_gemini_pro_dedup=True  # Usar Gemini 3 Pro para dedup + split adjustment
        )

        # Construir respuesta
        response = {
            "ticker": ticker,
            "cik": cik,
            "company_name": company_name,
            "version": "contextual_v4.4",
            "status": "success",
            "extracted_at": datetime.utcnow().isoformat(),
            "summary": {
                "shelf_registrations": len(result.get('shelf_registrations', [])),
                "atm_offerings": len(result.get('atm_offerings', [])),
                "s1_offerings": len(result.get('s1_offerings', [])),
                "warrants": len(result.get('warrants', [])),
                "convertible_notes": len(result.get('convertible_notes', [])),
                "convertible_preferred": len(result.get('convertible_preferred', [])),
            },
            **result,  # Incluir todos los instrumentos directamente
        }
        
        # Guardar en cache si save=true
        if save:
            await redis.set(cache_key, response, ttl=EXTRACTION_CACHE_TTL, serialize=True)
            logger.info("extraction_saved_to_cache", ticker=ticker, cache_key=cache_key)
            response["_saved_to_cache"] = True
            response["_cache_key"] = cache_key
        else:
            response["_saved_to_cache"] = False
        
        return response
        
    except HTTPException:
        raise
    except Exception as e:
        import traceback
        logger.error(
            "extraction_error",
            ticker=ticker,
            error=str(e),
            traceback=traceback.format_exc(),
        )
        raise HTTPException(status_code=500, detail=f"{type(e).__name__}: {str(e)}")
    finally:
        if redis:
            await redis.close()


@router.get("/{ticker}/chains")
async def get_filing_chains(ticker: str):
    """
    🔧 DEBUG: Ver cadenas de registro (fileNo) para un ticker.
    """
    ticker = ticker.upper()
    try:
        from shared.config.settings import settings
        import httpx
        from collections import defaultdict

        fetcher = SECFilingFetcher()
        cik, company_name = await fetcher.get_cik_and_company_name(ticker)
        if not cik:
            raise HTTPException(status_code=404, detail=f"CIK not found for {ticker}")

        cik_clean = cik.lstrip("0")
        sec_api_key = settings.SEC_API_IO_KEY
        form_types = "F-1 OR S-1 OR F-3 OR S-3 OR 424B4 OR 424B5 OR EFFECT"

        async with httpx.AsyncClient(timeout=60) as client:
            query = {
                "query": {"query_string": {"query": f"cik:{cik_clean} AND formType:({form_types})"}},
                "from": 0,
                "size": 200,
                "sort": [{"filedAt": {"order": "desc"}}],
            }
            response = await client.post(
                f"https://api.sec-api.io?token={sec_api_key}",
                json=query,
                headers={"Content-Type": "application/json"},
            )
            data = response.json()
            filings = data.get("filings", [])

        chains = defaultdict(list)
        for f in filings:
            file_no = None
            entities = f.get("entities", [])
            if entities:
                file_no = entities[0].get("fileNo") or entities[0].get("fileNumber")
            if not file_no:
                file_no = f.get("fileNumber") or f.get("fileNo")
            if file_no:
                chains[file_no].append({
                    "form": f.get("formType"),
                    "date": (f.get("filedAt", "") or "")[:10],
                    "description": (f.get("description", "") or "")[:100],
                    "accession": f.get("accessionNo"),
                })

        chains_list = []
        for file_no, filings_in_chain in sorted(chains.items(), reverse=True):
            filings_in_chain.sort(key=lambda x: x["date"])
            chains_list.append({
                "file_number": file_no,
                "filings_count": len(filings_in_chain),
                "date_range": f"{filings_in_chain[0]['date']} to {filings_in_chain[-1]['date']}",
                "forms": [f["form"] for f in filings_in_chain],
                "filings": filings_in_chain,
            })

        return {
            "ticker": ticker,
            "cik": cik,
            "company_name": company_name,
            "total_chains": len(chains_list),
            "chains": chains_list,
        }
    except HTTPException:
        raise
    except Exception as e:
        logger.error("get_chains_error", ticker=ticker, error=str(e))
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/{ticker}/events")
async def get_material_events(
    ticker: str,
    limit: int = Query(default=20, description="Número de eventos")
):
    """
    🔧 DEBUG: Ver material events (8-K/6-K) y si tienen contenido dilutivo.
    """
    ticker = ticker.upper()
    try:
        from shared.config.settings import settings
        import httpx
        import re

        fetcher = SECFilingFetcher()
        cik, company_name = await fetcher.get_cik_and_company_name(ticker)
        if not cik:
            raise HTTPException(status_code=404, detail=f"CIK not found for {ticker}")

        cik_clean = cik.lstrip('0')
        sec_api_key = settings.SEC_API_IO_KEY

        async with httpx.AsyncClient(timeout=60) as client:
            query = {
                "query": {"query_string": {"query": f"cik:{cik_clean} AND formType:(6-K OR 8-K)"}},
                "from": 0,
                "size": limit,
                "sort": [{"filedAt": {"order": "desc"}}],
            }
            response = await client.post(
                f"https://api.sec-api.io?token={sec_api_key}",
                json=query,
                headers={"Content-Type": "application/json"},
            )
            data = response.json()
            filings = data.get("filings", [])

        dilution_keywords = [
            "convertible", "warrant", "preferred", "securities purchase",
            "private placement", "exercise price", "conversion price",
            "at-the-market", "atm", "registered direct", "offering"
        ]

        results = []
        for f in filings:
            url = f.get("linkToFilingDetails") or f.get("linkToHtml")
            filing_info = {
                "form": f.get("formType"),
                "date": (f.get("filedAt", "") or "")[:10],
                "description": (f.get("description", "") or "")[:200],
                "url": url,
                "has_dilution_keywords": False,
                "keywords_found": [],
            }
            
            # Solo verificar keywords en descripción (rápido)
            desc_lower = filing_info["description"].lower()
            found = [kw for kw in dilution_keywords if kw in desc_lower]
            if found:
                filing_info["has_dilution_keywords"] = True
                filing_info["keywords_found"] = found
            
            results.append(filing_info)

        return {
            "ticker": ticker,
            "cik": cik,
            "total_events": len(results),
            "with_dilution_keywords": sum(1 for r in results if r["has_dilution_keywords"]),
            "events": results,
        }
    except HTTPException:
        raise
    except Exception as e:
        logger.error("get_events_error", ticker=ticker, error=str(e))
        raise HTTPException(status_code=500, detail=str(e))
