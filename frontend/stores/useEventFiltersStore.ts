/**
 * Zustand Store para Filtros de Eventos
 * 
 * FILTROS PER-CATEGORY: Cada tabla de eventos (categoryId) tiene sus propios filtros.
 * Esto permite tener "EVN High Vol Runners" con RVOL > 2x y "EVN All Events" sin filtros
 * al mismo tiempo en ventanas separadas.
 * 
 * PERSISTENCIA: Se guardan en localStorage y se sincronizan con la BD
 * via useClerkSync (usando el campo savedFilters.eventFilters)
 */

import { create } from 'zustand';
import { persist, createJSONStorage } from 'zustand/middleware';

// ============================================================================
// Types
// ============================================================================

interface EventFilterParameters {
  // Event type filters (which events to show)
  event_types?: string[];

  // Price filters
  min_price?: number;
  max_price?: number;

  // Change % filters
  min_change_percent?: number;
  max_change_percent?: number;

  // RVOL filters
  min_rvol?: number;
  max_rvol?: number;

  // Volume filters
  min_volume?: number;
  max_volume?: number;

  // Market Cap filters
  min_market_cap?: number;
  max_market_cap?: number;

  // Gap % filters
  min_gap_percent?: number;
  max_gap_percent?: number;

  // Change from open filters
  min_change_from_open?: number;
  max_change_from_open?: number;
  min_change_from_open_dollars?: number;
  max_change_from_open_dollars?: number;

  // VWAP filters
  min_vwap?: number;
  max_vwap?: number;

  // ATR % filters
  min_atr_percent?: number;
  max_atr_percent?: number;

  // Time-window change filters
  min_chg_1min?: number;
  max_chg_1min?: number;
  min_chg_1min_dollars?: number;
  max_chg_1min_dollars?: number;
  min_chg_5min?: number;
  max_chg_5min?: number;
  min_chg_5min_dollars?: number;
  max_chg_5min_dollars?: number;
  min_chg_10min?: number;
  max_chg_10min?: number;
  min_chg_10min_dollars?: number;
  max_chg_10min_dollars?: number;
  min_chg_15min?: number;
  max_chg_15min?: number;
  min_chg_15min_dollars?: number;
  max_chg_15min_dollars?: number;
  min_chg_30min?: number;
  max_chg_30min?: number;
  min_chg_30min_dollars?: number;
  max_chg_30min_dollars?: number;

  // Time-window volume filters
  min_vol_1min?: number;
  max_vol_1min?: number;
  min_vol_5min?: number;
  max_vol_5min?: number;
  min_vol_10min?: number;
  max_vol_10min?: number;
  min_vol_15min?: number;
  max_vol_15min?: number;
  min_vol_30min?: number;
  max_vol_30min?: number;

  // Volume window % (Trade Ideas style)
  min_vol_1min_pct?: number;
  max_vol_1min_pct?: number;
  min_vol_5min_pct?: number;
  max_vol_5min_pct?: number;
  min_vol_10min_pct?: number;
  max_vol_10min_pct?: number;
  min_vol_15min_pct?: number;
  max_vol_15min_pct?: number;
  min_vol_30min_pct?: number;
  max_vol_30min_pct?: number;

  // Range window filters (Trade Ideas: Range2..Range120)
  min_range_2min?: number;
  max_range_2min?: number;
  min_range_5min?: number;
  max_range_5min?: number;
  min_range_15min?: number;
  max_range_15min?: number;
  min_range_30min?: number;
  max_range_30min?: number;
  min_range_60min?: number;
  max_range_60min?: number;
  min_range_120min?: number;
  max_range_120min?: number;
  min_range_2min_pct?: number;
  max_range_2min_pct?: number;
  min_range_5min_pct?: number;
  max_range_5min_pct?: number;
  min_range_15min_pct?: number;
  max_range_15min_pct?: number;
  min_range_30min_pct?: number;
  max_range_30min_pct?: number;
  min_range_60min_pct?: number;
  max_range_60min_pct?: number;
  min_range_120min_pct?: number;
  max_range_120min_pct?: number;

