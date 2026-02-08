"""
Alert Catalog API Routes

Exposes the event detector's alert catalog to the frontend.
Provides:
  - GET /api/alerts/catalog       — Full alert catalog with metadata
  - GET /api/alerts/categories    — Alert categories
  - GET /api/alerts/catalog/active — Only active (implemented) alerts
  - GET /api/alerts/catalog/phase/:phase — Alerts by implementation phase
"""

from fastapi import APIRouter
from typing import Dict, Any, List, Optional
from dataclasses import asdict

router = APIRouter(prefix="/api/alerts", tags=["alerts"])


# ============================================================================
# Alert Registry Data (embedded — no dependency on event_detector service)
# ============================================================================
# We embed the catalog data here rather than importing from event_detector
# because the API gateway runs independently. The data is static (only changes
# when we deploy new alert types).

# Categories
CATEGORIES = [
    {"id": "price",     "name": "Price",              "name_es": "Precio",             "icon": "TrendingUp",     "order": 1},
    {"id": "vwap",      "name": "VWAP",               "name_es": "VWAP",              "icon": "Activity",       "order": 2},
    {"id": "volume",    "name": "Volume",             "name_es": "Volumen",            "icon": "BarChart3",      "order": 3},
    {"id": "momentum",  "name": "Momentum",           "name_es": "Momentum",           "icon": "Zap",            "order": 4},
    {"id": "pullback",  "name": "Pullbacks",          "name_es": "Retrocesos",         "icon": "ArrowDownUp",    "order": 5},
    {"id": "gap",       "name": "Gap",                "name_es": "Gap",                "icon": "ArrowLeftRight", "order": 6},
    {"id": "ma_cross",  "name": "Moving Averages",    "name_es": "Medias Móviles",     "icon": "LineChart",      "order": 7},
    {"id": "bollinger", "name": "Bollinger Bands",    "name_es": "Bandas Bollinger",   "icon": "Maximize2",      "order": 8},
    {"id": "orb",       "name": "Opening Range",      "name_es": "Rango Apertura",     "icon": "Clock",          "order": 9},
    {"id": "timeframe", "name": "Timeframe Extremes", "name_es": "Extremos Temporales","icon": "Timer",          "order": 10},
    {"id": "consol",    "name": "Consolidation",      "name_es": "Consolidación",      "icon": "Square",         "order": 11},
    {"id": "candle",    "name": "Candlestick Patterns","name_es": "Patrones de Velas", "icon": "CandlestickChart","order": 12},
    {"id": "indicator", "name": "Technical Indicators","name_es": "Indicadores Técnicos","icon": "Settings2",    "order": 13},
    {"id": "pattern",   "name": "Chart Patterns",     "name_es": "Patrones Gráficos",  "icon": "Shapes",         "order": 14},
    {"id": "halt",      "name": "Halts & Resumes",    "name_es": "Halts y Reanudaciones","icon": "AlertTriangle","order": 15},
    {"id": "session",   "name": "Pre/Post Market",    "name_es": "Pre/Post Mercado",   "icon": "Sun",            "order": 16},
]

