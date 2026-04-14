"""
Alert Catalog for alert_engine — Complete registry with custom_setting metadata.

Every AlertDefinition now includes:
  - custom_setting_type: What the quality number means (CustomSettingType enum)
  - custom_setting_label: Human-readable label for the filter input
  - custom_setting_hint: Placeholder/hint text for the filter input
  - custom_setting_default: Default value (None = show all)
  - custom_setting_unit: Display unit (days, x, shares, $, %, σ, sec, ¢)

This is the single source of truth for the frontend scan builder.
"""

from dataclasses import dataclass, field
from typing import Optional, List, Dict, Any

from models.alert_types import AlertType, CustomSettingType


@dataclass(frozen=True)
class AlertCategory:
    id: str
    name: str
    name_es: str
    icon: str
    description: str
    description_es: str
    order: int


@dataclass(frozen=True)
class AlertDefinition:
    code: str
    alert_type: AlertType
    name: str
    name_es: str
    category: str
    direction: str
    phase: int
    active: bool
    cooldown: int
    description: str
    description_es: str
    flip_code: Optional[str] = None
    parent_code: Optional[str] = None
    keywords: List[str] = field(default_factory=list)
    custom_setting_type: CustomSettingType = CustomSettingType.NONE
    custom_setting_label: Optional[str] = None
    custom_setting_label_es: Optional[str] = None
    custom_setting_hint: Optional[str] = None
    custom_setting_default: Optional[float] = None
    custom_setting_unit: Optional[str] = None
    quality_description: Optional[str] = None
    quality_description_es: Optional[str] = None
    requires: List[str] = field(default_factory=list)


# ============================================================================
# Categories
# ============================================================================

CATEGORY_CATALOG: Dict[str, AlertCategory] = {}

def _cat(id, name, name_es, icon, desc, desc_es, order):
    CATEGORY_CATALOG[id] = AlertCategory(id, name, name_es, icon, desc, desc_es, order)

_cat("price",     "Price",              "Precio",              "TrendingUp",    "Price highs, lows, and level crosses",         "Máximos, mínimos y cruces de niveles",        1)
_cat("vwap",      "VWAP",               "VWAP",                "Activity",      "VWAP crosses and divergence",                  "Cruces y divergencia del VWAP",               2)
_cat("volume",    "Volume",             "Volumen",             "BarChart3",     "Volume spikes, relative volume, block trades",  "Picos de volumen, RVOL, block trades",       3)
_cat("momentum",  "Momentum",           "Momentum",            "Zap",           "Running up/down, % change thresholds",         "Subiendo/bajando, umbrales de % cambio",      4)
_cat("pullback",  "Pullbacks",          "Retrocesos",          "ArrowDownUp",   "Retracements from highs/lows",                 "Retrocesos desde máximos/mínimos",            5)
_cat("gap",       "Gap",                "Gap",                 "ArrowLeftRight","Gap reversals and retracements",               "Reversiones y retrocesos de gap",             6)
_cat("ma_cross",  "Moving Averages",    "Medias Móviles",      "LineChart",     "SMA/EMA crosses on daily and intraday",        "Cruces de SMA/EMA en diario e intradía",      7)
_cat("bollinger", "Bollinger Bands",    "Bandas Bollinger",    "Maximize2",     "Standard deviation breakouts/breakdowns",      "Rupturas por desviación estándar",            8)
_cat("orb",       "Opening Range",      "Rango Apertura",      "Clock",         "Opening range breakouts at multiple timeframes","Rupturas del rango de apertura",              9)
_cat("consol",    "Consolidation",      "Consolidación",       "Square",        "Consolidation breakouts/breakdowns",           "Rupturas de consolidación",                   10)
_cat("bidask",    "Bid/Ask",            "Bid/Ask",             "ArrowUpDown",   "Market crossed, locked, large sizes, spread",  "Mercado cruzado, bloqueado, tamaños grandes", 11)
_cat("halt",      "Halts & Resumes",    "Halts y Reanudaciones","AlertTriangle","Trading halts and resumes",                    "Paradas y reanudaciones de trading",          12)
_cat("session",   "Pre/Post Market",    "Pre/Post Mercado",    "Sun",           "Extended hours highs and lows",                "Máximos y mínimos en horario extendido",      13)
_cat("indicator",  "Technical Indicators","Indicadores Técnicos","Settings2",   "MACD, Stochastic, RSI signals",                "Señales de MACD, Estocástico, RSI",           14)
_cat("geometric",  "Geometric Patterns", "Patrones Geométricos","Triangle",    "Broadening, wedge, and triangle patterns",     "Patrones de ensanchamiento, cuña y triángulo", 15)
_cat("candle",     "Candlestick",        "Velas",               "CandlestickChart","N-minute candlestick new highs and lows",   "Máximos y mínimos en velas de N minutos",     16)
_cat("trailing",   "Trailing Stops",     "Trailing Stops",      "Target",          "Percentage and volatility trailing stops",  "Trailing stops por porcentaje y volatilidad",  17)
_cat("fibonacci",  "Fibonacci",          "Fibonacci",           "GitBranch",       "Fibonacci retracement buy and sell signals", "Senales compra/venta retroceso Fibonacci",     18)
_cat("linreg",     "Linear Regression",  "Regresion Lineal",    "TrendingUp",      "Linear regression channel trend signals",   "Senales de tendencia por canal de regresion",  19)
_cat("thrust",     "SMA Thrust",         "Empuje SMA",          "Zap",             "SMA 8/20 sustained directional thrust",    "Empuje direccional sostenido de SMA 8/20",     20)
_cat("candle_pattern", "Candle Patterns",  "Patrones de Velas",   "CandlestickChart","Doji, Hammer, Engulfing, Piercing patterns","Patrones Doji, Martillo, Envolvente, Piercing", 21)

del _cat


# ============================================================================
# Alert Definitions
# ============================================================================

_alerts: List[AlertDefinition] = []

def _a(code, alert_type, name, name_es, cat, direction, phase, active, cooldown,
       desc, desc_es, flip=None, parent=None, keywords=None,
       cs_type=CustomSettingType.NONE, cs_label=None, cs_label_es=None,
       cs_hint=None, cs_default=None, cs_unit=None,
       q_desc=None, q_desc_es=None, requires=None):
    _alerts.append(AlertDefinition(
        code=code, alert_type=alert_type, name=name, name_es=name_es,
        category=cat, direction=direction, phase=phase, active=active,
        cooldown=cooldown, description=desc, description_es=desc_es,
        flip_code=flip, parent_code=parent, keywords=keywords or [],
        custom_setting_type=cs_type,
        custom_setting_label=cs_label, custom_setting_label_es=cs_label_es,
        custom_setting_hint=cs_hint, custom_setting_default=cs_default,
        custom_setting_unit=cs_unit,
        quality_description=q_desc, quality_description_es=q_desc_es,
        requires=requires or [],
    ))


# ──────────────────────────────────────────────────────────────────────
# PRICE — Highs & Lows (quality = lookback_days)
# ──────────────────────────────────────────────────────────────────────

_a("NHP", AlertType.NEW_HIGH,
   "New High", "Nuevo Máximo", "price", "+", 1, True, 30,
   "Price reaches new intraday high; only during regular market hours",
   "El precio alcanza un nuevo máximo intradía; solo en horario regular",
   flip="NLP", keywords=["highs", "lows", "single print"],
   cs_type=CustomSettingType.LOOKBACK_DAYS,
   cs_label="Min lookback days", cs_label_es="Mín días lookback",
   cs_hint="0=any new high, 1=above yesterday, 7=weekly, 365=52-week. Range 0-366",
   cs_default=0, cs_unit="days",
   q_desc="Lookback period: number of trading days this is a new high for",
   q_desc_es="Período lookback: días de trading para los que este es un nuevo máximo")

_a("NLP", AlertType.NEW_LOW,
   "New Low", "Nuevo Mínimo", "price", "-", 1, True, 30,
   "Price reaches new intraday low; only during regular market hours",
   "El precio alcanza un nuevo mínimo intradía; solo en horario regular",
   flip="NHP", parent="NHP", keywords=["highs", "lows", "single print"],
   cs_type=CustomSettingType.LOOKBACK_DAYS,
   cs_label="Min lookback days", cs_label_es="Mín días lookback",
   cs_hint="0=any new low, 1=below yesterday, 7=weekly, 365=52-week. Range 0-366",
   cs_default=0, cs_unit="days",
   q_desc="Lookback period: number of trading days this is a new low for",
   q_desc_es="Período lookback: días de trading para los que este es un nuevo mínimo")

_a("NHA", AlertType.NEW_HIGH_ASK,
   "New High Ask", "Nuevo Máximo Ask", "price", "+", 1, True, 30,
   "Ask price reaches new intraday high; blackout 30s pre / 60s post open",
   "El precio ask alcanza un nuevo máximo intradía; blackout 30s pre / 60s post apertura",
   flip="NLB", keywords=["bid and ask"],
   cs_type=CustomSettingType.MIN_SHARES,
   cs_label="Min shares on ask", cs_label_es="Mín acciones en ask",
   cs_hint="Minimum shares showing on ask at alert time. Blank = no filter",
   cs_default=None, cs_unit="shares",
   q_desc="Lookback period: trading days this is a new ask high for",
   q_desc_es="Período lookback: días de trading para los que este es un nuevo máximo del ask")

_a("NLB", AlertType.NEW_LOW_BID,
   "New Low Bid", "Nuevo Mínimo Bid", "price", "-", 1, True, 30,
   "Bid price reaches new intraday low; blackout 30s pre / 60s post open",
   "El precio bid alcanza un nuevo mínimo intradía; blackout 30s pre / 60s post apertura",
   flip="NHA", keywords=["bid and ask"],
   cs_type=CustomSettingType.MIN_SHARES,
   cs_label="Min shares on bid", cs_label_es="Mín acciones en bid",
   cs_hint="Minimum shares showing on bid at alert time. Blank = no filter",
   cs_default=None, cs_unit="shares",
   q_desc="Lookback period: trading days this is a new bid low for",
   q_desc_es="Período lookback: días de trading para los que este es un nuevo mínimo del bid")

_a("NHPF", AlertType.NEW_HIGH_FILTERED,
   "New High (filtered)", "Nuevo Máximo (filtrado)", "price", "+", 1, True, 60,
   "Subset of New High: rate-limited by volatility. One per minute unless move exceeds expected volatility",
   "Subconjunto de New High: limitado por volatilidad. Uno por minuto salvo que el movimiento supere la volatilidad esperada",
   flip="NLPF", keywords=["highs and lows", "single print"],
   cs_type=CustomSettingType.LOOKBACK_DAYS,
   cs_label="Min lookback days", cs_label_es="Mín días lookback",
   cs_hint="0=any new high, 1=above yesterday, 7=weekly, 365=52-week. Range 0-366",
   cs_default=0, cs_unit="days",
   q_desc="Lookback period: number of trading days this is a new high for",
   q_desc_es="Período lookback: días de trading para los que este es un nuevo máximo")

_a("NLPF", AlertType.NEW_LOW_FILTERED,
   "New Low (filtered)", "Nuevo Mínimo (filtrado)", "price", "-", 1, True, 60,
   "Subset of New Low: rate-limited by volatility. One per minute unless move exceeds expected volatility",
   "Subconjunto de New Low: limitado por volatilidad. Uno por minuto salvo que el movimiento supere la volatilidad esperada",
   flip="NHPF", parent="NHPF", keywords=["highs and lows", "single print"],
   cs_type=CustomSettingType.LOOKBACK_DAYS,
   cs_label="Min lookback days", cs_label_es="Mín días lookback",
   cs_hint="0=any new low, 1=below yesterday, 7=weekly, 365=52-week. Range 0-366",
   cs_default=0, cs_unit="days",
   q_desc="Lookback period: number of trading days this is a new low for",
   q_desc_es="Período lookback: días de trading para los que este es un nuevo mínimo")

_a("NHAF", AlertType.NEW_HIGH_ASK_FILTERED,
   "New High Ask (filtered)", "Nuevo Máximo Ask (filtrado)", "price", "+", 1, True, 60,
   "Subset of New High Ask: rate-limited by volatility; blackout 30s pre / 60s post open",
   "Subconjunto de New High Ask: limitado por volatilidad; blackout 30s pre / 60s post apertura",
   flip="NLBF", keywords=["bid and ask"],
   cs_type=CustomSettingType.MIN_SHARES,
   cs_label="Min shares on ask", cs_label_es="Mín acciones en ask",
   cs_hint="Minimum shares showing on ask at alert time. Blank = no filter",
   cs_default=None, cs_unit="shares",
   q_desc="Lookback period: trading days this is a new ask high for",
   q_desc_es="Período lookback: días de trading para los que este es un nuevo máximo del ask")

_a("NLBF", AlertType.NEW_LOW_BID_FILTERED,
   "New Low Bid (filtered)", "Nuevo Mínimo Bid (filtrado)", "price", "-", 1, True, 60,
   "Subset of New Low Bid: rate-limited by volatility; blackout 30s pre / 60s post open",
   "Subconjunto de New Low Bid: limitado por volatilidad; blackout 30s pre / 60s post apertura",
   flip="NHAF", keywords=["bid and ask"],
   cs_type=CustomSettingType.MIN_SHARES,
   cs_label="Min shares on bid", cs_label_es="Mín acciones en bid",
   cs_hint="Minimum shares showing on bid at alert time. Blank = no filter",
   cs_default=None, cs_unit="shares",
   q_desc="Lookback period: trading days this is a new bid low for",
   q_desc_es="Período lookback: días de trading para los que este es un nuevo mínimo del bid")

# ── Bid highs / Ask lows (NHB, NLA + filtered NHBF, NLAF) ──

_a("NHB", AlertType.NEW_HIGH_BID,
   "New High Bid", "Nuevo Máximo Bid", "price", "+", 1, True, 30,
   "Bid price reaches new intraday high; blackout 30s pre / 60s post open",
   "El precio bid alcanza un nuevo máximo intradía; blackout 30s pre / 60s post apertura",
   flip="NLA", keywords=["bid and ask"],
   cs_type=CustomSettingType.MIN_SHARES,
   cs_label="Min shares on bid", cs_label_es="Mín acciones en bid",
   cs_hint="Minimum shares showing on bid at alert time. Blank = no filter",
   cs_default=None, cs_unit="shares",
   q_desc="Shares on bid at alert time",
   q_desc_es="Acciones en bid al momento de la alerta")

_a("NLA", AlertType.NEW_LOW_ASK,
   "New Low Ask", "Nuevo Mínimo Ask", "price", "-", 1, True, 30,
   "Ask price reaches new intraday low; blackout 30s pre / 60s post open",
   "El precio ask alcanza un nuevo mínimo intradía; blackout 30s pre / 60s post apertura",
   flip="NHB", keywords=["bid and ask"],
   cs_type=CustomSettingType.MIN_SHARES,
   cs_label="Min shares on ask", cs_label_es="Mín acciones en ask",
   cs_hint="Minimum shares showing on ask at alert time. Blank = no filter",
   cs_default=None, cs_unit="shares",
   q_desc="Lookback period: trading days this is a new ask low for",
   q_desc_es="Período lookback: días de trading para los que este es un nuevo mínimo del ask")

_a("NHBF", AlertType.NEW_HIGH_BID_FILTERED,
   "New High Bid (filtered)", "Nuevo Máximo Bid (filtrado)", "price", "+", 1, True, 60,
   "Subset of New High Bid: rate-limited by volatility; blackout 30s pre / 60s post open",
   "Subconjunto de New High Bid: limitado por volatilidad; blackout 30s pre / 60s post apertura",
   flip="NLAF", keywords=["bid and ask"],
   cs_type=CustomSettingType.MIN_SHARES,
   cs_label="Min shares on bid", cs_label_es="Mín acciones en bid",
   cs_hint="Minimum shares showing on bid at alert time. Blank = no filter",
   cs_default=None, cs_unit="shares",
   q_desc="Shares on bid at alert time",
   q_desc_es="Acciones en bid al momento de la alerta")

_a("NLAF", AlertType.NEW_LOW_ASK_FILTERED,
   "New Low Ask (filtered)", "Nuevo Mínimo Ask (filtrado)", "price", "-", 1, True, 60,
   "Subset of New Low Ask: rate-limited by volatility; blackout 30s pre / 60s post open",
   "Subconjunto de New Low Ask: limitado por volatilidad; blackout 30s pre / 60s post apertura",
   flip="NHBF", parent="NHBF", keywords=["bid and ask"],
   cs_type=CustomSettingType.MIN_SHARES,
   cs_label="Min shares on ask", cs_label_es="Mín acciones en ask",
   cs_hint="Minimum shares showing on ask at alert time. Blank = no filter",
   cs_default=None, cs_unit="shares",
   q_desc="Lookback period: trading days this is a new ask low for",
   q_desc_es="Período lookback: días de trading para los que este es un nuevo mínimo del ask")

# ── Session highs/lows (pre-market only, not part of normal highs/lows) ──

_a("HPRE", AlertType.PRE_MARKET_HIGH,
   "Pre-market Highs", "Máximos Pre-Market", "session", "+", 1, True, 30,
   "Pre-market high: only includes pre-market prints, not part of normal highs",
   "Máximo pre-market: solo incluye prints pre-market, no parte de los máximos normales",
   flip="LPRE", keywords=["highs and lows", "single print"],
   cs_type=CustomSettingType.LOOKBACK_DAYS,
   cs_label="Min lookback days", cs_label_es="Mín días lookback",
   cs_hint="0=any pre-market high, 1=above yesterday, 7=weekly, 365=52-week. Range 0-366",
   cs_default=0, cs_unit="days",
   q_desc="Lookback period: trading days this is a new pre-market high for",
   q_desc_es="Período lookback: días de trading para los que este es un nuevo máximo pre-market")

_a("LPRE", AlertType.PRE_MARKET_LOW,
   "Pre-market Lows", "Mínimos Pre-Market", "session", "-", 1, True, 30,
   "Pre-market low: only includes pre-market prints, not part of normal lows",
   "Mínimo pre-market: solo incluye prints pre-market, no parte de los mínimos normales",
   flip="HPRE", parent="HPRE", keywords=["highs and lows", "single print"],
   cs_type=CustomSettingType.LOOKBACK_DAYS,
   cs_label="Min lookback days", cs_label_es="Mín días lookback",
   cs_hint="0=any pre-market low, 1=below yesterday, 7=weekly, 365=52-week. Range 0-366",
   cs_default=0, cs_unit="days",
   q_desc="Lookback period: trading days this is a new pre-market low for",
   q_desc_es="Período lookback: días de trading para los que este es un nuevo mínimo pre-market")

_a("HPOST", AlertType.POST_MARKET_HIGH,
   "Post-market Highs", "Máximos Post-Market", "session", "+", 1, True, 30,
   "Post-market high: only post-market prints. Lookback counts from today's close (1=above today's high)",
   "Máximo post-market: solo prints post-market. Lookback cuenta desde el cierre de hoy (1=sobre el máximo de hoy)",
   flip="LPOST", keywords=["highs and lows", "single print"],
   cs_type=CustomSettingType.LOOKBACK_DAYS,
   cs_label="Min lookback days", cs_label_es="Mín días lookback",
   cs_hint="0=any post-market high, 1=above today's high, 7=weekly, 365=52-week. Range 0-366",
   cs_default=0, cs_unit="days",
   q_desc="Lookback period: trading days this is a new post-market high for",
   q_desc_es="Período lookback: días de trading para los que este es un nuevo máximo post-market")

_a("LPOST", AlertType.POST_MARKET_LOW,
   "Post-market Lows", "Mínimos Post-Market", "session", "-", 1, True, 30,
   "Post-market low: only post-market prints. Lookback counts from today's close (1=below today's low)",
   "Mínimo post-market: solo prints post-market. Lookback cuenta desde el cierre de hoy (1=bajo el mínimo de hoy)",
   flip="HPOST", parent="HPOST", keywords=["highs and lows", "single print"],
   cs_type=CustomSettingType.LOOKBACK_DAYS,
   cs_label="Min lookback days", cs_label_es="Mín días lookback",
   cs_hint="0=any post-market low, 1=below today's low, 7=weekly, 365=52-week. Range 0-366",
   cs_default=0, cs_unit="days",
   q_desc="Lookback period: trading days this is a new post-market low for",
   q_desc_es="Período lookback: días de trading para los que este es un nuevo mínimo post-market")

# ── Daily resistance/support ──

_a("CDHR", AlertType.CROSSED_DAILY_HIGH_RESISTANCE,
   "Crossed daily highs resistance", "Cruzó resistencia de máximos diarios",
   "price", "+", 1, True, 0,
   "Price crosses above a previous day's high for the first time since that day. "
   "Only fires when the lookback level changes (subset of NHP).",
   "El precio cruza por encima del máximo de un día anterior por primera vez. "
   "Solo se dispara cuando cambia el nivel de lookback (subconjunto de NHP).",
   flip="CDLS", keywords=["highs and lows", "single print"],
   cs_type=CustomSettingType.LOOKBACK_DAYS,
   cs_label="Min lookback days", cs_label_es="Mín días lookback",
   cs_hint="0=any, 1=above yesterday's high, 7=weekly, 365=52-week. Range 0-366.",
   cs_default=0, cs_unit="days",
   q_desc="Days of resistance broken",
   q_desc_es="Días de resistencia rotos")

