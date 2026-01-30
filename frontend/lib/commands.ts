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
  { id: 'filters', label: 'FILTERS', description: 'commands.filters.description', icon: Filter, shortcut: 'Ctrl+Shift+F' },
  { id: 'sb', label: 'SB', description: 'commands.sb.description', icon: ScanSearch, isNew: true },
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
 * Mapeo rápido de id → label
 * Combina comandos principales + categorías del scanner
 */
export const COMMAND_LABELS: Record<string, string> = {
  ...Object.fromEntries(MAIN_COMMANDS.map(cmd => [cmd.id, cmd.label])),
  ...SCANNER_CATEGORY_LABELS,
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

