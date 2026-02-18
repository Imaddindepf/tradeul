"""
MCP Server: Screener (DuckDB) + Thematic Classification
High-performance stock screener with 60+ indicators powered by DuckDB on Parquet files.
Includes thematic search via GICS classification and 124-theme taxonomy in TimescaleDB.
"""
from fastmcp import FastMCP
from clients.http_client import service_get, service_post
from clients.db_client import db_fetch
from config import config
from typing import Optional
import logging

logger = logging.getLogger(__name__)

mcp = FastMCP(
    "Tradeul Screener",
    instructions="DuckDB-powered stock screener with 60+ technical and fundamental indicators. "
    "Supports complex multi-criteria screening with SQL-like filter expressions. "
    "Also supports thematic stock discovery via 124-theme classification taxonomy. "
    "Data source: Polygon day_aggs Parquet files + TimescaleDB classification tables.",
)

AVAILABLE_INDICATORS = [
    "open", "high", "low", "close", "volume", "vwap", "transactions",
    "change_pct", "gap_pct", "range_pct", "dollar_volume",
    "relative_volume", "avg_volume_5d", "avg_volume_10d", "avg_volume_20d",
    "rsi_14", "rsi_7",
    "sma_5", "sma_10", "sma_20", "sma_50", "sma_200",
    "ema_9", "ema_12", "ema_20", "ema_26", "ema_50",
    "macd_line", "macd_signal", "macd_histogram",
    "bb_upper", "bb_middle", "bb_lower", "bb_width", "bb_position",
    "atr_14", "atr_percent",
    "adx_14", "plus_di", "minus_di",
    "stoch_k", "stoch_d",
    "obv", "obv_change",
    "change_1d", "change_3d", "change_5d", "change_10d", "change_20d",
    "high_52w", "low_52w", "from_52w_high", "from_52w_low",
    "above_sma_20", "above_sma_50", "above_sma_200",
    "dist_from_sma_20", "dist_from_sma_50", "dist_from_sma_200",
    "market_cap", "float_shares", "sector", "industry",
]


@mcp.tool()
async def run_screen(
    filters: list[dict],
    sort_by: str = "relative_volume",
    sort_order: str = "desc",
    limit: int = 50,
    symbols: Optional[list[str]] = None,
) -> dict:
    """Run a stock screen with multiple filter criteria.

    Each filter is a dict with: field, operator, value.
    Operators: 'gt', 'lt', 'gte', 'lte', 'eq', 'neq', 'between'

    Example filters:
    [
      {"field": "rsi_14", "operator": "lt", "value": 30},
      {"field": "relative_volume", "operator": "gt", "value": 2.0},
      {"field": "market_cap", "operator": "gt", "value": 100000000},
      {"field": "price", "operator": "between", "value": [5, 50]}
    ]

    Available indicators: close, volume, rsi_14, macd_line, bb_position,
    atr_percent, adx_14, stoch_k, relative_volume, change_pct, gap_pct,
    sma_20, ema_50, market_cap, float_shares, and 50+ more.

    Returns: list of matching tickers with all requested indicator values.
    """
    try:
        body = {
            "filters": filters,
            "sort_by": sort_by,
            "sort_order": sort_order,
            "limit": limit,
        }
        if symbols:
            body["symbols"] = symbols
        return await service_post(
            config.screener_url,
            "/api/v1/screener/screen",
            json_data=body,
        )
    except Exception as e:
        return {"error": str(e)}


@mcp.tool()
async def get_available_filters() -> dict:
    """Get all available screener filters/indicators with their descriptions.
    Use this to understand what criteria you can screen for."""
    return {
        "indicators": AVAILABLE_INDICATORS,
        "operators": ["gt", "lt", "gte", "lte", "eq", "neq", "between"],
        "sort_options": AVAILABLE_INDICATORS,
        "total_indicators": len(AVAILABLE_INDICATORS),
    }