_a("CDLS", AlertType.CROSSED_DAILY_LOW_SUPPORT,
   "Crossed daily lows support", "Cruzó soporte de mínimos diarios",
   "price", "-", 1, True, 0,
   "Price crosses below a previous day's low for the first time since that day. "
   "Only fires when the lookback level changes (subset of NLP).",
   "El precio cruza por debajo del mínimo de un día anterior por primera vez. "
   "Solo se dispara cuando cambia el nivel de lookback (subconjunto de NLP).",
   flip="CDHR", parent="CDHR", keywords=["highs and lows", "single print"],
   cs_type=CustomSettingType.LOOKBACK_DAYS,
   cs_label="Min lookback days", cs_label_es="Mín días lookback",
   cs_hint="0=any, 1=below yesterday's low, 7=weekly, 365=52-week. Range 0-366.",
   cs_default=0, cs_unit="days",
   q_desc="Days of support broken",
   q_desc_es="Días de soporte rotos")


# ──────────────────────────────────────────────────────────────────────
# VOLUME (quality = volume_ratio or min_shares)
# ──────────────────────────────────────────────────────────────────────

_a("HRV", AlertType.HIGH_RELATIVE_VOLUME,
   "High relative volume", "Alto volumen relativo", "volume", "", 1, True, 0,
   "Stock trading on higher volume than normal for this time of day. "
   "Min 50% above historical avg (1.5x). 3x+ = very high relative volume. "
   "Based on 5-min interval comparison with recent historical data.",
   "La accion opera con volumen mayor al normal para esta hora del dia. "
   "Minimo 50% sobre promedio historico (1.5x). 3x+ = volumen relativo muy alto. "
   "Basado en comparacion de intervalos de 5 min con datos historicos recientes.",
   keywords=["volume confirmed"],
   cs_type=CustomSettingType.VOLUME_RATIO,
   cs_label="Min RVOL ratio", cs_label_es="Min ratio RVOL",
   cs_hint="1.5 = default (50% above normal). 3.0 = 3x normal volume.",
   cs_default=None, cs_unit="x",
   q_desc="Times more than average volume for this 5-min interval",
   q_desc_es="Veces mas que el volumen promedio para este intervalo de 5 min")

_a("SV", AlertType.STRONG_VOLUME,
   "Strong volume", "Volumen fuerte", "volume", "", 1, True, 0,
   "Total volume today vs average daily volume. Fires at each integer multiple "
   "(1x, 2x, 3x...). First alert when volume reaches daily average.",
   "Volumen total del dia vs promedio diario. Dispara en cada multiplo entero "
   "(1x, 2x, 3x...). Primera alerta cuando el volumen alcanza el promedio diario.",
   keywords=[],
   cs_type=CustomSettingType.VOLUME_RATIO,
   cs_label="Min volume multiple", cs_label_es="Min multiplo volumen",
   cs_hint="1 = default (alert at 1x avg daily). 3 = only at 3x+ avg daily.",
   cs_default=None, cs_unit="x",
   q_desc="Multiple of average daily volume",
   q_desc_es="Multiplo del volumen diario promedio")

_a("VS1", AlertType.VOLUME_SPIKE_1MIN,
   "1 minute volume spike", "Pico volumen 1 min", "volume", "", 1, True, 0,
   "Unusual volume in a 1-minute candle compared to historical baseline. "
   "Best for medium-high volume stocks. Baseline varies by stock and time of day.",
   "Volumen inusual en una vela de 1 minuto comparado con baseline historico. "
   "Mejor para acciones de volumen medio-alto. Baseline varia por accion y hora.",
   keywords=["fixed time frame"],
   cs_type=CustomSettingType.VOLUME_RATIO,
   cs_label="Min spike ratio", cs_label_es="Min ratio pico",
   cs_hint="Ratio of 1-min volume to historical average. Leave blank for defaults.",
   cs_default=None, cs_unit="x",
   q_desc="1-minute volume percentage divided by 100 (ratio to historical avg)",
   q_desc_es="Porcentaje de volumen de 1 minuto dividido por 100 (ratio vs promedio historico)")

_a("UNOP", AlertType.UNUSUAL_PRINTS,
   "Unusual number of prints", "Prints inusuales", "volume", "", 1, True, 0,
   "Stock printing tape much faster than normal for this time of day. "
   "Min 5x normal rate. Focused on 3 min or less timeframes.",
   "Accion imprimiendo mucho mas rapido de lo normal para esta hora del dia. "
   "Minimo 5x la tasa normal. Enfocado en ventanas de 3 min o menos.",
   keywords=[],
   cs_type=CustomSettingType.VOLUME_RATIO,
   cs_label="Min print ratio", cs_label_es="Min ratio prints",
   cs_hint="Multiple of normal print rate. Quality in increments of 5. "
   "Leave blank for default (5x minimum).",
   cs_default=None, cs_unit="x",
   q_desc="Multiple of normal print rate (increments of 5)",
   q_desc_es="Multiplo de la tasa normal de prints (incrementos de 5)")

_a("BP", AlertType.BLOCK_TRADE,
   "Block trade", "Block trade", "volume", "", 1, True, 0,
   "Single trade of 20,000+ shares (high vol stocks) or 5,000+ (low vol). "
   "Shows institutional trading. Description includes bid/ask context and exchange.",
   "Trade individual de 20,000+ acciones (alto vol) o 5,000+ (bajo vol). "
   "Indica trading institucional. Descripcion incluye contexto bid/ask y exchange.",
   keywords=["single print"],
   cs_type=CustomSettingType.MIN_SHARES,
   cs_label="Min shares", cs_label_es="Min acciones",
   cs_hint="20000 = default for high vol. 5000 = default for low vol. "
   "Enter larger value to see only bigger blocks (e.g. 50000).",
   cs_default=None, cs_unit="shares",
   q_desc="Number of shares in the block trade",
   q_desc_es="Numero de acciones en el block trade")


# ──────────────────────────────────────────────────────────────────────
# MOMENTUM (quality = min_dollars or quality_ratio or min_percent)
# ──────────────────────────────────────────────────────────────────────

_a("RUN", AlertType.RUNNING_UP_NOW,
   "Running up now", "Subiendo ahora", "momentum", "+", 1, True, 0,
   "Stock price trading up much faster than expected. Shortest timeframe (~1 min chart). "
   "No confirmation, can fire on a single print. Detects trends quickly.",
   "Precio subiendo mucho mas rapido de lo esperado. Timeframe mas corto (~1 min). "
   "Sin confirmacion, puede disparar con un solo print. Detecta tendencias rapido.",
   flip="RDN", keywords=["price vs time", "single print"],
   cs_type=CustomSettingType.MIN_CENTS,
   cs_label="Min move $", cs_label_es="Min movimiento $",
   cs_hint="Size of the move in dollars. 0.60 = at least 60 cents in last minute.",
   cs_default=None, cs_unit="$",
   q_desc="Size of the move in dollars",
   q_desc_es="Tamano del movimiento en dolares")

_a("RDN", AlertType.RUNNING_DOWN_NOW,
   "Running down now", "Bajando ahora", "momentum", "-", 1, True, 0,
   "Stock price trading down much faster than expected. Shortest timeframe (~1 min). "
   "No confirmation, can fire on a single print.",
   "Precio bajando mucho mas rapido de lo esperado. Timeframe mas corto (~1 min). "
   "Sin confirmacion, puede disparar con un solo print.",
   flip="RUN", parent="RUN", keywords=["price vs time", "single print"],
   cs_type=CustomSettingType.MIN_CENTS,
   cs_label="Min move $", cs_label_es="Min movimiento $",
   cs_hint="Size of the move in dollars. 0.60 = at least 60 cents in last minute.",
   cs_default=None, cs_unit="$",
   q_desc="Size of the move in dollars",
   q_desc_es="Tamano del movimiento en dolares")

_a("RU", AlertType.RUNNING_UP,
   "Running up", "Subiendo", "momentum", "+", 1, True, 0,
   "Clear, statistically validated move upwards on ~1 min scale. "
   "Quality = momentum/volatility ratio. 1=min, 4=top 1/3, 10=top 1%.",
   "Movimiento alcista claro y estadisticamente validado en escala ~1 min. "
   "Quality = ratio momentum/volatilidad. 1=min, 4=top 1/3, 10=top 1%.",
   flip="RD", keywords=["price vs time", "nbbo confirmed"],
   cs_type=CustomSettingType.QUALITY_RATIO,
   cs_label="Min quality", cs_label_es="Min calidad",
   cs_hint="1 = all alerts. 1.5 = 50% above minimum. 4 = top 1/3. 10 = top 1%.",
   cs_default=None, cs_unit="",
   q_desc="Momentum/volatility ratio (1=min, 4=top 1/3, 10=top 1%)",
   q_desc_es="Ratio momentum/volatilidad (1=min, 4=top 1/3, 10=top 1%)")

_a("RD", AlertType.RUNNING_DOWN,
   "Running down", "Bajando", "momentum", "-", 1, True, 0,
   "Clear, statistically validated move downwards on ~1 min scale. "
   "Quality = momentum/volatility ratio.",
   "Movimiento bajista claro y estadisticamente validado en escala ~1 min. "
   "Quality = ratio momentum/volatilidad.",
   flip="RU", parent="RU", keywords=["price vs time", "nbbo confirmed"],
   cs_type=CustomSettingType.QUALITY_RATIO,
   cs_label="Min quality", cs_label_es="Min calidad",
   cs_hint="1 = all alerts. 1.5 = 50% above minimum. 4 = top 1/3. 10 = top 1%.",
   cs_default=None, cs_unit="",
   q_desc="Momentum/volatility ratio",
   q_desc_es="Ratio momentum/volatilidad")

_a("RUI", AlertType.RUNNING_UP_INTERMEDIATE,
   "Running up (intermediate)", "Subiendo (intermedio)", "momentum", "+", 1, True, 0,
   "Middle ground between fast and confirmed running alerts. ~5 min timeframe. "
   "Spread-adjusted, NBBO-sensitive. Min 2x expected movement.",
   "Punto medio entre alertas running rapidas y confirmadas. ~5 min. "
   "Ajustado por spread, sensible a NBBO. Min 2x movimiento esperado.",
   flip="RDI", keywords=["price vs time"],
   cs_type=CustomSettingType.VOLUME_RATIO,
   cs_label="Min ratio", cs_label_es="Min ratio",
   cs_hint="Ratio of actual speed vs expected. 2.4=30th pct, 2.9=50th, 6.6=90th.",
   cs_default=None, cs_unit="x",
   q_desc="Ratio of actual speed vs expected speed based on historical volatility",
   q_desc_es="Ratio de velocidad real vs esperada basada en volatilidad historica")

_a("RDI", AlertType.RUNNING_DOWN_INTERMEDIATE,
   "Running down (intermediate)", "Bajando (intermedio)", "momentum", "-", 1, True, 0,
   "Middle ground between fast and confirmed running alerts. ~5 min timeframe.",
   "Punto medio entre alertas running rapidas y confirmadas. ~5 min.",
   flip="RUI", parent="RUI", keywords=["price vs time"],
   cs_type=CustomSettingType.VOLUME_RATIO,
   cs_label="Min ratio", cs_label_es="Min ratio",
   cs_hint="Ratio of actual speed vs expected. 2.4=30th pct, 2.9=50th, 6.6=90th.",
   cs_default=None, cs_unit="x",
   q_desc="Ratio of actual speed vs expected speed",
   q_desc_es="Ratio de velocidad real vs esperada")

_a("RUC", AlertType.RUNNING_UP_CONFIRMED,
   "Running up (confirmed)", "Subiendo (confirmado)", "momentum", "+", 1, True, 0,
   "Volume confirmed running alert. ~15 min timeframe. Requires speed + consistency. "
   "Quality 5.0+ = briskly. 4 = top 1/3. 10 = top 1%.",
   "Alerta running confirmada por volumen. ~15 min. Requiere velocidad + consistencia.",
   flip="RDC", keywords=["price vs time", "volume confirmed"],
   cs_type=CustomSettingType.QUALITY_RATIO,
   cs_label="Min quality", cs_label_es="Min calidad",
   cs_hint="1.0 = all alerts. 5.0+ = briskly. 4 = top 1/3. 10 = top 1%.",
   cs_default=None, cs_unit="",
   q_desc="Momentum/volatility ratio (1=min, 4=top 1/3, 10=top 1%)",
   q_desc_es="Ratio momentum/volatilidad (1=min, 4=top 1/3, 10=top 1%)")

_a("RDC", AlertType.RUNNING_DOWN_CONFIRMED,
   "Running down (confirmed)", "Bajando (confirmado)", "momentum", "-", 1, True, 0,
   "Volume confirmed running alert. ~15 min timeframe. Requires speed + consistency.",
   "Alerta running confirmada por volumen. ~15 min. Requiere velocidad + consistencia.",
   flip="RUC", parent="RUC", keywords=["price vs time", "volume confirmed"],
   cs_type=CustomSettingType.QUALITY_RATIO,
   cs_label="Min quality", cs_label_es="Min calidad",
   cs_hint="1.0 = all alerts. 5.0+ = briskly. 4 = top 1/3. 10 = top 1%.",
   cs_default=None, cs_unit="",
   q_desc="Momentum/volatility ratio",
   q_desc_es="Ratio momentum/volatilidad")

_a("PUD", AlertType.PERCENT_UP_DAY,
   "% Up For The Day", "% Arriba del Día", "momentum", "+", 1, True, 0,
   "Reports each integer % level (3,4,5,...) once per day. Official prints only",
   "Reporta cada nivel entero de % (3,4,5,...) una vez al día. Solo prints oficiales",
   flip="PDD", keywords=["highs and lows", "single print"],
   cs_type=CustomSettingType.MIN_PERCENT,
   cs_label="Min % change", cs_label_es="Mín % cambio",
   cs_hint="Min % up to show. Default 3%. Reports each integer level once per day",
   cs_default=3, cs_unit="%",
   q_desc="% up for the day", q_desc_es="% arriba del día")

_a("PDD", AlertType.PERCENT_DOWN_DAY,
   "% Down For The Day", "% Abajo del Día", "momentum", "-", 1, True, 0,
   "Reports each integer % level (3,4,5,...) once per day. Official prints only",
   "Reporta cada nivel entero de % (3,4,5,...) una vez al día. Solo prints oficiales",
   flip="PUD", parent="PUD", keywords=["highs and lows", "single print"],
   cs_type=CustomSettingType.MIN_PERCENT,
   cs_label="Min % change", cs_label_es="Mín % cambio",
   cs_hint="Min % down to show. Default 3%. Reports each integer level once per day",
   cs_default=3, cs_unit="%",
   q_desc="% down for the day", q_desc_es="% abajo del día")


# ──────────────────────────────────────────────────────────────────────
# STD DEV BREAKOUT / BREAKDOWN  (quality = total sigmas from prev close)
# TI: 1 year daily vol, scaled to 1 day. Integer levels, once per day.
# ──────────────────────────────────────────────────────────────────────

_a("BBU", AlertType.STD_DEV_BREAKOUT,
   "Standard deviation breakout", "Ruptura por desviación estándar",
   "price", "+", 1, True, 0,
   "Price moves up N daily standard deviations from previous close",
   "El precio sube N desviaciones estándar diarias desde el cierre anterior",
   flip="BBD", keywords=["highs and lows", "single print"],
   cs_type=CustomSettingType.MIN_SIGMA,
   cs_label="Min std devs", cs_label_es="Mín desv. estándar",
   cs_hint="1 = one daily σ (default). Integer levels only.", cs_default=1, cs_unit="σ",
   q_desc="Total standard deviations up from previous close",
   q_desc_es="Desviaciones estándar totales por encima del cierre anterior")

_a("BBD", AlertType.STD_DEV_BREAKDOWN,
   "Standard deviation breakdown", "Quiebre por desviación estándar",
   "price", "-", 1, True, 0,
   "Price moves down N daily standard deviations from previous close",
   "El precio baja N desviaciones estándar diarias desde el cierre anterior",
   flip="BBU", parent="BBU", keywords=["highs and lows", "single print"],
   cs_type=CustomSettingType.MIN_SIGMA,
   cs_label="Min std devs", cs_label_es="Mín desv. estándar",
   cs_hint="1 = one daily σ (default). Integer levels only.", cs_default=1, cs_unit="σ",
   q_desc="Total standard deviations down from previous close",
   q_desc_es="Desviaciones estándar totales por debajo del cierre anterior")


# ──────────────────────────────────────────────────────────────────────
# CROSSES — Open/Close (quality = min_seconds for confirmed variants)
# ──────────────────────────────────────────────────────────────────────

_a("CAO", AlertType.CROSSED_ABOVE_OPEN,
   "Crossed above open", "Cruzo sobre apertura", "price", "+", 1, True, 0,
   "Stock changes from down to up for the day (vs open). "
   "In pre-market, compares to previous day's open. "
   "CAO and CBO share the same timer; open and close are independent.",
   "La accion pasa de negativa a positiva en el dia (vs apertura). "
   "En pre-market, compara con la apertura del dia anterior. "
   "CAO y CBO comparten timer; apertura y cierre son independientes.",
   flip="CBO", keywords=["single print"],
   cs_type=CustomSettingType.MIN_SECONDS,
   cs_label="Min seconds", cs_label_es="Min segundos",
   cs_hint="After first cross, price must stay on one side for N seconds before next alert. "
   "Leave blank to see every cross.",
   cs_default=None, cs_unit="sec",
   q_desc="Seconds since it has crossed the open",
   q_desc_es="Segundos desde que cruzo la apertura")

_a("CBO", AlertType.CROSSED_BELOW_OPEN,
   "Crossed below open", "Cruzo bajo apertura", "price", "-", 1, True, 0,
   "Stock changes from up to down for the day (vs open). "
   "In pre-market, compares to previous day's open. "
   "Shares timer with CAO.",
   "La accion pasa de positiva a negativa en el dia (vs apertura). "
   "En pre-market, compara con la apertura del dia anterior. "
   "Comparte timer con CAO.",
   flip="CAO", parent="CAO", keywords=["single print"],
   cs_type=CustomSettingType.MIN_SECONDS,
   cs_label="Min seconds", cs_label_es="Min segundos",
   cs_hint="After first cross, price must stay on one side for N seconds before next alert.",
   cs_default=None, cs_unit="sec",
   q_desc="Seconds since it has crossed the open",
   q_desc_es="Segundos desde que cruzo la apertura")

_a("CAC", AlertType.CROSSED_ABOVE_CLOSE,
   "Crossed above close", "Cruzo sobre cierre", "price", "+", 1, True, 0,
   "Price crosses above previous day's close. "
   "CAC and CBC share the same timer; open and close are independent.",
   "El precio cruza por encima del cierre del dia anterior. "
   "CAC y CBC comparten timer; apertura y cierre son independientes.",
   flip="CBC", keywords=["single print"],
   cs_type=CustomSettingType.MIN_SECONDS,
   cs_label="Min seconds", cs_label_es="Min segundos",
   cs_hint="After first cross, price must stay on one side for N seconds before next alert.",
   cs_default=None, cs_unit="sec",
   q_desc="Seconds since it has crossed the close",
   q_desc_es="Segundos desde que cruzo el cierre")

_a("CBC", AlertType.CROSSED_BELOW_CLOSE,
   "Crossed below close", "Cruzo bajo cierre", "price", "-", 1, True, 0,
   "Price crosses below previous day's close. Shares timer with CAC.",
   "El precio cruza por debajo del cierre del dia anterior. Comparte timer con CAC.",
   flip="CAC", parent="CAC", keywords=["single print"],
   cs_type=CustomSettingType.MIN_SECONDS,
   cs_label="Min seconds", cs_label_es="Min segundos",
   cs_hint="After first cross, price must stay on one side for N seconds before next alert.",
   cs_default=None, cs_unit="sec",
   q_desc="Seconds since it has crossed the close",
   q_desc_es="Segundos desde que cruzo el cierre")

_a("CAOC", AlertType.CROSSED_ABOVE_OPEN_CONFIRMED,
   "Crossed above open (confirmed)", "Cruzo sobre apertura (confirmado)",
   "price", "+", 1, True, 0,
   "Price crosses above open, confirmed by volume-weighted statistical analysis. "
   "Filters out noise; requires price to hold with sufficient volume. "
   "Average confirmation ~15 min, shorter when volume is high.",
   "El precio cruza sobre la apertura, confirmado por analisis estadistico ponderado por volumen. "
   "Filtra ruido; requiere que el precio se mantenga con volumen suficiente.",
   flip="CBOC", keywords=["volume confirmed"])

