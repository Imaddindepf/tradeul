/**
 * Alert Catalog — Single source of truth for the frontend.
 *
 * Synchronized with services/alert_engine/registry/alert_catalog.py.
 * Every alert type the backend can produce is listed here with display
 * metadata so the Strategy Builder, EventTable, EventFeed, and filters
 * all derive labels / colors / icons from one place.
 *
 * When adding a new alert in the backend, add a matching entry here.
 */

// ============================================================================
// TYPES
// ============================================================================

export type AlertDirection = 'bullish' | 'bearish' | 'neutral';

export type CustomSettingType =
  | 'lookback_days'
  | 'quality_ratio'
  | 'volume_ratio'
  | 'min_shares'
  | 'min_dollars'
  | 'min_percent'
  | 'min_sigma'
  | 'min_seconds'
  | 'min_cents'
  | 'min_times'
  | 'min_hours'
  | 'none';

export interface CustomSettingMeta {
  type: CustomSettingType;
  label: string;
  labelEs: string;
  hint: string;
  unit: string;
  defaultValue: number | null;
}

export interface AlertCategory {
  id: string;
  name: string;
  nameEs: string;
  icon: string;
  order: number;
}

export interface AlertDefinition {
  code: string;
  eventType: string;
  name: string;
  nameEs: string;
  shortLabel: string;
  category: string;
  direction: AlertDirection;
  active: boolean;
  description: string;
  descriptionEs: string;
  flipCode?: string;
  keywords: string[];
  customSetting: CustomSettingMeta;
  qualityDesc?: string;
  qualityDescEs?: string;
}

// ============================================================================
// CATEGORIES
// ============================================================================

export const ALERT_CATEGORIES: AlertCategory[] = [
  { id: 'price',       name: 'Price',               nameEs: 'Precio',              icon: 'TrendingUp',       order: 1 },
  { id: 'vwap',        name: 'VWAP',                nameEs: 'VWAP',                icon: 'Activity',         order: 2 },
  { id: 'volume',      name: 'Volume',              nameEs: 'Volumen',             icon: 'BarChart3',        order: 3 },
  { id: 'momentum',    name: 'Momentum',            nameEs: 'Momentum',            icon: 'Zap',              order: 4 },
  { id: 'pullback',    name: 'Pullbacks',           nameEs: 'Retrocesos',          icon: 'ArrowDownUp',      order: 5 },
  { id: 'gap',         name: 'Gaps',                nameEs: 'Gaps',                icon: 'ArrowLeftRight',   order: 6 },
  { id: 'ma_cross',    name: 'Moving Averages',     nameEs: 'Medias Móviles',      icon: 'LineChart',        order: 7 },
  { id: 'bollinger',   name: 'Bollinger Bands',     nameEs: 'Bandas Bollinger',    icon: 'Maximize2',        order: 8 },
  { id: 'orb',         name: 'Opening Range',       nameEs: 'Rango Apertura',      icon: 'Clock',            order: 9 },
  { id: 'consol',      name: 'Consolidation',       nameEs: 'Consolidación',       icon: 'Square',           order: 10 },
  { id: 'bidask',      name: 'Bid / Ask',           nameEs: 'Bid / Ask',           icon: 'ArrowUpDown',      order: 11 },
  { id: 'halt',        name: 'Halts & Resumes',     nameEs: 'Halts y Reanudaciones', icon: 'AlertTriangle',  order: 12 },
  { id: 'session',     name: 'Pre/Post Market',     nameEs: 'Pre/Post Mercado',    icon: 'Sun',              order: 13 },
  { id: 'indicator',   name: 'Technical Indicators', nameEs: 'Indicadores Técnicos', icon: 'Settings2',      order: 14 },
  { id: 'geometric',   name: 'Geometric Patterns',  nameEs: 'Patrones Geométricos', icon: 'Triangle',        order: 15 },
  { id: 'candle',      name: 'Candlestick',         nameEs: 'Velas',               icon: 'CandlestickChart', order: 16 },
  { id: 'trailing',    name: 'Trailing Stops',      nameEs: 'Trailing Stops',      icon: 'Target',            order: 17 },
  { id: 'fibonacci',   name: 'Fibonacci',           nameEs: 'Fibonacci',           icon: 'GitBranch',         order: 18 },
  { id: 'linreg',      name: 'Linear Regression',   nameEs: 'Regresión Lineal',    icon: 'TrendingUp',        order: 19 },
  { id: 'thrust',      name: 'SMA Thrust',          nameEs: 'Empuje SMA',          icon: 'Zap',               order: 20 },
  { id: 'candle_pattern', name: 'Candle Patterns',  nameEs: 'Patrones de Velas',   icon: 'CandlestickChart',  order: 21 },
];

export const ALERT_CATEGORIES_MAP: Record<string, AlertCategory> = Object.fromEntries(
  ALERT_CATEGORIES.map(c => [c.id, c])
);

// ============================================================================
// HELPER — no custom setting
// ============================================================================

const NONE_CS: CustomSettingMeta = {
  type: 'none', label: '', labelEs: '', hint: '', unit: '', defaultValue: null,
};

function cs(
  type: CustomSettingType,
  label: string, labelEs: string,
  hint: string, unit: string,
  defaultValue: number | null = null,
): CustomSettingMeta {
  return { type, label, labelEs, hint, unit, defaultValue };
}

// ============================================================================
// ALERT CATALOG — Complete list matching backend alert_catalog.py
// ============================================================================

