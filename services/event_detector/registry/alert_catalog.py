"""
Alert Catalog - Complete registry of all market alert types.

Trade Ideas has ~300 alert types. We organize ours by implementation phase:
  Phase 1: Live now (current detectors, tick-based)
  Phase 2: Daily indicators (SMA/Bollinger crosses - needs screener bridge)
  Phase 3: Intraday bars (ORB, timeframe highs, consolidation - needs bar builder)
  Phase 4: Intraday indicators (MACD/Stochastic/SMA crosses per timeframe)
  Phase 5: Candlestick patterns (Doji, Hammer, Engulfing per timeframe)
  Phase 6: Advanced (chart patterns, Fibonacci, sector correlation)

Each alert has a short code (like Trade Ideas), display metadata,
and enough info for the frontend to render scan builders.
"""

from dataclasses import dataclass, field
from typing import Optional, List, Dict, Any


# ============================================================================
# Models
# ============================================================================

@dataclass(frozen=True)
class AlertCategory:
    """A grouping of related alert types."""
    id: str
    name: str
    name_es: str
    icon: str
    description: str
    description_es: str
    order: int  # Display order


@dataclass(frozen=True)
class AlertDefinition:
    """
    Complete definition of a market alert type.
    
    This is the "product catalog" — what the system CAN detect.
    Frontend uses this to build scan builders and display metadata.
    """
    code: str                     # Short code: "NHP", "CAO", "CA200"
    event_type: str               # EventType enum value: "new_high"
    name: str                     # English display name
    name_es: str                  # Spanish display name
    category: str                 # Category ID
    direction: str                # "+" (bullish), "-" (bearish), "~" (neutral)
    phase: int                    # Implementation phase (1-6)
    active: bool                  # True if detection is live
    cooldown: int                 # Default cooldown seconds
    description: str              # English description
    description_es: str           # Spanish description
    flip_code: Optional[str] = None       # Opposite alert code
    keywords: List[str] = field(default_factory=list)
    quality_filter: bool = False  # Supports quality/lookback filter
    quality_description: Optional[str] = None
    requires: List[str] = field(default_factory=list)  # Data requirements


# ============================================================================
# Categories
# ============================================================================

CATEGORY_CATALOG: Dict[str, AlertCategory] = {}

def _cat(id: str, name: str, name_es: str, icon: str, desc: str, desc_es: str, order: int):
    CATEGORY_CATALOG[id] = AlertCategory(id, name, name_es, icon, desc, desc_es, order)

_cat("price",      "Price",               "Precio",              "TrendingUp",    "Price highs, lows, and level crosses",         "Máximos, mínimos y cruces de niveles de precio",    1)
_cat("vwap",       "VWAP",                "VWAP",                "Activity",      "VWAP crosses and divergence",                  "Cruces y divergencia del VWAP",                      2)
_cat("volume",     "Volume",              "Volumen",             "BarChart3",     "Volume spikes, relative volume, block trades",  "Picos de volumen, volumen relativo, block trades",  3)
_cat("momentum",   "Momentum",            "Momentum",            "Zap",           "Running up/down, % change thresholds",         "Subiendo/bajando, umbrales de % cambio",             4)
_cat("pullback",   "Pullbacks",           "Retrocesos",          "ArrowDownUp",   "Retracements from highs/lows",                 "Retrocesos desde máximos/mínimos",                   5)
_cat("gap",        "Gap",                 "Gap",                 "ArrowLeftRight","Gap reversals and retracements",               "Reversiones y retrocesos de gap",                    6)
_cat("ma_cross",   "Moving Averages",     "Medias Móviles",      "LineChart",     "SMA/EMA crosses on daily and intraday",        "Cruces de SMA/EMA en diario e intradía",             7)
_cat("bollinger",  "Bollinger Bands",     "Bandas Bollinger",    "Maximize2",     "Standard deviation breakouts/breakdowns",      "Rupturas por desviación estándar",                   8)
_cat("orb",        "Opening Range",       "Rango Apertura",      "Clock",         "Opening range breakouts at multiple timeframes","Rupturas del rango de apertura en múltiples marcos", 9)
_cat("timeframe",  "Timeframe Extremes",  "Extremos Temporales", "Timer",         "New highs/lows at N-minute intervals",         "Nuevos máximos/mínimos en intervalos de N minutos",  10)
_cat("consol",     "Consolidation",       "Consolidación",       "Square",        "Consolidation breakouts/breakdowns",           "Rupturas de consolidación",                          11)
_cat("candle",     "Candlestick Patterns","Patrones de Velas",   "CandlestickChart","Doji, Hammer, Engulfing, etc.",              "Doji, Martillo, Envolvente, etc.",                   12)
_cat("indicator",  "Technical Indicators","Indicadores Técnicos","Settings2",     "MACD, Stochastic, RSI signals",                "Señales de MACD, Estocástico, RSI",                  13)
_cat("pattern",    "Chart Patterns",      "Patrones Gráficos",   "Shapes",        "H&S, Triangles, Rectangles, etc.",             "HCH, Triángulos, Rectángulos, etc.",                 14)
_cat("halt",       "Halts & Resumes",     "Halts y Reanudaciones","AlertTriangle","Trading halts and resumes",                    "Paradas y reanudaciones de trading",                 15)
_cat("session",    "Pre/Post Market",     "Pre/Post Mercado",    "Sun",           "Extended hours highs and lows",                "Máximos y mínimos en horario extendido",             16)

del _cat  # cleanup helper


# ============================================================================
# Alert Definitions — Complete Catalog
# ============================================================================

_alerts: List[AlertDefinition] = []

def _a(code, event_type, name, name_es, cat, direction, phase, active, cooldown,
       desc, desc_es, flip=None, keywords=None, quality=False, quality_desc=None, requires=None):
    _alerts.append(AlertDefinition(
        code=code, event_type=event_type, name=name, name_es=name_es,
        category=cat, direction=direction, phase=phase, active=active,
        cooldown=cooldown, description=desc, description_es=desc_es,
        flip_code=flip, keywords=keywords or [], quality_filter=quality,
        quality_description=quality_desc, requires=requires or [],
    ))


# ──────────────────────────────────────────────────────────────────────
# PHASE 1 — LIVE (tick-based, current detectors)
# ──────────────────────────────────────────────────────────────────────

# --- Price Events ---
_a("NHP",  "new_high",                 "New High",                  "Nuevo Máximo",               "price", "+", 1, True,  30,
   "Price reaches new intraday high",
   "El precio alcanza un nuevo máximo intradía",
   flip="NLP", keywords=["highs", "lows", "single print"], quality=True,
   quality_desc="Min days lookback (0=any, 1=above yesterday, 7=weekly, 365=52-week)")

_a("NLP",  "new_low",                  "New Low",                   "Nuevo Mínimo",               "price", "-", 1, True,  30,
   "Price reaches new intraday low",
   "El precio alcanza un nuevo mínimo intradía",
   flip="NHP", keywords=["highs", "lows", "single print"], quality=True,
   quality_desc="Min days lookback (0=any, 1=below yesterday, 7=weekly, 365=52-week)")

_a("CAO",  "crossed_above_open",       "Crossed Above Open",        "Cruzó Sobre Apertura",       "price", "+", 1, True,  120,
   "Price crosses above today's opening price",
   "El precio cruza por encima del precio de apertura de hoy",
   flip="CBO", keywords=["open", "cross"])

_a("CBO",  "crossed_below_open",       "Crossed Below Open",        "Cruzó Bajo Apertura",        "price", "-", 1, True,  120,
   "Price crosses below today's opening price",
   "El precio cruza por debajo del precio de apertura de hoy",
   flip="CAO", keywords=["open", "cross"])

_a("CAC",  "crossed_above_prev_close", "Crossed Above Close",       "Cruzó Sobre Cierre",         "price", "+", 1, True,  120,
   "Price crosses above previous day's close",
   "El precio cruza por encima del cierre del día anterior",
   flip="CBC", keywords=["close", "cross", "previous"])

_a("CBC",  "crossed_below_prev_close", "Crossed Below Close",       "Cruzó Bajo Cierre",          "price", "-", 1, True,  120,
   "Price crosses below previous day's close",
   "El precio cruza por debajo del cierre del día anterior",
   flip="CAC", keywords=["close", "cross", "previous"])

# --- VWAP Events ---
_a("CAVC", "vwap_cross_up",            "Crossed Above VWAP",        "Cruzó Sobre VWAP",           "vwap",  "+", 1, True,  60,
   "Price crosses above daily VWAP",
   "El precio cruza por encima del VWAP diario",
   flip="CBVC", keywords=["vwap", "cross"])

_a("CBVC", "vwap_cross_down",          "Crossed Below VWAP",        "Cruzó Bajo VWAP",            "vwap",  "-", 1, True,  60,
   "Price crosses below daily VWAP",
   "El precio cruza por debajo del VWAP diario",
   flip="CAVC", keywords=["vwap", "cross"])

# --- Volume Events ---
_a("HRV",  "rvol_spike",               "High Relative Volume",      "Alto Volumen Relativo",      "volume", "~", 1, True,  120,
   "Relative volume crosses above 3x normal",
   "El volumen relativo cruza por encima de 3x lo normal",
   keywords=["volume", "relative", "spike"])

_a("SV",   "volume_surge",             "Strong Volume",             "Volumen Fuerte",             "volume", "~", 1, True,  180,
   "Relative volume exceeds 5x normal",
   "El volumen relativo supera 5x lo normal",
   keywords=["volume", "surge", "strong"])

_a("VS1",  "volume_spike_1min",        "1 Minute Volume Spike",     "Pico Volumen 1 Min",         "volume", "~", 1, True,  60,
   "1-minute volume exceeds 50K shares",
   "El volumen de 1 minuto supera 50K acciones",
   keywords=["volume", "spike", "minute"])