_a("CBOC", AlertType.CROSSED_BELOW_OPEN_CONFIRMED,
   "Crossed below open (confirmed)", "Cruzo bajo apertura (confirmado)",
   "price", "-", 1, True, 0,
   "Price crosses below open, confirmed by volume-weighted statistical analysis. "
   "Filters out noise; requires price to hold with sufficient volume.",
   "El precio cruza bajo la apertura, confirmado por analisis estadistico ponderado por volumen. "
   "Filtra ruido; requiere que el precio se mantenga con volumen suficiente.",
   flip="CAOC", parent="CAOC", keywords=["volume confirmed"])

_a("CACC", AlertType.CROSSED_ABOVE_CLOSE_CONFIRMED,
   "Crossed above close (confirmed)", "Cruzo sobre cierre (confirmado)",
   "price", "+", 1, True, 0,
   "Price crosses above prev close, confirmed by volume-weighted statistical analysis. "
   "Filters out noise; requires price to hold with sufficient volume.",
   "El precio cruza sobre el cierre previo, confirmado por analisis estadistico ponderado por volumen. "
   "Filtra ruido; requiere que el precio se mantenga con volumen suficiente.",
   flip="CBCC", keywords=["volume confirmed"])

_a("CBCC", AlertType.CROSSED_BELOW_CLOSE_CONFIRMED,
   "Crossed below close (confirmed)", "Cruzo bajo cierre (confirmado)",
   "price", "-", 1, True, 0,
   "Price crosses below prev close, confirmed by volume-weighted statistical analysis. "
   "Filters out noise; requires price to hold with sufficient volume.",
   "El precio cruza bajo el cierre previo, confirmado por analisis estadistico ponderado por volumen. "
   "Filtra ruido; requiere que el precio se mantenga con volumen suficiente.",
   flip="CACC", parent="CACC", keywords=["volume confirmed"])


# ──────────────────────────────────────────────────────────────────────
# CROSSES — VWAP (no custom setting)
# ──────────────────────────────────────────────────────────────────────

_a("CAVC", AlertType.CROSSED_ABOVE_VWAP,
   "Crossed above VWAP", "Cruce sobre VWAP", "vwap", "+", 1, True, 0,
   "Crossed above VWAP. Same statistical analysis as confirmed crosses.",
   "Cruce sobre VWAP. Mismo analisis estadistico que cruces confirmados.",
   flip="CBVC", parent="CA200", keywords=["volume confirmed"])

_a("CBVC", AlertType.CROSSED_BELOW_VWAP,
   "Crossed below VWAP", "Cruce bajo VWAP", "vwap", "-", 1, True, 0,
   "Crossed below VWAP. Same statistical analysis as confirmed crosses.",
   "Cruce bajo VWAP. Mismo analisis estadistico que cruces confirmados.",
   flip="CAVC", parent="CAVC", keywords=["volume confirmed"])

_a("VDU", AlertType.VWAP_DIVERGENCE_UP,
   "Positive VWAP divergence", "Divergencia VWAP positiva", "vwap", "+", 1, True, 0,
   "Price is N integer % above VWAP. Reports each integer level once per day. "
   "Re-fires on return trip. Popular with algorithmic traders.",
   "Precio N% entero sobre VWAP. Reporta cada nivel entero una vez. "
   "Re-dispara en viaje de retorno. Popular con traders algoritmicos.",
   flip="VDD", keywords=[],
   cs_type=CustomSettingType.MIN_PERCENT,
   cs_label="Min % above VWAP", cs_label_es="Min % sobre VWAP",
   cs_hint="Min integer % above VWAP. Reports each integer level (1,2,3...).",
   cs_default=None, cs_unit="%",
   q_desc="% above VWAP", q_desc_es="% sobre VWAP")

_a("VDD", AlertType.VWAP_DIVERGENCE_DOWN,
   "Negative VWAP divergence", "Divergencia VWAP negativa", "vwap", "-", 1, True, 0,
   "Price is N integer % below VWAP. Reports each integer level once per day. "
   "Re-fires on return trip. Popular with algorithmic traders.",
   "Precio N% entero bajo VWAP. Reporta cada nivel entero una vez. "
   "Re-dispara en viaje de retorno. Popular con traders algoritmicos.",
   flip="VDU", parent="VDU", keywords=[],
   cs_type=CustomSettingType.MIN_PERCENT,
   cs_label="Min % below VWAP", cs_label_es="Min % bajo VWAP",
   cs_hint="Min integer % below VWAP. Reports each integer level (1,2,3...).",
   cs_default=None, cs_unit="%",
   q_desc="% below VWAP", q_desc_es="% bajo VWAP")


# ──────────────────────────────────────────────────────────────────────
# CROSSES — Daily MAs (no custom setting — binary cross)
# ──────────────────────────────────────────────────────────────────────

_a("CA20", AlertType.CROSSED_ABOVE_SMA20_DAILY,
   "Crossed above 20 day moving average", "Cruce sobre SMA 20 diaria", "ma_cross", "+", 1, True, 0,
   "Crossed above 20 day moving average. Volume confirmed.",
   "Cruce sobre media movil de 20 dias. Confirmado por volumen.",
   flip="CB20", keywords=["moving average", "volume confirmed"])

_a("CB20", AlertType.CROSSED_BELOW_SMA20_DAILY,
   "Crossed below 20 day moving average", "Cruce bajo SMA 20 diaria", "ma_cross", "-", 1, True, 0,
   "Crossed below 20 day moving average. Volume confirmed.",
   "Cruce bajo media movil de 20 dias. Confirmado por volumen.",
   flip="CA20", parent="CA20", keywords=["moving average", "volume confirmed"])

_a("CA50", AlertType.CROSSED_ABOVE_SMA50_DAILY,
   "Crossed above 50 day moving average", "Cruce sobre SMA 50 diaria", "ma_cross", "+", 1, True, 0,
   "Crossed above 50 day moving average. Volume confirmed.",
   "Cruce sobre media movil de 50 dias. Confirmado por volumen.",
   flip="CB50", keywords=["moving average", "volume confirmed"])

_a("CB50", AlertType.CROSSED_BELOW_SMA50_DAILY,
   "Crossed below 50 day moving average", "Cruce bajo SMA 50 diaria", "ma_cross", "-", 1, True, 0,
   "Crossed below 50 day moving average. Volume confirmed.",
   "Cruce bajo media movil de 50 dias. Confirmado por volumen.",
   flip="CA50", parent="CA50", keywords=["moving average", "volume confirmed"])

_a("CA200", AlertType.CROSSED_ABOVE_SMA200,
   "Crossed above 200 day moving average", "Cruce sobre SMA 200 diaria", "ma_cross", "+", 1, True, 0,
   "Crossed above 200 day moving average. Volume confirmed. Institutional staple.",
   "Cruce sobre media movil de 200 dias. Confirmado por volumen. Referencia institucional.",
   flip="CB200", keywords=["moving average", "volume confirmed"])

_a("CB200", AlertType.CROSSED_BELOW_SMA200,
   "Crossed below 200 day moving average", "Cruce bajo SMA 200 diaria", "ma_cross", "-", 1, True, 0,
   "Crossed below 200 day moving average. Volume confirmed. Institutional staple.",
   "Cruce bajo media movil de 200 dias. Confirmado por volumen. Referencia institucional.",
   flip="CA200", parent="CA200", keywords=["moving average", "volume confirmed"])


# ──────────────────────────────────────────────────────────────────────
# CHECK MARK — Continuation patterns (no custom settings)
# ──────────────────────────────────────────────────────────────────────

_a("CMU", AlertType.CHECK_MARK_UP,
   "Check Mark", "Marca de Verificación", "pullback", "+", 1, True, 600,
   "Higher highs, pullback, then even higher highs (continuation up). Not before open or first 3 min",
   "Máximos crecientes, retroceso, luego máximos aún mayores (continuación alcista). No antes de apertura ni primeros 3 min",
   flip="CMD", keywords=["highs and lows", "single print"])

_a("CMD", AlertType.CHECK_MARK_DOWN,
   "Inverted Check Mark", "Marca de Verificación Invertida", "pullback", "-", 1, True, 600,
   "Lower lows, bounce, then even lower lows (continuation down). Not before open or first 3 min",
   "Mínimos decrecientes, rebote, luego mínimos aún menores (continuación bajista). No antes de apertura ni primeros 3 min",
   flip="CMU", parent="CMU", keywords=["highs and lows", "single print"])


# ──────────────────────────────────────────────────────────────────────
# PULLBACKS — Auto variants (anchor = whichever of open/close is bigger)
# Popular with Fibonacci traders.
# ──────────────────────────────────────────────────────────────────────

_a("PFL75", AlertType.PULLBACK_75_FROM_LOW,
   "75% Pullback From Lows", "Retroceso 75% desde Mínimos",
   "pullback", "+", 1, True, 60,
   "Auto-picks open or prev close (whichever makes bigger pattern). Stock goes to low, bounces 75% back",
   "Auto-elige apertura o cierre previo (el que genere patrón mayor). Baja al mínimo, rebota 75%",
   flip="PFH75", keywords=["fibonacci", "highs and lows", "single print"],
   cs_type=CustomSettingType.MIN_PERCENT,
   cs_label="Min initial move %", cs_label_es="Mín movimiento inicial %",
   cs_hint="Size of first move (anchor to low). Blank = no filter",
   cs_default=None, cs_unit="%",
   q_desc="Initial move size: % from anchor to low",
   q_desc_es="Tamaño movimiento inicial: % desde ancla al mínimo")

_a("PFL25", AlertType.PULLBACK_25_FROM_LOW,
   "25% Pullback From Lows", "Retroceso 25% desde Mínimos",
   "pullback", "+", 1, True, 60,
   "Auto-picks open or prev close (whichever makes bigger pattern). Stock goes to low, bounces 25% back",
   "Auto-elige apertura o cierre previo (el que genere patrón mayor). Baja al mínimo, rebota 25%",
   flip="PFH25", parent="PFL75", keywords=["fibonacci", "highs and lows", "single print"],
   cs_type=CustomSettingType.MIN_PERCENT,
   cs_label="Min initial move %", cs_label_es="Mín movimiento inicial %",
   cs_hint="Size of first move (anchor to low). Blank = no filter",
   cs_default=None, cs_unit="%",
   q_desc="Initial move size: % from anchor to low",
   q_desc_es="Tamaño movimiento inicial: % desde ancla al mínimo")

_a("PFH75", AlertType.PULLBACK_75_FROM_HIGH,
   "75% Pullback From Highs", "Retroceso 75% desde Máximos",
   "pullback", "-", 1, True, 60,
   "Auto-picks open or prev close (whichever makes bigger pattern). Stock goes to high, pulls back 75%",
   "Auto-elige apertura o cierre previo (el que genere patrón mayor). Sube al máximo, retrocede 75%",
   flip="PFL75", keywords=["fibonacci", "highs and lows", "single print"],
   cs_type=CustomSettingType.MIN_PERCENT,
   cs_label="Min initial move %", cs_label_es="Mín movimiento inicial %",
   cs_hint="Size of first move (anchor to high). Blank = no filter",
   cs_default=None, cs_unit="%",
   q_desc="Initial move size: % from anchor to high",
   q_desc_es="Tamaño movimiento inicial: % desde ancla al máximo")

_a("PFH25", AlertType.PULLBACK_25_FROM_HIGH,
   "25% Pullback From Highs", "Retroceso 25% desde Máximos",
   "pullback", "-", 1, True, 60,
   "Auto-picks open or prev close (whichever makes bigger pattern). Stock goes to high, pulls back 25%",
   "Auto-elige apertura o cierre previo (el que genere patrón mayor). Sube al máximo, retrocede 25%",
   flip="PFL25", parent="PFH75", keywords=["fibonacci", "highs and lows", "single print"],
   cs_type=CustomSettingType.MIN_PERCENT,
   cs_label="Min initial move %", cs_label_es="Mín movimiento inicial %",
   cs_hint="Size of first move (anchor to high). Blank = no filter",
   cs_default=None, cs_unit="%",
   q_desc="Initial move size: % from anchor to high",
   q_desc_es="Tamaño movimiento inicial: % desde ancla al máximo")

# ──────────────────────────────────────────────────────────────────────
# PULLBACKS — Close variants (anchor = yesterday's close)
# ──────────────────────────────────────────────────────────────────────

_a("PFL75C", AlertType.PULLBACK_75_FROM_LOW_CLOSE,
   "75% Pullback From Lows (Close)", "Retroceso 75% desde Mínimos (Cierre)",
   "pullback", "+", 1, True, 60,
   "Start at prev close, stock goes down to low, bounces 75% back toward close",
   "Desde cierre anterior, baja al mínimo, rebota 75% hacia el cierre",
   flip="PFH75C", keywords=["highs and lows", "single print"],
   cs_type=CustomSettingType.MIN_PERCENT,
   cs_label="Min initial move %", cs_label_es="Mín movimiento inicial %",
   cs_hint="Size of first move (close to low). Blank = no filter",
   cs_default=None, cs_unit="%",
   q_desc="Initial move size: % from close to low",
   q_desc_es="Tamaño movimiento inicial: % desde cierre al mínimo")

_a("PFL25C", AlertType.PULLBACK_25_FROM_LOW_CLOSE,
   "25% Pullback From Lows (Close)", "Retroceso 25% desde Mínimos (Cierre)",
   "pullback", "+", 1, True, 60,
   "Start at prev close, stock goes down to low, bounces 25% back toward close",
   "Desde cierre anterior, baja al mínimo, rebota 25% hacia el cierre",
   flip="PFH25C", parent="PFL75C", keywords=["highs and lows", "single print"],
   cs_type=CustomSettingType.MIN_PERCENT,
   cs_label="Min initial move %", cs_label_es="Mín movimiento inicial %",
   cs_hint="Size of first move (close to low). Blank = no filter",
   cs_default=None, cs_unit="%",
   q_desc="Initial move size: % from close to low",
   q_desc_es="Tamaño movimiento inicial: % desde cierre al mínimo")

_a("PFH75C", AlertType.PULLBACK_75_FROM_HIGH_CLOSE,
   "75% Pullback From Highs (Close)", "Retroceso 75% desde Máximos (Cierre)",
   "pullback", "-", 1, True, 60,
   "Start at prev close, stock goes up to high, pulls back 75% toward close",
   "Desde cierre anterior, sube al máximo, retrocede 75% hacia el cierre",
   flip="PFL75C", keywords=["highs and lows", "single print"],
   cs_type=CustomSettingType.MIN_PERCENT,
   cs_label="Min initial move %", cs_label_es="Mín movimiento inicial %",
   cs_hint="Size of first move (close to high). Blank = no filter",
   cs_default=None, cs_unit="%",
   q_desc="Initial move size: % from close to high",
   q_desc_es="Tamaño movimiento inicial: % desde cierre al máximo")

_a("PFH25C", AlertType.PULLBACK_25_FROM_HIGH_CLOSE,
   "25% Pullback From Highs (Close)", "Retroceso 25% desde Máximos (Cierre)",
   "pullback", "-", 1, True, 60,
   "Start at prev close, stock goes up to high, pulls back 25% toward close",
   "Desde cierre anterior, sube al máximo, retrocede 25% hacia el cierre",
   flip="PFL25C", parent="PFH75C", keywords=["highs and lows", "single print"],
   cs_type=CustomSettingType.MIN_PERCENT,
   cs_label="Min initial move %", cs_label_es="Mín movimiento inicial %",
   cs_hint="Size of first move (close to high). Blank = no filter",
   cs_default=None, cs_unit="%",
   q_desc="Initial move size: % from close to high",
   q_desc_es="Tamaño movimiento inicial: % desde cierre al máximo")

# ── PULLBACKS — Open variants (anchor = today's open) ──

_a("PFL75O", AlertType.PULLBACK_75_FROM_LOW_OPEN,
   "75% Pullback From Lows (Open)", "Retroceso 75% desde Mínimos (Apertura)",
   "pullback", "+", 1, True, 60,
   "Start at today's open, stock goes down to low, bounces 75% back toward open",
   "Desde apertura de hoy, baja al mínimo, rebota 75% hacia la apertura",
   flip="PFH75O", keywords=["highs and lows", "single print"],
   cs_type=CustomSettingType.MIN_PERCENT,
   cs_label="Min initial move %", cs_label_es="Mín movimiento inicial %",
   cs_hint="Size of first move (open to low). Blank = no filter",
   cs_default=None, cs_unit="%",
   q_desc="Initial move size: % from open to low",
   q_desc_es="Tamaño movimiento inicial: % desde apertura al mínimo")

_a("PFL25O", AlertType.PULLBACK_25_FROM_LOW_OPEN,
   "25% Pullback From Lows (Open)", "Retroceso 25% desde Mínimos (Apertura)",
   "pullback", "+", 1, True, 60,
   "Start at today's open, stock goes down to low, bounces 25% back toward open",
   "Desde apertura de hoy, baja al mínimo, rebota 25% hacia la apertura",
   flip="PFH25O", parent="PFL75O", keywords=["highs and lows", "single print"],
   cs_type=CustomSettingType.MIN_PERCENT,
   cs_label="Min initial move %", cs_label_es="Mín movimiento inicial %",
   cs_hint="Size of first move (open to low). Blank = no filter",
   cs_default=None, cs_unit="%",
   q_desc="Initial move size: % from open to low",
   q_desc_es="Tamaño movimiento inicial: % desde apertura al mínimo")

_a("PFH75O", AlertType.PULLBACK_75_FROM_HIGH_OPEN,
   "75% Pullback From Highs (Open)", "Retroceso 75% desde Máximos (Apertura)",
   "pullback", "-", 1, True, 60,
   "Start at today's open, stock goes up to high, pulls back 75% toward open",
   "Desde apertura de hoy, sube al máximo, retrocede 75% hacia la apertura",
   flip="PFL75O", keywords=["highs and lows", "single print"],
   cs_type=CustomSettingType.MIN_PERCENT,
   cs_label="Min initial move %", cs_label_es="Mín movimiento inicial %",
   cs_hint="Size of first move (open to high). Blank = no filter",
   cs_default=None, cs_unit="%",
   q_desc="Initial move size: % from open to high",
   q_desc_es="Tamaño movimiento inicial: % desde apertura al máximo")

_a("PFH25O", AlertType.PULLBACK_25_FROM_HIGH_OPEN,
   "25% Pullback From Highs (Open)", "Retroceso 25% desde Máximos (Apertura)",
   "pullback", "-", 1, True, 60,
   "Start at today's open, stock goes up to high, pulls back 25% toward open",
   "Desde apertura de hoy, sube al máximo, retrocede 25% hacia la apertura",
   flip="PFL25O", parent="PFH75O", keywords=["highs and lows", "single print"],
   cs_type=CustomSettingType.MIN_PERCENT,
   cs_label="Min initial move %", cs_label_es="Mín movimiento inicial %",
   cs_hint="Size of first move (open to high). Blank = no filter",
   cs_default=None, cs_unit="%",
   q_desc="Initial move size: % from open to high",
   q_desc_es="Tamaño movimiento inicial: % desde apertura al máximo")


# ──────────────────────────────────────────────────────────────────────
# GAPS (quality = min_dollars = total retracement $)
# ──────────────────────────────────────────────────────────────────────

_a("GUR", AlertType.GAP_UP_REVERSAL,
   "Gap up reversal", "Reversion gap alcista", "gap", "-", 1, True, 0,
   "Stock gaps up then crosses prev close from above. Once per day. "
   "Quality = total retracement (gap + continuation).",
   "Accion con gap alcista cruza cierre previo. Una vez al dia. "
   "Quality = retroceso total (gap + continuacion).",
   flip="GDR", keywords=["single print"],
   cs_type=CustomSettingType.MIN_DOLLARS,
   cs_label="Min total retracement $", cs_label_es="Min retroceso total $",
   cs_hint="Min total retracement (gap + continuation) in dollars.",
   cs_default=None, cs_unit="$",
   q_desc="Total retracement: gap + continuation ($)",
   q_desc_es="Retroceso total: gap + continuacion ($)")

_a("GDR", AlertType.GAP_DOWN_REVERSAL,
   "Gap down reversal", "Reversion gap bajista", "gap", "+", 1, True, 0,
   "Stock gaps down then crosses prev close from below. Once per day. "
   "Quality = total retracement (gap + continuation).",
   "Accion con gap bajista cruza cierre previo. Una vez al dia. "
   "Quality = retroceso total (gap + continuacion).",
   flip="GUR", parent="GUR", keywords=["single print"],
   cs_type=CustomSettingType.MIN_DOLLARS,
   cs_label="Min total retracement $", cs_label_es="Min retroceso total $",
   cs_hint="Min total retracement (gap + continuation) in dollars.",
   cs_default=None, cs_unit="$",
   q_desc="Total retracement: gap + continuation ($)",
   q_desc_es="Retroceso total: gap + continuacion ($)")