export const ALERT_CATALOG: AlertDefinition[] = [

  // ═══════════════════════════════════════════════════════════════════════
  // PRICE — Highs & Lows
  // ═══════════════════════════════════════════════════════════════════════

  { code: 'NHP',  eventType: 'new_high',          name: 'New High',                nameEs: 'Nuevo Máximo',             shortLabel: 'New High',    category: 'price', direction: 'bullish',  active: true, description: 'Price reaches new intraday high', descriptionEs: 'El precio alcanza un nuevo máximo intradía', flipCode: 'NLP', keywords: ['highs', 'lows', 'single print'], customSetting: cs('lookback_days', 'Min lookback days', 'Mín días lookback', '0=any, 1=above yesterday, 7=weekly, 365=52-week', 'days', 0), qualityDesc: 'Lookback period in trading days', qualityDescEs: 'Período lookback en días de trading' },
  { code: 'NLP',  eventType: 'new_low',           name: 'New Low',                 nameEs: 'Nuevo Mínimo',             shortLabel: 'New Low',     category: 'price', direction: 'bearish',  active: true, description: 'Price reaches new intraday low', descriptionEs: 'El precio alcanza un nuevo mínimo intradía', flipCode: 'NHP', keywords: ['highs', 'lows', 'single print'], customSetting: cs('lookback_days', 'Min lookback days', 'Mín días lookback', '0=any, 1=below yesterday, 7=weekly, 365=52-week', 'days', 0), qualityDesc: 'Lookback period in trading days', qualityDescEs: 'Período lookback en días de trading' },
  { code: 'NHA',  eventType: 'new_high_ask',      name: 'New High Ask',            nameEs: 'Nuevo Máximo Ask',         shortLabel: 'High Ask',    category: 'price', direction: 'bullish',  active: true, description: 'Ask price reaches new intraday high', descriptionEs: 'El precio ask alcanza un nuevo máximo intradía', flipCode: 'NLB', keywords: ['bid and ask'], customSetting: cs('min_shares', 'Min shares on ask', 'Mín acciones en ask', 'Minimum shares showing on ask', 'shares'), qualityDesc: 'Lookback period', qualityDescEs: 'Período lookback' },
  { code: 'NLB',  eventType: 'new_low_bid',       name: 'New Low Bid',             nameEs: 'Nuevo Mínimo Bid',         shortLabel: 'Low Bid',     category: 'price', direction: 'bearish',  active: true, description: 'Bid price reaches new intraday low', descriptionEs: 'El precio bid alcanza un nuevo mínimo intradía', flipCode: 'NHA', keywords: ['bid and ask'], customSetting: cs('min_shares', 'Min shares on bid', 'Mín acciones en bid', 'Minimum shares showing on bid', 'shares'), qualityDesc: 'Lookback period', qualityDescEs: 'Período lookback' },
  { code: 'NHPF', eventType: 'new_high_filtered', name: 'New High (filtered)',     nameEs: 'Nuevo Máximo (filtrado)',   shortLabel: 'High Filt',   category: 'price', direction: 'bullish',  active: true, description: 'New High rate-limited by volatility', descriptionEs: 'Nuevo Máximo limitado por volatilidad', flipCode: 'NLPF', keywords: ['highs and lows', 'single print'], customSetting: cs('lookback_days', 'Min lookback days', 'Mín días lookback', '0=any, 1=above yesterday, 365=52-week', 'days', 0), qualityDesc: 'Lookback period', qualityDescEs: 'Período lookback' },
  { code: 'NLPF', eventType: 'new_low_filtered',  name: 'New Low (filtered)',      nameEs: 'Nuevo Mínimo (filtrado)',   shortLabel: 'Low Filt',    category: 'price', direction: 'bearish',  active: true, description: 'New Low rate-limited by volatility', descriptionEs: 'Nuevo Mínimo limitado por volatilidad', flipCode: 'NHPF', keywords: ['highs and lows', 'single print'], customSetting: cs('lookback_days', 'Min lookback days', 'Mín días lookback', '0=any, 1=below yesterday, 365=52-week', 'days', 0), qualityDesc: 'Lookback period', qualityDescEs: 'Período lookback' },
  { code: 'NHAF', eventType: 'new_high_ask_filtered', name: 'New High Ask (filtered)', nameEs: 'Nuevo Máximo Ask (filtrado)', shortLabel: 'HiAsk Filt', category: 'price', direction: 'bullish', active: true, description: 'New High Ask rate-limited by volatility', descriptionEs: 'Nuevo Máximo Ask limitado por volatilidad', flipCode: 'NLBF', keywords: ['bid and ask'], customSetting: cs('min_shares', 'Min shares on ask', 'Mín acciones en ask', 'Minimum shares on ask', 'shares'), qualityDesc: 'Lookback period', qualityDescEs: 'Período lookback' },
  { code: 'NLBF', eventType: 'new_low_bid_filtered', name: 'New Low Bid (filtered)', nameEs: 'Nuevo Mínimo Bid (filtrado)', shortLabel: 'LoBid Filt', category: 'price', direction: 'bearish', active: true, description: 'New Low Bid rate-limited by volatility', descriptionEs: 'Nuevo Mínimo Bid limitado por volatilidad', flipCode: 'NHAF', keywords: ['bid and ask'], customSetting: cs('min_shares', 'Min shares on bid', 'Mín acciones en bid', 'Minimum shares on bid', 'shares'), qualityDesc: 'Lookback period', qualityDescEs: 'Período lookback' },
  { code: 'NHB',  eventType: 'new_high_bid',      name: 'New High Bid',            nameEs: 'Nuevo Máximo Bid',         shortLabel: 'High Bid',    category: 'price', direction: 'bullish',  active: true, description: 'Bid price reaches new intraday high', descriptionEs: 'El precio bid alcanza un nuevo máximo intradía', flipCode: 'NLA', keywords: ['bid and ask'], customSetting: cs('min_shares', 'Min shares on bid', 'Mín acciones en bid', 'Minimum shares on bid', 'shares'), qualityDesc: 'Shares on bid', qualityDescEs: 'Acciones en bid' },
  { code: 'NLA',  eventType: 'new_low_ask',       name: 'New Low Ask',             nameEs: 'Nuevo Mínimo Ask',         shortLabel: 'Low Ask',     category: 'price', direction: 'bearish',  active: true, description: 'Ask price reaches new intraday low', descriptionEs: 'El precio ask alcanza un nuevo mínimo intradía', flipCode: 'NHB', keywords: ['bid and ask'], customSetting: cs('min_shares', 'Min shares on ask', 'Mín acciones en ask', 'Minimum shares on ask', 'shares'), qualityDesc: 'Lookback period', qualityDescEs: 'Período lookback' },
  { code: 'NHBF', eventType: 'new_high_bid_filtered', name: 'New High Bid (filtered)', nameEs: 'Nuevo Máximo Bid (filtrado)', shortLabel: 'HiBid Filt', category: 'price', direction: 'bullish', active: true, description: 'New High Bid rate-limited by volatility', descriptionEs: 'Nuevo Máximo Bid limitado por volatilidad', flipCode: 'NLAF', keywords: ['bid and ask'], customSetting: cs('min_shares', 'Min shares on bid', 'Mín acciones en bid', 'Minimum shares on bid', 'shares'), qualityDesc: 'Shares on bid', qualityDescEs: 'Acciones en bid' },
  { code: 'NLAF', eventType: 'new_low_ask_filtered', name: 'New Low Ask (filtered)', nameEs: 'Nuevo Mínimo Ask (filtrado)', shortLabel: 'LoAsk Filt', category: 'price', direction: 'bearish', active: true, description: 'New Low Ask rate-limited by volatility', descriptionEs: 'Nuevo Mínimo Ask limitado por volatilidad', flipCode: 'NHBF', keywords: ['bid and ask'], customSetting: cs('min_shares', 'Min shares on ask', 'Mín acciones en ask', 'Minimum shares on ask', 'shares'), qualityDesc: 'Lookback period', qualityDescEs: 'Período lookback' },

  // Daily resistance / support
  { code: 'CDHR', eventType: 'crossed_daily_high_resistance', name: 'Crossed Daily Highs Resistance', nameEs: 'Cruzó Resistencia Máximos Diarios', shortLabel: 'Day High ↑', category: 'price', direction: 'bullish', active: true, description: 'Price crosses above a previous day high', descriptionEs: 'El precio cruza por encima del máximo de un día anterior', flipCode: 'CDLS', keywords: ['highs and lows', 'single print'], customSetting: cs('lookback_days', 'Min lookback days', 'Mín días lookback', '0=any, 1=above yesterday, 365=52-week', 'days', 0), qualityDesc: 'Days of resistance broken', qualityDescEs: 'Días de resistencia rotos' },
  { code: 'CDLS', eventType: 'crossed_daily_low_support', name: 'Crossed Daily Lows Support', nameEs: 'Cruzó Soporte Mínimos Diarios', shortLabel: 'Day Low ↓', category: 'price', direction: 'bearish', active: true, description: 'Price crosses below a previous day low', descriptionEs: 'El precio cruza por debajo del mínimo de un día anterior', flipCode: 'CDHR', keywords: ['highs and lows', 'single print'], customSetting: cs('lookback_days', 'Min lookback days', 'Mín días lookback', '0=any, 1=below yesterday, 365=52-week', 'days', 0), qualityDesc: 'Days of support broken', qualityDescEs: 'Días de soporte rotos' },

  // Std deviation
  { code: 'BBU',  eventType: 'std_dev_breakout',   name: 'Std Dev Breakout',        nameEs: 'Ruptura Desv. Estándar',   shortLabel: 'σ Break ↑',   category: 'price', direction: 'bullish',  active: true, description: 'Price moves up N daily std devs from prev close', descriptionEs: 'El precio sube N desv. estándar diarias desde el cierre anterior', flipCode: 'BBD', keywords: ['highs and lows', 'single print'], customSetting: cs('min_sigma', 'Min std devs', 'Mín desv. estándar', '1 = one daily σ. Integer levels only.', 'σ', 1), qualityDesc: 'Std devs from prev close', qualityDescEs: 'Desv. estándar desde cierre anterior' },
  { code: 'BBD',  eventType: 'std_dev_breakdown',  name: 'Std Dev Breakdown',       nameEs: 'Quiebre Desv. Estándar',   shortLabel: 'σ Break ↓',   category: 'price', direction: 'bearish',  active: true, description: 'Price moves down N daily std devs from prev close', descriptionEs: 'El precio baja N desv. estándar diarias desde el cierre anterior', flipCode: 'BBU', keywords: ['highs and lows', 'single print'], customSetting: cs('min_sigma', 'Min std devs', 'Mín desv. estándar', '1 = one daily σ. Integer levels only.', 'σ', 1), qualityDesc: 'Std devs from prev close', qualityDescEs: 'Desv. estándar desde cierre anterior' },

  // Crosses — Open / Close
  { code: 'CAO',  eventType: 'crossed_above_open', name: 'Crossed Above Open',      nameEs: 'Cruzó Sobre Apertura',     shortLabel: '↑ Open',      category: 'price', direction: 'bullish',  active: true, description: 'Price crosses above today open', descriptionEs: 'El precio cruza por encima de la apertura', flipCode: 'CBO', keywords: ['single print'], customSetting: cs('min_seconds', 'Min seconds', 'Mín segundos', 'Price must stay on one side for N seconds', 'sec'), qualityDesc: 'Seconds since cross', qualityDescEs: 'Segundos desde el cruce' },
  { code: 'CBO',  eventType: 'crossed_below_open', name: 'Crossed Below Open',      nameEs: 'Cruzó Bajo Apertura',      shortLabel: '↓ Open',      category: 'price', direction: 'bearish',  active: true, description: 'Price crosses below today open', descriptionEs: 'El precio cruza por debajo de la apertura', flipCode: 'CAO', keywords: ['single print'], customSetting: cs('min_seconds', 'Min seconds', 'Mín segundos', 'Price must stay on one side for N seconds', 'sec'), qualityDesc: 'Seconds since cross', qualityDescEs: 'Segundos desde el cruce' },
  { code: 'CAC',  eventType: 'crossed_above_prev_close', name: 'Crossed Above Close', nameEs: 'Cruzó Sobre Cierre',    shortLabel: '↑ Close',     category: 'price', direction: 'bullish',  active: true, description: 'Price crosses above prev close', descriptionEs: 'El precio cruza por encima del cierre anterior', flipCode: 'CBC', keywords: ['single print'], customSetting: cs('min_seconds', 'Min seconds', 'Mín segundos', 'Price must stay on one side for N seconds', 'sec'), qualityDesc: 'Seconds since cross', qualityDescEs: 'Segundos desde el cruce' },
  { code: 'CBC',  eventType: 'crossed_below_prev_close', name: 'Crossed Below Close', nameEs: 'Cruzó Bajo Cierre',     shortLabel: '↓ Close',     category: 'price', direction: 'bearish',  active: true, description: 'Price crosses below prev close', descriptionEs: 'El precio cruza por debajo del cierre anterior', flipCode: 'CAC', keywords: ['single print'], customSetting: cs('min_seconds', 'Min seconds', 'Mín segundos', 'Price must stay on one side for N seconds', 'sec'), qualityDesc: 'Seconds since cross', qualityDescEs: 'Segundos desde el cruce' },
  { code: 'CAOC', eventType: 'crossed_above_open_confirmed', name: 'Crossed Above Open (confirmed)', nameEs: 'Cruzó Sobre Apertura (confirmado)', shortLabel: '↑ Open Conf', category: 'price', direction: 'bullish', active: true, description: 'Crossed above open, volume confirmed', descriptionEs: 'Cruzó sobre apertura, confirmado por volumen', flipCode: 'CBOC', keywords: ['volume confirmed'], customSetting: NONE_CS },
  { code: 'CBOC', eventType: 'crossed_below_open_confirmed', name: 'Crossed Below Open (confirmed)', nameEs: 'Cruzó Bajo Apertura (confirmado)', shortLabel: '↓ Open Conf', category: 'price', direction: 'bearish', active: true, description: 'Crossed below open, volume confirmed', descriptionEs: 'Cruzó bajo apertura, confirmado por volumen', flipCode: 'CAOC', keywords: ['volume confirmed'], customSetting: NONE_CS },
  { code: 'CACC', eventType: 'crossed_above_close_confirmed', name: 'Crossed Above Close (confirmed)', nameEs: 'Cruzó Sobre Cierre (confirmado)', shortLabel: '↑ Close Conf', category: 'price', direction: 'bullish', active: true, description: 'Crossed above prev close, volume confirmed', descriptionEs: 'Cruzó sobre cierre anterior, confirmado por volumen', flipCode: 'CBCC', keywords: ['volume confirmed'], customSetting: NONE_CS },
  { code: 'CBCC', eventType: 'crossed_below_close_confirmed', name: 'Crossed Below Close (confirmed)', nameEs: 'Cruzó Bajo Cierre (confirmado)', shortLabel: '↓ Close Conf', category: 'price', direction: 'bearish', active: true, description: 'Crossed below prev close, volume confirmed', descriptionEs: 'Cruzó bajo cierre anterior, confirmado por volumen', flipCode: 'CACC', keywords: ['volume confirmed'], customSetting: NONE_CS },

  // ═══════════════════════════════════════════════════════════════════════
  // VWAP
  // ═══════════════════════════════════════════════════════════════════════

  { code: 'CAVC', eventType: 'vwap_cross_up',      name: 'Crossed Above VWAP',      nameEs: 'Cruce Sobre VWAP',         shortLabel: 'VWAP ↑',      category: 'vwap', direction: 'bullish',  active: true, description: 'Crossed above VWAP, volume confirmed', descriptionEs: 'Cruzó sobre VWAP, confirmado por volumen', flipCode: 'CBVC', keywords: ['volume confirmed'], customSetting: NONE_CS },
  { code: 'CBVC', eventType: 'vwap_cross_down',    name: 'Crossed Below VWAP',      nameEs: 'Cruce Bajo VWAP',          shortLabel: 'VWAP ↓',      category: 'vwap', direction: 'bearish',  active: true, description: 'Crossed below VWAP, volume confirmed', descriptionEs: 'Cruzó bajo VWAP, confirmado por volumen', flipCode: 'CAVC', keywords: ['volume confirmed'], customSetting: NONE_CS },
  { code: 'VDU',  eventType: 'vwap_divergence_up', name: 'Positive VWAP Divergence', nameEs: 'Divergencia VWAP Positiva', shortLabel: 'VWAP Div ↑', category: 'vwap', direction: 'bullish',  active: true, description: 'Price N integer % above VWAP', descriptionEs: 'Precio N% entero sobre VWAP', flipCode: 'VDD', keywords: [], customSetting: cs('min_percent', 'Min % above VWAP', 'Mín % sobre VWAP', 'Min integer % above VWAP', '%'), qualityDesc: '% above VWAP', qualityDescEs: '% sobre VWAP' },
  { code: 'VDD',  eventType: 'vwap_divergence_down', name: 'Negative VWAP Divergence', nameEs: 'Divergencia VWAP Negativa', shortLabel: 'VWAP Div ↓', category: 'vwap', direction: 'bearish', active: true, description: 'Price N integer % below VWAP', descriptionEs: 'Precio N% entero bajo VWAP', flipCode: 'VDU', keywords: [], customSetting: cs('min_percent', 'Min % below VWAP', 'Mín % bajo VWAP', 'Min integer % below VWAP', '%'), qualityDesc: '% below VWAP', qualityDescEs: '% bajo VWAP' },

  // ═══════════════════════════════════════════════════════════════════════
  // VOLUME
  // ═══════════════════════════════════════════════════════════════════════

  { code: 'HRV',  eventType: 'rvol_spike',         name: 'High Relative Volume',    nameEs: 'Alto Volumen Relativo',    shortLabel: 'RVOL',        category: 'volume', direction: 'neutral', active: true, description: 'Stock trading on higher volume than normal', descriptionEs: 'Acción operando con volumen mayor al normal', keywords: ['volume confirmed'], customSetting: cs('volume_ratio', 'Min RVOL ratio', 'Mín ratio RVOL', '1.5 = 50% above normal. 3.0 = 3x normal.', 'x'), qualityDesc: 'Times more than avg volume', qualityDescEs: 'Veces más que el volumen promedio' },
  { code: 'SV',   eventType: 'volume_surge',       name: 'Strong Volume',           nameEs: 'Volumen Fuerte',           shortLabel: 'Strong Vol',  category: 'volume', direction: 'neutral', active: true, description: 'Total volume today vs average daily volume', descriptionEs: 'Volumen total del día vs promedio diario', keywords: [], customSetting: cs('volume_ratio', 'Min volume multiple', 'Mín múltiplo volumen', '1 = at 1x avg daily. 3 = only at 3x+.', 'x'), qualityDesc: 'Multiple of avg daily volume', qualityDescEs: 'Múltiplo del volumen diario promedio' },
  { code: 'VS1',  eventType: 'volume_spike_1min',  name: '1 Minute Volume Spike',   nameEs: 'Pico Volumen 1 Min',       shortLabel: 'Vol Spike',   category: 'volume', direction: 'neutral', active: true, description: 'Unusual volume in a 1-minute candle', descriptionEs: 'Volumen inusual en una vela de 1 minuto', keywords: ['fixed time frame'], customSetting: cs('volume_ratio', 'Min spike ratio', 'Mín ratio pico', 'Ratio of 1-min volume to historical average', 'x'), qualityDesc: '1-min volume ratio', qualityDescEs: 'Ratio de volumen de 1 minuto' },
  { code: 'UNOP', eventType: 'unusual_prints',     name: 'Unusual Prints',          nameEs: 'Prints Inusuales',         shortLabel: 'Unusual',     category: 'volume', direction: 'neutral', active: true, description: 'Stock printing tape much faster than normal', descriptionEs: 'Acción imprimiendo mucho más rápido de lo normal', keywords: [], customSetting: cs('volume_ratio', 'Min print ratio', 'Mín ratio prints', 'Multiple of normal print rate', 'x'), qualityDesc: 'Multiple of normal print rate', qualityDescEs: 'Múltiplo de la tasa normal de prints' },
  { code: 'BP',   eventType: 'block_trade',        name: 'Block Trade',             nameEs: 'Block Trade',              shortLabel: 'Block',       category: 'volume', direction: 'neutral', active: true, description: 'Single trade of 20,000+ shares', descriptionEs: 'Trade individual de 20,000+ acciones', keywords: ['single print'], customSetting: cs('min_shares', 'Min shares', 'Mín acciones', '20000 = default high vol. 5000 = low vol.', 'shares'), qualityDesc: 'Shares in the block trade', qualityDescEs: 'Acciones en el block trade' },

  // ═══════════════════════════════════════════════════════════════════════
  // MOMENTUM
  // ═══════════════════════════════════════════════════════════════════════

  { code: 'RUN',  eventType: 'running_up',         name: 'Running Up Now',          nameEs: 'Subiendo Ahora',           shortLabel: 'Run ↑',       category: 'momentum', direction: 'bullish',  active: true, description: 'Stock price trading up much faster than expected', descriptionEs: 'Precio subiendo mucho más rápido de lo esperado', flipCode: 'RDN', keywords: ['price vs time', 'single print'], customSetting: cs('min_cents', 'Min move $', 'Mín movimiento $', 'Size of the move in dollars', '$'), qualityDesc: 'Size of move in dollars', qualityDescEs: 'Tamaño del movimiento en dólares' },
  { code: 'RDN',  eventType: 'running_down',       name: 'Running Down Now',        nameEs: 'Bajando Ahora',            shortLabel: 'Run ↓',       category: 'momentum', direction: 'bearish',  active: true, description: 'Stock price trading down much faster than expected', descriptionEs: 'Precio bajando mucho más rápido de lo esperado', flipCode: 'RUN', keywords: ['price vs time', 'single print'], customSetting: cs('min_cents', 'Min move $', 'Mín movimiento $', 'Size of the move in dollars', '$'), qualityDesc: 'Size of move in dollars', qualityDescEs: 'Tamaño del movimiento en dólares' },
  { code: 'RU',   eventType: 'running_up_sustained', name: 'Running Up',            nameEs: 'Subiendo',                 shortLabel: 'Run ↑ Sust',  category: 'momentum', direction: 'bullish',  active: true, description: 'Clear, validated move upwards on ~1 min scale', descriptionEs: 'Movimiento alcista validado en escala ~1 min', flipCode: 'RD', keywords: ['price vs time', 'nbbo confirmed'], customSetting: cs('quality_ratio', 'Min quality', 'Mín calidad', '1=all, 4=top 1/3, 10=top 1%', ''), qualityDesc: 'Momentum/volatility ratio', qualityDescEs: 'Ratio momentum/volatilidad' },
  { code: 'RD',   eventType: 'running_down_sustained', name: 'Running Down',        nameEs: 'Bajando',                  shortLabel: 'Run ↓ Sust',  category: 'momentum', direction: 'bearish',  active: true, description: 'Clear, validated move downwards on ~1 min scale', descriptionEs: 'Movimiento bajista validado en escala ~1 min', flipCode: 'RU', keywords: ['price vs time', 'nbbo confirmed'], customSetting: cs('quality_ratio', 'Min quality', 'Mín calidad', '1=all, 4=top 1/3, 10=top 1%', ''), qualityDesc: 'Momentum/volatility ratio', qualityDescEs: 'Ratio momentum/volatilidad' },
  { code: 'RUI',  eventType: 'running_up_intermediate', name: 'Running Up (intermediate)', nameEs: 'Subiendo (intermedio)', shortLabel: 'Run ↑ Int', category: 'momentum', direction: 'bullish', active: true, description: 'Middle ground between fast and confirmed running. ~5 min.', descriptionEs: 'Punto medio entre running rápido y confirmado. ~5 min.', flipCode: 'RDI', keywords: ['price vs time'], customSetting: cs('volume_ratio', 'Min ratio', 'Mín ratio', '2.4=30th pct, 2.9=50th, 6.6=90th', 'x'), qualityDesc: 'Actual speed vs expected speed ratio', qualityDescEs: 'Ratio velocidad real vs esperada' },
  { code: 'RDI',  eventType: 'running_down_intermediate', name: 'Running Down (intermediate)', nameEs: 'Bajando (intermedio)', shortLabel: 'Run ↓ Int', category: 'momentum', direction: 'bearish', active: true, description: 'Middle ground between fast and confirmed running. ~5 min.', descriptionEs: 'Punto medio entre running rápido y confirmado. ~5 min.', flipCode: 'RUI', keywords: ['price vs time'], customSetting: cs('volume_ratio', 'Min ratio', 'Mín ratio', '2.4=30th pct, 2.9=50th, 6.6=90th', 'x'), qualityDesc: 'Actual speed vs expected speed ratio', qualityDescEs: 'Ratio velocidad real vs esperada' },
  { code: 'RUC',  eventType: 'running_up_confirmed', name: 'Running Up (confirmed)', nameEs: 'Subiendo (confirmado)',   shortLabel: 'Run ↑ Conf',  category: 'momentum', direction: 'bullish',  active: true, description: 'Volume confirmed running alert. ~15 min timeframe.', descriptionEs: 'Alerta running confirmada por volumen. ~15 min.', flipCode: 'RDC', keywords: ['price vs time', 'volume confirmed'], customSetting: cs('quality_ratio', 'Min quality', 'Mín calidad', '1.0=all, 5.0+=briskly, 10=top 1%', ''), qualityDesc: 'Momentum/volatility ratio', qualityDescEs: 'Ratio momentum/volatilidad' },
  { code: 'RDC',  eventType: 'running_down_confirmed', name: 'Running Down (confirmed)', nameEs: 'Bajando (confirmado)', shortLabel: 'Run ↓ Conf',  category: 'momentum', direction: 'bearish',  active: true, description: 'Volume confirmed running alert. ~15 min timeframe.', descriptionEs: 'Alerta running confirmada por volumen. ~15 min.', flipCode: 'RUC', keywords: ['price vs time', 'volume confirmed'], customSetting: cs('quality_ratio', 'Min quality', 'Mín calidad', '1.0=all, 5.0+=briskly, 10=top 1%', ''), qualityDesc: 'Momentum/volatility ratio', qualityDescEs: 'Ratio momentum/volatilidad' },
  { code: 'PUD',  eventType: 'percent_up_day',     name: '% Up For The Day',        nameEs: '% Arriba del Día',         shortLabel: '% Up',        category: 'momentum', direction: 'bullish',  active: true, description: 'Reports each integer % level once per day', descriptionEs: 'Reporta cada nivel entero de % una vez al día', flipCode: 'PDD', keywords: ['highs and lows', 'single print'], customSetting: cs('min_percent', 'Min % change', 'Mín % cambio', 'Min % up to show. Default 3%.', '%', 3), qualityDesc: '% up for the day', qualityDescEs: '% arriba del día' },
  { code: 'PDD',  eventType: 'percent_down_day',   name: '% Down For The Day',      nameEs: '% Abajo del Día',          shortLabel: '% Down',      category: 'momentum', direction: 'bearish',  active: true, description: 'Reports each integer % level once per day', descriptionEs: 'Reporta cada nivel entero de % una vez al día', flipCode: 'PUD', keywords: ['highs and lows', 'single print'], customSetting: cs('min_percent', 'Min % change', 'Mín % cambio', 'Min % down to show. Default 3%.', '%', 3), qualityDesc: '% down for the day', qualityDescEs: '% abajo del día' },

  // ═══════════════════════════════════════════════════════════════════════
  // PULLBACKS
  // ═══════════════════════════════════════════════════════════════════════

  // Check Mark
  { code: 'CMU',  eventType: 'check_mark_up',      name: 'Check Mark',              nameEs: 'Marca de Verificación',    shortLabel: 'Check ↑',     category: 'pullback', direction: 'bullish',  active: true, description: 'Higher highs, pullback, then even higher highs', descriptionEs: 'Máximos crecientes, retroceso, luego máximos aún mayores', flipCode: 'CMD', keywords: ['highs and lows', 'single print'], customSetting: NONE_CS },
  { code: 'CMD',  eventType: 'check_mark_down',    name: 'Inverted Check Mark',     nameEs: 'Marca de Verificación Inv.', shortLabel: 'Check ↓',   category: 'pullback', direction: 'bearish',  active: true, description: 'Lower lows, bounce, then even lower lows', descriptionEs: 'Mínimos decrecientes, rebote, luego mínimos aún menores', flipCode: 'CMU', keywords: ['highs and lows', 'single print'], customSetting: NONE_CS },

  // Auto variants
  { code: 'PFL75', eventType: 'pullback_75_from_low',       name: '75% Pullback From Lows',  nameEs: 'Retroceso 75% desde Mínimos', shortLabel: 'Bounce 75%',   category: 'pullback', direction: 'bullish', active: true, description: 'Stock goes to low, bounces 75% back', descriptionEs: 'Baja al mínimo, rebota 75%', flipCode: 'PFH75', keywords: ['fibonacci', 'single print'], customSetting: cs('min_percent', 'Min initial move %', 'Mín movimiento inicial %', 'Size of first move (anchor to low)', '%'), qualityDesc: 'Initial move size %', qualityDescEs: 'Tamaño movimiento inicial %' },
  { code: 'PFL25', eventType: 'pullback_25_from_low',       name: '25% Pullback From Lows',  nameEs: 'Retroceso 25% desde Mínimos', shortLabel: 'Bounce 25%',   category: 'pullback', direction: 'bullish', active: true, description: 'Stock goes to low, bounces 25% back', descriptionEs: 'Baja al mínimo, rebota 25%', flipCode: 'PFH25', keywords: ['fibonacci', 'single print'], customSetting: cs('min_percent', 'Min initial move %', 'Mín movimiento inicial %', 'Size of first move', '%'), qualityDesc: 'Initial move size %', qualityDescEs: 'Tamaño movimiento inicial %' },
  { code: 'PFH75', eventType: 'pullback_75_from_high',      name: '75% Pullback From Highs', nameEs: 'Retroceso 75% desde Máximos', shortLabel: 'PB 75% H',     category: 'pullback', direction: 'bearish', active: true, description: 'Stock goes to high, pulls back 75%', descriptionEs: 'Sube al máximo, retrocede 75%', flipCode: 'PFL75', keywords: ['fibonacci', 'single print'], customSetting: cs('min_percent', 'Min initial move %', 'Mín movimiento inicial %', 'Size of first move', '%'), qualityDesc: 'Initial move size %', qualityDescEs: 'Tamaño movimiento inicial %' },
  { code: 'PFH25', eventType: 'pullback_25_from_high',      name: '25% Pullback From Highs', nameEs: 'Retroceso 25% desde Máximos', shortLabel: 'PB 25% H',     category: 'pullback', direction: 'bearish', active: true, description: 'Stock goes to high, pulls back 25%', descriptionEs: 'Sube al máximo, retrocede 25%', flipCode: 'PFL25', keywords: ['fibonacci', 'single print'], customSetting: cs('min_percent', 'Min initial move %', 'Mín movimiento inicial %', 'Size of first move', '%'), qualityDesc: 'Initial move size %', qualityDescEs: 'Tamaño movimiento inicial %' },

  // Close variants
  { code: 'PFL75C', eventType: 'pullback_75_from_low_close',  name: '75% PB From Lows (Close)', nameEs: 'Retroceso 75% Mínimos (Cierre)', shortLabel: 'Bounce 75% C', category: 'pullback', direction: 'bullish', active: true, description: 'From prev close, goes to low, bounces 75%', descriptionEs: 'Desde cierre anterior, baja al mínimo, rebota 75%', flipCode: 'PFH75C', keywords: ['single print'], customSetting: cs('min_percent', 'Min initial move %', 'Mín movimiento inicial %', 'Size of first move (close to low)', '%'), qualityDesc: 'Initial move size %', qualityDescEs: 'Tamaño movimiento inicial %' },
  { code: 'PFL25C', eventType: 'pullback_25_from_low_close',  name: '25% PB From Lows (Close)', nameEs: 'Retroceso 25% Mínimos (Cierre)', shortLabel: 'Bounce 25% C', category: 'pullback', direction: 'bullish', active: true, description: 'From prev close, goes to low, bounces 25%', descriptionEs: 'Desde cierre anterior, baja al mínimo, rebota 25%', flipCode: 'PFH25C', keywords: ['single print'], customSetting: cs('min_percent', 'Min initial move %', 'Mín movimiento inicial %', 'Size of first move', '%'), qualityDesc: 'Initial move size %', qualityDescEs: 'Tamaño movimiento inicial %' },
  { code: 'PFH75C', eventType: 'pullback_75_from_high_close', name: '75% PB From Highs (Close)', nameEs: 'Retroceso 75% Máximos (Cierre)', shortLabel: 'PB 75% H/C', category: 'pullback', direction: 'bearish', active: true, description: 'From prev close, goes to high, pulls back 75%', descriptionEs: 'Desde cierre anterior, sube al máximo, retrocede 75%', flipCode: 'PFL75C', keywords: ['single print'], customSetting: cs('min_percent', 'Min initial move %', 'Mín movimiento inicial %', 'Size of first move', '%'), qualityDesc: 'Initial move size %', qualityDescEs: 'Tamaño movimiento inicial %' },
  { code: 'PFH25C', eventType: 'pullback_25_from_high_close', name: '25% PB From Highs (Close)', nameEs: 'Retroceso 25% Máximos (Cierre)', shortLabel: 'PB 25% H/C', category: 'pullback', direction: 'bearish', active: true, description: 'From prev close, goes to high, pulls back 25%', descriptionEs: 'Desde cierre anterior, sube al máximo, retrocede 25%', flipCode: 'PFL25C', keywords: ['single print'], customSetting: cs('min_percent', 'Min initial move %', 'Mín movimiento inicial %', 'Size of first move', '%'), qualityDesc: 'Initial move size %', qualityDescEs: 'Tamaño movimiento inicial %' },

  // Open variants
  { code: 'PFL75O', eventType: 'pullback_75_from_low_open',  name: '75% PB From Lows (Open)', nameEs: 'Retroceso 75% Mínimos (Apertura)', shortLabel: 'Bounce 75% O', category: 'pullback', direction: 'bullish', active: true, description: 'From today open, goes to low, bounces 75%', descriptionEs: 'Desde apertura, baja al mínimo, rebota 75%', flipCode: 'PFH75O', keywords: ['single print'], customSetting: cs('min_percent', 'Min initial move %', 'Mín movimiento inicial %', 'Size of first move (open to low)', '%'), qualityDesc: 'Initial move size %', qualityDescEs: 'Tamaño movimiento inicial %' },
  { code: 'PFL25O', eventType: 'pullback_25_from_low_open',  name: '25% PB From Lows (Open)', nameEs: 'Retroceso 25% Mínimos (Apertura)', shortLabel: 'Bounce 25% O', category: 'pullback', direction: 'bullish', active: true, description: 'From today open, goes to low, bounces 25%', descriptionEs: 'Desde apertura, baja al mínimo, rebota 25%', flipCode: 'PFH25O', keywords: ['single print'], customSetting: cs('min_percent', 'Min initial move %', 'Mín movimiento inicial %', 'Size of first move', '%'), qualityDesc: 'Initial move size %', qualityDescEs: 'Tamaño movimiento inicial %' },
  { code: 'PFH75O', eventType: 'pullback_75_from_high_open', name: '75% PB From Highs (Open)', nameEs: 'Retroceso 75% Máximos (Apertura)', shortLabel: 'PB 75% H/O', category: 'pullback', direction: 'bearish', active: true, description: 'From today open, goes to high, pulls back 75%', descriptionEs: 'Desde apertura, sube al máximo, retrocede 75%', flipCode: 'PFL75O', keywords: ['single print'], customSetting: cs('min_percent', 'Min initial move %', 'Mín movimiento inicial %', 'Size of first move', '%'), qualityDesc: 'Initial move size %', qualityDescEs: 'Tamaño movimiento inicial %' },
  { code: 'PFH25O', eventType: 'pullback_25_from_high_open', name: '25% PB From Highs (Open)', nameEs: 'Retroceso 25% Máximos (Apertura)', shortLabel: 'PB 25% H/O', category: 'pullback', direction: 'bearish', active: true, description: 'From today open, goes to high, pulls back 25%', descriptionEs: 'Desde apertura, sube al máximo, retrocede 25%', flipCode: 'PFL25O', keywords: ['single print'], customSetting: cs('min_percent', 'Min initial move %', 'Mín movimiento inicial %', 'Size of first move', '%'), qualityDesc: 'Initial move size %', qualityDescEs: 'Tamaño movimiento inicial %' },

  // ═══════════════════════════════════════════════════════════════════════
  // GAPS
  // ═══════════════════════════════════════════════════════════════════════

  { code: 'GUR',  eventType: 'gap_up_reversal',    name: 'Gap Up Reversal',         nameEs: 'Reversión Gap Alcista',    shortLabel: 'Gap↑ Rev',    category: 'gap', direction: 'bearish',  active: true, description: 'Stock gaps up then crosses prev close from above', descriptionEs: 'Acción con gap alcista cruza cierre previo', flipCode: 'GDR', keywords: ['single print'], customSetting: cs('min_dollars', 'Min total retracement $', 'Mín retroceso total $', 'Min total retracement (gap + continuation)', '$'), qualityDesc: 'Total retracement ($)', qualityDescEs: 'Retroceso total ($)' },
  { code: 'GDR',  eventType: 'gap_down_reversal',  name: 'Gap Down Reversal',       nameEs: 'Reversión Gap Bajista',    shortLabel: 'Gap↓ Rev',    category: 'gap', direction: 'bullish',  active: true, description: 'Stock gaps down then crosses prev close from below', descriptionEs: 'Acción con gap bajista cruza cierre previo', flipCode: 'GUR', keywords: ['single print'], customSetting: cs('min_dollars', 'Min total retracement $', 'Mín retroceso total $', 'Min total retracement (gap + continuation)', '$'), qualityDesc: 'Total retracement ($)', qualityDescEs: 'Retroceso total ($)' },
  { code: 'FGUR', eventType: 'false_gap_up_retracement', name: 'False Gap Up Retracement', nameEs: 'Retroceso Falso Gap Alcista', shortLabel: 'False Gap↑', category: 'gap', direction: 'bullish', active: true, description: 'Gap up, partial fill, then continues above open', descriptionEs: 'Gap alcista, llenado parcial, luego continúa sobre apertura', flipCode: 'FGDR', keywords: ['single print'], customSetting: cs('min_percent', 'Min % gap filled', 'Mín % gap llenado', 'Min % of gap that was filled', '%'), qualityDesc: '% of gap filled', qualityDescEs: '% del gap llenado' },
  { code: 'FGDR', eventType: 'false_gap_down_retracement', name: 'False Gap Down Retracement', nameEs: 'Retroceso Falso Gap Bajista', shortLabel: 'False Gap↓', category: 'gap', direction: 'bearish', active: true, description: 'Gap down, partial fill, then continues below open', descriptionEs: 'Gap bajista, llenado parcial, luego continúa bajo apertura', flipCode: 'FGUR', keywords: ['single print'], customSetting: cs('min_percent', 'Min % gap filled', 'Mín % gap llenado', 'Min % of gap that was filled', '%'), qualityDesc: '% of gap filled', qualityDescEs: '% del gap llenado' },

  // ═══════════════════════════════════════════════════════════════════════
  // MOVING AVERAGE CROSSES — Daily
  // ═══════════════════════════════════════════════════════════════════════

  { code: 'CA20',  eventType: 'crossed_above_sma20_daily', name: 'Crossed Above 20 Day MA', nameEs: 'Cruce Sobre SMA 20 Diaria', shortLabel: 'SMA20d ↑', category: 'ma_cross', direction: 'bullish', active: true, description: 'Crossed above 20 day moving average, volume confirmed', descriptionEs: 'Cruce sobre media móvil de 20 días, confirmado por volumen', flipCode: 'CB20', keywords: ['moving average', 'volume confirmed'], customSetting: NONE_CS },
  { code: 'CB20',  eventType: 'crossed_below_sma20_daily', name: 'Crossed Below 20 Day MA', nameEs: 'Cruce Bajo SMA 20 Diaria', shortLabel: 'SMA20d ↓', category: 'ma_cross', direction: 'bearish', active: true, description: 'Crossed below 20 day moving average, volume confirmed', descriptionEs: 'Cruce bajo media móvil de 20 días, confirmado por volumen', flipCode: 'CA20', keywords: ['moving average', 'volume confirmed'], customSetting: NONE_CS },
  { code: 'CA50',  eventType: 'crossed_above_sma50_daily', name: 'Crossed Above 50 Day MA', nameEs: 'Cruce Sobre SMA 50 Diaria', shortLabel: 'SMA50d ↑', category: 'ma_cross', direction: 'bullish', active: true, description: 'Crossed above 50 day moving average, volume confirmed', descriptionEs: 'Cruce sobre media móvil de 50 días, confirmado por volumen', flipCode: 'CB50', keywords: ['moving average', 'volume confirmed'], customSetting: NONE_CS },
  { code: 'CB50',  eventType: 'crossed_below_sma50_daily', name: 'Crossed Below 50 Day MA', nameEs: 'Cruce Bajo SMA 50 Diaria', shortLabel: 'SMA50d ↓', category: 'ma_cross', direction: 'bearish', active: true, description: 'Crossed below 50 day moving average, volume confirmed', descriptionEs: 'Cruce bajo media móvil de 50 días, confirmado por volumen', flipCode: 'CA50', keywords: ['moving average', 'volume confirmed'], customSetting: NONE_CS },
  { code: 'CA200', eventType: 'crossed_above_sma200', name: 'Crossed Above 200 Day MA', nameEs: 'Cruce Sobre SMA 200 Diaria', shortLabel: 'SMA200 ↑', category: 'ma_cross', direction: 'bullish', active: true, description: 'Crossed above 200 day moving average, volume confirmed', descriptionEs: 'Cruce sobre media móvil de 200 días, confirmado por volumen', flipCode: 'CB200', keywords: ['moving average', 'volume confirmed'], customSetting: NONE_CS },
  { code: 'CB200', eventType: 'crossed_below_sma200', name: 'Crossed Below 200 Day MA', nameEs: 'Cruce Bajo SMA 200 Diaria', shortLabel: 'SMA200 ↓', category: 'ma_cross', direction: 'bearish', active: true, description: 'Crossed below 200 day moving average, volume confirmed', descriptionEs: 'Cruce bajo media móvil de 200 días, confirmado por volumen', flipCode: 'CA200', keywords: ['moving average', 'volume confirmed'], customSetting: NONE_CS },

  // 5/8 SMA Cross — 7 timeframes
  ...([1, 2, 4, 5, 10, 20, 30] as const).flatMap(tf => [
    { code: `X5A8_${tf}`, eventType: `sma5_above_sma8_${tf}m`, name: `5 SMA Crossed Above 8 SMA (${tf} Min)`, nameEs: `SMA 5 Cruzó Sobre SMA 8 (${tf} Min)`, shortLabel: `5/8 ${tf}m↑`, category: 'ma_cross', direction: 'bullish' as const, active: true, description: `5-period SMA crosses above 8-period SMA on ${tf}-min chart. End-of-candle.`, descriptionEs: `SMA de 5 cruza sobre SMA de 8 en gráfico de ${tf} min. Al cierre de vela.`, flipCode: `X5B8_${tf}`, keywords: ['end of candle', 'moving average', 'fixed time frame'], customSetting: NONE_CS },
    { code: `X5B8_${tf}`, eventType: `sma5_below_sma8_${tf}m`, name: `5 SMA Crossed Below 8 SMA (${tf} Min)`, nameEs: `SMA 5 Cruzó Bajo SMA 8 (${tf} Min)`, shortLabel: `5/8 ${tf}m↓`, category: 'ma_cross', direction: 'bearish' as const, active: true, description: `5-period SMA crosses below 8-period SMA on ${tf}-min chart. End-of-candle.`, descriptionEs: `SMA de 5 cruza bajo SMA de 8 en gráfico de ${tf} min. Al cierre de vela.`, flipCode: `X5A8_${tf}`, keywords: ['end of candle', 'moving average', 'fixed time frame'], customSetting: NONE_CS },
  ]),

  // 8/20 SMA Cross — 3 timeframes
  ...([2, 5, 15] as const).flatMap(tf => [
    { code: `ECAY${tf}`, eventType: tf === 5 ? 'sma8_above_sma20_5min' : `sma8_above_sma20_${tf}m`, name: `8 SMA Crossed Above 20 SMA (${tf} Min)`, nameEs: `SMA 8 Cruzó Sobre SMA 20 (${tf} Min)`, shortLabel: `8/20 ${tf}m↑`, category: 'ma_cross', direction: 'bullish' as const, active: true, description: `8-period SMA crosses above 20-period SMA on ${tf}-min chart. End-of-candle.`, descriptionEs: `SMA de 8 cruza sobre SMA de 20 en gráfico de ${tf} min. Al cierre de vela.`, flipCode: `ECBY${tf}`, keywords: ['end of candle', 'moving average', 'fixed time frame'], customSetting: NONE_CS },
    { code: `ECBY${tf}`, eventType: tf === 5 ? 'sma8_below_sma20_5min' : `sma8_below_sma20_${tf}m`, name: `8 SMA Crossed Below 20 SMA (${tf} Min)`, nameEs: `SMA 8 Cruzó Bajo SMA 20 (${tf} Min)`, shortLabel: `8/20 ${tf}m↓`, category: 'ma_cross', direction: 'bearish' as const, active: true, description: `8-period SMA crosses below 20-period SMA on ${tf}-min chart. End-of-candle.`, descriptionEs: `SMA de 8 cruza bajo SMA de 20 en gráfico de ${tf} min. Al cierre de vela.`, flipCode: `ECAY${tf}`, keywords: ['end of candle', 'moving average', 'fixed time frame'], customSetting: NONE_CS },
  ]),

  // 20/200 SMA Cross — 3 timeframes
  ...([2, 5, 15] as const).flatMap(tf => [
    { code: `YCAD${tf}`, eventType: `sma20_above_sma200_${tf}m`, name: `20 SMA Crossed Above 200 SMA (${tf} Min)`, nameEs: `SMA 20 Cruzó Sobre SMA 200 (${tf} Min)`, shortLabel: `20/200 ${tf}m↑`, category: 'ma_cross', direction: 'bullish' as const, active: true, description: `20-period SMA crosses above 200-period SMA on ${tf}-min chart. End-of-candle.`, descriptionEs: `SMA de 20 cruza sobre SMA de 200 en gráfico de ${tf} min. Al cierre de vela.`, flipCode: `YCBD${tf}`, keywords: ['end of candle', 'moving average', 'fixed time frame'], customSetting: NONE_CS },
    { code: `YCBD${tf}`, eventType: `sma20_below_sma200_${tf}m`, name: `20 SMA Crossed Below 200 SMA (${tf} Min)`, nameEs: `SMA 20 Cruzó Bajo SMA 200 (${tf} Min)`, shortLabel: `20/200 ${tf}m↓`, category: 'ma_cross', direction: 'bearish' as const, active: true, description: `20-period SMA crosses below 200-period SMA on ${tf}-min chart. End-of-candle.`, descriptionEs: `SMA de 20 cruza bajo SMA de 200 en gráfico de ${tf} min. Al cierre de vela.`, flipCode: `YCAD${tf}`, keywords: ['end of candle', 'moving average', 'fixed time frame'], customSetting: NONE_CS },
  ]),

  // ═══════════════════════════════════════════════════════════════════════
  // BID / ASK MICROSTRUCTURE
  // ═══════════════════════════════════════════════════════════════════════

  { code: 'MC',   eventType: 'market_crossed',     name: 'Market Crossed',          nameEs: 'Mercado Cruzado',          shortLabel: 'Mkt Cross',   category: 'bidask', direction: 'neutral', active: true, description: 'Ask price lower than bid price', descriptionEs: 'El precio ask es menor que el bid', keywords: ['bid and ask'], customSetting: cs('min_cents', 'Min cents crossed', 'Mín centavos cruzados', '0.05 = only when bid-ask ≥ 5¢ crossed', '¢'), qualityDesc: 'Cents the market is crossed by', qualityDescEs: 'Centavos por los que el mercado está cruzado' },
  { code: 'MCU',  eventType: 'market_crossed_up',  name: 'Market Crossed Up',       nameEs: 'Mercado Cruzado Arriba',   shortLabel: 'Mkt Cross ↑', category: 'bidask', direction: 'bullish', active: true, description: 'Market crossed with upward bias', descriptionEs: 'Mercado cruzado con sesgo alcista', flipCode: 'MCD', keywords: ['bid and ask', 'listed'], customSetting: cs('min_cents', 'Min cents crossed', 'Mín centavos cruzados', '0.05 = at least 5¢ crossed', '¢'), qualityDesc: 'Cents crossed up', qualityDescEs: 'Centavos cruzados arriba' },
  { code: 'MCD',  eventType: 'market_crossed_down', name: 'Market Crossed Down',    nameEs: 'Mercado Cruzado Abajo',    shortLabel: 'Mkt Cross ↓', category: 'bidask', direction: 'bearish', active: true, description: 'Market crossed with downward bias', descriptionEs: 'Mercado cruzado con sesgo bajista', flipCode: 'MCU', keywords: ['bid and ask', 'listed'], customSetting: cs('min_cents', 'Min cents crossed', 'Mín centavos cruzados', '0.05 = at least 5¢ crossed', '¢'), qualityDesc: 'Cents crossed down', qualityDescEs: 'Centavos cruzados abajo' },
  { code: 'ML',   eventType: 'market_locked',      name: 'Market Locked',           nameEs: 'Mercado Bloqueado',        shortLabel: 'Mkt Lock',    category: 'bidask', direction: 'neutral', active: true, description: 'Bid equals ask (locked market)', descriptionEs: 'El bid es igual al ask (mercado bloqueado)', keywords: ['bid and ask'], customSetting: NONE_CS },
  { code: 'LBS',  eventType: 'large_bid_size',     name: 'Large Bid Size',          nameEs: 'Gran Tamaño Bid',          shortLabel: 'Lg Bid',      category: 'bidask', direction: 'bullish', active: true, description: 'Unusually large bid size', descriptionEs: 'Tamaño de bid inusualmente grande', flipCode: 'LAS', keywords: ['bid and ask'], customSetting: cs('min_shares', 'Min bid shares', 'Mín acciones bid', 'Min shares on best bid', 'shares'), qualityDesc: 'Shares on the bid', qualityDescEs: 'Acciones en el bid' },
  { code: 'LAS',  eventType: 'large_ask_size',     name: 'Large Ask Size',          nameEs: 'Gran Tamaño Ask',          shortLabel: 'Lg Ask',      category: 'bidask', direction: 'bearish', active: true, description: 'Unusually large ask size', descriptionEs: 'Tamaño de ask inusualmente grande', flipCode: 'LBS', keywords: ['bid and ask'], customSetting: cs('min_shares', 'Min ask shares', 'Mín acciones ask', 'Min shares on best ask', 'shares'), qualityDesc: 'Shares on the ask', qualityDescEs: 'Acciones en el ask' },
  { code: 'LSP',  eventType: 'large_spread',       name: 'Large Spread',            nameEs: 'Spread Grande',            shortLabel: 'Lg Spread',   category: 'bidask', direction: 'neutral', active: true, description: 'Specialist spread suddenly becomes large (≥50¢)', descriptionEs: 'El spread del especialista se vuelve grande (≥50¢)', keywords: ['bid and ask'], customSetting: NONE_CS },
  { code: 'TRA',  eventType: 'trading_above',      name: 'Trading Above',           nameEs: 'Operando Por Encima',      shortLabel: 'Trd Above',   category: 'bidask', direction: 'bullish', active: true, description: 'Print above best ask', descriptionEs: 'Operación por encima del mejor ask', flipCode: 'TRB', keywords: ['bid and ask', 'single print'], customSetting: cs('min_times', 'Min times', 'Mín veces', 'Min number of grouped events', 'times'), qualityDesc: 'Consecutive prints above ask', qualityDescEs: 'Prints consecutivos sobre ask' },
  { code: 'TRB',  eventType: 'trading_below',      name: 'Trading Below',           nameEs: 'Operando Por Debajo',      shortLabel: 'Trd Below',   category: 'bidask', direction: 'bearish', active: true, description: 'Print below best bid', descriptionEs: 'Operación por debajo del mejor bid', flipCode: 'TRA', keywords: ['bid and ask', 'single print'], customSetting: cs('min_times', 'Min times', 'Mín veces', 'Min number of grouped events', 'times'), qualityDesc: 'Consecutive prints below bid', qualityDescEs: 'Prints consecutivos bajo bid' },
  { code: 'TRAS', eventType: 'trading_above_specialist', name: 'Trading Above Specialist', nameEs: 'Operando Sobre Especialista', shortLabel: 'Trd Abv Spec', category: 'bidask', direction: 'bullish', active: true, description: 'Print above specialist offer (NYSE/AMEX)', descriptionEs: 'Operación sobre oferta del especialista (NYSE/AMEX)', flipCode: 'TRBS', keywords: ['bid and ask', 'listed'], customSetting: cs('min_times', 'Min times', 'Mín veces', 'Min grouped events', 'times'), qualityDesc: 'Consecutive prints above specialist', qualityDescEs: 'Prints consecutivos sobre especialista' },
  { code: 'TRBS', eventType: 'trading_below_specialist', name: 'Trading Below Specialist', nameEs: 'Operando Bajo Especialista', shortLabel: 'Trd Blw Spec', category: 'bidask', direction: 'bearish', active: true, description: 'Print below specialist bid (NYSE/AMEX)', descriptionEs: 'Operación bajo bid del especialista (NYSE/AMEX)', flipCode: 'TRAS', keywords: ['bid and ask', 'listed'], customSetting: cs('min_times', 'Min times', 'Mín veces', 'Min grouped events', 'times'), qualityDesc: 'Consecutive prints below specialist', qualityDescEs: 'Prints consecutivos bajo especialista' },

  // ═══════════════════════════════════════════════════════════════════════
  // HALTS
  // ═══════════════════════════════════════════════════════════════════════

  { code: 'HALT',   eventType: 'halt',             name: 'Halt',                    nameEs: 'Halt',                     shortLabel: 'HALT',        category: 'halt', direction: 'neutral', active: true, description: 'Trading halt triggered', descriptionEs: 'Se activó una parada de trading', keywords: [], customSetting: NONE_CS },
  { code: 'RESUME', eventType: 'resume',           name: 'Resume',                  nameEs: 'Reanudación',              shortLabel: 'RESUME',      category: 'halt', direction: 'neutral', active: true, description: 'Trading resumes after halt', descriptionEs: 'El trading se reanuda después de una parada', keywords: [], customSetting: NONE_CS },

  // ═══════════════════════════════════════════════════════════════════════
  // SESSION — Pre/Post Market
  // ═══════════════════════════════════════════════════════════════════════

  { code: 'HPRE',  eventType: 'pre_market_high',   name: 'Pre-Market High',         nameEs: 'Máximo Pre-Market',        shortLabel: 'Pre High',    category: 'session', direction: 'bullish', active: true, description: 'New pre-market high', descriptionEs: 'Nuevo máximo en pre-market', flipCode: 'LPRE', keywords: ['highs and lows', 'single print'], customSetting: cs('lookback_days', 'Min lookback days', 'Mín días lookback', '0=any, 1=above yesterday, 365=52-week', 'days', 0), qualityDesc: 'Lookback period', qualityDescEs: 'Período lookback' },
  { code: 'LPRE',  eventType: 'pre_market_low',    name: 'Pre-Market Low',          nameEs: 'Mínimo Pre-Market',        shortLabel: 'Pre Low',     category: 'session', direction: 'bearish', active: true, description: 'New pre-market low', descriptionEs: 'Nuevo mínimo en pre-market', flipCode: 'HPRE', keywords: ['highs and lows', 'single print'], customSetting: cs('lookback_days', 'Min lookback days', 'Mín días lookback', '0=any, 1=below yesterday, 365=52-week', 'days', 0), qualityDesc: 'Lookback period', qualityDescEs: 'Período lookback' },
  { code: 'HPOST', eventType: 'post_market_high',  name: 'Post-Market High',        nameEs: 'Máximo Post-Market',       shortLabel: 'Post High',   category: 'session', direction: 'bullish', active: true, description: 'New post-market high', descriptionEs: 'Nuevo máximo en post-market', flipCode: 'LPOST', keywords: ['highs and lows', 'single print'], customSetting: cs('lookback_days', 'Min lookback days', 'Mín días lookback', '0=any, 1=above today high, 365=52-week', 'days', 0), qualityDesc: 'Lookback period', qualityDescEs: 'Período lookback' },
  { code: 'LPOST', eventType: 'post_market_low',   name: 'Post-Market Low',         nameEs: 'Mínimo Post-Market',       shortLabel: 'Post Low',    category: 'session', direction: 'bearish', active: true, description: 'New post-market low', descriptionEs: 'Nuevo mínimo en post-market', flipCode: 'HPOST', keywords: ['highs and lows', 'single print'], customSetting: cs('lookback_days', 'Min lookback days', 'Mín días lookback', '0=any, 1=below today low, 365=52-week', 'days', 0), qualityDesc: 'Lookback period', qualityDescEs: 'Período lookback' },

  // ═══════════════════════════════════════════════════════════════════════
  // ORB — Opening Range Breakout (7 timeframes)
  // ═══════════════════════════════════════════════════════════════════════

  ...([1, 2, 5, 10, 15, 30, 60] as const).flatMap(tf => [
    { code: `ORU${tf}`, eventType: `orb_up_${tf}min`, name: `${tf} Min ORB Breakout`, nameEs: `Ruptura ORB ${tf} Min`, shortLabel: `ORB${tf} ↑`, category: 'orb', direction: 'bullish' as const, active: true, description: `Price breaks above ${tf}-min opening range high`, descriptionEs: `El precio rompe el máximo del rango de apertura de ${tf} min`, flipCode: `ORD${tf}`, keywords: ['opening range', 'breakout', `${tf}min`], customSetting: cs('min_percent', 'Min range %', 'Mín rango %', '0.5 = only when ORB range ≥ 0.5%', '%'), qualityDesc: `${tf}-min ORB range width %`, qualityDescEs: `Ancho del rango ORB de ${tf} min %` },
    { code: `ORD${tf}`, eventType: `orb_down_${tf}min`, name: `${tf} Min ORB Breakdown`, nameEs: `Quiebre ORB ${tf} Min`, shortLabel: `ORB${tf} ↓`, category: 'orb', direction: 'bearish' as const, active: true, description: `Price breaks below ${tf}-min opening range low`, descriptionEs: `El precio rompe el mínimo del rango de apertura de ${tf} min`, flipCode: `ORU${tf}`, keywords: ['opening range', 'breakdown', `${tf}min`], customSetting: cs('min_percent', 'Min range %', 'Mín rango %', '0.5 = only when ORB range ≥ 0.5%', '%'), qualityDesc: `${tf}-min ORB range width %`, qualityDescEs: `Ancho del rango ORB de ${tf} min %` },
  ]),

  // ═══════════════════════════════════════════════════════════════════════
  // CONSOLIDATION / CHANNEL
  // ═══════════════════════════════════════════════════════════════════════

  { code: 'C',     eventType: 'consolidation',     name: 'Consolidation',           nameEs: 'Consolidación',            shortLabel: 'Consol',      category: 'consol', direction: 'neutral', active: true, description: 'Stock price changing significantly less than normal', descriptionEs: 'El precio cambia significativamente menos de lo normal', keywords: ['price vs time', 'volume confirmed'], customSetting: cs('quality_ratio', 'Min quality', 'Mín calidad', '2=default, 5=tight, 10=perfect', '', 2), qualityDesc: 'Z-score of consolidation', qualityDescEs: 'Z-score de la consolidación' },
  { code: 'CHBO',  eventType: 'channel_breakout',  name: 'Channel Breakout',        nameEs: 'Ruptura de Canal',         shortLabel: 'Ch Break ↑',  category: 'consol', direction: 'bullish', active: true, description: 'Fast channel breakout. ~1 min timescale.', descriptionEs: 'Ruptura rápida de canal. ~1 min.', flipCode: 'CHBD', keywords: [], customSetting: cs('quality_ratio', 'Min consolidation quality', 'Mín calidad consolidación', '2=min, 5=tight, 10=best', ''), qualityDesc: 'Z-score of consolidation broken', qualityDescEs: 'Z-score del patrón de consolidación roto' },
  { code: 'CHBD',  eventType: 'channel_breakdown',  name: 'Channel Breakdown',      nameEs: 'Quiebre de Canal',         shortLabel: 'Ch Break ↓',  category: 'consol', direction: 'bearish', active: true, description: 'Fast channel breakdown. ~1 min timescale.', descriptionEs: 'Quiebre rápido de canal. ~1 min.', flipCode: 'CHBO', keywords: [], customSetting: cs('quality_ratio', 'Min consolidation quality', 'Mín calidad consolidación', '2=min, 5=tight, 10=best', ''), qualityDesc: 'Z-score of consolidation broken', qualityDescEs: 'Z-score del patrón de consolidación roto' },
  { code: 'CHBOC', eventType: 'channel_breakout_confirmed', name: 'Channel Breakout (confirmed)', nameEs: 'Ruptura de Canal (confirmada)', shortLabel: 'Ch Brk ↑ Conf', category: 'consol', direction: 'bullish', active: true, description: 'Volume confirmed channel breakout. ~15 min.', descriptionEs: 'Ruptura de canal confirmada por volumen. ~15 min.', flipCode: 'CHBDC', keywords: ['volume confirmed'], customSetting: cs('quality_ratio', 'Min quality', 'Mín calidad', '1.0=all, 5.0+=briskly, 10=top 1%', ''), qualityDesc: 'Momentum/volatility ratio', qualityDescEs: 'Ratio momentum/volatilidad' },
  { code: 'CHBDC', eventType: 'channel_breakdown_confirmed', name: 'Channel Breakdown (confirmed)', nameEs: 'Quiebre de Canal (confirmado)', shortLabel: 'Ch Brk ↓ Conf', category: 'consol', direction: 'bearish', active: true, description: 'Volume confirmed channel breakdown. ~15 min.', descriptionEs: 'Quiebre de canal confirmado por volumen. ~15 min.', flipCode: 'CHBOC', keywords: ['volume confirmed'], customSetting: cs('quality_ratio', 'Min quality', 'Mín calidad', '1.0=all, 5.0+=briskly, 10=top 1%', ''), qualityDesc: 'Momentum/volatility ratio', qualityDescEs: 'Ratio momentum/volatilidad' },

  // Fixed-timeframe consolidation breakout/breakdown
  ...([5, 10, 15, 30] as const).flatMap(tf => [
    { code: `CBO${tf}`, eventType: `consol_breakout_${tf}m`, name: `${tf} Min Consolidation Breakout`, nameEs: `Ruptura Consolidación ${tf} Min`, shortLabel: `CBO${tf}`, category: 'consol', direction: 'bullish' as const, active: true, description: `Price broke above ${tf}-min consolidation channel`, descriptionEs: `Precio rompió sobre canal de consolidación de ${tf} min`, flipCode: `CBD${tf}`, keywords: ['fixed time frame', 'single print'], customSetting: cs('min_cents', `Min $ above channel`, `Mín $ sobre canal`, 'Dollar distance above channel top', '$'), qualityDesc: '$ above channel top', qualityDescEs: '$ sobre techo del canal' },
    { code: `CBD${tf}`, eventType: `consol_breakdown_${tf}m`, name: `${tf} Min Consolidation Breakdown`, nameEs: `Quiebre Consolidación ${tf} Min`, shortLabel: `CBD${tf}`, category: 'consol', direction: 'bearish' as const, active: true, description: `Price broke below ${tf}-min consolidation channel`, descriptionEs: `Precio rompió bajo canal de consolidación de ${tf} min`, flipCode: `CBO${tf}`, keywords: ['fixed time frame', 'single print'], customSetting: cs('min_cents', `Min $ below channel`, `Mín $ bajo canal`, 'Dollar distance below channel bottom', '$'), qualityDesc: '$ below channel bottom', qualityDescEs: '$ bajo piso del canal' },
  ]),

  // ═══════════════════════════════════════════════════════════════════════
  // GEOMETRIC PATTERNS
  // ═══════════════════════════════════════════════════════════════════════

  { code: 'GBBOT', eventType: 'broadening_bottom', name: 'Broadening Bottom',       nameEs: 'Fondo Ensanchado',         shortLabel: 'Broad Bot',   category: 'geometric', direction: 'bullish', active: true, description: 'Broadening pattern: price touched bottom, turned back up. 5+ turning points.', descriptionEs: 'Patrón ensanchamiento: precio tocó fondo, subió. 5+ puntos de giro.', flipCode: 'GBTOP', keywords: ['geometric pattern', 'volume confirmed'], customSetting: cs('min_hours', 'Min hours', 'Mín horas', '6.5 = full trading day. 7.5 = including pre/post.', 'hours'), qualityDesc: 'Hours since pattern established', qualityDescEs: 'Horas desde que se estableció el patrón' },
  { code: 'GBTOP', eventType: 'broadening_top',    name: 'Broadening Top',          nameEs: 'Techo Ensanchado',         shortLabel: 'Broad Top',   category: 'geometric', direction: 'bearish', active: true, description: 'Broadening pattern: price touched top, turned back down. 5+ turning points.', descriptionEs: 'Patrón ensanchamiento: precio tocó techo, bajó. 5+ puntos de giro.', flipCode: 'GBBOT', keywords: ['geometric pattern', 'volume confirmed'], customSetting: cs('min_hours', 'Min hours', 'Mín horas', '6.5 = full trading day. 7.5 = including pre/post.', 'hours'), qualityDesc: 'Hours since pattern established', qualityDescEs: 'Horas desde que se estableció el patrón' },

  { code: 'GTBOT', eventType: 'triangle_bottom',   name: 'Triangle Bottom',         nameEs: 'Triángulo Inferior',       shortLabel: 'Tri Bot',     category: 'geometric', direction: 'bullish', active: true, description: 'Triangle pattern (converging): lower highs + higher lows. 5+ turning points. First point is low, ends going up.', descriptionEs: 'Patrón triángulo (convergente): máximos decrecientes + mínimos crecientes. 5+ puntos. Primer punto es mínimo, termina subiendo.', flipCode: 'GTTOP', keywords: ['geometric pattern', 'volume confirmed'], customSetting: cs('min_hours', 'Min hours', 'Mín horas', '6.5 = full trading day. 7.5 = including pre/post.', 'hours'), qualityDesc: 'Hours since pattern established', qualityDescEs: 'Horas desde que se estableció el patrón' },
  { code: 'GTTOP', eventType: 'triangle_top',       name: 'Triangle Top',            nameEs: 'Triángulo Superior',       shortLabel: 'Tri Top',     category: 'geometric', direction: 'bearish', active: true, description: 'Triangle pattern (converging): lower highs + higher lows. 5+ turning points. First point is high, ends going down.', descriptionEs: 'Patrón triángulo (convergente): máximos decrecientes + mínimos crecientes. 5+ puntos. Primer punto es máximo, termina bajando.', flipCode: 'GTBOT', keywords: ['geometric pattern', 'volume confirmed'], customSetting: cs('min_hours', 'Min hours', 'Mín horas', '6.5 = full trading day. 7.5 = including pre/post.', 'hours'), qualityDesc: 'Hours since pattern established', qualityDescEs: 'Horas desde que se estableció el patrón' },

  { code: 'GRBOT', eventType: 'rectangle_bottom',   name: 'Rectangle Bottom',        nameEs: 'Rectángulo Inferior',      shortLabel: 'Rect Bot',    category: 'geometric', direction: 'bullish', active: true, description: 'Rectangle pattern: highs and lows at approximately the same prices. 5+ turning points. Last point is low (price going up).', descriptionEs: 'Patrón rectángulo: máximos y mínimos a aproximadamente los mismos precios. 5+ puntos. Último punto es mínimo (precio subiendo).', flipCode: 'GRTOP', keywords: ['geometric pattern', 'volume confirmed'], customSetting: cs('min_hours', 'Min hours', 'Mín horas', '6.5 = full trading day. 7.5 = including pre/post.', 'hours'), qualityDesc: 'Hours since pattern established', qualityDescEs: 'Horas desde que se estableció el patrón' },
  { code: 'GRTOP', eventType: 'rectangle_top',       name: 'Rectangle Top',           nameEs: 'Rectángulo Superior',      shortLabel: 'Rect Top',    category: 'geometric', direction: 'bearish', active: true, description: 'Rectangle pattern: highs and lows at approximately the same prices. 5+ turning points. Last point is high (price going down).', descriptionEs: 'Patrón rectángulo: máximos y mínimos a aproximadamente los mismos precios. 5+ puntos. Último punto es máximo (precio bajando).', flipCode: 'GRBOT', keywords: ['geometric pattern', 'volume confirmed'], customSetting: cs('min_hours', 'Min hours', 'Mín horas', '6.5 = full trading day. 7.5 = including pre/post.', 'hours'), qualityDesc: 'Hours since pattern established', qualityDescEs: 'Horas desde que se estableció el patrón' },

  { code: 'GDBOT', eventType: 'double_bottom',       name: 'Double Bottom',           nameEs: 'Doble Suelo',              shortLabel: 'Dbl Bot',     category: 'geometric', direction: 'bullish', active: true, description: 'Two or more lows at approximately the same price with significant time/volume between them. Also reports triple/quadruple bottoms.', descriptionEs: 'Dos o más mínimos a aproximadamente el mismo precio con tiempo/volumen significativo entre ellos. También reporta triple/cuádruple suelos.', flipCode: 'GDTOP', keywords: ['geometric pattern', 'volume confirmed'], customSetting: cs('min_hours', 'Min hours', 'Mín horas', '6.5 = full trading day. 7.5 = including pre/post.', 'hours'), qualityDesc: 'Hours since pattern established', qualityDescEs: 'Horas desde que se estableció el patrón' },
  { code: 'GDTOP', eventType: 'double_top',           name: 'Double Top',              nameEs: 'Doble Techo',              shortLabel: 'Dbl Top',     category: 'geometric', direction: 'bearish', active: true, description: 'Two or more highs at approximately the same price with significant time/volume between them. Also reports triple/quadruple tops.', descriptionEs: 'Dos o más máximos a aproximadamente el mismo precio con tiempo/volumen significativo entre ellos. También reporta triple/cuádruple techos.', flipCode: 'GDBOT', keywords: ['geometric pattern', 'volume confirmed'], customSetting: cs('min_hours', 'Min hours', 'Mín horas', '6.5 = full trading day. 7.5 = including pre/post.', 'hours'), qualityDesc: 'Hours since pattern established', qualityDescEs: 'Horas desde que se estableció el patrón' },

  { code: 'GHASI', eventType: 'head_and_shoulders_inv', name: 'Inverted Head and Shoulders', nameEs: 'Hombro Cabeza Hombro Invertido', shortLabel: 'Inv H&S', category: 'geometric', direction: 'bullish', active: true, description: 'Exactly 5 turning points: L-H-L-H-L where middle low is lowest, shoulders (~same), neckline (~same). Bullish reversal.', descriptionEs: 'Exactamente 5 puntos: L-H-L-H-L donde el mínimo central es el más bajo, hombros (~iguales), línea de cuello (~igual). Reversión alcista.', flipCode: 'GHAS', keywords: ['geometric pattern', 'volume confirmed'], customSetting: cs('min_hours', 'Min hours', 'Mín horas', '6.5 = full trading day. 7.5 = including pre/post.', 'hours'), qualityDesc: 'Hours since pattern established', qualityDescEs: 'Horas desde que se estableció el patrón' },
  { code: 'GHAS',  eventType: 'head_and_shoulders',     name: 'Head and Shoulders',          nameEs: 'Hombro Cabeza Hombro',          shortLabel: 'H&S',     category: 'geometric', direction: 'bearish', active: true, description: 'Exactly 5 turning points: H-L-H-L-H where middle high is highest, shoulders (~same), neckline (~same). Bearish reversal.', descriptionEs: 'Exactamente 5 puntos: H-L-H-L-H donde el máximo central es el más alto, hombros (~iguales), línea de cuello (~igual). Reversión bajista.', flipCode: 'GHASI', keywords: ['geometric pattern', 'volume confirmed'], customSetting: cs('min_hours', 'Min hours', 'Mín horas', '6.5 = full trading day. 7.5 = including pre/post.', 'hours'), qualityDesc: 'Hours since pattern established', qualityDescEs: 'Horas desde que se estableció el patrón' },

  // ═══════════════════════════════════════════════════════════════════════
  // MULTI-TIMEFRAME INDICATORS (5-min)
  // ═══════════════════════════════════════════════════════════════════════

  // ECAY5/ECBY5 moved to SMA Cross section in ma_cross category
  // ── MACD Cross Alerts (5 timeframes × 4 cross types = 20 alerts) ──
  // TI: Standard MACD (26/12/9 EMA). Single Print (no candle wait). quality=0, no custom settings.
  // 5 min
  { code: 'MDAS5', eventType: 'macd_above_signal_5min', name: '5 minute MACD crossed above signal', nameEs: 'MACD 5 min cruzó sobre señal', shortLabel: 'MACD Sig 5m↑', category: 'indicator', direction: 'bullish', active: true, description: 'MACD line crosses above signal line on 5-min chart', descriptionEs: 'Línea MACD cruza sobre línea de señal en gráfico de 5 min', flipCode: 'MDBS5', keywords: ['macd', 'single print', 'fixed time frame'], customSetting: NONE_CS },
  { code: 'MDBS5', eventType: 'macd_below_signal_5min', name: '5 minute MACD crossed below signal', nameEs: 'MACD 5 min cruzó bajo señal', shortLabel: 'MACD Sig 5m↓', category: 'indicator', direction: 'bearish', active: true, description: 'MACD line crosses below signal line on 5-min chart', descriptionEs: 'Línea MACD cruza bajo línea de señal en gráfico de 5 min', flipCode: 'MDAS5', keywords: ['macd', 'single print', 'fixed time frame'], customSetting: NONE_CS },
  { code: 'MDAZ5', eventType: 'macd_above_zero_5min', name: '5 minute MACD crossed above zero', nameEs: 'MACD 5 min cruzó sobre cero', shortLabel: 'MACD 0 5m↑', category: 'indicator', direction: 'bullish', active: true, description: 'MACD line crosses above zero on 5-min chart', descriptionEs: 'Línea MACD cruza sobre cero en gráfico de 5 min', flipCode: 'MDBZ5', keywords: ['macd', 'single print', 'fixed time frame'], customSetting: NONE_CS },
  { code: 'MDBZ5', eventType: 'macd_below_zero_5min', name: '5 minute MACD crossed below zero', nameEs: 'MACD 5 min cruzó bajo cero', shortLabel: 'MACD 0 5m↓', category: 'indicator', direction: 'bearish', active: true, description: 'MACD line crosses below zero on 5-min chart', descriptionEs: 'Línea MACD cruza bajo cero en gráfico de 5 min', flipCode: 'MDAZ5', keywords: ['macd', 'single print', 'fixed time frame'], customSetting: NONE_CS },
  // 10 min
  { code: 'MDAS10', eventType: 'macd_above_signal_10m', name: '10 minute MACD crossed above signal', nameEs: 'MACD 10 min cruzó sobre señal', shortLabel: 'MACD Sig 10m↑', category: 'indicator', direction: 'bullish', active: true, description: 'MACD line crosses above signal line on 10-min chart', descriptionEs: 'Línea MACD cruza sobre línea de señal en gráfico de 10 min', flipCode: 'MDBS10', keywords: ['macd', 'single print', 'fixed time frame'], customSetting: NONE_CS },
  { code: 'MDBS10', eventType: 'macd_below_signal_10m', name: '10 minute MACD crossed below signal', nameEs: 'MACD 10 min cruzó bajo señal', shortLabel: 'MACD Sig 10m↓', category: 'indicator', direction: 'bearish', active: true, description: 'MACD line crosses below signal line on 10-min chart', descriptionEs: 'Línea MACD cruza bajo línea de señal en gráfico de 10 min', flipCode: 'MDAS10', keywords: ['macd', 'single print', 'fixed time frame'], customSetting: NONE_CS },
  { code: 'MDAZ10', eventType: 'macd_above_zero_10m', name: '10 minute MACD crossed above zero', nameEs: 'MACD 10 min cruzó sobre cero', shortLabel: 'MACD 0 10m↑', category: 'indicator', direction: 'bullish', active: true, description: 'MACD line crosses above zero on 10-min chart', descriptionEs: 'Línea MACD cruza sobre cero en gráfico de 10 min', flipCode: 'MDBZ10', keywords: ['macd', 'single print', 'fixed time frame'], customSetting: NONE_CS },
  { code: 'MDBZ10', eventType: 'macd_below_zero_10m', name: '10 minute MACD crossed below zero', nameEs: 'MACD 10 min cruzó bajo cero', shortLabel: 'MACD 0 10m↓', category: 'indicator', direction: 'bearish', active: true, description: 'MACD line crosses below zero on 10-min chart', descriptionEs: 'Línea MACD cruza bajo cero en gráfico de 10 min', flipCode: 'MDAZ10', keywords: ['macd', 'single print', 'fixed time frame'], customSetting: NONE_CS },
  // 15 min
  { code: 'MDAS15', eventType: 'macd_above_signal_15m', name: '15 minute MACD crossed above signal', nameEs: 'MACD 15 min cruzó sobre señal', shortLabel: 'MACD Sig 15m↑', category: 'indicator', direction: 'bullish', active: true, description: 'MACD line crosses above signal line on 15-min chart', descriptionEs: 'Línea MACD cruza sobre línea de señal en gráfico de 15 min', flipCode: 'MDBS15', keywords: ['macd', 'single print', 'fixed time frame'], customSetting: NONE_CS },
  { code: 'MDBS15', eventType: 'macd_below_signal_15m', name: '15 minute MACD crossed below signal', nameEs: 'MACD 15 min cruzó bajo señal', shortLabel: 'MACD Sig 15m↓', category: 'indicator', direction: 'bearish', active: true, description: 'MACD line crosses below signal line on 15-min chart', descriptionEs: 'Línea MACD cruza bajo línea de señal en gráfico de 15 min', flipCode: 'MDAS15', keywords: ['macd', 'single print', 'fixed time frame'], customSetting: NONE_CS },
  { code: 'MDAZ15', eventType: 'macd_above_zero_15m', name: '15 minute MACD crossed above zero', nameEs: 'MACD 15 min cruzó sobre cero', shortLabel: 'MACD 0 15m↑', category: 'indicator', direction: 'bullish', active: true, description: 'MACD line crosses above zero on 15-min chart', descriptionEs: 'Línea MACD cruza sobre cero en gráfico de 15 min', flipCode: 'MDBZ15', keywords: ['macd', 'single print', 'fixed time frame'], customSetting: NONE_CS },
  { code: 'MDBZ15', eventType: 'macd_below_zero_15m', name: '15 minute MACD crossed below zero', nameEs: 'MACD 15 min cruzó bajo cero', shortLabel: 'MACD 0 15m↓', category: 'indicator', direction: 'bearish', active: true, description: 'MACD line crosses below zero on 15-min chart', descriptionEs: 'Línea MACD cruza bajo cero en gráfico de 15 min', flipCode: 'MDAZ15', keywords: ['macd', 'single print', 'fixed time frame'], customSetting: NONE_CS },
  // 30 min
  { code: 'MDAS30', eventType: 'macd_above_signal_30m', name: '30 minute MACD crossed above signal', nameEs: 'MACD 30 min cruzó sobre señal', shortLabel: 'MACD Sig 30m↑', category: 'indicator', direction: 'bullish', active: true, description: 'MACD line crosses above signal line on 30-min chart', descriptionEs: 'Línea MACD cruza sobre línea de señal en gráfico de 30 min', flipCode: 'MDBS30', keywords: ['macd', 'single print', 'fixed time frame'], customSetting: NONE_CS },
  { code: 'MDBS30', eventType: 'macd_below_signal_30m', name: '30 minute MACD crossed below signal', nameEs: 'MACD 30 min cruzó bajo señal', shortLabel: 'MACD Sig 30m↓', category: 'indicator', direction: 'bearish', active: true, description: 'MACD line crosses below signal line on 30-min chart', descriptionEs: 'Línea MACD cruza bajo línea de señal en gráfico de 30 min', flipCode: 'MDAS30', keywords: ['macd', 'single print', 'fixed time frame'], customSetting: NONE_CS },
  { code: 'MDAZ30', eventType: 'macd_above_zero_30m', name: '30 minute MACD crossed above zero', nameEs: 'MACD 30 min cruzó sobre cero', shortLabel: 'MACD 0 30m↑', category: 'indicator', direction: 'bullish', active: true, description: 'MACD line crosses above zero on 30-min chart', descriptionEs: 'Línea MACD cruza sobre cero en gráfico de 30 min', flipCode: 'MDBZ30', keywords: ['macd', 'single print', 'fixed time frame'], customSetting: NONE_CS },
  { code: 'MDBZ30', eventType: 'macd_below_zero_30m', name: '30 minute MACD crossed below zero', nameEs: 'MACD 30 min cruzó bajo cero', shortLabel: 'MACD 0 30m↓', category: 'indicator', direction: 'bearish', active: true, description: 'MACD line crosses below zero on 30-min chart', descriptionEs: 'Línea MACD cruza bajo cero en gráfico de 30 min', flipCode: 'MDAZ30', keywords: ['macd', 'single print', 'fixed time frame'], customSetting: NONE_CS },
  // 60 min
  { code: 'MDAS60', eventType: 'macd_above_signal_60m', name: '60 minute MACD crossed above signal', nameEs: 'MACD 60 min cruzó sobre señal', shortLabel: 'MACD Sig 60m↑', category: 'indicator', direction: 'bullish', active: true, description: 'MACD line crosses above signal line on 60-min chart', descriptionEs: 'Línea MACD cruza sobre línea de señal en gráfico de 60 min', flipCode: 'MDBS60', keywords: ['macd', 'single print', 'fixed time frame'], customSetting: NONE_CS },
  { code: 'MDBS60', eventType: 'macd_below_signal_60m', name: '60 minute MACD crossed below signal', nameEs: 'MACD 60 min cruzó bajo señal', shortLabel: 'MACD Sig 60m↓', category: 'indicator', direction: 'bearish', active: true, description: 'MACD line crosses below signal line on 60-min chart', descriptionEs: 'Línea MACD cruza bajo línea de señal en gráfico de 60 min', flipCode: 'MDAS60', keywords: ['macd', 'single print', 'fixed time frame'], customSetting: NONE_CS },
  { code: 'MDAZ60', eventType: 'macd_above_zero_60m', name: '60 minute MACD crossed above zero', nameEs: 'MACD 60 min cruzó sobre cero', shortLabel: 'MACD 0 60m↑', category: 'indicator', direction: 'bullish', active: true, description: 'MACD line crosses above zero on 60-min chart', descriptionEs: 'Línea MACD cruza sobre cero en gráfico de 60 min', flipCode: 'MDBZ60', keywords: ['macd', 'single print', 'fixed time frame'], customSetting: NONE_CS },
  { code: 'MDBZ60', eventType: 'macd_below_zero_60m', name: '60 minute MACD crossed below zero', nameEs: 'MACD 60 min cruzó bajo cero', shortLabel: 'MACD 0 60m↓', category: 'indicator', direction: 'bearish', active: true, description: 'MACD line crosses below zero on 60-min chart', descriptionEs: 'Línea MACD cruza bajo cero en gráfico de 60 min', flipCode: 'MDAZ60', keywords: ['macd', 'single print', 'fixed time frame'], customSetting: NONE_CS },
  // ── Stochastic Cross Alerts (3 timeframes × 2 = 6 alerts) ──
  // TI: Standard Stochastic (14-period). Single Print. Crossed above 20 = no longer oversold. Crossed below 80 = no longer overbought.
  // 5 min
  { code: 'SC20_5', eventType: 'stoch_cross_bullish_5min', name: '5 minute stochastic crossed above 20', nameEs: 'Estocástico 5 min cruzó sobre 20', shortLabel: 'Stoch 5m↑20', category: 'indicator', direction: 'bullish', active: true, description: 'Stochastic %K crosses above 20 (no longer oversold) on 5-min chart', descriptionEs: 'Estocástico %K cruza sobre 20 (ya no sobrevendido) en gráfico de 5 min', flipCode: 'SC80_5', keywords: ['stochastic', 'single print', 'fixed time frame'], customSetting: NONE_CS },
  { code: 'SC80_5', eventType: 'stoch_cross_bearish_5min', name: '5 minute stochastic crossed below 80', nameEs: 'Estocástico 5 min cruzó bajo 80', shortLabel: 'Stoch 5m↓80', category: 'indicator', direction: 'bearish', active: true, description: 'Stochastic %K crosses below 80 (no longer overbought) on 5-min chart', descriptionEs: 'Estocástico %K cruza bajo 80 (ya no sobrecomprado) en gráfico de 5 min', flipCode: 'SC20_5', keywords: ['stochastic', 'single print', 'fixed time frame'], customSetting: NONE_CS },
  // 15 min
  { code: 'SC20_15', eventType: 'stoch_cross_bullish_15m', name: '15 minute stochastic crossed above 20', nameEs: 'Estocástico 15 min cruzó sobre 20', shortLabel: 'Stoch 15m↑20', category: 'indicator', direction: 'bullish', active: true, description: 'Stochastic %K crosses above 20 (no longer oversold) on 15-min chart', descriptionEs: 'Estocástico %K cruza sobre 20 (ya no sobrevendido) en gráfico de 15 min', flipCode: 'SC80_15', keywords: ['stochastic', 'single print', 'fixed time frame'], customSetting: NONE_CS },
  { code: 'SC80_15', eventType: 'stoch_cross_bearish_15m', name: '15 minute stochastic crossed below 80', nameEs: 'Estocástico 15 min cruzó bajo 80', shortLabel: 'Stoch 15m↓80', category: 'indicator', direction: 'bearish', active: true, description: 'Stochastic %K crosses below 80 (no longer overbought) on 15-min chart', descriptionEs: 'Estocástico %K cruza bajo 80 (ya no sobrecomprado) en gráfico de 15 min', flipCode: 'SC20_15', keywords: ['stochastic', 'single print', 'fixed time frame'], customSetting: NONE_CS },
  // 60 min
  { code: 'SC20_60', eventType: 'stoch_cross_bullish_60m', name: '60 minute stochastic crossed above 20', nameEs: 'Estocástico 60 min cruzó sobre 20', shortLabel: 'Stoch 60m↑20', category: 'indicator', direction: 'bullish', active: true, description: 'Stochastic %K crosses above 20 (no longer oversold) on 60-min chart', descriptionEs: 'Estocástico %K cruza sobre 20 (ya no sobrevendido) en gráfico de 60 min', flipCode: 'SC80_60', keywords: ['stochastic', 'single print', 'fixed time frame'], customSetting: NONE_CS },
  { code: 'SC80_60', eventType: 'stoch_cross_bearish_60m', name: '60 minute stochastic crossed below 80', nameEs: 'Estocástico 60 min cruzó bajo 80', shortLabel: 'Stoch 60m↓80', category: 'indicator', direction: 'bearish', active: true, description: 'Stochastic %K crosses below 80 (no longer overbought) on 60-min chart', descriptionEs: 'Estocástico %K cruza bajo 80 (ya no sobrecomprado) en gráfico de 60 min', flipCode: 'SC20_60', keywords: ['stochastic', 'single print', 'fixed time frame'], customSetting: NONE_CS },

  // ═══════════════════════════════════════════════════════════════════════
  // N-MINUTE HIGH/LOW (Candlestick)
  // ═══════════════════════════════════════════════════════════════════════

  ...([5, 10, 15, 30, 60] as const).flatMap(tf => [
    { code: `IDH${tf}`, eventType: `intraday_high_${tf}m`, name: `${tf} Minute High`, nameEs: `Máximo ${tf} Minutos`, shortLabel: `${tf}m High`, category: 'candle', direction: 'bullish' as const, active: true, description: `New intraday high on ${tf}-min candlestick chart`, descriptionEs: `Nuevo máximo intradía en gráfico de velas de ${tf} min`, flipCode: `IDL${tf}`, keywords: ['fixed time frame', 'candlestick'], customSetting: NONE_CS },
    { code: `IDL${tf}`, eventType: `intraday_low_${tf}m`, name: `${tf} Minute Low`, nameEs: `Mínimo ${tf} Minutos`, shortLabel: `${tf}m Low`, category: 'candle', direction: 'bearish' as const, active: true, description: `New intraday low on ${tf}-min candlestick chart`, descriptionEs: `Nuevo mínimo intradía en gráfico de velas de ${tf} min`, flipCode: `IDH${tf}`, keywords: ['fixed time frame', 'candlestick'], customSetting: NONE_CS },
  ]),

  // ── Trailing Stops ──────────────────────────────────────────────────
  { code: 'TSPU', eventType: 'trailing_stop_pct_up', name: 'Trailing Stop, % Up', nameEs: 'Trailing Stop, % Arriba', shortLabel: 'TS% Up', category: 'trailing', direction: 'bullish', active: true, description: 'Price moves up from local low. First at 0.5%, re-fire every 0.25%. Any single print can be the turning point.', descriptionEs: 'Precio sube desde mínimo local. Primera alerta al 0.5%, luego cada 0.25%. Cualquier print puede ser punto de giro.', flipCode: 'TSPD', keywords: [], customSetting: cs('min_percent', 'Period multiplier', 'Multiplicador periodo', '2 = alerts at 2%, 4%, 6%. Leave blank for default.', '%'), qualityDesc: '% move up from the local low', qualityDescEs: '% de subida desde el mínimo local' },
  { code: 'TSPD', eventType: 'trailing_stop_pct_down', name: 'Trailing Stop, % Down', nameEs: 'Trailing Stop, % Abajo', shortLabel: 'TS% Down', category: 'trailing', direction: 'bearish', active: true, description: 'Price moves down from local high. First at 0.5%, re-fire every 0.25%. Any single print can be the turning point.', descriptionEs: 'Precio baja desde máximo local. Primera alerta al 0.5%, luego cada 0.25%. Cualquier print puede ser punto de giro.', flipCode: 'TSPU', keywords: [], customSetting: cs('min_percent', 'Period multiplier', 'Multiplicador periodo', '2 = alerts at 2%, 4%, 6%. Leave blank for default.', '%'), qualityDesc: '% move down from the local high', qualityDescEs: '% de bajada desde el máximo local' },
  { code: 'TSSU', eventType: 'trailing_stop_vol_up', name: 'Trailing Stop, Volatility Up', nameEs: 'Trailing Stop, Volatilidad Arriba', shortLabel: 'TSVol Up', category: 'trailing', direction: 'bullish', active: true, description: 'Like % up but scaled by volatility. 1 bar = typical 15-min move. First at 1 bar, re-fire every 0.5 bar. Volatile stocks need bigger moves.', descriptionEs: 'Como % arriba pero escalado por volatilidad. 1 bar = movimiento típico 15 min. Primera a 1 bar, luego cada 0.5 bar.', flipCode: 'TSSD', keywords: [], customSetting: cs('volume_ratio', 'Period multiplier', 'Multiplicador periodo', '2 = alerts at 2x, 4x, 6x vol bars. Leave blank for default.', 'x'), qualityDesc: 'Volatility bars moved up from the local low', qualityDescEs: 'Barras de volatilidad subidas desde el mínimo local' },
  { code: 'TSSD', eventType: 'trailing_stop_vol_down', name: 'Trailing Stop, Volatility Down', nameEs: 'Trailing Stop, Volatilidad Abajo', shortLabel: 'TSVol Down', category: 'trailing', direction: 'bearish', active: true, description: 'Like % down but scaled by volatility. 1 bar = typical 15-min move. First at 1 bar, re-fire every 0.5 bar. Volatile stocks need bigger moves.', descriptionEs: 'Como % abajo pero escalado por volatilidad. 1 bar = movimiento típico 15 min. Primera a 1 bar, luego cada 0.5 bar.', flipCode: 'TSSU', keywords: [], customSetting: cs('volume_ratio', 'Period multiplier', 'Multiplicador periodo', '2 = alerts at 2x, 4x, 6x vol bars. Leave blank for default.', 'x'), qualityDesc: 'Volatility bars moved down from the local high', qualityDescEs: 'Barras de volatilidad bajadas desde el máximo local' },

  // ── Fibonacci Retracements ──────────────────────────────────────────
  ...([38, 50, 62, 79] as const).flatMap(level => [
    { code: `FU${level}`, eventType: `fib_buy_${level}`, name: `Fibonacci ${level}% Buy Signal`, nameEs: `Fibonacci ${level}% Señal Compra`, shortLabel: `Fib${level} Buy`, category: 'fibonacci', direction: 'bullish' as const, active: true, description: `Price retraces ${level}% from high. Three-point volume-confirmed pattern. Reversal signal (bullish).`, descriptionEs: `Precio retrocede ${level}% desde máximo. Patrón de 3 puntos confirmado por volumen. Señal de reversión (alcista).`, flipCode: `FD${level}`, keywords: ['fibonacci', 'single print', 'support and resistance'], customSetting: cs('min_hours', 'Min hours', 'Mín horas', '6.5 = full day. 7.5 = day + pre/post. Volume-weighted.', 'hours'), qualityDesc: 'Hours since the pattern was established', qualityDescEs: 'Horas desde que se estableció el patrón' },
    { code: `FD${level}`, eventType: `fib_sell_${level}`, name: `Fibonacci ${level}% Sell Signal`, nameEs: `Fibonacci ${level}% Señal Venta`, shortLabel: `Fib${level} Sell`, category: 'fibonacci', direction: 'bearish' as const, active: true, description: `Price retraces ${level}% from low. Three-point volume-confirmed pattern. Reversal signal (bearish).`, descriptionEs: `Precio retrocede ${level}% desde mínimo. Patrón de 3 puntos confirmado por volumen. Señal de reversión (bajista).`, flipCode: `FU${level}`, keywords: ['fibonacci', 'single print', 'support and resistance'], customSetting: cs('min_hours', 'Min hours', 'Mín horas', '6.5 = full day. 7.5 = day + pre/post. Volume-weighted.', 'hours'), qualityDesc: 'Hours since the pattern was established', qualityDescEs: 'Horas desde que se estableció el patrón' },
  ]),

  // ── Linear Regression Trends ────────────────────────────────────────
  ...([5, 15, 30, 90] as const).flatMap(tf => [
    { code: `PEU${tf}`, eventType: `linreg_up_${tf}m`, name: `${tf} Min Linear Regression Up Trend`, nameEs: `Regresión Lineal ${tf} Min Tendencia Alcista`, shortLabel: `LR${tf} Up`, category: 'linreg', direction: 'bullish' as const, active: true, description: `Short-term momentum crosses upward within ${tf}-min linear regression channel. Quality = $/share room left in channel.`, descriptionEs: `Momentum corto plazo cruza al alza dentro del canal de regresión lineal de ${tf} min. Calidad = $/acción de espacio en el canal.`, flipCode: `PED${tf}`, keywords: ['fixed time frame'], customSetting: cs('min_dollars', 'Min $/share', 'Mín $/acción', 'Forecast of how far stock will move. Higher = fewer alerts.', '$'), qualityDesc: 'Dollars per share of room left in the channel', qualityDescEs: 'Dólares por acción de espacio en el canal' },
    { code: `PED${tf}`, eventType: `linreg_down_${tf}m`, name: `${tf} Min Linear Regression Down Trend`, nameEs: `Regresión Lineal ${tf} Min Tendencia Bajista`, shortLabel: `LR${tf} Down`, category: 'linreg', direction: 'bearish' as const, active: true, description: `Short-term momentum crosses downward within ${tf}-min linear regression channel. Quality = $/share room left in channel.`, descriptionEs: `Momentum corto plazo cruza a la baja dentro del canal de regresión lineal de ${tf} min. Calidad = $/acción de espacio en el canal.`, flipCode: `PEU${tf}`, keywords: ['fixed time frame'], customSetting: cs('min_dollars', 'Min $/share', 'Mín $/acción', 'Forecast of how far stock will move. Higher = fewer alerts.', '$'), qualityDesc: 'Dollars per share of room left in the channel', qualityDescEs: 'Dólares por acción de espacio en el canal' },
  ]),

  // ── SMA Thrust ──────────────────────────────────────────────────────
  ...([2, 5, 15] as const).flatMap(tf => [
    { code: `SMAU${tf}`, eventType: `sma_thrust_up_${tf}m`, name: `Upward Thrust (${tf} Minute)`, nameEs: `Empuje Alcista (${tf} Minutos)`, shortLabel: `Thrust${tf} Up`, category: 'thrust', direction: 'bullish' as const, active: true, description: `SMA(8) and SMA(20) both going up for 5+ consecutive ${tf}-min periods. Re-fires at Fibonacci intervals. Quality = suddenness (0-100).`, descriptionEs: `SMA(8) y SMA(20) ambas subiendo durante 5+ periodos consecutivos de ${tf} min. Se repite en intervalos Fibonacci. Calidad = brusquedad (0-100).`, flipCode: `SMAD${tf}`, keywords: ['end of candle', 'moving average', 'fixed time frame'], customSetting: cs('min_percent', 'Min suddenness', 'Mín brusquedad', 'Suddenness 0-100. Flatter 200 SMA = closer to 100. Most alerts > 90.', '%'), qualityDesc: 'Suddenness of the move (0-100)', qualityDescEs: 'Brusquedad del movimiento (0-100)' },
    { code: `SMAD${tf}`, eventType: `sma_thrust_down_${tf}m`, name: `Downward Thrust (${tf} Minute)`, nameEs: `Empuje Bajista (${tf} Minutos)`, shortLabel: `Thrust${tf} Dn`, category: 'thrust', direction: 'bearish' as const, active: true, description: `SMA(8) and SMA(20) both going down for 5+ consecutive ${tf}-min periods. Re-fires at Fibonacci intervals. Quality = suddenness (0-100).`, descriptionEs: `SMA(8) y SMA(20) ambas bajando durante 5+ periodos consecutivos de ${tf} min. Se repite en intervalos Fibonacci. Calidad = brusquedad (0-100).`, flipCode: `SMAU${tf}`, keywords: ['end of candle', 'moving average', 'fixed time frame'], customSetting: cs('min_percent', 'Min suddenness', 'Mín brusquedad', 'Suddenness 0-100. Flatter 200 SMA = closer to 100. Most alerts > 90.', '%'), qualityDesc: 'Suddenness of the move (0-100)', qualityDescEs: 'Brusquedad del movimiento (0-100)' },
  ]),

  // ── Candle Pattern Alerts ──────────────────────────────────────────
  // Doji (5 timeframes, neutral, no custom setting)
  ...([5, 10, 15, 30, 60] as const).map(tf => (
    { code: `DOJ${tf}`, eventType: `doji_${tf}m`, name: `${tf} minute Doji`, nameEs: `Doji ${tf} min`, shortLabel: `Doji ${tf}m`, category: 'candle_pattern', direction: 'neutral' as const, active: true, description: `Doji pattern on ${tf}-min chart. Open and close nearly identical. Signals indecision.`, descriptionEs: `Patrón Doji en gráfico de ${tf} min. Apertura y cierre casi idénticos. Señal de indecisión.`, keywords: ['candle pattern', 'end of candle', 'fixed time frame'], customSetting: NONE_CS }
  )),

  // Hammer (6 timeframes, bullish, quality = grade 0-100)
  ...([2, 5, 10, 15, 30, 60] as const).map(tf => (
    { code: `HMR${tf}`, eventType: `hammer_${tf}m`, name: `${tf} minute hammer`, nameEs: `Martillo ${tf} min`, shortLabel: `Hammer ${tf}m`, category: 'candle_pattern', direction: 'bullish' as const, active: true, description: `Hammer pattern on ${tf}-min chart. No upper wick, small body, large lower wick in downtrend. Bullish reversal.`, descriptionEs: `Patrón martillo en gráfico de ${tf} min. Sin mecha superior, cuerpo pequeño, gran mecha inferior en tendencia bajista.`, flipCode: `HGM${tf}`, keywords: ['candle pattern', 'end of candle', 'fixed time frame'], customSetting: cs('min_percent', 'Min grade', 'Mín grado', '0-100, higher = closer to ideal pattern shape', '%'), qualityDesc: 'Pattern match grade (0-100)', qualityDescEs: 'Grado de coincidencia del patrón (0-100)' }
  )),

  // Hanging Man (6 timeframes, bearish, quality = grade 0-100)
  ...([2, 5, 10, 15, 30, 60] as const).map(tf => (
    { code: `HGM${tf}`, eventType: `hanging_man_${tf}m`, name: `${tf} minute hanging man`, nameEs: `Hombre colgado ${tf} min`, shortLabel: `HangMan ${tf}m`, category: 'candle_pattern', direction: 'bearish' as const, active: true, description: `Hanging man pattern on ${tf}-min chart. Similar to hammer but in uptrend. Bearish reversal.`, descriptionEs: `Patrón hombre colgado en gráfico de ${tf} min. Similar al martillo pero en tendencia alcista. Reversión bajista.`, flipCode: `HMR${tf}`, keywords: ['candle pattern', 'end of candle', 'fixed time frame'], customSetting: cs('min_percent', 'Min grade', 'Mín grado', '0-100, higher = closer to ideal pattern shape', '%'), qualityDesc: 'Pattern match grade (0-100)', qualityDescEs: 'Grado de coincidencia del patrón (0-100)' }
  )),

  // Bullish Engulfing (4 timeframes)
  ...([5, 10, 15, 30] as const).map(tf => (
    { code: `NGU${tf}`, eventType: `engulf_bull_${tf}m`, name: `${tf} minute bullish engulfing`, nameEs: `Envolvente alcista ${tf} min`, shortLabel: `Engulf↑ ${tf}m`, category: 'candle_pattern', direction: 'bullish' as const, active: true, description: `Bullish engulfing on ${tf}-min chart. Green candle engulfs previous red candle.`, descriptionEs: `Envolvente alcista en gráfico de ${tf} min. Vela verde envuelve la vela roja anterior.`, flipCode: `NGD${tf}`, keywords: ['candle pattern', 'end of candle', 'fixed time frame'], customSetting: cs('min_percent', 'Min grade', 'Mín grado', '0-100, higher = closer to ideal pattern shape', '%'), qualityDesc: 'Pattern match grade (0-100)', qualityDescEs: 'Grado de coincidencia del patrón (0-100)' }
  )),

  // Bearish Engulfing (4 timeframes)
  ...([5, 10, 15, 30] as const).map(tf => (
    { code: `NGD${tf}`, eventType: `engulf_bear_${tf}m`, name: `${tf} minute bearish engulfing`, nameEs: `Envolvente bajista ${tf} min`, shortLabel: `Engulf↓ ${tf}m`, category: 'candle_pattern', direction: 'bearish' as const, active: true, description: `Bearish engulfing on ${tf}-min chart. Red candle engulfs previous green candle.`, descriptionEs: `Envolvente bajista en gráfico de ${tf} min. Vela roja envuelve la vela verde anterior.`, flipCode: `NGU${tf}`, keywords: ['candle pattern', 'end of candle', 'fixed time frame'], customSetting: cs('min_percent', 'Min grade', 'Mín grado', '0-100, higher = closer to ideal pattern shape', '%'), qualityDesc: 'Pattern match grade (0-100)', qualityDescEs: 'Grado de coincidencia del patrón (0-100)' }
  )),

  // Piercing Pattern (4 timeframes, bullish)
  ...([5, 10, 15, 30] as const).map(tf => (
    { code: `PP${tf}`, eventType: `piercing_${tf}m`, name: `${tf} minute piercing pattern`, nameEs: `Patrón penetrante ${tf} min`, shortLabel: `Pierce ${tf}m`, category: 'candle_pattern', direction: 'bullish' as const, active: true, description: `Piercing pattern on ${tf}-min chart. Bullish candle opens below previous bearish candle and closes above its midpoint.`, descriptionEs: `Patrón penetrante en gráfico de ${tf} min. Vela alcista abre bajo la vela bajista anterior y cierra sobre su punto medio.`, flipCode: `DCC${tf}`, keywords: ['candle pattern', 'end of candle', 'fixed time frame'], customSetting: cs('min_percent', 'Min grade', 'Mín grado', '0-100, higher = closer to ideal pattern shape', '%'), qualityDesc: 'Pattern match grade (0-100)', qualityDescEs: 'Grado de coincidencia del patrón (0-100)' }
  )),

  // Dark Cloud Cover (4 timeframes, bearish)
  ...([5, 10, 15, 30] as const).map(tf => (
    { code: `DCC${tf}`, eventType: `dark_cloud_${tf}m`, name: `${tf} minute dark cloud cover`, nameEs: `Nube oscura ${tf} min`, shortLabel: `DCC ${tf}m`, category: 'candle_pattern', direction: 'bearish' as const, active: true, description: `Dark cloud cover on ${tf}-min chart. Bearish candle opens above previous bullish candle and closes below its midpoint.`, descriptionEs: `Nube oscura en gráfico de ${tf} min. Vela bajista abre sobre la vela alcista anterior y cierra bajo su punto medio.`, flipCode: `PP${tf}`, keywords: ['candle pattern', 'end of candle', 'fixed time frame'], customSetting: cs('min_percent', 'Min grade', 'Mín grado', '0-100, higher = closer to ideal pattern shape', '%'), qualityDesc: 'Pattern match grade (0-100)', qualityDescEs: 'Grado de coincidencia del patrón (0-100)' }
  )),
];

