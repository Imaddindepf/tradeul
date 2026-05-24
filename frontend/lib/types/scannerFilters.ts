/**
 * Scanner Filters Types
 * Tipos para filtros personalizados del scanner por usuario
 * Reutiliza la estructura de FilterParameters del backend
 */

// ============================================================================
// Filter Parameters (mismo formato que backend FilterParameters)
// ============================================================================

export interface FilterParameters {
  // RVOL filters
  min_rvol?: number;
  max_rvol?: number;
  
  // Price filters
  min_price?: number;
  max_price?: number;
  
  // Spread filters (in CENTS 50.00 = $0.50)
  min_spread?: number;
  max_spread?: number;
  
  // Bid/Ask size filters (in shares)
  min_bid_size?: number;
  max_bid_size?: number;
  min_ask_size?: number;
  max_ask_size?: number;
  
  // Distance from Inside Market (NBBO)
  min_distance_from_nbbo?: number;
  max_distance_from_nbbo?: number;
  
  // Volume filters
  min_volume?: number;  // Alias de min_volume_today (compatibilidad con backend)
  min_volume_today?: number;
  min_minute_volume?: number;
  
  // Average Daily Volume filters
  min_avg_volume_5d?: number;
  max_avg_volume_5d?: number;
  min_avg_volume_10d?: number;
  max_avg_volume_10d?: number;
  min_avg_volume_3m?: number;
  max_avg_volume_3m?: number;
  
  // Dollar Volume filter (price × avg_volume_10d)
  min_dollar_volume?: number;
  max_dollar_volume?: number;
  
  // Volume Today/Yesterday % filters (volume as % of avg_volume_10d)
  min_volume_today_pct?: number;
  max_volume_today_pct?: number;
  min_volume_yesterday_pct?: number;
  max_volume_yesterday_pct?: number;
  
  // Volume window filters (volume in last N minutes)
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
  
  // Data freshness filters
  max_data_age_seconds?: number;
  
  // Change filters
  min_change_percent?: number;
  max_change_percent?: number;
  min_change_from_open?: number;
  max_change_from_open?: number;
  min_change_from_open_dollars?: number;
  max_change_from_open_dollars?: number;
  
  // Market cap filters
  min_market_cap?: number;
  max_market_cap?: number;
  
  // Float filters (applies to free_float field)
  min_float?: number;
  max_float?: number;
  
  // Sector/Industry filters
  sectors?: string[];
  industries?: string[];
  exchanges?: string[];
  
  // Advanced filters
  min_price_from_high?: number;
  max_price_from_high?: number;
  min_price_from_low?: number;
  max_price_from_low?: number;
  min_price_from_intraday_high?: number;
  max_price_from_intraday_high?: number;
  min_price_from_intraday_low?: number;
  max_price_from_intraday_low?: number;
  
  // Custom expression (for advanced users - futuro)
  custom_expression?: string;

  // ============================================================================
  // Dilution Risk filters (1=Low, 2=Medium, 3=High; null = no data → excluded)
  // ============================================================================
  min_dilution_overall_risk_score?: 1 | 2 | 3;
  max_dilution_overall_risk_score?: 1 | 2 | 3;
  min_dilution_offering_ability_score?: 1 | 2 | 3;
  max_dilution_offering_ability_score?: 1 | 2 | 3;
  min_dilution_overhead_supply_score?: 1 | 2 | 3;
  max_dilution_overhead_supply_score?: 1 | 2 | 3;
  min_dilution_historical_score?: 1 | 2 | 3;
  max_dilution_historical_score?: 1 | 2 | 3;
  min_dilution_cash_need_score?: 1 | 2 | 3;
  max_dilution_cash_need_score?: 1 | 2 | 3;

  // Time of Day [TOD] — minutes since NYSE market open (9:30 ET)
  min_minutes_since_open?: number;
  max_minutes_since_open?: number;

  // Allow additional fields
  [key: string]: any;
}

// ============================================================================
// User Filter (Response from API)
// ============================================================================

export interface UserFilter {
  id: number;
  userId: string;
  name: string;
  description?: string;
  enabled: boolean;
  filter_type: string;
  parameters: FilterParameters;
  priority: number;
  isShared: boolean;
  isPublic: boolean;
  createdAt: string;
  updatedAt: string;
}

// ============================================================================
// User Filter Create/Update (Request to API)
// ============================================================================

export interface UserFilterCreate {
  name: string;
  description?: string;
  enabled?: boolean;
  filter_type: string;
  parameters: FilterParameters;
  priority?: number;
}

export interface UserFilterUpdate {
  name?: string;
  description?: string;
  enabled?: boolean;
  filter_type?: string;
  parameters?: FilterParameters;
  priority?: number;
}