  // Change 60 min
  min_chg_60min?: number;
  max_chg_60min?: number;
  min_chg_60min_dollars?: number;
  max_chg_60min_dollars?: number;

  // Float & Shares
  min_float_shares?: number;
  max_float_shares?: number;
  min_shares_outstanding?: number;
  max_shares_outstanding?: number;

  // RSI (intraday 1-min bars)
  min_rsi?: number;
  max_rsi?: number;

  // EMA filters (intraday EMAs from BarEngine)
  min_ema_20?: number;
  max_ema_20?: number;
  min_ema_50?: number;
  max_ema_50?: number;
  // Legacy SMA filter names (backward compat with saved filters)
  min_sma_20?: number;
  max_sma_20?: number;
  min_sma_50?: number;
  max_sma_50?: number;

  // Intraday SMA (from BarEngine 1-min bars)
  min_sma_5?: number;
  max_sma_5?: number;
  min_sma_8?: number;
  max_sma_8?: number;
  min_sma_200?: number;
  max_sma_200?: number;

  // Quote data
  min_bid?: number;
  max_bid?: number;
  min_ask?: number;
  max_ask?: number;
  min_bid_size?: number;
  max_bid_size?: number;
  min_ask_size?: number;
  max_ask_size?: number;
  min_spread?: number;
  max_spread?: number;

  // MACD
  min_macd_line?: number;
  max_macd_line?: number;
  min_macd_hist?: number;
  max_macd_hist?: number;

  // Stochastic
  min_stoch_k?: number;
  max_stoch_k?: number;
  min_stoch_d?: number;
  max_stoch_d?: number;

  // ADX
  min_adx_14?: number;
  max_adx_14?: number;

  // Bollinger Bands (intraday)
  min_bb_upper?: number;
  max_bb_upper?: number;
  min_bb_lower?: number;
  max_bb_lower?: number;

  // Daily indicators (from screener)
  min_daily_sma_5?: number;
  max_daily_sma_5?: number;
  min_daily_sma_8?: number;
  max_daily_sma_8?: number;
  min_daily_sma_10?: number;
  max_daily_sma_10?: number;
  min_daily_sma_20?: number;
  max_daily_sma_20?: number;
  min_daily_sma_50?: number;
  max_daily_sma_50?: number;
  min_daily_sma_200?: number;
  max_daily_sma_200?: number;
  min_daily_rsi?: number;
  max_daily_rsi?: number;
  min_high_52w?: number;
  max_high_52w?: number;
  min_low_52w?: number;
  max_low_52w?: number;

  // Trades anomaly
  min_trades_today?: number;
  max_trades_today?: number;
  min_trades_z_score?: number;
  max_trades_z_score?: number;

  // === NEW: Computed derived fields ===
  // Dollar volume
  min_dollar_volume?: number;
  max_dollar_volume?: number;
  // Today's range
  min_todays_range?: number;
  max_todays_range?: number;
  min_todays_range_pct?: number;
  max_todays_range_pct?: number;
  // Bid/Ask ratio
  min_bid_ask_ratio?: number;
  max_bid_ask_ratio?: number;
  // Float turnover
  min_float_turnover?: number;
  max_float_turnover?: number;
  // Distance from VWAP (%)
  min_dist_from_vwap?: number;
  max_dist_from_vwap?: number;
  // Distance from intraday SMAs (%)
  min_dist_sma_5?: number;
  max_dist_sma_5?: number;
  min_dist_sma_8?: number;
  max_dist_sma_8?: number;
  min_dist_sma_20?: number;
  max_dist_sma_20?: number;
  min_dist_sma_50?: number;
  max_dist_sma_50?: number;
  min_dist_sma_200?: number;
  max_dist_sma_200?: number;
  // Position in range (0-100%)
  min_pos_in_range?: number;
  max_pos_in_range?: number;
  // Below high / Above low ($)
  min_below_high?: number;
  max_below_high?: number;
  min_above_low?: number;
  max_above_low?: number;
  // Position of open (0-100%)
  min_pos_of_open?: number;
  max_pos_of_open?: number;
  // Previous day volume
  min_prev_day_volume?: number;
  max_prev_day_volume?: number;