_a("UNOP", "unusual_prints",           "Unusual Number of Prints",  "Prints Inusuales",           "volume", "~", 1, True,  120,
   "Number of trades significantly above normal (Z-score > 3)",
   "Número de operaciones significativamente por encima de lo normal (Z-score > 3)",
   keywords=["trades", "unusual", "prints"])

_a("BP",   "block_trade",              "Block Trade",               "Block Trade",                "volume", "~", 1, True,  30,
   "Large single-minute volume (>50K shares)",
   "Gran volumen en un solo minuto (>50K acciones)",
   keywords=["block", "trade", "large"])

# --- Momentum Events ---
_a("RUN",  "running_up",               "Running Up Now",            "Subiendo Ahora",             "momentum", "+", 1, True,  60,
   "Price up >2% in last 5 minutes",
   "Precio sube >2% en los últimos 5 minutos",
   flip="RDN", keywords=["running", "momentum", "fast"])

_a("RDN",  "running_down",             "Running Down Now",          "Bajando Ahora",              "momentum", "-", 1, True,  60,
   "Price down >2% in last 5 minutes",
   "Precio baja >2% en los últimos 5 minutos",
   flip="RUN", keywords=["running", "momentum", "fast"])

_a("PUD",  "percent_up_5",             "% Up for the Day (5%)",     "% Arriba del Día (5%)",      "momentum", "+", 1, True,  300,
   "Daily change crosses above +5%",
   "El cambio diario cruza por encima de +5%",
   flip="PDD", keywords=["percent", "change", "daily"])

_a("PDD",  "percent_down_5",           "% Down for the Day (5%)",   "% Abajo del Día (5%)",       "momentum", "-", 1, True,  300,
   "Daily change crosses below -5%",
   "El cambio diario cruza por debajo de -5%",
   flip="PUD", keywords=["percent", "change", "daily"])

_a("PU10", "percent_up_10",            "% Up for the Day (10%)",    "% Arriba del Día (10%)",     "momentum", "+", 1, True,  600,
   "Daily change crosses above +10%",
   "El cambio diario cruza por encima de +10%",
   keywords=["percent", "change", "daily"])

_a("PD10", "percent_down_10",          "% Down for the Day (10%)",  "% Abajo del Día (10%)",      "momentum", "-", 1, True,  600,
   "Daily change crosses below -10%",
   "El cambio diario cruza por debajo de -10%",
   keywords=["percent", "change", "daily"])

# --- Pullback Events ---
_a("PFH75","pullback_75_from_high",    "75% Pullback from Highs",   "Retroceso 75% desde Máximos","pullback", "-", 1, True,  120,
   "Price retraces 75% from intraday high toward low",
   "El precio retrocede 75% desde el máximo intradía hacia el mínimo",
   flip="PFL75", keywords=["pullback", "retrace"])

_a("PFH25","pullback_25_from_high",    "25% Pullback from Highs",   "Retroceso 25% desde Máximos","pullback", "-", 1, True,  120,
   "Price retraces 25% from intraday high toward low",
   "El precio retrocede 25% desde el máximo intradía hacia el mínimo",
   flip="PFL25", keywords=["pullback", "retrace"])

_a("PFL75","pullback_75_from_low",     "75% Pullback from Lows",    "Retroceso 75% desde Mínimos","pullback", "+", 1, True,  120,
   "Price bounces 75% from intraday low toward high",
   "El precio rebota 75% desde el mínimo intradía hacia el máximo",
   flip="PFH75", keywords=["pullback", "bounce"])

_a("PFL25","pullback_25_from_low",     "25% Pullback from Lows",    "Retroceso 25% desde Mínimos","pullback", "+", 1, True,  120,
   "Price bounces 25% from intraday low toward high",
   "El precio rebota 25% desde el mínimo intradía hacia el máximo",
   flip="PFH25", keywords=["pullback", "bounce"])

# --- Gap Events ---
_a("GUR",  "gap_up_reversal",          "Gap Up Reversal",           "Reversión Gap Alcista",      "gap",  "-", 1, True,  300,
   "Stock gapped up ≥2% but price crosses below open",
   "La acción abrió con gap alcista ≥2% pero el precio cruza bajo la apertura",
   flip="GDR", keywords=["gap", "reversal"])

_a("GDR",  "gap_down_reversal",        "Gap Down Reversal",         "Reversión Gap Bajista",      "gap",  "+", 1, True,  300,
   "Stock gapped down ≥2% but price crosses above open",
   "La acción abrió con gap bajista ≥2% pero el precio cruza sobre la apertura",
   flip="GUR", keywords=["gap", "reversal"])

# --- Halt Events ---
_a("HALT", "halt",                     "Halt",                      "Halt",                       "halt", "~", 1, True,  0,
   "Trading halt triggered (LULD or regulatory)",
   "Se activó una parada de trading (LULD o regulatoria)",
   flip="RESUME", keywords=["halt", "pause", "luld"])

_a("RESUME","resume",                  "Resume",                    "Reanudación",                "halt", "~", 1, True,  0,
   "Trading resumes after halt",
   "El trading se reanuda después de una parada",
   flip="HALT", keywords=["resume", "halt"])


# ──────────────────────────────────────────────────────────────────────
# PHASE 1B — SNAPSHOT-DRIVEN (active, detected from enriched snapshot)
# ──────────────────────────────────────────────────────────────────────

# --- DEPRECATED: Price vs Intraday EMA (1-min) — NO LONGER EMITTED ---
# Trade Ideas CA20/CA50/CB20/CB50 are DAILY MAs, not intraday.
_a("iCA20", "crossed_above_ema20",     "Crossed Above EMA 20 (1m)", "Cruzó Sobre EMA 20 (1m)",    "ma_cross", "+", 1, False, 300,
   "DEPRECATED: Price crosses above intraday EMA(20) from 1-min bars",
   "DEPRECADO: Cruce intraday EMA(20) — no aporta edge",
   flip="iCB20", keywords=["ema", "20", "intraday", "deprecated"],
   requires=["ema_20"])

_a("iCB20", "crossed_below_ema20",     "Crossed Below EMA 20 (1m)", "Cruzó Bajo EMA 20 (1m)",     "ma_cross", "-", 1, False, 300,
   "DEPRECATED: Price crosses below intraday EMA(20) from 1-min bars",
   "DEPRECADO: Cruce intraday EMA(20) — no aporta edge",
   flip="iCA20", keywords=["ema", "20", "intraday", "deprecated"],
   requires=["ema_20"])

_a("iCA50", "crossed_above_ema50",     "Crossed Above EMA 50 (1m)", "Cruzó Sobre EMA 50 (1m)",    "ma_cross", "+", 1, False, 300,
   "DEPRECATED: Price crosses above intraday EMA(50) from 1-min bars",
   "DEPRECADO: Cruce intraday EMA(50) — no aporta edge",
   flip="iCB50", keywords=["ema", "50", "intraday", "deprecated"],
   requires=["ema_50"])

_a("iCB50", "crossed_below_ema50",     "Crossed Below EMA 50 (1m)", "Cruzó Bajo EMA 50 (1m)",     "ma_cross", "-", 1, False, 300,
   "DEPRECATED: Price crosses below intraday EMA(50) from 1-min bars",
   "DEPRECADO: Cruce intraday EMA(50) — no aporta edge",
   flip="iCA50", keywords=["ema", "50", "intraday", "deprecated"],
   requires=["ema_50"])

# --- Bollinger Band Events ---
_a("BBU",  "bb_upper_breakout",        "BB Upper Breakout",         "Ruptura BB Superior",        "bollinger", "+", 1, True, 120,
   "Price crosses above upper Bollinger Band (2σ above EMA 20)",
   "El precio cruza por encima de la Banda Bollinger superior (2σ sobre EMA 20)",
   flip="BBD", keywords=["bollinger", "breakout", "std dev", "band"],
   requires=["bb_upper"])

_a("BBD",  "bb_lower_breakdown",       "BB Lower Breakdown",        "Quiebre BB Inferior",        "bollinger", "-", 1, True, 120,
   "Price crosses below lower Bollinger Band (2σ below EMA 20)",
   "El precio cruza por debajo de la Banda Bollinger inferior (2σ bajo EMA 20)",
   flip="BBU", keywords=["bollinger", "breakdown", "std dev", "band"],
   requires=["bb_lower"])

# --- DEPRECATED: Price vs Intraday SMA (1-min) — NO LONGER EMITTED ---
# Trade Ideas does NOT have price-vs-intraday-SMA alerts. Only DAILY MAs.
_a("CAS8", "crossed_above_sma8",       "Crossed Above SMA 8 (1m)",  "Cruzó Sobre SMA 8 (1m)",    "ma_cross", "+", 1, False, 120,
   "DEPRECATED: Price vs intraday SMA(8) — not in Trade Ideas, pure noise",
   "DEPRECADO: Precio vs SMA(8) intradía — no existe en Trade Ideas",
   flip="CBS8", keywords=["deprecated"], requires=["sma_8"])

_a("CBS8", "crossed_below_sma8",       "Crossed Below SMA 8 (1m)",  "Cruzó Bajo SMA 8 (1m)",     "ma_cross", "-", 1, False, 120,
   "DEPRECATED", "DEPRECADO", flip="CAS8", keywords=["deprecated"], requires=["sma_8"])

_a("CAS20","crossed_above_sma20",      "Crossed Above SMA 20 (1m)", "Cruzó Sobre SMA 20 (1m)",   "ma_cross", "+", 1, False, 180,
   "DEPRECATED: Use CA20D (daily) instead", "DEPRECADO: Usar CA20D (diario)",
   flip="CBS20", keywords=["deprecated"], requires=["sma_20"])