_a("FGUR", AlertType.FALSE_GAP_UP_RETRACEMENT,
   "False gap up retracement", "Retroceso falso gap alcista", "gap", "+", 1, True, 0,
   "Stock gaps up, partially fills gap (drops below open but stays above close), "
   "then continues above open. Horseshoe pattern. Quality = % of gap filled.",
   "Accion con gap alcista, llena parcialmente el gap (baja del open pero no del cierre), "
   "luego continua sobre el open. Patron herradura. Quality = % del gap llenado.",
   flip="FGDR", keywords=["single print"],
   cs_type=CustomSettingType.MIN_PERCENT,
   cs_label="Min % gap filled", cs_label_es="Min % gap llenado",
   cs_hint="Min % of gap that was filled before continuing. E.g. 60 = gap was 60% filled.",
   cs_default=None, cs_unit="%",
   q_desc="% of gap filled before continuation",
   q_desc_es="% del gap llenado antes de continuar")

_a("FGDR", AlertType.FALSE_GAP_DOWN_RETRACEMENT,
   "False gap down retracement", "Retroceso falso gap bajista", "gap", "-", 1, True, 0,
   "Stock gaps down, partially fills gap (rises above open but stays below close), "
   "then continues below open. Horseshoe pattern. Quality = % of gap filled.",
   "Accion con gap bajista, llena parcialmente el gap (sube del open pero no del cierre), "
   "luego continua bajo el open. Patron herradura. Quality = % del gap llenado.",
   flip="FGUR", parent="FGUR", keywords=["single print"],
   cs_type=CustomSettingType.MIN_PERCENT,
   cs_label="Min % gap filled", cs_label_es="Min % gap llenado",
   cs_hint="Min % of gap that was filled before continuing. E.g. 60 = gap was 60% filled.",
   cs_default=None, cs_unit="%",
   q_desc="% of gap filled before continuation",
   q_desc_es="% del gap llenado antes de continuar")


# ──────────────────────────────────────────────────────────────────────
# BID/ASK MICROSTRUCTURE
# ──────────────────────────────────────────────────────────────────────

_a("MC", AlertType.MARKET_CROSSED,
   "Market crossed", "Mercado cruzado", "bidask", "", 1, True, 0,
   "Ask price lower than bid price. Reports first crossing in each group; "
   "new alert only if cross grows or market uncrossed for several minutes.",
   "El precio ask es menor que el bid. Reporta el primer cruce de cada grupo; "
   "nueva alerta solo si el cruce crece o el mercado estuvo descruzado varios minutos.",
   keywords=["bid and ask"],
   cs_type=CustomSettingType.MIN_CENTS,
   cs_label="Min cents crossed", cs_label_es="Mín centavos cruzados",
   cs_hint="0.05 = only when bid-ask ≥ 5¢ crossed. Leave blank for all.",
   cs_default=None, cs_unit="¢",
   q_desc="Cents the market is crossed by",
   q_desc_es="Centavos por los que el mercado está cruzado")

_a("MCU", AlertType.MARKET_CROSSED_UP,
   "Market crossed up", "Mercado cruzado arriba", "bidask", "+", 1, True, 0,
   "Market crossed with upward bias (bid > prev close on primary market). "
   "Signals potential upward move.",
   "Mercado cruzado con sesgo alcista (bid > cierre anterior en mercado primario). "
   "Señal de posible movimiento alcista.",
   flip="MCD", parent="MC", keywords=["bid and ask", "listed"],
   cs_type=CustomSettingType.MIN_CENTS,
   cs_label="Min cents crossed", cs_label_es="Mín centavos cruzados",
   cs_hint="0.05 = at least 5¢ crossed. Leave blank for all.",
   cs_default=None, cs_unit="¢",
   q_desc="Cents crossed up",
   q_desc_es="Centavos cruzados arriba")

_a("MCD", AlertType.MARKET_CROSSED_DOWN,
   "Market crossed down", "Mercado cruzado abajo", "bidask", "-", 1, True, 0,
   "Market crossed with downward bias (ask < prev close on primary market). "
   "Signals potential downward move.",
   "Mercado cruzado con sesgo bajista (ask < cierre anterior en mercado primario). "
   "Señal de posible movimiento bajista.",
   flip="MCU", parent="MC", keywords=["bid and ask", "listed"],
   cs_type=CustomSettingType.MIN_CENTS,
   cs_label="Min cents crossed", cs_label_es="Mín centavos cruzados",
   cs_hint="0.05 = at least 5¢ crossed. Leave blank for all.",
   cs_default=None, cs_unit="¢",
   q_desc="Cents crossed down",
   q_desc_es="Centavos cruzados abajo")

_a("ML", AlertType.MARKET_LOCKED,
   "Market locked", "Mercado bloqueado", "bidask", "", 1, True, 0,
   "Bid equals ask (locked market). Filtered similar to market crossed: "
   "if this occurs several times in a row, only one alert is shown.",
   "El bid es igual al ask (mercado bloqueado). Filtrado similar a market crossed: "
   "si ocurre varias veces seguidas, solo se muestra una alerta.",
   keywords=["bid and ask"])

_a("LBS", AlertType.LARGE_BID_SIZE,
   "Large bid size", "Gran tamaño bid", "bidask", "+", 1, True, 0,
   "Unusually large bid size. Only for avg daily vol < 3M. "
   "Reports size increasing and price rising/dropping labels.",
   "Tamaño de bid inusualmente grande. Solo para vol diario promedio < 3M. "
   "Reporta etiquetas de tamaño creciente y precio subiendo/bajando.",
   flip="LAS", keywords=["bid and ask"],
   cs_type=CustomSettingType.MIN_SHARES,
   cs_label="Min bid shares", cs_label_es="Mín acciones bid",
   cs_hint="Min shares on best bid. Leave blank for defaults (6K if <1M vol, 10K if 1-3M vol).",
   cs_default=None, cs_unit="shares",
   q_desc="Number of shares on the bid",
   q_desc_es="Número de acciones en el bid")

_a("LAS", AlertType.LARGE_ASK_SIZE,
   "Large ask size", "Gran tamaño ask", "bidask", "-", 1, True, 0,
   "Unusually large ask size. Only for avg daily vol < 3M. "
   "Reports size increasing and price rising/dropping labels.",
   "Tamaño de ask inusualmente grande. Solo para vol diario promedio < 3M. "
   "Reporta etiquetas de tamaño creciente y precio subiendo/bajando.",
   flip="LBS", parent="LBS", keywords=["bid and ask"],
   cs_type=CustomSettingType.MIN_SHARES,
   cs_label="Min ask shares", cs_label_es="Mín acciones ask",
   cs_hint="Min shares on best ask. Leave blank for defaults (6K if <1M vol, 10K if 1-3M vol).",
   cs_default=None, cs_unit="shares",
   q_desc="Number of shares on the ask",
   q_desc_es="Número de acciones en el ask")

_a("LSP", AlertType.LARGE_SPREAD,
   "Large spread", "Spread grande", "bidask", "", 1, True, 0,
   "Specialist's spread suddenly becomes large (≥50 cents). "
   "If spread changes multiple times quickly, only the first alert is shown.",
   "El spread del especialista se vuelve grande repentinamente (≥50 centavos). "
   "Si el spread cambia varias veces rápidamente, solo se muestra la primera alerta.",
   keywords=["bid and ask"])

_a("TRA", AlertType.TRADING_ABOVE,
   "Trading above", "Operando por encima", "bidask", "+", 1, True, 0,
   "Print above best ask. Groups consecutive events. "
   "Strongest when multiple events occur for the same stock in a short period.",
   "Operación por encima del mejor ask. Agrupa eventos consecutivos. "
   "Más fuerte cuando ocurren múltiples eventos para el mismo símbolo en poco tiempo.",
   flip="TRB", keywords=["bid and ask", "single print"],
   cs_type=CustomSettingType.MIN_TIMES,
   cs_label="Min times", cs_label_es="Mín veces",
   cs_hint="Filter by min number of grouped events. Leave blank for all.",
   cs_default=None, cs_unit="times",
   q_desc="Number of consecutive prints above the ask",
   q_desc_es="Número de operaciones consecutivas por encima del ask")

_a("TRB", AlertType.TRADING_BELOW,
   "Trading below", "Operando por debajo", "bidask", "-", 1, True, 0,
   "Print below best bid. Groups consecutive events. "
   "Strongest when multiple events occur for the same stock in a short period.",
   "Operación por debajo del mejor bid. Agrupa eventos consecutivos. "
   "Más fuerte cuando ocurren múltiples eventos para el mismo símbolo en poco tiempo.",
   flip="TRA", parent="TRA", keywords=["bid and ask", "single print"],
   cs_type=CustomSettingType.MIN_TIMES,
   cs_label="Min times", cs_label_es="Mín veces",
   cs_hint="Filter by min number of grouped events. Leave blank for all.",
   cs_default=None, cs_unit="times",
   q_desc="Number of consecutive prints below the bid",
   q_desc_es="Número de operaciones consecutivas por debajo del bid")

_a("TRAS", AlertType.TRADING_ABOVE_SPECIALIST,
   "Trading above specialist", "Operando por encima del especialista",
   "bidask", "+", 1, True, 0,
   "Print above specialist's offer. Subset of Trading Above, "
   "only for NYSE/AMEX stocks during regular market hours.",
   "Operacion por encima de la oferta del especialista. Subconjunto de Trading Above, "
   "solo para acciones NYSE/AMEX durante horario regular.",
   flip="TRBS", keywords=["bid and ask", "single print", "listed"],
   cs_type=CustomSettingType.MIN_TIMES,
   cs_label="Min times", cs_label_es="Min veces",
   cs_hint="Filter by min number of grouped events. Leave blank for all.",
   cs_default=None, cs_unit="times",
   q_desc="Number of consecutive prints above the specialist's offer",
   q_desc_es="Numero de operaciones consecutivas por encima de la oferta del especialista")

_a("TRBS", AlertType.TRADING_BELOW_SPECIALIST,
   "Trading below specialist", "Operando por debajo del especialista",
   "bidask", "-", 1, True, 0,
   "Print below specialist's bid. Subset of Trading Below, "
   "only for NYSE/AMEX stocks during regular market hours.",
   "Operacion por debajo del bid del especialista. Subconjunto de Trading Below, "
   "solo para acciones NYSE/AMEX durante horario regular.",
   flip="TRAS", parent="TRAS", keywords=["bid and ask", "single print", "listed"],
   cs_type=CustomSettingType.MIN_TIMES,
   cs_label="Min times", cs_label_es="Min veces",
   cs_hint="Filter by min number of grouped events. Leave blank for all.",
   cs_default=None, cs_unit="times",
   q_desc="Number of consecutive prints below the specialist's bid",
   q_desc_es="Numero de operaciones consecutivas por debajo del bid del especialista")



# ──────────────────────────────────────────────────────────────────────
# HALTS (no custom setting)
# ──────────────────────────────────────────────────────────────────────

_a("HALT", AlertType.HALT,
   "Halt", "Halt", "halt", "", 1, True, 0,
   "Trading halt triggered. Description reports halt reason.",
   "Se activo una parada de trading. La descripcion reporta la razon.",
   keywords=[])

_a("RESUME", AlertType.RESUME,
   "Resume", "Reanudacion", "halt", "", 1, True, 0,
   "Trading resumes after halt.",
   "El trading se reanuda despues de una parada.",
   parent="HALT", keywords=[])


# ──────────────────────────────────────────────────────────────────────
# ORB — All 7 Tradeul timeframes (quality = range_pct)
# Codes: ORU1/ORD1, ORU2/ORD2, ORU5/ORD5, ORU10/ORD10,
#        ORU15/ORD15, ORU30/ORD30, ORU60/ORD60
# ──────────────────────────────────────────────────────────────────────

_ORB_TF_MAP = {
    1:  (AlertType.ORB_UP_1M,  AlertType.ORB_DOWN_1M),
    2:  (AlertType.ORB_UP_2M,  AlertType.ORB_DOWN_2M),
    5:  (AlertType.ORB_UP_5M,  AlertType.ORB_DOWN_5M),
    10: (AlertType.ORB_UP_10M, AlertType.ORB_DOWN_10M),
    15: (AlertType.ORB_UP_15M, AlertType.ORB_DOWN_15M),
    30: (AlertType.ORB_UP_30M, AlertType.ORB_DOWN_30M),
    60: (AlertType.ORB_UP_60M, AlertType.ORB_DOWN_60M),
}

for _tf, (_up_at, _dn_at) in _ORB_TF_MAP.items():
    _a(f"ORU{_tf}", _up_at,
       f"{_tf} Min Opening Range Breakout", f"Ruptura Rango Apertura {_tf} Min",
       "orb", "+", 1, True, 86400,
       f"Price breaks above the first {_tf} minute(s) trading range high",
       f"El precio rompe por encima del máximo del rango de los primeros {_tf} minuto(s)",
       flip=f"ORD{_tf}", keywords=["opening range", "breakout", "ORB", f"{_tf}min"],
       cs_type=CustomSettingType.MIN_PERCENT,
       cs_label="Min range %", cs_label_es="Mín rango %",
       cs_hint="0.5 = only when ORB range ≥ 0.5%", cs_default=None, cs_unit="%",
       q_desc=f"{_tf}-min opening range width %",
       q_desc_es=f"Ancho del rango de apertura de {_tf} min %")

    _a(f"ORD{_tf}", _dn_at,
       f"{_tf} Min Opening Range Breakdown", f"Quiebre Rango Apertura {_tf} Min",
       "orb", "-", 1, True, 86400,
       f"Price breaks below the first {_tf} minute(s) trading range low",
       f"El precio rompe por debajo del mínimo del rango de los primeros {_tf} minuto(s)",
       flip=f"ORU{_tf}", keywords=["opening range", "breakdown", "ORB", f"{_tf}min"],
       cs_type=CustomSettingType.MIN_PERCENT,
       cs_label="Min range %", cs_label_es="Mín rango %",
       cs_hint="0.5 = only when ORB range ≥ 0.5%", cs_default=None, cs_unit="%",
       q_desc=f"{_tf}-min opening range width %",
       q_desc_es=f"Ancho del rango de apertura de {_tf} min %")

del _ORB_TF_MAP


# ──────────────────────────────────────────────────────────────────────
# CONSOLIDATION
# ──────────────────────────────────────────────────────────────────────

_a("C", AlertType.CONSOLIDATION,
   "Consolidation", "Consolidacion", "consol", "", 1, True, 0,
   "Stock price changing significantly less than normal. "
   "Quality is a Z-score (2=min, 5=tight, 10=perfect). "
   "Uses historical volatility to determine expected range.",
   "El precio de la accion cambia significativamente menos de lo normal. "
   "Quality es un Z-score (2=min, 5=estrecho, 10=perfecto). "
   "Usa volatilidad historica para determinar el rango esperado.",
   keywords=["price vs time", "volume confirmed"],
   cs_type=CustomSettingType.QUALITY_RATIO,
   cs_label="Min quality", cs_label_es="Min calidad",
   cs_hint="2=default (any consolidation), 5=tight only, 10=perfect range",
   cs_default=2, cs_unit="",
   q_desc="Z-score quality of the consolidation pattern",
   q_desc_es="Z-score de calidad del patron de consolidacion")


# CONSOLIDATION BREAKOUT (quality = breakout magnitude / ATR)
# ──────────────────────────────────────────────────────────────────────

_a("CHBO", AlertType.CHANNEL_BREAKOUT,
   "Channel breakout", "Ruptura de canal", "consol", "+", 1, True, 0,
   "Fast channel breakout. Consolidation ends abruptly by upward movement. "
   "~1 min timescale. Quality = Z-score of consolidation (2=min, 5=tight, 10=best).",
   "Ruptura rapida de canal. Consolidacion termina abruptamente al alza. "
   "~1 min. Quality = Z-score de consolidacion (2=min, 5=tight, 10=best).",
   flip="CHBD", keywords=[],
   cs_type=CustomSettingType.QUALITY_RATIO,
   cs_label="Min consolidation quality", cs_label_es="Min calidad consolidacion",
   cs_hint="Quality of consolidation being broken. 2=min, 5=tight, 10=best.",
   cs_default=None, cs_unit="",
   q_desc="Z-score of consolidation pattern broken",
   q_desc_es="Z-score del patron de consolidacion roto")

_a("CHBD", AlertType.CHANNEL_BREAKDOWN,
   "Channel breakdown", "Quiebre de canal", "consol", "-", 1, True, 0,
   "Fast channel breakdown. Consolidation ends abruptly by downward movement. "
   "~1 min timescale. Quality = Z-score of consolidation (2=min, 5=tight, 10=best).",
   "Quiebre rapido de canal. Consolidacion termina abruptamente a la baja. "
   "~1 min. Quality = Z-score de consolidacion (2=min, 5=tight, 10=best).",
   flip="CHBO", parent="CHBO", keywords=[],
   cs_type=CustomSettingType.QUALITY_RATIO,
   cs_label="Min consolidation quality", cs_label_es="Min calidad consolidacion",
   cs_hint="Quality of consolidation being broken. 2=min, 5=tight, 10=best.",
   cs_default=None, cs_unit="",
   q_desc="Z-score of consolidation pattern broken",
   q_desc_es="Z-score del patron de consolidacion roto")

_a("CHBOC", AlertType.CHANNEL_BREAKOUT_CONFIRMED,
   "Channel breakout (confirmed)", "Ruptura de canal (confirmada)", "consol", "+", 1, True, 0,
   "Volume confirmed channel breakout. Transitions from consolidating to running. "
   "~15 min timeframe. Quality = momentum/vol ratio. 5.0+ = briskly.",
   "Ruptura de canal confirmada por volumen. Transicion de consolidacion a running. "
   "~15 min. Quality = ratio momentum/vol. 5.0+ = briskly.",
   flip="CHBDC", keywords=["volume confirmed"],
   cs_type=CustomSettingType.QUALITY_RATIO,
   cs_label="Min quality", cs_label_es="Min calidad",
   cs_hint="1.0 = all alerts. 5.0+ = briskly. 4 = top 1/3. 10 = top 1%.",
   cs_default=None, cs_unit="",
   q_desc="Momentum/volatility ratio (1=min, 4=top 1/3, 10=top 1%)",
   q_desc_es="Ratio momentum/volatilidad (1=min, 4=top 1/3, 10=top 1%)")

_a("CHBDC", AlertType.CHANNEL_BREAKDOWN_CONFIRMED,
   "Channel breakdown (confirmed)", "Quiebre de canal (confirmado)", "consol", "-", 1, True, 0,
   "Volume confirmed channel breakdown. Transitions from consolidating to running. "
   "~15 min timeframe. Quality = momentum/vol ratio. 5.0+ = briskly.",
   "Quiebre de canal confirmado por volumen. Transicion de consolidacion a running. "
   "~15 min. Quality = ratio momentum/vol. 5.0+ = briskly.",
   flip="CHBOC", parent="CHBOC", keywords=["volume confirmed"],
   cs_type=CustomSettingType.QUALITY_RATIO,
   cs_label="Min quality", cs_label_es="Min calidad",
   cs_hint="1.0 = all alerts. 5.0+ = briskly. 4 = top 1/3. 10 = top 1%.",
   cs_default=None, cs_unit="",
   q_desc="Momentum/volatility ratio",
   q_desc_es="Ratio momentum/volatilidad")


# ──────────────────────────────────────────────────────────────────────
# FIXED-TIMEFRAME CONSOLIDATION BREAKOUT / BREAKDOWN (Tier 1)
# TI: Traditional candlestick analysis, fixed N-min timeframe (41 periods).
# Single print can trigger. Quality = $ above/below channel.
# No volume confirmation. Additional alerts as price continues.
# ──────────────────────────────────────────────────────────────────────

_a("CBO5", AlertType.CONSOL_BREAKOUT_5M,
   "5 minute consolidation breakout", "Ruptura de consolidacion 5 min", "consol", "+", 1, True, 0,
   "Price broke above 5-min consolidation channel. Traditional candlestick analysis, "
   "single print can trigger. Quality = $ above channel top. Additional alerts as price continues.",
   "Precio rompio por encima del canal de consolidacion de 5 min. Analisis de velas tradicional, "
   "un solo print puede disparar. Quality = $ sobre techo del canal.",
   flip="CBD5", keywords=["fixed time frame", "single print"],
   cs_type=CustomSettingType.MIN_CENTS,
   cs_label="Min $ above channel", cs_label_es="Min $ sobre canal",
   cs_hint="Dollar distance above the top of the consolidation pattern.",
   cs_default=None, cs_unit="$",
   q_desc="Dollar value above channel top",
   q_desc_es="Valor en dolares sobre techo del canal")