# Phase 1 alerts (active)
PHASE_1_ALERTS = [
    {"code": "NHP",  "event_type": "new_high",                 "name": "New High",                "name_es": "Nuevo Máximo",             "category": "price",    "direction": "+", "phase": 1, "active": True, "cooldown": 30,  "quality_filter": True},
    {"code": "NLP",  "event_type": "new_low",                  "name": "New Low",                 "name_es": "Nuevo Mínimo",             "category": "price",    "direction": "-", "phase": 1, "active": True, "cooldown": 30,  "quality_filter": True, "flip_code": "NHP"},
    {"code": "CAO",  "event_type": "crossed_above_open",       "name": "Crossed Above Open",      "name_es": "Cruzó Sobre Apertura",     "category": "price",    "direction": "+", "phase": 1, "active": True, "cooldown": 120, "flip_code": "CBO"},
    {"code": "CBO",  "event_type": "crossed_below_open",       "name": "Crossed Below Open",      "name_es": "Cruzó Bajo Apertura",      "category": "price",    "direction": "-", "phase": 1, "active": True, "cooldown": 120, "flip_code": "CAO"},
    {"code": "CAC",  "event_type": "crossed_above_prev_close", "name": "Crossed Above Close",     "name_es": "Cruzó Sobre Cierre",       "category": "price",    "direction": "+", "phase": 1, "active": True, "cooldown": 120, "flip_code": "CBC"},
    {"code": "CBC",  "event_type": "crossed_below_prev_close", "name": "Crossed Below Close",     "name_es": "Cruzó Bajo Cierre",        "category": "price",    "direction": "-", "phase": 1, "active": True, "cooldown": 120, "flip_code": "CAC"},
    {"code": "CAVC", "event_type": "vwap_cross_up",            "name": "Crossed Above VWAP",      "name_es": "Cruzó Sobre VWAP",         "category": "vwap",     "direction": "+", "phase": 1, "active": True, "cooldown": 60,  "flip_code": "CBVC"},
    {"code": "CBVC", "event_type": "vwap_cross_down",          "name": "Crossed Below VWAP",      "name_es": "Cruzó Bajo VWAP",          "category": "vwap",     "direction": "-", "phase": 1, "active": True, "cooldown": 60,  "flip_code": "CAVC"},
    {"code": "HRV",  "event_type": "rvol_spike",               "name": "High Relative Volume",    "name_es": "Alto Volumen Relativo",    "category": "volume",   "direction": "~", "phase": 1, "active": True, "cooldown": 120},
    {"code": "SV",   "event_type": "volume_surge",             "name": "Strong Volume",           "name_es": "Volumen Fuerte",           "category": "volume",   "direction": "~", "phase": 1, "active": True, "cooldown": 180},
    {"code": "VS1",  "event_type": "volume_spike_1min",        "name": "1 Min Volume Spike",      "name_es": "Pico Volumen 1 Min",       "category": "volume",   "direction": "~", "phase": 1, "active": True, "cooldown": 60},
    {"code": "UNOP", "event_type": "unusual_prints",           "name": "Unusual Prints",          "name_es": "Prints Inusuales",         "category": "volume",   "direction": "~", "phase": 1, "active": True, "cooldown": 120},
    {"code": "BP",   "event_type": "block_trade",              "name": "Block Trade",             "name_es": "Block Trade",              "category": "volume",   "direction": "~", "phase": 1, "active": True, "cooldown": 30},
    {"code": "RUN",  "event_type": "running_up",               "name": "Running Up Now",          "name_es": "Subiendo Ahora",           "category": "momentum", "direction": "+", "phase": 1, "active": True, "cooldown": 60,  "flip_code": "RDN"},
    {"code": "RDN",  "event_type": "running_down",             "name": "Running Down Now",        "name_es": "Bajando Ahora",            "category": "momentum", "direction": "-", "phase": 1, "active": True, "cooldown": 60,  "flip_code": "RUN"},
    {"code": "PUD",  "event_type": "percent_up_5",             "name": "% Up for the Day (5%)",   "name_es": "% Arriba del Día (5%)",    "category": "momentum", "direction": "+", "phase": 1, "active": True, "cooldown": 300, "flip_code": "PDD"},
    {"code": "PDD",  "event_type": "percent_down_5",           "name": "% Down for the Day (5%)", "name_es": "% Abajo del Día (5%)",     "category": "momentum", "direction": "-", "phase": 1, "active": True, "cooldown": 300, "flip_code": "PUD"},
    {"code": "PU10", "event_type": "percent_up_10",            "name": "% Up for the Day (10%)",  "name_es": "% Arriba del Día (10%)",   "category": "momentum", "direction": "+", "phase": 1, "active": True, "cooldown": 600},
    {"code": "PD10", "event_type": "percent_down_10",          "name": "% Down for the Day (10%)","name_es": "% Abajo del Día (10%)",    "category": "momentum", "direction": "-", "phase": 1, "active": True, "cooldown": 600},
    {"code": "PFH75","event_type": "pullback_75_from_high",    "name": "75% Pullback from Highs", "name_es": "Retroceso 75% Máximos",    "category": "pullback", "direction": "-", "phase": 1, "active": True, "cooldown": 120, "flip_code": "PFL75"},
    {"code": "PFH25","event_type": "pullback_25_from_high",    "name": "25% Pullback from Highs", "name_es": "Retroceso 25% Máximos",    "category": "pullback", "direction": "-", "phase": 1, "active": True, "cooldown": 120, "flip_code": "PFL25"},
    {"code": "PFL75","event_type": "pullback_75_from_low",     "name": "75% Pullback from Lows",  "name_es": "Retroceso 75% Mínimos",    "category": "pullback", "direction": "+", "phase": 1, "active": True, "cooldown": 120, "flip_code": "PFH75"},
    {"code": "PFL25","event_type": "pullback_25_from_low",     "name": "25% Pullback from Lows",  "name_es": "Retroceso 25% Mínimos",    "category": "pullback", "direction": "+", "phase": 1, "active": True, "cooldown": 120, "flip_code": "PFH25"},
    {"code": "GUR",  "event_type": "gap_up_reversal",          "name": "Gap Up Reversal",         "name_es": "Reversión Gap Alcista",    "category": "gap",      "direction": "-", "phase": 1, "active": True, "cooldown": 300, "flip_code": "GDR"},
    {"code": "GDR",  "event_type": "gap_down_reversal",        "name": "Gap Down Reversal",       "name_es": "Reversión Gap Bajista",    "category": "gap",      "direction": "+", "phase": 1, "active": True, "cooldown": 300, "flip_code": "GUR"},
    {"code": "HALT", "event_type": "halt",                     "name": "Halt",                    "name_es": "Halt",                     "category": "halt",     "direction": "~", "phase": 1, "active": True, "cooldown": 0,   "flip_code": "RESUME"},
    {"code": "RESUME","event_type": "resume",                  "name": "Resume",                  "name_es": "Reanudación",              "category": "halt",     "direction": "~", "phase": 1, "active": True, "cooldown": 0,   "flip_code": "HALT"},
]

