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
  'evt_new_highs': 'New Highs',
  'evt_new_lows': 'New Lows',
  'evt_vwap_crosses': 'VWAP Crosses',
  'evt_open_crosses': 'Open Crosses',
  'evt_close_crosses': 'Close Crosses',
  'evt_volume': 'Volume Events',
  'evt_momentum': 'Momentum',
  'evt_big_movers': 'Big Movers',
  'evt_pullbacks': 'Pullbacks',
  'evt_gap_reversals': 'Gap Reversals',
  'evt_halts': 'Halts',
  'evt_ma_crosses': 'MA Crosses',
  'evt_bollinger': 'Bollinger',
  'evt_daily_levels': 'Daily Levels',
  'evt_confirmed': 'Confirmed',
  'evt_all': 'All Events',
};

/**
 * Categorías de eventos del sistema (predefinidas)
 */
export interface EventCategory {
  id: string;
  label: string;
  description: string;
  eventTypes: string[]; // Tipos de eventos que incluye
  icon: string;
}

export const SYSTEM_EVENT_CATEGORIES: EventCategory[] = [
  // ===== PRICE EVENTS =====
  {
    id: 'evt_new_highs',
    label: 'New Highs',
    description: 'Stocks making new intraday highs',
    eventTypes: ['new_high'],
    icon: '📈',
  },
  {
    id: 'evt_new_lows',
    label: 'New Lows',
    description: 'Stocks making new intraday lows',
    eventTypes: ['new_low'],
    icon: '📉',
  },
  // ===== VWAP EVENTS =====
  {
    id: 'evt_vwap_crosses',
    label: 'VWAP Crosses',
    description: 'Stocks crossing VWAP up or down',
    eventTypes: ['vwap_cross_up', 'vwap_cross_down'],
    icon: '⚡',
  },
  // ===== OPEN / CLOSE CROSSES =====
  {
    id: 'evt_open_crosses',
    label: 'Open Crosses',
    description: 'Stocks crossing above or below today\'s open',
    eventTypes: ['crossed_above_open', 'crossed_below_open'],
    icon: '🔀',
  },
  {
    id: 'evt_close_crosses',
    label: 'Close Crosses',
    description: 'Stocks crossing above or below previous close',
    eventTypes: ['crossed_above_prev_close', 'crossed_below_prev_close'],
    icon: '🔄',
  },
  // ===== VOLUME EVENTS =====
  {
    id: 'evt_volume',
    label: 'Volume Events',
    description: 'RVOL spikes, volume surges, block trades, unusual prints',
    eventTypes: ['rvol_spike', 'volume_surge', 'volume_spike_1min', 'unusual_prints', 'block_trade'],
    icon: '🔥',
  },
  // ===== MOMENTUM EVENTS =====
  {
    id: 'evt_momentum',
    label: 'Momentum',
    description: 'Stocks running up or down rapidly',
    eventTypes: ['running_up', 'running_down'],
    icon: '🏃',
  },
  {
    id: 'evt_big_movers',
    label: 'Big Movers',
    description: 'Stocks crossing +5% or +10% change thresholds',
    eventTypes: ['percent_up_5', 'percent_down_5', 'percent_up_10', 'percent_down_10'],
    icon: '💎',
  },
  // ===== PULLBACK EVENTS =====
  {
    id: 'evt_pullbacks',
    label: 'Pullbacks',
    description: 'Stocks pulling back from highs or bouncing from lows',
    eventTypes: ['pullback_75_from_high', 'pullback_25_from_high', 'pullback_75_from_low', 'pullback_25_from_low'],
    icon: '↩️',
  },
  // ===== GAP EVENTS =====
  {
    id: 'evt_gap_reversals',
    label: 'Gap Reversals',
    description: 'Stocks reversing their opening gaps',
    eventTypes: ['gap_up_reversal', 'gap_down_reversal'],
    icon: '🔃',
  },
  // ===== HALT EVENTS =====
  {
    id: 'evt_halts',
    label: 'Halts',
    description: 'Trading halts and resumes',
    eventTypes: ['halt', 'resume'],
    icon: '🛑',
  },
  // ===== PHASE 2: MA CROSSES =====
  {
    id: 'evt_ma_crosses',
    label: 'MA Crosses',
    description: 'Stocks crossing key moving averages (SMA 20, 50, 200)',
    eventTypes: ['crossed_above_sma200', 'crossed_below_sma200', 'crossed_above_sma50', 'crossed_below_sma50', 'crossed_above_sma20', 'crossed_below_sma20'],
    icon: '📐',
  },
  // ===== PHASE 2: BOLLINGER =====
  {
    id: 'evt_bollinger',
    label: 'Bollinger',
    description: 'Bollinger Band breakouts and breakdowns',
    eventTypes: ['bb_upper_breakout', 'bb_lower_breakdown'],
    icon: '📏',
  },
  // ===== PHASE 2: DAILY LEVELS =====
  {
    id: 'evt_daily_levels',
    label: 'Daily Levels',
    description: 'Previous day high/low breaks and false gap reversals',
    eventTypes: ['crossed_daily_high_resistance', 'crossed_daily_low_support', 'false_gap_up_retracement', 'false_gap_down_retracement'],
    icon: '📍',
  },
  // ===== PHASE 2: CONFIRMED =====
  {
    id: 'evt_confirmed',
    label: 'Confirmed',
    description: 'Multi-tick confirmed signals with volume validation',
    eventTypes: ['running_up_sustained', 'running_down_sustained', 'running_up_confirmed', 'running_down_confirmed', 'vwap_divergence_up', 'vwap_divergence_down', 'crossed_above_open_confirmed', 'crossed_below_open_confirmed', 'crossed_above_close_confirmed', 'crossed_below_close_confirmed'],
    icon: '✅',
  },
  // ===== ALL =====
  {
    id: 'evt_all',
    label: 'All Events',
    description: 'All market events in real-time',
    eventTypes: [], // Empty = all types
    icon: '📊',
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