_a("CBD5", AlertType.CONSOL_BREAKDOWN_5M,
   "5 minute consolidation breakdown", "Quiebre de consolidacion 5 min", "consol", "-", 1, True, 0,
   "Price broke below 5-min consolidation channel. Traditional candlestick analysis, "
   "single print can trigger. Quality = $ below channel bottom.",
   "Precio rompio por debajo del canal de consolidacion de 5 min. Analisis de velas tradicional, "
   "un solo print puede disparar. Quality = $ bajo piso del canal.",
   flip="CBO5", parent="CBO5", keywords=["fixed time frame", "single print"],
   cs_type=CustomSettingType.MIN_CENTS,
   cs_label="Min $ below channel", cs_label_es="Min $ bajo canal",
   cs_hint="Dollar distance below the bottom of the consolidation pattern.",
   cs_default=None, cs_unit="$",
   q_desc="Dollar value below channel bottom",
   q_desc_es="Valor en dolares bajo piso del canal")

_a("CBO10", AlertType.CONSOL_BREAKOUT_10M,
   "10 minute consolidation breakout", "Ruptura de consolidacion 10 min", "consol", "+", 1, True, 0,
   "Price broke above 10-min consolidation channel. Traditional candlestick analysis, "
   "single print can trigger. Quality = $ above channel top.",
   "Precio rompio por encima del canal de consolidacion de 10 min. Analisis de velas tradicional, "
   "un solo print puede disparar. Quality = $ sobre techo del canal.",
   flip="CBD10", keywords=["fixed time frame", "single print"],
   cs_type=CustomSettingType.MIN_CENTS,
   cs_label="Min $ above channel", cs_label_es="Min $ sobre canal",
   cs_hint="Dollar distance above the top of the consolidation pattern.",
   cs_default=None, cs_unit="$",
   q_desc="Dollar value above channel top",
   q_desc_es="Valor en dolares sobre techo del canal")

_a("CBD10", AlertType.CONSOL_BREAKDOWN_10M,
   "10 minute consolidation breakdown", "Quiebre de consolidacion 10 min", "consol", "-", 1, True, 0,
   "Price broke below 10-min consolidation channel. Traditional candlestick analysis, "
   "single print can trigger. Quality = $ below channel bottom.",
   "Precio rompio por debajo del canal de consolidacion de 10 min. Analisis de velas tradicional, "
   "un solo print puede disparar. Quality = $ bajo piso del canal.",
   flip="CBO10", parent="CBO10", keywords=["fixed time frame", "single print"],
   cs_type=CustomSettingType.MIN_CENTS,
   cs_label="Min $ below channel", cs_label_es="Min $ bajo canal",
   cs_hint="Dollar distance below the bottom of the consolidation pattern.",
   cs_default=None, cs_unit="$",
   q_desc="Dollar value below channel bottom",
   q_desc_es="Valor en dolares bajo piso del canal")

_a("CBO15", AlertType.CONSOL_BREAKOUT_15M,
   "15 minute consolidation breakout", "Ruptura de consolidacion 15 min", "consol", "+", 1, True, 0,
   "Price broke above 15-min consolidation channel. Traditional candlestick analysis, "
   "single print can trigger. Quality = $ above channel top.",
   "Precio rompio por encima del canal de consolidacion de 15 min. Analisis de velas tradicional, "
   "un solo print puede disparar. Quality = $ sobre techo del canal.",
   flip="CBD15", keywords=["fixed time frame", "single print"],
   cs_type=CustomSettingType.MIN_CENTS,
   cs_label="Min $ above channel", cs_label_es="Min $ sobre canal",
   cs_hint="Dollar distance above the top of the consolidation pattern.",
   cs_default=None, cs_unit="$",
   q_desc="Dollar value above channel top",
   q_desc_es="Valor en dolares sobre techo del canal")

_a("CBD15", AlertType.CONSOL_BREAKDOWN_15M,
   "15 minute consolidation breakdown", "Quiebre de consolidacion 15 min", "consol", "-", 1, True, 0,
   "Price broke below 15-min consolidation channel. Traditional candlestick analysis, "
   "single print can trigger. Quality = $ below channel bottom.",
   "Precio rompio por debajo del canal de consolidacion de 15 min. Analisis de velas tradicional, "
   "un solo print puede disparar. Quality = $ bajo piso del canal.",
   flip="CBO15", parent="CBO15", keywords=["fixed time frame", "single print"],
   cs_type=CustomSettingType.MIN_CENTS,
   cs_label="Min $ below channel", cs_label_es="Min $ bajo canal",
   cs_hint="Dollar distance below the bottom of the consolidation pattern.",
   cs_default=None, cs_unit="$",
   q_desc="Dollar value below channel bottom",
   q_desc_es="Valor en dolares bajo piso del canal")

_a("CBO30", AlertType.CONSOL_BREAKOUT_30M,
   "30 minute consolidation breakout", "Ruptura de consolidacion 30 min", "consol", "+", 1, True, 0,
   "Price broke above 30-min consolidation channel. Traditional candlestick analysis, "
   "single print can trigger. Quality = $ above channel top.",
   "Precio rompio por encima del canal de consolidacion de 30 min. Analisis de velas tradicional, "
   "un solo print puede disparar. Quality = $ sobre techo del canal.",
   flip="CBD30", keywords=["fixed time frame", "single print"],
   cs_type=CustomSettingType.MIN_CENTS,
   cs_label="Min $ above channel", cs_label_es="Min $ sobre canal",
   cs_hint="Dollar distance above the top of the consolidation pattern.",
   cs_default=None, cs_unit="$",
   q_desc="Dollar value above channel top",
   q_desc_es="Valor en dolares sobre techo del canal")

_a("CBD30", AlertType.CONSOL_BREAKDOWN_30M,
   "30 minute consolidation breakdown", "Quiebre de consolidacion 30 min", "consol", "-", 1, True, 0,
   "Price broke below 30-min consolidation channel. Traditional candlestick analysis, "
   "single print can trigger. Quality = $ below channel bottom.",
   "Precio rompio por debajo del canal de consolidacion de 30 min. Analisis de velas tradicional, "
   "un solo print puede disparar. Quality = $ bajo piso del canal.",
   flip="CBO30", parent="CBO30", keywords=["fixed time frame", "single print"],
   cs_type=CustomSettingType.MIN_CENTS,
   cs_label="Min $ below channel", cs_label_es="Min $ bajo canal",
   cs_hint="Dollar distance below the bottom of the consolidation pattern.",
   cs_default=None, cs_unit="$",
   q_desc="Dollar value below channel bottom",
   q_desc_es="Valor en dolares bajo piso del canal")


# ──────────────────────────────────────────────────────────────────────
# GEOMETRIC PATTERNS (Tier 1)
# TI: Volume-confirmed turning points forming geometric shapes.
# Broadening = inverted triangle (higher highs + lower lows, 5+ points).
# Quality = hours of the pattern. Custom setting = min hours.
# ──────────────────────────────────────────────────────────────────────

_a("GBBOT", AlertType.BROADENING_BOTTOM,
   "Broadening bottom", "Fondo ensanchado", "geometric", "+", 1, True, 0,
   "Broadening (inverted triangle) pattern: series of higher highs and lower lows. "
   "Price touched the bottom and turned back up. Requires 5+ volume-confirmed "
   "turning points. Quality = hours of the pattern.",
   "Patron de ensanchamiento (triangulo invertido): serie de maximos mas altos y "
   "minimos mas bajos. Precio toco el fondo y subio. Requiere 5+ puntos de giro "
   "confirmados por volumen. Quality = horas del patron.",
   flip="GBTOP", keywords=["geometric pattern", "volume confirmed"],
   cs_type=CustomSettingType.MIN_HOURS,
   cs_label="Min hours", cs_label_es="Min horas",
   cs_hint="Hours of the pattern. 6.5 = full trading day. "
   "7.5 = full day including pre/post market. "
   "Volume-weighted: high volume stocks satisfy faster.",
   cs_default=None, cs_unit="hours",
   q_desc="Hours since the pattern was established",
   q_desc_es="Horas desde que se establecio el patron")

_a("GBTOP", AlertType.BROADENING_TOP,
   "Broadening top", "Techo ensanchado", "geometric", "-", 1, True, 0,
   "Broadening (inverted triangle) pattern: series of higher highs and lower lows. "
   "Price touched the top and turned back down. Requires 5+ volume-confirmed "
   "turning points. Quality = hours of the pattern.",
   "Patron de ensanchamiento (triangulo invertido): serie de maximos mas altos y "
   "minimos mas bajos. Precio toco el techo y bajo. Requiere 5+ puntos de giro "
   "confirmados por volumen. Quality = horas del patron.",
   flip="GBBOT", parent="GBBOT", keywords=["geometric pattern", "volume confirmed"],
   cs_type=CustomSettingType.MIN_HOURS,
   cs_label="Min hours", cs_label_es="Min horas",
   cs_hint="Hours of the pattern. 6.5 = full trading day. "
   "7.5 = full day including pre/post market. "
   "Volume-weighted: high volume stocks satisfy faster.",
   cs_default=None, cs_unit="hours",
   q_desc="Hours since the pattern was established",
   q_desc_es="Horas desde que se establecio el patron")

_a("GTBOT", AlertType.TRIANGLE_BOTTOM,
   "Triangle bottom", "Triangulo inferior", "geometric", "+", 1, True, 0,
   "Standard triangle pattern: series of lower highs and higher lows (converging range). "
   "Requires 5+ volume-confirmed turning points. Called 'bottom' when first point is a low "
   "and first line goes up. With exactly 5 points, ends going up. "
   "Additional points strengthen the pattern; name is based on the initial (strongest) trend.",
   "Patron triangulo estandar: serie de maximos decrecientes y minimos crecientes (rango convergente). "
   "Requiere 5+ puntos de giro confirmados por volumen. Se llama 'inferior' cuando el primer punto "
   "es un minimo y la primera linea sube. Con exactamente 5 puntos, termina subiendo. "
   "Puntos adicionales fortalecen el patron; el nombre se basa en la tendencia inicial (la mas fuerte).",
   flip="GTTOP", keywords=["geometric pattern", "volume confirmed"],
   cs_type=CustomSettingType.MIN_HOURS,
   cs_label="Min hours", cs_label_es="Min horas",
   cs_hint="Hours of the pattern. 6.5 = full trading day. "
   "7.5 = full day including pre/post market. "
   "Volume-weighted: high volume stocks satisfy faster.",
   cs_default=None, cs_unit="hours",
   q_desc="Hours since the pattern was established",
   q_desc_es="Horas desde que se establecio el patron")

_a("GTTOP", AlertType.TRIANGLE_TOP,
   "Triangle top", "Triangulo superior", "geometric", "-", 1, True, 0,
   "Standard triangle pattern: series of lower highs and higher lows (converging range). "
   "Requires 5+ volume-confirmed turning points. Called 'top' when first point is a high "
   "and first line goes down. With exactly 5 points, ends going down. "
   "Additional points strengthen the pattern; name is based on the initial (strongest) trend.",
   "Patron triangulo estandar: serie de maximos decrecientes y minimos crecientes (rango convergente). "
   "Requiere 5+ puntos de giro confirmados por volumen. Se llama 'superior' cuando el primer punto "
   "es un maximo y la primera linea baja. Con exactamente 5 puntos, termina bajando. "
   "Puntos adicionales fortalecen el patron; el nombre se basa en la tendencia inicial (la mas fuerte).",
   flip="GTBOT", parent="GTBOT", keywords=["geometric pattern", "volume confirmed"],
   cs_type=CustomSettingType.MIN_HOURS,
   cs_label="Min hours", cs_label_es="Min horas",
   cs_hint="Hours of the pattern. 6.5 = full trading day. "
   "7.5 = full day including pre/post market. "
   "Volume-weighted: high volume stocks satisfy faster.",
   cs_default=None, cs_unit="hours",
   q_desc="Hours since the pattern was established",
   q_desc_es="Horas desde que se establecio el patron")

_a("GRBOT", AlertType.RECTANGLE_BOTTOM,
   "Rectangle bottom", "Rectangulo inferior", "geometric", "+", 1, True, 0,
   "Rectangle pattern: series of highs at approximately the same price and lows at "
   "approximately the same price. Requires 5+ turning points. Called 'bottom' when "
   "last turning point is a low (price going up). Different algorithm from consolidation: "
   "depends on specific edge prices, not volatility. Confirms the channel is holding.",
   "Patron rectangulo: serie de maximos a aproximadamente el mismo precio y minimos a "
   "aproximadamente el mismo precio. Requiere 5+ puntos de giro. Se llama 'inferior' cuando "
   "el ultimo punto de giro es un minimo (precio subiendo). Algoritmo diferente de consolidacion: "
   "depende de precios especificos en los bordes, no volatilidad. Confirma que el canal se mantiene.",
   flip="GRTOP", keywords=["geometric pattern", "volume confirmed"],
   cs_type=CustomSettingType.MIN_HOURS,
   cs_label="Min hours", cs_label_es="Min horas",
   cs_hint="Hours of the pattern. 6.5 = full trading day. "
   "7.5 = full day including pre/post market. "
   "Volume-weighted: high volume stocks satisfy faster.",
   cs_default=None, cs_unit="hours",
   q_desc="Hours since the pattern was established",
   q_desc_es="Horas desde que se establecio el patron")

_a("GRTOP", AlertType.RECTANGLE_TOP,
   "Rectangle top", "Rectangulo superior", "geometric", "-", 1, True, 0,
   "Rectangle pattern: series of highs at approximately the same price and lows at "
   "approximately the same price. Requires 5+ turning points. Called 'top' when "
   "last turning point is a high (price going down). Different algorithm from consolidation: "
   "depends on specific edge prices, not volatility. Confirms the channel is holding.",
   "Patron rectangulo: serie de maximos a aproximadamente el mismo precio y minimos a "
   "aproximadamente el mismo precio. Requiere 5+ puntos de giro. Se llama 'superior' cuando "
   "el ultimo punto de giro es un maximo (precio bajando). Algoritmo diferente de consolidacion: "
   "depende de precios especificos en los bordes, no volatilidad. Confirma que el canal se mantiene.",
   flip="GRBOT", parent="GRBOT", keywords=["geometric pattern", "volume confirmed"],
   cs_type=CustomSettingType.MIN_HOURS,
   cs_label="Min hours", cs_label_es="Min horas",
   cs_hint="Hours of the pattern. 6.5 = full trading day. "
   "7.5 = full day including pre/post market. "
   "Volume-weighted: high volume stocks satisfy faster.",
   cs_default=None, cs_unit="hours",
   q_desc="Hours since the pattern was established",
   q_desc_es="Horas desde que se establecio el patron")

_a("GDBOT", AlertType.DOUBLE_BOTTOM,
   "Double bottom", "Doble suelo", "geometric", "+", 1, True, 0,
   "At least two lows at approximately the same price level with significant time and "
   "volume between them. Can also report triple/quadruple bottoms (description states count). "
   "Less time/volume required between individual lows in triple+ as long as first and last "
   "are sufficiently far apart.",
   "Al menos dos minimos a aproximadamente el mismo precio con tiempo y volumen significativo "
   "entre ellos. Tambien reporta triple/cuadruple suelos (la descripcion indica la cantidad). "
   "Menos tiempo/volumen requerido entre minimos individuales en triple+ siempre que el primero "
   "y el ultimo esten suficientemente separados.",
   flip="GDTOP", keywords=["geometric pattern", "volume confirmed"],
   cs_type=CustomSettingType.MIN_HOURS,
   cs_label="Min hours", cs_label_es="Min horas",
   cs_hint="Hours of the pattern. 6.5 = full trading day. "
   "7.5 = full day including pre/post market. "
   "Volume-weighted: high volume stocks satisfy faster.",
   cs_default=None, cs_unit="hours",
   q_desc="Hours since the pattern was established",
   q_desc_es="Horas desde que se establecio el patron")

_a("GDTOP", AlertType.DOUBLE_TOP,
   "Double top", "Doble techo", "geometric", "-", 1, True, 0,
   "At least two highs at approximately the same price level with significant time and "
   "volume between them. Can also report triple/quadruple tops (description states count). "
   "Less time/volume required between individual highs in triple+ as long as first and last "
   "are sufficiently far apart.",
   "Al menos dos maximos a aproximadamente el mismo precio con tiempo y volumen significativo "
   "entre ellos. Tambien reporta triple/cuadruple techos (la descripcion indica la cantidad). "
   "Menos tiempo/volumen requerido entre maximos individuales en triple+ siempre que el primero "
   "y el ultimo esten suficientemente separados.",
   flip="GDBOT", parent="GDBOT", keywords=["geometric pattern", "volume confirmed"],
   cs_type=CustomSettingType.MIN_HOURS,
   cs_label="Min hours", cs_label_es="Min horas",
   cs_hint="Hours of the pattern. 6.5 = full trading day. "
   "7.5 = full day including pre/post market. "
   "Volume-weighted: high volume stocks satisfy faster.",
   cs_default=None, cs_unit="hours",
   q_desc="Hours since the pattern was established",
   q_desc_es="Horas desde que se establecio el patron")

_a("GHASI", AlertType.HEAD_AND_SHOULDERS_INV,
   "Inverted head and shoulders", "Hombro cabeza hombro invertido", "geometric", "+", 1, True, 0,
   "Exactly 5 turning points: 1st=low (left shoulder), 2nd=high, 3rd=low (head, must be "
   "lowest of all 5), 4th=high (~same as 2nd), 5th=low (~same as 1st). "
   "'Approximately same price' depends on pattern size and stock volatility. "
   "Reversal pattern (bullish).",
   "Exactamente 5 puntos de giro: 1ro=minimo (hombro izquierdo), 2do=maximo, 3ro=minimo "
   "(cabeza, debe ser el mas bajo de los 5), 4to=maximo (~igual al 2do), 5to=minimo (~igual al 1ro). "
   "'Aproximadamente el mismo precio' depende del tamano del patron y la volatilidad. "
   "Patron de reversion (alcista).",
   flip="GHAS", keywords=["geometric pattern", "volume confirmed"],
   cs_type=CustomSettingType.MIN_HOURS,
   cs_label="Min hours", cs_label_es="Min horas",
   cs_hint="Hours of the pattern. 6.5 = full trading day. "
   "7.5 = full day including pre/post market. "
   "Volume-weighted: high volume stocks satisfy faster.",
   cs_default=None, cs_unit="hours",
   q_desc="Hours since the pattern was established",
   q_desc_es="Horas desde que se establecio el patron")

_a("GHAS", AlertType.HEAD_AND_SHOULDERS,
   "Head and shoulders", "Hombro cabeza hombro", "geometric", "-", 1, True, 0,
   "Exactly 5 turning points: 1st=high (left shoulder), 2nd=low, 3rd=high (head, must be "
   "highest of all 5), 4th=low (~same as 2nd), 5th=high (~same as 1st). "
   "'Approximately same price' depends on pattern size and stock volatility. "
   "Reversal pattern (bearish).",
   "Exactamente 5 puntos de giro: 1ro=maximo (hombro izquierdo), 2do=minimo, 3ro=maximo "
   "(cabeza, debe ser el mas alto de los 5), 4to=minimo (~igual al 2do), 5to=maximo (~igual al 1ro). "
   "'Aproximadamente el mismo precio' depende del tamano del patron y la volatilidad. "
   "Patron de reversion (bajista).",
   flip="GHASI", parent="GHASI", keywords=["geometric pattern", "volume confirmed"],
   cs_type=CustomSettingType.MIN_HOURS,
   cs_label="Min hours", cs_label_es="Min horas",
   cs_hint="Hours of the pattern. 6.5 = full trading day. "
   "7.5 = full day including pre/post market. "
   "Volume-weighted: high volume stocks satisfy faster.",
   cs_default=None, cs_unit="hours",
   q_desc="Hours since the pattern was established",
   q_desc_es="Horas desde que se establecio el patron")


# ──────────────────────────────────────────────────────────────────────
# MULTI-TIMEFRAME INDICATORS (Tier 2 — no custom setting, binary cross)
# ──────────────────────────────────────────────────────────────────────

# ECAY5/ECBY5 moved to SMA CROSS ALERTS section below

# MDAS5/MDBS5/MDAZ5/MDBZ5 moved to MACD CROSS ALERTS section below

# SC20_5/SC80_5 moved to STOCHASTIC CROSS ALERTS section below


# ──────────────────────────────────────────────────────────────────────
# N-MINUTE HIGH/LOW (Tier 2 — traditional candlestick, no custom setting)
# ──────────────────────────────────────────────────────────────────────

_a("IDH5", AlertType.INTRADAY_HIGH_5M,
   "5 minute high", "Máximo 5 minutos", "candle", "+", 2, True, 0,
   "New intraday high on 5-minute candlestick chart. Current candle's high "
   "exceeds previous candle's high. Strictly price and time, no volume filtering.",
   "Nuevo máximo intradiario en gráfico de velas de 5 minutos. El máximo de la "
   "vela actual supera el máximo de la vela anterior. Solo precio y tiempo.",
   flip="IDL5", keywords=["fixed time frame", "candlestick"])