# Phase 2 alerts (coming soon — daily indicators)
PHASE_2_ALERTS = [
    {"code": "CA200","event_type": "crossed_above_sma200",     "name": "Crossed Above 200 SMA",   "name_es": "Cruzó Sobre SMA 200",     "category": "ma_cross", "direction": "+", "phase": 2, "active": True,  "cooldown": 300, "flip_code": "CB200"},
    {"code": "CB200","event_type": "crossed_below_sma200",     "name": "Crossed Below 200 SMA",   "name_es": "Cruzó Bajo SMA 200",      "category": "ma_cross", "direction": "-", "phase": 2, "active": True,  "cooldown": 300, "flip_code": "CA200"},
    {"code": "CA50", "event_type": "crossed_above_sma50",      "name": "Crossed Above 50 SMA",    "name_es": "Cruzó Sobre SMA 50",      "category": "ma_cross", "direction": "+", "phase": 2, "active": True,  "cooldown": 300, "flip_code": "CB50"},
    {"code": "CB50", "event_type": "crossed_below_sma50",      "name": "Crossed Below 50 SMA",    "name_es": "Cruzó Bajo SMA 50",       "category": "ma_cross", "direction": "-", "phase": 2, "active": True,  "cooldown": 300, "flip_code": "CA50"},
    {"code": "CA20", "event_type": "crossed_above_sma20",      "name": "Crossed Above 20 SMA",    "name_es": "Cruzó Sobre SMA 20",      "category": "ma_cross", "direction": "+", "phase": 2, "active": True,  "cooldown": 300, "flip_code": "CB20"},
    {"code": "CB20", "event_type": "crossed_below_sma20",      "name": "Crossed Below 20 SMA",    "name_es": "Cruzó Bajo SMA 20",       "category": "ma_cross", "direction": "-", "phase": 2, "active": True,  "cooldown": 300, "flip_code": "CA20"},
    {"code": "BBU",  "event_type": "bb_upper_breakout",        "name": "Std Dev Breakout",        "name_es": "Ruptura Desv. Estándar",  "category": "bollinger","direction": "+", "phase": 2, "active": True,  "cooldown": 120, "flip_code": "BBD"},
    {"code": "BBD",  "event_type": "bb_lower_breakdown",       "name": "Std Dev Breakdown",       "name_es": "Quiebre Desv. Estándar",  "category": "bollinger","direction": "-", "phase": 2, "active": True,  "cooldown": 120, "flip_code": "BBU"},
    {"code": "CDHR", "event_type": "crossed_daily_high_resistance","name": "Crossed Daily High",   "name_es": "Cruzó Máximo Diario",     "category": "price",    "direction": "+", "phase": 2, "active": True,  "cooldown": 300, "flip_code": "CDLS"},
    {"code": "CDLS", "event_type": "crossed_daily_low_support", "name": "Crossed Daily Low",      "name_es": "Cruzó Mínimo Diario",     "category": "price",    "direction": "-", "phase": 2, "active": True,  "cooldown": 300, "flip_code": "CDHR"},
    {"code": "FGUR", "event_type": "false_gap_up_retracement", "name": "False Gap Up Retracement", "name_es": "Retroceso Falso Gap Up",  "category": "gap",      "direction": "-", "phase": 2, "active": True,  "cooldown": 600, "flip_code": "FGDR"},
    {"code": "FGDR", "event_type": "false_gap_down_retracement","name": "False Gap Down Retracement","name_es": "Retroceso Falso Gap Down","category": "gap",     "direction": "+", "phase": 2, "active": True,  "cooldown": 600, "flip_code": "FGUR"},
    {"code": "RU",   "event_type": "running_up_sustained",     "name": "Running Up",              "name_es": "Subiendo Sostenido",       "category": "momentum", "direction": "+", "phase": 2, "active": True,  "cooldown": 120, "flip_code": "RD"},
    {"code": "RD",   "event_type": "running_down_sustained",   "name": "Running Down",            "name_es": "Bajando Sostenido",        "category": "momentum", "direction": "-", "phase": 2, "active": True,  "cooldown": 120, "flip_code": "RU"},
    {"code": "RUC",  "event_type": "running_up_confirmed",     "name": "Running Up (Confirmed)",  "name_es": "Subiendo (Confirmado)",    "category": "momentum", "direction": "+", "phase": 2, "active": True,  "cooldown": 180, "flip_code": "RDC"},
    {"code": "RDC",  "event_type": "running_down_confirmed",   "name": "Running Down (Confirmed)","name_es": "Bajando (Confirmado)",     "category": "momentum", "direction": "-", "phase": 2, "active": True,  "cooldown": 180, "flip_code": "RUC"},
]