// ============================================================================
// LOOKUP MAPS — Generated dynamically from the catalog
// ============================================================================

/** Map: eventType → AlertDefinition */
export const ALERT_BY_EVENT_TYPE: Record<string, AlertDefinition> = Object.fromEntries(
  ALERT_CATALOG.map(a => [a.eventType, a])
);

/** Map: code → AlertDefinition */
export const ALERT_BY_CODE: Record<string, AlertDefinition> = Object.fromEntries(
  ALERT_CATALOG.map(a => [a.code, a])
);

/** All event type strings */
export const ALL_EVENT_TYPES: string[] = ALERT_CATALOG.map(a => a.eventType);

/** All active event type strings */
export const ACTIVE_EVENT_TYPES: string[] = ALERT_CATALOG.filter(a => a.active).map(a => a.eventType);

// ============================================================================
// DISPLAY HELPERS — Derived from catalog, no more hardcoded maps
// ============================================================================

/** Get short label for an event type (for table cells, badges) */
export function getEventLabel(eventType: string): string {
  return ALERT_BY_EVENT_TYPE[eventType]?.shortLabel ?? eventType;
}

/** Get Tailwind color class for an event type */
export function getEventColor(eventType: string): string {
  const def = ALERT_BY_EVENT_TYPE[eventType];
  if (!def) return 'text-foreground/80';
  switch (def.direction) {
    case 'bullish': return 'text-emerald-600';
    case 'bearish': return 'text-rose-600 dark:text-rose-400';
    default: return 'text-foreground/80';
  }
}

