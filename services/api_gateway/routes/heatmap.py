"""
Market Heatmap API
Provides aggregated market data grouped by sector/industry for heatmap visualization.
Combines snapshot:enriched:latest (prices) with metadata:ticker:* (sector/market_cap).
"""

from fastapi import APIRouter, HTTPException, Query
from typing import Optional, List, Dict, Any
from collections import defaultdict
import time
import json
from shared.utils.logger import get_logger

logger = get_logger(__name__)

router = APIRouter(prefix="/api/v1/heatmap", tags=["heatmap"])

# Redis client will be injected from main.py
redis_client = None

# In-memory cache to reduce Redis reads
_cache: Dict[str, Any] = {}
_cache_timestamp: float = 0
CACHE_TTL_SECONDS = 3  # Cache for 3 seconds


def set_redis_client(client):
    global redis_client
    redis_client = client


# Standard GICS-like sectors with display order
SECTOR_ORDER = [
    "Technology",
    "Healthcare", 
    "Financial Services",
    "Consumer Cyclical",
    "Communication Services",
    "Industrials",
    "Consumer Defensive",
    "Energy",
    "Basic Materials",
    "Real Estate",
    "Utilities",
]

# Sector colors (professional palette)
SECTOR_COLORS = {
    "Technology": "#6366f1",
    "Healthcare": "#ec4899",
    "Financial Services": "#f59e0b",
    "Consumer Cyclical": "#10b981",
    "Communication Services": "#3b82f6",
    "Industrials": "#8b5cf6",
    "Consumer Defensive": "#14b8a6",
    "Energy": "#ef4444",
    "Basic Materials": "#f97316",
    "Real Estate": "#06b6d4",
    "Utilities": "#84cc16",
}

