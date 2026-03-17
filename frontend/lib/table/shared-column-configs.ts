/**
 * Configuraciones compartidas de columnas para tablas de mercado
 * 
 * Centraliza las definiciones de columnas para evitar duplicación entre:
 * - Scanner (CategoryTableV2.tsx)
 * - Eventos (EventTableContent.tsx)
 * - Cualquier otra tabla futura
 * 
 * Cada configuración define:
 * - header: nombre visible de la columna
 * - size: ancho por defecto
 * - minSize/maxSize: límites de tamaño
 * - format: función de formateo
 * - cellClass: clases CSS condicionales
 * - enableHiding: si se puede ocultar/mostrar
 */

import { formatNumber, formatPercent, formatRVOL } from '@/lib/formatters';

export type ColumnFormat = 'number' | 'currency' | 'percent' | 'rvol' | 'volume' | 'marketcap' | 'custom';

export interface SharedColumnConfig {
  header: string;
  size: number;
  minSize?: number;
  maxSize?: number;
  enableHiding?: boolean;
  format?: ColumnFormat;
  /** Función de formateo personalizada */
  formatter?: (value: any) => string | React.ReactNode;
  /** Función para clases CSS condicionales */
  cellClass?: (value: any) => string;
  /** Sufijo para valores (ej: %, $, x) */
  suffix?: string;
}

/**
 * Configuraciones de todas las columnas disponibles
 * Organizadas por categoría para facilitar mantenimiento
 */