_a("CBS20","crossed_below_sma20",      "Crossed Below SMA 20 (1m)", "Cruzó Bajo SMA 20 (1m)",    "ma_cross", "-", 1, False, 180,
   "DEPRECATED", "DEPRECADO", flip="CAS20", keywords=["deprecated"], requires=["sma_20"])

_a("CAS50","crossed_above_sma50",      "Crossed Above SMA 50 (1m)", "Cruzó Sobre SMA 50 (1m)",   "ma_cross", "+", 1, False, 300,
   "DEPRECATED: Use CA50D (daily) instead", "DEPRECADO: Usar CA50D (diario)",
   flip="CBS50", keywords=["deprecated"], requires=["sma_50"])

_a("CBS50","crossed_below_sma50",      "Crossed Below SMA 50 (1m)", "Cruzó Bajo SMA 50 (1m)",    "ma_cross", "-", 1, False, 300,
   "DEPRECATED", "DEPRECADO", flip="CAS50", keywords=["deprecated"], requires=["sma_50"])

# --- DEPRECATED: 1-min MA-to-MA Cross (replaced by 5m ECAY5/ECBY5) ---
_a("SXU",  "sma_8_cross_above_20",     "SMA 8/20 Golden Cross (1m)","Cruce Dorado 8/20 (1m)",    "ma_cross", "+", 1, False, 300,
   "DEPRECATED: Use ECAY5 (5-min) instead", "DEPRECADO: Usar ECAY5 (5 min)",
   flip="SXD", keywords=["deprecated"], requires=["sma_8", "sma_20"])

_a("SXD",  "sma_8_cross_below_20",     "SMA 8/20 Death Cross (1m)", "Cruce Mortal 8/20 (1m)",    "ma_cross", "-", 1, False, 300,
   "DEPRECATED: Use ECBY5 (5-min) instead", "DEPRECADO: Usar ECBY5 (5 min)",
   flip="SXU", keywords=["deprecated"], requires=["sma_8", "sma_20"])

# --- DEPRECATED: 1-min MACD (replaced by 5m MDAS5/MDBS5) ---
_a("MACDU","macd_cross_bullish",        "MACD Bullish Cross (1m)",   "Cruce MACD Alcista (1m)",    "indicator", "+", 1, False, 300,
   "DEPRECATED: Use MDAS5 (5-min) instead", "DEPRECADO: Usar MDAS5 (5 min)",
   flip="MACDD", keywords=["deprecated"], requires=["macd_line", "macd_signal"])

_a("MACDD","macd_cross_bearish",        "MACD Bearish Cross (1m)",   "Cruce MACD Bajista (1m)",    "indicator", "-", 1, False, 300,
   "DEPRECATED", "DEPRECADO", flip="MACDU", keywords=["deprecated"], requires=["macd_line", "macd_signal"])

_a("MZU",  "macd_zero_cross_up",        "MACD Zero Up (1m)",         "MACD Cero Arriba (1m)",     "indicator", "+", 1, False, 600,
   "DEPRECATED: Use MDAZ5 (5-min) instead", "DEPRECADO: Usar MDAZ5 (5 min)",
   flip="MZD", keywords=["deprecated"], requires=["macd_line"])

_a("MZD",  "macd_zero_cross_down",      "MACD Zero Down (1m)",       "MACD Cero Abajo (1m)",      "indicator", "-", 1, False, 600,
   "DEPRECATED", "DEPRECADO", flip="MZU", keywords=["deprecated"], requires=["macd_line"])

# --- DEPRECATED: 1-min Stochastic (replaced by 5m) ---
_a("STBU", "stoch_cross_bullish",       "Stoch Bullish (1m)",        "Estocástico Alcista (1m)",   "indicator", "+", 1, False, 300,
   "DEPRECATED: Use 5-min stochastic", "DEPRECADO: Usar estocástico 5 min",
   flip="STBD", keywords=["deprecated"], requires=["stoch_k", "stoch_d"])

_a("STBD", "stoch_cross_bearish",       "Stoch Bearish (1m)",        "Estocástico Bajista (1m)",   "indicator", "-", 1, False, 300,
   "DEPRECATED", "DEPRECADO", flip="STBU", keywords=["deprecated"], requires=["stoch_k", "stoch_d"])

_a("STOS", "stoch_oversold",            "Stoch Oversold (1m)",       "Sobreventa (1m)",            "indicator", "-", 1, False, 600,
   "DEPRECATED", "DEPRECADO", flip="STOB", keywords=["deprecated"], requires=["stoch_k"])

_a("STOB", "stoch_overbought",          "Stoch Overbought (1m)",     "Sobrecompra (1m)",           "indicator", "+", 1, False, 600,
   "DEPRECATED", "DEPRECADO", flip="STOS", keywords=["deprecated"], requires=["stoch_k"])

# --- Opening Range Breakout (5-min ORB, active) ---
_a("ORBU", "orb_breakout_up",           "Opening Range Breakout Up", "Ruptura Rango Apertura",     "orb", "+", 1, True, 600,
   "Price breaks above the 5-minute opening range high",
   "El precio rompe por encima del máximo del rango de apertura de 5 minutos",
   flip="ORBD", keywords=["opening range", "breakout", "ORB"],
   requires=["open_price", "intraday_high"])

_a("ORBD", "orb_breakout_down",         "Opening Range Breakout Down","Quiebre Rango Apertura",    "orb", "-", 1, True, 600,
   "Price breaks below the 5-minute opening range low",
   "El precio rompe por debajo del mínimo del rango de apertura de 5 minutos",
   flip="ORBU", keywords=["opening range", "breakdown", "ORB"],
   requires=["open_price", "intraday_low"])

# --- Consolidation Breakout (active, from window metrics) ---
_a("CBU",  "consolidation_breakout_up",  "Consolidation Breakout",   "Ruptura Consolidación",     "consol", "+", 1, True, 600,
   "Price breaks out of tight consolidation (low chg_5/10min then sudden 1min move)",
   "El precio rompe un rango de consolidación estrecho con impulso repentino",
   flip="CBD", keywords=["consolidation", "breakout", "tight range"],
   requires=["chg_1min", "chg_5min", "chg_10min"])

_a("CBD",  "consolidation_breakout_down","Consolidation Breakdown",   "Quiebre Consolidación",    "consol", "-", 1, True, 600,
   "Price breaks down from tight consolidation (low chg_5/10min then sudden 1min drop)",
   "El precio quiebra un rango de consolidación estrecho con caída repentina",
   flip="CBU", keywords=["consolidation", "breakdown", "tight range"],
   requires=["chg_1min", "chg_5min", "chg_10min"])

# ──────────────────────────────────────────────────────────────────────
# PHASE 2 — FUTURE (requires additional data / infrastructure)
# ──────────────────────────────────────────────────────────────────────

# --- Daily SMA Crosses (Trade Ideas CA20/CA50/CA200/CB20/CB50/CB200) ---
# These are the REAL MA alerts — price vs DAILY moving averages. Rare, meaningful.
_a("CA20D","crossed_above_sma20_daily", "Crossed Above 20-Day SMA",  "Cruzó Sobre SMA 20 Diaria",  "ma_cross", "+", 2, True, 600,
   "Price crosses above 20-day simple moving average (short-term trend shift)",
   "El precio cruza por encima de la SMA de 20 días (cambio de tendencia a corto plazo)",
   flip="CB20D", keywords=["sma", "20", "moving average", "daily"],
   requires=["daily_sma_20"])

_a("CB20D","crossed_below_sma20_daily", "Crossed Below 20-Day SMA",  "Cruzó Bajo SMA 20 Diaria",   "ma_cross", "-", 2, True, 600,
   "Price crosses below 20-day simple moving average",
   "El precio cruza por debajo de la SMA de 20 días",
   flip="CA20D", keywords=["sma", "20", "moving average", "daily"],
   requires=["daily_sma_20"])

_a("CA50D","crossed_above_sma50_daily", "Crossed Above 50-Day SMA",  "Cruzó Sobre SMA 50 Diaria",  "ma_cross", "+", 2, True, 600,
   "Price crosses above 50-day simple moving average (major trend change)",
   "El precio cruza por encima de la SMA de 50 días (cambio de tendencia mayor)",
   flip="CB50D", keywords=["sma", "50", "moving average", "daily"],
   requires=["daily_sma_50"])

_a("CB50D","crossed_below_sma50_daily", "Crossed Below 50-Day SMA",  "Cruzó Bajo SMA 50 Diaria",   "ma_cross", "-", 2, True, 600,
   "Price crosses below 50-day simple moving average",
   "El precio cruza por debajo de la SMA de 50 días",
   flip="CA50D", keywords=["sma", "50", "moving average", "daily"],
   requires=["daily_sma_50"])

_a("CA200","crossed_above_sma200",     "Crossed Above 200-Day SMA", "Cruzó Sobre SMA 200 Diaria", "ma_cross", "+", 2, True, 600,
   "Price crosses above 200-day simple moving average (long-term trend shift)",
   "El precio cruza por encima de la media móvil simple de 200 días",
   flip="CB200", keywords=["sma", "200", "moving average", "daily"],
   requires=["daily_sma_200"])

_a("CB200","crossed_below_sma200",     "Crossed Below 200-Day SMA", "Cruzó Bajo SMA 200 Diaria",  "ma_cross", "-", 2, True, 600,
   "Price crosses below 200-day simple moving average",
   "El precio cruza por debajo de la media móvil simple de 200 días",
   flip="CA200", keywords=["sma", "200", "moving average", "daily"],
   requires=["daily_sma_200"])