/** Get alerts grouped by category (sorted by category order) */
export function getAlertsByCategory(): { category: AlertCategory; alerts: AlertDefinition[] }[] {
  const grouped = new Map<string, AlertDefinition[]>();
  for (const alert of ALERT_CATALOG) {
    if (!grouped.has(alert.category)) grouped.set(alert.category, []);
    grouped.get(alert.category)!.push(alert);
  }
  return ALERT_CATEGORIES
    .filter(cat => grouped.has(cat.id))
    .map(cat => ({ category: cat, alerts: grouped.get(cat.id)! }));
}

/** Get only active alerts */
export function getActiveAlerts(): AlertDefinition[] {
  return ALERT_CATALOG.filter(a => a.active);
}

/** Get all active event type strings */
export function getActiveEventTypes(): string[] {
  return ACTIVE_EVENT_TYPES;
}

/** Search alerts by name, code, or description */
export function searchAlerts(query: string, locale: 'en' | 'es' = 'en'): AlertDefinition[] {
  const q = query.toLowerCase().trim();
  if (!q) return ALERT_CATALOG;
  return ALERT_CATALOG.filter(a => {
    const name = locale === 'es' ? a.nameEs : a.name;
    const desc = locale === 'es' ? a.descriptionEs : a.description;
    return (
      a.code.toLowerCase().includes(q) ||
      name.toLowerCase().includes(q) ||
      desc.toLowerCase().includes(q) ||
      a.eventType.toLowerCase().includes(q) ||
      a.keywords.some(k => k.toLowerCase().includes(q))
    );
  });
}

