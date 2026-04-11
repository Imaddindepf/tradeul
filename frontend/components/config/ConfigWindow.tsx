'use client';

/**
 * ConfigWindow - Strategy Builder (estilo Trade Ideas Alert Config Window)
 *
 * Tabs: Strategies | Alerts | Filters | Symbols | Summary
 *
 * Strategies tab: carpetas (Recent, Favorites, Bullish, Bearish, Neutral, Custom, Built-in)
 *   - panel izquierdo: arbol de carpetas con estrategias
 *   - panel derecho: detalle de la estrategia seleccionada (alerts + filters)
 *   - Start from Scratch, Load Settings
 *
 * Crea/guarda estrategias en BD via useAlertStrategies + abre Alert Window
 */

import { useState, useCallback, useMemo, useEffect } from 'react';
import { useAlertStrategies, type AlertStrategy, type CreateStrategyData } from '@/hooks/useAlertStrategies';
import { useUserFilters } from '@/hooks/useUserFilters';
import { BUILT_IN_PRESETS, type AlertPreset, BUILT_IN_TOP_LISTS, type TopListPreset, ALERT_CATEGORIES, ALERT_CATALOG, ALERT_BY_EVENT_TYPE, getAlertsByCategory, searchAlerts } from '@/lib/alert-catalog';
import { useEventFiltersStore, type ActiveEventFilters } from '@/stores/useEventFiltersStore';
import type { UserFilter } from '@/lib/types/scannerFilters';
import { SECURITY_TYPES, SECTORS, INDUSTRIES } from '@/lib/constants/filters';

// ============================================================================
// Types
// ============================================================================

type BuilderMode = 'strategy' | 'toplist';
type ConfigTab = 'saved' | 'alerts' | 'filters' | 'symbols' | 'summary';

export interface AlertWindowConfig {
  name: string;
  eventTypes: string[];
  filters: ActiveEventFilters;
  symbolsInclude: string[];
  symbolsExclude: string[];
  /** ID de la estrategia de usuario de origen, para sincronización al restaurar workspace */
  strategyId?: number;
}

export interface BacktestFromConfigData {
  eventTypes: string[];
  filters: Record<string, any>;
  name: string;
}

interface ConfigWindowProps {
  onCreateAlertWindow?: (config: AlertWindowConfig) => void;
  onBacktestStrategy?: (data: BacktestFromConfigData) => void;
  onCreateScannerWindow?: (filter: UserFilter) => void;
  /** Pre-load existing config (for reconfiguring an existing window) */
  initialAlerts?: string[];
  initialFilters?: Record<string, any>;
  initialSymbolsInclude?: string;
  initialSymbolsExclude?: string;
  initialName?: string;
  /** Start on a specific tab */
  initialTab?: ConfigTab;
  /** Start in a specific mode */
  initialMode?: BuilderMode;
  /** If provided, read live filters from the store instead of static initialFilters */
  sourceCategoryId?: string;
}

// ============================================================================
// Strategy folder definitions
// ============================================================================

const STRATEGY_FOLDERS = [
  { id: 'recent', label: 'Recent', labelEs: 'Recientes' },
  { id: 'favorites', label: 'Favorites', labelEs: 'Favoritos' },
  { id: 'bullish', label: 'Bullish Strategies', labelEs: 'Estrategias Alcistas' },
  { id: 'bearish', label: 'Bearish Strategies', labelEs: 'Estrategias Bajistas' },
  { id: 'neutral', label: 'Neutral Strategies', labelEs: 'Estrategias Neutrales' },
  { id: 'custom', label: 'My Strategies', labelEs: 'Mis Estrategias' },
  { id: 'builtin', label: 'Built-in', labelEs: 'Del Sistema' },
] as const;

const TOPLIST_FOLDERS = [
  { id: 'all', label: 'All Top Lists', labelEs: 'Todas las Listas' },
  { id: 'active', label: 'Active', labelEs: 'Activas' },
  { id: 'inactive', label: 'Inactive', labelEs: 'Inactivas' },
  { id: 'builtin', label: 'Built-in', labelEs: 'Del Sistema' },
] as const;

// ============================================================================
// Filter metadata — single source of truth for labels and suffixes.
// Generated from FG filter definitions. Every key must be here.
// ============================================================================