  // === NEW: Multi-day changes (%) ===
  min_change_1d?: number;
  max_change_1d?: number;
  min_change_3d?: number;
  max_change_3d?: number;
  min_change_5d?: number;
  max_change_5d?: number;
  min_change_10d?: number;
  max_change_10d?: number;
  min_change_20d?: number;
  max_change_20d?: number;

  // === NEW: Average daily volumes ===
  min_avg_volume_5d?: number;
  max_avg_volume_5d?: number;
  min_avg_volume_10d?: number;
  max_avg_volume_10d?: number;
  min_avg_volume_20d?: number;
  max_avg_volume_20d?: number;

  // === NEW: Distance from daily SMAs (%) ===
  min_dist_daily_sma_20?: number;
  max_dist_daily_sma_20?: number;
  min_dist_daily_sma_50?: number;
  max_dist_daily_sma_50?: number;

  // === NEW: 52w distances (%) ===
  min_from_52w_high?: number;
  max_from_52w_high?: number;
  min_from_52w_low?: number;
  max_from_52w_low?: number;

  // === NEW: Daily ADX / ATR / Bollinger position ===
  min_daily_adx_14?: number;
  max_daily_adx_14?: number;
  min_daily_atr_percent?: number;
  max_daily_atr_percent?: number;
  min_daily_bb_position?: number;
  max_daily_bb_position?: number;

  // String filters (fundamentals)
  security_type?: string;   // CS, ETF, PFD, WARRANT
  sector?: string;
  industry?: string;

  // Symbol filters
  symbols_include?: string[];
  symbols_exclude?: string[];
  watchlist_only?: boolean;

