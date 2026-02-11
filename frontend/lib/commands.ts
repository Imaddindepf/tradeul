/**
 * Definición centralizada de comandos principales
 * FUENTE ÚNICA DE VERDAD para evitar duplicación
 */

import {
  LayoutGrid,
  BarChart3,
  FileText,
  DollarSign,
  Settings,
  Newspaper,
  User,
  Rocket,
  List,
  Filter,
  Zap,
  MessageCircle,
  StickyNote,
  Sparkles,
  GitCompareArrows,
  ScanSearch,
  TrendingUp,
  Users,
  Brain,
  Bot,
  Sun,
  Calendar,
  Globe,
  Grid3X3,
  Activity,
  type LucideIcon,
} from 'lucide-react';

export interface MainCommand {
  id: string;
  label: string;
  description: string;
  icon: LucideIcon;
  shortcut?: string;
  isNew?: boolean; // Tag azul "NEW" para comandos recientes
}

/**
 * Comandos principales de la aplicación
 * Usados por: CommandPalette, PinnedCommands, SettingsContent
 */
export const MAIN_COMMANDS: MainCommand[] = [
  { id: 'sc', label: 'SC', description: 'commands.sc.description', icon: LayoutGrid },
  { id: 'watchlist', label: 'WL', description: 'commands.wl.description', icon: List, shortcut: 'Ctrl+W' },
  { id: 'dt', label: 'DT', description: 'commands.dt.description', icon: BarChart3, shortcut: 'Ctrl+D' },
  { id: 'sec', label: 'SEC', description: 'commands.sec.description', icon: FileText },
  { id: 'news', label: 'NEWS', description: 'commands.news.description', icon: Newspaper, shortcut: 'Ctrl+N' },
  { id: 'ins', label: 'INS', description: 'commands.ins.description', icon: FileText, isNew: true },
  { id: 'alerts', label: 'ALERTS', description: 'commands.alerts.description', icon: Zap },
  { id: 'fa', label: 'FA', description: 'commands.fa.description', icon: DollarSign },
  { id: 'ipo', label: 'IPO', description: 'commands.ipo.description', icon: Rocket },
  { id: 'profile', label: 'PROFILE', description: 'commands.profile.description', icon: User },
  { id: 'settings', label: 'SET', description: 'commands.settings.description', icon: Settings, shortcut: 'Ctrl+,' },
  { id: 'chat', label: 'CHAT', description: 'commands.chat.description', icon: MessageCircle, shortcut: 'Ctrl+Shift+C' },
  { id: 'notes', label: 'NOTE', description: 'commands.notes.description', icon: StickyNote, shortcut: 'Ctrl+Shift+N' },
  { id: 'patterns', label: 'PM', description: 'commands.patterns.description', icon: Sparkles, shortcut: 'Ctrl+P' },
  { id: 'ratio', label: 'GR', description: 'commands.ratio.description', icon: GitCompareArrows, shortcut: 'Ctrl+G' },
  { id: 'screener', label: 'SCREEN', description: 'commands.screener.description', icon: ScanSearch, shortcut: 'Ctrl+Shift+S' },
  { id: 'mp', label: 'MP', description: 'commands.mp.description', icon: TrendingUp, shortcut: 'Ctrl+M' },
  { id: 'insider', label: 'INSIDER', description: 'commands.insider.description', icon: Users, shortcut: 'Ctrl+I' },
  { id: 'fan', label: 'FAN', description: 'commands.fan.description', icon: Brain, shortcut: 'Ctrl+Shift+F', isNew: true },
  { id: 'ai', label: 'AI', description: 'commands.ai.description', icon: Bot, shortcut: 'Ctrl+Shift+A', isNew: true },
  { id: 'earnings', label: 'ERN', description: 'commands.earnings.description', icon: Calendar, shortcut: 'Ctrl+E', isNew: true },
  { id: 'predict', label: 'PREDICT', description: 'commands.predict.description', icon: Globe, isNew: true },
  { id: 'heatmap', label: 'HM', description: 'commands.heatmap.description', icon: Grid3X3, shortcut: 'Ctrl+H', isNew: true },
  { id: 'hds', label: 'HDS', description: 'commands.hds.description', icon: Users, isNew: true },
  { id: 'evn', label: 'EVN', description: 'commands.evn.description', icon: Activity, isNew: true },
  { id: 'sb', label: 'SB', description: 'commands.sb.description', icon: Filter },
  { id: 'build', label: 'BUILD', description: 'commands.build.description', icon: Zap, isNew: true },
];