# --- 5-min SMA(8) vs SMA(20) Cross (Trade Ideas ECAY5/ECBY5) — ACTIVE ---
_a("ECAY5","sma8_above_sma20_5min",    "SMA 8/20 Golden Cross (5m)","Cruce Dorado 8/20 (5m)",     "indicator", "+", 4, True, 300,
   "8-period SMA crosses above 20-period SMA on 5-minute chart",
   "SMA de 8 cruza sobre SMA de 20 en gráfico de 5 minutos",
   flip="ECBY5", keywords=["sma", "golden cross", "5min"],
   requires=["sma_8_5m", "sma_20_5m"])

_a("ECBY5","sma8_below_sma20_5min",    "SMA 8/20 Death Cross (5m)", "Cruce Mortal 8/20 (5m)",     "indicator", "-", 4, True, 300,
   "8-period SMA crosses below 20-period SMA on 5-minute chart",
   "SMA de 8 cruza bajo SMA de 20 en gráfico de 5 minutos",
   flip="ECAY5", keywords=["sma", "death cross", "5min"],
   requires=["sma_8_5m", "sma_20_5m"])

# --- 5-min MACD (Trade Ideas MDAS5/MDBS5/MDAZ5/MDBZ5) — ACTIVE ---
_a("MDAS5","macd_above_signal_5min",   "MACD Above Signal (5m)",    "MACD Sobre Señal (5m)",      "indicator", "+", 4, True, 300,
   "MACD crosses above signal line on 5-minute chart",
   "MACD cruza sobre la línea de señal en gráfico de 5 minutos",
   flip="MDBS5", keywords=["macd", "signal", "5min"],
   requires=["macd_line_5m", "macd_signal_5m"])

_a("MDBS5","macd_below_signal_5min",   "MACD Below Signal (5m)",    "MACD Bajo Señal (5m)",       "indicator", "-", 4, True, 300,
   "MACD crosses below signal line on 5-minute chart",
   "MACD cruza bajo la línea de señal en gráfico de 5 minutos",
   flip="MDAS5", keywords=["macd", "signal", "5min"],
   requires=["macd_line_5m", "macd_signal_5m"])

_a("MDAZ5","macd_above_zero_5min",     "MACD Above Zero (5m)",      "MACD Sobre Cero (5m)",       "indicator", "+", 4, True, 600,
   "MACD crosses above zero on 5-minute chart (trend bullish)",
   "MACD cruza sobre cero en gráfico de 5 minutos",
   flip="MDBZ5", keywords=["macd", "zero", "5min"],
   requires=["macd_line_5m"])

_a("MDBZ5","macd_below_zero_5min",     "MACD Below Zero (5m)",      "MACD Bajo Cero (5m)",        "indicator", "-", 4, True, 600,
   "MACD crosses below zero on 5-minute chart (trend bearish)",
   "MACD cruza bajo cero en gráfico de 5 minutos",
   flip="MDAZ5", keywords=["macd", "zero", "5min"],
   requires=["macd_line_5m"])

# --- 5-min Stochastic (Trade Ideas SC20_5/SC80_5) — ACTIVE ---
_a("SC20_5","stoch_cross_bullish_5min", "Stoch Bullish Cross (5m)",  "Estocástico Alcista (5m)",   "indicator", "+", 4, True, 300,
   "Stochastic %K crosses above %D from oversold on 5-minute chart",
   "Estocástico %K cruza sobre %D desde sobreventa en gráfico de 5 minutos",
   flip="SC80_5", keywords=["stochastic", "oversold", "5min"],
   requires=["stoch_k_5m", "stoch_d_5m"])

_a("SC80_5","stoch_cross_bearish_5min", "Stoch Bearish Cross (5m)",  "Estocástico Bajista (5m)",   "indicator", "-", 4, True, 300,
   "Stochastic %K crosses below %D from overbought on 5-minute chart",
   "Estocástico %K cruza bajo %D desde sobrecompra en gráfico de 5 minutos",
   flip="SC20_5", keywords=["stochastic", "overbought", "5min"],
   requires=["stoch_k_5m", "stoch_d_5m"])

_a("STO5","stoch_oversold_5min",        "Stoch Oversold (5m)",       "Sobreventa Estocástico (5m)","indicator", "-", 4, True, 600,
   "Stochastic %K enters oversold zone (<20) on 5-minute chart",
   "Estocástico %K entra en sobreventa (<20) en gráfico de 5 minutos",
   flip="STB5", keywords=["stochastic", "oversold", "5min"],
   requires=["stoch_k_5m"])

_a("STB5","stoch_overbought_5min",      "Stoch Overbought (5m)",     "Sobrecompra Estocástico (5m)","indicator", "+", 4, True, 600,
   "Stochastic %K enters overbought zone (>80) on 5-minute chart",
   "Estocástico %K entra en sobrecompra (>80) en gráfico de 5 minutos",
   flip="STO5", keywords=["stochastic", "overbought", "5min"],
   requires=["stoch_k_5m"])

# --- Pre/Post Market ---
_a("HPRE", "pre_market_high",          "Pre-Market High",           "Máximo Pre-Market",          "session", "+", 2, True, 30,
   "Stock makes new high during pre-market session",
   "La acción alcanza un nuevo máximo durante la sesión pre-market",
   flip="LPRE", keywords=["pre-market", "high", "extended"],
   requires=["market_session"])

_a("LPRE", "pre_market_low",           "Pre-Market Low",            "Mínimo Pre-Market",          "session", "-", 2, True, 30,
   "Stock makes new low during pre-market session",
   "La acción alcanza un nuevo mínimo durante la sesión pre-market",
   flip="HPRE", keywords=["pre-market", "low", "extended"])

_a("HPOST","post_market_high",         "Post-Market High",          "Máximo Post-Market",         "session", "+", 2, True, 30,
   "Stock makes new high during post-market session",
   "La acción alcanza un nuevo máximo durante la sesión post-market",
   flip="LPOST", keywords=["post-market", "high", "extended"])

_a("LPOST","post_market_low",          "Post-Market Low",           "Mínimo Post-Market",         "session", "-", 2, True, 30,
   "Stock makes new low during post-market session",
   "La acción alcanza un nuevo mínimo durante la sesión post-market",
   flip="HPOST", keywords=["post-market", "low", "extended"])

# --- Confirmed Crosses ---
_a("CAOC", "crossed_above_open_confirmed",  "Crossed Above Open (Confirmed)", "Cruzó Sobre Apertura (Conf.)",  "price", "+", 2, True, 300,
   "Price crosses above open and stays above for 30+ seconds",
   "El precio cruza sobre la apertura y se mantiene por 30+ segundos",
   flip="CBOC", keywords=["open", "cross", "confirmed"])

_a("CBOC", "crossed_below_open_confirmed",  "Crossed Below Open (Confirmed)", "Cruzó Bajo Apertura (Conf.)",   "price", "-", 2, True, 300,
   "Price crosses below open and stays below for 30+ seconds",
   "El precio cruza bajo la apertura y se mantiene por 30+ segundos",
   flip="CAOC", keywords=["open", "cross", "confirmed"])

_a("CACC", "crossed_above_close_confirmed", "Crossed Above Close (Confirmed)","Cruzó Sobre Cierre (Conf.)",    "price", "+", 2, True, 300,
   "Price crosses above prev close and stays above for 30+ seconds",
   "El precio cruza sobre el cierre previo y se mantiene por 30+ segundos",
   flip="CBCC", keywords=["close", "cross", "confirmed"])

_a("CBCC", "crossed_below_close_confirmed", "Crossed Below Close (Confirmed)","Cruzó Bajo Cierre (Conf.)",     "price", "-", 2, True, 300,
   "Price crosses below prev close and stays below for 30+ seconds",
   "El precio cruza bajo el cierre previo y se mantiene por 30+ segundos",
   flip="CACC", keywords=["close", "cross", "confirmed"])

# --- Gap Variants (active: gap_percent and prev_close available from REST) ---
_a("FGUR", "false_gap_up_retracement", "False Gap Up Retracement",  "Retroceso Falso Gap Alcista", "gap", "-", 1, True, 300,
   "Gap up stock fully retraces to previous close level",
   "Acción con gap alcista retrocede completamente al nivel del cierre previo",
   flip="FGDR", keywords=["gap", "false", "retrace"],
   requires=["gap_percent", "prev_close"])

_a("FGDR", "false_gap_down_retracement","False Gap Down Retracement","Retroceso Falso Gap Bajista", "gap", "+", 1, True, 300,
   "Gap down stock fully retraces back up to previous close level",
   "Acción con gap bajista retrocede completamente al nivel del cierre previo",
   flip="FGUR", keywords=["gap", "false", "retrace"],
   requires=["gap_percent", "prev_close"])

# --- Pullback Variants (from open/close) ---
_a("PFH75C","pullback_75_from_high_close", "75% Pullback from Highs (Close)", "Retroceso 75% Máx (Cierre)", "pullback", "-", 2, True, 120,
   "Price retraces 75% from high toward previous close",
   "El precio retrocede 75% desde el máximo hacia el cierre previo",
   flip="PFL75C", keywords=["pullback", "retrace", "close"])

_a("PFL75C","pullback_75_from_low_close",  "75% Pullback from Lows (Close)",  "Retroceso 75% Mín (Cierre)", "pullback", "+", 2, True, 120,
   "Price bounces 75% from low toward previous close",
   "El precio rebota 75% desde el mínimo hacia el cierre previo",
   flip="PFH75C", keywords=["pullback", "bounce", "close"])

_a("PFH25C","pullback_25_from_high_close", "25% Pullback from Highs (Close)", "Retroceso 25% Máx (Cierre)", "pullback", "-", 2, True, 120,
   "Price retraces 25% from high toward previous close",
   "El precio retrocede 25% desde el máximo hacia el cierre previo",
   flip="PFL25C", keywords=["pullback", "retrace", "close"])

