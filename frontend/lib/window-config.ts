/**
 * Configuración centralizada de tipos de ventana
 * Un solo lugar para mantener la consistencia
 */

export const WINDOW_TYPES: Record<string, string> = {
  'Settings': 'settings',
  'Dilution Tracker': 'dt',
  'SEC Filings': 'sec',
  'News': 'news',
  'Financial Analysis': 'fa',
  'User Profile': 'profile',
  'IPOs': 'ipo',
  'Community Chat': 'chat',
  'Quote Monitor': 'watchlist',
  'Notes': 'notes',
  'Pattern Matching': 'pm',
  'Ratio Analysis': 'ratio',
  'Stock Screener': 'screener',
  'Historical Multiple Security': 'mp',
  'Catalyst Alerts': 'alerts',
  'AI Agent': 'ai_agent',
  'Earnings Calendar': 'earnings',
  'Prediction Markets': 'predict',
  'Market Heatmap': 'heatmap',
  'Strategy Builder': 'strategy_builder',
  'Institutional Holdings': 'hds',
  'Market Pulse': 'pulse',
  'Bug Reports Admin': 'bug_admin',
};

/**
 * Obtener el tipo de ventana por título
 * Soporta patrones dinámicos para scanner y gráficos financieros
 */
export function getWindowType(title: string): string {
  // Primero checar tipos conocidos
  if (WINDOW_TYPES[title]) {
    return WINDOW_TYPES[title];
  }

  // Para tablas del scanner: "Scanner: Gappers Up" -> "scanner_gappers_up"
  if (title.startsWith('Scanner:')) {
    return title.toLowerCase().replace(/\s+/g, '_').replace(':', '');
  }

  // Para tablas de eventos: "Events: High Vol Runners" -> "events_high_vol_runners"
  if (title.startsWith('Events:')) {
    return title.toLowerCase().replace(/\s+/g, '_').replace(':', '');
  }

  // Para gráficos financieros: "AAPL — Revenue" -> "fa_chart_revenue"
  if (title.includes(' — ')) {
    const [, metric] = title.split(' — ');
    return `fa_chart_${metric.toLowerCase().replace(/\s+/g, '_')}`;
  }

  // Fallback
  return title.toLowerCase().replace(/\s+/g, '_');
}