@mcp.tool()
async def search_by_theme(
    themes: list[str],
    limit: int = 20,
    min_relevance: float = 0.5,
    operating_only: bool = True,
    sort_by: str = "relevance",
) -> dict:
    """Search stocks by investment theme from the 124-theme classification taxonomy.

    Themes are pre-computed tags assigned to every ticker via GICS + AI classification.
    This is deterministic (no LLM call) — pure SQL lookup, sub-10ms.

    Args:
        themes: One or more canonical theme tags (e.g. ["robotics"], ["memory_chips", "gpu_accelerators"]).
        limit: Max results to return (default 20).
        min_relevance: Minimum relevance score 0.0-1.0 (default 0.5).
        operating_only: If true, exclude ETFs/funds/SPACs (default true).
        sort_by: "relevance" (default), "market_cap", or "symbol".

    Returns: Matching tickers with classification, themes, and market cap.

    Example themes: semiconductors, memory_chips, gpu_accelerators, chip_foundry,
    analog_mixed_signal, power_semiconductors, eda_chip_design, rf_wireless_chips,
    networking_chips, artificial_intelligence, generative_ai, cybersecurity,
    identity_zero_trust, endpoint_network_security, cloud_computing, saas,
    enterprise_software, data_infrastructure, robotics, surgical_robotics,
    autonomous_vehicles, quantum_computing, blockchain_crypto, electric_vehicles,
    ev_charging, solar, wind, nuclear_energy, uranium, lithium, battery_storage,
    hydrogen_fuel_cells, gold_mining, silver_mining, copper, rare_earths,
    biotech, genomics, gene_editing_crispr, mrna_therapeutics, oncology,
    glp1_weight_loss, diabetes, neuroscience, rare_disease, medical_devices,
    digital_health, fintech, digital_payments, neobanking, insurtech,
    defense_contractors, defense_tech, space_technology, drones, shipping,
    e_commerce, streaming, esports_gaming, travel_tech, agriculture_agtech.
    """
    if not themes:
        return {"error": "No themes provided", "results": [], "count": 0}

    order_clause = {
        "relevance": "MAX(tt.relevance) DESC, tu.market_cap DESC NULLS LAST",
        "market_cap": "tu.market_cap DESC NULLS LAST, MAX(tt.relevance) DESC",
        "symbol": "tc.symbol ASC",
    }.get(sort_by, "MAX(tt.relevance) DESC, tu.market_cap DESC NULLS LAST")

    operating_filter = "AND tc.is_operating = true" if operating_only else ""

    query = f"""
        SELECT
            tc.symbol,
            tc.company_name_clean,
            tc.sector,
            tc.industry,
            tc.sub_industry,
            tc.is_operating,
            tu.market_cap,
            ARRAY_AGG(DISTINCT tt.theme ORDER BY tt.theme) AS matched_themes,
            MAX(tt.relevance) AS max_relevance,
            ROUND(AVG(tt.relevance), 2) AS avg_relevance
        FROM ticker_themes tt
        JOIN ticker_classification tc ON tt.symbol = tc.symbol
        LEFT JOIN tickers_unified tu ON tc.symbol = tu.symbol
        WHERE tt.theme = ANY($1)
          AND tt.relevance >= $2
          {operating_filter}
        GROUP BY tc.symbol, tc.company_name_clean, tc.sector, tc.industry,
                 tc.sub_industry, tc.is_operating, tu.market_cap
        ORDER BY {order_clause}
        LIMIT $3
    """

    try:
        rows = await db_fetch(query, themes, min_relevance, limit)
    except Exception as e:
        logger.error("search_by_theme error: %s", e)
        return {"error": str(e), "results": [], "count": 0}

    results = []
    for r in rows:
        results.append({
            "symbol": r["symbol"],
            "company_name": r["company_name_clean"],
            "sector": r["sector"],
            "industry": r["industry"],
            "sub_industry": r["sub_industry"],
            "is_operating": r["is_operating"],
            "market_cap": r["market_cap"],
            "matched_themes": r["matched_themes"],
            "relevance": float(r["max_relevance"]),
        })

    return {
        "themes_searched": themes,
        "count": len(results),
        "total_matched": len(results),
        "results": results,
    }


@mcp.tool()
async def list_available_themes() -> dict:
    """List all available thematic tags with ticker counts.
    Use this to discover what themes exist in the classification system."""
    try:
        rows = await db_fetch("""
            SELECT tt.theme, tt.theme_category, COUNT(DISTINCT tt.symbol) AS tickers
            FROM ticker_themes tt
            JOIN ticker_classification tc ON tt.symbol = tc.symbol
            WHERE tc.is_operating = true
            GROUP BY tt.theme, tt.theme_category
            ORDER BY tickers DESC
        """)
        themes = [{"theme": r["theme"], "category": r["theme_category"], "tickers": r["tickers"]} for r in rows]
        return {"themes": themes, "total": len(themes)}
    except Exception as e:
        return {"error": str(e)}


@mcp.tool()
async def enrich_with_classification(symbols: list[str]) -> dict:
    """Enrich a list of ticker symbols with GICS classification data.

    Replaces messy SIC codes with clean GICS sector/industry/sub-industry.
    Use this to add proper classification to scanner or enriched data.

    Returns a dict keyed by symbol with classification fields.
    """
    if not symbols:
        return {}

    upper = [s.upper() for s in symbols]
    try:
        rows = await db_fetch("""
            SELECT tc.symbol, tc.company_name_clean, tc.sector, tc.industry,
                   tc.sub_industry, tc.is_operating
            FROM ticker_classification tc
            WHERE tc.symbol = ANY($1)
        """, upper)
    except Exception as e:
        logger.error("enrich_with_classification error: %s", e)
        return {}

    result = {}
    for r in rows:
        result[r["symbol"]] = {
            "company_name": r["company_name_clean"],
            "sector": r["sector"],
            "industry": r["industry"],
            "sub_industry": r["sub_industry"],
            "is_operating": r["is_operating"],
        }
    return result


@mcp.tool()
async def get_daily_indicators(symbols: Optional[list[str]] = None) -> dict:
    """Get pre-computed daily indicators for all tickers or specific symbols.
    Includes: RSI, MACD, Bollinger Bands, SMA, EMA, ATR, ADX, and more.
    Updated every 5 minutes from DuckDB."""
    try:
        params = {}
        if symbols:
            params["symbols"] = ",".join(s.upper() for s in symbols)
        return await service_get(
            config.screener_url, "/api/v1/indicators", params=params
        )
    except Exception as e:
        return {"error": str(e)}