_a("PFL25C","pullback_25_from_low_close",  "25% Pullback from Lows (Close)",  "Retroceso 25% Mín (Cierre)", "pullback", "+", 2, True, 120,
   "Price bounces 25% from low toward previous close",
   "El precio rebota 25% desde el mínimo hacia el cierre previo",
   flip="PFH25C", keywords=["pullback", "bounce", "close"])

_a("PFH75O","pullback_75_from_high_open",  "75% Pullback from Highs (Open)", "Retroceso 75% Máx (Apert.)", "pullback", "-", 2, True, 120,
   "Price retraces 75% from high toward today's open",
   "El precio retrocede 75% desde el máximo hacia la apertura",
   flip="PFL75O", keywords=["pullback", "retrace", "open"])

_a("PFL75O","pullback_75_from_low_open",   "75% Pullback from Lows (Open)",  "Retroceso 75% Mín (Apert.)", "pullback", "+", 2, True, 120,
   "Price bounces 75% from low toward today's open",
   "El precio rebota 75% desde el mínimo hacia la apertura",
   flip="PFH75O", keywords=["pullback", "bounce", "open"])

_a("PFH25O","pullback_25_from_high_open",  "25% Pullback from Highs (Open)", "Retroceso 25% Máx (Apert.)", "pullback", "-", 2, True, 120,
   "Price retraces 25% from high toward today's open",
   "El precio retrocede 25% desde el máximo hacia la apertura",
   flip="PFL25O", keywords=["pullback", "retrace", "open"])

_a("PFL25O","pullback_25_from_low_open",   "25% Pullback from Lows (Open)",  "Retroceso 25% Mín (Apert.)", "pullback", "+", 2, True, 120,
   "Price bounces 25% from low toward today's open",
   "El precio rebota 25% desde el mínimo hacia la apertura",
   flip="PFH25O", keywords=["pullback", "bounce", "open"])

# --- Running Variants (active: chg_Xmin from window trackers) ---
_a("RU",   "running_up_sustained",     "Running Up Sustained",      "Subiendo Sostenido",         "momentum", "+", 1, True, 120,
   "Price up >3% in last 10 minutes (sustained momentum)",
   "Precio sube >3% en los últimos 10 minutos (momentum sostenido)",
   flip="RD", keywords=["running", "sustained"],
   requires=["chg_10min"])

_a("RD",   "running_down_sustained",   "Running Down Sustained",    "Bajando Sostenido",          "momentum", "-", 1, True, 120,
   "Price down >3% in last 10 minutes (sustained momentum)",
   "Precio baja >3% en los últimos 10 minutos (momentum sostenido)",
   flip="RU", keywords=["running", "sustained"],
   requires=["chg_10min"])

_a("RUC",  "running_up_confirmed",     "Running Up (Confirmed)",    "Subiendo (Confirmado)",      "momentum", "+", 1, True, 180,
   "Price up >2% in 5 min AND >4% in 15 min (confirmed trend)",
   "Precio sube >2% en 5 min Y >4% en 15 min (tendencia confirmada)",
   flip="RDC", keywords=["running", "confirmed"],
   requires=["chg_5min", "chg_15min"])

_a("RDC",  "running_down_confirmed",   "Running Down (Confirmed)",  "Bajando (Confirmado)",       "momentum", "-", 1, True, 180,
   "Price down >2% in 5 min AND >4% in 15 min (confirmed trend)",
   "Precio baja >2% en 5 min Y >4% en 15 min (tendencia confirmada)",
   flip="RUC", keywords=["running", "confirmed"],
   requires=["chg_5min", "chg_15min"])

# --- VWAP Divergence ---
_a("VDU",  "vwap_divergence_up",       "Positive VWAP Divergence",  "Divergencia VWAP Positiva",  "vwap", "+", 2, False, 180,
   "Price making new lows but VWAP is not (bullish divergence)",
   "El precio hace nuevos mínimos pero el VWAP no (divergencia alcista)",
   flip="VDD", keywords=["vwap", "divergence"],
   requires=["vwap", "price_lows_tracking"])

_a("VDD",  "vwap_divergence_down",     "Negative VWAP Divergence",  "Divergencia VWAP Negativa",  "vwap", "-", 2, False, 180,
   "Price making new highs but VWAP is not (bearish divergence)",
   "El precio hace nuevos máximos pero el VWAP no (divergencia bajista)",
   flip="VDU", keywords=["vwap", "divergence"],
   requires=["vwap", "price_highs_tracking"])

# --- Daily Support/Resistance (active: prevDay data from REST snapshot) ---
_a("CDHR", "crossed_daily_high_resistance", "Crossed Daily High",    "Cruzó Máximo Día Anterior",    "price", "+", 1, True, 300,
   "Price crosses above previous day's high (resistance level)",
   "El precio cruza por encima del máximo del día anterior (nivel de resistencia)",
   flip="CDLS", keywords=["resistance", "daily high"],
   requires=["prev_day_high"])

_a("CDLS", "crossed_daily_low_support",     "Crossed Daily Low",     "Cruzó Mínimo Día Anterior",    "price", "-", 1, True, 300,
   "Price crosses below previous day's low (support level)",
   "El precio cruza por debajo del mínimo del día anterior (nivel de soporte)",
   flip="CDHR", keywords=["support", "daily low"],
   requires=["prev_day_low"])


# ──────────────────────────────────────────────────────────────────────
# PHASE 3 — INTRADAY BARS (needs bar builder service)
# ──────────────────────────────────────────────────────────────────────

# --- Timeframe Highs/Lows ---
for tf in [5, 10, 15, 30, 60]:
    _a(f"IDH{tf}", f"intraday_high_{tf}min",   f"{tf} Minute High",   f"Máximo {tf} Minutos",   "timeframe", "+", 3, False, tf * 2,
       f"Price makes new high for last {tf} minutes",
       f"El precio alcanza un nuevo máximo de los últimos {tf} minutos",
       flip=f"IDL{tf}", keywords=["timeframe", "high", f"{tf}min"],
       requires=[f"bar_{tf}min"])
    _a(f"IDL{tf}", f"intraday_low_{tf}min",    f"{tf} Minute Low",    f"Mínimo {tf} Minutos",   "timeframe", "-", 3, False, tf * 2,
       f"Price makes new low for last {tf} minutes",
       f"El precio alcanza un nuevo mínimo de los últimos {tf} minutos",
       flip=f"IDH{tf}", keywords=["timeframe", "low", f"{tf}min"],
       requires=[f"bar_{tf}min"])

# --- Opening Range Breakouts ---
for tf in [1, 2, 5, 10, 15, 30, 60]:
    _a(f"ORU{tf}", f"orb_up_{tf}min",    f"{tf} Min Opening Range Breakout",  f"Ruptura Rango Apertura {tf} Min",  "orb", "+", 3, False, 60,
       f"Price breaks above the first {tf} minute(s) trading range high",
       f"El precio rompe por encima del máximo del rango de los primeros {tf} minuto(s)",
       flip=f"ORD{tf}", keywords=["opening range", "breakout", f"{tf}min"],
       requires=[f"opening_range_{tf}min"])
    _a(f"ORD{tf}", f"orb_down_{tf}min",  f"{tf} Min Opening Range Breakdown", f"Quiebre Rango Apertura {tf} Min",  "orb", "-", 3, False, 60,
       f"Price breaks below the first {tf} minute(s) trading range low",
       f"El precio rompe por debajo del mínimo del rango de los primeros {tf} minuto(s)",
       flip=f"ORU{tf}", keywords=["opening range", "breakdown", f"{tf}min"],
       requires=[f"opening_range_{tf}min"])

# --- Consolidation Breakouts ---
for tf in [5, 10, 15, 30]:
    _a(f"CBO{tf}",  f"consolidation_breakout_{tf}min", f"{tf} Min Consolidation Breakout",  f"Ruptura Consolidación {tf} Min",  "consol", "+", 3, False, tf * 3,
       f"Price breaks out of {tf}-minute consolidation range (tight range then expansion)",
       f"El precio rompe el rango de consolidación de {tf} minutos",
       flip=f"CBD{tf}", keywords=["consolidation", "breakout", f"{tf}min"],
       requires=[f"bar_{tf}min"])
    _a(f"CBD{tf}",  f"consolidation_breakdown_{tf}min", f"{tf} Min Consolidation Breakdown", f"Quiebre Consolidación {tf} Min",  "consol", "-", 3, False, tf * 3,
       f"Price breaks down from {tf}-minute consolidation range",
       f"El precio quiebra el rango de consolidación de {tf} minutos",
       flip=f"CBO{tf}", keywords=["consolidation", "breakdown", f"{tf}min"],
       requires=[f"bar_{tf}min"])

# --- Channel Breakouts ---
_a("CHBO", "channel_breakout",           "Channel Breakout",            "Ruptura de Canal",           "consol", "+", 3, False, 300,
   "Price breaks above a price channel (series of higher lows)",
   "El precio rompe por encima de un canal de precios",
   flip="CHBD", keywords=["channel", "breakout"],
   requires=["bar_5min"])

_a("CHBD", "channel_breakdown",          "Channel Breakdown",           "Quiebre de Canal",           "consol", "-", 3, False, 300,
   "Price breaks below a price channel (series of lower highs)",
   "El precio quiebra por debajo de un canal de precios",
   flip="CHBO", keywords=["channel", "breakdown"],
   requires=["bar_5min"])

_a("CHBOC","channel_breakout_confirmed",  "Channel Breakout (Confirmed)","Ruptura Canal (Conf.)",      "consol", "+", 3, False, 300,
   "Channel breakout confirmed by sustained price above channel",
   "Ruptura de canal confirmada por precio sostenido sobre el canal",
   flip="CHBDC", keywords=["channel", "breakout", "confirmed"],
   requires=["bar_5min"])