export const COLUMN_CONFIGS: Record<string, SharedColumnConfig> = {
  // ═══════════════════════════════════════════════════════════════
  // COLUMNAS ESENCIALES (siempre visibles)
  // ═══════════════════════════════════════════════════════════════
  timestamp: {
    header: 'Time',
    size: 70,
    minSize: 60,
    maxSize: 90,
    enableHiding: false,
  },
  symbol: {
    header: 'Symbol',
    size: 70,
    minSize: 60,
    maxSize: 100,
    enableHiding: false,
  },
  event_type: {
    header: 'Event',
    size: 90,
    minSize: 70,
    maxSize: 120,
    enableHiding: false,
  },

  // ═══════════════════════════════════════════════════════════════
  // PRECIO Y CAMBIOS
  // ═══════════════════════════════════════════════════════════════
  price: {
    header: 'Price',
    size: 80,
    minSize: 60,
    maxSize: 120,
    enableHiding: true,
    format: 'currency',
  },
  change_percent: {
    header: 'Change %',
    size: 90,
    minSize: 70,
    maxSize: 135,
    enableHiding: true,
    format: 'percent',
    cellClass: (value) => value >= 0 ? 'text-emerald-600' : 'text-rose-600',
  },
  change_from_open: {
    header: 'From Open',
    size: 80,
    minSize: 60,
    maxSize: 100,
    enableHiding: true,
    format: 'percent',
    cellClass: (value) => value > 0 ? 'text-emerald-600' : 'text-rose-600',
  },
  change_from_open_dollars: {
    header: 'From Open $',
    size: 85,
    minSize: 60,
    maxSize: 105,
    enableHiding: true,
    format: 'currency',
    cellClass: (value) => value > 0 ? 'text-emerald-600' : 'text-rose-600',
  },
  gap_percent: {
    header: 'Gap %',
    size: 65,
    minSize: 50,
    maxSize: 85,
    enableHiding: true,
    format: 'percent',
    cellClass: (value) => value > 0 ? 'text-emerald-600' : 'text-rose-600',
  },

  // ═══════════════════════════════════════════════════════════════
  // VOLUMEN
  // ═══════════════════════════════════════════════════════════════
  volume: {
    header: 'Volume',
    size: 75,
    minSize: 60,
    maxSize: 100,
    enableHiding: true,
    format: 'volume',
  },
  rvol: {
    header: 'RVOL',
    size: 60,
    minSize: 50,
    maxSize: 80,
    enableHiding: true,
    format: 'rvol',
  },
  vol_1min: {
    header: 'Volume 1m',
    size: 85,
    minSize: 65,
    maxSize: 105,
    enableHiding: true,
    format: 'volume',
  },
  vol_5min: {
    header: 'Volume 5m',
    size: 85,
    minSize: 65,
    maxSize: 105,
    enableHiding: true,
    format: 'volume',
  },
  vol_10min: {
    header: 'Volume 10m',
    size: 85,
    minSize: 65,
    maxSize: 105,
    enableHiding: true,
    format: 'volume',
  },
  vol_15min: {
    header: 'Volume 15m',
    size: 85,
    minSize: 65,
    maxSize: 105,
    enableHiding: true,
    format: 'volume',
  },
  vol_30min: {
    header: 'Volume 30m',
    size: 85,
    minSize: 65,
    maxSize: 105,
    enableHiding: true,
    format: 'volume',
  },

  // ═══════════════════════════════════════════════════════════════
  // VOLUMEN VENTANA % (Trade Ideas style)
  // ═══════════════════════════════════════════════════════════════
  vol_1min_pct: {
    header: 'Vol 1m %',
    size: 85,
    minSize: 65,
    maxSize: 105,
    enableHiding: true,
    format: 'percent',
    suffix: '%',
  },
  vol_5min_pct: {
    header: 'Vol 5m %',
    size: 85,
    minSize: 65,
    maxSize: 105,
    enableHiding: true,
    format: 'percent',
    suffix: '%',
  },
  vol_10min_pct: {
    header: 'Vol 10m %',
    size: 85,
    minSize: 65,
    maxSize: 105,
    enableHiding: true,
    format: 'percent',
    suffix: '%',
  },
  vol_15min_pct: {
    header: 'Vol 15m %',
    size: 85,
    minSize: 65,
    maxSize: 105,
    enableHiding: true,
    format: 'percent',
    suffix: '%',
  },
  vol_30min_pct: {
    header: 'Vol 30m %',
    size: 85,
    minSize: 65,
    maxSize: 105,
    enableHiding: true,
    format: 'percent',
    suffix: '%',
  },

  // ═══════════════════════════════════════════════════════════════
  // RANGE WINDOWS (Trade Ideas: Range2..Range120)
  // ═══════════════════════════════════════════════════════════════
  range_2min: { header: 'Range 2m $', size: 90, minSize: 70, maxSize: 110, enableHiding: true, format: 'currency', suffix: '$' },
  range_5min: { header: 'Range 5m $', size: 90, minSize: 70, maxSize: 110, enableHiding: true, format: 'currency', suffix: '$' },
  range_15min: { header: 'Range 15m $', size: 90, minSize: 70, maxSize: 110, enableHiding: true, format: 'currency', suffix: '$' },
  range_30min: { header: 'Range 30m $', size: 90, minSize: 70, maxSize: 110, enableHiding: true, format: 'currency', suffix: '$' },
  range_60min: { header: 'Range 60m $', size: 90, minSize: 70, maxSize: 110, enableHiding: true, format: 'currency', suffix: '$' },
  range_120min: { header: 'Range 120m $', size: 95, minSize: 75, maxSize: 115, enableHiding: true, format: 'currency', suffix: '$' },
  range_2min_pct: { header: 'Range 2m %', size: 90, minSize: 70, maxSize: 110, enableHiding: true, format: 'percent', suffix: '%' },
  range_5min_pct: { header: 'Range 5m %', size: 90, minSize: 70, maxSize: 110, enableHiding: true, format: 'percent', suffix: '%' },
  range_15min_pct: { header: 'Range 15m %', size: 90, minSize: 70, maxSize: 110, enableHiding: true, format: 'percent', suffix: '%' },
  range_30min_pct: { header: 'Range 30m %', size: 90, minSize: 70, maxSize: 110, enableHiding: true, format: 'percent', suffix: '%' },
  range_60min_pct: { header: 'Range 60m %', size: 90, minSize: 70, maxSize: 110, enableHiding: true, format: 'percent', suffix: '%' },
  range_120min_pct: { header: 'Range 120m %', size: 95, minSize: 75, maxSize: 115, enableHiding: true, format: 'percent', suffix: '%' },

  // ═══════════════════════════════════════════════════════════════
  // CAMBIOS POR VENTANA DE TIEMPO
  // ═══════════════════════════════════════════════════════════════
  chg_1min: {
    header: 'Change 1m',
    size: 85,
    minSize: 65,
    maxSize: 100,
    enableHiding: true,
    format: 'percent',
    cellClass: (value) => value > 0 ? 'text-emerald-600' : 'text-rose-600',
  },
  chg_5min: {
    header: 'Change 5m',
    size: 85,
    minSize: 65,
    maxSize: 100,
    enableHiding: true,
    format: 'percent',
    cellClass: (value) => value > 0 ? 'text-emerald-600' : 'text-rose-600',
  },
  chg_10min: {
    header: 'Change 10m',
    size: 85,
    minSize: 65,
    maxSize: 100,
    enableHiding: true,
    format: 'percent',
    cellClass: (value) => value > 0 ? 'text-emerald-600' : 'text-rose-600',
  },
  chg_15min: {
    header: 'Change 15m',
    size: 85,
    minSize: 65,
    maxSize: 100,
    enableHiding: true,
    format: 'percent',
    cellClass: (value) => value > 0 ? 'text-emerald-600' : 'text-rose-600',
  },
  chg_30min: {
    header: 'Change 30m',
    size: 85,
    minSize: 65,
    maxSize: 100,
    enableHiding: true,
    format: 'percent',
    cellClass: (value) => value > 0 ? 'text-emerald-600' : 'text-rose-600',
  },
  chg_60min: {
    header: 'Change 60m',
    size: 85,
    minSize: 65,
    maxSize: 100,
    enableHiding: true,
    format: 'percent',
    cellClass: (value) => value > 0 ? 'text-emerald-600' : 'text-rose-600',
  },

  // ═══════════════════════════════════════════════════════════════
  // FUNDAMENTALES
  // ═══════════════════════════════════════════════════════════════
  market_cap: {
    header: 'Market Cap',
    size: 85,
    minSize: 65,
    maxSize: 110,
    enableHiding: true,
    format: 'marketcap',
  },
  float_shares: {
    header: 'Float',
    size: 75,
    minSize: 60,
    maxSize: 95,
    enableHiding: true,
    format: 'volume',
  },
  shares_outstanding: {
    header: 'Shares Outstanding',
    size: 120,
    minSize: 90,
    maxSize: 150,
    enableHiding: true,
    format: 'volume',
  },

  // ═══════════════════════════════════════════════════════════════
  // INDICADORES TÉCNICOS INTRADAY
  // ═══════════════════════════════════════════════════════════════
  rsi: {
    header: 'RSI',
    size: 60,
    minSize: 50,
    maxSize: 75,
    enableHiding: true,
    format: 'number',
    cellClass: (value) => {
      if (value < 30) return 'text-green-600 font-semibold';
      if (value > 70) return 'text-red-600 font-semibold';
      return 'text-muted-fg';
    },
  },
  atr_percent: {
    header: 'ATR %',
    size: 65,
    minSize: 50,
    maxSize: 80,
    enableHiding: true,
    format: 'percent',
    cellClass: (value) => value > 5 ? 'text-orange-600 font-semibold' : 'text-muted-fg',
  },
  vwap: {
    header: 'VWAP',
    size: 70,
    minSize: 55,
    maxSize: 90,
    enableHiding: true,
    format: 'currency',
  },
  ema_20: {
    header: 'EMA(20)',
    size: 70,
    minSize: 55,
    maxSize: 90,
    enableHiding: true,
    format: 'currency',
  },
  ema_50: {
    header: 'EMA(50)',
    size: 70,
    minSize: 55,
    maxSize: 90,
    enableHiding: true,
    format: 'currency',
  },
  sma_5: {
    header: 'SMA(5)',
    size: 70,
    minSize: 55,
    maxSize: 90,
    enableHiding: true,
    format: 'currency',
  },
  sma_8: {
    header: 'SMA(8)',
    size: 70,
    minSize: 55,
    maxSize: 90,
    enableHiding: true,
    format: 'currency',
  },
  sma_20: {
    header: 'SMA(20)',
    size: 70,
    minSize: 55,
    maxSize: 90,
    enableHiding: true,
    format: 'currency',
  },
  sma_50: {
    header: 'SMA(50)',
    size: 70,
    minSize: 55,
    maxSize: 90,
    enableHiding: true,
    format: 'currency',
  },
  sma_200: {
    header: 'SMA(200)',
    size: 75,
    minSize: 60,
    maxSize: 95,
    enableHiding: true,
    format: 'currency',
  },

  // MACD, Stochastic, ADX, Bollinger
  macd_line: {
    header: 'MACD',
    size: 65,
    minSize: 50,
    maxSize: 80,
    enableHiding: true,
    format: 'number',
  },
  macd_hist: {
    header: 'MACD Histogram',
    size: 100,
    minSize: 80,
    maxSize: 120,
    enableHiding: true,
    format: 'number',
  },
  stoch_k: {
    header: 'Stochastic %K',
    size: 100,
    minSize: 80,
    maxSize: 120,
    enableHiding: true,
    format: 'number',
  },
  stoch_d: {
    header: 'Stochastic %D',
    size: 100,
    minSize: 80,
    maxSize: 120,
    enableHiding: true,
    format: 'number',
  },
  adx_14: {
    header: 'ADX',
    size: 60,
    minSize: 50,
    maxSize: 75,
    enableHiding: true,
    format: 'number',
  },
  bb_upper: {
    header: 'Bollinger Upper',
    size: 100,
    minSize: 80,
    maxSize: 120,
    enableHiding: true,
    format: 'currency',
  },
  bb_lower: {
    header: 'Bollinger Lower',
    size: 100,
    minSize: 80,
    maxSize: 120,
    enableHiding: true,
    format: 'currency',
  },

  // ═══════════════════════════════════════════════════════════════
  // INDICADORES DIARIOS
  // ═══════════════════════════════════════════════════════════════
  daily_sma_20: {
    header: 'Daily SMA(20)',
    size: 95,
    minSize: 75,
    maxSize: 115,
    enableHiding: true,
    format: 'currency',
  },
  daily_sma_50: {
    header: 'Daily SMA(50)',
    size: 95,
    minSize: 75,
    maxSize: 115,
    enableHiding: true,
    format: 'currency',
  },
  daily_sma_200: {
    header: 'Daily SMA(200)',
    size: 100,
    minSize: 80,
    maxSize: 120,
    enableHiding: true,
    format: 'currency',
  },
  daily_rsi: {
    header: 'Daily RSI',
    size: 70,
    minSize: 55,
    maxSize: 85,
    enableHiding: true,
    format: 'number',
  },
  daily_adx_14: {
    header: 'Daily ADX',
    size: 80,
    minSize: 60,
    maxSize: 100,
    enableHiding: true,
    format: 'number',
  },
  daily_atr_percent: {
    header: 'Daily ATR %',
    size: 85,
    minSize: 65,
    maxSize: 105,
    enableHiding: true,
    format: 'percent',
  },
  daily_bb_position: {
    header: 'Daily BB Position',
    size: 105,
    minSize: 80,
    maxSize: 125,
    enableHiding: true,
    format: 'percent',
  },

  // ═══════════════════════════════════════════════════════════════
  // 52 SEMANAS
  // ═══════════════════════════════════════════════════════════════
  high_52w: {
    header: '52w High',
    size: 70,
    minSize: 55,
    maxSize: 90,
    enableHiding: true,
    format: 'currency',
  },
  low_52w: {
    header: '52w Low',
    size: 70,
    minSize: 55,
    maxSize: 90,
    enableHiding: true,
    format: 'currency',
  },
  from_52w_high: {
    header: 'From 52W High %',
    size: 105,
    minSize: 80,
    maxSize: 125,
    enableHiding: true,
    format: 'percent',
  },
  from_52w_low: {
    header: 'From 52W Low %',
    size: 105,
    minSize: 80,
    maxSize: 125,
    enableHiding: true,
    format: 'percent',
  },

  // ═══════════════════════════════════════════════════════════════
  // DATOS DE COTIZACIÓN
  // ═══════════════════════════════════════════════════════════════
  bid: {
    header: 'Bid',
    size: 65,
    minSize: 50,
    maxSize: 80,
    enableHiding: true,
    format: 'currency',
  },
  ask: {
    header: 'Ask',
    size: 65,
    minSize: 50,
    maxSize: 80,
    enableHiding: true,
    format: 'currency',
  },
  bid_size: {
    header: 'Bid Size',
    size: 70,
    minSize: 55,
    maxSize: 85,
    enableHiding: true,
    format: 'volume',
  },
  ask_size: {
    header: 'Ask Size',
    size: 70,
    minSize: 55,
    maxSize: 85,
    enableHiding: true,
    format: 'volume',
  },
  spread: {
    header: 'Spread',
    size: 65,
    minSize: 50,
    maxSize: 80,
    enableHiding: true,
    format: 'currency',
  },

  // ═══════════════════════════════════════════════════════════════
  // OHLC (Contexto de evento)
  // ═══════════════════════════════════════════════════════════════
  open_price: {
    header: 'Open',
    size: 65,
    minSize: 50,
    maxSize: 80,
    enableHiding: true,
    format: 'currency',
  },
  prev_close: {
    header: 'Prev Close',
    size: 75,
    minSize: 60,
    maxSize: 95,
    enableHiding: true,
    format: 'currency',
  },
  intraday_high: {
    header: 'High',
    size: 65,
    minSize: 50,
    maxSize: 80,
    enableHiding: true,
    format: 'currency',
  },
  intraday_low: {
    header: 'Low',
    size: 65,
    minSize: 50,
    maxSize: 80,
    enableHiding: true,
    format: 'currency',
  },

  // ═══════════════════════════════════════════════════════════════
  // CAMPOS DE EVENTO (específicos de EventTableContent)
  // ═══════════════════════════════════════════════════════════════
  prev_value: {
    header: 'Prev Val',
    size: 70,
    minSize: 55,
    maxSize: 90,
    enableHiding: true,
    format: 'currency',
  },
  new_value: {
    header: 'New Val',
    size: 70,
    minSize: 55,
    maxSize: 90,
    enableHiding: true,
    format: 'currency',
  },
  delta: {
    header: 'Delta',
    size: 65,
    minSize: 50,
    maxSize: 85,
    enableHiding: true,
    format: 'number',
    cellClass: (value) => value > 0 ? 'text-emerald-600' : 'text-rose-600',
  },
  delta_percent: {
    header: 'Delta %',
    size: 70,
    minSize: 55,
    maxSize: 90,
    enableHiding: true,
    format: 'percent',
    cellClass: (value) => value > 0 ? 'text-emerald-600' : 'text-rose-600',
  },

  // ═══════════════════════════════════════════════════════════════
  // CLASIFICACIÓN
  // ═══════════════════════════════════════════════════════════════
  security_type: {
    header: 'Type',
    size: 70,
    minSize: 55,
    maxSize: 90,
    enableHiding: true,
  },
  sector: {
    header: 'Sector',
    size: 90,
    minSize: 70,
    maxSize: 120,
    enableHiding: true,
  },
  industry: {
    header: 'Industry',
    size: 100,
    minSize: 80,
    maxSize: 140,
    enableHiding: true,
  },

  // ═══════════════════════════════════════════════════════════════
  // CAMPOS DERIVADOS / COMPUTADOS
  // ═══════════════════════════════════════════════════════════════
  dollar_volume: {
    header: '$ Volume',
    size: 80,
    minSize: 65,
    maxSize: 100,
    enableHiding: true,
    format: 'marketcap',
  },
  todays_range: {
    header: 'Range $',
    size: 70,
    minSize: 55,
    maxSize: 85,
    enableHiding: true,
    format: 'currency',
  },
  todays_range_pct: {
    header: 'Range %',
    size: 70,
    minSize: 55,
    maxSize: 85,
    enableHiding: true,
    format: 'percent',
  },
  bid_ask_ratio: {
    header: 'Bid/Ask Ratio',
    size: 90,
    minSize: 70,
    maxSize: 110,
    enableHiding: true,
    format: 'number',
  },
  float_turnover: {
    header: 'Float Turnover',
    size: 95,
    minSize: 75,
    maxSize: 115,
    enableHiding: true,
    format: 'number',
    suffix: 'x',
  },
  pos_in_range: {
    header: 'Position in Range',
    size: 105,
    minSize: 80,
    maxSize: 125,
    enableHiding: true,
    format: 'percent',
  },
  below_high: {
    header: 'Below High',
    size: 80,
    minSize: 60,
    maxSize: 100,
    enableHiding: true,
    format: 'currency',
  },
  above_low: {
    header: 'Above Low',
    size: 80,
    minSize: 60,
    maxSize: 100,
    enableHiding: true,
    format: 'currency',
  },
  pos_of_open: {
    header: 'Position of Open',
    size: 105,
    minSize: 80,
    maxSize: 125,
    enableHiding: true,
    format: 'percent',
  },
  prev_day_volume: {
    header: 'Previous Volume',
    size: 105,
    minSize: 80,
    maxSize: 125,
    enableHiding: true,
    format: 'volume',
  },

  // ═══════════════════════════════════════════════════════════════
  // DISTANCIAS DE INDICADORES
  // ═══════════════════════════════════════════════════════════════
  dist_from_vwap: {
    header: 'Distance VWAP',
    size: 100,
    minSize: 80,
    maxSize: 120,
    enableHiding: true,
    format: 'percent',
  },
  dist_sma_5: {
    header: 'Distance SMA 5',
    size: 100,
    minSize: 80,
    maxSize: 120,
    enableHiding: true,
    format: 'percent',
  },
  dist_sma_8: {
    header: 'Distance SMA 8',
    size: 100,
    minSize: 80,
    maxSize: 120,
    enableHiding: true,
    format: 'percent',
  },
  dist_sma_20: {
    header: 'Distance SMA 20',
    size: 100,
    minSize: 80,
    maxSize: 120,
    enableHiding: true,
    format: 'percent',
  },
  dist_sma_50: {
    header: 'Distance SMA 50',
    size: 100,
    minSize: 80,
    maxSize: 120,
    enableHiding: true,
    format: 'percent',
  },
  dist_sma_200: {
    header: 'Distance SMA 200',
    size: 105,
    minSize: 85,
    maxSize: 125,
    enableHiding: true,
    format: 'percent',
  },
  dist_daily_sma_20: {
    header: 'Dist Daily SMA 20',
    size: 110,
    minSize: 90,
    maxSize: 130,
    enableHiding: true,
    format: 'percent',
  },
  dist_daily_sma_50: {
    header: 'Dist Daily SMA 50',
    size: 110,
    minSize: 90,
    maxSize: 130,
    enableHiding: true,
    format: 'percent',
  },

  // ═══════════════════════════════════════════════════════════════
  // CAMBIOS MULTI-DÍA
  // ═══════════════════════════════════════════════════════════════
  change_1d: {
    header: '1 Day',
    size: 65,
    minSize: 50,
    maxSize: 80,
    enableHiding: true,
    format: 'percent',
    cellClass: (value) => value > 0 ? 'text-emerald-600' : 'text-rose-600',
  },
  change_3d: {
    header: '3 Days',
    size: 65,
    minSize: 50,
    maxSize: 80,
    enableHiding: true,
    format: 'percent',
    cellClass: (value) => value > 0 ? 'text-emerald-600' : 'text-rose-600',
  },
  change_5d: {
    header: '5 Days',
    size: 65,
    minSize: 50,
    maxSize: 80,
    enableHiding: true,
    format: 'percent',
    cellClass: (value) => value > 0 ? 'text-emerald-600' : 'text-rose-600',
  },
  change_10d: {
    header: '10 Days',
    size: 70,
    minSize: 55,
    maxSize: 85,
    enableHiding: true,
    format: 'percent',
    cellClass: (value) => value > 0 ? 'text-emerald-600' : 'text-rose-600',
  },
  change_20d: {
    header: '20 Days',
    size: 70,
    minSize: 55,
    maxSize: 85,
    enableHiding: true,
    format: 'percent',
    cellClass: (value) => value > 0 ? 'text-emerald-600' : 'text-rose-600',
  },

  // ═══════════════════════════════════════════════════════════════
  // VOLÚMENES PROMEDIO
  // ═══════════════════════════════════════════════════════════════
  avg_volume_5d: {
    header: 'Avg 5D',
    size: 75,
    minSize: 60,
    maxSize: 95,
    enableHiding: true,
    format: 'volume',
  },
  avg_volume_10d: {
    header: 'Avg 10D',
    size: 75,
    minSize: 60,
    maxSize: 95,
    enableHiding: true,
    format: 'volume',
  },
  avg_volume_20d: {
    header: 'Avg 20D',
    size: 75,
    minSize: 60,
    maxSize: 95,
    enableHiding: true,
    format: 'volume',
  },
  avg_volume_3m: {
    header: 'Average 3M',
    size: 85,
    minSize: 65,
    maxSize: 105,
    enableHiding: true,
    format: 'volume',
  },

  // ═══════════════════════════════════════════════════════════════
  // OTROS (específicos de Scanner)
  // ═══════════════════════════════════════════════════════════════
  volume_today_pct: {
    header: 'Volume Today %',
    size: 100,
    minSize: 80,
    maxSize: 120,
    enableHiding: true,
    format: 'percent',
  },
  price_from_high: {
    header: 'From High',
    size: 75,
    minSize: 60,
    maxSize: 95,
    enableHiding: true,
    format: 'percent',
  },
  price_from_low: {
    header: 'From Low',
    size: 75,
    minSize: 60,
    maxSize: 95,
    enableHiding: true,
    format: 'percent',
  },
  price_from_intraday_high: {
    header: 'From Hi',
    size: 70,
    minSize: 55,
    maxSize: 90,
    enableHiding: true,
    format: 'percent',
  },
  price_from_intraday_low: {
    header: 'From Lo',
    size: 70,
    minSize: 55,
    maxSize: 90,
    enableHiding: true,
    format: 'percent',
  },
  distance_from_nbbo: {
    header: 'NBBO Dist',
    size: 75,
    minSize: 60,
    maxSize: 95,
    enableHiding: true,
    format: 'percent',
  },
  premarket_change_percent: {
    header: 'Pre-Mkt%',
    size: 75,
    minSize: 60,
    maxSize: 95,
    enableHiding: true,
    format: 'percent',
  },
  postmarket_change_percent: {
    header: 'Post-Mkt%',
    size: 75,
    minSize: 60,
    maxSize: 95,
    enableHiding: true,
    format: 'percent',
  },
  postmarket_volume: {
    header: 'PM Vol',
    size: 80,
    minSize: 60,
    maxSize: 100,
    enableHiding: true,
    format: 'volume',
  },
  atr: {
    header: 'ATR $',
    size: 65,
    minSize: 50,
    maxSize: 80,
    enableHiding: true,
    format: 'currency',
  },
  trades_today: {
    header: 'Trades',
    size: 70,
    minSize: 55,
    maxSize: 85,
    enableHiding: true,
    format: 'number',
  },
  trades_z_score: {
    header: 'Z-Score',
    size: 70,
    minSize: 55,
    maxSize: 85,
    enableHiding: true,
    format: 'number',
  },
};

/**
 * Helper para formatear valores según el tipo
 */
export function formatValue(value: any, format?: ColumnFormat, suffix?: string): string {
  if (value === undefined || value === null) return '-';

  switch (format) {
    case 'currency':
      return `$${typeof value === 'number' ? value.toFixed(2) : value}`;
    case 'percent':
      return formatPercent(value);
    case 'rvol':
      return formatRVOL(value);
    case 'volume':
      return formatNumber(value);
    case 'marketcap':
      if (value >= 1e12) return `$${(value / 1e12).toFixed(1)}T`;
      if (value >= 1e9) return `$${(value / 1e9).toFixed(1)}B`;
      if (value >= 1e6) return `$${(value / 1e6).toFixed(0)}M`;
      return `$${formatNumber(value)}`;
    case 'number':
      return typeof value === 'number' ? value.toFixed(2) : String(value);
    default:
      return String(value);
  }
}

/**
 * Obtener configuración de columna con defaults
 */
export function getColumnConfig(field: string): SharedColumnConfig {
  return COLUMN_CONFIGS[field] || {
    header: field,
    size: 80,
    minSize: 60,
    maxSize: 120,
    enableHiding: true,
  };
}