  // === Scanner-aligned filters ===
  // Volume Today %
  min_volume_today_pct?: number;
  max_volume_today_pct?: number;
  // Minute volume
  min_minute_volume?: number;
  max_minute_volume?: number;
  // Volume Yesterday %
  min_volume_yesterday_pct?: number;
  max_volume_yesterday_pct?: number;
  // Price from day high (%)
  min_price_from_high?: number;
  max_price_from_high?: number;
  min_price_from_low?: number;
  max_price_from_low?: number;
  min_price_from_intraday_high?: number;
  max_price_from_intraday_high?: number;
  min_price_from_intraday_low?: number;
  max_price_from_intraday_low?: number;
  // Distance from NBBO (%)
  min_distance_from_nbbo?: number;
  max_distance_from_nbbo?: number;
  // Pre-Market %
  min_premarket_change_percent?: number;
  max_premarket_change_percent?: number;
  // Post-Market %
  min_postmarket_change_percent?: number;
  max_postmarket_change_percent?: number;
  // Post-Market Volume
  min_postmarket_volume?: number;
  max_postmarket_volume?: number;
  // Avg Volume 3M
  min_avg_volume_3m?: number;
  max_avg_volume_3m?: number;
  // ATR ($)
  min_atr?: number;
  max_atr?: number;
  // Pivot Points (distance %)
  min_dist_pivot?: number;
  max_dist_pivot?: number;
  min_dist_pivot_r1?: number;
  max_dist_pivot_r1?: number;
  min_dist_pivot_s1?: number;
  max_dist_pivot_s1?: number;
  min_dist_pivot_r2?: number;
  max_dist_pivot_r2?: number;
  min_dist_pivot_s2?: number;
  max_dist_pivot_s2?: number;
  // Consecutive Candles
  min_consecutive_candles?: number;
  max_consecutive_candles?: number;
  min_consecutive_candles_2m?: number;
  max_consecutive_candles_2m?: number;
  min_consecutive_candles_5m?: number;
  max_consecutive_candles_5m?: number;
  min_consecutive_candles_10m?: number;
  max_consecutive_candles_10m?: number;
  min_consecutive_candles_15m?: number;
  max_consecutive_candles_15m?: number;
  min_consecutive_candles_30m?: number;
  max_consecutive_candles_30m?: number;
  min_consecutive_candles_60m?: number;
  max_consecutive_candles_60m?: number;
  // Position in TF Range (0-100%)
  min_pos_in_range_5m?: number;
  max_pos_in_range_5m?: number;
  min_pos_in_range_15m?: number;
  max_pos_in_range_15m?: number;
  min_pos_in_range_30m?: number;
  max_pos_in_range_30m?: number;
  min_pos_in_range_60m?: number;
  max_pos_in_range_60m?: number;
  // Multi-TF RSI
  min_rsi_2m?: number;
  max_rsi_2m?: number;
  min_rsi_5m?: number;
  max_rsi_5m?: number;
  min_rsi_15m?: number;
  max_rsi_15m?: number;
  min_rsi_60m?: number;
  max_rsi_60m?: number;
  // Multi-TF Bollinger Position (0-100%)
  min_bb_position_1m?: number;
  max_bb_position_1m?: number;
  min_bb_position_5m?: number;
  max_bb_position_5m?: number;
  min_bb_position_15m?: number;
  max_bb_position_15m?: number;
  min_bb_position_60m?: number;
  max_bb_position_60m?: number;
  // Change 2min / 120min (%)
  min_chg_2min?: number;
  max_chg_2min?: number;
  min_chg_120min?: number;
  max_chg_120min?: number;
  min_chg_2min_dollars?: number;
  max_chg_2min_dollars?: number;
  min_chg_120min_dollars?: number;
  max_chg_120min_dollars?: number;