# Map raw sector names (SIC codes) to standardized GICS-like names
# This covers the most common SIC industry classifications
SECTOR_MAPPINGS = {
    # === GICS names (already standardized) ===
    "technology": "Technology",
    "healthcare": "Healthcare",
    "health care": "Healthcare",
    "financial services": "Financial Services",
    "financials": "Financial Services",
    "consumer cyclical": "Consumer Cyclical",
    "consumer discretionary": "Consumer Cyclical",
    "communication services": "Communication Services",
    "industrials": "Industrials",
    "consumer defensive": "Consumer Defensive",
    "consumer staples": "Consumer Defensive",
    "energy": "Energy",
    "basic materials": "Basic Materials",
    "materials": "Basic Materials",
    "real estate": "Real Estate",
    "utilities": "Utilities",
    
    # === Technology (SIC) ===
    "electronic computers": "Technology",
    "computer & office equipment": "Technology",
    "computer communications equipment": "Technology",
    "computer peripheral equipment, nec": "Technology",
    "computer storage devices": "Technology",
    "computer integrated systems design": "Technology",
    "computer processing & data preparation": "Technology",
    "services-prepackaged software": "Technology",
    "services-computer programming services": "Technology",
    "services-computer integrated systems design": "Technology",
    "services-computer processing & data preparation": "Technology",
    "services-computer programming, data processing, etc.": "Technology",
    "semiconductors & related devices": "Technology",
    "printed circuit boards": "Technology",
    "electronic components, nec": "Technology",
    "electronic connectors": "Technology",
    "household audio & video equipment": "Technology",
    "calculating & accounting machines (no electronic computers)": "Technology",
    "communications equipment, nec": "Technology",
    "telephone & telegraph apparatus": "Technology",
    "radio & tv broadcasting & communications equipment": "Technology",
    
    # === Healthcare (SIC) ===
    "pharmaceutical preparations": "Healthcare",
    "biological products, (no disgnostic substances)": "Healthcare",
    "biological products (no diagnostic substances)": "Healthcare",
    "in vitro & in vivo diagnostic substances": "Healthcare",
    "surgical & medical instruments & apparatus": "Healthcare",
    "orthopedic, prosthetic & surgical appliances & supplies": "Healthcare",
    "electromedical & electrotherapeutic apparatus": "Healthcare",
    "dental equipment & supplies": "Healthcare",
    "ophthalmic goods": "Healthcare",
    "services-hospitals": "Healthcare",
    "services-health services": "Healthcare",
    "services-nursing & personal care facilities": "Healthcare",
    "services-specialty outpatient facilities, nec": "Healthcare",
    "services-medical laboratories": "Healthcare",
    "services-home health care services": "Healthcare",
    "medicinal chemicals & botanical products": "Healthcare",
    "general medical & surgical hospitals, nec": "Healthcare",
    
    # === Financial Services (SIC) ===
    "state commercial banks-federal reserve member": "Financial Services",
    "state commercial banks": "Financial Services",
    "national commercial banks": "Financial Services",
    "commercial banks, nec": "Financial Services",
    "savings institution, federally chartered": "Financial Services",
    "savings institutions, not federally chartered": "Financial Services",
    "federal savings institutions": "Financial Services",
    "functions related to depository banking, nec": "Financial Services",
    "security brokers, dealers & flotation companies": "Financial Services",
    "commodity contracts brokers & dealers": "Financial Services",
    "security & commodity exchanges": "Financial Services",
    "investment advice": "Financial Services",
    "investment offices, nec": "Financial Services",
    "unit investment trusts, face-amount certificate offices": "Financial Services",
    "finance services": "Financial Services",
    "finance lessors": "Financial Services",
    "personal credit institutions": "Financial Services",
    "short-term business credit institutions": "Financial Services",
    "miscellaneous business credit institutions": "Financial Services",
    "asset-backed securities": "Financial Services",
    "accident & health insurance": "Financial Services",
    "life insurance": "Financial Services",
    "fire, marine & casualty insurance": "Financial Services",
    "surety insurance": "Financial Services",
    "title insurance": "Financial Services",
    "insurance agents, brokers & service": "Financial Services",
    "blank checks": "Financial Services",  # SPACs
    
    # === Real Estate (SIC) ===
    "real estate investment trusts": "Real Estate",
    "real estate operators (no developers) & lessors": "Real Estate",
    "real estate agents & managers (for others)": "Real Estate",
    "land subdividers & developers (no cemeteries)": "Real Estate",
    "lessors of real property, nec": "Real Estate",
    "operators of nonresidential buildings": "Real Estate",
    
    # === Consumer Cyclical (SIC) ===
    "motor vehicles & passenger car bodies": "Consumer Cyclical",
    "motor vehicle parts & accessories": "Consumer Cyclical",
    "aircraft engines & engine parts": "Consumer Cyclical",
    "retail-auto dealers & gasoline stations": "Consumer Cyclical",
    "retail-home furniture, furnishings & equipment stores": "Consumer Cyclical",
    "retail-eating places": "Consumer Cyclical",
    "retail-apparel & accessory stores": "Consumer Cyclical",
    "retail-family clothing stores": "Consumer Cyclical",
    "retail-catalog & mail-order houses": "Consumer Cyclical",
    "retail-miscellaneous retail": "Consumer Cyclical",
    "retail-retail stores, nec": "Consumer Cyclical",
    "hotels, rooming houses, camps & other lodging places": "Consumer Cyclical",
    "hotels & motels": "Consumer Cyclical",
    "services-hotels & motels": "Consumer Cyclical",
    "services-amusement & recreation services": "Consumer Cyclical",
    "services-motion picture theaters": "Consumer Cyclical",
    "apparel & other finishd prods of fabrics & similar matl": "Consumer Cyclical",
    "household furniture": "Consumer Cyclical",
    "footwear, (no rubber)": "Consumer Cyclical",
    "games, toys & children's vehicles (no dolls & bicycles)": "Consumer Cyclical",
    "sporting & athletic goods, nec": "Consumer Cyclical",
    
    # === Communication Services (SIC) ===
    "radiotelephone communications": "Communication Services",
    "telephone communications (no radiotelephone)": "Communication Services",
    "cable & other pay television services": "Communication Services",
    "television broadcasting stations": "Communication Services",
    "radio broadcasting stations": "Communication Services",
    "communications services, nec": "Communication Services",
    "services-motion picture & video tape production": "Communication Services",
    "services-motion picture & video tape distribution": "Communication Services",
    "services-advertising agencies": "Communication Services",
    "services-advertising": "Communication Services",
    "services-computer related services, nec": "Communication Services",
    "newspapers: publishing or publishing & printing": "Communication Services",
    "periodicals: publishing or publishing & printing": "Communication Services",
    "books: publishing or publishing & printing": "Communication Services",
    
    # === Industrials (SIC) ===
    "aircraft": "Industrials",
    "aircraft & parts": "Industrials",
    "aircraft parts & auxiliary equipment, nec": "Industrials",
    "guided missiles & space vehicles & parts": "Industrials",
    "search, detection, navagation, guidance, aeronauttic sys": "Industrials",
    "ordnance & accessories, (no vehicles/guided missiles)": "Industrials",
    "ship & boat building & repairing": "Industrials",
    "railroad equipment": "Industrials",
    "motor homes": "Industrials",
    "industrial trucks, tractors, trailers & stackers": "Industrials",
    "construction, mining & materials handling machinery & equip": "Industrials",
    "construction machinery & equip": "Industrials",
    "farm machinery & equipment": "Industrials",
    "general industrial machinery & equipment": "Industrials",
    "general industrial machinery & equipment, nec": "Industrials",
    "special industry machinery, nec": "Industrials",
    "metalworkg machinery & equipment": "Industrials",
    "industrial & commercial machinery & computer equipment": "Industrials",
    "measuring & controlling devices, nec": "Industrials",
    "services-engineering services": "Industrials",
    "services-management consulting services": "Industrials",
    "services-detective, guard & armored car services": "Industrials",
    "services-business services, nec": "Industrials",
    "services-help supply services": "Industrials",
    "air transportation, scheduled": "Industrials",
    "air transportation, nonscheduled": "Industrials",
    "air courier services": "Industrials",
    "trucking (no local)": "Industrials",
    "trucking & courier services (no air)": "Industrials",
    "railroads, line-haul operating": "Industrials",
    "arrangement of transportation of freight & cargo": "Industrials",
    "transportation services": "Industrials",
    "united states postal service": "Industrials",
    "construction - special trade contractors": "Industrials",
    "operative builders": "Industrials",
    "heavy construction other than bldg const - Loss or contractors": "Industrials",
    
    # === Consumer Defensive (SIC) ===
    "beverages": "Consumer Defensive",
    "bottled & canned soft drinks & carbonated waters": "Consumer Defensive",
    "malt beverages": "Consumer Defensive",
    "distilled & blended liquors": "Consumer Defensive",
    "wines, brandy & brandy spirits": "Consumer Defensive",
    "cigarettes": "Consumer Defensive",
    "tobacco products": "Consumer Defensive",
    "retail-grocery stores": "Consumer Defensive",
    "retail-drug stores and proprietary stores": "Consumer Defensive",
    "wholesale-groceries & related products": "Consumer Defensive",
    "wholesale-drugs, proprietaries & druggists' sundries": "Consumer Defensive",
    "grain mill products": "Consumer Defensive",
    "canned, frozen & preservd fruit, veg & food specialties": "Consumer Defensive",
    "canned, fruits, veg, preserves, jams & jellies": "Consumer Defensive",
    "meat packing plants": "Consumer Defensive",
    "sausages & other prepared meat products": "Consumer Defensive",
    "poultry slaughtering and processing": "Consumer Defensive",
    "dairy products": "Consumer Defensive",
    "sugar & confectionery products": "Consumer Defensive",
    "fats & oils": "Consumer Defensive",
    "soap, detergents, cleang preparations, perfumes, cosmetics": "Consumer Defensive",
    "perfumes, cosmetics & other toilet preparations": "Consumer Defensive",
    
    # === Energy (SIC) ===
    "crude petroleum & natural gas": "Energy",
    "petroleum refining": "Energy",
    "oil & gas field services": "Energy",
    "drilling oil & gas wells": "Energy",
    "natural gas transmission": "Energy",
    "natural gas transmission & distribution": "Energy",
    "natural gas distribution": "Energy",
    "petroleum & petroleum products wholesalers (no bulk stations)": "Energy",
    "bituminous coal & lignite mining": "Energy",
    "bituminous coal & lignite surface mining": "Energy",
    
    # === Basic Materials (SIC) ===
    "chemicals & allied products": "Basic Materials",
    "industrial inorganic chemicals": "Basic Materials",
    "plastic material, synth resins & nonvultic elastomers": "Basic Materials",
    "industrial organic chemicals": "Basic Materials",
    "agricultural chemicals": "Basic Materials",
    "adhesives & sealants": "Basic Materials",
    "paints, varnishes, lacquers, enamels & allied prods": "Basic Materials",
    "steel works, blast furnaces & rolling & finishing mills": "Basic Materials",
    "primary smelting & refining of nonferrous metals": "Basic Materials",
    "rolling drawing & extruding of nonferrous metals": "Basic Materials",
    "gold and silver ores": "Basic Materials",
    "miscellaneous metal ores": "Basic Materials",
    "metal mining": "Basic Materials",
    "copper ores": "Basic Materials",
    "lead and zinc ores": "Basic Materials",
    "paper mills": "Basic Materials",
    "paperboard mills": "Basic Materials",
    "converted paper & paperboard prods (no containers/boxes)": "Basic Materials",
    "paperboard containers & boxes": "Basic Materials",
    "lumber & wood products (no furniture)": "Basic Materials",
    "cement, hydraulic": "Basic Materials",
    "concrete products, except block & brick": "Basic Materials",
    
    # === Utilities (SIC) ===
    "electric services": "Utilities",
    "electric & other services combined": "Utilities",
    "natural gas transmissn & distribution": "Utilities",
    "gas & other services combined": "Utilities",
    "water supply": "Utilities",
    "sanitary services": "Utilities",
    "combination electric & gas, and other utility services": "Utilities",
    "cogeneration services & small power producers": "Utilities",
}