const FILTER_META: Record<string, { label: string; suf: string }> = {
  'industry': { label: 'Industry', suf: '' },
  'max_above_low': { label: 'Above Low <', suf: '$' },
  'max_above_premarket_low': { label: 'Above Pre-Market Low <', suf: '$' },
  'max_adx_14': { label: 'ADX (Intraday) <', suf: '' },
  'max_ask_size': { label: 'Ask Size <', suf: '' },
  'max_atr': { label: 'Average True Range <', suf: '$' },
  'max_atr_percent': { label: 'Average True Range % <', suf: '%' },
  'max_avg_volume_10d': { label: 'Average Daily Volume (10D) <', suf: '' },
  'max_avg_volume_20d': { label: 'Average Daily Volume (20D) <', suf: '' },
  'max_avg_volume_3m': { label: 'Average Daily Volume (3M) <', suf: '' },
  'max_avg_volume_5d': { label: 'Average Daily Volume (5D) <', suf: '' },
  'max_bb_lower': { label: 'Bollinger Lower <', suf: '$' },
  'max_bb_position_15m': { label: 'Position in Bollinger Bands (15m) <', suf: '%' },
  'max_bb_position_1m': { label: 'Position in Bollinger Bands (1m) <', suf: '%' },
  'max_bb_position_5m': { label: 'Position in Bollinger Bands (5m) <', suf: '%' },
  'max_bb_position_60m': { label: 'Position in Bollinger Bands (60m) <', suf: '%' },
  'max_bb_std_dev': { label: 'Standard Deviation (Bollinger) <', suf: '$' },
  'max_bb_upper': { label: 'Bollinger Upper <', suf: '$' },
  'max_below_high': { label: 'Below High <', suf: '$' },
  'max_below_premarket_high': { label: 'Below Pre-Market High <', suf: '$' },
  'max_bid_ask_ratio': { label: 'Bid / Ask Ratio <', suf: '' },
  'max_bid_size': { label: 'Bid Size <', suf: '' },
  'max_change_10d': { label: 'Change in 10 Days <', suf: '%' },
  'max_change_10d_dollars': { label: 'Change in 10 Days $ <', suf: '$' },
  'max_change_1d': { label: 'Change Previous Day <', suf: '%' },
  'max_change_1y': { label: 'Change in 1 Year % <', suf: '%' },
  'max_change_1y_dollars': { label: 'Change in 1 Year $ <', suf: '$' },
  'max_change_20d': { label: 'Change in 20 Days <', suf: '%' },
  'max_change_20d_dollars': { label: 'Change in 20 Days $ <', suf: '$' },
  'max_change_3d': { label: 'Change in 3 Days <', suf: '%' },
  'max_change_5d': { label: 'Change in 5 Days <', suf: '%' },
  'max_change_5d_dollars': { label: 'Change in 5 Days $ <', suf: '$' },
  'max_change_from_close_dollars': { label: 'Change from the Close $ <', suf: '$' },
  'max_change_from_close_ratio': { label: 'Change from the Close (ATR) <', suf: 'x' },
  'max_change_from_open': { label: 'Change from the Open % <', suf: '%' },
  'max_change_from_open_dollars': { label: 'Change from the Open $ <', suf: '$' },
  'max_change_from_open_ratio': { label: 'Change from the Open (ATR) <', suf: 'x' },
  'max_change_from_open_weighted': { label: 'Change from the Open Weighted <', suf: '' },
  'max_change_percent': { label: 'Change from the Close % <', suf: '%' },
  'max_change_prev_day_pct': { label: 'Change Previous Day % <', suf: '%' },
  'max_change_ytd': { label: 'Change Since January 1 % <', suf: '%' },
  'max_change_ytd_dollars': { label: 'Change Since January 1 $ <', suf: '$' },
  'max_chg_10min': { label: 'Change 10 Minute <', suf: '%' },
  'max_chg_10min_dollars': { label: 'Change 10 Minute <', suf: '$' },
  'max_chg_120min': { label: 'Change 120 Minute <', suf: '%' },
  'max_chg_120min_dollars': { label: 'Change 120 Minute <', suf: '$' },
  'max_chg_15min': { label: 'Change 15 Minute <', suf: '%' },
  'max_chg_15min_dollars': { label: 'Change 15 Minute <', suf: '$' },
  'max_chg_1min': { label: 'Change 1 Minute <', suf: '%' },
  'max_chg_1min_dollars': { label: 'Change 1 Minute <', suf: '$' },
  'max_chg_2min': { label: 'Change 2 Minute <', suf: '%' },
  'max_chg_2min_dollars': { label: 'Change 2 Minute <', suf: '$' },
  'max_chg_30min': { label: 'Change 30 Minute <', suf: '%' },
  'max_chg_30min_dollars': { label: 'Change 30 Minute <', suf: '$' },
  'max_chg_5min': { label: 'Change 5 Minute <', suf: '%' },
  'max_chg_5min_dollars': { label: 'Change 5 Minute <', suf: '$' },
  'max_chg_60min': { label: 'Change 60 Minute <', suf: '%' },
  'max_chg_60min_dollars': { label: 'Change 60 Minute <', suf: '$' },
  'max_consecutive_candles': { label: 'Consecutive Candles (1m) <', suf: '' },
  'max_consecutive_candles_10m': { label: 'Consecutive Candles (10m) <', suf: '' },
  'max_consecutive_candles_15m': { label: 'Consecutive Candles (15m) <', suf: '' },
  'max_consecutive_candles_2m': { label: 'Consecutive Candles (2m) <', suf: '' },
  'max_consecutive_candles_30m': { label: 'Consecutive Candles (30m) <', suf: '' },
  'max_consecutive_candles_5m': { label: 'Consecutive Candles (5m) <', suf: '' },
  'max_consecutive_candles_60m': { label: 'Consecutive Candles (60m) <', suf: '' },
  'max_consecutive_days_up': { label: 'Consecutive Days Up/Down <', suf: '' },
  'max_consolidation_days': { label: 'Consolidation Days <', suf: '' },
  'max_daily_adx_14': { label: 'Average Directional Index (Daily) <', suf: '' },
  'max_daily_atr_percent': { label: 'Daily ATR % <', suf: '%' },
  'max_daily_bb_position': { label: 'Position in Bollinger Bands (Daily) <', suf: '%' },
  'max_daily_rsi': { label: 'Daily RSI <', suf: '' },
  'max_daily_sma_10': { label: '10 Day SMA <', suf: '$' },
  'max_daily_sma_20': { label: '20 Day SMA <', suf: '$' },
  'max_daily_sma_200': { label: '200 Day SMA <', suf: '$' },
  'max_daily_sma_5': { label: '5 Day SMA <', suf: '$' },
  'max_daily_sma_50': { label: '50 Day SMA <', suf: '$' },
  'max_daily_sma_8': { label: '8 Day SMA <', suf: '$' },
  'max_decimal': { label: 'Decimal <', suf: '' },
  'max_dist_daily_sma_10': { label: 'Change from 10 Day SMA % <', suf: '%' },
  'max_dist_daily_sma_10_dollars': { label: 'Change from 10 Day SMA $ <', suf: '$' },
  'max_dist_daily_sma_20': { label: 'Change from 20 Day SMA % <', suf: '%' },
  'max_dist_daily_sma_20_dollars': { label: 'Change from 20 Day SMA $ <', suf: '$' },
  'max_dist_daily_sma_200': { label: 'Change from 200 Day SMA % <', suf: '%' },
  'max_dist_daily_sma_200_dollars': { label: 'Change from 200 Day SMA $ <', suf: '$' },
  'max_dist_daily_sma_5': { label: 'Change from 5 Day SMA % <', suf: '%' },
  'max_dist_daily_sma_5_dollars': { label: 'Change from 5 Day SMA $ <', suf: '$' },
  'max_dist_daily_sma_50': { label: 'Change from 50 Day SMA % <', suf: '%' },
  'max_dist_daily_sma_50_dollars': { label: 'Change from 50 Day SMA $ <', suf: '$' },
  'max_dist_daily_sma_8': { label: 'Change from 8 Day SMA % <', suf: '%' },
  'max_dist_daily_sma_8_dollars': { label: 'Change from 8 Day SMA $ <', suf: '$' },
  'max_dist_from_vwap': { label: 'Distance from VWAP <', suf: '%' },
  'max_dist_pivot': { label: 'Distance from Pivot <', suf: '%' },
  'max_dist_pivot_r1': { label: 'Distance from Pivot R1 <', suf: '%' },
  'max_dist_pivot_r2': { label: 'Distance from Pivot R2 <', suf: '%' },
  'max_dist_pivot_s1': { label: 'Distance from Pivot S1 <', suf: '%' },
  'max_dist_pivot_s2': { label: 'Distance from Pivot S2 <', suf: '%' },
  'max_dist_sma_10_15m': { label: 'Change from 10 Period SMA (15m) <', suf: '%' },
  'max_dist_sma_10_2m': { label: 'Change from 10 Period SMA (2m) <', suf: '%' },
  'max_dist_sma_10_5m': { label: 'Change from 10 Period SMA (5m) <', suf: '%' },
  'max_dist_sma_10_60m': { label: 'Change from 10 Period SMA (60m) <', suf: '%' },
  'max_dist_sma_130_15m': { label: 'Change from 130 Period SMA (15m) <', suf: '%' },
  'max_dist_sma_20': { label: 'Change from SMA 20 (Intraday) <', suf: '%' },
  'max_dist_sma_20_15m': { label: 'Change from 20 Period SMA (15m) <', suf: '%' },
  'max_dist_sma_20_2m': { label: 'Change from 20 Period SMA (2m) <', suf: '%' },
  'max_dist_sma_20_5m': { label: 'Change from 20 Period SMA (5m) <', suf: '%' },
  'max_dist_sma_20_60m': { label: 'Change from 20 Period SMA (60m) <', suf: '%' },
  'max_dist_sma_200': { label: 'Change from SMA 200 (Intraday) <', suf: '%' },
  'max_dist_sma_200_15m': { label: 'Change from 200 Period SMA (15m) <', suf: '%' },
  'max_dist_sma_200_2m': { label: 'Change from 200 Period SMA (2m) <', suf: '%' },
  'max_dist_sma_200_5m': { label: 'Change from 200 Period SMA (5m) <', suf: '%' },
  'max_dist_sma_200_60m': { label: 'Change from 200 Period SMA (60m) <', suf: '%' },
  'max_dist_sma_5': { label: 'Change from SMA 5 (Intraday) <', suf: '%' },
  'max_dist_sma_5_15m': { label: 'Change from 5 Period SMA (15m) <', suf: '%' },
  'max_dist_sma_5_2m': { label: 'Change from 5 Period SMA (2m) <', suf: '%' },
  'max_dist_sma_5_5m': { label: 'Change from 5 Period SMA (5m) <', suf: '%' },
  'max_dist_sma_5_60m': { label: 'Change from 5 Period SMA (60m) <', suf: '%' },
  'max_dist_sma_50': { label: 'Change from SMA 50 (Intraday) <', suf: '%' },
  'max_dist_sma_8': { label: 'Change from SMA 8 (Intraday) <', suf: '%' },
  'max_dist_sma_8_15m': { label: 'Change from 8 Period SMA (15m) <', suf: '%' },
  'max_dist_sma_8_2m': { label: 'Change from 8 Period SMA (2m) <', suf: '%' },
  'max_dist_sma_8_5m': { label: 'Change from 8 Period SMA (5m) <', suf: '%' },
  'max_dist_sma_8_60m': { label: 'Change from 8 Period SMA (60m) <', suf: '%' },
  'max_distance_from_nbbo': { label: 'Distance from Inside Market <', suf: '%' },
  'max_dollar_volume': { label: 'Dollar Volume <', suf: '$' },
  'max_ema_20': { label: 'EMA 20 <', suf: '$' },
  'max_ema_50': { label: 'EMA 50 <', suf: '$' },
  'max_float_shares': { label: 'Float <', suf: '' },
  'max_float_turnover': { label: 'Float Turnover <', suf: 'x' },
  'max_from_52w_high': { label: 'From 52 Week High % <', suf: '%' },
  'max_from_52w_low': { label: 'From 52 Week Low % <', suf: '%' },
  'max_gap_dollars': { label: 'Gap $ <', suf: '$' },
  'max_gap_percent': { label: 'Gap % <', suf: '%' },
  'max_gap_ratio': { label: 'Gap (ATR) <', suf: 'x' },
  'max_high_52w': { label: '52 Week High <', suf: '$' },
  'max_low_52w': { label: '52 Week Low <', suf: '$' },
  'max_lr_divergence_130': { label: 'Linear Regression Divergence <', suf: '%' },
  'max_macd_hist': { label: 'MACD Histogram <', suf: '' },
  'max_macd_line': { label: 'MACD Line <', suf: '' },
  'max_market_cap': { label: 'Market Cap <', suf: '$' },
  'max_minute_volume': { label: 'Minute Volume <', suf: '' },
  'max_minutes_since_open': { label: 'Minutes Since Open <', suf: 'min' },
  'max_plus_di_minus_di': { label: 'Directional Indicator (+DI - -DI) <', suf: '' },
  'max_pos_in_10d_range': { label: 'Position in 10 Day Range <', suf: '%' },
  'max_pos_in_20d_range': { label: 'Position in 20 Day Range <', suf: '%' },
  'max_pos_in_2y_range': { label: 'Position in 2 Year Range <', suf: '%' },
  'max_pos_in_3m_range': { label: 'Position in 3 Month Range <', suf: '%' },
  'max_pos_in_52w_range': { label: 'Position in 52 Week Range <', suf: '%' },
  'max_pos_in_5d_range': { label: 'Position in 5 Day Range <', suf: '%' },
  'max_pos_in_6m_range': { label: 'Position in 6 Month Range <', suf: '%' },
  'max_pos_in_9m_range': { label: 'Position in 9 Month Range <', suf: '%' },
  'max_pos_in_consolidation': { label: 'Position in Consolidation <', suf: '%' },
  'max_pos_in_lifetime_range': { label: 'Position in Lifetime Range <', suf: '%' },
  'max_pos_in_premarket_range': { label: 'Position in Pre-Market Range <', suf: '%' },
  'max_pos_in_range': { label: 'Position in Range (Today) <', suf: '%' },
  'max_pos_in_range_15m': { label: 'Position in 15 Minute Range <', suf: '%' },
  'max_pos_in_range_30m': { label: 'Position in 30 Minute Range <', suf: '%' },
  'max_pos_in_range_5m': { label: 'Position in 5 Minute Range <', suf: '%' },
  'max_pos_in_range_60m': { label: 'Position in 60 Minute Range <', suf: '%' },
  'max_pos_of_open': { label: 'Position of Open <', suf: '%' },
  'max_postmarket_change_dollars': { label: 'Change Post-Market $ <', suf: '$' },
  'max_postmarket_change_percent': { label: 'Change Post-Market % <', suf: '%' },
  'max_postmarket_volume': { label: 'Post-Market Volume <', suf: '' },
  'max_premarket_change_percent': { label: 'Change Pre-Market % <', suf: '%' },
  'max_prev_day_volume': { label: 'Previous Day Volume <', suf: '' },
  'max_price': { label: 'Price <', suf: '$' },
  'max_price_from_high': { label: 'From High % <', suf: '%' },
  'max_price_from_intraday_high': { label: 'From Intraday High % <', suf: '%' },
  'max_price_from_intraday_low': { label: 'From Intraday Low % <', suf: '%' },
  'max_price_from_low': { label: 'From Low % <', suf: '%' },
  'max_range_10d': { label: '10 Day Range $ <', suf: '$' },
  'max_range_10d_pct': { label: '10 Day Range % <', suf: '%' },
  'max_range_120min': { label: '120 Minute Range $ <', suf: '$' },
  'max_range_120min_pct': { label: '120 Minute Range % <', suf: '%' },
  'max_range_15min': { label: '15 Minute Range $ <', suf: '$' },
  'max_range_15min_pct': { label: '15 Minute Range % <', suf: '%' },
  'max_range_20d': { label: '20 Day Range $ <', suf: '$' },
  'max_range_20d_pct': { label: '20 Day Range % <', suf: '%' },
  'max_range_2min': { label: '2 Minute Range $ <', suf: '$' },
  'max_range_2min_pct': { label: '2 Minute Range % <', suf: '%' },
  'max_range_30min': { label: '30 Minute Range $ <', suf: '$' },
  'max_range_30min_pct': { label: '30 Minute Range % <', suf: '%' },
  'max_range_5d': { label: '5 Day Range $ <', suf: '$' },
  'max_range_5d_pct': { label: '5 Day Range % <', suf: '%' },
  'max_range_5min': { label: '5 Minute Range $ <', suf: '$' },
  'max_range_5min_pct': { label: '5 Minute Range % <', suf: '%' },
  'max_range_60min': { label: '60 Minute Range $ <', suf: '$' },
  'max_range_60min_pct': { label: '60 Minute Range % <', suf: '%' },
  'max_range_contraction': { label: 'Range Contraction <', suf: '' },
  'max_rsi': { label: 'RSI (1m) <', suf: '' },
  'max_rsi_15m': { label: '15 Minute RSI <', suf: '' },
  'max_rsi_2m': { label: '2 Minute RSI <', suf: '' },
  'max_rsi_5m': { label: '5 Minute RSI <', suf: '' },
  'max_rsi_60m': { label: '60 Minute RSI <', suf: '' },
  'max_rvol': { label: 'Relative Volume <', suf: 'x' },
  'max_shares_outstanding': { label: 'Shares Outstanding <', suf: '' },
  'max_sma_20': { label: 'SMA 20 <', suf: '$' },
  'max_sma_20_vs_200_15m': { label: '20 vs. 200 Period SMA (15m) <', suf: '%' },
  'max_sma_20_vs_200_2m': { label: '20 vs. 200 Period SMA (2m) <', suf: '%' },
  'max_sma_20_vs_200_5m': { label: '20 vs. 200 Period SMA (5m) <', suf: '%' },
  'max_sma_20_vs_200_60m': { label: '20 vs. 200 Period SMA (60m) <', suf: '%' },
  'max_sma_200': { label: 'SMA 200 <', suf: '$' },
  'max_sma_5': { label: 'SMA 5 <', suf: '$' },
  'max_sma_50': { label: 'SMA 50 <', suf: '$' },
  'max_sma_8': { label: 'SMA 8 <', suf: '$' },
  'max_sma_8_vs_20_15m': { label: '8 vs. 20 Period SMA (15m) <', suf: '%' },
  'max_sma_8_vs_20_2m': { label: '8 vs. 20 Period SMA (2m) <', suf: '%' },
  'max_sma_8_vs_20_5m': { label: '8 vs. 20 Period SMA (5m) <', suf: '%' },
  'max_sma_8_vs_20_60m': { label: '8 vs. 20 Period SMA (60m) <', suf: '%' },
  'max_spread': { label: 'Spread <', suf: '$' },
  'max_stoch_d': { label: 'Stochastic %D <', suf: '' },
  'max_stoch_k': { label: 'Stochastic %K <', suf: '' },
  'max_trades_today': { label: 'Average Number of Prints <', suf: '' },
  'max_trades_z_score': { label: 'Trades Z-Score <', suf: '' },
  'max_vol_10min': { label: 'Volume 10 Minute <', suf: '' },
  'max_vol_10min_pct': { label: 'Average Volume 10m % <', suf: '%' },
  'max_vol_15min': { label: 'Volume 15 Minute <', suf: '' },
  'max_vol_15min_pct': { label: 'Average Volume 15m % <', suf: '%' },
  'max_vol_1min': { label: 'Volume 1 Minute <', suf: '' },
  'max_vol_1min_pct': { label: 'Average Volume 1m % <', suf: '%' },
  'max_vol_30min': { label: 'Volume 30 Minute <', suf: '' },
  'max_vol_30min_pct': { label: 'Average Volume 30m % <', suf: '%' },
  'max_vol_5min': { label: 'Volume 5 Minute <', suf: '' },
  'max_vol_5min_pct': { label: 'Average Volume 5m % <', suf: '%' },
  'max_volume': { label: 'Volume Today <', suf: '' },
  'max_volume_today_pct': { label: 'Volume Today % <', suf: '%' },
  'max_volume_yesterday_pct': { label: 'Volume Yesterday % <', suf: '%' },
  'max_vwap': { label: 'VWAP <', suf: '$' },
  'max_yearly_std_dev': { label: 'Yearly Standard Deviation <', suf: '$' },
  'min_above_low': { label: 'Above Low >', suf: '$' },
  'min_above_premarket_low': { label: 'Above Pre-Market Low >', suf: '$' },
  'min_adx_14': { label: 'ADX (Intraday) >', suf: '' },
  'min_ask_size': { label: 'Ask Size >', suf: '' },
  'min_atr': { label: 'Average True Range >', suf: '$' },
  'min_atr_percent': { label: 'Average True Range % >', suf: '%' },
  'min_avg_volume_10d': { label: 'Average Daily Volume (10D) >', suf: '' },
  'min_avg_volume_20d': { label: 'Average Daily Volume (20D) >', suf: '' },
  'min_avg_volume_3m': { label: 'Average Daily Volume (3M) >', suf: '' },
  'min_avg_volume_5d': { label: 'Average Daily Volume (5D) >', suf: '' },
  'min_bb_lower': { label: 'Bollinger Lower >', suf: '$' },
  'min_bb_position_15m': { label: 'Position in Bollinger Bands (15m) >', suf: '%' },
  'min_bb_position_1m': { label: 'Position in Bollinger Bands (1m) >', suf: '%' },
  'min_bb_position_5m': { label: 'Position in Bollinger Bands (5m) >', suf: '%' },
  'min_bb_position_60m': { label: 'Position in Bollinger Bands (60m) >', suf: '%' },
  'min_bb_std_dev': { label: 'Standard Deviation (Bollinger) >', suf: '$' },
  'min_bb_upper': { label: 'Bollinger Upper >', suf: '$' },
  'min_below_high': { label: 'Below High >', suf: '$' },
  'min_below_premarket_high': { label: 'Below Pre-Market High >', suf: '$' },
  'min_bid_ask_ratio': { label: 'Bid / Ask Ratio >', suf: '' },
  'min_bid_size': { label: 'Bid Size >', suf: '' },
  'min_change_10d': { label: 'Change in 10 Days >', suf: '%' },
  'min_change_10d_dollars': { label: 'Change in 10 Days $ >', suf: '$' },
  'min_change_1d': { label: 'Change Previous Day >', suf: '%' },
  'min_change_1y': { label: 'Change in 1 Year % >', suf: '%' },
  'min_change_1y_dollars': { label: 'Change in 1 Year $ >', suf: '$' },
  'min_change_20d': { label: 'Change in 20 Days >', suf: '%' },
  'min_change_20d_dollars': { label: 'Change in 20 Days $ >', suf: '$' },
  'min_change_3d': { label: 'Change in 3 Days >', suf: '%' },
  'min_change_5d': { label: 'Change in 5 Days >', suf: '%' },
  'min_change_5d_dollars': { label: 'Change in 5 Days $ >', suf: '$' },
  'min_change_from_close_dollars': { label: 'Change from the Close $ >', suf: '$' },
  'min_change_from_close_ratio': { label: 'Change from the Close (ATR) >', suf: 'x' },
  'min_change_from_open': { label: 'Change from the Open % >', suf: '%' },
  'min_change_from_open_dollars': { label: 'Change from the Open $ >', suf: '$' },
  'min_change_from_open_ratio': { label: 'Change from the Open (ATR) >', suf: 'x' },
  'min_change_from_open_weighted': { label: 'Change from the Open Weighted >', suf: '' },
  'min_change_percent': { label: 'Change from the Close % >', suf: '%' },
  'min_change_prev_day_pct': { label: 'Change Previous Day % >', suf: '%' },
  'min_change_ytd': { label: 'Change Since January 1 % >', suf: '%' },
  'min_change_ytd_dollars': { label: 'Change Since January 1 $ >', suf: '$' },
  'min_chg_10min': { label: 'Change 10 Minute >', suf: '%' },
  'min_chg_10min_dollars': { label: 'Change 10 Minute >', suf: '$' },
  'min_chg_120min': { label: 'Change 120 Minute >', suf: '%' },
  'min_chg_120min_dollars': { label: 'Change 120 Minute >', suf: '$' },
  'min_chg_15min': { label: 'Change 15 Minute >', suf: '%' },
  'min_chg_15min_dollars': { label: 'Change 15 Minute >', suf: '$' },
  'min_chg_1min': { label: 'Change 1 Minute >', suf: '%' },
  'min_chg_1min_dollars': { label: 'Change 1 Minute >', suf: '$' },
  'min_chg_2min': { label: 'Change 2 Minute >', suf: '%' },
  'min_chg_2min_dollars': { label: 'Change 2 Minute >', suf: '$' },
  'min_chg_30min': { label: 'Change 30 Minute >', suf: '%' },
  'min_chg_30min_dollars': { label: 'Change 30 Minute >', suf: '$' },
  'min_chg_5min': { label: 'Change 5 Minute >', suf: '%' },
  'min_chg_5min_dollars': { label: 'Change 5 Minute >', suf: '$' },
  'min_chg_60min': { label: 'Change 60 Minute >', suf: '%' },
  'min_chg_60min_dollars': { label: 'Change 60 Minute >', suf: '$' },
  'min_consecutive_candles': { label: 'Consecutive Candles (1m) >', suf: '' },
  'min_consecutive_candles_10m': { label: 'Consecutive Candles (10m) >', suf: '' },
  'min_consecutive_candles_15m': { label: 'Consecutive Candles (15m) >', suf: '' },
  'min_consecutive_candles_2m': { label: 'Consecutive Candles (2m) >', suf: '' },
  'min_consecutive_candles_30m': { label: 'Consecutive Candles (30m) >', suf: '' },
  'min_consecutive_candles_5m': { label: 'Consecutive Candles (5m) >', suf: '' },
  'min_consecutive_candles_60m': { label: 'Consecutive Candles (60m) >', suf: '' },
  'min_consecutive_days_up': { label: 'Consecutive Days Up/Down >', suf: '' },
  'min_consolidation_days': { label: 'Consolidation Days >', suf: '' },
  'min_daily_adx_14': { label: 'Average Directional Index (Daily) >', suf: '' },
  'min_daily_atr_percent': { label: 'Daily ATR % >', suf: '%' },
  'min_daily_bb_position': { label: 'Position in Bollinger Bands (Daily) >', suf: '%' },
  'min_daily_rsi': { label: 'Daily RSI >', suf: '' },
  'min_daily_sma_10': { label: '10 Day SMA >', suf: '$' },
  'min_daily_sma_20': { label: '20 Day SMA >', suf: '$' },
  'min_daily_sma_200': { label: '200 Day SMA >', suf: '$' },
  'min_daily_sma_5': { label: '5 Day SMA >', suf: '$' },
  'min_daily_sma_50': { label: '50 Day SMA >', suf: '$' },
  'min_daily_sma_8': { label: '8 Day SMA >', suf: '$' },
  'min_decimal': { label: 'Decimal >', suf: '' },
  'min_dist_daily_sma_10': { label: 'Change from 10 Day SMA % >', suf: '%' },
  'min_dist_daily_sma_10_dollars': { label: 'Change from 10 Day SMA $ >', suf: '$' },
  'min_dist_daily_sma_20': { label: 'Change from 20 Day SMA % >', suf: '%' },
  'min_dist_daily_sma_20_dollars': { label: 'Change from 20 Day SMA $ >', suf: '$' },
  'min_dist_daily_sma_200': { label: 'Change from 200 Day SMA % >', suf: '%' },
  'min_dist_daily_sma_200_dollars': { label: 'Change from 200 Day SMA $ >', suf: '$' },
  'min_dist_daily_sma_5': { label: 'Change from 5 Day SMA % >', suf: '%' },
  'min_dist_daily_sma_5_dollars': { label: 'Change from 5 Day SMA $ >', suf: '$' },
  'min_dist_daily_sma_50': { label: 'Change from 50 Day SMA % >', suf: '%' },
  'min_dist_daily_sma_50_dollars': { label: 'Change from 50 Day SMA $ >', suf: '$' },
  'min_dist_daily_sma_8': { label: 'Change from 8 Day SMA % >', suf: '%' },
  'min_dist_daily_sma_8_dollars': { label: 'Change from 8 Day SMA $ >', suf: '$' },
  'min_dist_from_vwap': { label: 'Distance from VWAP >', suf: '%' },
  'min_dist_pivot': { label: 'Distance from Pivot >', suf: '%' },
  'min_dist_pivot_r1': { label: 'Distance from Pivot R1 >', suf: '%' },
  'min_dist_pivot_r2': { label: 'Distance from Pivot R2 >', suf: '%' },
  'min_dist_pivot_s1': { label: 'Distance from Pivot S1 >', suf: '%' },
  'min_dist_pivot_s2': { label: 'Distance from Pivot S2 >', suf: '%' },
  'min_dist_sma_10_15m': { label: 'Change from 10 Period SMA (15m) >', suf: '%' },
  'min_dist_sma_10_2m': { label: 'Change from 10 Period SMA (2m) >', suf: '%' },
  'min_dist_sma_10_5m': { label: 'Change from 10 Period SMA (5m) >', suf: '%' },
  'min_dist_sma_10_60m': { label: 'Change from 10 Period SMA (60m) >', suf: '%' },
  'min_dist_sma_130_15m': { label: 'Change from 130 Period SMA (15m) >', suf: '%' },
  'min_dist_sma_20': { label: 'Change from SMA 20 (Intraday) >', suf: '%' },
  'min_dist_sma_20_15m': { label: 'Change from 20 Period SMA (15m) >', suf: '%' },
  'min_dist_sma_20_2m': { label: 'Change from 20 Period SMA (2m) >', suf: '%' },
  'min_dist_sma_20_5m': { label: 'Change from 20 Period SMA (5m) >', suf: '%' },
  'min_dist_sma_20_60m': { label: 'Change from 20 Period SMA (60m) >', suf: '%' },
  'min_dist_sma_200': { label: 'Change from SMA 200 (Intraday) >', suf: '%' },
  'min_dist_sma_200_15m': { label: 'Change from 200 Period SMA (15m) >', suf: '%' },
  'min_dist_sma_200_2m': { label: 'Change from 200 Period SMA (2m) >', suf: '%' },
  'min_dist_sma_200_5m': { label: 'Change from 200 Period SMA (5m) >', suf: '%' },
  'min_dist_sma_200_60m': { label: 'Change from 200 Period SMA (60m) >', suf: '%' },
  'min_dist_sma_5': { label: 'Change from SMA 5 (Intraday) >', suf: '%' },
  'min_dist_sma_5_15m': { label: 'Change from 5 Period SMA (15m) >', suf: '%' },
  'min_dist_sma_5_2m': { label: 'Change from 5 Period SMA (2m) >', suf: '%' },
  'min_dist_sma_5_5m': { label: 'Change from 5 Period SMA (5m) >', suf: '%' },
  'min_dist_sma_5_60m': { label: 'Change from 5 Period SMA (60m) >', suf: '%' },
  'min_dist_sma_50': { label: 'Change from SMA 50 (Intraday) >', suf: '%' },
  'min_dist_sma_8': { label: 'Change from SMA 8 (Intraday) >', suf: '%' },
  'min_dist_sma_8_15m': { label: 'Change from 8 Period SMA (15m) >', suf: '%' },
  'min_dist_sma_8_2m': { label: 'Change from 8 Period SMA (2m) >', suf: '%' },
  'min_dist_sma_8_5m': { label: 'Change from 8 Period SMA (5m) >', suf: '%' },
  'min_dist_sma_8_60m': { label: 'Change from 8 Period SMA (60m) >', suf: '%' },
  'min_distance_from_nbbo': { label: 'Distance from Inside Market >', suf: '%' },
  'min_dollar_volume': { label: 'Dollar Volume >', suf: '$' },
  'min_ema_20': { label: 'EMA 20 >', suf: '$' },
  'min_ema_50': { label: 'EMA 50 >', suf: '$' },
  'min_float_shares': { label: 'Float >', suf: '' },
  'min_float_turnover': { label: 'Float Turnover >', suf: 'x' },
  'min_from_52w_high': { label: 'From 52 Week High % >', suf: '%' },
  'min_from_52w_low': { label: 'From 52 Week Low % >', suf: '%' },
  'min_gap_dollars': { label: 'Gap $ >', suf: '$' },
  'min_gap_percent': { label: 'Gap % >', suf: '%' },
  'min_gap_ratio': { label: 'Gap (ATR) >', suf: 'x' },
  'min_high_52w': { label: '52 Week High >', suf: '$' },
  'min_low_52w': { label: '52 Week Low >', suf: '$' },
  'min_lr_divergence_130': { label: 'Linear Regression Divergence >', suf: '%' },
  'min_macd_hist': { label: 'MACD Histogram >', suf: '' },
  'min_macd_line': { label: 'MACD Line >', suf: '' },
  'min_market_cap': { label: 'Market Cap >', suf: '$' },
  'min_minute_volume': { label: 'Minute Volume >', suf: '' },
  'min_minutes_since_open': { label: 'Minutes Since Open >', suf: 'min' },
  'min_plus_di_minus_di': { label: 'Directional Indicator (+DI - -DI) >', suf: '' },
  'min_pos_in_10d_range': { label: 'Position in 10 Day Range >', suf: '%' },
  'min_pos_in_20d_range': { label: 'Position in 20 Day Range >', suf: '%' },
  'min_pos_in_2y_range': { label: 'Position in 2 Year Range >', suf: '%' },
  'min_pos_in_3m_range': { label: 'Position in 3 Month Range >', suf: '%' },
  'min_pos_in_52w_range': { label: 'Position in 52 Week Range >', suf: '%' },
  'min_pos_in_5d_range': { label: 'Position in 5 Day Range >', suf: '%' },
  'min_pos_in_6m_range': { label: 'Position in 6 Month Range >', suf: '%' },
  'min_pos_in_9m_range': { label: 'Position in 9 Month Range >', suf: '%' },
  'min_pos_in_consolidation': { label: 'Position in Consolidation >', suf: '%' },
  'min_pos_in_lifetime_range': { label: 'Position in Lifetime Range >', suf: '%' },
  'min_pos_in_premarket_range': { label: 'Position in Pre-Market Range >', suf: '%' },
  'min_pos_in_range': { label: 'Position in Range (Today) >', suf: '%' },
  'min_pos_in_range_15m': { label: 'Position in 15 Minute Range >', suf: '%' },
  'min_pos_in_range_30m': { label: 'Position in 30 Minute Range >', suf: '%' },
  'min_pos_in_range_5m': { label: 'Position in 5 Minute Range >', suf: '%' },
  'min_pos_in_range_60m': { label: 'Position in 60 Minute Range >', suf: '%' },
  'min_pos_of_open': { label: 'Position of Open >', suf: '%' },
  'min_postmarket_change_dollars': { label: 'Change Post-Market $ >', suf: '$' },
  'min_postmarket_change_percent': { label: 'Change Post-Market % >', suf: '%' },
  'min_postmarket_volume': { label: 'Post-Market Volume >', suf: '' },
  'min_premarket_change_percent': { label: 'Change Pre-Market % >', suf: '%' },
  'min_prev_day_volume': { label: 'Previous Day Volume >', suf: '' },
  'min_price': { label: 'Price >', suf: '$' },
  'min_price_from_high': { label: 'From High % >', suf: '%' },
  'min_price_from_intraday_high': { label: 'From Intraday High % >', suf: '%' },
  'min_price_from_intraday_low': { label: 'From Intraday Low % >', suf: '%' },
  'min_price_from_low': { label: 'From Low % >', suf: '%' },
  'min_range_10d': { label: '10 Day Range $ >', suf: '$' },
  'min_range_10d_pct': { label: '10 Day Range % >', suf: '%' },
  'min_range_120min': { label: '120 Minute Range $ >', suf: '$' },
  'min_range_120min_pct': { label: '120 Minute Range % >', suf: '%' },
  'min_range_15min': { label: '15 Minute Range $ >', suf: '$' },
  'min_range_15min_pct': { label: '15 Minute Range % >', suf: '%' },
  'min_range_20d': { label: '20 Day Range $ >', suf: '$' },
  'min_range_20d_pct': { label: '20 Day Range % >', suf: '%' },
  'min_range_2min': { label: '2 Minute Range $ >', suf: '$' },
  'min_range_2min_pct': { label: '2 Minute Range % >', suf: '%' },
  'min_range_30min': { label: '30 Minute Range $ >', suf: '$' },
  'min_range_30min_pct': { label: '30 Minute Range % >', suf: '%' },
  'min_range_5d': { label: '5 Day Range $ >', suf: '$' },
  'min_range_5d_pct': { label: '5 Day Range % >', suf: '%' },
  'min_range_5min': { label: '5 Minute Range $ >', suf: '$' },
  'min_range_5min_pct': { label: '5 Minute Range % >', suf: '%' },
  'min_range_60min': { label: '60 Minute Range $ >', suf: '$' },
  'min_range_60min_pct': { label: '60 Minute Range % >', suf: '%' },
  'min_range_contraction': { label: 'Range Contraction >', suf: '' },
  'min_rsi': { label: 'RSI (1m) >', suf: '' },
  'min_rsi_15m': { label: '15 Minute RSI >', suf: '' },
  'min_rsi_2m': { label: '2 Minute RSI >', suf: '' },
  'min_rsi_5m': { label: '5 Minute RSI >', suf: '' },
  'min_rsi_60m': { label: '60 Minute RSI >', suf: '' },
  'min_rvol': { label: 'Relative Volume >', suf: 'x' },
  'min_shares_outstanding': { label: 'Shares Outstanding >', suf: '' },
  'min_sma_20': { label: 'SMA 20 >', suf: '$' },
  'min_sma_20_vs_200_15m': { label: '20 vs. 200 Period SMA (15m) >', suf: '%' },
  'min_sma_20_vs_200_2m': { label: '20 vs. 200 Period SMA (2m) >', suf: '%' },
  'min_sma_20_vs_200_5m': { label: '20 vs. 200 Period SMA (5m) >', suf: '%' },
  'min_sma_20_vs_200_60m': { label: '20 vs. 200 Period SMA (60m) >', suf: '%' },
  'min_sma_200': { label: 'SMA 200 >', suf: '$' },
  'min_sma_5': { label: 'SMA 5 >', suf: '$' },
  'min_sma_50': { label: 'SMA 50 >', suf: '$' },
  'min_sma_8': { label: 'SMA 8 >', suf: '$' },
  'min_sma_8_vs_20_15m': { label: '8 vs. 20 Period SMA (15m) >', suf: '%' },
  'min_sma_8_vs_20_2m': { label: '8 vs. 20 Period SMA (2m) >', suf: '%' },
  'min_sma_8_vs_20_5m': { label: '8 vs. 20 Period SMA (5m) >', suf: '%' },
  'min_sma_8_vs_20_60m': { label: '8 vs. 20 Period SMA (60m) >', suf: '%' },
  'min_spread': { label: 'Spread >', suf: '$' },
  'min_stoch_d': { label: 'Stochastic %D >', suf: '' },
  'min_stoch_k': { label: 'Stochastic %K >', suf: '' },
  'min_trades_today': { label: 'Average Number of Prints >', suf: '' },
  'min_trades_z_score': { label: 'Trades Z-Score >', suf: '' },
  'min_vol_10min': { label: 'Volume 10 Minute >', suf: '' },
  'min_vol_10min_pct': { label: 'Average Volume 10m % >', suf: '%' },
  'min_vol_15min': { label: 'Volume 15 Minute >', suf: '' },
  'min_vol_15min_pct': { label: 'Average Volume 15m % >', suf: '%' },
  'min_vol_1min': { label: 'Volume 1 Minute >', suf: '' },
  'min_vol_1min_pct': { label: 'Average Volume 1m % >', suf: '%' },
  'min_vol_30min': { label: 'Volume 30 Minute >', suf: '' },
  'min_vol_30min_pct': { label: 'Average Volume 30m % >', suf: '%' },
  'min_vol_5min': { label: 'Volume 5 Minute >', suf: '' },
  'min_vol_5min_pct': { label: 'Average Volume 5m % >', suf: '%' },
  'min_volume': { label: 'Volume Today >', suf: '' },
  'min_volume_today_pct': { label: 'Volume Today % >', suf: '%' },
  'min_volume_yesterday_pct': { label: 'Volume Yesterday % >', suf: '%' },
  'min_vwap': { label: 'VWAP >', suf: '$' },
  'min_yearly_std_dev': { label: 'Yearly Standard Deviation >', suf: '$' },
  'sector': { label: 'Sector', suf: '' },
  'security_type': { label: 'Type', suf: '' },
};