_a("CHBDC","channel_breakdown_confirmed", "Channel Breakdown (Confirmed)","Quiebre Canal (Conf.)",     "consol", "-", 3, False, 300,
   "Channel breakdown confirmed by sustained price below channel",
   "Quiebre de canal confirmado por precio sostenido bajo el canal",
   flip="CHBOC", keywords=["channel", "breakdown", "confirmed"],
   requires=["bar_5min"])

# --- Support/Resistance (intraday) ---
_a("CAR",  "crossed_above_resistance",           "Crossed Above Resistance",            "Cruzó Sobre Resistencia",        "price", "+", 3, False, 180,
   "Price crosses above intraday resistance level",
   "El precio cruza por encima del nivel de resistencia intradía",
   flip="CBS", keywords=["resistance", "support", "cross"],
   requires=["bar_5min"])

_a("CBS",  "crossed_below_support",              "Crossed Below Support",               "Cruzó Bajo Soporte",             "price", "-", 3, False, 180,
   "Price crosses below intraday support level",
   "El precio cruza por debajo del nivel de soporte intradía",
   flip="CAR", keywords=["resistance", "support", "cross"],
   requires=["bar_5min"])

_a("CARC", "crossed_above_resistance_confirmed", "Crossed Above Resistance (Confirmed)","Cruzó Resistencia (Conf.)",      "price", "+", 3, False, 300,
   "Resistance cross confirmed by sustained price above level",
   "Cruce de resistencia confirmado por precio sostenido sobre el nivel",
   flip="CBSC", keywords=["resistance", "confirmed"],
   requires=["bar_5min"])

_a("CBSC", "crossed_below_support_confirmed",    "Crossed Below Support (Confirmed)",   "Cruzó Soporte (Conf.)",          "price", "-", 3, False, 300,
   "Support break confirmed by sustained price below level",
   "Quiebre de soporte confirmado por precio sostenido bajo el nivel",
   flip="CARC", keywords=["support", "confirmed"],
   requires=["bar_5min"])

# --- Consolidation ---
_a("C",    "consolidation",             "Consolidation",             "Consolidación",               "consol", "~", 3, False, 300,
   "Stock enters tight consolidation range (low volatility contraction)",
   "La acción entra en rango de consolidación estrecho",
   keywords=["consolidation", "range", "tight"],
   requires=["bar_5min"])

# --- Trailing Stops ---
_a("TSPU", "trailing_stop_pct_up",      "Trailing Stop % Up",        "Trailing Stop % Arriba",      "momentum", "+", 3, False, 120,
   "Price triggers trailing stop upward (momentum reversal up)",
   "El precio activa trailing stop alcista",
   flip="TSPD", keywords=["trailing", "stop"],
   requires=["bar_1min"])

_a("TSPD", "trailing_stop_pct_down",    "Trailing Stop % Down",      "Trailing Stop % Abajo",       "momentum", "-", 3, False, 120,
   "Price triggers trailing stop downward (momentum reversal down)",
   "El precio activa trailing stop bajista",
   flip="TSPU", keywords=["trailing", "stop"],
   requires=["bar_1min"])


# ──────────────────────────────────────────────────────────────────────
# PHASE 4 — INTRADAY INDICATORS (needs bar builder + indicator calc)
# ──────────────────────────────────────────────────────────────────────

# --- SMA Crosses (5 vs 8 at multiple timeframes) ---
for tf in [1, 2, 5, 10, 15, 30]:
    _a(f"X5A8_{tf}",  f"sma5_above_sma8_{tf}min",  f"SMA5 Crossed Above SMA8 ({tf}min)",  f"SMA5 Cruzó Sobre SMA8 ({tf}min)",  "indicator", "+", 4, False, tf * 4,
       f"5-period SMA crosses above 8-period SMA on {tf}-minute chart",
       f"SMA de 5 periodos cruza sobre SMA de 8 en gráfico de {tf} minutos",
       flip=f"X5B8_{tf}", keywords=["sma", "cross", f"{tf}min"],
       requires=[f"sma_5_{tf}min", f"sma_8_{tf}min"])
    _a(f"X5B8_{tf}",  f"sma5_below_sma8_{tf}min",  f"SMA5 Crossed Below SMA8 ({tf}min)",  f"SMA5 Cruzó Bajo SMA8 ({tf}min)",   "indicator", "-", 4, False, tf * 4,
       f"5-period SMA crosses below 8-period SMA on {tf}-minute chart",
       f"SMA de 5 periodos cruza bajo SMA de 8 en gráfico de {tf} minutos",
       flip=f"X5A8_{tf}", keywords=["sma", "cross", f"{tf}min"],
       requires=[f"sma_5_{tf}min", f"sma_8_{tf}min"])

# --- SMA 8 vs 20 (2m and 15m — 5m already defined above as active) ---
for tf in [2, 15]:
    _a(f"ECAY{tf}",  f"sma8_above_sma20_{tf}min",  f"SMA8 Crossed Above SMA20 ({tf}min)", f"SMA8 Cruzó Sobre SMA20 ({tf}min)", "indicator", "+", 4, False, tf * 4,
       f"8-period SMA crosses above 20-period SMA on {tf}-minute chart",
       f"SMA de 8 cruza sobre SMA de 20 en gráfico de {tf} minutos",
       flip=f"ECBY{tf}", keywords=["sma", "cross", f"{tf}min"],
       requires=[f"sma_8_{tf}min", f"sma_20_{tf}min"])
    _a(f"ECBY{tf}",  f"sma8_below_sma20_{tf}min",  f"SMA8 Crossed Below SMA20 ({tf}min)", f"SMA8 Cruzó Bajo SMA20 ({tf}min)",  "indicator", "-", 4, False, tf * 4,
       f"8-period SMA crosses below 20-period SMA on {tf}-minute chart",
       f"SMA de 8 cruza bajo SMA de 20 en gráfico de {tf} minutos",
       flip=f"ECAY{tf}", keywords=["sma", "cross", f"{tf}min"],
       requires=[f"sma_8_{tf}min", f"sma_20_{tf}min"])

# --- MACD (10, 15, 30, 60 min — 5m already defined above as active) ---
for tf in [10, 15, 30, 60]:
    _a(f"MDAS{tf}", f"macd_above_signal_{tf}min",  f"MACD Above Signal ({tf}min)",  f"MACD Sobre Señal ({tf}min)",  "indicator", "+", 4, False, tf * 3,
       f"MACD crosses above signal line on {tf}-minute chart",
       f"MACD cruza sobre la línea de señal en gráfico de {tf} minutos",
       flip=f"MDBS{tf}", keywords=["macd", "signal", f"{tf}min"],
       requires=[f"macd_{tf}min"])
    _a(f"MDBS{tf}", f"macd_below_signal_{tf}min",  f"MACD Below Signal ({tf}min)",  f"MACD Bajo Señal ({tf}min)",   "indicator", "-", 4, False, tf * 3,
       f"MACD crosses below signal line on {tf}-minute chart",
       f"MACD cruza bajo la línea de señal en gráfico de {tf} minutos",
       flip=f"MDAS{tf}", keywords=["macd", "signal", f"{tf}min"],
       requires=[f"macd_{tf}min"])
    _a(f"MDAZ{tf}", f"macd_above_zero_{tf}min",    f"MACD Above Zero ({tf}min)",    f"MACD Sobre Cero ({tf}min)",   "indicator", "+", 4, False, tf * 3,
       f"MACD crosses above zero line on {tf}-minute chart",
       f"MACD cruza sobre la línea cero en gráfico de {tf} minutos",
       flip=f"MDBZ{tf}", keywords=["macd", "zero", f"{tf}min"],
       requires=[f"macd_{tf}min"])
    _a(f"MDBZ{tf}", f"macd_below_zero_{tf}min",    f"MACD Below Zero ({tf}min)",    f"MACD Bajo Cero ({tf}min)",    "indicator", "-", 4, False, tf * 3,
       f"MACD crosses below zero line on {tf}-minute chart",
       f"MACD cruza bajo la línea cero en gráfico de {tf} minutos",
       flip=f"MDAZ{tf}", keywords=["macd", "zero", f"{tf}min"],
       requires=[f"macd_{tf}min"])

# --- Stochastic (15m, 60m — 5m already defined above as active) ---
for tf in [15, 60]:
    _a(f"SC20_{tf}", f"stoch_above_20_{tf}min",  f"Stochastic Crossed Above 20 ({tf}min)", f"Estocástico Cruzó 20 ({tf}min)",  "indicator", "+", 4, False, tf * 3,
       f"Stochastic %K crosses above 20 (oversold exit) on {tf}-minute chart",
       f"Estocástico %K cruza sobre 20 (salida de sobreventa) en gráfico de {tf} minutos",
       flip=f"SC80_{tf}", keywords=["stochastic", "oversold", f"{tf}min"],
       requires=[f"stoch_{tf}min"])
    _a(f"SC80_{tf}", f"stoch_below_80_{tf}min",  f"Stochastic Crossed Below 80 ({tf}min)", f"Estocástico Cruzó 80 ({tf}min)",  "indicator", "-", 4, False, tf * 3,
       f"Stochastic %K crosses below 80 (overbought exit) on {tf}-minute chart",
       f"Estocástico %K cruza bajo 80 (salida de sobrecompra) en gráfico de {tf} minutos",
       flip=f"SC20_{tf}", keywords=["stochastic", "overbought", f"{tf}min"],
       requires=[f"stoch_{tf}min"])