  // === Extended Trade Ideas parity filters ===
  // Gap $ [GUD]
  min_gap_dollars?: number;
  max_gap_dollars?: number;
  // Gap Ratio [GUR]
  min_gap_ratio?: number;
  max_gap_ratio?: number;
  // Change from Close $ [FCD]
  min_change_from_close_dollars?: number;
  max_change_from_close_dollars?: number;
  // Change from Close Ratio [FCR]
  min_change_from_close_ratio?: number;
  max_change_from_close_ratio?: number;
  // Change from Open Ratio [FOR]
  min_change_from_open_ratio?: number;
  max_change_from_open_ratio?: number;
  // Post-Market Change $ [PostD]
  min_postmarket_change_dollars?: number;
  max_postmarket_change_dollars?: number;
  // Decimal [Dec]
  min_decimal?: number;
  max_decimal?: number;
  // Position in Previous Day Range [RPD]
  min_pos_in_prev_day_range?: number;
  max_pos_in_prev_day_range?: number;
  // Directional Indicator [PDIMDI]
  min_plus_di_minus_di?: number;
  max_plus_di_minus_di?: number;
  // Standard Deviation [BB]
  min_bb_std_dev?: number;
  max_bb_std_dev?: number;
  // Multi-TF SMA distances (%)
  min_dist_sma_5_2m?: number;
  max_dist_sma_5_2m?: number;
  min_dist_sma_5_5m?: number;
  max_dist_sma_5_5m?: number;
  min_dist_sma_5_15m?: number;
  max_dist_sma_5_15m?: number;
  min_dist_sma_8_2m?: number;
  max_dist_sma_8_2m?: number;
  min_dist_sma_8_5m?: number;
  max_dist_sma_8_5m?: number;
  min_dist_sma_8_15m?: number;
  max_dist_sma_8_15m?: number;
  min_dist_sma_8_60m?: number;
  max_dist_sma_8_60m?: number;
  min_dist_sma_20_2m?: number;
  max_dist_sma_20_2m?: number;
  min_dist_sma_20_5m?: number;
  max_dist_sma_20_5m?: number;
  min_dist_sma_20_15m?: number;
  max_dist_sma_20_15m?: number;
  min_dist_sma_20_60m?: number;
  max_dist_sma_20_60m?: number;
  // SMA cross: 8 vs 20 per TF
  min_sma_8_vs_20_2m?: number;
  max_sma_8_vs_20_2m?: number;
  min_sma_8_vs_20_5m?: number;
  max_sma_8_vs_20_5m?: number;
  min_sma_8_vs_20_15m?: number;
  max_sma_8_vs_20_15m?: number;
  min_sma_8_vs_20_60m?: number;
  max_sma_8_vs_20_60m?: number;
  // Distance from Daily SMA 200 (%)
  min_dist_daily_sma_200?: number;
  max_dist_daily_sma_200?: number;
  // Multi-day ranges ($) [Range5D, Range10D, Range20D]
  min_range_5d?: number;
  max_range_5d?: number;
  min_range_10d?: number;
  max_range_10d?: number;
  min_range_20d?: number;
  max_range_20d?: number;
  // Position in multi-day ranges (%) [R5D, R10D, R20D, R52W]
  min_pos_in_5d_range?: number;
  max_pos_in_5d_range?: number;
  min_pos_in_10d_range?: number;
  max_pos_in_10d_range?: number;
  min_pos_in_20d_range?: number;
  max_pos_in_20d_range?: number;
  min_pos_in_52w_range?: number;
  max_pos_in_52w_range?: number;
  // Multi-day ranges (%) — ATR-normalized [Range5DP, Range10DP, Range20DP]
  min_range_5d_pct?: number;
  max_range_5d_pct?: number;
  min_range_10d_pct?: number;
  max_range_10d_pct?: number;
  min_range_20d_pct?: number;
  max_range_20d_pct?: number;
  // Change 5/10/20 Days ($) [U5DD, U10DD, U20DD]
  min_change_5d_dollars?: number;
  max_change_5d_dollars?: number;
  min_change_10d_dollars?: number;
  max_change_10d_dollars?: number;
  min_change_20d_dollars?: number;
  max_change_20d_dollars?: number;
  // Change from Open Weighted [FOW]
  min_change_from_open_weighted?: number;
  max_change_from_open_weighted?: number;
  // Distance from Daily SMA 5/8/10 ($) [MA5P, MA8P, MA10P]
  min_dist_daily_sma_5_dollars?: number;
  max_dist_daily_sma_5_dollars?: number;
  min_dist_daily_sma_8_dollars?: number;
  max_dist_daily_sma_8_dollars?: number;
  min_dist_daily_sma_10_dollars?: number;
  max_dist_daily_sma_10_dollars?: number;
  // Distance from Daily SMA 20/50/200 ($) [MA20P, MA50P, MA200P]
  min_dist_daily_sma_20_dollars?: number;
  max_dist_daily_sma_20_dollars?: number;
  min_dist_daily_sma_50_dollars?: number;
  max_dist_daily_sma_50_dollars?: number;
  min_dist_daily_sma_200_dollars?: number;
  max_dist_daily_sma_200_dollars?: number;
  // Distance from Daily SMA 5/8/10 (%) [MA5R, MA8R, MA10R]
  min_dist_daily_sma_5?: number;
  max_dist_daily_sma_5?: number;
  min_dist_daily_sma_8?: number;
  max_dist_daily_sma_8?: number;
  min_dist_daily_sma_10?: number;
  max_dist_daily_sma_10?: number;
  // 20 vs 200 SMA cross per TF [2Sma20a200, 5Sma20a200, 15Sma20a200, 60Sma20a200]
  min_sma_20_vs_200_2m?: number;
  max_sma_20_vs_200_2m?: number;
  min_sma_20_vs_200_5m?: number;
  max_sma_20_vs_200_5m?: number;
  min_sma_20_vs_200_15m?: number;
  max_sma_20_vs_200_15m?: number;
  min_sma_20_vs_200_60m?: number;
  max_sma_20_vs_200_60m?: number;
  // Change in 1 Year [UYP/UYD]
  min_change_1y?: number;
  max_change_1y?: number;
  min_change_1y_dollars?: number;
  max_change_1y_dollars?: number;
  // Change Since Jan 1 [UpJan1P/UpJan1D]
  min_change_ytd?: number;
  max_change_ytd?: number;
  min_change_ytd_dollars?: number;
  max_change_ytd_dollars?: number;
  // Yearly Standard Deviation [YSD]
  min_yearly_std_dev?: number;
  max_yearly_std_dev?: number;
  // Consecutive Days Up [Up]
  min_consecutive_days_up?: number;
  max_consecutive_days_up?: number;

