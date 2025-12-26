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
  type LucideIcon,
} from 'lucide-react';

export interface MainCommand {
  id: string;
  label: string;
  description: string;
  icon: LucideIcon;
  shortcut?: string;
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
  { id: 'alerts', label: 'ALERTS', description: 'commands.alerts.description', icon: Zap },
  { id: 'fa', label: 'FA', description: 'commands.fa.description', icon: DollarSign },
  { id: 'ipo', label: 'IPO', description: 'commands.ipo.description', icon: Rocket },
  { id: 'profile', label: 'PROFILE', description: 'commands.profile.description', icon: User },
  { id: 'settings', label: 'SET', description: 'commands.settings.description', icon: Settings, shortcut: 'Ctrl+,' },
  { id: 'filters', label: 'FILTERS', description: 'commands.filters.description', icon: Filter, shortcut: 'Ctrl+Shift+F' },
  { id: 'chat', label: 'CHAT', description: 'commands.chat.description', icon: MessageCircle, shortcut: 'Ctrl+Shift+C' },
  { id: 'notes', label: 'NOTE', description: 'commands.notes.description', icon: StickyNote, shortcut: 'Ctrl+Shift+N' },
  { id: 'patterns', label: 'PM', description: 'commands.patterns.description', icon: Sparkles, shortcut: 'Ctrl+P' },
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