# --- Linear Regression ---
for tf in [5, 15, 30, 90]:
    _a(f"PEU{tf}", f"linreg_uptrend_{tf}min",   f"{tf} Min Linear Regression Up",   f"Regresión Lineal Alcista {tf}min",  "indicator", "+", 4, False, tf * 3,
       f"Linear regression slope positive on {tf}-minute chart",
       f"Pendiente de regresión lineal positiva en gráfico de {tf} minutos",
       flip=f"PED{tf}", keywords=["linear regression", "trend", f"{tf}min"],
       requires=[f"linreg_{tf}min"])
    _a(f"PED{tf}", f"linreg_downtrend_{tf}min",  f"{tf} Min Linear Regression Down", f"Regresión Lineal Bajista {tf}min",  "indicator", "-", 4, False, tf * 3,
       f"Linear regression slope negative on {tf}-minute chart",
       f"Pendiente de regresión lineal negativa en gráfico de {tf} minutos",
       flip=f"PEU{tf}", keywords=["linear regression", "trend", f"{tf}min"],
       requires=[f"linreg_{tf}min"])

# --- Thrust (SMA momentum) ---
for tf in [2, 5, 15]:
    _a(f"SMAU{tf}", f"upward_thrust_{tf}min",   f"Upward Thrust ({tf}min)",   f"Impulso Alcista ({tf}min)",  "indicator", "+", 4, False, tf * 4,
       f"Strong upward price thrust on {tf}-minute chart (rapid SMA acceleration)",
       f"Fuerte impulso alcista en gráfico de {tf} minutos",
       flip=f"SMAD{tf}", keywords=["thrust", "momentum", f"{tf}min"],
       requires=[f"sma_5_{tf}min"])
    _a(f"SMAD{tf}", f"downward_thrust_{tf}min",  f"Downward Thrust ({tf}min)", f"Impulso Bajista ({tf}min)",  "indicator", "-", 4, False, tf * 4,
       f"Strong downward price thrust on {tf}-minute chart (rapid SMA deceleration)",
       f"Fuerte impulso bajista en gráfico de {tf} minutos",
       flip=f"SMAU{tf}", keywords=["thrust", "momentum", f"{tf}min"],
       requires=[f"sma_5_{tf}min"])

# --- Fibonacci ---
for level in [38, 50, 62, 79]:
    _a(f"FU{level}", f"fib_buy_{level}",   f"Fibonacci {level}% Buy Signal",   f"Fibonacci {level}% Señal Compra",  "indicator", "+", 4, False, 180,
       f"Price bounces from {level}% Fibonacci retracement level",
       f"El precio rebota desde el nivel de retroceso Fibonacci del {level}%",
       flip=f"FD{level}", keywords=["fibonacci", "retracement", f"{level}%"],
       requires=["fib_levels"])
    _a(f"FD{level}", f"fib_sell_{level}",  f"Fibonacci {level}% Sell Signal",  f"Fibonacci {level}% Señal Venta",   "indicator", "-", 4, False, 180,
       f"Price rejected at {level}% Fibonacci retracement level",
       f"El precio es rechazado en el nivel de retroceso Fibonacci del {level}%",
       flip=f"FU{level}", keywords=["fibonacci", "retracement", f"{level}%"],
       requires=["fib_levels"])


# ──────────────────────────────────────────────────────────────────────
# PHASE 5 — CANDLESTICK PATTERNS (needs bar builder)
# ──────────────────────────────────────────────────────────────────────

# --- Doji ---
for tf in [5, 10, 15, 30, 60]:
    _a(f"DOJ{tf}", f"doji_{tf}min", f"{tf} Minute Doji", f"Doji {tf} Minutos", "candle", "~", 5, False, tf * 2,
       f"Doji candlestick pattern on {tf}-minute chart (indecision)",
       f"Patrón de vela Doji en gráfico de {tf} minutos (indecisión)",
       keywords=["doji", "candle", f"{tf}min"], requires=[f"bar_{tf}min"])

# --- Hammer ---
for tf in [2, 5, 10, 15, 30, 60]:
    _a(f"HMR{tf}", f"hammer_{tf}min", f"{tf} Minute Hammer", f"Martillo {tf} Minutos", "candle", "+", 5, False, tf * 2,
       f"Hammer candlestick pattern on {tf}-minute chart (bullish reversal)",
       f"Patrón de vela Martillo en gráfico de {tf} minutos (reversión alcista)",
       keywords=["hammer", "candle", "reversal", f"{tf}min"], requires=[f"bar_{tf}min"])

# --- Hanging Man ---
for tf in [2, 5, 10, 15, 30, 60]:
    _a(f"HGM{tf}", f"hanging_man_{tf}min", f"{tf} Minute Hanging Man", f"Hombre Colgado {tf} Min", "candle", "-", 5, False, tf * 2,
       f"Hanging man candlestick on {tf}-minute chart (bearish reversal)",
       f"Patrón Hombre Colgado en gráfico de {tf} minutos (reversión bajista)",
       flip=f"HMR{tf}", keywords=["hanging man", "candle", "reversal", f"{tf}min"], requires=[f"bar_{tf}min"])

# --- Engulfing ---
for tf in [5, 10, 15, 30]:
    _a(f"NGU{tf}", f"bullish_engulfing_{tf}min", f"{tf} Min Bullish Engulfing", f"Envolvente Alcista {tf} Min", "candle", "+", 5, False, tf * 3,
       f"Bullish engulfing pattern on {tf}-minute chart",
       f"Patrón envolvente alcista en gráfico de {tf} minutos",
       flip=f"NGD{tf}", keywords=["engulfing", "bullish", f"{tf}min"], requires=[f"bar_{tf}min"])
    _a(f"NGD{tf}", f"bearish_engulfing_{tf}min", f"{tf} Min Bearish Engulfing", f"Envolvente Bajista {tf} Min", "candle", "-", 5, False, tf * 3,
       f"Bearish engulfing pattern on {tf}-minute chart",
       f"Patrón envolvente bajista en gráfico de {tf} minutos",
       flip=f"NGU{tf}", keywords=["engulfing", "bearish", f"{tf}min"], requires=[f"bar_{tf}min"])

# --- Piercing / Dark Cloud ---
for tf in [5, 10, 15, 30]:
    _a(f"PP{tf}",  f"piercing_pattern_{tf}min", f"{tf} Min Piercing Pattern",  f"Patrón Penetrante {tf} Min",   "candle", "+", 5, False, tf * 3,
       f"Piercing pattern on {tf}-minute chart (bullish reversal)",
       f"Patrón penetrante en gráfico de {tf} minutos (reversión alcista)",
       flip=f"DCC{tf}", keywords=["piercing", "candle", f"{tf}min"], requires=[f"bar_{tf}min"])
    _a(f"DCC{tf}", f"dark_cloud_cover_{tf}min", f"{tf} Min Dark Cloud Cover",  f"Nube Oscura {tf} Min",         "candle", "-", 5, False, tf * 3,
       f"Dark cloud cover on {tf}-minute chart (bearish reversal)",
       f"Cobertura de nube oscura en gráfico de {tf} minutos (reversión bajista)",
       flip=f"PP{tf}", keywords=["dark cloud", "candle", f"{tf}min"], requires=[f"bar_{tf}min"])

# --- Bottoming/Topping Tails ---
for tf in [2, 5, 10, 15, 30, 60]:
    _a(f"BT{tf}", f"bottoming_tail_{tf}min", f"{tf} Min Bottoming Tail", f"Cola Inferior {tf} Min", "candle", "+", 5, False, tf * 2,
       f"Bottoming tail on {tf}-minute chart (long lower shadow, bullish)",
       f"Cola inferior en gráfico de {tf} minutos (sombra inferior larga, alcista)",
       flip=f"TT{tf}", keywords=["tail", "bottom", f"{tf}min"], requires=[f"bar_{tf}min"])
    _a(f"TT{tf}", f"topping_tail_{tf}min",   f"{tf} Min Topping Tail",   f"Cola Superior {tf} Min",  "candle", "-", 5, False, tf * 2,
       f"Topping tail on {tf}-minute chart (long upper shadow, bearish)",
       f"Cola superior en gráfico de {tf} minutos (sombra superior larga, bajista)",
       flip=f"BT{tf}", keywords=["tail", "top", f"{tf}min"], requires=[f"bar_{tf}min"])

# --- NR7 ---
for tf in [1, 2, 5, 10, 15, 30]:
    label = f"NR7 ({tf}min)" if tf != 15 else "NR7"
    code = f"NR7_{tf}" if tf != 15 else "NR7"
    _a(code, f"nr7_{tf}min", label, f"NR7 ({tf} Min)", "candle", "~", 5, False, tf * 3,
       f"Narrowest range of last 7 bars on {tf}-minute chart (volatility contraction)",
       f"Rango más estrecho de las últimas 7 barras en gráfico de {tf} minutos",
       keywords=["nr7", "narrow range", f"{tf}min"], requires=[f"bar_{tf}min"])

# --- Wide Range Bars ---
for tf in [2, 5, 15]:
    _a(f"WRB{tf}", f"wide_range_bar_{tf}min", f"{tf} Min Wide Range Bar", f"Barra Rango Amplio {tf} Min", "candle", "~", 5, False, tf * 3,
       f"Wide range bar on {tf}-minute chart (high volatility expansion)",
       f"Barra de rango amplio en gráfico de {tf} minutos (expansión de volatilidad)",
       keywords=["wide range", "bar", f"{tf}min"], requires=[f"bar_{tf}min"])

# --- Green/Red Bar Reversal ---
for tf in [2, 5, 15, 60]:
    _a(f"GBR{tf}", f"green_bar_reversal_{tf}min", f"{tf} Min Green Bar Reversal", f"Reversión Barra Verde {tf} Min", "candle", "+", 5, False, tf * 3,
       f"Green bar reversal on {tf}-minute chart (closes above prior bar's high)",
       f"Reversión de barra verde en gráfico de {tf} minutos",
       flip=f"RBR{tf}", keywords=["reversal", "green bar", f"{tf}min"], requires=[f"bar_{tf}min"])
    _a(f"RBR{tf}", f"red_bar_reversal_{tf}min",   f"{tf} Min Red Bar Reversal",   f"Reversión Barra Roja {tf} Min",   "candle", "-", 5, False, tf * 3,
       f"Red bar reversal on {tf}-minute chart (closes below prior bar's low)",
       f"Reversión de barra roja en gráfico de {tf} minutos",
       flip=f"GBR{tf}", keywords=["reversal", "red bar", f"{tf}min"], requires=[f"bar_{tf}min"])