  // Change from 10 Period SMA (multi-TF)
  min_dist_sma_10_2m?: number; max_dist_sma_10_2m?: number;
  min_dist_sma_10_5m?: number; max_dist_sma_10_5m?: number;
  min_dist_sma_10_15m?: number; max_dist_sma_10_15m?: number;
  min_dist_sma_10_60m?: number; max_dist_sma_10_60m?: number;
  // Change from 130 Period SMA (15m)
  min_dist_sma_130_15m?: number; max_dist_sma_130_15m?: number;
  // Change from 200 Period SMA (multi-TF)
  min_dist_sma_200_2m?: number; max_dist_sma_200_2m?: number;
  min_dist_sma_200_5m?: number; max_dist_sma_200_5m?: number;
  min_dist_sma_200_15m?: number; max_dist_sma_200_15m?: number;
  min_dist_sma_200_60m?: number; max_dist_sma_200_60m?: number;
  // Change from 5 Period SMA (60m)
  min_dist_sma_5_60m?: number; max_dist_sma_5_60m?: number;
  // Position in Range (3M/6M/9M/2Y/Lifetime)
  min_pos_in_3m_range?: number; max_pos_in_3m_range?: number;
  min_pos_in_6m_range?: number; max_pos_in_6m_range?: number;
  min_pos_in_9m_range?: number; max_pos_in_9m_range?: number;
  min_pos_in_2y_range?: number; max_pos_in_2y_range?: number;
  min_pos_in_lifetime_range?: number; max_pos_in_lifetime_range?: number;
  // Pre-Market
  min_below_premarket_high?: number; max_below_premarket_high?: number;
  min_above_premarket_low?: number; max_above_premarket_low?: number;
  min_pos_in_premarket_range?: number; max_pos_in_premarket_range?: number;
  // Consolidation / Range Contraction / LR
  min_consolidation_days?: number; max_consolidation_days?: number;
  min_pos_in_consolidation?: number; max_pos_in_consolidation?: number;
  min_range_contraction?: number; max_range_contraction?: number;
  min_lr_divergence_130?: number; max_lr_divergence_130?: number;
  // Change Previous Day
  min_change_prev_day_pct?: number; max_change_prev_day_pct?: number;

  // Per-alert custom settings (keys like "aq:running_up", "aq:new_high", etc.)
  [key: `aq:${string}`]: number | undefined;
}

export interface ActiveEventFilters extends EventFilterParameters { }

interface EventFiltersState {
  // Per-category filters (key = categoryId, e.g. "evt_high_vol_runners")
  filtersMap: Record<string, ActiveEventFilters>;

  // Actions (all take categoryId for per-window isolation)
  getFilters: (categoryId: string) => ActiveEventFilters;
  setFilter: <K extends keyof ActiveEventFilters>(categoryId: string, key: K, value: ActiveEventFilters[K]) => void;
  clearFilter: (categoryId: string, key: keyof ActiveEventFilters) => void;
  clearAllFilters: (categoryId: string) => void;
  setAllFilters: (categoryId: string, filters: ActiveEventFilters) => void;
  hasActiveFilters: (categoryId: string) => boolean;