def _normalize_sector(sector: Optional[str]) -> Optional[str]:
    """Normalize sector names to standard GICS-like format."""
    if not sector:
        return None
    
    sector_lower = sector.strip().lower()
    return SECTOR_MAPPINGS.get(sector_lower, sector.title())


@router.get("")
async def get_heatmap_data(
    metric: str = Query("change_percent", description="Color metric: change_percent, rvol, chg_5min, price_vs_vwap"),
    size_by: str = Query("market_cap", description="Size metric: market_cap, volume_today, dollar_volume"),
    min_market_cap: Optional[int] = Query(None, description="Minimum market cap filter"),
    max_tickers_per_sector: int = Query(100, ge=10, le=200, description="Max tickers per sector"),
    exclude_etfs: bool = Query(True, description="Exclude ETFs"),
    sectors: Optional[str] = Query(None, description="Comma-separated sector filter"),
    only_gics: bool = Query(True, description="Only show main GICS sectors (11 sectors)"),
):
    """
    Get market heatmap data grouped by sector and industry.
    
    Returns hierarchical data optimized for treemap visualization:
    - Sectors contain industries
    - Industries contain tickers
    - Each level has aggregated metrics
    
    Data combines:
    - snapshot:enriched:latest (prices, volume, rvol)
    - metadata:ticker:* (sector, industry, market_cap)
    
    Response is cached for 3 seconds to reduce load.
    """
    global _cache, _cache_timestamp
    
    if not redis_client:
        raise HTTPException(status_code=503, detail="Redis not available")
    
    # Build cache key from params
    cache_key = f"{metric}:{size_by}:{min_market_cap}:{max_tickers_per_sector}:{exclude_etfs}:{sectors}:{only_gics}"
    
    # Check cache
    now = time.time()
    if cache_key in _cache and (now - _cache_timestamp) < CACHE_TTL_SECONDS:
        return _cache[cache_key]
    
    try:
        # 1. Read snapshot from Redis (con fallback a last_close para mercado cerrado)
        snapshot_data = await redis_client.get("snapshot:enriched:latest")
        is_realtime = True
        
        if not snapshot_data:
            # Fallback: usar último cierre si no hay datos en tiempo real
            snapshot_data = await redis_client.get("snapshot:enriched:last_close")
            is_realtime = False
            
            if not snapshot_data:
                raise HTTPException(status_code=404, detail="No market data available")
        
        tickers_raw = snapshot_data.get("tickers", [])
        snapshot_timestamp = snapshot_data.get("timestamp")
        
        if not tickers_raw:
            raise HTTPException(status_code=404, detail="No tickers in snapshot")
        
        # 2. Get all symbols
        symbols = [t.get("ticker") for t in tickers_raw if t.get("ticker")]
        
        # 3. Batch fetch metadata from Redis using MGET
        metadata_keys = [f"metadata:ticker:{sym}" for sym in symbols]
        
        # Split into chunks to avoid memory issues
        CHUNK_SIZE = 1000
        metadata_map = {}
        
        for i in range(0, len(metadata_keys), CHUNK_SIZE):
            chunk_keys = metadata_keys[i:i+CHUNK_SIZE]
            chunk_symbols = symbols[i:i+CHUNK_SIZE]
            
            try:
                # MGET returns list of values in same order as keys
                raw_results = await redis_client.client.mget(chunk_keys)
                
                fetched_count = sum(1 for r in raw_results if r)
                
                for sym, raw in zip(chunk_symbols, raw_results):
                    if raw:
                        try:
                            meta = json.loads(raw) if isinstance(raw, str) else raw
                            metadata_map[sym] = meta
                        except (json.JSONDecodeError, TypeError):
                            continue
            except Exception as e:
                # Log error but continue with partial data
                continue
        
        # Parse sector filter
        sector_filter = None
        if sectors:
            sector_filter = set(s.strip() for s in sectors.split(","))
        
        # 4. Combine snapshot + metadata and filter
        valid_tickers = []
        
        for t in tickers_raw:
            symbol = t.get("ticker")
            if not symbol:
                continue
            
            # Get metadata
            meta = metadata_map.get(symbol, {})
            if not meta:
                continue
            
            # Get sector from metadata and normalize
            raw_sector = meta.get("sector")
            sector = _normalize_sector(raw_sector)
            
            # Get market cap from metadata
            market_cap = meta.get("market_cap")
            
            # Skip if missing required fields
            if not sector or not market_cap:
                continue
            
            # Skip if market cap below minimum
            if min_market_cap and market_cap < min_market_cap:
                continue
            
            # Skip ETFs if requested
            if exclude_etfs and meta.get("is_etf"):
                continue
            
            # Skip if not in sector filter
            if sector_filter and sector not in sector_filter:
                continue
            
            # Extract price data from snapshot
            day_data = t.get("day", {})
            current_price = t.get("current_price") or day_data.get("c") or 0
            prev_day = t.get("prevDay", {})
            prev_close = prev_day.get("c") or 0
            
            # Calculate change_percent
            change_percent = t.get("todaysChangePerc") or 0
            if not change_percent and current_price and prev_close:
                change_percent = ((current_price - prev_close) / prev_close) * 100 if prev_close > 0 else 0
            
            # Get volume
            volume_today = day_data.get("v") or t.get("current_volume") or 0
            
            # Get industry from metadata
            raw_industry = meta.get("industry") or "Other"
            industry = raw_industry.title() if raw_industry else "Other"
            
            # Build ticker object
            ticker_obj = {
                "symbol": symbol,
                "name": meta.get("name") or meta.get("company_name") or symbol,
                "sector": sector,
                "industry": industry,
                "price": current_price,
                "change_percent": round(change_percent, 2) if change_percent else 0,
                "market_cap": market_cap,
                "volume_today": volume_today,
                "dollar_volume": (current_price or 0) * (volume_today or 0),
                "rvol": t.get("rvol") or 0,
                "chg_5min": t.get("chg_5min") or 0,
                "price_vs_vwap": 0,  # TODO: calculate if vwap available
                "logo_url": meta.get("logo_url"),
                "icon_url": meta.get("icon_url"),
            }
            
            valid_tickers.append(ticker_obj)
        
        
        # 5. Group by sector -> industry -> tickers
        sectors_data = defaultdict(lambda: {
            "industries": defaultdict(list),
            "tickers": [],
        })
        
        for ticker in valid_tickers:
            sector = ticker["sector"]
            industry = ticker["industry"]
            sectors_data[sector]["tickers"].append(ticker)
            sectors_data[sector]["industries"][industry].append(ticker)
        
        # 6. Build response with aggregations
        result_sectors = []
        
        # Process sectors in order - filter to GICS only if requested
        if only_gics:
            all_sectors = [s for s in SECTOR_ORDER if s in sectors_data]
        else:
            all_sectors = list(SECTOR_ORDER) + [s for s in sectors_data.keys() if s not in SECTOR_ORDER]
        
        for sector_name in all_sectors:
            if sector_name not in sectors_data:
                continue
            
            sector_info = sectors_data[sector_name]
            all_tickers = sector_info["tickers"]
            
            if not all_tickers:
                continue
            
            # Sort by size metric and limit
            size_key = size_by if size_by in all_tickers[0] else "market_cap"
            all_tickers.sort(key=lambda x: x.get(size_key) or 0, reverse=True)
            top_tickers = all_tickers[:max_tickers_per_sector]
            
            # Calculate sector aggregates
            total_market_cap = sum(t["market_cap"] for t in top_tickers)
            total_volume = sum(t["volume_today"] for t in top_tickers)
            
            # Weighted average change (by market cap)
            if total_market_cap > 0:
                weighted_change = sum(
                    t["change_percent"] * t["market_cap"] 
                    for t in top_tickers
                ) / total_market_cap
            else:
                weighted_change = 0
            
            # Build industries
            industries_result = []
            for industry_name, industry_tickers in sector_info["industries"].items():
                # Filter to only include tickers in top_tickers
                top_symbols = {t["symbol"] for t in top_tickers}
                filtered_industry_tickers = [
                    t for t in industry_tickers 
                    if t["symbol"] in top_symbols
                ]
                
                if not filtered_industry_tickers:
                    continue
                
                # Sort industry tickers
                filtered_industry_tickers.sort(
                    key=lambda x: x.get(size_key) or 0, 
                    reverse=True
                )
                
                ind_market_cap = sum(t["market_cap"] for t in filtered_industry_tickers)
                
                if ind_market_cap > 0:
                    ind_weighted_change = sum(
                        t["change_percent"] * t["market_cap"]
                        for t in filtered_industry_tickers
                    ) / ind_market_cap
                else:
                    ind_weighted_change = 0
                
                industries_result.append({
                    "industry": industry_name,
                    "ticker_count": len(filtered_industry_tickers),
                    "total_market_cap": ind_market_cap,
                    "avg_change_percent": round(ind_weighted_change, 2),
                    "tickers": filtered_industry_tickers,
                })
            
            # Sort industries by market cap
            industries_result.sort(
                key=lambda x: x["total_market_cap"], 
                reverse=True
            )
            
            result_sectors.append({
                "sector": sector_name,
                "color": SECTOR_COLORS.get(sector_name, "#64748b"),
                "ticker_count": len(top_tickers),
                "total_market_cap": total_market_cap,
                "total_volume": total_volume,
                "avg_change_percent": round(weighted_change, 2),
                "industries": industries_result,
            })
        
        # 7. Build final response
        total_tickers = sum(s["ticker_count"] for s in result_sectors)
        total_market_cap = sum(s["total_market_cap"] for s in result_sectors)
        
        if total_market_cap > 0:
            market_avg_change = sum(
                s["avg_change_percent"] * s["total_market_cap"]
                for s in result_sectors
            ) / total_market_cap
        else:
            market_avg_change = 0
        
        response = {
            "timestamp": snapshot_timestamp,
            "total_tickers": total_tickers,
            "total_market_cap": total_market_cap,
            "market_avg_change": round(market_avg_change, 2),
            "metric": metric,
            "size_by": size_by,
            "sectors": result_sectors,
            "is_realtime": is_realtime,  # False cuando usa datos del último cierre
        }
        
        # Update cache
        _cache[cache_key] = response
        _cache_timestamp = now
        
        return response
        
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/sectors")
async def get_sectors():
    """Get list of available sectors with their colors."""
    return {
        "sectors": [
            {"name": s, "color": SECTOR_COLORS.get(s, "#64748b")}
            for s in SECTOR_ORDER
        ]
    }