/**
 * Labels de categorías del scanner (para PinnedCommands)
 */
export const SCANNER_CATEGORY_LABELS: Record<string, string> = {
  'gappers_up': 'Gap Up',
  'gappers_down': 'Gap Down',
  'momentum_up': 'Mom Up',
  'momentum_down': 'Mom Down',
  'winners': 'Winners',
  'losers': 'Losers',
  'new_highs': 'Highs',
  'new_lows': 'Lows',
  'anomalies': 'Anomalies',
  'high_volume': 'Volume',
  'reversals': 'Reversals',
  'with_news': 'With News',
};

/**
 * Labels de categorías de eventos (para EVN command)
 */
export const EVENT_CATEGORY_LABELS: Record<string, string> = {
  'evt_high_vol_runners': 'Momentum Runners',
  'evt_parabolic_movers': 'Parabolic Movers',
  'evt_gap_fade': 'Gap Fade',
  'evt_gap_recovery': 'Gap Down Recovery',
  'evt_vwap_reclaim': 'VWAP Reclaim',
  'evt_ema_trend_break': 'SMA 50 Trend Break',
  'evt_halt_momentum': 'Halt Resume',
  'evt_dip_buy': 'Dip Buy on Runners',
  'evt_confirmed_longs': 'Confirmed Longs',
  'evt_confirmed_shorts': 'Confirmed Shorts',
  'evt_squeeze_play': 'Squeeze Play',
  'evt_institutional_bid': 'Institutional Bid',
  'evt_reversal_play': 'Reversal Play',
  'evt_breakdown_short': 'Breakdown Short',
  'evt_macd_momentum': 'MACD Momentum',
  'evt_stoch_reversal': 'Stochastic Reversal',
  'evt_orb_play': 'Opening Range Play',
  'evt_consolidation_break': 'Consolidation Break',
  'evt_all': 'All Events',
};

/**
 * Categorías de eventos del sistema (predefinidas)
 */
export interface EventCategoryDefaults {
  // Price & basics
  min_price?: number;
  max_price?: number;
  min_rvol?: number;
  max_rvol?: number;
  min_volume?: number;
  max_volume?: number;
  min_change_percent?: number;
  max_change_percent?: number;
  min_market_cap?: number;
  max_market_cap?: number;
  min_gap_percent?: number;
  max_gap_percent?: number;
  min_change_from_open?: number;
  max_change_from_open?: number;
  min_float_shares?: number;
  max_float_shares?: number;
  min_rsi?: number;
  max_rsi?: number;
  min_atr_percent?: number;
  max_atr_percent?: number;
  // Enriched filters (applied server-side via enriched cache)
  min_vwap?: number;
  max_vwap?: number;
  min_shares_outstanding?: number;
  max_shares_outstanding?: number;
  min_daily_sma_200?: number;
  max_daily_sma_200?: number;
  min_daily_rsi?: number;
  max_daily_rsi?: number;
  min_adx_14?: number;
  max_adx_14?: number;
  min_stoch_k?: number;
  max_stoch_k?: number;
  security_type?: string;
  sector?: string;
}

export interface EventCategory {
  id: string;
  label: string;
  description: string;
  eventTypes: string[]; // Tipos de eventos que incluye
  icon: string;
  /** Default server-side filters applied when user hasn't set custom filters */
  defaultFilters?: EventCategoryDefaults;
}