ALL_ALERTS = PHASE_1_ALERTS + PHASE_2_ALERTS


# ============================================================================
# Routes
# ============================================================================

@router.get("/catalog")
async def get_alert_catalog(
    locale: str = "en",
    phase: Optional[int] = None,
    category: Optional[str] = None,
    active_only: bool = False,
) -> Dict[str, Any]:
    """
    Get the full alert catalog with metadata.
    
    Query params:
        locale: 'en' or 'es' (affects name field)
        phase: Filter by implementation phase (1-6)
        category: Filter by category ID
        active_only: Only return active (implemented) alerts
    """
    alerts = ALL_ALERTS
    
    if active_only:
        alerts = [a for a in alerts if a.get("active")]
    if phase is not None:
        alerts = [a for a in alerts if a.get("phase") == phase]
    if category:
        alerts = [a for a in alerts if a.get("category") == category]
    
    # Apply locale
    if locale == "es":
        for a in alerts:
            a["display_name"] = a.get("name_es", a["name"])
    else:
        for a in alerts:
            a["display_name"] = a["name"]
    
    return {
        "alerts": alerts,
        "count": len(alerts),
        "total_in_catalog": len(ALL_ALERTS),
        "active_count": sum(1 for a in ALL_ALERTS if a.get("active")),
    }


@router.get("/categories")
async def get_alert_categories(locale: str = "en") -> Dict[str, Any]:
    """Get all alert categories with counts."""
    # Count alerts per category
    cat_counts = {}
    cat_active = {}
    for a in ALL_ALERTS:
        cat = a.get("category", "")
        cat_counts[cat] = cat_counts.get(cat, 0) + 1
        if a.get("active"):
            cat_active[cat] = cat_active.get(cat, 0) + 1
    
    categories = []
    for c in CATEGORIES:
        cat_id = c["id"]
        categories.append({
            **c,
            "display_name": c.get("name_es") if locale == "es" else c["name"],
            "alert_count": cat_counts.get(cat_id, 0),
            "active_count": cat_active.get(cat_id, 0),
        })
    
    return {"categories": categories}


@router.get("/catalog/active")
async def get_active_alerts(locale: str = "en") -> Dict[str, Any]:
    """Get only active (implemented) alerts."""
    return await get_alert_catalog(locale=locale, active_only=True)


@router.get("/catalog/phase/{phase}")
async def get_alerts_by_phase(phase: int, locale: str = "en") -> Dict[str, Any]:
    """Get alerts for a specific implementation phase."""
    return await get_alert_catalog(locale=locale, phase=phase)


@router.get("/stats")
async def get_alert_stats() -> Dict[str, Any]:
    """Get summary statistics of the alert system."""
    by_phase: Dict[int, int] = {}
    by_category: Dict[str, int] = {}
    active = 0
    
    for a in ALL_ALERTS:
        p = a.get("phase", 0)
        by_phase[p] = by_phase.get(p, 0) + 1
        c = a.get("category", "")
        by_category[c] = by_category.get(c, 0) + 1
        if a.get("active"):
            active += 1
    
    return {
        "total_alerts": len(ALL_ALERTS),
        "active_alerts": active,
        "categories": len(CATEGORIES),
        "by_phase": dict(sorted(by_phase.items())),
        "by_category": dict(sorted(by_category.items(), key=lambda x: -x[1])),
        "phase_names": {
            1: "Live (tick-based)",
            2: "Daily indicators",
            3: "Intraday bars",
            4: "Intraday indicators",
            5: "Candlestick patterns",
            6: "Chart patterns",
        },
    }