_a("IDL5", AlertType.INTRADAY_LOW_5M,
   "5 minute low", "Mínimo 5 minutos", "candle", "-", 2, True, 0,
   "New intraday low on 5-minute candlestick chart. Current candle's low "
   "goes below previous candle's low. Strictly price and time, no volume filtering.",
   "Nuevo mínimo intradiario en gráfico de velas de 5 minutos. El mínimo de la "
   "vela actual cae bajo el mínimo de la vela anterior. Solo precio y tiempo.",
   flip="IDH5", parent="IDH5", keywords=["fixed time frame", "candlestick"])

_a("IDH10", AlertType.INTRADAY_HIGH_10M,
   "10 minute high", "Máximo 10 minutos", "candle", "+", 2, True, 0,
   "New intraday high on 10-minute candlestick chart. Current candle's high "
   "exceeds previous candle's high. Strictly price and time.",
   "Nuevo máximo intradiario en gráfico de velas de 10 minutos. El máximo de la "
   "vela actual supera el máximo de la vela anterior. Solo precio y tiempo.",
   flip="IDL10", keywords=["fixed time frame", "candlestick"])

_a("IDL10", AlertType.INTRADAY_LOW_10M,
   "10 minute low", "Mínimo 10 minutos", "candle", "-", 2, True, 0,
   "New intraday low on 10-minute candlestick chart. Current candle's low "
   "goes below previous candle's low. Strictly price and time.",
   "Nuevo mínimo intradiario en gráfico de velas de 10 minutos. El mínimo de la "
   "vela actual cae bajo el mínimo de la vela anterior. Solo precio y tiempo.",
   flip="IDH10", parent="IDH10", keywords=["fixed time frame", "candlestick"])

_a("IDH15", AlertType.INTRADAY_HIGH_15M,
   "15 minute high", "Máximo 15 minutos", "candle", "+", 2, True, 0,
   "New intraday high on 15-minute candlestick chart. Current candle's high "
   "exceeds previous candle's high. Strictly price and time.",
   "Nuevo máximo intradiario en gráfico de velas de 15 minutos. El máximo de la "
   "vela actual supera el máximo de la vela anterior. Solo precio y tiempo.",
   flip="IDL15", keywords=["fixed time frame", "candlestick"])

_a("IDL15", AlertType.INTRADAY_LOW_15M,
   "15 minute low", "Mínimo 15 minutos", "candle", "-", 2, True, 0,
   "New intraday low on 15-minute candlestick chart. Current candle's low "
   "goes below previous candle's low. Strictly price and time.",
   "Nuevo mínimo intradiario en gráfico de velas de 15 minutos. El mínimo de la "
   "vela actual cae bajo el mínimo de la vela anterior. Solo precio y tiempo.",
   flip="IDH15", parent="IDH15", keywords=["fixed time frame", "candlestick"])

_a("IDH30", AlertType.INTRADAY_HIGH_30M,
   "30 minute high", "Máximo 30 minutos", "candle", "+", 2, True, 0,
   "New intraday high on 30-minute candlestick chart. Current candle's high "
   "exceeds previous candle's high. Strictly price and time.",
   "Nuevo máximo intradiario en gráfico de velas de 30 minutos. El máximo de la "
   "vela actual supera el máximo de la vela anterior. Solo precio y tiempo.",
   flip="IDL30", keywords=["fixed time frame", "candlestick"])

_a("IDL30", AlertType.INTRADAY_LOW_30M,
   "30 minute low", "Mínimo 30 minutos", "candle", "-", 2, True, 0,
   "New intraday low on 30-minute candlestick chart. Current candle's low "
   "goes below previous candle's low. Strictly price and time.",
   "Nuevo mínimo intradiario en gráfico de velas de 30 minutos. El mínimo de la "
   "vela actual cae bajo el mínimo de la vela anterior. Solo precio y tiempo.",
   flip="IDH30", parent="IDH30", keywords=["fixed time frame", "candlestick"])

_a("IDH60", AlertType.INTRADAY_HIGH_60M,
   "60 minute high", "Máximo 60 minutos", "candle", "+", 2, True, 0,
   "New intraday high on 60-minute candlestick chart. Current candle's high "
   "exceeds previous candle's high. Strictly price and time.",
   "Nuevo máximo intradiario en gráfico de velas de 60 minutos. El máximo de la "
   "vela actual supera el máximo de la vela anterior. Solo precio y tiempo.",
   flip="IDL60", keywords=["fixed time frame", "candlestick"])

_a("IDL60", AlertType.INTRADAY_LOW_60M,
   "60 minute low", "Mínimo 60 minutos", "candle", "-", 2, True, 0,
   "New intraday low on 60-minute candlestick chart. Current candle's low "
   "goes below previous candle's low. Strictly price and time.",
   "Nuevo mínimo intradiario en gráfico de velas de 60 minutos. El mínimo de la "
   "vela actual cae bajo el mínimo de la vela anterior. Solo precio y tiempo.",
   flip="IDH60", parent="IDH60", keywords=["fixed time frame", "candlestick"])


# ──────────────────────────────────────────────────────────────────────
# TRAILING STOPS
# TI: Reports when price pulls back from a local high/low.
# % variants: initial trigger at 0.5%, re-fire every 0.25%.
# Volatility variants: initial trigger at 1 bar (15-min vol), re-fire every 0.5 bar.
# Single print can serve as turning point (no volume confirmation needed).
# Custom setting = period multiplier (2 = alerts at 2x, 4x, 6x...).
# Quality = % move from turning point (TSPU/TSPD) or bars from turning point (TSSU/TSSD).
# ──────────────────────────────────────────────────────────────────────

_a("TSPU", AlertType.TRAILING_STOP_PCT_UP,
   "Trailing stop, % up", "Trailing stop, % arriba", "trailing", "+", 1, True, 0,
   "Reports when price moves up from a local low. First alert at 0.5% from low, "
   "then every additional 0.25%. Any single print can be the turning point. "
   "Similar to pullbacks but shorter timeframe and more frequent. "
   "Custom setting multiplies the period (2 = alerts at 2%, 4%, 6%...).",
   "Reporta cuando el precio sube desde un minimo local. Primera alerta al 0.5% del minimo, "
   "luego cada 0.25% adicional. Cualquier print puede ser el punto de giro. "
   "Similar a pullbacks pero en timeframe mas corto y mas frecuente. "
   "Custom setting multiplica el periodo (2 = alertas al 2%, 4%, 6%...).",
   flip="TSPD", keywords=[],
   cs_type=CustomSettingType.MIN_PERCENT,
   cs_label="Period multiplier", cs_label_es="Multiplicador periodo",
   cs_hint="Multiplies the alert period. 2 = alerts at 2%, 4%, 6%. "
   "0.33 = alerts every 1/3%. Leave blank for default (0.5% then 0.25%).",
   cs_default=None, cs_unit="%",
   q_desc="% move up from the local low",
   q_desc_es="% de subida desde el minimo local")

_a("TSPD", AlertType.TRAILING_STOP_PCT_DOWN,
   "Trailing stop, % down", "Trailing stop, % abajo", "trailing", "-", 1, True, 0,
   "Reports when price moves down from a local high. First alert at 0.5% from high, "
   "then every additional 0.25%. Any single print can be the turning point. "
   "Similar to pullbacks but shorter timeframe and more frequent. "
   "Custom setting multiplies the period (2 = alerts at 2%, 4%, 6%...).",
   "Reporta cuando el precio baja desde un maximo local. Primera alerta al 0.5% del maximo, "
   "luego cada 0.25% adicional. Cualquier print puede ser el punto de giro. "
   "Similar a pullbacks pero en timeframe mas corto y mas frecuente. "
   "Custom setting multiplica el periodo (2 = alertas al 2%, 4%, 6%...).",
   flip="TSPU", parent="TSPU", keywords=[],
   cs_type=CustomSettingType.MIN_PERCENT,
   cs_label="Period multiplier", cs_label_es="Multiplicador periodo",
   cs_hint="Multiplies the alert period. 2 = alerts at 2%, 4%, 6%. "
   "0.33 = alerts every 1/3%. Leave blank for default (0.5% then 0.25%).",
   cs_default=None, cs_unit="%",
   q_desc="% move down from the local high",
   q_desc_es="% de bajada desde el maximo local")

_a("TSSU", AlertType.TRAILING_STOP_VOL_UP,
   "Trailing stop, volatility up", "Trailing stop, volatilidad arriba",
   "trailing", "+", 1, True, 0,
   "Like trailing stop % up but scaled by volatility. One 'bar' = typical move in a "
   "15-min bar. First alert at 1 bar from low, then every 0.5 bar. "
   "Volatile stocks need bigger moves to trigger. Values updated nightly. "
   "Custom setting multiplies the period (2 = alerts at 2 bars, 4 bars...).",
   "Como trailing stop % arriba pero escalado por volatilidad. Un 'bar' = movimiento tipico "
   "en barra de 15 min. Primera alerta a 1 bar del minimo, luego cada 0.5 bar. "
   "Acciones volatiles necesitan movimientos mayores. Valores actualizados cada noche. "
   "Custom setting multiplica el periodo (2 = alertas a 2 bars, 4 bars...).",
   flip="TSSD", keywords=[],
   cs_type=CustomSettingType.VOLUME_RATIO,
   cs_label="Period multiplier", cs_label_es="Multiplicador periodo",
   cs_hint="Multiplies the alert period. 2 = alerts at 2x, 4x, 6x volatility bars. "
   "Leave blank for default (1 bar then 0.5 bar).",
   cs_default=None, cs_unit="x",
   q_desc="Volatility bars moved up from the local low",
   q_desc_es="Barras de volatilidad subidas desde el minimo local")

_a("TSSD", AlertType.TRAILING_STOP_VOL_DOWN,
   "Trailing stop, volatility down", "Trailing stop, volatilidad abajo",
   "trailing", "-", 1, True, 0,
   "Like trailing stop % down but scaled by volatility. One 'bar' = typical move in a "
   "15-min bar. First alert at 1 bar from high, then every 0.5 bar. "
   "Volatile stocks need bigger moves to trigger. Values updated nightly. "
   "Custom setting multiplies the period (2 = alerts at 2 bars, 4 bars...).",
   "Como trailing stop % abajo pero escalado por volatilidad. Un 'bar' = movimiento tipico "
   "en barra de 15 min. Primera alerta a 1 bar del maximo, luego cada 0.5 bar. "
   "Acciones volatiles necesitan movimientos mayores. Valores actualizados cada noche. "
   "Custom setting multiplica el periodo (2 = alertas a 2 bars, 4 bars...).",
   flip="TSSU", parent="TSSU", keywords=[],
   cs_type=CustomSettingType.VOLUME_RATIO,
   cs_label="Period multiplier", cs_label_es="Multiplicador periodo",
   cs_hint="Multiplies the alert period. 2 = alerts at 2x, 4x, 6x volatility bars. "
   "Leave blank for default (1 bar then 0.5 bar).",
   cs_default=None, cs_unit="x",
   q_desc="Volatility bars moved down from the local high",
   q_desc_es="Barras de volatilidad bajadas desde el maximo local")


# ──────────────────────────────────────────────────────────────────────
# FIBONACCI RETRACEMENTS
# TI: Three-point patterns with decreasing volume confirmation:
#   Point 1 (far left): strong volume-confirmed pivot (like geometric patterns).
#   Point 2 (middle):   support/resistance level, moderate confirmation.
#   Point 3 (final):    single print crossing the Fibonacci level triggers alert.
# After alert, trend is monitored; if most prints don't confirm, alert resets.
# Quality = hours of the pattern (volume-weighted for pre/post market).
# Custom setting = min hours.
# Buy signal = price retraces DOWN through the level (reversal, bullish).
# Sell signal = price retraces UP through the level (reversal, bearish).
# ──────────────────────────────────────────────────────────────────────

_FIB_CS_HINT = ("Hours of the pattern. 6.5 = full trading day. "
    "7.5 = full day including pre/post market. "
    "Volume-weighted: high volume stocks satisfy faster.")

_a("FU38", AlertType.FIB_BUY_38,
   "Fibonacci 38% buy signal", "Fibonacci 38% senal compra",
   "fibonacci", "+", 1, True, 0,
   "Price retraces 38% from the high of its daily range. Three-point pattern: "
   "volume-confirmed pivot (left), support/resistance (middle), single print crossing "
   "the 38% Fibonacci level (right). Reversal signal (bullish). "
   "Trend monitored after alert; resets if not confirmed.",
   "El precio retrocede 38% desde el maximo del rango diario. Patron de tres puntos: "
   "pivot confirmado por volumen (izq), soporte/resistencia (medio), un solo print "
   "cruzando el nivel Fibonacci 38% (derecha). Senal de reversion (alcista). "
   "Se monitorea la tendencia; se resetea si no se confirma.",
   flip="FD38", keywords=["fibonacci", "single print", "support and resistance"],
   cs_type=CustomSettingType.MIN_HOURS,
   cs_label="Min hours", cs_label_es="Min horas",
   cs_hint=_FIB_CS_HINT,
   cs_default=None, cs_unit="hours",
   q_desc="Hours since the pattern was established",
   q_desc_es="Horas desde que se establecio el patron")

_a("FD38", AlertType.FIB_SELL_38,
   "Fibonacci 38% sell signal", "Fibonacci 38% senal venta",
   "fibonacci", "-", 1, True, 0,
   "Price retraces 38% from the low of its daily range. Three-point pattern: "
   "volume-confirmed pivot (left), support/resistance (middle), single print crossing "
   "the 38% Fibonacci level (right). Reversal signal (bearish). "
   "Trend monitored after alert; resets if not confirmed.",
   "El precio retrocede 38% desde el minimo del rango diario. Patron de tres puntos: "
   "pivot confirmado por volumen (izq), soporte/resistencia (medio), un solo print "
   "cruzando el nivel Fibonacci 38% (derecha). Senal de reversion (bajista). "
   "Se monitorea la tendencia; se resetea si no se confirma.",
   flip="FU38", parent="FU38", keywords=["fibonacci", "single print", "support and resistance"],
   cs_type=CustomSettingType.MIN_HOURS,
   cs_label="Min hours", cs_label_es="Min horas",
   cs_hint=_FIB_CS_HINT,
   cs_default=None, cs_unit="hours",
   q_desc="Hours since the pattern was established",
   q_desc_es="Horas desde que se establecio el patron")

_a("FU50", AlertType.FIB_BUY_50,
   "Fibonacci 50% buy signal", "Fibonacci 50% senal compra",
   "fibonacci", "+", 1, True, 0,
   "Price retraces 50% from the high of its daily range. Three-point pattern: "
   "volume-confirmed pivot (left), support/resistance (middle), single print crossing "
   "the 50% Fibonacci level (right). Reversal signal (bullish). "
   "Trend monitored after alert; resets if not confirmed.",
   "El precio retrocede 50% desde el maximo del rango diario. Patron de tres puntos: "
   "pivot confirmado por volumen (izq), soporte/resistencia (medio), un solo print "
   "cruzando el nivel Fibonacci 50% (derecha). Senal de reversion (alcista). "
   "Se monitorea la tendencia; se resetea si no se confirma.",
   flip="FD50", keywords=["fibonacci", "single print", "support and resistance"],
   cs_type=CustomSettingType.MIN_HOURS,
   cs_label="Min hours", cs_label_es="Min horas",
   cs_hint=_FIB_CS_HINT,
   cs_default=None, cs_unit="hours",
   q_desc="Hours since the pattern was established",
   q_desc_es="Horas desde que se establecio el patron")

_a("FD50", AlertType.FIB_SELL_50,
   "Fibonacci 50% sell signal", "Fibonacci 50% senal venta",
   "fibonacci", "-", 1, True, 0,
   "Price retraces 50% from the low of its daily range. Three-point pattern: "
   "volume-confirmed pivot (left), support/resistance (middle), single print crossing "
   "the 50% Fibonacci level (right). Reversal signal (bearish). "
   "Trend monitored after alert; resets if not confirmed.",
   "El precio retrocede 50% desde el minimo del rango diario. Patron de tres puntos: "
   "pivot confirmado por volumen (izq), soporte/resistencia (medio), un solo print "
   "cruzando el nivel Fibonacci 50% (derecha). Senal de reversion (bajista). "
   "Se monitorea la tendencia; se resetea si no se confirma.",
   flip="FU50", parent="FU50", keywords=["fibonacci", "single print", "support and resistance"],
   cs_type=CustomSettingType.MIN_HOURS,
   cs_label="Min hours", cs_label_es="Min horas",
   cs_hint=_FIB_CS_HINT,
   cs_default=None, cs_unit="hours",
   q_desc="Hours since the pattern was established",
   q_desc_es="Horas desde que se establecio el patron")

_a("FU62", AlertType.FIB_BUY_62,
   "Fibonacci 62% buy signal", "Fibonacci 62% senal compra",
   "fibonacci", "+", 1, True, 0,
   "Price retraces 62% from the high of its daily range. Three-point pattern: "
   "volume-confirmed pivot (left), support/resistance (middle), single print crossing "
   "the 62% Fibonacci level (right). Reversal signal (bullish). "
   "Trend monitored after alert; resets if not confirmed.",
   "El precio retrocede 62% desde el maximo del rango diario. Patron de tres puntos: "
   "pivot confirmado por volumen (izq), soporte/resistencia (medio), un solo print "
   "cruzando el nivel Fibonacci 62% (derecha). Senal de reversion (alcista). "
   "Se monitorea la tendencia; se resetea si no se confirma.",
   flip="FD62", keywords=["fibonacci", "single print", "support and resistance"],
   cs_type=CustomSettingType.MIN_HOURS,
   cs_label="Min hours", cs_label_es="Min horas",
   cs_hint=_FIB_CS_HINT,
   cs_default=None, cs_unit="hours",
   q_desc="Hours since the pattern was established",
   q_desc_es="Horas desde que se establecio el patron")

_a("FD62", AlertType.FIB_SELL_62,
   "Fibonacci 62% sell signal", "Fibonacci 62% senal venta",
   "fibonacci", "-", 1, True, 0,
   "Price retraces 62% from the low of its daily range. Three-point pattern: "
   "volume-confirmed pivot (left), support/resistance (middle), single print crossing "
   "the 62% Fibonacci level (right). Reversal signal (bearish). "
   "Trend monitored after alert; resets if not confirmed.",
   "El precio retrocede 62% desde el minimo del rango diario. Patron de tres puntos: "
   "pivot confirmado por volumen (izq), soporte/resistencia (medio), un solo print "
   "cruzando el nivel Fibonacci 62% (derecha). Senal de reversion (bajista). "
   "Se monitorea la tendencia; se resetea si no se confirma.",
   flip="FU62", parent="FU62", keywords=["fibonacci", "single print", "support and resistance"],
   cs_type=CustomSettingType.MIN_HOURS,
   cs_label="Min hours", cs_label_es="Min horas",
   cs_hint=_FIB_CS_HINT,
   cs_default=None, cs_unit="hours",
   q_desc="Hours since the pattern was established",
   q_desc_es="Horas desde que se establecio el patron")

_a("FU79", AlertType.FIB_BUY_79,
   "Fibonacci 79% buy signal", "Fibonacci 79% senal compra",
   "fibonacci", "+", 1, True, 0,
   "Price retraces 79% from the high of its daily range. Three-point pattern: "
   "volume-confirmed pivot (left), support/resistance (middle), single print crossing "
   "the 79% Fibonacci level (right). Reversal signal (bullish). "
   "Trend monitored after alert; resets if not confirmed.",
   "El precio retrocede 79% desde el maximo del rango diario. Patron de tres puntos: "
   "pivot confirmado por volumen (izq), soporte/resistencia (medio), un solo print "
   "cruzando el nivel Fibonacci 79% (derecha). Senal de reversion (alcista). "
   "Se monitorea la tendencia; se resetea si no se confirma.",
   flip="FD79", keywords=["fibonacci", "single print", "support and resistance"],
   cs_type=CustomSettingType.MIN_HOURS,
   cs_label="Min hours", cs_label_es="Min horas",
   cs_hint=_FIB_CS_HINT,
   cs_default=None, cs_unit="hours",
   q_desc="Hours since the pattern was established",
   q_desc_es="Horas desde que se establecio el patron")

_a("FD79", AlertType.FIB_SELL_79,
   "Fibonacci 79% sell signal", "Fibonacci 79% senal venta",
   "fibonacci", "-", 1, True, 0,
   "Price retraces 79% from the low of its daily range. Three-point pattern: "
   "volume-confirmed pivot (left), support/resistance (middle), single print crossing "
   "the 79% Fibonacci level (right). Reversal signal (bearish). "
   "Trend monitored after alert; resets if not confirmed.",
   "El precio retrocede 79% desde el minimo del rango diario. Patron de tres puntos: "
   "pivot confirmado por volumen (izq), soporte/resistencia (medio), un solo print "
   "cruzando el nivel Fibonacci 79% (derecha). Senal de reversion (bajista). "
   "Se monitorea la tendencia; se resetea si no se confirma.",
   flip="FU79", parent="FU79", keywords=["fibonacci", "single print", "support and resistance"],
   cs_type=CustomSettingType.MIN_HOURS,
   cs_label="Min hours", cs_label_es="Min horas",
   cs_hint=_FIB_CS_HINT,
   cs_default=None, cs_unit="hours",
   q_desc="Hours since the pattern was established",
   q_desc_es="Horas desde que se establecio el patron")