# --- Narrow Range Buy/Sell Bars ---
for tf in [5, 10, 15, 30]:
    _a(f"NRBB{tf}", f"narrow_range_buy_{tf}min",  f"{tf} Min Narrow Range Buy Bar",  f"Barra Compra Rango Estrecho {tf} Min",  "candle", "+", 5, False, tf * 3,
       f"Narrow range bar followed by bullish break on {tf}-minute chart",
       f"Barra de rango estrecho seguida de ruptura alcista en gráfico de {tf} minutos",
       flip=f"NRSB{tf}", keywords=["narrow range", "buy", f"{tf}min"], requires=[f"bar_{tf}min"])
    _a(f"NRSB{tf}", f"narrow_range_sell_{tf}min",  f"{tf} Min Narrow Range Sell Bar", f"Barra Venta Rango Estrecho {tf} Min",  "candle", "-", 5, False, tf * 3,
       f"Narrow range bar followed by bearish break on {tf}-minute chart",
       f"Barra de rango estrecho seguida de quiebre bajista en gráfico de {tf} minutos",
       flip=f"NRBB{tf}", keywords=["narrow range", "sell", f"{tf}min"], requires=[f"bar_{tf}min"])

# --- 1-2-3 Continuation ---
for tf in [2, 5, 15, 60]:
    _a(f"C1U_{tf}",  f"continuation_buy_{tf}min",        f"{tf} Min 1-2-3 Buy Signal",   f"Señal Compra 1-2-3 {tf} Min",   "candle", "+", 5, False, tf * 4,
       f"1-2-3 continuation buy signal on {tf}-minute chart",
       f"Señal de compra continuación 1-2-3 en gráfico de {tf} minutos",
       flip=f"C1D_{tf}", keywords=["123", "continuation", f"{tf}min"], requires=[f"bar_{tf}min"])
    _a(f"C1D_{tf}",  f"continuation_sell_{tf}min",        f"{tf} Min 1-2-3 Sell Signal",  f"Señal Venta 1-2-3 {tf} Min",    "candle", "-", 5, False, tf * 4,
       f"1-2-3 continuation sell signal on {tf}-minute chart",
       f"Señal de venta continuación 1-2-3 en gráfico de {tf} minutos",
       flip=f"C1U_{tf}", keywords=["123", "continuation", f"{tf}min"], requires=[f"bar_{tf}min"])

# --- Opening Power Bar ---
_a("OVO5U", "bullish_opening_power_bar", "Bullish Opening Power Bar", "Power Bar Apertura Alcista", "candle", "+", 5, False, 300,
   "First 5 minutes form strong bullish bar (body > 60% of range, close near high)",
   "Los primeros 5 minutos forman una barra alcista fuerte",
   flip="OVO5D", keywords=["opening", "power bar", "bullish"], requires=["bar_5min"])

_a("OVO5D", "bearish_opening_power_bar", "Bearish Opening Power Bar", "Power Bar Apertura Bajista", "candle", "-", 5, False, 300,
   "First 5 minutes form strong bearish bar (body > 60% of range, close near low)",
   "Los primeros 5 minutos forman una barra bajista fuerte",
   flip="OVO5U", keywords=["opening", "power bar", "bearish"], requires=["bar_5min"])


# ──────────────────────────────────────────────────────────────────────
# PHASE 6 — ADVANCED (chart patterns, sector correlation)
# ──────────────────────────────────────────────────────────────────────

# --- Chart Patterns ---
_a("GDBOT", "double_bottom",       "Double Bottom",           "Doble Suelo",              "pattern", "+", 6, False, 600,
   "Double bottom chart pattern detected (W formation)",
   "Patrón de doble suelo detectado (formación W)",
   flip="GDTOP", keywords=["pattern", "double bottom"], requires=["pattern_engine"])

_a("GDTOP", "double_top",          "Double Top",              "Doble Techo",              "pattern", "-", 6, False, 600,
   "Double top chart pattern detected (M formation)",
   "Patrón de doble techo detectado (formación M)",
   flip="GDBOT", keywords=["pattern", "double top"], requires=["pattern_engine"])

_a("GHASI", "inv_head_shoulders",  "Inverted Head & Shoulders","HCH Invertido",           "pattern", "+", 6, False, 600,
   "Inverted head and shoulders pattern (bullish reversal)",
   "Patrón de hombro-cabeza-hombro invertido (reversión alcista)",
   flip="GHAS", keywords=["pattern", "head shoulders"], requires=["pattern_engine"])

_a("GHAS",  "head_shoulders",      "Head & Shoulders",        "Hombro-Cabeza-Hombro",    "pattern", "-", 6, False, 600,
   "Head and shoulders pattern (bearish reversal)",
   "Patrón de hombro-cabeza-hombro (reversión bajista)",
   flip="GHASI", keywords=["pattern", "head shoulders"], requires=["pattern_engine"])

_a("GTBOT", "triangle_bottom",     "Triangle Bottom",         "Triángulo Inferior",       "pattern", "+", 6, False, 600,
   "Ascending triangle pattern (bullish breakout potential)",
   "Patrón de triángulo ascendente (potencial ruptura alcista)",
   flip="GTTOP", keywords=["pattern", "triangle"], requires=["pattern_engine"])

_a("GTTOP", "triangle_top",        "Triangle Top",            "Triángulo Superior",       "pattern", "-", 6, False, 600,
   "Descending triangle pattern (bearish breakdown potential)",
   "Patrón de triángulo descendente (potencial quiebre bajista)",
   flip="GTBOT", keywords=["pattern", "triangle"], requires=["pattern_engine"])

_a("GRBOT", "rectangle_bottom",    "Rectangle Bottom",        "Rectángulo Inferior",      "pattern", "+", 6, False, 600,
   "Rectangle bottom pattern (bullish breakout from range)",
   "Patrón de rectángulo inferior (ruptura alcista desde rango)",
   flip="GRTOP", keywords=["pattern", "rectangle"], requires=["pattern_engine"])

_a("GRTOP", "rectangle_top",       "Rectangle Top",           "Rectángulo Superior",      "pattern", "-", 6, False, 600,
   "Rectangle top pattern (bearish breakdown from range)",
   "Patrón de rectángulo superior (quiebre bajista desde rango)",
   flip="GRBOT", keywords=["pattern", "rectangle"], requires=["pattern_engine"])

_a("GBBOT", "broadening_bottom",   "Broadening Bottom",       "Ampliación Inferior",      "pattern", "+", 6, False, 600,
   "Broadening bottom pattern (expanding volatility, bullish)",
   "Patrón de ampliación inferior (volatilidad en expansión, alcista)",
   flip="GBTOP", keywords=["pattern", "broadening"], requires=["pattern_engine"])

_a("GBTOP", "broadening_top",      "Broadening Top",          "Ampliación Superior",      "pattern", "-", 6, False, 600,
   "Broadening top pattern (expanding volatility, bearish)",
   "Patrón de ampliación superior (volatilidad en expansión, bajista)",
   flip="GBBOT", keywords=["pattern", "broadening"], requires=["pattern_engine"])


# ──────────────────────────────────────────────────────────────────────
# Cleanup helper
# ──────────────────────────────────────────────────────────────────────
del _a


# ============================================================================
# Build lookup dictionaries
# ============================================================================

ALERT_CATALOG: Dict[str, AlertDefinition] = {a.code: a for a in _alerts}

# Secondary indexes
_BY_EVENT_TYPE: Dict[str, AlertDefinition] = {a.event_type: a for a in _alerts}
_BY_CATEGORY: Dict[str, List[AlertDefinition]] = {}
for a in _alerts:
    _BY_CATEGORY.setdefault(a.category, []).append(a)


# ============================================================================
# Query functions
# ============================================================================

def get_alert_by_code(code: str) -> Optional[AlertDefinition]:
    """Get alert definition by its short code (e.g., 'NHP')."""
    return ALERT_CATALOG.get(code)


def get_alert_by_event_type(event_type: str) -> Optional[AlertDefinition]:
    """Get alert definition by event_type value (e.g., 'new_high')."""
    return _BY_EVENT_TYPE.get(event_type)


def get_alerts_by_category(category_id: str) -> List[AlertDefinition]:
    """Get all alerts in a category."""
    return _BY_CATEGORY.get(category_id, [])


def get_alerts_by_phase(phase: int) -> List[AlertDefinition]:
    """Get all alerts in a specific implementation phase."""
    return [a for a in _alerts if a.phase == phase]


def get_active_alerts() -> List[AlertDefinition]:
    """Get all currently active (implemented) alerts."""
    return [a for a in _alerts if a.active]


def get_catalog_stats() -> Dict[str, Any]:
    """Get summary statistics of the alert catalog."""
    total = len(_alerts)
    by_phase = {}
    by_category = {}
    active = sum(1 for a in _alerts if a.active)
    
    for a in _alerts:
        by_phase[a.phase] = by_phase.get(a.phase, 0) + 1
        by_category[a.category] = by_category.get(a.category, 0) + 1
    
    return {
        "total_alerts": total,
        "active_alerts": active,
        "by_phase": dict(sorted(by_phase.items())),
        "by_category": dict(sorted(by_category.items(), key=lambda x: -x[1])),
        "categories": len(CATEGORY_CATALOG),
    }
