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
  { id: 'sc', label: 'SC', description: 'Scanner - Ver todas las tablas', icon: LayoutGrid },
  { id: 'watchlist', label: 'WL', description: 'Quote Monitor - Watchlist con quotes en tiempo real', icon: List, shortcut: 'Ctrl+W' },
  { id: 'dt', label: 'DT', description: 'Dilution Tracker - Análisis de dilución', icon: BarChart3, shortcut: 'Ctrl+D' },
  { id: 'sec', label: 'SEC', description: 'SEC Filings - Filings de la SEC en tiempo real', icon: FileText, shortcut: 'Ctrl+F' },
  { id: 'news', label: 'NEWS', description: 'News - Noticias del mercado en tiempo real', icon: Newspaper, shortcut: 'Ctrl+N' },
  { id: 'fa', label: 'FA', description: 'Financial Analysis - Balance, Income, Cash Flow', icon: DollarSign },
  { id: 'ipo', label: 'IPO', description: 'IPOs - Initial Public Offerings en tiempo real', icon: Rocket },
  { id: 'profile', label: 'PROFILE', description: 'User Profile - Tu perfil y configuración de cuenta', icon: User },
  { id: 'settings', label: 'SET', description: 'Settings - Configuración de la app', icon: Settings, shortcut: 'Ctrl+,' },
];

/**
 * Mapeo rápido de id → label
 * Generado automáticamente desde MAIN_COMMANDS
 */
export const COMMAND_LABELS: Record<string, string> = Object.fromEntries(
  MAIN_COMMANDS.map(cmd => [cmd.id, cmd.label])
);

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