# ──────────────────────────────────────────────────────────────────────
# LINEAR REGRESSION TRENDS
# ──────────────────────────────────────────────────────────────────────

_LR_CS_HINT = ("Forecast in dollars per share. Only show signals where the "
    "stock is expected to move more than this value.")
_LR_QD = "Dollars per share of room left in the channel"
_LR_QDE = "Dolares por accion de espacio en el canal"

for _tf, _up_t, _dn_t in [
    (5, AlertType.LINREG_UP_5M, AlertType.LINREG_DOWN_5M),
    (15, AlertType.LINREG_UP_15M, AlertType.LINREG_DOWN_15M),
    (30, AlertType.LINREG_UP_30M, AlertType.LINREG_DOWN_30M),
    (90, AlertType.LINREG_UP_90M, AlertType.LINREG_DOWN_90M),
]:
    _code_u = f"PEU{_tf}"
    _code_d = f"PED{_tf}"
    _a(_code_u, _up_t,
       f"{_tf} minute linear regression up trend",
       f"Regresion lineal {_tf} min tendencia alcista",
       "linreg", "+", 1, True, 0,
       f"Short-term momentum crosses upward within the long-term linear regression "
       f"channel on {_tf}-minute bars. Long-term regression defines trend and channel "
       f"width. Short-term shows current momentum.",
       f"Momentum corto plazo cruza al alza dentro del canal de regresion lineal "
       f"largo plazo en barras de {_tf} min.",
       flip=_code_d, keywords=["fixed time frame"],
       cs_type=CustomSettingType.MIN_DOLLARS,
       cs_label="Min $/share", cs_label_es="Min $/accion",
       cs_hint=_LR_CS_HINT, cs_default=None, cs_unit="$",
       q_desc=_LR_QD, q_desc_es=_LR_QDE)
    _a(_code_d, _dn_t,
       f"{_tf} minute linear regression down trend",
       f"Regresion lineal {_tf} min tendencia bajista",
       "linreg", "-", 1, True, 0,
       f"Short-term momentum crosses downward within the long-term linear regression "
       f"channel on {_tf}-minute bars. Long-term regression defines trend and channel "
       f"width. Short-term shows current momentum.",
       f"Momentum corto plazo cruza a la baja dentro del canal de regresion lineal "
       f"largo plazo en barras de {_tf} min.",
       flip=_code_u, parent=_code_u, keywords=["fixed time frame"],
       cs_type=CustomSettingType.MIN_DOLLARS,
       cs_label="Min $/share", cs_label_es="Min $/accion",
       cs_hint=_LR_CS_HINT, cs_default=None, cs_unit="$",
       q_desc=_LR_QD, q_desc_es=_LR_QDE)

del _tf, _up_t, _dn_t, _code_u, _code_d


# ──────────────────────────────────────────────────────────────────────
# SMA THRUST (Upward / Downward)
# TI: 8-period SMA and 20-period SMA both going same direction for
# last 5 consecutive periods. Re-fires at Fibonacci intervals (8, 13, 21...).
# Quality = suddenness (0-100). Flatter the 200-period SMA, closer to 100.
# Custom setting = min suddenness value.
# ──────────────────────────────────────────────────────────────────────

_TH_CS_HINT = ("Suddenness of the move (0-100). Flatter the 200-period SMA, "
    "closer to 100. Most alerts have values above 90. "
    "A value of 0 means the 200 SMA moved from bottom to top of chart.")

for _tf, _up_t, _dn_t in [
    (2, AlertType.SMA_THRUST_UP_2M, AlertType.SMA_THRUST_DOWN_2M),
    (5, AlertType.SMA_THRUST_UP_5M, AlertType.SMA_THRUST_DOWN_5M),
    (15, AlertType.SMA_THRUST_UP_15M, AlertType.SMA_THRUST_DOWN_15M),
]:
    _code_u = f"SMAU{_tf}"
    _code_d = f"SMAD{_tf}"
    _a(_code_u, _up_t,
       f"Upward thrust ({_tf} minute)",
       f"Empuje alcista ({_tf} minutos)",
       "thrust", "+", 1, True, 0,
       f"8-period SMA and 20-period SMA both going up for last 5 consecutive "
       f"{_tf}-minute periods (at least {5 * _tf} minutes of sustained uptrend). "
       f"Re-fires at Fibonacci intervals (8, 13, 21 periods). "
       f"End-of-candle alert.",
       f"SMA de 8 periodos y SMA de 20 periodos ambas subiendo durante los ultimos "
       f"5 periodos consecutivos de {_tf} min (al menos {5 * _tf} min de tendencia alcista). "
       f"Se repite en intervalos Fibonacci (8, 13, 21 periodos).",
       flip=_code_d, keywords=["end of candle", "moving average", "fixed time frame"],
       cs_type=CustomSettingType.MIN_PERCENT,
       cs_label="Min suddenness", cs_label_es="Min brusquedad",
       cs_hint=_TH_CS_HINT, cs_default=None, cs_unit="%",
       q_desc="Suddenness of the move (0-100)",
       q_desc_es="Brusquedad del movimiento (0-100)")
    _a(_code_d, _dn_t,
       f"Downward thrust ({_tf} minute)",
       f"Empuje bajista ({_tf} minutos)",
       "thrust", "-", 1, True, 0,
       f"8-period SMA and 20-period SMA both going down for last 5 consecutive "
       f"{_tf}-minute periods (at least {5 * _tf} minutes of sustained downtrend). "
       f"Re-fires at Fibonacci intervals (8, 13, 21 periods). "
       f"End-of-candle alert.",
       f"SMA de 8 periodos y SMA de 20 periodos ambas bajando durante los ultimos "
       f"5 periodos consecutivos de {_tf} min (al menos {5 * _tf} min de tendencia bajista). "
       f"Se repite en intervalos Fibonacci (8, 13, 21 periodos).",
       flip=_code_u, parent=_code_u,
       keywords=["end of candle", "moving average", "fixed time frame"],
       cs_type=CustomSettingType.MIN_PERCENT,
       cs_label="Min suddenness", cs_label_es="Min brusquedad",
       cs_hint=_TH_CS_HINT, cs_default=None, cs_unit="%",
       q_desc="Suddenness of the move (0-100)",
       q_desc_es="Brusquedad del movimiento (0-100)")

del _tf, _up_t, _dn_t, _code_u, _code_d, _TH_CS_HINT


# ──────────────────────────────────────────────────────────────────────
# SMA CROSS ALERTS
# TI: End-of-candle crossover alerts. No custom settings, no quality.
# Three families:
#   5/8 SMA cross: [X5A8_N / X5B8_N] — 7 timeframes (1,2,4,5,10,20,30)
#   8/20 SMA cross: [ECAY_N / ECBY_N] — 3 timeframes (2,5,15)
#   20/200 SMA cross: [YCAD_N / YCBD_N] — 3 timeframes (2,5,15)
# ──────────────────────────────────────────────────────────────────────

# --- 5/8 SMA cross (7 timeframes) ---
for _tf, _up_t, _dn_t in [
    (1, AlertType.SMA5_ABOVE_SMA8_1M, AlertType.SMA5_BELOW_SMA8_1M),
    (2, AlertType.SMA5_ABOVE_SMA8_2M, AlertType.SMA5_BELOW_SMA8_2M),
    (4, AlertType.SMA5_ABOVE_SMA8_4M, AlertType.SMA5_BELOW_SMA8_4M),
    (5, AlertType.SMA5_ABOVE_SMA8_5M, AlertType.SMA5_BELOW_SMA8_5M),
    (10, AlertType.SMA5_ABOVE_SMA8_10M, AlertType.SMA5_BELOW_SMA8_10M),
    (20, AlertType.SMA5_ABOVE_SMA8_20M, AlertType.SMA5_BELOW_SMA8_20M),
    (30, AlertType.SMA5_ABOVE_SMA8_30M, AlertType.SMA5_BELOW_SMA8_30M),
]:
    _cu = f"X5A8_{_tf}"
    _cd = f"X5B8_{_tf}"
    _a(_cu, _up_t,
       f"5 period SMA crossed above 8 period SMA ({_tf} minute)",
       f"SMA 5 cruzo sobre SMA 8 ({_tf} minutos)",
       "ma_cross", "+", 1, True, 0,
       f"5-period SMA crosses above 8-period SMA on {_tf}-minute chart. "
       f"End-of-candle alert. Short-term trend reversal signal.",
       f"SMA de 5 periodos cruza sobre SMA de 8 periodos en grafico de {_tf} min. "
       f"Alerta al cierre de vela. Senal de reversion de tendencia corto plazo.",
       flip=_cd, keywords=["end of candle", "moving average", "fixed time frame"])
    _a(_cd, _dn_t,
       f"5 period SMA crossed below 8 period SMA ({_tf} minute)",
       f"SMA 5 cruzo bajo SMA 8 ({_tf} minutos)",
       "ma_cross", "-", 1, True, 0,
       f"5-period SMA crosses below 8-period SMA on {_tf}-minute chart. "
       f"End-of-candle alert. Short-term trend reversal signal.",
       f"SMA de 5 periodos cruza bajo SMA de 8 periodos en grafico de {_tf} min. "
       f"Alerta al cierre de vela. Senal de reversion de tendencia corto plazo.",
       flip=_cu, parent=_cu,
       keywords=["end of candle", "moving average", "fixed time frame"])

del _tf, _up_t, _dn_t, _cu, _cd

# --- 8/20 SMA cross (3 timeframes) ---
for _tf, _up_t, _dn_t in [
    (2, AlertType.SMA8_ABOVE_SMA20_2M, AlertType.SMA8_BELOW_SMA20_2M),
    (5, AlertType.SMA8_ABOVE_SMA20_5M, AlertType.SMA8_BELOW_SMA20_5M),
    (15, AlertType.SMA8_ABOVE_SMA20_15M, AlertType.SMA8_BELOW_SMA20_15M),
]:
    _cu = f"ECAY{_tf}"
    _cd = f"ECBY{_tf}"
    _a(_cu, _up_t,
       f"8 period SMA crossed above 20 period SMA ({_tf} minute)",
       f"SMA 8 cruzo sobre SMA 20 ({_tf} minutos)",
       "ma_cross", "+", 1, True, 0,
       f"8-period SMA crosses above 20-period SMA on {_tf}-minute chart. "
       f"End-of-candle alert. Medium-term golden cross signal.",
       f"SMA de 8 periodos cruza sobre SMA de 20 periodos en grafico de {_tf} min. "
       f"Alerta al cierre de vela. Senal de cruce dorado medio plazo.",
       flip=_cd, keywords=["end of candle", "moving average", "fixed time frame"])
    _a(_cd, _dn_t,
       f"8 period SMA crossed below 20 period SMA ({_tf} minute)",
       f"SMA 8 cruzo bajo SMA 20 ({_tf} minutos)",
       "ma_cross", "-", 1, True, 0,
       f"8-period SMA crosses below 20-period SMA on {_tf}-minute chart. "
       f"End-of-candle alert. Medium-term death cross signal.",
       f"SMA de 8 periodos cruza bajo SMA de 20 periodos en grafico de {_tf} min. "
       f"Alerta al cierre de vela. Senal de cruce mortal medio plazo.",
       flip=_cu, parent=_cu,
       keywords=["end of candle", "moving average", "fixed time frame"])

del _tf, _up_t, _dn_t, _cu, _cd

# --- 20/200 SMA cross (3 timeframes) ---
for _tf, _up_t, _dn_t in [
    (2, AlertType.SMA20_ABOVE_SMA200_2M, AlertType.SMA20_BELOW_SMA200_2M),
    (5, AlertType.SMA20_ABOVE_SMA200_5M, AlertType.SMA20_BELOW_SMA200_5M),
    (15, AlertType.SMA20_ABOVE_SMA200_15M, AlertType.SMA20_BELOW_SMA200_15M),
]:
    _cu = f"YCAD{_tf}"
    _cd = f"YCBD{_tf}"
    _a(_cu, _up_t,
       f"20 period SMA crossed above 200 period SMA ({_tf} minute)",
       f"SMA 20 cruzo sobre SMA 200 ({_tf} minutos)",
       "ma_cross", "+", 1, True, 0,
       f"20-period SMA crosses above 200-period SMA on {_tf}-minute chart. "
       f"End-of-candle alert. Long-term golden cross signal.",
       f"SMA de 20 periodos cruza sobre SMA de 200 periodos en grafico de {_tf} min. "
       f"Alerta al cierre de vela. Senal de cruce dorado largo plazo.",
       flip=_cd, keywords=["end of candle", "moving average", "fixed time frame"])
    _a(_cd, _dn_t,
       f"20 period SMA crossed below 200 period SMA ({_tf} minute)",
       f"SMA 20 cruzo bajo SMA 200 ({_tf} minutos)",
       "ma_cross", "-", 1, True, 0,
       f"20-period SMA crosses below 200-period SMA on {_tf}-minute chart. "
       f"End-of-candle alert. Long-term death cross signal.",
       f"SMA de 20 periodos cruza bajo SMA de 200 periodos en grafico de {_tf} min. "
       f"Alerta al cierre de vela. Senal de cruce mortal largo plazo.",
       flip=_cu, parent=_cu,
       keywords=["end of candle", "moving average", "fixed time frame"])

del _tf, _up_t, _dn_t, _cu, _cd


# ──────────────────────────────────────────────────────────────────────
# MACD CROSS ALERTS
# TI: Standard MACD (26,12,9 EMA). Single print (no end-of-candle wait).
# Two cross types per timeframe:
#   MACD line vs Signal line: [MDAS_N / MDBS_N]
#   MACD line vs Zero:        [MDAZ_N / MDBZ_N]
# 5 timeframes: 5, 10, 15, 30, 60 min.
# No custom settings, quality = 0.
# ──────────────────────────────────────────────────────────────────────

for _tf, _as_t, _bs_t, _az_t, _bz_t in [
    (5,  AlertType.MACD_ABOVE_SIGNAL_5M,  AlertType.MACD_BELOW_SIGNAL_5M,
         AlertType.MACD_ABOVE_ZERO_5M,    AlertType.MACD_BELOW_ZERO_5M),
    (10, AlertType.MACD_ABOVE_SIGNAL_10M, AlertType.MACD_BELOW_SIGNAL_10M,
         AlertType.MACD_ABOVE_ZERO_10M,   AlertType.MACD_BELOW_ZERO_10M),
    (15, AlertType.MACD_ABOVE_SIGNAL_15M, AlertType.MACD_BELOW_SIGNAL_15M,
         AlertType.MACD_ABOVE_ZERO_15M,   AlertType.MACD_BELOW_ZERO_15M),
    (30, AlertType.MACD_ABOVE_SIGNAL_30M, AlertType.MACD_BELOW_SIGNAL_30M,
         AlertType.MACD_ABOVE_ZERO_30M,   AlertType.MACD_BELOW_ZERO_30M),
    (60, AlertType.MACD_ABOVE_SIGNAL_60M, AlertType.MACD_BELOW_SIGNAL_60M,
         AlertType.MACD_ABOVE_ZERO_60M,   AlertType.MACD_BELOW_ZERO_60M),
]:
    _cas = f"MDAS{_tf}"
    _cbs = f"MDBS{_tf}"
    _caz = f"MDAZ{_tf}"
    _cbz = f"MDBZ{_tf}"
    _a(_cas, _as_t,
       f"{_tf} minute MACD crossed above signal",
       f"MACD {_tf} min cruzo sobre senal",
       "indicator", "+", 1, True, 0,
       f"MACD line crosses above signal line on {_tf}-minute chart. "
       f"Standard 26/12/9 EMA. Single print (no candle wait). Bullish momentum.",
       f"Linea MACD cruza sobre linea de senal en grafico de {_tf} min. "
       f"EMA estandar 26/12/9. Single print. Momentum alcista.",
       flip=_cbs, keywords=["single print", "fixed time frame"])
    _a(_cbs, _bs_t,
       f"{_tf} minute MACD crossed below signal",
       f"MACD {_tf} min cruzo bajo senal",
       "indicator", "-", 1, True, 0,
       f"MACD line crosses below signal line on {_tf}-minute chart. "
       f"Standard 26/12/9 EMA. Single print (no candle wait). Bearish momentum.",
       f"Linea MACD cruza bajo linea de senal en grafico de {_tf} min. "
       f"EMA estandar 26/12/9. Single print. Momentum bajista.",
       flip=_cas, parent=_cas, keywords=["single print", "fixed time frame"])
    _a(_caz, _az_t,
       f"{_tf} minute MACD crossed above zero",
       f"MACD {_tf} min cruzo sobre cero",
       "indicator", "+", 1, True, 0,
       f"MACD line crosses above zero on {_tf}-minute chart. "
       f"Standard 26/12/9 EMA. Single print. Bullish trend confirmation.",
       f"Linea MACD cruza sobre cero en grafico de {_tf} min. "
       f"EMA estandar 26/12/9. Single print. Confirmacion tendencia alcista.",
       flip=_cbz, keywords=["single print", "fixed time frame"])
    _a(_cbz, _bz_t,
       f"{_tf} minute MACD crossed below zero",
       f"MACD {_tf} min cruzo bajo cero",
       "indicator", "-", 1, True, 0,
       f"MACD line crosses below zero on {_tf}-minute chart. "
       f"Standard 26/12/9 EMA. Single print. Bearish trend confirmation.",
       f"Linea MACD cruza bajo cero en grafico de {_tf} min. "
       f"EMA estandar 26/12/9. Single print. Confirmacion tendencia bajista.",
       flip=_caz, parent=_caz, keywords=["single print", "fixed time frame"])

del _tf, _as_t, _bs_t, _az_t, _bz_t, _cas, _cbs, _caz, _cbz


# ──────────────────────────────────────────────────────────────────────
# STOCHASTIC CROSS ALERTS
# TI: Standard Stochastic (14-period, %K, %D = SMA(3) of %K).
# Single Print (no end-of-candle wait).
# Crossed above 20 = no longer oversold (bullish).
# Crossed below 80 = no longer overbought (bearish).
# 3 timeframes: 5, 15, 60 min.
# No custom settings, quality = 0.
# ──────────────────────────────────────────────────────────────────────

for _tf, _bull_t, _bear_t in [
    (5,  AlertType.STOCH_CROSS_BULLISH_5M,  AlertType.STOCH_CROSS_BEARISH_5M),
    (15, AlertType.STOCH_CROSS_BULLISH_15M, AlertType.STOCH_CROSS_BEARISH_15M),
    (60, AlertType.STOCH_CROSS_BULLISH_60M, AlertType.STOCH_CROSS_BEARISH_60M),
]:
    _ca = f"SC20_{_tf}"
    _cb = f"SC80_{_tf}"
    _a(_ca, _bull_t,
       f"{_tf} minute stochastic crossed above 20",
       f"Estocastico {_tf} min cruzo sobre 20",
       "indicator", "+", 1, True, 0,
       f"Stochastic %K crosses above 20 (no longer oversold) on {_tf}-minute chart. "
       f"Standard 14-period. Single print. Bullish signal.",
       f"Estocastico %K cruza sobre 20 (ya no sobrevendido) en grafico de {_tf} min. "
       f"Periodo estandar 14. Single print. Senal alcista.",
       flip=_cb, keywords=["single print", "fixed time frame"])
    _a(_cb, _bear_t,
       f"{_tf} minute stochastic crossed below 80",
       f"Estocastico {_tf} min cruzo bajo 80",
       "indicator", "-", 1, True, 0,
       f"Stochastic %K crosses below 80 (no longer overbought) on {_tf}-minute chart. "
       f"Standard 14-period. Single print. Bearish signal.",
       f"Estocastico %K cruza bajo 80 (ya no sobrecomprado) en grafico de {_tf} min. "
       f"Periodo estandar 14. Single print. Senal bajista.",
       flip=_ca, parent=_ca, keywords=["single print", "fixed time frame"])

del _tf, _bull_t, _bear_t, _ca, _cb


# ──────────────────────────────────────────────────────────────────────
# CANDLE PATTERN ALERTS
# TI: End-of-candle. Multiple pattern families.
# ──────────────────────────────────────────────────────────────────────

# --- Doji (5 timeframes, neutral, no custom setting, quality=0) ---
for _tf, _t in [
    (5,  AlertType.DOJI_5M),  (10, AlertType.DOJI_10M),
    (15, AlertType.DOJI_15M), (30, AlertType.DOJI_30M),
    (60, AlertType.DOJI_60M),
]:
    _a(f"DOJ{_tf}", _t,
       f"{_tf} minute Doji", f"Doji {_tf} min",
       "candle_pattern", "", 1, True, 0,
       f"Doji pattern on {_tf}-minute candlestick chart. "
       f"Open and close nearly identical. Signals indecision. End-of-candle.",
       f"Patron Doji en grafico de velas de {_tf} min. "
       f"Apertura y cierre casi identicos. Senal de indecision. Fin de vela.",
       keywords=["candle pattern", "end of candle", "fixed time frame"])