// ============================================================================
// Helpers
// ============================================================================

function fmtFilter(key: string, val: number): string {
  const meta = FILTER_META[key];
  if (!meta) return String(val);
  const fmtLarge = (v: number, prefix = '') => {
    const a = Math.abs(v);
    if (a >= 1e9) return `${prefix}${parseFloat((v / 1e9).toPrecision(3))}B`;
    if (a >= 1e6) return `${prefix}${parseFloat((v / 1e6).toPrecision(3))}M`;
    if (a >= 1e3) return `${prefix}${parseFloat((v / 1e3).toPrecision(3))}K`;
    return `${prefix}${v}`;
  };
  switch (meta.suf) {
    case '%': return `${val}%`;
    case '$': return (Math.abs(val) >= 1e3) ? fmtLarge(val, '$') : `$${val}`;
    case 'x': return `${val}x`;
    default:  return (Math.abs(val) >= 1e3) ? fmtLarge(val) : String(val);
  }
}

function filtersToDisplay(filters: Record<string, any>): string[] {
  return Object.entries(filters)
    .filter(([, v]) => v != null && (typeof v === 'number' || typeof v === 'string'))
    .map(([k, v]) => {
      const meta = FILTER_META[k];
      const label = meta ? meta.label : k;
      if (typeof v === 'string') return `${label}: ${v}`;
      return `${label} ${fmtFilter(k, v as number)}`;
    });
}

function alertTypeLabel(eventType: string): string {
  const a = ALERT_CATALOG.find(x => x.eventType === eventType);
  return a ? a.name : eventType;
}

// ============================================================================
// Unit system & formatted numeric input
// ============================================================================

const UNIT_MUL: Record<string, number> = { '': 1, K: 1e3, M: 1e6, B: 1e9 };

const fmtLocale = (n: number) => n.toLocaleString('en-US', { maximumFractionDigits: 6 });

/** Numeric input with thousand-separator formatting on blur, raw editing on focus */
function FmtNum({ value, onChange, placeholder, className }: {
  value: number | undefined;
  onChange: (v: number | undefined) => void;
  placeholder?: string;
  className?: string;
}) {
  const [editing, setEditing] = useState(false);
  const [editStr, setEditStr] = useState('');
  const display = value !== undefined ? fmtLocale(value) : '';
  return (
    <input type="text" inputMode="decimal"
      value={editing ? editStr : display}
      onFocus={() => { setEditing(true); setEditStr(value !== undefined ? String(value) : ''); }}
      onBlur={() => {
        setEditing(false);
        const s = editStr.replace(/,/g, '').trim();
        onChange(s && !isNaN(Number(s)) ? Number(s) : undefined);
      }}
      onChange={e => setEditStr(e.target.value)}
      placeholder={placeholder} className={className} />
  );
}

// ============================================================================
// Component
// ============================================================================