// ============================================================================
// BUILT-IN PRESETS — Strategy templates
// ============================================================================

export interface BuiltInPreset {
  id: string;
  name: string;
  nameEs: string;
  description: string;
  descriptionEs: string;
  eventTypes: string[];
  filters: Record<string, any>;
  category: 'bullish' | 'bearish' | 'neutral' | 'custom';
  isBuiltIn: true;
}

/** Backward-compatible alias used by ConfigWindow */
export type AlertPreset = BuiltInPreset;

export interface TopListPreset {
  id: string;
  name: string;
  nameEs: string;
  description: string;
  descriptionEs: string;
  filters: Record<string, any>;
  isTopList: true;
}

export const BUILT_IN_PRESETS: BuiltInPreset[] = [
  {
    id: 'high_vol_runners',
    name: 'High Vol Runners',
    nameEs: 'Runners Alto Volumen',
    description: 'Running up/down alerts with high relative volume',
    descriptionEs: 'Alertas running up/down con alto volumen relativo',
    eventTypes: ['running_up', 'running_down', 'running_up_sustained', 'running_down_sustained', 'running_up_confirmed', 'running_down_confirmed', 'running_up_intermediate', 'running_down_intermediate', 'rvol_spike', 'volume_surge'],
    filters: { min_rvol: 2 },
    category: 'neutral',
    isBuiltIn: true,
  },
  {
    id: 'gap_plays',
    name: 'Gap Plays',
    nameEs: 'Jugadas de Gap',
    description: 'Gap reversals and false gap retracements',
    descriptionEs: 'Reversiones de gap y retrocesos falsos',
    eventTypes: ['gap_up_reversal', 'gap_down_reversal', 'false_gap_up_retracement', 'false_gap_down_retracement'],
    filters: {},
    category: 'neutral',
    isBuiltIn: true,
  },
  {
    id: 'breakouts',
    name: 'Breakouts',
    nameEs: 'Rupturas',
    description: 'Channel breakouts, consolidation breaks, and ORB',
    descriptionEs: 'Rupturas de canal, consolidación y ORB',
    eventTypes: ['channel_breakout', 'channel_breakout_confirmed', 'orb_up_5min', 'orb_up_15min', 'consol_breakout_5m', 'consol_breakout_15m', 'new_high', 'crossed_daily_high_resistance'],
    filters: {},
    category: 'bullish',
    isBuiltIn: true,
  },
  {
    id: 'institutional',
    name: 'Institutional Flow',
    nameEs: 'Flujo Institucional',
    description: 'Block trades, large bid/ask, and volume confirmed crosses',
    descriptionEs: 'Block trades, grandes bid/ask, y cruces confirmados por volumen',
    eventTypes: ['block_trade', 'large_bid_size', 'large_ask_size', 'crossed_above_sma200', 'crossed_below_sma200', 'running_up_confirmed', 'running_down_confirmed'],
    filters: {},
    category: 'neutral',
    isBuiltIn: true,
  },
  {
    id: 'scalping',
    name: 'Scalping',
    nameEs: 'Scalping',
    description: 'Fast alerts: running now, VWAP crosses, open/close crosses',
    descriptionEs: 'Alertas rápidas: running now, cruces VWAP, cruces open/close',
    eventTypes: ['running_up', 'running_down', 'vwap_cross_up', 'vwap_cross_down', 'crossed_above_open', 'crossed_below_open'],
    filters: {},
    category: 'neutral',
    isBuiltIn: true,
  },
];

export const BUILT_IN_TOP_LISTS: TopListPreset[] = [
  {
    id: 'top_gainers',
    name: 'Top Gainers',
    nameEs: 'Mayores Subidas',
    description: 'Stocks with highest % change today',
    descriptionEs: 'Acciones con mayor % de cambio hoy',
    filters: { sort_by: 'change_percent', sort_dir: 'desc' },
    isTopList: true,
  },
  {
    id: 'top_losers',
    name: 'Top Losers',
    nameEs: 'Mayores Bajadas',
    description: 'Stocks with lowest % change today',
    descriptionEs: 'Acciones con menor % de cambio hoy',
    filters: { sort_by: 'change_percent', sort_dir: 'asc' },
    isTopList: true,
  },
  {
    id: 'most_active',
    name: 'Most Active',
    nameEs: 'Más Activos',
    description: 'Highest relative volume today',
    descriptionEs: 'Mayor volumen relativo hoy',
    filters: { sort_by: 'rvol', sort_dir: 'desc', min_rvol: 2 },
    isTopList: true,
  },
];