del _tf, _t

# --- Hammer (6 timeframes, bullish, quality=grade 0-100) ---
_HMR_TFS = [
    (2,  AlertType.HAMMER_2M),  (5,  AlertType.HAMMER_5M),
    (10, AlertType.HAMMER_10M), (15, AlertType.HAMMER_15M),
    (30, AlertType.HAMMER_30M), (60, AlertType.HAMMER_60M),
]
for _tf, _t in _HMR_TFS:
    _flip = f"HGM{_tf}"
    _parent = "HMR2" if _tf != 2 else ""
    _a(f"HMR{_tf}", _t,
       f"{_tf} minute hammer", f"Martillo {_tf} min",
       "candle_pattern", "+", 1, True, 0,
       f"Hammer pattern on {_tf}-minute chart. No upper wick, small body, "
       f"large lower wick in a downtrend. Bullish reversal. End-of-candle.",
       f"Patron martillo en grafico de {_tf} min. Sin mecha superior, cuerpo "
       f"pequeno, gran mecha inferior en tendencia bajista. Reversion alcista.",
       flip=_flip, parent=_parent,
       cs_type=CustomSettingType.MIN_PERCENT, cs_label="Min grade", cs_label_es="Min grado",
       cs_hint="0-100, higher = closer to ideal pattern shape", cs_default=0,
       q_desc="Pattern match grade (0-100)", q_desc_es="Grado de coincidencia (0-100)",
       keywords=["candle pattern", "end of candle", "fixed time frame"])
del _HMR_TFS

# --- Hanging Man (6 timeframes, bearish, quality=grade 0-100) ---
_HGM_TFS = [
    (2,  AlertType.HANGING_MAN_2M),  (5,  AlertType.HANGING_MAN_5M),
    (10, AlertType.HANGING_MAN_10M), (15, AlertType.HANGING_MAN_15M),
    (30, AlertType.HANGING_MAN_30M), (60, AlertType.HANGING_MAN_60M),
]
for _tf, _t in _HGM_TFS:
    _flip = f"HMR{_tf}"
    _parent = "HGM2" if _tf != 2 else ""
    _a(f"HGM{_tf}", _t,
       f"{_tf} minute hanging man", f"Hombre colgado {_tf} min",
       "candle_pattern", "-", 1, True, 0,
       f"Hanging man pattern on {_tf}-minute chart. Similar to hammer but "
       f"occurs in an uptrend. Bearish reversal. End-of-candle.",
       f"Patron hombre colgado en grafico de {_tf} min. Similar al martillo "
       f"pero en tendencia alcista. Reversion bajista.",
       flip=_flip, parent=_parent,
       cs_type=CustomSettingType.MIN_PERCENT, cs_label="Min grade", cs_label_es="Min grado",
       cs_hint="0-100, higher = closer to ideal pattern shape", cs_default=0,
       q_desc="Pattern match grade (0-100)", q_desc_es="Grado de coincidencia (0-100)",
       keywords=["candle pattern", "end of candle", "fixed time frame"])
del _HGM_TFS

# --- Bullish Engulfing (4 timeframes) ---
for _tf, _t in [
    (5,  AlertType.ENGULF_BULL_5M),  (10, AlertType.ENGULF_BULL_10M),
    (15, AlertType.ENGULF_BULL_15M), (30, AlertType.ENGULF_BULL_30M),
]:
    _a(f"NGU{_tf}", _t,
       f"{_tf} minute bullish engulfing", f"Envolvente alcista {_tf} min",
       "candle_pattern", "+", 1, True, 0,
       f"Bullish engulfing pattern on {_tf}-minute chart. Green candle engulfs "
       f"previous red candle. Shift from bearish to bullish. End-of-candle.",
       f"Patron envolvente alcista en grafico de {_tf} min. Vela verde envuelve "
       f"la vela roja anterior. Cambio de bajista a alcista.",
       flip=f"NGD{_tf}",
       cs_type=CustomSettingType.MIN_PERCENT, cs_label="Min grade", cs_label_es="Min grado",
       cs_hint="0-100, higher = closer to ideal pattern shape", cs_default=0,
       q_desc="Pattern match grade (0-100)", q_desc_es="Grado de coincidencia (0-100)",
       keywords=["candle pattern", "end of candle", "fixed time frame"])
del _tf, _t

# --- Bearish Engulfing (4 timeframes) ---
for _tf, _t in [
    (5,  AlertType.ENGULF_BEAR_5M),  (10, AlertType.ENGULF_BEAR_10M),
    (15, AlertType.ENGULF_BEAR_15M), (30, AlertType.ENGULF_BEAR_30M),
]:
    _a(f"NGD{_tf}", _t,
       f"{_tf} minute bearish engulfing", f"Envolvente bajista {_tf} min",
       "candle_pattern", "-", 1, True, 0,
       f"Bearish engulfing pattern on {_tf}-minute chart. Red candle engulfs "
       f"previous green candle. Shift from bullish to bearish. End-of-candle.",
       f"Patron envolvente bajista en grafico de {_tf} min. Vela roja envuelve "
       f"la vela verde anterior. Cambio de alcista a bajista.",
       flip=f"NGU{_tf}", parent=f"NGU{_tf}",
       cs_type=CustomSettingType.MIN_PERCENT, cs_label="Min grade", cs_label_es="Min grado",
       cs_hint="0-100, higher = closer to ideal pattern shape", cs_default=0,
       q_desc="Pattern match grade (0-100)", q_desc_es="Grado de coincidencia (0-100)",
       keywords=["candle pattern", "end of candle", "fixed time frame"])
del _tf, _t

# --- Piercing Pattern (4 timeframes, bullish) ---
for _tf, _t in [
    (5,  AlertType.PIERCING_5M),  (10, AlertType.PIERCING_10M),
    (15, AlertType.PIERCING_15M), (30, AlertType.PIERCING_30M),
]:
    _a(f"PP{_tf}", _t,
       f"{_tf} minute piercing pattern", f"Patron penetrante {_tf} min",
       "candle_pattern", "+", 1, True, 0,
       f"Piercing pattern on {_tf}-minute chart. Bullish candle opens below "
       f"previous bearish candle and closes above its midpoint. End-of-candle.",
       f"Patron penetrante en grafico de {_tf} min. Vela alcista abre bajo "
       f"la vela bajista anterior y cierra sobre su punto medio.",
       flip=f"DCC{_tf}",
       cs_type=CustomSettingType.MIN_PERCENT, cs_label="Min grade", cs_label_es="Min grado",
       cs_hint="0-100, higher = closer to ideal pattern shape", cs_default=0,
       q_desc="Pattern match grade (0-100)", q_desc_es="Grado de coincidencia (0-100)",
       keywords=["candle pattern", "end of candle", "fixed time frame"])
del _tf, _t

# --- Dark Cloud Cover (4 timeframes, bearish) ---
for _tf, _t in [
    (5,  AlertType.DARK_CLOUD_5M),  (10, AlertType.DARK_CLOUD_10M),
    (15, AlertType.DARK_CLOUD_15M), (30, AlertType.DARK_CLOUD_30M),
]:
    _a(f"DCC{_tf}", _t,
       f"{_tf} minute dark cloud cover", f"Nube oscura {_tf} min",
       "candle_pattern", "-", 1, True, 0,
       f"Dark cloud cover on {_tf}-minute chart. Bearish candle opens above "
       f"previous bullish candle and closes below its midpoint. End-of-candle.",
       f"Nube oscura en grafico de {_tf} min. Vela bajista abre sobre "
       f"la vela alcista anterior y cierra bajo su punto medio.",
       flip=f"PP{_tf}", parent=f"PP{_tf}",
       cs_type=CustomSettingType.MIN_PERCENT, cs_label="Min grade", cs_label_es="Min grado",
       cs_hint="0-100, higher = closer to ideal pattern shape", cs_default=0,
       q_desc="Pattern match grade (0-100)", q_desc_es="Grado de coincidencia (0-100)",
       keywords=["candle pattern", "end of candle", "fixed time frame"])
del _tf, _t

# --- Bottoming Tail (6 timeframes, bullish, quality=grade 0-100) ---
_BT_TFS = [
    (2,  AlertType.BOTTOMING_TAIL_2M),  (5,  AlertType.BOTTOMING_TAIL_5M),
    (10, AlertType.BOTTOMING_TAIL_10M), (15, AlertType.BOTTOMING_TAIL_15M),
    (30, AlertType.BOTTOMING_TAIL_30M), (60, AlertType.BOTTOMING_TAIL_60M),
]
for _tf, _t in _BT_TFS:
    _flip = f"TT{_tf}"
    _parent = "BT2" if _tf != 2 else ""
    _a(f"BT{_tf}", _t,
       f"{_tf} minute bottoming tail", f"Cola de fondo {_tf} min",
       "candle_pattern", "+", 1, True, 0,
       f"Bottoming tail on {_tf}-minute chart. Small bullish candle with long "
       f"lower wick after 3+ bearish candles. Reversal signal. End-of-candle.",
       f"Cola de fondo en grafico de {_tf} min. Vela alcista pequena con gran "
       f"mecha inferior tras 3+ velas bajistas. Senal de reversion.",
       flip=_flip, parent=_parent,
       cs_type=CustomSettingType.MIN_PERCENT, cs_label="Min grade", cs_label_es="Min grado",
       cs_hint="0-100, higher = closer to ideal pattern shape", cs_default=0,
       q_desc="Pattern match grade (0-100)", q_desc_es="Grado de coincidencia (0-100)",
       keywords=["candle pattern", "end of candle", "fixed time frame"])
del _BT_TFS

# --- Topping Tail (6 timeframes, bearish, quality=grade 0-100) ---
_TT_TFS = [
    (2,  AlertType.TOPPING_TAIL_2M),  (5,  AlertType.TOPPING_TAIL_5M),
    (10, AlertType.TOPPING_TAIL_10M), (15, AlertType.TOPPING_TAIL_15M),
    (30, AlertType.TOPPING_TAIL_30M), (60, AlertType.TOPPING_TAIL_60M),
]
for _tf, _t in _TT_TFS:
    _flip = f"BT{_tf}"
    _parent = "TT2" if _tf != 2 else ""
    _a(f"TT{_tf}", _t,
       f"{_tf} minute topping tail", f"Cola de techo {_tf} min",
       "candle_pattern", "-", 1, True, 0,
       f"Topping tail on {_tf}-minute chart. Small bearish candle with long "
       f"upper wick after 3+ bullish candles. Reversal signal. End-of-candle.",
       f"Cola de techo en grafico de {_tf} min. Vela bajista pequena con gran "
       f"mecha superior tras 3+ velas alcistas. Senal de reversion.",
       flip=_flip, parent=_parent,
       cs_type=CustomSettingType.MIN_PERCENT, cs_label="Min grade", cs_label_es="Min grado",
       cs_hint="0-100, higher = closer to ideal pattern shape", cs_default=0,
       q_desc="Pattern match grade (0-100)", q_desc_es="Grado de coincidencia (0-100)",
       keywords=["candle pattern", "end of candle", "fixed time frame"])
del _TT_TFS

# --- Narrow Range Buy Bar (4 timeframes, bullish, quality=grade 0-100) ---
for _tf, _t in [
    (5,  AlertType.NARROW_RANGE_BUY_5M),  (10, AlertType.NARROW_RANGE_BUY_10M),
    (15, AlertType.NARROW_RANGE_BUY_15M), (30, AlertType.NARROW_RANGE_BUY_30M),
]:
    _a(f"NRBB{_tf}", _t,
       f"{_tf} minute narrow range buy bar", f"Barra rango estrecho compra {_tf} min",
       "candle_pattern", "+", 1, True, 0,
       f"Narrow range buy bar on {_tf}-minute chart. 3+ green bars followed by "
       f"a bar smaller than 25% of avg range of past 5 bars. End-of-candle.",
       f"Barra rango estrecho compra en grafico de {_tf} min. 3+ velas verdes "
       f"seguidas de barra menor al 25% del rango promedio de 5 barras.",
       flip=f"NRSB{_tf}",
       cs_type=CustomSettingType.MIN_PERCENT, cs_label="Min grade", cs_label_es="Min grado",
       cs_hint="0-100, higher = closer to ideal pattern shape", cs_default=0,
       q_desc="Pattern match grade (0-100)", q_desc_es="Grado de coincidencia (0-100)",
       keywords=["candle pattern", "end of candle", "fixed time frame"])
del _tf, _t

# --- Narrow Range Sell Bar (4 timeframes, bearish, quality=grade 0-100) ---
for _tf, _t in [
    (5,  AlertType.NARROW_RANGE_SELL_5M),  (10, AlertType.NARROW_RANGE_SELL_10M),
    (15, AlertType.NARROW_RANGE_SELL_15M), (30, AlertType.NARROW_RANGE_SELL_30M),
]:
    _a(f"NRSB{_tf}", _t,
       f"{_tf} minute narrow range sell bar", f"Barra rango estrecho venta {_tf} min",
       "candle_pattern", "-", 1, True, 0,
       f"Narrow range sell bar on {_tf}-minute chart. 3+ red bars followed by "
       f"a bar smaller than 25% of avg range of past 5 bars. End-of-candle.",
       f"Barra rango estrecho venta en grafico de {_tf} min. 3+ velas rojas "
       f"seguidas de barra menor al 25% del rango promedio de 5 barras.",
       flip=f"NRBB{_tf}", parent=f"NRBB{_tf}",
       cs_type=CustomSettingType.MIN_PERCENT, cs_label="Min grade", cs_label_es="Min grado",
       cs_hint="0-100, higher = closer to ideal pattern shape", cs_default=0,
       q_desc="Pattern match grade (0-100)", q_desc_es="Grado de coincidencia (0-100)",
       keywords=["candle pattern", "end of candle", "fixed time frame"])
del _tf, _t

# --- Red Bar Reversal (4 timeframes, bearish, quality=consecutive candles) ---
for _tf, _t in [
    (2,  AlertType.RED_BAR_REV_2M),  (5,  AlertType.RED_BAR_REV_5M),
    (15, AlertType.RED_BAR_REV_15M), (60, AlertType.RED_BAR_REV_60M),
]:
    _parent = "RBR2" if _tf != 2 else ""
    _a(f"RBR{_tf}", _t,
       f"{_tf} minute red bar reversal", f"Reversion barra roja {_tf} min",
       "candle_pattern", "-", 1, True, 0,
       f"Red bar reversal on {_tf}-minute chart. 3+ consecutive green candles "
       f"followed by a red candle. End-of-candle.",
       f"Reversion barra roja en grafico de {_tf} min. 3+ velas verdes "
       f"consecutivas seguidas de una vela roja.",
       flip=f"GBR{_tf}", parent=_parent,
       cs_type=CustomSettingType.MIN_TIMES, cs_label="Min bars", cs_label_es="Min barras",
       cs_hint="Min consecutive green bars before reversal. Default 3.", cs_default=3,
       q_desc="Consecutive green bars before reversal",
       q_desc_es="Barras verdes consecutivas antes de la reversion",
       keywords=["candle pattern", "end of candle", "fixed time frame"])
del _tf, _t, _parent

# --- Green Bar Reversal (4 timeframes, bullish, quality=consecutive candles) ---
for _tf, _t in [
    (2,  AlertType.GREEN_BAR_REV_2M),  (5,  AlertType.GREEN_BAR_REV_5M),
    (15, AlertType.GREEN_BAR_REV_15M), (60, AlertType.GREEN_BAR_REV_60M),
]:
    _parent = "GBR2" if _tf != 2 else ""
    _a(f"GBR{_tf}", _t,
       f"{_tf} minute green bar reversal", f"Reversion barra verde {_tf} min",
       "candle_pattern", "+", 1, True, 0,
       f"Green bar reversal on {_tf}-minute chart. 3+ consecutive red candles "
       f"followed by a green candle. End-of-candle.",
       f"Reversion barra verde en grafico de {_tf} min. 3+ velas rojas "
       f"consecutivas seguidas de una vela verde.",
       flip=f"RBR{_tf}", parent=_parent,
       cs_type=CustomSettingType.MIN_TIMES, cs_label="Min bars", cs_label_es="Min barras",
       cs_hint="Min consecutive red bars before reversal. Default 3.", cs_default=3,
       q_desc="Consecutive red bars before reversal",
       q_desc_es="Barras rojas consecutivas antes de la reversion",
       keywords=["candle pattern", "end of candle", "fixed time frame"])
del _tf, _t, _parent

# --- 1-2-3 Continuation Buy (4 timeframes, bullish, Single Print) ---
for _tf, _t in [
    (2,  AlertType.CONT_123_BUY_2M),  (5,  AlertType.CONT_123_BUY_5M),
    (15, AlertType.CONT_123_BUY_15M), (60, AlertType.CONT_123_BUY_60M),
]:
    _parent = "C1U_2" if _tf != 2 else ""
    _a(f"C1U_{_tf}", _t,
       f"{_tf} minute 1-2-3 continuation buy signal",
       f"Senal compra continuacion 1-2-3 {_tf} min",
       "candle_pattern", "+", 1, True, 0,
       f"1-2-3 continuation buy on {_tf}-minute chart. Tall green bar followed "
       f"by smaller green bar (mini double-top), then price breaks above both highs. "
       f"Single print trigger.",
       f"Compra continuacion 1-2-3 en grafico de {_tf} min. Barra verde alta "
       f"seguida de barra verde menor (mini doble techo), luego precio rompe "
       f"sobre ambos maximos. Single print.",
       flip=f"C1D_{_tf}", parent=_parent,
       keywords=["candle pattern", "single print", "fixed time frame"])
del _tf, _t, _parent

# --- 1-2-3 Continuation Sell (4 timeframes, bearish, Single Print) ---
for _tf, _t in [
    (2,  AlertType.CONT_123_SELL_2M),  (5,  AlertType.CONT_123_SELL_5M),
    (15, AlertType.CONT_123_SELL_15M), (60, AlertType.CONT_123_SELL_60M),
]:
    _parent = "C1D_2" if _tf != 2 else ""
    _a(f"C1D_{_tf}", _t,
       f"{_tf} minute 1-2-3 continuation sell signal",
       f"Senal venta continuacion 1-2-3 {_tf} min",
       "candle_pattern", "-", 1, True, 0,
       f"1-2-3 continuation sell on {_tf}-minute chart. Tall red bar followed "
       f"by smaller red bar (mini double-bottom), then price breaks below both lows. "
       f"Single print trigger.",
       f"Venta continuacion 1-2-3 en grafico de {_tf} min. Barra roja alta "
       f"seguida de barra roja menor (mini doble suelo), luego precio rompe "
       f"bajo ambos minimos. Single print.",
       flip=f"C1U_{_tf}", parent=_parent,
       keywords=["candle pattern", "single print", "fixed time frame"])
del _tf, _t, _parent


# ──────────────────────────────────────────────────────────────────────
# Cleanup & Lookups
# ──────────────────────────────────────────────────────────────────────

del _a

ALERT_CATALOG: Dict[str, AlertDefinition] = {a.code: a for a in _alerts}
_BY_ALERT_TYPE: Dict[AlertType, AlertDefinition] = {a.alert_type: a for a in _alerts}
_BY_CATEGORY: Dict[str, List[AlertDefinition]] = {}
for _a_item in _alerts:
    _BY_CATEGORY.setdefault(_a_item.category, []).append(_a_item)


def get_alert_by_code(code: str) -> Optional[AlertDefinition]:
    return ALERT_CATALOG.get(code)


def get_alert_by_type(alert_type: AlertType) -> Optional[AlertDefinition]:
    return _BY_ALERT_TYPE.get(alert_type)


def get_alerts_by_category(category_id: str) -> List[AlertDefinition]:
    return _BY_CATEGORY.get(category_id, [])


def get_active_alerts() -> List[AlertDefinition]:
    return [a for a in _alerts if a.active]


def get_alerts_with_custom_settings() -> List[AlertDefinition]:
    return [a for a in _alerts if a.custom_setting_type != CustomSettingType.NONE]


def get_catalog_stats() -> Dict[str, Any]:
    total = len(_alerts)
    active = sum(1 for a in _alerts if a.active)
    with_cs = sum(1 for a in _alerts if a.custom_setting_type != CustomSettingType.NONE)
    by_cs_type: Dict[str, int] = {}
    for a in _alerts:
        if a.custom_setting_type != CustomSettingType.NONE:
            by_cs_type[a.custom_setting_type.value] = by_cs_type.get(a.custom_setting_type.value, 0) + 1
    return {
        "total_alerts": total,
        "active_alerts": active,
        "with_custom_settings": with_cs,
        "by_custom_setting_type": by_cs_type,
        "categories": len(CATEGORY_CATALOG),
    }
