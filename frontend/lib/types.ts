// ============================================================================
// MARKET SESSION
// ============================================================================

export type MarketSessionType = 'PRE_MARKET' | 'MARKET_OPEN' | 'POST_MARKET' | 'CLOSED';

export interface MarketSession {
  current_session: MarketSessionType;
  trading_date: string;
  timestamp?: string;
  market_open_time?: string;
  market_close_time?: string;
}

// ============================================================================
// TICKER TYPES
// ============================================================================

export interface Ticker {
  symbol: string;
  rank?: number;

  // Real-time subscription status
  isSubscribedToPolygon?: boolean;  // ✅ Nuevo: indica si está suscrito al WS de Polygon
  lastAggregateTime?: number;       // Timestamp del último aggregate recibido

  // Price data
  price?: number;
  last_price?: number;
  prev_close?: number;
  open?: number;
  high?: number;
  low?: number;
  intraday_high?: number;
  intraday_low?: number;
  bid?: number;
  ask?: number;

  // Change metrics
  change?: number;
  change_percent?: number;
  changePercent?: number;
  gap?: number;
  gap_percent?: number;
  gapPercent?: number;

  // Volume metrics
  volume?: number;
  volume_today?: number;
  prev_volume?: number;    // Previous day volume
  minute_volume?: number;  // Volume in last minute bar
  rvol?: number;
  rvol_slot?: number;
  volume_today_pct?: number;     // Volume today as % of avg 10d
  volume_yesterday_pct?: number; // Volume yesterday as % of avg 10d

  // Volume window metrics (volume in last N minutes)
  vol_1min?: number;
  vol_5min?: number;
  vol_10min?: number;
  vol_15min?: number;
  vol_30min?: number;

  // Price change window metrics (% change in last N minutes - per-second precision)
  chg_1min?: number;
  chg_5min?: number;
  chg_10min?: number;
  chg_15min?: number;
  chg_30min?: number;

  // VWAP
  vwap?: number;           // Volume Weighted Average Price (today)
  price_vs_vwap?: number;  // % distance from VWAP

  // Post-Market metrics (only populated during POST_MARKET session 16:00-20:00 ET)
  postmarket_change_percent?: number;  // % change from regular session close
  postmarket_volume?: number;          // Volume traded in post-market only

  // Trades Anomaly Detection (Z-Score based)
  trades_today?: number;        // Number of transactions today (Polygon day.n)
  avg_trades_5d?: number;       // Average trades per day (last 5 trading days)
  trades_z_score?: number;      // Z-Score = (trades_today - avg) / std
  is_trade_anomaly?: boolean;   // True if Z-Score >= 3.0

  // Volatility metrics
  atr_percent?: number;

  // Company fundamentals
  market_cap?: number;
  free_float?: number;
  free_float_percent?: number;
  shares_outstanding?: number;
  sector?: string;
  industry?: string;

  // Metadata
  timestamp?: string;

  // UI State (animaciones)
  priceFlash?: 'up' | 'down' | null;  // Flash animation direction

  // Allow any additional properties from backend
  [key: string]: any;
}

export interface ScannerTicker extends Ticker {
  // Alias for backward compatibility
}

// ============================================================================
// WEBSOCKET MESSAGES
// ============================================================================

export interface WebSocketMessage {
  type: 'snapshot' | 'delta' | 'aggregate' | 'connected';
  list?: string;
  sequence?: number;
  rows?: Ticker[];
  deltas?: DeltaAction[];
  symbol?: string;
  data?: any;
  connection_id?: string;
  timestamp?: string;
}

export interface DeltaAction {
  action: 'add' | 'update' | 'remove' | 'rerank';
  symbol: string;
  ticker?: Ticker;
  old_rank?: number;
  new_rank?: number;
}

// ============================================================================
// COMPANY METADATA
// ============================================================================

export interface CompanyMetadata {
  symbol: string;
  name?: string;
  sector?: string;
  industry?: string;
  marketCap?: number;
  market_cap?: number;
  description?: string;
  logo_url?: string;
  website?: string;
  employees?: number;
  headquarters?: string;
  founded?: string;
  is_actively_trading?: boolean;
  ceo?: string;
  phone?: string;
  phone_number?: string;
  address?: {
    city?: string;
    state?: string;
    zip?: string;
    country?: string;
    street?: string;
  };
  city?: string;
  state?: string;
  zip?: string;
  country?: string;
  exchange?: string;
  currency?: string;
  cik?: string;
  [key: string]: any; // Allow additional dynamic properties
}

// ============================================================================
// DILUTION TRACKER TYPES
// ============================================================================

export interface Filing {
  id: string;
  symbol: string;
  formType: string;
  filingDate: string;
  reportDate?: string;
  acceptedDate?: string;
  url?: string;
}

export interface FilingTag {
  tag: string;
  value: string | number;
  priority: number;
}

export interface TickerAnalysis {
  summary?: {
    ticker: string;
    company_name?: string;
    description?: string;
    sector?: string;
    industry?: string;
    exchange?: string;
    market_cap?: number;
    shares_outstanding?: number;
    free_float?: number;
    free_float_percent?: number;
    institutional_ownership?: number;
    homepage_url?: string;
    list_date?: string;
    total_employees?: number;
    [key: string]: any;
  };
  cash_runway?: {
    current_cash?: number;
    quarterly_burn_rate?: number;
    estimated_runway_months?: number;
    is_burning_cash?: boolean;
    runway_risk_level?: string;
    history?: any[];
    projection?: any[];
    [key: string]: any;
  };
  dilution_history?: {
    dilution_1y?: number;
    dilution_3y?: number;
    dilution_5y?: number;
    history?: any[];
    [key: string]: any;
  };
  holders?: any[];
  filings?: any[];
  financials?: any[];
  dilution?: any;
  risk_scores?: any;
  [key: string]: any;
}