export function ConfigWindow({
  onCreateAlertWindow,
  onCreateScannerWindow,
  onBacktestStrategy,
  initialAlerts, initialFilters, initialSymbolsInclude, initialSymbolsExclude,
  initialName, initialTab, initialMode,
  sourceCategoryId,
}: ConfigWindowProps) {
  const [builderMode, setBuilderMode] = useState<BuilderMode>(initialMode || 'strategy');
  const [activeTab, setActiveTab] = useState<ConfigTab>(initialTab || 'saved');

  // Strategy state
  const {
    strategies, loading, createStrategy, updateStrategy, deleteStrategy,
    useStrategy, toggleFavorite, getRecent, getFavorites, getByCategory,
  } = useAlertStrategies();

  // Top List state (scanner filters)
  const {
    filters: scannerFilters, loading: loadingScans,
    createFilter: createScanFilter, updateFilter: updateScanFilter,
    deleteFilter: deleteScanFilter, refreshFilters: refreshScanFilters,
  } = useUserFilters();

  // Resolve initial state: prefer live store data over static props
  const liveFilters = useEventFiltersStore(
    useCallback((s: { filtersMap: Record<string, ActiveEventFilters> }) =>
      sourceCategoryId ? s.filtersMap[sourceCategoryId] : undefined,
    [sourceCategoryId])
  );
  const resolvedInitialFilters = liveFilters || initialFilters;

  // Extract numeric/string filters for the local editing state
  const extractEditableFilters = useCallback((src: Record<string, any> | undefined) => {
    if (!src) return {};
    return Object.fromEntries(
      Object.entries(src).filter(([, v]) => typeof v === 'number' || typeof v === 'string')
    );
  }, []);

  // Current config being built
  const [strategyName, setStrategyName] = useState(initialName || '');
  const [selectedAlerts, setSelectedAlerts] = useState<Set<string>>(new Set(initialAlerts || []));
  const [filters, setFilters] = useState<Record<string, number | string | undefined>>(
    extractEditableFilters(resolvedInitialFilters)
  );
  const [filterUnits, setFilterUnits] = useState<Record<string, string>>({});
  const [symbolsInclude, setSymbolsInclude] = useState(initialSymbolsInclude || '');
  const [symbolsExclude, setSymbolsExclude] = useState(initialSymbolsExclude || '');
  const [saving, setSaving] = useState(false);
  const [saveCategory, setSaveCategory] = useState('custom');
  const [loadedStrategyId, setLoadedStrategyId] = useState<string | null>(null);
  // Snapshot of loaded strategy to detect modifications
  const [loadedSnapshot, setLoadedSnapshot] = useState<{ alerts: string[]; filters: Record<string, any>; name: string } | null>(null);

  // Unit helpers: raw value <-> display value
  const getUnit = useCallback((id: string, def?: string) => filterUnits[id] || def || '', [filterUnits]);
  const getMul = useCallback((id: string, def?: string) => UNIT_MUL[filterUnits[id] || def || ''] || 1, [filterUnits]);
  const setUnitFor = useCallback((id: string, u: string) => setFilterUnits(p => ({ ...p, [id]: u })), []);
  const rawToDisplay = useCallback((raw: number | undefined, id: string, def?: string): string => {
    if (raw === undefined) return '';
    return parseFloat((raw / (UNIT_MUL[filterUnits[id] || def || ''] || 1)).toPrecision(10)).toString();
  }, [filterUnits]);
  const displayToRaw = useCallback((val: string, id: string, def?: string): number | undefined => {
    if (!val) return undefined;
    return Number(val) * (UNIT_MUL[filterUnits[id] || def || ''] || 1);
  }, [filterUnits]);

  // Loaded scan (top list) state
  const [loadedScanId, setLoadedScanId] = useState<number | null>(null);
  const [loadedScanSnapshot, setLoadedScanSnapshot] = useState<{ filters: Record<string, any>; name: string } | null>(null);

  // Strategies tab state
  const [expandedFolders, setExpandedFolders] = useState<Set<string>>(new Set(['builtin', 'custom']));
  const [selectedStrategy, setSelectedStrategy] = useState<AlertStrategy | AlertPreset | null>(null);
  const [alertSearch, setAlertSearch] = useState('');

  const toggleFolder = (id: string) => setExpandedFolders(prev => {
    const n = new Set(prev); if (n.has(id)) n.delete(id); else n.add(id); return n;
  });

  // Load strategy into editor
  const loadStrategy = useCallback((eventTypes: string[], stratFilters: Record<string, any>, name?: string) => {
    setSelectedAlerts(new Set(eventTypes));
    const allFilters: Record<string, number | string | undefined> = {};
    for (const [k, v] of Object.entries(stratFilters)) {
      if (typeof v === 'number' || typeof v === 'string') allFilters[k] = v;
    }
    setFilters(allFilters);
    if (name) setStrategyName(name);
    setActiveTab('summary');
  }, []);

  const handleLoadUserStrategy = useCallback(async (s: AlertStrategy) => {
    loadStrategy(s.eventTypes, s.filters, s.name);
    setLoadedStrategyId(String(s.id));
    setLoadedSnapshot({ alerts: [...s.eventTypes], filters: { ...s.filters }, name: s.name });
    await useStrategy(s.id);
  }, [loadStrategy, useStrategy]);

  const handleLoadBuiltIn = useCallback((p: AlertPreset) => {
    loadStrategy(p.eventTypes, p.filters, p.name);
    setLoadedStrategyId(null);
    setLoadedSnapshot(null);
  }, [loadStrategy]);

  const handleStartFromScratch = useCallback(() => {
    setSelectedAlerts(new Set());
    setFilters({});
    setSymbolsInclude('');
    setSymbolsExclude('');
    setStrategyName('');
    setLoadedStrategyId(null);
    setLoadedSnapshot(null);
    setLoadedScanId(null);
    setLoadedScanSnapshot(null);
    setActiveTab(builderMode === 'strategy' ? 'alerts' : 'filters');
  }, [builderMode]);

  // Alert handlers
  const toggleAlert = useCallback((id: string) => {
    setSelectedAlerts(prev => { const n = new Set(prev); if (n.has(id)) n.delete(id); else n.add(id); return n; });
  }, []);

  const toggleAlertCat = useCallback((catAlerts: string[]) => {
    setSelectedAlerts(prev => {
      const n = new Set(prev);
      const all = catAlerts.every(a => n.has(a));
      catAlerts.forEach(a => { if (all) n.delete(a); else n.add(a); });
      return n;
    });
  }, []);

  // Filter handlers
  const setFilter = useCallback((key: string, val: number | string | undefined) => {
    setFilters(prev => {
      const n = { ...prev };
      if (val === undefined || val === null) delete n[key]; else n[key] = val;
      return n;
    });
  }, []);

  // Validation - different rules per mode
  const canCreate = useMemo(() => {
    if (!strategyName.trim()) return false;
    if (builderMode === 'strategy') return selectedAlerts.size > 0;
    // Top List: requires at least 1 filter
    return Object.values(filters).some(v => v !== undefined);
  }, [strategyName, selectedAlerts, filters, builderMode]);

  // Detect if config was modified from loaded snapshot
  const isDirty = useMemo(() => {
    if (!loadedSnapshot) return false;
    const curAlerts = Array.from(selectedAlerts).sort();
    const snapAlerts = [...loadedSnapshot.alerts].sort();
    if (curAlerts.length !== snapAlerts.length || curAlerts.some((a, i) => a !== snapAlerts[i])) return true;
    if (strategyName !== loadedSnapshot.name) return true;
    const curFilterKeys = Object.keys(filters).filter(k => filters[k] !== undefined).sort();
    const snapFilterKeys = Object.keys(loadedSnapshot.filters).filter(k => loadedSnapshot.filters[k] != null && typeof loadedSnapshot.filters[k] === 'number').sort();
    if (curFilterKeys.length !== snapFilterKeys.length || curFilterKeys.some((k, i) => k !== snapFilterKeys[i])) return true;
    if (curFilterKeys.some(k => filters[k] !== loadedSnapshot.filters[k])) return true;
    return false;
  }, [selectedAlerts, filters, strategyName, loadedSnapshot]);

  const buildAlertWindowConfig = useCallback((): AlertWindowConfig => {
    const inc = symbolsInclude.trim() ? symbolsInclude.split(/[,\s]+/).map(s => s.trim().toUpperCase()).filter(Boolean) : [];
    const exc = symbolsExclude.trim() ? symbolsExclude.split(/[,\s]+/).map(s => s.trim().toUpperCase()).filter(Boolean) : [];
    const ef: ActiveEventFilters = {
      event_types: Array.from(selectedAlerts),
      symbols_include: inc.length ? inc : undefined,
      symbols_exclude: exc.length ? exc : undefined,
      ...filters,
    };
    return {
      name: strategyName.trim() || `Custom ${new Date().toLocaleTimeString()}`,
      eventTypes: Array.from(selectedAlerts),
      filters: ef,
      symbolsInclude: inc,
      symbolsExclude: exc,
      strategyId: loadedStrategyId ? Number(loadedStrategyId) : undefined,
    };
  }, [selectedAlerts, filters, symbolsInclude, symbolsExclude, strategyName]);

  // Create / Open
  const handleCreate = useCallback(async () => {
    if (!canCreate || saving) return;
    setSaving(true);
    try {
      // Save strategy to BD
      const saved = await createStrategy({
        name: strategyName.trim(),
        category: saveCategory,
        event_types: Array.from(selectedAlerts),
        filters,
      });

      // CRITICAL: Don't open window if save failed (JWT expired, 409 conflict, etc.)
      if (!saved) {
        return;
      }

      // Transition to "loaded" state so subsequent edits use Update (not Create again → 409)
      setLoadedStrategyId(String(saved.id));
      setLoadedSnapshot({
        alerts: Array.from(selectedAlerts),
        filters: { ...filters },
        name: strategyName.trim(),
      });

      if (onCreateAlertWindow) {
        onCreateAlertWindow(buildAlertWindowConfig());
      }
    } finally { setSaving(false); }
  }, [canCreate, saving, strategyName, saveCategory, selectedAlerts, filters, createStrategy, onCreateAlertWindow, buildAlertWindowConfig]);

  // Update existing strategy & open
  const handleUpdate = useCallback(async () => {
    if (!loadedStrategyId || saving) return;
    setSaving(true);
    try {
      await updateStrategy(Number(loadedStrategyId), {
        name: strategyName.trim(),
        event_types: Array.from(selectedAlerts),
        filters,
      });
      setLoadedSnapshot({ alerts: Array.from(selectedAlerts), filters: { ...filters }, name: strategyName.trim() });

      if (onCreateAlertWindow) {
        onCreateAlertWindow(buildAlertWindowConfig());
      }
    } finally { setSaving(false); }
  }, [loadedStrategyId, saving, strategyName, selectedAlerts, filters, updateStrategy, onCreateAlertWindow, buildAlertWindowConfig]);

  const handleOpenDirect = useCallback(() => {
    if (selectedAlerts.size === 0) return;
    if (onCreateAlertWindow) {
      onCreateAlertWindow(buildAlertWindowConfig());
    }
  }, [selectedAlerts, onCreateAlertWindow, buildAlertWindowConfig]);

  // Detect if top list was modified from loaded snapshot
  const isScanDirty = useMemo(() => {
    if (!loadedScanSnapshot) return false;
    if (strategyName !== loadedScanSnapshot.name) return true;
    const curKeys = Object.keys(filters).filter(k => filters[k] !== undefined).sort();
    const snapKeys = Object.keys(loadedScanSnapshot.filters).filter(k => loadedScanSnapshot.filters[k] != null).sort();
    if (curKeys.length !== snapKeys.length || curKeys.some((k, i) => k !== snapKeys[i])) return true;
    if (curKeys.some(k => filters[k] !== loadedScanSnapshot.filters[k])) return true;
    return false;
  }, [filters, strategyName, loadedScanSnapshot]);

  // ── Top List handlers ──

  const handleLoadScan = useCallback((scan: UserFilter) => {
    const numFilters: Record<string, number | string | undefined> = {};
    for (const [k, v] of Object.entries(scan.parameters || {})) {
      if (typeof v === 'number') numFilters[k] = v;
      if (typeof v === 'string') numFilters[k] = v;
    }
    setFilters(numFilters);
    setSelectedAlerts(new Set()); // Top lists have no alerts
    setStrategyName(scan.name);
    setLoadedScanId(scan.id);
    setLoadedScanSnapshot({ filters: { ...numFilters }, name: scan.name });
    setLoadedStrategyId(null);
    setLoadedSnapshot(null);
    setActiveTab('summary');
  }, []);

  const handleLoadBuiltInTopList = useCallback((preset: TopListPreset) => {
    const numFilters: Record<string, number | string | undefined> = {};
    for (const [k, v] of Object.entries(preset.filters)) {
      numFilters[k] = v;
    }
    setFilters(numFilters);
    setSelectedAlerts(new Set());
    setStrategyName(preset.name);
    setLoadedScanId(null);
    setLoadedScanSnapshot(null);
    setLoadedStrategyId(null);
    setLoadedSnapshot(null);
    setActiveTab('summary');
  }, []);

  const handleCreateTopList = useCallback(async () => {
    if (!canCreate || saving) return;
    setSaving(true);
    try {
      // Build parameters from filters
      const params: Record<string, any> = {};
      for (const [k, v] of Object.entries(filters)) {
        if (v !== undefined) params[k] = v;
      }
      const saved = await createScanFilter({
        name: strategyName.trim(),
        description: `${Object.keys(params).length} filters`,
        enabled: true,
        filter_type: 'custom',
        parameters: params,
        priority: 0,
      });
      if (!saved) return;
      setLoadedScanId(saved.id);
      setLoadedScanSnapshot({ filters: { ...filters }, name: strategyName.trim() });
      if (onCreateScannerWindow) {
        onCreateScannerWindow(saved);
      }
    } finally { setSaving(false); }
  }, [canCreate, saving, strategyName, filters, createScanFilter, onCreateScannerWindow]);

  // Open scanner for an already-saved scan (no save needed)
  const handleOpenScanDirect = useCallback(() => {
    if (!loadedScanId) return;
    // Build a minimal UserFilter-like object to pass to the callback
    const params: Record<string, any> = {};
    for (const [k, v] of Object.entries(filters)) {
      if (v !== undefined) params[k] = v;
    }
    if (onCreateScannerWindow) {
      onCreateScannerWindow({
        id: loadedScanId,
        userId: '',
        name: strategyName.trim(),
        enabled: true,
        filter_type: 'custom',
        parameters: params,
        priority: 0,
        isShared: false,
        isPublic: false,
        createdAt: '',
        updatedAt: '',
      });
    }
  }, [loadedScanId, strategyName, filters, onCreateScannerWindow]);

  const handleUpdateTopList = useCallback(async () => {
    if (!loadedScanId || saving) return;
    setSaving(true);
    try {
      const params: Record<string, any> = {};
      for (const [k, v] of Object.entries(filters)) {
        if (v !== undefined) params[k] = v;
      }
      const updated = await updateScanFilter(loadedScanId, {
        name: strategyName.trim(),
        parameters: params,
      });
      if (!updated) return;
      setLoadedScanSnapshot({ filters: { ...filters }, name: strategyName.trim() });
      if (onCreateScannerWindow) {
        onCreateScannerWindow(updated);
      }
    } finally { setSaving(false); }
  }, [loadedScanId, saving, strategyName, filters, updateScanFilter, onCreateScannerWindow]);

  // Folder data
  const folderData: Record<string, AlertStrategy[]> = {
    recent: getRecent(8),
    favorites: getFavorites(),
    bullish: getByCategory('bullish'),
    bearish: getByCategory('bearish'),
    neutral: getByCategory('neutral'),
    custom: getByCategory('custom'),
  };

  // Alert categories expand state (collapsed by default)
  const [expandedAlertCats, setExpandedAlertCats] = useState<Set<string>>(new Set());
  const toggleAlertCatExpand = (id: string) => setExpandedAlertCats(prev => {
    const n = new Set(prev); if (n.has(id)) n.delete(id); else n.add(id); return n;
  });

  // Filter groups expand state + search
  const [expandedFilterGroups, setExpandedFilterGroups] = useState<Set<string>>(new Set());
  const toggleFilterGroup = (id: string) => setExpandedFilterGroups(prev => {
    const n = new Set(prev); if (n.has(id)) n.delete(id); else n.add(id); return n;
  });
  const [filterSearch, setFilterSearch] = useState('');

  // Search alerts
  const alertGroups = useMemo(() => {
    if (!alertSearch.trim()) return getAlertsByCategory();
    const results = searchAlerts(alertSearch, 'en');
    const resultSet = new Set(results.map(a => a.eventType));
    return getAlertsByCategory()
      .map(g => ({ ...g, alerts: g.alerts.filter(a => resultSet.has(a.eventType)) }))
      .filter(g => g.alerts.length > 0);
  }, [alertSearch]);

  // Top List folder data
  const topListFolderData: Record<string, UserFilter[]> = useMemo(() => ({
    all: scannerFilters,
    active: scannerFilters.filter(s => s.enabled),
    inactive: scannerFilters.filter(s => !s.enabled),
  }), [scannerFilters]);

  const tabs: { id: ConfigTab; label: string }[] = useMemo(() => {
    if (builderMode === 'toplist') {
      return [
        { id: 'saved', label: 'Top Lists' },
        { id: 'filters', label: 'Filters' },
        { id: 'symbols', label: 'Symbols' },
        { id: 'summary', label: 'Summary' },
      ];
    }
    return [
      { id: 'saved', label: 'Strategies' },
      { id: 'alerts', label: `Alerts (${selectedAlerts.size})` },
      { id: 'filters', label: 'Filters' },
      { id: 'symbols', label: 'Symbols' },
      { id: 'summary', label: 'Summary' },
    ];
  }, [builderMode, selectedAlerts.size]);

  const activeFilterCount = Object.values(filters).filter(v => v !== undefined).length;

  // When switching modes, clear selection and redirect incompatible tabs
  const handleModeSwitch = useCallback((mode: BuilderMode) => {
    setBuilderMode(mode);
    setSelectedStrategy(null);
    if (mode === 'toplist' && activeTab === 'alerts') {
      setActiveTab('filters');
    }
  }, [activeTab]);

  return (
    <div className="h-full flex flex-col bg-surface text-foreground text-xs">
      {/* Mode toggle + Tabs */}
      <div className="flex-shrink-0 border-b border-border bg-surface-hover">
        {/* Mode selector */}
        <div className="flex items-center gap-1 px-3 pt-1.5 pb-1">
          <div className="flex bg-muted rounded-md p-0.5 gap-0.5">
            <button
              onClick={() => handleModeSwitch('strategy')}
              className={`px-2.5 py-[3px] text-[10px] font-semibold rounded transition-all ${builderMode === 'strategy'
                  ? 'bg-surface text-primary shadow-sm'
                  : 'text-muted-fg hover:text-foreground'
                }`}
            >Strategy</button>
            <button
              onClick={() => handleModeSwitch('toplist')}
              className={`px-2.5 py-[3px] text-[10px] font-semibold rounded transition-all ${builderMode === 'toplist'
                  ? 'bg-surface text-emerald-600 shadow-sm'
                  : 'text-muted-fg hover:text-foreground'
                }`}
            >Top List</button>
          </div>
          <span className="text-[9px] text-muted-fg ml-1.5">
            {builderMode === 'strategy' ? 'Events + Filters' : 'Filters only → Scanner'}
          </span>
        </div>
        {/* Tabs */}
        <div className="flex">
          {tabs.map(tab => (
            <button key={tab.id} onClick={() => setActiveTab(tab.id)}
              className={`px-3 py-1.5 text-xs border-b-2 transition-colors ${activeTab === tab.id
                ? (builderMode === 'toplist' ? 'border-emerald-600 text-emerald-600 bg-emerald-500/10' : 'border-primary text-primary bg-primary/10')
                : 'border-transparent text-muted-fg hover:text-foreground hover:bg-surface-hover'
                }`}
            >{tab.label}</button>
          ))}
        </div>
      </div>

      <div className="flex-1 overflow-hidden">

        {/* ====== SAVED TAB (Strategies or Top Lists) ====== */}
        {activeTab === 'saved' && builderMode === 'strategy' && (
          <div className="h-full flex">
            {/* Left: folder tree */}
            <div className="w-52 border-r border-border flex flex-col overflow-hidden">
              <button onClick={handleStartFromScratch}
                className="w-full text-left px-3 py-1.5 text-xs font-semibold text-primary hover:bg-primary/10 border-b border-border-subtle transition-colors flex-shrink-0">
                Start from Scratch
              </button>
              <div className="flex-1 overflow-y-auto">
                {STRATEGY_FOLDERS.filter(f => f.id !== 'builtin').map(folder => {
                  const items = folderData[folder.id] || [];
                  const exp = expandedFolders.has(folder.id);
                  return (
                    <div key={folder.id} className="border-b border-border-subtle">
                      <button onClick={() => toggleFolder(folder.id)}
                        className="w-full flex items-center gap-1.5 px-3 py-1 text-left hover:bg-surface-hover transition-colors">
                        <span className="text-[10px] text-muted-fg">{exp ? '\u25BC' : '\u25B6'}</span>
                        <span className="text-xs font-semibold text-foreground/80 flex-1">{folder.label}</span>
                        {items.length > 0 && <span className="text-[10px] text-muted-fg">{items.length}</span>}
                      </button>
                      {exp && items.length === 0 && (
                        <div className="px-5 py-1 text-[10px] text-muted-fg/50">Empty</div>
                      )}
                      {exp && items.map(s => (
                        <button key={s.id}
                          onClick={() => setSelectedStrategy(s)}
                          onDoubleClick={() => handleLoadUserStrategy(s)}
                          className={`w-full text-left px-5 py-1 text-[11px] transition-colors truncate ${selectedStrategy && 'id' in selectedStrategy && selectedStrategy.id === s.id
                            ? 'bg-primary/10 text-primary font-medium'
                            : 'text-foreground/80 hover:bg-surface-hover'
                            }`}
                        >{s.name}</button>
                      ))}
                    </div>
                  );
                })}
                {/* Built-in strategies folder */}
                <div className="border-b border-border-subtle">
                  <button onClick={() => toggleFolder('builtin')}
                    className="w-full flex items-center gap-1.5 px-3 py-1 text-left hover:bg-surface-hover transition-colors">
                    <span className="text-[10px] text-muted-fg">{expandedFolders.has('builtin') ? '\u25BC' : '\u25B6'}</span>
                    <span className="text-xs font-semibold text-foreground/80 flex-1">Built-in</span>
                    <span className="text-[10px] text-muted-fg">{BUILT_IN_PRESETS.length}</span>
                  </button>
                  {expandedFolders.has('builtin') && BUILT_IN_PRESETS.map(p => (
                    <button key={p.id}
                      onClick={() => setSelectedStrategy(p)}
                      onDoubleClick={() => handleLoadBuiltIn(p)}
                      className={`w-full text-left px-5 py-1 text-[11px] transition-colors truncate ${selectedStrategy && 'isBuiltIn' in selectedStrategy && selectedStrategy.id === p.id
                        ? 'bg-blue-500/10 text-blue-700 font-medium'
                        : 'text-foreground/80 hover:bg-surface-hover'
                        }`}
                    >{p.name}</button>
                  ))}
                </div>
              </div>
              {loading && <div className="px-3 py-1 text-[10px] text-muted-fg text-center flex-shrink-0">Loading...</div>}
            </div>
            {/* Right: strategy detail */}
            <div className="flex-1 flex flex-col overflow-hidden">
              {selectedStrategy ? (
                <>
                  <div className="flex-1 overflow-y-auto p-3">
                    {'isBuiltIn' in selectedStrategy ? (
                      <>
                        <div className="text-xs font-bold text-foreground mb-1">{selectedStrategy.name}</div>
                        <p className="text-[11px] text-muted-fg mb-3">{selectedStrategy.description}</p>
                        <div className="mb-2">
                          <div className="text-[10px] font-semibold text-muted-fg uppercase tracking-wide mb-1">Alerts</div>
                          <div className="flex flex-wrap gap-1">
                            {selectedStrategy.eventTypes.map(et => (
                              <span key={et} className="px-1.5 py-0.5 bg-surface-hover border border-border rounded text-[10px] text-foreground/80">{alertTypeLabel(et)}</span>
                            ))}
                          </div>
                        </div>
                        {Object.keys(selectedStrategy.filters).length > 0 && (
                          <div>
                            <div className="text-[10px] font-semibold text-muted-fg uppercase tracking-wide mb-1">Filters</div>
                            <div className="flex flex-wrap gap-1">
                              {filtersToDisplay(selectedStrategy.filters).map(f => (
                                <span key={f} className="px-1.5 py-0.5 bg-surface-hover border border-border rounded text-[10px] font-mono text-foreground/80">{f}</span>
                              ))}
                            </div>
                          </div>
                        )}
                      </>
                    ) : (
                      <>
                        <div className="flex items-center justify-between mb-1">
                          <div className="text-xs font-bold text-foreground">{(selectedStrategy as AlertStrategy).name}</div>
                          <div className="flex items-center gap-1">
                            <button onClick={() => toggleFavorite((selectedStrategy as AlertStrategy).id)}
                              className={`text-[11px] ${(selectedStrategy as AlertStrategy).isFavorite ? 'text-primary' : 'text-muted-fg/50 hover:text-muted-fg'}`}
                            >{'\u2605'}</button>
                            <button onClick={async () => { await deleteStrategy((selectedStrategy as AlertStrategy).id); setSelectedStrategy(null); }}
                              className="text-[10px] text-muted-fg/50 hover:text-rose-500">x</button>
                          </div>
                        </div>
                        {(selectedStrategy as AlertStrategy).description && (
                          <p className="text-[11px] text-muted-fg mb-2">{(selectedStrategy as AlertStrategy).description}</p>
                        )}
                        <div className="text-[10px] text-muted-fg mb-3">
                          {(selectedStrategy as AlertStrategy).useCount > 0 && `Used ${(selectedStrategy as AlertStrategy).useCount}x`}
                          {(selectedStrategy as AlertStrategy).lastUsedAt && ` \u00b7 Last: ${new Date((selectedStrategy as AlertStrategy).lastUsedAt!).toLocaleDateString()}`}
                        </div>
                        <div className="mb-2">
                          <div className="text-[10px] font-semibold text-muted-fg uppercase tracking-wide mb-1">Alerts ({(selectedStrategy as AlertStrategy).eventTypes.length})</div>
                          <div className="flex flex-wrap gap-1">
                            {(selectedStrategy as AlertStrategy).eventTypes.map(et => (
                              <span key={et} className="px-1.5 py-0.5 bg-surface-hover border border-border rounded text-[10px] text-foreground/80">{alertTypeLabel(et)}</span>
                            ))}
                          </div>
                        </div>
                        {Object.keys((selectedStrategy as AlertStrategy).filters).length > 0 && (
                          <div>
                            <div className="text-[10px] font-semibold text-muted-fg uppercase tracking-wide mb-1">Filters</div>
                            <div className="flex flex-wrap gap-1">
                              {filtersToDisplay((selectedStrategy as AlertStrategy).filters).map(f => (
                                <span key={f} className="px-1.5 py-0.5 bg-surface-hover border border-border rounded text-[10px] font-mono text-foreground/80">{f}</span>
                              ))}
                            </div>
                          </div>
                        )}
                      </>
                    )}
                  </div>
                  <div className="flex-shrink-0 p-2 border-t border-border bg-surface-hover">
                    <button
                      onClick={() => {
                        if ('isBuiltIn' in selectedStrategy) handleLoadBuiltIn(selectedStrategy as AlertPreset);
                        else handleLoadUserStrategy(selectedStrategy as AlertStrategy);
                      }}
                      className="w-full py-1.5 text-xs font-semibold bg-primary text-white rounded hover:bg-primary-hover transition-colors"
                    >Load Settings</button>
                  </div>
                </>
              ) : (
                <div className="h-full flex items-center justify-center text-muted-fg text-[11px] p-4 text-center">
                  Select a strategy to see details, or double-click to load
                </div>
              )}
            </div>
          </div>
        )}

        {/* ====== SAVED TAB — TOP LIST MODE ====== */}
        {activeTab === 'saved' && builderMode === 'toplist' && (
          <div className="h-full flex">
            {/* Left: folder tree */}
            <div className="w-52 border-r border-border flex flex-col overflow-hidden">
              <button onClick={handleStartFromScratch}
                className="w-full text-left px-3 py-1.5 text-xs font-semibold text-emerald-600 hover:bg-emerald-500/10 border-b border-border-subtle transition-colors flex-shrink-0">
                Start from Scratch
              </button>
              <div className="flex-1 overflow-y-auto">
                {TOPLIST_FOLDERS.filter(f => f.id !== 'builtin').map(folder => {
                  const items = topListFolderData[folder.id] || [];
                  const exp = expandedFolders.has(folder.id);
                  return (
                    <div key={folder.id} className="border-b border-border-subtle">
                      <button onClick={() => toggleFolder(folder.id)}
                        className="w-full flex items-center gap-1.5 px-3 py-1 text-left hover:bg-surface-hover transition-colors">
                        <span className="text-[10px] text-muted-fg">{exp ? '\u25BC' : '\u25B6'}</span>
                        <span className="text-xs font-semibold text-foreground/80 flex-1">{folder.label}</span>
                        {items.length > 0 && <span className="text-[10px] text-muted-fg">{items.length}</span>}
                      </button>
                      {exp && items.length === 0 && (
                        <div className="px-5 py-1 text-[10px] text-muted-fg/50">Empty</div>
                      )}
                      {exp && items.map(scan => (
                        <button key={scan.id}
                          onClick={() => setSelectedStrategy(scan as any)}
                          onDoubleClick={() => handleLoadScan(scan)}
                          className={`w-full text-left px-5 py-1 text-[11px] transition-colors truncate ${selectedStrategy && 'userId' in selectedStrategy && (selectedStrategy as any).id === scan.id
                            ? 'bg-emerald-500/10 text-emerald-700 font-medium'
                            : 'text-foreground/80 hover:bg-surface-hover'
                            }`}
                        >
                          <span className="flex items-center gap-1">
                            <span className={`w-1.5 h-1.5 rounded-full flex-shrink-0 ${scan.enabled ? 'bg-emerald-400' : 'bg-muted'}`} />
                            {scan.name}
                          </span>
                        </button>
                      ))}
                    </div>
                  );
                })}
                {/* Built-in top lists */}
                <div className="border-b border-border-subtle">
                  <button onClick={() => toggleFolder('builtin')}
                    className="w-full flex items-center gap-1.5 px-3 py-1 text-left hover:bg-surface-hover transition-colors">
                    <span className="text-[10px] text-muted-fg">{expandedFolders.has('builtin') ? '\u25BC' : '\u25B6'}</span>
                    <span className="text-xs font-semibold text-foreground/80 flex-1">Built-in</span>
                    <span className="text-[10px] text-muted-fg">{BUILT_IN_TOP_LISTS.length}</span>
                  </button>
                  {expandedFolders.has('builtin') && BUILT_IN_TOP_LISTS.map(p => (
                    <button key={p.id}
                      onClick={() => setSelectedStrategy(p as any)}
                      onDoubleClick={() => handleLoadBuiltInTopList(p)}
                      className={`w-full text-left px-5 py-1 text-[11px] transition-colors truncate ${selectedStrategy && 'isTopList' in selectedStrategy && (selectedStrategy as any).id === p.id
                        ? 'bg-emerald-500/10 text-emerald-700 font-medium'
                        : 'text-foreground/80 hover:bg-surface-hover'
                        }`}
                    >{p.name}</button>
                  ))}
                </div>
              </div>
              {loadingScans && <div className="px-3 py-1 text-[10px] text-muted-fg text-center flex-shrink-0">Loading...</div>}
            </div>
            {/* Right: top list detail */}
            <div className="flex-1 flex flex-col overflow-hidden">
              {selectedStrategy ? (
                <>
                  <div className="flex-1 overflow-y-auto p-3">
                    {'isTopList' in selectedStrategy ? (
                      // Built-in top list preset
                      <>
                        <div className="text-xs font-bold text-foreground mb-1">{(selectedStrategy as any).name}</div>
                        <p className="text-[11px] text-muted-fg mb-3">{(selectedStrategy as any).description}</p>
                        <div>
                          <div className="text-[10px] font-semibold text-muted-fg uppercase tracking-wide mb-1">Filters</div>
                          <div className="flex flex-wrap gap-1">
                            {filtersToDisplay((selectedStrategy as any).filters).map(f => (
                              <span key={f} className="px-1.5 py-0.5 bg-surface-hover border border-border rounded text-[10px] font-mono text-foreground/80">{f}</span>
                            ))}
                          </div>
                        </div>
                      </>
                    ) : 'userId' in selectedStrategy ? (
                      // User scanner filter
                      <>
                        <div className="flex items-center justify-between mb-1">
                          <div className="text-xs font-bold text-foreground">{(selectedStrategy as any).name}</div>
                          <button onClick={async () => { await deleteScanFilter((selectedStrategy as any).id); setSelectedStrategy(null); }}
                            className="text-[10px] text-muted-fg/50 hover:text-rose-500">x</button>
                        </div>
                        <div className="flex items-center gap-2 mb-3">
                          <span className={`text-[10px] px-1.5 py-0.5 rounded ${(selectedStrategy as any).enabled ? 'bg-emerald-500/10 text-emerald-600 border border-emerald-200' : 'bg-surface-hover text-muted-fg border border-border'}`}>
                            {(selectedStrategy as any).enabled ? 'Active' : 'Inactive'}
                          </span>
                          <span className="text-[10px] text-muted-fg">
                            {new Date((selectedStrategy as any).createdAt).toLocaleDateString()}
                          </span>
                        </div>
                        <div>
                          <div className="text-[10px] font-semibold text-muted-fg uppercase tracking-wide mb-1">Filters</div>
                          <div className="flex flex-wrap gap-1">
                            {filtersToDisplay((selectedStrategy as any).parameters || {}).map(f => (
                              <span key={f} className="px-1.5 py-0.5 bg-surface-hover border border-border rounded text-[10px] font-mono text-foreground/80">{f}</span>
                            ))}
                          </div>
                        </div>
                      </>
                    ) : (
                      // Fallback: could be a strategy loaded while in toplist mode
                      <div className="text-[11px] text-muted-fg">Select a top list</div>
                    )}
                  </div>
                  <div className="flex-shrink-0 p-2 border-t border-border bg-surface-hover">
                    <button
                      onClick={() => {
                        if ('isTopList' in selectedStrategy) handleLoadBuiltInTopList(selectedStrategy as TopListPreset);
                        else if ('userId' in selectedStrategy) handleLoadScan(selectedStrategy as unknown as UserFilter);
                      }}
                      className="w-full py-1.5 text-xs font-semibold bg-emerald-600 text-white rounded hover:bg-emerald-700 transition-colors"
                    >Load Settings</button>
                  </div>
                </>
              ) : (
                <div className="h-full flex items-center justify-center text-muted-fg text-[11px] p-4 text-center">
                  Select a top list to see details, or double-click to load
                </div>
              )}
            </div>
          </div>
        )}

        {/* ====== ALERTS TAB ====== */}
        {activeTab === 'alerts' && (
          <div className="h-full flex flex-col">
            <div className="flex-shrink-0 px-2 pt-1.5 pb-1 border-b border-border flex items-center gap-2">
              <input type="text" value={alertSearch} onChange={(e) => setAlertSearch(e.target.value)}
                placeholder="Search..."
                className="flex-1 px-1.5 py-0.5 text-[11px] border border-border rounded focus:outline-none focus:ring-1 focus:ring-primary bg-[var(--color-input-bg)] text-foreground" />
              <span className="text-[10px] text-muted-fg tabular-nums">{selectedAlerts.size}</span>
              <button onClick={() => setSelectedAlerts(new Set(ALERT_CATALOG.filter(a => a.active).map(a => a.eventType)))}
                className="text-[10px] text-blue-600 dark:text-blue-400 hover:text-blue-700 dark:hover:text-blue-300">all</button>
              <button onClick={() => setSelectedAlerts(new Set())}
                className="text-[10px] text-muted-fg hover:text-foreground/80">clear</button>
            </div>
            <div className="flex-1 overflow-y-auto">
              {alertGroups.map(({ category, alerts }) => {
                const catTypes = alerts.map(a => a.eventType);
                const selCount = catTypes.filter(t => selectedAlerts.has(t)).length;
                const allSel = selCount === catTypes.length && catTypes.length > 0;
                const exp = expandedAlertCats.has(category.id);
                return (
                  <div key={category.id}>
                    <button onClick={() => toggleAlertCatExpand(category.id)}
                      className="w-full flex items-center gap-1 px-2 py-[3px] text-left hover:bg-surface-hover/80 transition-colors border-b border-border-subtle">
                      <span className="text-[9px] text-muted-fg w-3">{exp ? '\u25BC' : '\u25B6'}</span>
                      <span className="text-[11px] font-medium text-foreground/90 flex-1">{category.name}</span>
                      {selCount > 0 && <span className="text-[9px] text-blue-600 dark:text-blue-400 font-semibold tabular-nums">{selCount}/{catTypes.length}</span>}
                      <button onClick={(e) => { e.stopPropagation(); toggleAlertCat(catTypes); }}
                        className="text-[9px] text-muted-fg hover:text-blue-600 dark:hover:text-blue-400 px-1">
                        {allSel ? 'none' : 'all'}
                      </button>
                    </button>
                    {exp && (
                      <div className="px-2 py-1 space-y-[2px]">
                        {alerts.map(a => {
                          const sel = selectedAlerts.has(a.eventType);
                          const cs = a.customSetting;
                          const csKey = `aq:${a.eventType}`;
                          return (
                            <div key={a.eventType} className="flex items-center gap-1">
                              <button onClick={() => toggleAlert(a.eventType)}
                                className={`flex-1 px-1.5 py-[2px] text-[11px] rounded border transition-colors text-left truncate ${sel
                                  ? 'bg-blue-500/10 border-blue-500/30 text-blue-600 dark:text-blue-400 font-medium'
                                  : 'border-border-subtle text-foreground/80 hover:bg-surface-hover hover:text-foreground'
                                  }`}
                              >{a.name}</button>
                              {sel && cs.type !== 'none' && (
                                <input
                                  type="number"
                                  step="any"
                                  placeholder={cs.defaultValue != null ? String(cs.defaultValue) : cs.hint || ''}
                                  title={`${cs.label}${cs.unit ? ` (${cs.unit})` : ''}`}
                                  value={filters[csKey] ?? ''}
                                  onChange={e => {
                                    const v = e.target.value;
                                    setFilter(csKey, v === '' ? undefined : Number(v));
                                  }}
                                  className="w-14 px-1 py-[1px] text-[10px] tabular-nums border border-border rounded bg-[var(--color-input-bg)] text-foreground text-center focus:outline-none focus:ring-1 focus:ring-primary"
                                />
                              )}
                            </div>
                          );
                        })}
                      </div>
                    )}
                  </div>
                );
              })}
            </div>
          </div>
        )}

        {/* ====== FILTERS TAB ====== */}
        {activeTab === 'filters' && (() => {
          const FG = [
            // ═══════════════════════════════════════════════════════════
            // PRICE & QUOTE
            // ═══════════════════════════════════════════════════════════
            {
              id: 'price', group: 'Price & Quote', filters: [
                { label: 'Price', minK: 'min_price', maxK: 'max_price', suf: '$', phMin: '0.50', phMax: '500' },
                { label: 'Spread', minK: 'min_spread', maxK: 'max_spread', suf: '$', phMin: '0.01', phMax: '0.50' },
                { label: 'Bid Size', minK: 'min_bid_size', maxK: 'max_bid_size', suf: '', units: ['', 'K'], defU: '', phMin: '100', phMax: '10000' },
                { label: 'Ask Size', minK: 'min_ask_size', maxK: 'max_ask_size', suf: '', units: ['', 'K'], defU: '', phMin: '100', phMax: '10000' },
                { label: 'Bid / Ask Ratio', minK: 'min_bid_ask_ratio', maxK: 'max_bid_ask_ratio', suf: '', phMin: '0.5', phMax: '3' },
                { label: 'Distance from Inside Market', minK: 'min_distance_from_nbbo', maxK: 'max_distance_from_nbbo', suf: '%', phMin: '0', phMax: '1' },
                { label: 'Decimal', minK: 'min_decimal', maxK: 'max_decimal', suf: '', phMin: '0', phMax: '0.99' },
              ]
            },
            // ═══════════════════════════════════════════════════════════
            // VOLUME
            // ═══════════════════════════════════════════════════════════
            {
              id: 'volume', group: 'Volume', filters: [
                { label: 'Relative Volume', minK: 'min_rvol', maxK: 'max_rvol', suf: 'x', phMin: '1', phMax: '10' },
                { label: 'Volume Today', minK: 'min_volume', maxK: 'max_volume', suf: '', units: ['', 'K', 'M'], defU: 'K', phMin: '10', phMax: '500' },
                { label: 'Volume Today %', minK: 'min_volume_today_pct', maxK: 'max_volume_today_pct', suf: '%', phMin: '50', phMax: '500' },
                { label: 'Volume Yesterday %', minK: 'min_volume_yesterday_pct', maxK: 'max_volume_yesterday_pct', suf: '%', phMin: '50', phMax: '500' },
                { label: 'Dollar Volume', minK: 'min_dollar_volume', maxK: 'max_dollar_volume', suf: '$', units: ['K', 'M', 'B'], defU: 'M', phMin: '1', phMax: '100' },
                { label: 'Float Turnover', minK: 'min_float_turnover', maxK: 'max_float_turnover', suf: 'x', phMin: '0.01', phMax: '5' },
                { label: 'Previous Day Volume', minK: 'min_prev_day_volume', maxK: 'max_prev_day_volume', suf: '', units: ['', 'K', 'M'], defU: 'K', phMin: '100', phMax: '10000' },
                { label: 'Post-Market Volume', minK: 'min_postmarket_volume', maxK: 'max_postmarket_volume', suf: '', units: ['', 'K', 'M'], defU: 'K', phMin: '10', phMax: '500' },
              ]
            },
            {
              id: 'volwindows', group: 'Volume by Minute Window', filters: [
                { label: 'Volume 1 Minute', minK: 'min_vol_1min', maxK: 'max_vol_1min', suf: '', units: ['', 'K', 'M'], defU: 'K', phMin: '1', phMax: '50' },
                { label: 'Volume 5 Minute', minK: 'min_vol_5min', maxK: 'max_vol_5min', suf: '', units: ['', 'K', 'M'], defU: 'K', phMin: '1', phMax: '100' },
                { label: 'Volume 10 Minute', minK: 'min_vol_10min', maxK: 'max_vol_10min', suf: '', units: ['', 'K', 'M'], defU: 'K', phMin: '5', phMax: '200' },
                { label: 'Volume 15 Minute', minK: 'min_vol_15min', maxK: 'max_vol_15min', suf: '', units: ['', 'K', 'M'], defU: 'K', phMin: '10', phMax: '500' },
                { label: 'Volume 30 Minute', minK: 'min_vol_30min', maxK: 'max_vol_30min', suf: '', units: ['', 'K', 'M'], defU: 'K', phMin: '20', phMax: '1000' },
                { label: 'Average Volume 1m %', minK: 'min_vol_1min_pct', maxK: 'max_vol_1min_pct', suf: '%', phMin: '100', phMax: '500' },
                { label: 'Average Volume 5m %', minK: 'min_vol_5min_pct', maxK: 'max_vol_5min_pct', suf: '%', phMin: '100', phMax: '500' },
                { label: 'Average Volume 10m %', minK: 'min_vol_10min_pct', maxK: 'max_vol_10min_pct', suf: '%', phMin: '100', phMax: '500' },
                { label: 'Average Volume 15m %', minK: 'min_vol_15min_pct', maxK: 'max_vol_15min_pct', suf: '%', phMin: '100', phMax: '500' },
                { label: 'Average Volume 30m %', minK: 'min_vol_30min_pct', maxK: 'max_vol_30min_pct', suf: '%', phMin: '100', phMax: '500' },
                { label: 'Minute Volume', minK: 'min_minute_volume', maxK: 'max_minute_volume', suf: '', units: ['', 'K', 'M'], defU: 'K', phMin: '1', phMax: '100' },
              ]
            },
            {
              id: 'avgvol', group: 'Average Daily Volume', filters: [
                { label: 'Average Daily Volume (5D)', minK: 'min_avg_volume_5d', maxK: 'max_avg_volume_5d', suf: '', units: ['', 'K', 'M'], defU: 'K', phMin: '100', phMax: '5000' },
                { label: 'Average Daily Volume (10D)', minK: 'min_avg_volume_10d', maxK: 'max_avg_volume_10d', suf: '', units: ['', 'K', 'M'], defU: 'K', phMin: '100', phMax: '5000' },
                { label: 'Average Daily Volume (20D)', minK: 'min_avg_volume_20d', maxK: 'max_avg_volume_20d', suf: '', units: ['', 'K', 'M'], defU: 'K', phMin: '100', phMax: '5000' },
                { label: 'Average Daily Volume (3M)', minK: 'min_avg_volume_3m', maxK: 'max_avg_volume_3m', suf: '', units: ['', 'K', 'M'], defU: 'K', phMin: '100', phMax: '5000' },
              ]
            },
            // ═══════════════════════════════════════════════════════════
            // CHANGE FROM CLOSE / OPEN / GAP
            // ═══════════════════════════════════════════════════════════
            {
              id: 'change', group: 'Change from Close / Open', filters: [
                { label: 'Change from the Close %', minK: 'min_change_percent', maxK: 'max_change_percent', suf: '%', phMin: '-10', phMax: '50' },
                { label: 'Change from the Close $', minK: 'min_change_from_close_dollars', maxK: 'max_change_from_close_dollars', suf: '$', phMin: '-10', phMax: '20' },
                { label: 'Change from the Close (ATR)', minK: 'min_change_from_close_ratio', maxK: 'max_change_from_close_ratio', suf: 'x', phMin: '-5', phMax: '5' },
                { label: 'Change from the Open %', minK: 'min_change_from_open', maxK: 'max_change_from_open', suf: '%', phMin: '-5', phMax: '20' },
                { label: 'Change from the Open $', minK: 'min_change_from_open_dollars', maxK: 'max_change_from_open_dollars', suf: '$', phMin: '-5', phMax: '10' },
                { label: 'Change from the Open (ATR)', minK: 'min_change_from_open_ratio', maxK: 'max_change_from_open_ratio', suf: 'x', phMin: '-5', phMax: '5' },
                { label: 'Change from the Open Weighted', minK: 'min_change_from_open_weighted', maxK: 'max_change_from_open_weighted', suf: '', phMin: '-3', phMax: '3' },
              ]
            },
            {
              id: 'gap', group: 'Gap', filters: [
                { label: 'Gap %', minK: 'min_gap_percent', maxK: 'max_gap_percent', suf: '%', phMin: '-10', phMax: '30' },
                { label: 'Gap $', minK: 'min_gap_dollars', maxK: 'max_gap_dollars', suf: '$', phMin: '-5', phMax: '10' },
                { label: 'Gap (ATR)', minK: 'min_gap_ratio', maxK: 'max_gap_ratio', suf: 'x', phMin: '-3', phMax: '5' },
              ]
            },
            {
              id: 'prepost', group: 'Pre-Market / Post-Market', filters: [
                { label: 'Change Pre-Market %', minK: 'min_premarket_change_percent', maxK: 'max_premarket_change_percent', suf: '%', phMin: '-5', phMax: '20' },
                { label: 'Change Post-Market %', minK: 'min_postmarket_change_percent', maxK: 'max_postmarket_change_percent', suf: '%', phMin: '-5', phMax: '10' },
                { label: 'Change Post-Market $', minK: 'min_postmarket_change_dollars', maxK: 'max_postmarket_change_dollars', suf: '$', phMin: '-5', phMax: '5' },
              ]
            },
            // ═══════════════════════════════════════════════════════════
            // INTRADAY CHANGE BY MINUTE
            // ═══════════════════════════════════════════════════════════
            {
              id: 'chgminute', group: 'Change by Minute', filters: [
                { label: 'Change 1 Minute', minK: 'min_chg_1min', maxK: 'max_chg_1min', suf: '%', phMin: '-2', phMax: '5' },
                { label: 'Change 1 Minute', minK: 'min_chg_1min_dollars', maxK: 'max_chg_1min_dollars', suf: '$', phMin: '-0.50', phMax: '1.00' },
                { label: 'Change 2 Minute', minK: 'min_chg_2min', maxK: 'max_chg_2min', suf: '%', phMin: '-3', phMax: '7' },
                { label: 'Change 2 Minute', minK: 'min_chg_2min_dollars', maxK: 'max_chg_2min_dollars', suf: '$', phMin: '-0.75', phMax: '1.50' },
                { label: 'Change 5 Minute', minK: 'min_chg_5min', maxK: 'max_chg_5min', suf: '%', phMin: '-5', phMax: '10' },
                { label: 'Change 5 Minute', minK: 'min_chg_5min_dollars', maxK: 'max_chg_5min_dollars', suf: '$', phMin: '-1.00', phMax: '2.50' },
                { label: 'Change 10 Minute', minK: 'min_chg_10min', maxK: 'max_chg_10min', suf: '%', phMin: '-5', phMax: '15' },
                { label: 'Change 10 Minute', minK: 'min_chg_10min_dollars', maxK: 'max_chg_10min_dollars', suf: '$', phMin: '-1.50', phMax: '4.00' },
                { label: 'Change 15 Minute', minK: 'min_chg_15min', maxK: 'max_chg_15min', suf: '%', phMin: '-8', phMax: '20' },
                { label: 'Change 15 Minute', minK: 'min_chg_15min_dollars', maxK: 'max_chg_15min_dollars', suf: '$', phMin: '-2.00', phMax: '5.00' },
                { label: 'Change 30 Minute', minK: 'min_chg_30min', maxK: 'max_chg_30min', suf: '%', phMin: '-10', phMax: '25' },
                { label: 'Change 30 Minute', minK: 'min_chg_30min_dollars', maxK: 'max_chg_30min_dollars', suf: '$', phMin: '-3.00', phMax: '7.00' },
                { label: 'Change 60 Minute', minK: 'min_chg_60min', maxK: 'max_chg_60min', suf: '%', phMin: '-15', phMax: '30' },
                { label: 'Change 60 Minute', minK: 'min_chg_60min_dollars', maxK: 'max_chg_60min_dollars', suf: '$', phMin: '-5.00', phMax: '10.00' },
                { label: 'Change 120 Minute', minK: 'min_chg_120min', maxK: 'max_chg_120min', suf: '%', phMin: '-20', phMax: '40' },
                { label: 'Change 120 Minute', minK: 'min_chg_120min_dollars', maxK: 'max_chg_120min_dollars', suf: '$', phMin: '-8.00', phMax: '15.00' },
              ]
            },
            // ═══════════════════════════════════════════════════════════
            // MULTI-DAY CHANGE
            // ═══════════════════════════════════════════════════════════
            {
              id: 'multiday', group: 'Change in Days %', filters: [
                { label: 'Change Previous Day', minK: 'min_change_1d', maxK: 'max_change_1d', suf: '%', phMin: '-10', phMax: '10' },
                { label: 'Change in 3 Days', minK: 'min_change_3d', maxK: 'max_change_3d', suf: '%', phMin: '-20', phMax: '20' },
                { label: 'Change in 5 Days', minK: 'min_change_5d', maxK: 'max_change_5d', suf: '%', phMin: '-20', phMax: '50' },
                { label: 'Change in 10 Days', minK: 'min_change_10d', maxK: 'max_change_10d', suf: '%', phMin: '-30', phMax: '100' },
                { label: 'Change in 20 Days', minK: 'min_change_20d', maxK: 'max_change_20d', suf: '%', phMin: '-50', phMax: '200' },
              ]
            },
            {
              id: 'multidaychgdollars', group: 'Change in Days $', filters: [
                { label: 'Change in 5 Days $', minK: 'min_change_5d_dollars', maxK: 'max_change_5d_dollars', suf: '$', phMin: '-10', phMax: '10' },
                { label: 'Change in 10 Days $', minK: 'min_change_10d_dollars', maxK: 'max_change_10d_dollars', suf: '$', phMin: '-20', phMax: '20' },
                { label: 'Change in 20 Days $', minK: 'min_change_20d_dollars', maxK: 'max_change_20d_dollars', suf: '$', phMin: '-30', phMax: '30' },
              ]
            },
            {
              id: 'longterm', group: 'Long-Term Change', filters: [
                { label: 'Change in 1 Year %', minK: 'min_change_1y', maxK: 'max_change_1y', suf: '%', phMin: '-50', phMax: '200' },
                { label: 'Change in 1 Year $', minK: 'min_change_1y_dollars', maxK: 'max_change_1y_dollars', suf: '$', phMin: '-50', phMax: '100' },
                { label: 'Change Since January 1 %', minK: 'min_change_ytd', maxK: 'max_change_ytd', suf: '%', phMin: '-30', phMax: '100' },
                { label: 'Change Since January 1 $', minK: 'min_change_ytd_dollars', maxK: 'max_change_ytd_dollars', suf: '$', phMin: '-20', phMax: '50' },
              ]
            },
            // ═══════════════════════════════════════════════════════════
            // VOLATILITY & RANGE
            // ═══════════════════════════════════════════════════════════
            {
              id: 'volatility', group: 'Volatility', filters: [
                { label: 'Average True Range', minK: 'min_atr', maxK: 'max_atr', suf: '$', phMin: '0.1', phMax: '5' },
                { label: 'Average True Range %', minK: 'min_atr_percent', maxK: 'max_atr_percent', suf: '%', phMin: '2', phMax: '10' },
                { label: 'Yearly Standard Deviation', minK: 'min_yearly_std_dev', maxK: 'max_yearly_std_dev', suf: '$', phMin: '0.5', phMax: '10' },
                { label: 'Standard Deviation (Bollinger)', minK: 'min_bb_std_dev', maxK: 'max_bb_std_dev', suf: '$', phMin: '0.01', phMax: '5' },
                { label: 'Daily ATR %', minK: 'min_daily_atr_percent', maxK: 'max_daily_atr_percent', suf: '%', phMin: '1', phMax: '15' },
              ]
            },
            {
              id: 'todayrange', group: "Today's Range", filters: [
                { label: "Today's Range $", minK: 'min_todays_range', maxK: 'max_todays_range', suf: '$', phMin: '0.1', phMax: '10' },
                { label: "Today's Range %", minK: 'min_todays_range_pct', maxK: 'max_todays_range_pct', suf: '%', phMin: '1', phMax: '20' },
              ]
            },
            {
              id: 'minuterange', group: 'Minute Range $', filters: [
                { label: '2 Minute Range $', minK: 'min_range_2min', maxK: 'max_range_2min', suf: '$', phMin: '0.10', phMax: '2' },
                { label: '5 Minute Range $', minK: 'min_range_5min', maxK: 'max_range_5min', suf: '$', phMin: '0.20', phMax: '5' },
                { label: '15 Minute Range $', minK: 'min_range_15min', maxK: 'max_range_15min', suf: '$', phMin: '0.50', phMax: '10' },
                { label: '30 Minute Range $', minK: 'min_range_30min', maxK: 'max_range_30min', suf: '$', phMin: '1', phMax: '15' },
                { label: '60 Minute Range $', minK: 'min_range_60min', maxK: 'max_range_60min', suf: '$', phMin: '1', phMax: '20' },
                { label: '120 Minute Range $', minK: 'min_range_120min', maxK: 'max_range_120min', suf: '$', phMin: '2', phMax: '30' },
              ]
            },
            {
              id: 'minuterangepct', group: 'Minute Range %', filters: [
                { label: '2 Minute Range %', minK: 'min_range_2min_pct', maxK: 'max_range_2min_pct', suf: '%', phMin: '50', phMax: '300' },
                { label: '5 Minute Range %', minK: 'min_range_5min_pct', maxK: 'max_range_5min_pct', suf: '%', phMin: '50', phMax: '300' },
                { label: '15 Minute Range %', minK: 'min_range_15min_pct', maxK: 'max_range_15min_pct', suf: '%', phMin: '50', phMax: '300' },
                { label: '30 Minute Range %', minK: 'min_range_30min_pct', maxK: 'max_range_30min_pct', suf: '%', phMin: '50', phMax: '300' },
                { label: '60 Minute Range %', minK: 'min_range_60min_pct', maxK: 'max_range_60min_pct', suf: '%', phMin: '50', phMax: '300' },
                { label: '120 Minute Range %', minK: 'min_range_120min_pct', maxK: 'max_range_120min_pct', suf: '%', phMin: '50', phMax: '300' },
              ]
            },
            {
              id: 'multidayrange', group: 'Multi-Day Range $', filters: [
                { label: '5 Day Range $', minK: 'min_range_5d', maxK: 'max_range_5d', suf: '$', phMin: '0.5', phMax: '20' },
                { label: '10 Day Range $', minK: 'min_range_10d', maxK: 'max_range_10d', suf: '$', phMin: '1', phMax: '30' },
                { label: '20 Day Range $', minK: 'min_range_20d', maxK: 'max_range_20d', suf: '$', phMin: '2', phMax: '50' },
              ]
            },
            {
              id: 'multidayrangepct', group: 'Multi-Day Range %', filters: [
                { label: '5 Day Range %', minK: 'min_range_5d_pct', maxK: 'max_range_5d_pct', suf: '%', phMin: '50', phMax: '500' },
                { label: '10 Day Range %', minK: 'min_range_10d_pct', maxK: 'max_range_10d_pct', suf: '%', phMin: '100', phMax: '800' },
                { label: '20 Day Range %', minK: 'min_range_20d_pct', maxK: 'max_range_20d_pct', suf: '%', phMin: '150', phMax: '1200' },
              ]
            },
            // ═══════════════════════════════════════════════════════════
            // POSITION IN RANGE
            // ═══════════════════════════════════════════════════════════
            {
              id: 'posrange', group: 'Position in Range', filters: [
                { label: 'Position in Range (Today)', minK: 'min_pos_in_range', maxK: 'max_pos_in_range', suf: '%', phMin: '0', phMax: '100' },
                { label: "Position in Previous Day's Range", minK: 'min_pos_in_prev_day_range', maxK: 'max_pos_in_prev_day_range', suf: '%', phMin: '0', phMax: '100' },
                { label: 'Position in 5 Day Range', minK: 'min_pos_in_5d_range', maxK: 'max_pos_in_5d_range', suf: '%', phMin: '0', phMax: '100' },
                { label: 'Position in 10 Day Range', minK: 'min_pos_in_10d_range', maxK: 'max_pos_in_10d_range', suf: '%', phMin: '0', phMax: '100' },
                { label: 'Position in 20 Day Range', minK: 'min_pos_in_20d_range', maxK: 'max_pos_in_20d_range', suf: '%', phMin: '0', phMax: '100' },
                { label: 'Position in 52 Week Range', minK: 'min_pos_in_52w_range', maxK: 'max_pos_in_52w_range', suf: '%', phMin: '0', phMax: '100' },
                { label: 'Position in 3 Month Range', minK: 'min_pos_in_3m_range', maxK: 'max_pos_in_3m_range', suf: '%', phMin: '0', phMax: '100' },
                { label: 'Position in 6 Month Range', minK: 'min_pos_in_6m_range', maxK: 'max_pos_in_6m_range', suf: '%', phMin: '0', phMax: '100' },
                { label: 'Position in 9 Month Range', minK: 'min_pos_in_9m_range', maxK: 'max_pos_in_9m_range', suf: '%', phMin: '0', phMax: '100' },
                { label: 'Position in 2 Year Range', minK: 'min_pos_in_2y_range', maxK: 'max_pos_in_2y_range', suf: '%', phMin: '0', phMax: '100' },
                { label: 'Position in Lifetime Range', minK: 'min_pos_in_lifetime_range', maxK: 'max_pos_in_lifetime_range', suf: '%', phMin: '0', phMax: '100' },
                { label: 'Position in Pre-Market Range', minK: 'min_pos_in_premarket_range', maxK: 'max_pos_in_premarket_range', suf: '%', phMin: '0', phMax: '100' },
              ]
            },
            {
              id: 'tfrange', group: 'Position in Minute Range', filters: [
                { label: 'Position in 5 Minute Range', minK: 'min_pos_in_range_5m', maxK: 'max_pos_in_range_5m', suf: '%', phMin: '0', phMax: '100' },
                { label: 'Position in 15 Minute Range', minK: 'min_pos_in_range_15m', maxK: 'max_pos_in_range_15m', suf: '%', phMin: '0', phMax: '100' },
                { label: 'Position in 30 Minute Range', minK: 'min_pos_in_range_30m', maxK: 'max_pos_in_range_30m', suf: '%', phMin: '0', phMax: '100' },
                { label: 'Position in 60 Minute Range', minK: 'min_pos_in_range_60m', maxK: 'max_pos_in_range_60m', suf: '%', phMin: '0', phMax: '100' },
              ]
            },
            {
              id: 'highlow', group: 'High / Low', filters: [
                { label: 'Below High', minK: 'min_below_high', maxK: 'max_below_high', suf: '$', phMin: '0', phMax: '5' },
                { label: 'Above Low', minK: 'min_above_low', maxK: 'max_above_low', suf: '$', phMin: '0', phMax: '5' },
                { label: 'Below Pre-Market High', minK: 'min_below_premarket_high', maxK: 'max_below_premarket_high', suf: '$', phMin: '0', phMax: '5' },
                { label: 'Above Pre-Market Low', minK: 'min_above_premarket_low', maxK: 'max_above_premarket_low', suf: '$', phMin: '0', phMax: '5' },
                { label: 'From Intraday High %', minK: 'min_price_from_intraday_high', maxK: 'max_price_from_intraday_high', suf: '%', phMin: '-10', phMax: '0' },
                { label: 'From Intraday Low %', minK: 'min_price_from_intraday_low', maxK: 'max_price_from_intraday_low', suf: '%', phMin: '0', phMax: '20' },
                { label: 'From High %', minK: 'min_price_from_high', maxK: 'max_price_from_high', suf: '%', phMin: '-20', phMax: '0' },
                { label: 'From Low %', minK: 'min_price_from_low', maxK: 'max_price_from_low', suf: '%', phMin: '0', phMax: '50' },
                { label: 'Position of Open', minK: 'min_pos_of_open', maxK: 'max_pos_of_open', suf: '%', phMin: '0', phMax: '100' },
              ]
            },
            // ═══════════════════════════════════════════════════════════
            // CONSECUTIVE CANDLES / DAYS
            // ═══════════════════════════════════════════════════════════
            {
              id: 'consec', group: 'Consecutive Candles', filters: [
                { label: 'Consecutive Candles (1m)', minK: 'min_consecutive_candles', maxK: 'max_consecutive_candles', suf: '', phMin: '-10', phMax: '10' },
                { label: 'Consecutive Candles (2m)', minK: 'min_consecutive_candles_2m', maxK: 'max_consecutive_candles_2m', suf: '', phMin: '-10', phMax: '10' },
                { label: 'Consecutive Candles (5m)', minK: 'min_consecutive_candles_5m', maxK: 'max_consecutive_candles_5m', suf: '', phMin: '-10', phMax: '10' },
                { label: 'Consecutive Candles (10m)', minK: 'min_consecutive_candles_10m', maxK: 'max_consecutive_candles_10m', suf: '', phMin: '-10', phMax: '10' },
                { label: 'Consecutive Candles (15m)', minK: 'min_consecutive_candles_15m', maxK: 'max_consecutive_candles_15m', suf: '', phMin: '-10', phMax: '10' },
                { label: 'Consecutive Candles (30m)', minK: 'min_consecutive_candles_30m', maxK: 'max_consecutive_candles_30m', suf: '', phMin: '-10', phMax: '10' },
                { label: 'Consecutive Candles (60m)', minK: 'min_consecutive_candles_60m', maxK: 'max_consecutive_candles_60m', suf: '', phMin: '-10', phMax: '10' },
              ]
            },
            {
              id: 'consecdays', group: 'Consecutive Days', filters: [
                { label: 'Consecutive Days Up/Down', minK: 'min_consecutive_days_up', maxK: 'max_consecutive_days_up', suf: '', phMin: '-5', phMax: '5' },
              ]
            },
            // ═══════════════════════════════════════════════════════════
            // PIVOT POINTS & VWAP
            // ═══════════════════════════════════════════════════════════
            {
              id: 'pivot', group: 'Pivot Points', filters: [
                { label: 'Distance from Pivot', minK: 'min_dist_pivot', maxK: 'max_dist_pivot', suf: '%', phMin: '-5', phMax: '5' },
                { label: 'Distance from Pivot R1', minK: 'min_dist_pivot_r1', maxK: 'max_dist_pivot_r1', suf: '%', phMin: '-5', phMax: '5' },
                { label: 'Distance from Pivot R2', minK: 'min_dist_pivot_r2', maxK: 'max_dist_pivot_r2', suf: '%', phMin: '-5', phMax: '5' },
                { label: 'Distance from Pivot S1', minK: 'min_dist_pivot_s1', maxK: 'max_dist_pivot_s1', suf: '%', phMin: '-5', phMax: '5' },
                { label: 'Distance from Pivot S2', minK: 'min_dist_pivot_s2', maxK: 'max_dist_pivot_s2', suf: '%', phMin: '-5', phMax: '5' },
              ]
            },
            {
              id: 'vwap', group: 'VWAP', filters: [
                { label: 'VWAP', minK: 'min_vwap', maxK: 'max_vwap', suf: '$', phMin: '5', phMax: '200' },
                { label: 'Distance from VWAP', minK: 'min_dist_from_vwap', maxK: 'max_dist_from_vwap', suf: '%', phMin: '-10', phMax: '10' },
              ]
            },
            // ═══════════════════════════════════════════════════════════
            // INTRADAY TECHNICAL INDICATORS
            // ═══════════════════════════════════════════════════════════
            {
              id: 'tech', group: 'Intraday Technical', filters: [
                { label: 'RSI (1m)', minK: 'min_rsi', maxK: 'max_rsi', suf: '', phMin: '20', phMax: '80' },
                { label: 'SMA 5', minK: 'min_sma_5', maxK: 'max_sma_5', suf: '$', phMin: '1', phMax: '500' },
                { label: 'SMA 8', minK: 'min_sma_8', maxK: 'max_sma_8', suf: '$', phMin: '1', phMax: '500' },
                { label: 'SMA 20', minK: 'min_sma_20', maxK: 'max_sma_20', suf: '$', phMin: '5', phMax: '500' },
                { label: 'SMA 50', minK: 'min_sma_50', maxK: 'max_sma_50', suf: '$', phMin: '5', phMax: '500' },
                { label: 'SMA 200', minK: 'min_sma_200', maxK: 'max_sma_200', suf: '$', phMin: '5', phMax: '500' },
                { label: 'EMA 20', minK: 'min_ema_20', maxK: 'max_ema_20', suf: '$', phMin: '5', phMax: '500' },
                { label: 'EMA 50', minK: 'min_ema_50', maxK: 'max_ema_50', suf: '$', phMin: '5', phMax: '500' },
                { label: 'MACD Line', minK: 'min_macd_line', maxK: 'max_macd_line', suf: '', phMin: '-5', phMax: '5' },
                { label: 'MACD Histogram', minK: 'min_macd_hist', maxK: 'max_macd_hist', suf: '', phMin: '-2', phMax: '2' },
                { label: 'Stochastic %K', minK: 'min_stoch_k', maxK: 'max_stoch_k', suf: '', phMin: '20', phMax: '80' },
                { label: 'Stochastic %D', minK: 'min_stoch_d', maxK: 'max_stoch_d', suf: '', phMin: '20', phMax: '80' },
                { label: 'ADX (Intraday)', minK: 'min_adx_14', maxK: 'max_adx_14', suf: '', phMin: '20', phMax: '50' },
                { label: 'Bollinger Upper', minK: 'min_bb_upper', maxK: 'max_bb_upper', suf: '$', phMin: '', phMax: '' },
                { label: 'Bollinger Lower', minK: 'min_bb_lower', maxK: 'max_bb_lower', suf: '$', phMin: '', phMax: '' },
              ]
            },
            {
              id: 'tfrsi', group: 'Multi-Timeframe RSI', filters: [
                { label: '2 Minute RSI', minK: 'min_rsi_2m', maxK: 'max_rsi_2m', suf: '', phMin: '20', phMax: '80' },
                { label: '5 Minute RSI', minK: 'min_rsi_5m', maxK: 'max_rsi_5m', suf: '', phMin: '20', phMax: '80' },
                { label: '15 Minute RSI', minK: 'min_rsi_15m', maxK: 'max_rsi_15m', suf: '', phMin: '20', phMax: '80' },
                { label: '60 Minute RSI', minK: 'min_rsi_60m', maxK: 'max_rsi_60m', suf: '', phMin: '20', phMax: '80' },
              ]
            },
            {
              id: 'tfboll', group: 'Position in Bollinger Bands', filters: [
                { label: 'Position in Bollinger Bands (1m)', minK: 'min_bb_position_1m', maxK: 'max_bb_position_1m', suf: '%', phMin: '0', phMax: '100' },
                { label: 'Position in Bollinger Bands (5m)', minK: 'min_bb_position_5m', maxK: 'max_bb_position_5m', suf: '%', phMin: '0', phMax: '100' },
                { label: 'Position in Bollinger Bands (15m)', minK: 'min_bb_position_15m', maxK: 'max_bb_position_15m', suf: '%', phMin: '0', phMax: '100' },
                { label: 'Position in Bollinger Bands (60m)', minK: 'min_bb_position_60m', maxK: 'max_bb_position_60m', suf: '%', phMin: '0', phMax: '100' },
                { label: 'Position in Bollinger Bands (Daily)', minK: 'min_daily_bb_position', maxK: 'max_daily_bb_position', suf: '%', phMin: '0', phMax: '100' },
              ]
            },
            // ═══════════════════════════════════════════════════════════
            // INTRADAY SMA DISTANCE (%)
            // ═══════════════════════════════════════════════════════════
            {
              id: 'tfsma', group: 'Change from Period SMA (Intraday)', filters: [
                { label: 'Change from 5 Period SMA (2m)', minK: 'min_dist_sma_5_2m', maxK: 'max_dist_sma_5_2m', suf: '%', phMin: '-5', phMax: '5' },
                { label: 'Change from 5 Period SMA (5m)', minK: 'min_dist_sma_5_5m', maxK: 'max_dist_sma_5_5m', suf: '%', phMin: '-5', phMax: '5' },
                { label: 'Change from 5 Period SMA (15m)', minK: 'min_dist_sma_5_15m', maxK: 'max_dist_sma_5_15m', suf: '%', phMin: '-5', phMax: '5' },
                { label: 'Change from 5 Period SMA (60m)', minK: 'min_dist_sma_5_60m', maxK: 'max_dist_sma_5_60m', suf: '%', phMin: '-10', phMax: '10' },
                { label: 'Change from 8 Period SMA (2m)', minK: 'min_dist_sma_8_2m', maxK: 'max_dist_sma_8_2m', suf: '%', phMin: '-5', phMax: '5' },
                { label: 'Change from 8 Period SMA (5m)', minK: 'min_dist_sma_8_5m', maxK: 'max_dist_sma_8_5m', suf: '%', phMin: '-5', phMax: '5' },
                { label: 'Change from 8 Period SMA (15m)', minK: 'min_dist_sma_8_15m', maxK: 'max_dist_sma_8_15m', suf: '%', phMin: '-5', phMax: '5' },
                { label: 'Change from 8 Period SMA (60m)', minK: 'min_dist_sma_8_60m', maxK: 'max_dist_sma_8_60m', suf: '%', phMin: '-10', phMax: '10' },
                { label: 'Change from 10 Period SMA (2m)', minK: 'min_dist_sma_10_2m', maxK: 'max_dist_sma_10_2m', suf: '%', phMin: '-5', phMax: '5' },
                { label: 'Change from 10 Period SMA (5m)', minK: 'min_dist_sma_10_5m', maxK: 'max_dist_sma_10_5m', suf: '%', phMin: '-5', phMax: '5' },
                { label: 'Change from 10 Period SMA (15m)', minK: 'min_dist_sma_10_15m', maxK: 'max_dist_sma_10_15m', suf: '%', phMin: '-5', phMax: '5' },
                { label: 'Change from 10 Period SMA (60m)', minK: 'min_dist_sma_10_60m', maxK: 'max_dist_sma_10_60m', suf: '%', phMin: '-10', phMax: '10' },
                { label: 'Change from 20 Period SMA (2m)', minK: 'min_dist_sma_20_2m', maxK: 'max_dist_sma_20_2m', suf: '%', phMin: '-10', phMax: '10' },
                { label: 'Change from 20 Period SMA (5m)', minK: 'min_dist_sma_20_5m', maxK: 'max_dist_sma_20_5m', suf: '%', phMin: '-10', phMax: '10' },
                { label: 'Change from 20 Period SMA (15m)', minK: 'min_dist_sma_20_15m', maxK: 'max_dist_sma_20_15m', suf: '%', phMin: '-10', phMax: '10' },
                { label: 'Change from 20 Period SMA (60m)', minK: 'min_dist_sma_20_60m', maxK: 'max_dist_sma_20_60m', suf: '%', phMin: '-10', phMax: '10' },
                { label: 'Change from 130 Period SMA (15m)', minK: 'min_dist_sma_130_15m', maxK: 'max_dist_sma_130_15m', suf: '%', phMin: '-15', phMax: '15' },
                { label: 'Change from 200 Period SMA (2m)', minK: 'min_dist_sma_200_2m', maxK: 'max_dist_sma_200_2m', suf: '%', phMin: '-20', phMax: '20' },
                { label: 'Change from 200 Period SMA (5m)', minK: 'min_dist_sma_200_5m', maxK: 'max_dist_sma_200_5m', suf: '%', phMin: '-20', phMax: '20' },
                { label: 'Change from 200 Period SMA (15m)', minK: 'min_dist_sma_200_15m', maxK: 'max_dist_sma_200_15m', suf: '%', phMin: '-20', phMax: '20' },
                { label: 'Change from 200 Period SMA (60m)', minK: 'min_dist_sma_200_60m', maxK: 'max_dist_sma_200_60m', suf: '%', phMin: '-20', phMax: '20' },
                { label: 'Change from SMA 5 (Intraday)', minK: 'min_dist_sma_5', maxK: 'max_dist_sma_5', suf: '%', phMin: '-5', phMax: '5' },
                { label: 'Change from SMA 8 (Intraday)', minK: 'min_dist_sma_8', maxK: 'max_dist_sma_8', suf: '%', phMin: '-5', phMax: '5' },
                { label: 'Change from SMA 20 (Intraday)', minK: 'min_dist_sma_20', maxK: 'max_dist_sma_20', suf: '%', phMin: '-10', phMax: '10' },
                { label: 'Change from SMA 50 (Intraday)', minK: 'min_dist_sma_50', maxK: 'max_dist_sma_50', suf: '%', phMin: '-20', phMax: '20' },
                { label: 'Change from SMA 200 (Intraday)', minK: 'min_dist_sma_200', maxK: 'max_dist_sma_200', suf: '%', phMin: '-50', phMax: '50' },
              ]
            },
            // ═══════════════════════════════════════════════════════════
            // SMA CROSS (INTRADAY)
            // ═══════════════════════════════════════════════════════════
            {
              id: 'smacross', group: '8 vs. 20 Period SMA', filters: [
                { label: '8 vs. 20 Period SMA (2m)', minK: 'min_sma_8_vs_20_2m', maxK: 'max_sma_8_vs_20_2m', suf: '%', phMin: '-5', phMax: '5' },
                { label: '8 vs. 20 Period SMA (5m)', minK: 'min_sma_8_vs_20_5m', maxK: 'max_sma_8_vs_20_5m', suf: '%', phMin: '-5', phMax: '5' },
                { label: '8 vs. 20 Period SMA (15m)', minK: 'min_sma_8_vs_20_15m', maxK: 'max_sma_8_vs_20_15m', suf: '%', phMin: '-5', phMax: '5' },
                { label: '8 vs. 20 Period SMA (60m)', minK: 'min_sma_8_vs_20_60m', maxK: 'max_sma_8_vs_20_60m', suf: '%', phMin: '-5', phMax: '5' },
              ]
            },
            {
              id: 'smacross20v200', group: '20 vs. 200 Period SMA', filters: [
                { label: '20 vs. 200 Period SMA (2m)', minK: 'min_sma_20_vs_200_2m', maxK: 'max_sma_20_vs_200_2m', suf: '%', phMin: '-5', phMax: '5' },
                { label: '20 vs. 200 Period SMA (5m)', minK: 'min_sma_20_vs_200_5m', maxK: 'max_sma_20_vs_200_5m', suf: '%', phMin: '-5', phMax: '5' },
                { label: '20 vs. 200 Period SMA (15m)', minK: 'min_sma_20_vs_200_15m', maxK: 'max_sma_20_vs_200_15m', suf: '%', phMin: '-5', phMax: '5' },
                { label: '20 vs. 200 Period SMA (60m)', minK: 'min_sma_20_vs_200_60m', maxK: 'max_sma_20_vs_200_60m', suf: '%', phMin: '-5', phMax: '5' },
              ]
            },
            // ═══════════════════════════════════════════════════════════
            // DAILY INDICATORS & SMA
            // ═══════════════════════════════════════════════════════════
            {
              id: 'daily', group: 'Daily SMA', filters: [
                { label: '5 Day SMA', minK: 'min_daily_sma_5', maxK: 'max_daily_sma_5', suf: '$', phMin: '', phMax: '' },
                { label: '8 Day SMA', minK: 'min_daily_sma_8', maxK: 'max_daily_sma_8', suf: '$', phMin: '', phMax: '' },
                { label: '10 Day SMA', minK: 'min_daily_sma_10', maxK: 'max_daily_sma_10', suf: '$', phMin: '', phMax: '' },
                { label: '20 Day SMA', minK: 'min_daily_sma_20', maxK: 'max_daily_sma_20', suf: '$', phMin: '', phMax: '' },
                { label: '50 Day SMA', minK: 'min_daily_sma_50', maxK: 'max_daily_sma_50', suf: '$', phMin: '', phMax: '' },
                { label: '200 Day SMA', minK: 'min_daily_sma_200', maxK: 'max_daily_sma_200', suf: '$', phMin: '', phMax: '' },
              ]
            },
            {
              id: 'dailysmapct', group: 'Change from Daily SMA %', filters: [
                { label: 'Change from 5 Day SMA %', minK: 'min_dist_daily_sma_5', maxK: 'max_dist_daily_sma_5', suf: '%', phMin: '-5', phMax: '5' },
                { label: 'Change from 8 Day SMA %', minK: 'min_dist_daily_sma_8', maxK: 'max_dist_daily_sma_8', suf: '%', phMin: '-5', phMax: '5' },
                { label: 'Change from 10 Day SMA %', minK: 'min_dist_daily_sma_10', maxK: 'max_dist_daily_sma_10', suf: '%', phMin: '-5', phMax: '5' },
                { label: 'Change from 20 Day SMA %', minK: 'min_dist_daily_sma_20', maxK: 'max_dist_daily_sma_20', suf: '%', phMin: '-10', phMax: '10' },
                { label: 'Change from 50 Day SMA %', minK: 'min_dist_daily_sma_50', maxK: 'max_dist_daily_sma_50', suf: '%', phMin: '-20', phMax: '20' },
                { label: 'Change from 200 Day SMA %', minK: 'min_dist_daily_sma_200', maxK: 'max_dist_daily_sma_200', suf: '%', phMin: '-50', phMax: '50' },
              ]
            },
            {
              id: 'dailysmadollars', group: 'Change from Daily SMA $', filters: [
                { label: 'Change from 5 Day SMA $', minK: 'min_dist_daily_sma_5_dollars', maxK: 'max_dist_daily_sma_5_dollars', suf: '$', phMin: '-2', phMax: '2' },
                { label: 'Change from 8 Day SMA $', minK: 'min_dist_daily_sma_8_dollars', maxK: 'max_dist_daily_sma_8_dollars', suf: '$', phMin: '-3', phMax: '3' },
                { label: 'Change from 10 Day SMA $', minK: 'min_dist_daily_sma_10_dollars', maxK: 'max_dist_daily_sma_10_dollars', suf: '$', phMin: '-5', phMax: '5' },
                { label: 'Change from 20 Day SMA $', minK: 'min_dist_daily_sma_20_dollars', maxK: 'max_dist_daily_sma_20_dollars', suf: '$', phMin: '-10', phMax: '10' },
                { label: 'Change from 50 Day SMA $', minK: 'min_dist_daily_sma_50_dollars', maxK: 'max_dist_daily_sma_50_dollars', suf: '$', phMin: '-20', phMax: '20' },
                { label: 'Change from 200 Day SMA $', minK: 'min_dist_daily_sma_200_dollars', maxK: 'max_dist_daily_sma_200_dollars', suf: '$', phMin: '-50', phMax: '50' },
              ]
            },
            {
              id: 'dailyextra', group: 'Daily Indicators', filters: [
                { label: 'Daily RSI', minK: 'min_daily_rsi', maxK: 'max_daily_rsi', suf: '', phMin: '20', phMax: '80' },
                { label: 'Average Directional Index (Daily)', minK: 'min_daily_adx_14', maxK: 'max_daily_adx_14', suf: '', phMin: '20', phMax: '50' },
                { label: 'Directional Indicator (+DI - -DI)', minK: 'min_plus_di_minus_di', maxK: 'max_plus_di_minus_di', suf: '', phMin: '-30', phMax: '30' },
                { label: '52 Week High', minK: 'min_high_52w', maxK: 'max_high_52w', suf: '$', phMin: '', phMax: '' },
                { label: '52 Week Low', minK: 'min_low_52w', maxK: 'max_low_52w', suf: '$', phMin: '', phMax: '' },
                { label: 'From 52 Week High %', minK: 'min_from_52w_high', maxK: 'max_from_52w_high', suf: '%', phMin: '-80', phMax: '0' },
                { label: 'From 52 Week Low %', minK: 'min_from_52w_low', maxK: 'max_from_52w_low', suf: '%', phMin: '0', phMax: '500' },
              ]
            },
            // ═══════════════════════════════════════════════════════════
            // CONSOLIDATION / RANGE CONTRACTION / LINEAR REGRESSION
            // ═══════════════════════════════════════════════════════════
            {
              id: 'consolidation', group: 'Consolidation & Regression', filters: [
                { label: 'Consolidation Days', minK: 'min_consolidation_days', maxK: 'max_consolidation_days', suf: '', phMin: '2', phMax: '20' },
                { label: 'Position in Consolidation', minK: 'min_pos_in_consolidation', maxK: 'max_pos_in_consolidation', suf: '%', phMin: '0', phMax: '100' },
                { label: 'Range Contraction', minK: 'min_range_contraction', maxK: 'max_range_contraction', suf: '', phMin: '0.2', phMax: '1' },
                { label: 'Linear Regression Divergence', minK: 'min_lr_divergence_130', maxK: 'max_lr_divergence_130', suf: '%', phMin: '-10', phMax: '10' },
                { label: 'Change Previous Day %', minK: 'min_change_prev_day_pct', maxK: 'max_change_prev_day_pct', suf: '%', phMin: '-10', phMax: '10' },
              ]
            },
            // ═══════════════════════════════════════════════════════════
            // TIME OF DAY (minutes since 9:30 ET market open)
            // ═══════════════════════════════════════════════════════════
            {
              id: 'tod', group: 'Time of Day', filters: [
                { label: 'Minutes Since Open', minK: 'min_minutes_since_open', maxK: 'max_minutes_since_open', suf: 'min', phMin: '0', phMax: '390' },
              ]
            },
            // ═══════════════════════════════════════════════════════════
            // FUNDAMENTALS
            // ═══════════════════════════════════════════════════════════
            {
              id: 'fund', group: 'Fundamentals', filters: [
                { label: 'Market Cap', minK: 'min_market_cap', maxK: 'max_market_cap', suf: '$', units: ['K', 'M', 'B'], defU: 'M', phMin: '50', phMax: '10' },
                { label: 'Float', minK: 'min_float_shares', maxK: 'max_float_shares', suf: '', units: ['K', 'M', 'B'], defU: 'M', phMin: '1', phMax: '100' },
                { label: 'Shares Outstanding', minK: 'min_shares_outstanding', maxK: 'max_shares_outstanding', suf: '', units: ['K', 'M', 'B'], defU: 'M', phMin: '1', phMax: '500' },
              ]
            },
            // ═══════════════════════════════════════════════════════════
            // PRINTS / TRADES
            // ═══════════════════════════════════════════════════════════
            {
              id: 'trades', group: 'Prints / Trades', filters: [
                { label: 'Average Number of Prints', minK: 'min_trades_today', maxK: 'max_trades_today', suf: '', units: ['', 'K'], defU: '', phMin: '100', phMax: '10000' },
                { label: 'Trades Z-Score', minK: 'min_trades_z_score', maxK: 'max_trades_z_score', suf: '', phMin: '1', phMax: '5' },
              ]
            },
          ] as const;

          type FDef = (typeof FG)[number]['filters'][number];
          const hasUnits = (f: FDef): f is FDef & { units: readonly string[]; defU: string } => 'units' in f;
          const q = filterSearch.trim().toLowerCase();
          const visibleGroups = q
            ? FG.map(g => ({ ...g, filters: g.filters.filter(f => f.label.toLowerCase().includes(q)) })).filter(g => g.filters.length > 0)
            : FG;

          return (
            <div className="h-full flex flex-col">
              <div className="flex-shrink-0 px-2 pt-1.5 pb-1 border-b border-border flex items-center gap-2">
                <input type="text" value={filterSearch} onChange={(e) => setFilterSearch(e.target.value)}
                  placeholder="Search filters..."
                  className="flex-1 px-1.5 py-0.5 text-[11px] border border-border rounded focus:outline-none focus:ring-1 focus:ring-primary bg-surface" />
                <span className="text-[10px] text-muted-fg tabular-nums">{activeFilterCount}</span>
                {activeFilterCount > 0 && (
                  <button onClick={() => { setFilters({}); setFilterUnits({}); }} className="text-[10px] text-muted-fg hover:text-blue-600">clear</button>
                )}
              </div>
              <div className="flex-1 overflow-y-auto">
                {visibleGroups.map(g => {
                  const exp = expandedFilterGroups.has(g.id) || !!q;
                  const activeInGroup = g.filters.filter(f => filters[f.minK] !== undefined || filters[f.maxK] !== undefined).length;
                  return (
                    <div key={g.id}>
                      <button onClick={() => toggleFilterGroup(g.id)}
                        className="w-full flex items-center gap-1 px-2 py-[3px] text-left hover:bg-surface-hover transition-colors border-b border-border-subtle">
                        <span className="text-[9px] text-muted-fg/50 w-3">{exp ? '\u25BC' : '\u25B6'}</span>
                        <span className="text-[11px] font-medium text-foreground/80 flex-1">{g.group}</span>
                        {activeInGroup > 0 && <span className="text-[9px] text-primary font-semibold tabular-nums">{activeInGroup}</span>}
                      </button>
                      {exp && (
                        <div className="px-2 py-1 space-y-[3px]">
                          {g.filters.map((f) => {
                            const wu = hasUnits(f);
                            const uid = f.label;
                            const curUnit = wu ? getUnit(uid, f.defU) : '';
                            const m = wu ? (UNIT_MUL[curUnit] || 1) : 1;
                            const toDisp = (raw: number | undefined) => raw !== undefined ? raw / m : undefined;
                            const toRaw = (v: number | undefined) => v !== undefined ? v * m : undefined;
                            return (
                              <div key={f.label} className="flex items-center gap-1">
                                <span className="text-[11px] text-foreground/70 w-[90px] flex-shrink-0">{f.label}</span>
                                <FmtNum
                                  value={toDisp(filters[f.minK] as number | undefined)}
                                  onChange={v => setFilter(f.minK, toRaw(v))}
                                  placeholder={f.phMin}
                                  className="w-[72px] px-1.5 py-[3px] text-[11px] font-mono border border-border rounded focus:outline-none focus:ring-1 focus:ring-primary bg-[var(--color-input-bg)] text-foreground text-right tabular-nums" />
                                <span className="text-muted-fg/50 text-[8px]">-</span>
                                <FmtNum
                                  value={toDisp(filters[f.maxK] as number | undefined)}
                                  onChange={v => setFilter(f.maxK, toRaw(v))}
                                  placeholder={f.phMax}
                                  className="w-[72px] px-1.5 py-[3px] text-[11px] font-mono border border-border rounded focus:outline-none focus:ring-1 focus:ring-primary bg-[var(--color-input-bg)] text-foreground text-right tabular-nums" />
                                {wu ? (
                                  <select value={curUnit} onChange={e => setUnitFor(uid, e.target.value)}
                                    className="w-8 py-[1px] text-[9px] text-muted-fg border border-border rounded bg-[var(--color-input-bg)] focus:outline-none focus:ring-1 focus:ring-primary cursor-pointer appearance-none text-center">
                                    {f.units.map(u => <option key={u} value={u}>{u || 'sh'}</option>)}
                                  </select>
                                ) : (
                                  f.suf ? <span className="text-[9px] text-muted-fg/50 w-3 text-center">{f.suf}</span> : <span className="w-3" />
                                )}
                              </div>
                            );
                          })}
                        </div>
                      )}
                    </div>
                  );
                })}
                {/* String filters (not min/max) */}
                <div>
                  <button onClick={() => toggleFilterGroup('strings')}
                    className="w-full flex items-center gap-1 px-2 py-[3px] text-left hover:bg-surface-hover/80 transition-colors border-b border-border-subtle/80">
                    <span className="text-[9px] text-muted-fg/50 w-3">{expandedFilterGroups.has('strings') ? '\u25BC' : '\u25B6'}</span>
                    <span className="text-[11px] font-medium text-foreground/80 flex-1">Classification</span>
                    {(filters.security_type || filters.sector || filters.industry) && <span className="text-[9px] text-blue-600 dark:text-blue-400 font-semibold">active</span>}
                  </button>
                  {expandedFilterGroups.has('strings') && (
                    <div className="px-2 py-1 space-y-[3px]">
                      <div className="flex items-center gap-1">
                        <span className="text-[11px] text-foreground/70 w-[90px] flex-shrink-0">Type</span>
                        <select value={(filters.security_type as string) || ''} onChange={e => setFilter('security_type', e.target.value || undefined)}
                          className="flex-1 px-1.5 py-[2px] text-[10px] border border-border rounded focus:outline-none focus:ring-1 focus:ring-primary bg-[var(--color-input-bg)]">
                          <option value="">All Types</option>
                          {SECURITY_TYPES.map(st => (
                            <option key={st.value} value={st.value}>{st.label}</option>
                          ))}
                        </select>
                      </div>
                      <div className="flex items-center gap-1">
                        <span className="text-[11px] text-foreground/70 w-[90px] flex-shrink-0">Sector</span>
                        <select value={(filters.sector as string) || ''} onChange={e => setFilter('sector', e.target.value || undefined)}
                          className="flex-1 px-1.5 py-[2px] text-[10px] border border-border rounded focus:outline-none focus:ring-1 focus:ring-primary bg-[var(--color-input-bg)]">
                          <option value="">All Sectors</option>
                          {SECTORS.map(s => (
                            <option key={s.value} value={s.value}>{s.label}</option>
                          ))}
                        </select>
                      </div>
                      <div className="flex items-center gap-1">
                        <span className="text-[11px] text-foreground/70 w-[90px] flex-shrink-0">Industry</span>
                        <select value={(filters.industry as string) || ''} onChange={e => setFilter('industry', e.target.value || undefined)}
                          className="flex-1 px-1.5 py-[2px] text-[10px] border border-border rounded focus:outline-none focus:ring-1 focus:ring-primary bg-[var(--color-input-bg)]">
                          <option value="">All Industries</option>
                          {INDUSTRIES.map(i => (
                            <option key={i.value} value={i.value}>{i.label}</option>
                          ))}
                        </select>
                      </div>
                    </div>
                  )}
                </div>

                {/* Dilution Risk filters - collapsible like the rest */}
                {(() => {
                  const dilutionFields = [
                    { label: 'Overall Risk',     minK: 'min_dilution_overall_risk_score',    maxK: 'max_dilution_overall_risk_score' },
                    { label: 'Offering Ability', minK: 'min_dilution_offering_ability_score', maxK: 'max_dilution_offering_ability_score' },
                    { label: 'Overhead Supply',  minK: 'min_dilution_overhead_supply_score',  maxK: 'max_dilution_overhead_supply_score' },
                    { label: 'Historical',       minK: 'min_dilution_historical_score',       maxK: 'max_dilution_historical_score' },
                    { label: 'Cash Need',        minK: 'min_dilution_cash_need_score',        maxK: 'max_dilution_cash_need_score' },
                  ] as { label: string; minK: string; maxK: string }[];
                  const visibleDilutionFields = q
                    ? dilutionFields.filter(f => f.label.toLowerCase().includes(q))
                    : dilutionFields;
                  if (q && visibleDilutionFields.length === 0) return null;
                  const activeDilution = dilutionFields.filter(f => filters[f.minK] !== undefined || filters[f.maxK] !== undefined).length;
                  const expDilution = expandedFilterGroups.has('dilution') || !!q;
                  return (
                    <div>
                      <button onClick={() => toggleFilterGroup('dilution')}
                        className="w-full flex items-center gap-1 px-2 py-[3px] text-left hover:bg-surface-hover transition-colors border-b border-border-subtle">
                        <span className="text-[9px] text-muted-fg/50 w-3">{expDilution ? '\u25BC' : '\u25B6'}</span>
                        <span className="text-[11px] font-medium text-foreground/80 flex-1">Dilution Risk</span>
                        {activeDilution > 0 && <span className="text-[9px] text-primary font-semibold tabular-nums">{activeDilution}</span>}
                      </button>
                      {expDilution && (
                        <div className="px-2 py-1 space-y-[3px]">
                          <p className="text-[9px] text-muted-fg/50 pb-0.5">1=Low · 2=Medium · 3=High</p>
                          {visibleDilutionFields.map(({ label, minK, maxK }) => (
                            <div key={minK} className="flex items-center gap-1">
                              <span className="text-[11px] text-foreground/70 w-[90px] flex-shrink-0">{label}</span>
                              <select
                                value={filters[minK] !== undefined ? String(filters[minK]) : ''}
                                onChange={e => setFilter(minK, e.target.value ? Number(e.target.value) : undefined)}
                                className="flex-1 px-1.5 py-[2px] text-[10px] border border-border rounded focus:outline-none focus:ring-1 focus:ring-primary bg-[var(--color-input-bg)]"
                              >
                                <option value="">Any</option>
                                <option value="1">Low</option>
                                <option value="2">Medium</option>
                                <option value="3">High</option>
                              </select>
                              <span className="text-[9px] text-muted-fg/50 w-2 text-center">-</span>
                              <select
                                value={filters[maxK] !== undefined ? String(filters[maxK]) : ''}
                                onChange={e => setFilter(maxK, e.target.value ? Number(e.target.value) : undefined)}
                                className="flex-1 px-1.5 py-[2px] text-[10px] border border-border rounded focus:outline-none focus:ring-1 focus:ring-primary bg-[var(--color-input-bg)]"
                              >
                                <option value="">Any</option>
                                <option value="1">Low</option>
                                <option value="2">Medium</option>
                                <option value="3">High</option>
                              </select>
                            </div>
                          ))}
                        </div>
                      )}
                    </div>
                  );
                })()}
              </div>

            </div>
          );
        })()}

        {/* ====== SYMBOLS TAB ====== */}
        {activeTab === 'symbols' && (
          <div className="h-full p-3 space-y-3">
            <div>
              <label className="block text-[10px] font-semibold text-muted-fg uppercase tracking-wide mb-1">Include only</label>
              <textarea value={symbolsInclude} onChange={(e) => setSymbolsInclude(e.target.value)}
                placeholder="AAPL, TSLA, NVDA..."
                className="w-full h-16 px-2 py-1 text-xs font-mono border border-border rounded resize-none focus:outline-none focus:ring-1 focus:ring-primary bg-surface" />
              <p className="text-[10px] text-muted-fg">Empty = all symbols</p>
            </div>
            <div>
              <label className="block text-[10px] font-semibold text-muted-fg uppercase tracking-wide mb-1">Exclude</label>
              <textarea value={symbolsExclude} onChange={(e) => setSymbolsExclude(e.target.value)}
                placeholder="SPY, QQQ, IWM..."
                className="w-full h-16 px-2 py-1 text-xs font-mono border border-border rounded resize-none focus:outline-none focus:ring-1 focus:ring-primary bg-surface" />
            </div>
          </div>
        )}

        {/* ====== SUMMARY TAB ====== */}
        {activeTab === 'summary' && builderMode === 'strategy' && (
          <div className="h-full flex flex-col">
            <div className="flex-1 overflow-y-auto p-3 space-y-2">
              <div>
                <label className="block text-[10px] font-semibold text-muted-fg uppercase tracking-wide mb-1">Strategy Name</label>
                <input type="text" value={strategyName} onChange={(e) => setStrategyName(e.target.value)}
                  placeholder="My Strategy..."
                  className="w-full px-2 py-1 text-xs border border-border rounded focus:outline-none focus:ring-1 focus:ring-primary bg-surface" />
              </div>
              <div>
                <label className="block text-[10px] font-semibold text-muted-fg uppercase tracking-wide mb-1">Category</label>
                <select value={saveCategory} onChange={e => setSaveCategory(e.target.value)}
                  className="w-full px-2 py-1 text-xs border border-border rounded bg-surface text-foreground/80 focus:outline-none focus:ring-1 focus:ring-primary">
                  <option value="custom">Custom</option>
                  <option value="bullish">Bullish</option>
                  <option value="bearish">Bearish</option>
                  <option value="neutral">Neutral</option>
                </select>
              </div>
              <div className="py-1 border-t border-border-subtle">
                <div className="text-[10px] font-semibold text-muted-fg uppercase tracking-wide mb-1">Alerts ({selectedAlerts.size})</div>
                {selectedAlerts.size === 0
                  ? <span className="text-[10px] text-muted-fg/50">none selected</span>
                  : <div className="flex flex-wrap gap-1">
                    {Array.from(selectedAlerts).map(et => (
                      <span key={et} className="px-1.5 py-0.5 bg-primary/10 border border-border rounded text-[10px] text-primary">{alertTypeLabel(et)}</span>
                    ))}
                  </div>
                }
              </div>
              <div className="py-1 border-t border-border-subtle">
                <div className="text-[10px] font-semibold text-muted-fg uppercase tracking-wide mb-1">Filters ({activeFilterCount})</div>
                {activeFilterCount === 0
                  ? <span className="text-[10px] text-muted-fg/50">none</span>
                  : <div className="flex flex-wrap gap-1">
                    {filtersToDisplay(filters).map(f => (
                      <span key={f} className="px-1.5 py-0.5 bg-surface-hover border border-border rounded text-[10px] font-mono text-foreground/80">{f}</span>
                    ))}
                  </div>
                }
              </div>
              {(symbolsInclude.trim() || symbolsExclude.trim()) && (
                <div className="py-1 border-t border-border-subtle">
                  <div className="text-[10px] font-semibold text-muted-fg uppercase tracking-wide mb-1">Symbols</div>
                  {symbolsInclude.trim() && <div className="text-[10px] text-foreground/80 font-mono">+ {symbolsInclude.trim()}</div>}
                  {symbolsExclude.trim() && <div className="text-[10px] text-foreground/80 font-mono">- {symbolsExclude.trim()}</div>}
                </div>
              )}
            </div>
            {/* Strategy action buttons */}
            <div className="flex-shrink-0 p-2 border-t border-border bg-surface-hover space-y-1.5">
              {loadedStrategyId && !isDirty ? (
                <button onClick={handleOpenDirect} disabled={selectedAlerts.size === 0}
                  className={`w-full py-1.5 text-xs rounded font-semibold transition-colors ${selectedAlerts.size > 0 ? 'bg-primary text-white hover:bg-primary-hover' : 'bg-muted text-muted-fg cursor-not-allowed'}`}>
                  Open
                </button>
              ) : loadedStrategyId && isDirty ? (
                <>
                  <button onClick={handleUpdate} disabled={saving || selectedAlerts.size === 0}
                    className={`w-full py-1.5 text-xs rounded font-semibold transition-colors ${!saving && selectedAlerts.size > 0 ? 'bg-blue-600 text-white hover:bg-blue-700' : 'bg-muted text-muted-fg cursor-not-allowed'}`}>
                    {saving ? 'Saving...' : 'Update & Open'}
                  </button>
                  <div className="flex gap-1.5">
                    <button onClick={handleCreate} disabled={!canCreate || saving}
                      className="flex-1 py-1 text-xs text-muted-fg border border-border rounded hover:bg-surface-hover disabled:opacity-40 transition-colors">Save as new</button>
                    <button onClick={handleOpenDirect} disabled={selectedAlerts.size === 0}
                      className="flex-1 py-1 text-xs text-muted-fg border border-border rounded hover:bg-surface-hover disabled:opacity-40 transition-colors">Open only</button>
                  </div>
                </>
              ) : (
                <>
                  <button onClick={handleCreate} disabled={!canCreate || saving}
                    className={`w-full py-1.5 text-xs rounded font-semibold transition-colors ${canCreate && !saving ? 'bg-blue-600 text-white hover:bg-blue-700' : 'bg-muted text-muted-fg cursor-not-allowed'}`}>
                    {saving ? 'Saving...' : 'Save & Open'}
                  </button>
                  <button onClick={handleOpenDirect} disabled={selectedAlerts.size === 0}
                    className="w-full py-1 text-xs text-muted-fg border border-border rounded hover:bg-surface-hover disabled:opacity-40 transition-colors">
                    Open without saving
                  </button>
                </>
              )}
              {onBacktestStrategy && selectedAlerts.size > 0 && (
                <button onClick={() => onBacktestStrategy({
                  eventTypes: Array.from(selectedAlerts),
                  filters: { ...filters },
                  name: strategyName.trim() || 'Strategy Backtest',
                })}
                  className="w-full py-1 text-xs text-amber-700 bg-amber-500/10 border border-amber-200 rounded hover:bg-amber-500/15 font-medium transition-colors">
                  Backtest Strategy
                </button>
              )}
              {selectedAlerts.size === 0 && (
                <p className="text-[10px] text-muted-fg text-center">Select alerts first</p>
              )}
            </div>
          </div>
        )}

        {/* ====== SUMMARY TAB — TOP LIST MODE ====== */}
        {activeTab === 'summary' && builderMode === 'toplist' && (
          <div className="h-full flex flex-col">
            <div className="flex-1 overflow-y-auto p-3 space-y-2">
              <div>
                <label className="block text-[10px] font-semibold text-muted-fg uppercase tracking-wide mb-1">Top List Name</label>
                <input type="text" value={strategyName} onChange={(e) => setStrategyName(e.target.value)}
                  placeholder="My Top List..."
                  className="w-full px-2 py-1 text-xs border border-border rounded focus:outline-none focus:ring-1 focus:ring-emerald-500 bg-surface" />
              </div>

              {/* Mode indicator */}
              <div className="py-1 border-t border-border-subtle">
                <div className="flex items-center gap-2 mb-2">
                  <span className="px-2 py-0.5 bg-emerald-500/10 border border-emerald-500/30 rounded text-[10px] font-semibold text-emerald-600 dark:text-emerald-400">
                    Scanner / Top List
                  </span>
                  <span className="text-[10px] text-muted-fg">Real-time ticker list updated every scan cycle</span>
                </div>
              </div>

              {/* Filters summary */}
              <div className="py-1 border-t border-border-subtle">
                <div className="text-[10px] font-semibold text-muted-fg uppercase tracking-wide mb-1">Filters ({activeFilterCount})</div>
                {activeFilterCount === 0
                  ? <span className="text-[10px] text-amber-500">Add at least 1 filter</span>
                  : <div className="flex flex-wrap gap-1">
                    {filtersToDisplay(filters).map(f => (
                      <span key={f} className="px-1.5 py-0.5 bg-surface-hover border border-border rounded text-[10px] font-mono text-foreground/80">{f}</span>
                    ))}
                  </div>
                }
              </div>

              {/* Symbols summary */}
              {(symbolsInclude.trim() || symbolsExclude.trim()) && (
                <div className="py-1 border-t border-border-subtle">
                  <div className="text-[10px] font-semibold text-muted-fg uppercase tracking-wide mb-1">Symbols</div>
                  {symbolsInclude.trim() && <div className="text-[10px] text-foreground/80 font-mono">+ {symbolsInclude.trim()}</div>}
                  {symbolsExclude.trim() && <div className="text-[10px] text-foreground/80 font-mono">- {symbolsExclude.trim()}</div>}
                </div>
              )}
            </div>

            {/* Top List action buttons — 3 states */}
            <div className="flex-shrink-0 p-2 border-t border-border bg-surface-hover space-y-1.5">
              {loadedScanId && !isScanDirty ? (
                /* Saved scan, no changes → just Open */
                <button onClick={handleOpenScanDirect}
                  className="w-full py-1.5 text-xs rounded font-semibold transition-colors bg-emerald-600 text-white hover:bg-emerald-700">
                  Open Scanner
                </button>
              ) : loadedScanId && isScanDirty ? (
                /* Saved scan, modified → Update or Save as new */
                <>
                  <button onClick={handleUpdateTopList} disabled={!canCreate || saving}
                    className={`w-full py-1.5 text-xs rounded font-semibold transition-colors ${canCreate && !saving ? 'bg-emerald-600 text-white hover:bg-emerald-700' : 'bg-muted text-muted-fg cursor-not-allowed'}`}>
                    {saving ? 'Saving...' : 'Update & Open Scanner'}
                  </button>
                  <div className="flex gap-1.5">
                    <button onClick={handleCreateTopList} disabled={!canCreate || saving}
                      className="flex-1 py-1 text-xs text-muted-fg border border-border rounded hover:bg-surface-hover disabled:opacity-40 transition-colors">
                      Save as new
                    </button>
                    <button onClick={handleOpenScanDirect}
                      className="flex-1 py-1 text-xs text-muted-fg border border-border rounded hover:bg-surface-hover transition-colors">
                      Open only
                    </button>
                  </div>
                </>
              ) : (
                /* New / built-in top list → Save & Open */
                <button onClick={handleCreateTopList} disabled={!canCreate || saving}
                  className={`w-full py-1.5 text-xs rounded font-semibold transition-colors ${canCreate && !saving ? 'bg-emerald-600 text-white hover:bg-emerald-700' : 'bg-muted text-muted-fg cursor-not-allowed'}`}>
                  {saving ? 'Saving...' : 'Save & Open Scanner'}
                </button>
              )}
              {activeFilterCount === 0 && !loadedScanId && (
                <p className="text-[10px] text-muted-fg text-center">Add filters first</p>
              )}
              {!strategyName.trim() && activeFilterCount > 0 && !loadedScanId && (
                <p className="text-[10px] text-muted-fg text-center">Enter a name</p>
              )}
            </div>
          </div>
        )}
      </div>
    </div>
  );
}