export const SYSTEM_EVENT_CATEGORIES: EventCategory[] = [
  // ── MOMENTUM ──
  {
    id: 'evt_high_vol_runners',
    label: 'Momentum Runners',
    description: 'Confirmed runners with catalyst, high RVOL, small/mid cap',
    eventTypes: ['running_up_confirmed', 'running_up_sustained', 'new_high', 'volume_surge'],
    icon: '🏃',
    defaultFilters: { min_price: 2, max_price: 50, min_rvol: 3, min_volume: 200000, min_gap_percent: 1, min_change_from_open: 2, max_market_cap: 5000000000 },
  },
  {
    id: 'evt_parabolic_movers',
    label: 'Parabolic Movers',
    description: 'Extreme moves: +10%, massive volume, low float',
    eventTypes: ['percent_up_10', 'volume_surge', 'new_high', 'running_up_confirmed'],
    icon: '🚀',
    defaultFilters: { min_price: 2, min_rvol: 4, min_volume: 500000, max_market_cap: 5000000000, max_float_shares: 30000000, min_gap_percent: 3 },
  },
  // ── GAPS ──
  {
    id: 'evt_gap_fade',
    label: 'Gap Fade',
    description: 'Gap ups that fail — short opportunity when gap fades',
    eventTypes: ['gap_up_reversal', 'false_gap_up_retracement'],
    icon: '📉',
    defaultFilters: { min_price: 3, min_gap_percent: 4, max_gap_percent: 20, min_rvol: 1.5, min_volume: 100000, max_change_from_open: -0.5, min_market_cap: 200000000 },
  },
  {
    id: 'evt_gap_recovery',
    label: 'Gap Down Recovery',
    description: 'Gap down stocks bouncing back with volume',
    eventTypes: ['gap_down_reversal', 'false_gap_down_retracement'],
    icon: '📈',
    defaultFilters: { min_price: 5, max_gap_percent: -3, min_rvol: 2, min_volume: 200000, min_change_from_open: 1, min_market_cap: 500000000 },
  },
  // ── VWAP ──
  {
    id: 'evt_vwap_reclaim',
    label: 'VWAP Reclaim',
    description: 'Institutional entry: VWAP reclaim on catalyst stock',
    eventTypes: ['vwap_cross_up'],
    icon: '⚡',
    defaultFilters: { min_price: 5, min_rvol: 2, min_volume: 200000, min_gap_percent: 1, min_change_percent: -2, min_market_cap: 500000000, min_rsi: 30, max_rsi: 65 },
  },
  // ── SMA TREND ──
  {
    id: 'evt_ema_trend_break',
    label: 'SMA 50 Trend Break',
    description: 'SMA 50 cross + golden/death cross with volume',
    eventTypes: ['crossed_above_sma50', 'crossed_below_sma50', 'sma_8_cross_above_20', 'sma_8_cross_below_20'],
    icon: '📐',
    defaultFilters: { min_price: 5, min_rvol: 2, min_volume: 200000, min_atr_percent: 1.5, min_market_cap: 500000000 },
  },
  // ── HALTS ──
  {
    id: 'evt_halt_momentum',
    label: 'Halt Resume',
    description: 'Halts on runners — explosive resume plays',
    eventTypes: ['halt', 'resume'],
    icon: '🛑',
    defaultFilters: { min_price: 2, min_change_percent: 5, min_rvol: 3, min_volume: 100000, max_market_cap: 5000000000 },
  },
  // ── PULLBACKS ──
  {
    id: 'evt_dip_buy',
    label: 'Dip Buy on Runners',
    description: 'Pullbacks on strong stocks with catalyst',
    eventTypes: ['pullback_25_from_high', 'pullback_75_from_high'],
    icon: '🎯',
    defaultFilters: { min_price: 2, min_rvol: 2.5, min_volume: 200000, min_gap_percent: 2, min_change_percent: 3, max_market_cap: 10000000000 },
  },
  // ── CONFIRMED ──
  {
    id: 'evt_confirmed_longs',
    label: 'Confirmed Longs',
    description: 'Highest conviction bullish signals',
    eventTypes: ['running_up_confirmed', 'running_up_sustained', 'crossed_above_open', 'crossed_above_prev_close'],
    icon: '✅',
    defaultFilters: { min_price: 2, min_rvol: 2.5, min_volume: 200000, min_change_percent: 1, min_market_cap: 100000000 },
  },
  {
    id: 'evt_confirmed_shorts',
    label: 'Confirmed Shorts',
    description: 'Highest conviction bearish signals',
    eventTypes: ['running_down_confirmed', 'running_down_sustained', 'crossed_below_open', 'crossed_below_prev_close'],
    icon: '🔻',
    defaultFilters: { min_price: 5, min_rvol: 2, min_volume: 200000, max_change_percent: -1, min_market_cap: 200000000 },
  },
  // ── ADVANCED ──
  {
    id: 'evt_squeeze_play',
    label: 'Squeeze Play',
    description: 'Low float + massive volume + Bollinger breakout',
    eventTypes: ['running_up_confirmed', 'volume_surge', 'bb_upper_breakout', 'new_high'],
    icon: '💥',
    defaultFilters: { min_price: 2, max_float_shares: 20000000, min_rvol: 4, min_gap_percent: 3, max_market_cap: 2000000000, min_volume: 300000 },
  },
  {
    id: 'evt_institutional_bid',
    label: 'Institutional Bid',
    description: 'Large cap momentum with institutional footprint',
    eventTypes: ['vwap_cross_up', 'crossed_above_sma50', 'volume_surge', 'percent_up_5'],
    icon: '🏦',
    defaultFilters: { min_market_cap: 5000000000, min_volume: 1000000, min_rvol: 2, min_price: 20, min_change_percent: 1 },
  },
  {
    id: 'evt_reversal_play',
    label: 'Reversal Play',
    description: 'Gap down stocks showing reversal signs',
    eventTypes: ['gap_down_reversal', 'vwap_cross_up', 'pullback_25_from_low', 'pullback_75_from_low'],
    icon: '🔄',
    defaultFilters: { max_gap_percent: -3, min_rvol: 2.5, min_volume: 300000, min_change_from_open: 1, min_market_cap: 500000000, min_price: 5 },
  },
  {
    id: 'evt_breakdown_short',
    label: 'Breakdown Short',
    description: 'Technical breakdown with volume',
    eventTypes: ['running_down_confirmed', 'crossed_below_sma50', 'bb_lower_breakdown', 'macd_cross_bearish', 'crossed_daily_low_support'],
    icon: '⬇️',
    defaultFilters: { max_change_percent: -2, min_rvol: 2, min_volume: 200000, min_price: 5, min_market_cap: 300000000 },
  },
  // ── MACD / STOCHASTIC ──
  {
    id: 'evt_macd_momentum',
    label: 'MACD Momentum',
    description: 'MACD bullish cross + SMA golden cross — triple confirmation',
    eventTypes: ['macd_cross_bullish', 'macd_zero_cross_up', 'sma_8_cross_above_20', 'crossed_above_sma20'],
    icon: '📊',
    defaultFilters: { min_price: 3, min_rvol: 1.5, min_volume: 150000, min_market_cap: 200000000 },
  },
  {
    id: 'evt_stoch_reversal',
    label: 'Stochastic Reversal',
    description: 'Oversold stochastic cross + VWAP reclaim — mean reversion',
    eventTypes: ['stoch_cross_bullish', 'stoch_oversold', 'vwap_cross_up', 'pullback_75_from_low'],
    icon: '🔄',
    defaultFilters: { min_price: 5, min_rvol: 2, min_volume: 200000, min_market_cap: 500000000, max_rsi: 40 },
  },
  // ── OPENING RANGE ──
  {
    id: 'evt_orb_play',
    label: 'Opening Range Play',
    description: 'ORB breakout with gap and volume',
    eventTypes: ['orb_breakout_up', 'orb_breakout_down', 'volume_surge'],
    icon: '⏰',
    defaultFilters: { min_price: 3, min_rvol: 2, min_volume: 200000, min_gap_percent: 1, max_market_cap: 10000000000 },
  },
  // ── CONSOLIDATION ──
  {
    id: 'evt_consolidation_break',
    label: 'Consolidation Break',
    description: 'Tight range breakout with volume confirmation',
    eventTypes: ['consolidation_breakout_up', 'consolidation_breakout_down', 'volume_surge'],
    icon: '📦',
    defaultFilters: { min_price: 3, min_rvol: 2, min_volume: 200000, max_market_cap: 10000000000 },
  },
  // ===== ALL (catch-all) =====
  {
    id: 'evt_all',
    label: 'All Events',
    description: 'All market events in real-time (unfiltered)',
    eventTypes: [], // Empty = all types
    icon: '📊',
    defaultFilters: { min_price: 1, min_volume: 10000 },
  },
];

/**
 * Mapeo rápido de id → label
 * Combina comandos principales + categorías del scanner + categorías de eventos
 */
export const COMMAND_LABELS: Record<string, string> = {
  ...Object.fromEntries(MAIN_COMMANDS.map(cmd => [cmd.id, cmd.label])),
  ...SCANNER_CATEGORY_LABELS,
  ...EVENT_CATEGORY_LABELS,
};

/**
 * Obtener label de un comando por su id
 */
export function getCommandLabel(id: string): string {
  return COMMAND_LABELS[id] || id.toUpperCase();
}

/**
 * Obtener comando completo por id
 */
export function getCommand(id: string): MainCommand | undefined {
  return MAIN_COMMANDS.find(cmd => cmd.id === id);
}