  // Event type specific actions
  toggleEventType: (categoryId: string, eventType: string) => void;
  setEventTypes: (categoryId: string, eventTypes: string[]) => void;
  clearEventTypes: (categoryId: string) => void;
}

// ============================================================================
// Available Event Types — derived from alert-catalog.ts (single source of truth)
// ============================================================================

import { ALL_EVENT_TYPES } from '@/lib/alert-catalog';
export { ALL_EVENT_TYPES };
export type EventType = string;

// ============================================================================
// Helpers
// ============================================================================

function cleanFilters(filters: ActiveEventFilters): ActiveEventFilters {
  const clean: ActiveEventFilters = {};
  for (const [key, value] of Object.entries(filters)) {
    if (value !== null && value !== undefined) {
      (clean as any)[key] = value;
    }
  }
  return clean;
}

function isNotEmpty(filters: ActiveEventFilters): boolean {
  return Object.keys(filters).length > 0;
}

// ============================================================================
// Store con Persistencia (per-category)
// ============================================================================

export const useEventFiltersStore = create<EventFiltersState>()(
  persist(
    (set, get) => ({
      filtersMap: {},

      getFilters: (categoryId) => {
        return get().filtersMap[categoryId] || {};
      },

      setFilter: (categoryId, key, value) => {
        set((state) => {
          const current = { ...(state.filtersMap[categoryId] || {}) };
          if (value === null || value === undefined) {
            delete current[key];
          } else {
            current[key] = value;
          }
          return {
            filtersMap: { ...state.filtersMap, [categoryId]: current },
          };
        });
      },

      clearFilter: (categoryId, key) => {
        set((state) => {
          const current = { ...(state.filtersMap[categoryId] || {}) };
          delete current[key];
          return {
            filtersMap: { ...state.filtersMap, [categoryId]: current },
          };
        });
      },

      clearAllFilters: (categoryId) => {
        set((state) => ({
          filtersMap: { ...state.filtersMap, [categoryId]: {} },
        }));
      },

      setAllFilters: (categoryId, filters) => {
        set((state) => ({
          filtersMap: { ...state.filtersMap, [categoryId]: cleanFilters(filters) },
        }));
      },

      hasActiveFilters: (categoryId) => {
        return isNotEmpty(get().filtersMap[categoryId] || {});
      },

      // Event type specific actions
      toggleEventType: (categoryId, eventType) => {
        set((state) => {
          const current = { ...(state.filtersMap[categoryId] || {}) };
          const types = current.event_types || [];
          let newTypes: string[];

          if (types.includes(eventType)) {
            newTypes = types.filter(t => t !== eventType);
          } else {
            newTypes = [...types, eventType];
          }

          if (newTypes.length === 0) {
            delete current.event_types;
          } else {
            current.event_types = newTypes;
          }

          return {
            filtersMap: { ...state.filtersMap, [categoryId]: current },
          };
        });
      },

      setEventTypes: (categoryId, eventTypes) => {
        set((state) => {
          const current = { ...(state.filtersMap[categoryId] || {}) };
          if (eventTypes.length === 0) {
            delete current.event_types;
          } else {
            current.event_types = eventTypes;
          }
          return {
            filtersMap: { ...state.filtersMap, [categoryId]: current },
          };
        });
      },

      clearEventTypes: (categoryId) => {
        set((state) => {
          const current = { ...(state.filtersMap[categoryId] || {}) };
          delete current.event_types;
          return {
            filtersMap: { ...state.filtersMap, [categoryId]: current },
          };
        });
      },
    }),
    {
      name: 'tradeul-event-filters',
      storage: createJSONStorage(() => localStorage),
      partialize: (state) => ({
        filtersMap: state.filtersMap,
      }),
    }
  )
);
