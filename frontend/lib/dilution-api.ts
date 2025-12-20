import type { TickerAnalysis } from './types';

// ENDPOINTS REALES - Dilution Tracker Service (puerto 8009)
const DILUTION_SERVICE_URL = process.env.NEXT_PUBLIC_DILUTION_API_URL || 'http://localhost:8009';

// ============================================================================
// TYPES
// ============================================================================

export interface Warrant {
  id?: string;
  symbol?: string;
  ticker?: string;
  series_name?: string;
  // Pricing
  exercise_price?: number;
  original_exercise_price?: number;
  // Quantities
  outstanding?: number;
  outstanding_warrants?: number;
  remaining?: number;
  total_issued?: number;
  potential_new_shares?: number;
  exercised?: number;
  expired?: number;
  // Type: "standard" | "pre-funded" | "callable" | "penny warrants"
  warrant_type?: 'standard' | 'pre-funded' | 'callable' | 'penny' | string;
  // Status: "active" | "expired" | "exercised" | "replaced"
  status?: 'Active' | 'Expired' | 'Exercised' | 'Replaced' | string;
  // Registration
  is_registered?: boolean;
  registration_type?: 'EDGAR' | 'Not Registered' | string;
  is_prefunded?: boolean;
  has_cashless_exercise?: boolean;
  warrant_coverage_ratio?: number;
  // Ownership & Underwriting
  known_owners?: string;
  underwriter_agent?: string;
  // Price Protection
  price_protection?: string;
  price_protection_clause?: string;
  pp_clause?: string; // alias
  anti_dilution_provision?: boolean;
  // Dates
  issue_date?: string;
  exercisable_date?: string;
  expiration_date?: string;
  last_update_date?: string;
  // Filing info
  filing_date?: string;
  source_filing?: string;
  filing_url?: string;
  notes?: string;
  [key: string]: any;
}

export interface ATMOffering {
  id?: string;
  symbol?: string;
  ticker?: string;
  series_name?: string;
  // Capacity & Usage
  total_capacity?: number;
  max_amount?: number;
  remaining_capacity?: number;
  amount_raised_to_date?: number;
  registered_shares?: number;
  potential_shares_at_current_price?: number;
  // Status: "Active" | "Terminated" | "Expired" | "Replaced"
  status?: 'Active' | 'Terminated' | 'Expired' | 'Replaced' | string;
  // Placement Agent (primary field, broker is alias)
  placement_agent?: string;
  broker_dealer?: string;
  broker?: string; // deprecated alias
  commission_rate?: number;
  // Baby Shelf Limitations
  is_baby_shelf_limited?: boolean;
  remaining_capacity_without_baby_shelf?: number;
  // Dates
  agreement_date?: string;
  issue_date?: string;
  filing_date?: string;
  expiration_date?: string;
  last_update_date?: string;
  last_update?: string; // alias
  // Filing info
  filing_url?: string;
  notes?: string;
  [key: string]: any;
}

export interface ShelfRegistration {
  id?: string;
  symbol?: string;
  ticker?: string;
  series_name?: string;
  // Capacity & Usage
  total_capacity?: number;
  total_amount?: number;
  remaining_capacity?: number;
  amount_raised?: number;
  amount_raised_last_12_months?: number;
  // Baby Shelf (IB-6) fields
  is_baby_shelf?: boolean;
  public_float?: number;
  highest_60_day_close?: number;
  ib6_float_value?: number;
  current_raisable_amount?: number;
  price_to_exceed_baby_shelf?: number;
  // Registration type: "S-1" | "S-3" | "F-1" | "F-3"
  registration_statement?: 'S-1' | 'S-3' | 'F-1' | 'F-3' | string;
  registration_type?: string; // alias
  // Status: "Active" | "Expired" | "Used"
  status?: 'Active' | 'Expired' | 'Used' | string;
  // Shelf Type
  is_mixed_shelf?: boolean;
  is_primary_offering?: boolean;
  is_resale?: boolean;
  // Dates
  effect_date?: string;
  filing_date?: string;
  expiration_date?: string;
  last_update_date?: string;
  last_update?: string; // alias
  // Filing info
  filing_url?: string;
  notes?: string;
  [key: string]: any;
}

export interface CompletedOffering {
  id?: string;
  symbol?: string;
  ticker?: string;
  // Offering Details
  offering_date?: string;
  shares_offered?: number;
  shares_issued?: number;
  price_per_share?: number;
  gross_proceeds?: number;
  amount_raised?: number;
  // Type: "Underwritten" | "Direct" | "Private" | "ATM" | "PIPE" | "Registered Direct"
  offering_type?: string;
  // Method: "S-1" | "S-3" | "Direct" | "Private"
  method?: 'S-1' | 'S-3' | 'Direct' | 'Private' | string;
  // Warrant info (if warrants were issued with offering)
  warrants_issued?: number;
  warrant_exercise_price?: number;
  warrant_coverage?: number;
  // Participants
  investors?: string;
  underwriter?: string;
  placement_agent?: string;
  // Dates
  last_update_date?: string;
  // Filing info
  filing_link?: string;
  filing_url?: string;
  notes?: string;
  [key: string]: any;
}

export interface ConvertibleNote {
  id?: string;
  symbol?: string;
  ticker?: string;
  series_name?: string;
  // Principal Amounts
  total_principal_amount?: number;
  remaining_principal_amount?: number;
  // Conversion Terms
  conversion_price?: number;
  original_conversion_price?: number;
  conversion_ratio?: number;
  total_shares_when_converted?: number;
  remaining_shares_when_converted?: number;
  interest_rate?: number;
  // Registration
  is_registered?: boolean;
  registration_type?: 'EDGAR' | 'Not Registered' | string;
  // Ownership & Underwriting
  known_owners?: string;
  underwriter_agent?: string;
  // Price Protection
  price_protection?: 'Customary Anti-Dilution' | 'Full Ratchet' | 'Variable Rate (TOXIC)' | 'Reset' | 'None' | string;
  price_protection_clause?: string;
  pp_clause?: string; // alias
  // Toxic Financing Indicators
  is_toxic?: boolean;
  variable_rate_adjustment?: boolean;
  floor_price?: number;
  // Dates
  issue_date?: string;
  convertible_date?: string;
  maturity_date?: string;
  last_update_date?: string;
  // Filing info
  filing_url?: string;
  notes?: string;
  [key: string]: any;
}

export interface SECDilutionProfileResponse {
  profile: {
    symbol: string;
    current_price?: number;
    shares_outstanding?: number;
    warrants: Warrant[];
    atm_offerings: ATMOffering[];
    shelf_registrations: ShelfRegistration[];
    completed_offerings: CompletedOffering[];
    convertible_notes?: ConvertibleNote[];
    metadata: {
      last_scraped_at: string;
      source: string;
      source_filings: string[];
    };
  };
  dilution_analysis: {
    total_potential_dilution_pct?: number;
    total_potential_new_shares?: number;
    warrant_shares?: number;
    atm_shares?: number;
    atm_potential_shares?: number;
    shelf_shares?: number;
    shelf_potential_shares?: number;
    risk_level?: 'HIGH' | 'MEDIUM' | 'LOW' | 'UNKNOWN';
    risk_factors?: string[];
    total_warrants?: number;
    total_atm_capacity?: number;
    total_shelf_capacity?: number;
    [key: string]: any; // Allow additional dynamic properties
  };
  cached: boolean;
  cache_age_seconds?: number;

  // Company type detection
  is_spac?: boolean;
  sic_code?: string;
}

// ============================================================================
// API FUNCTIONS
// ============================================================================

export async function validateTicker(symbol: string): Promise<boolean> {
  try {
    // Endpoint REAL: /api/analysis/validate/{ticker} - Validación rápida
    const response = await fetch(`${DILUTION_SERVICE_URL}/api/analysis/validate/${symbol}`);
    if (!response.ok) {
      return false;
    }
    const data = await response.json();
    return data.valid === true;
  } catch (error) {
    console.error(`Error validating ticker ${symbol}:`, error);
    return false;
  }
}

export async function getTickerAnalysis(symbol: string): Promise<TickerAnalysis> {
  try {
    // Endpoint REAL: /api/analysis/{ticker} - Devuelve análisis COMPLETO
    // Incluye: summary, cash_runway, dilution_history, holders, filings, financials, dilution (SEC)
    const response = await fetch(`${DILUTION_SERVICE_URL}/api/analysis/${symbol}`);

    if (!response.ok) {
      throw new Error(`Failed to fetch analysis for ${symbol}`);
    }

    const data = await response.json();
    return data;
  } catch (error) {
    console.error(`Error fetching analysis for ${symbol}:`, error);
    throw error;
  }
}

// ============================================================================
// RISK RATINGS (DilutionTracker 5 Ratings)
// ============================================================================

export type RiskLevel = 'Low' | 'Medium' | 'High' | 'Unknown';

export interface DilutionRiskRatings {
  ticker: string;
  overall_risk: RiskLevel;
  offering_ability: RiskLevel;
  overhead_supply: RiskLevel;
  historical: RiskLevel;
  cash_need: RiskLevel;
  scores: {
    overall: number;
    offering_ability: number;
    overhead_supply: number;
    historical: number;
    cash_need: number;
  };
  details: {
    offering_ability: {
      shelf_capacity_remaining: number;
      has_active_shelf: boolean;
      has_pending_s1: boolean;
    };
    overhead_supply: {
      warrants_shares: number;
      atm_shares: number;
      convertible_shares: number;
      equity_line_shares: number;
      total_potential_shares: number;
      shares_outstanding: number;
      dilution_pct: number;
    };
    historical: {
      shares_outstanding_current: number;
      shares_outstanding_3yr_ago: number;
      increase_pct: number;
    };
    cash_need: {
      runway_months: number | null;
      has_positive_operating_cf: boolean;
    };
  };
  data_available: boolean;
}

/**
 * Get DilutionTracker 5 Risk Ratings
 */
export async function getRiskRatings(symbol: string): Promise<DilutionRiskRatings | null> {
  try {
    const response = await fetch(`${DILUTION_SERVICE_URL}/api/sec-dilution/${symbol}/risk-ratings`);

    if (!response.ok) {
      console.warn(`Risk ratings not available for ${symbol}`);
      return null;
    }

    return await response.json();
  } catch (error) {
    console.error(`Error fetching risk ratings for ${symbol}:`, error);
    return null;
  }
}

/**
 * CHECK SEC CACHE (NON-BLOCKING)
 * 
 * Verifica si hay datos de dilución en caché.
 * NUNCA bloquea - retorna inmediatamente.
 * 
 * @returns 
 * - Si hay caché: { status: 'cached', data: SECDilutionProfileResponse }
 * - Si no hay: { status: 'no_cache', job_status: 'queued'|'processing'|'none' }
 */
export interface SECCacheCheckResult {
  status: 'cached' | 'no_cache' | 'error';
  data?: SECDilutionProfileResponse;
  ticker?: string;
  job_status?: 'queued' | 'processing' | 'none' | 'unknown';
  job_id?: string;
  message?: string;
  error?: string;
}

export async function checkSECCache(symbol: string, enqueueIfMissing: boolean = true): Promise<SECCacheCheckResult> {
  try {
    const response = await fetch(
      `${DILUTION_SERVICE_URL}/api/sec-dilution/${symbol}/check?enqueue_if_missing=${enqueueIfMissing}`,
      {
        // Timeout corto - este endpoint debe ser rápido
        signal: AbortSignal.timeout(10000)
      }
    );

    if (!response.ok) {
      throw new Error(`HTTP ${response.status}`);
    }

    return await response.json();
  } catch (error) {
    console.error(`Error checking SEC cache for ${symbol}:`, error);
    return {
      status: 'error',
      ticker: symbol,
      error: error instanceof Error ? error.message : 'Unknown error'
    };
  }
}

export async function getSECDilutionProfile(symbol: string): Promise<SECDilutionProfileResponse> {
  try {
    // Endpoint REAL: /api/sec-dilution/{ticker}/profile
    // include_filings=true para obtener la lista de filings analizados
    const response = await fetch(`${DILUTION_SERVICE_URL}/api/sec-dilution/${symbol}/profile?include_filings=true`);

    if (!response.ok) {
      throw new Error(`Failed to fetch SEC dilution profile for ${symbol}: ${response.status}`);
    }

    const data = await response.json();
    return data;
  } catch (error) {
    console.error(`Error fetching SEC dilution profile for ${symbol}:`, error);
    throw error;
  }
}

export async function refreshSECDilutionProfile(symbol: string): Promise<SECDilutionProfileResponse> {
  try {
    // Endpoint REAL: /api/sec-dilution/{ticker}/profile con parámetros refresh e include_filings
    const response = await fetch(`${DILUTION_SERVICE_URL}/api/sec-dilution/${symbol}/profile?force_refresh=true&include_filings=true`);

    if (!response.ok) {
      throw new Error(`Failed to refresh SEC dilution profile for ${symbol}`);
    }

    const data = await response.json();
    return data;
  } catch (error) {
    console.error(`Error refreshing SEC dilution profile for ${symbol}:`, error);
    throw error;
  }
}

// ============================================================================
// CASH POSITION API
// ============================================================================

export interface CashPositionResponse {
  cash_history: Array<{
    date: string;
    cash: number;
    total_assets?: number;
    total_liabilities?: number;
  }>;
  cashflow_history: Array<{
    date: string;
    operating_cf: number;
    investing_cf?: number;
    financing_cf?: number;
    net_income?: number;
  }>;
  latest_cash: number;
  latest_operating_cf: number;
  last_report_date: string;
  days_since_report: number;
  daily_burn_rate: number;
  prorated_cf: number;
  estimated_current_cash: number;
  runway_days: number | null;
  runway_risk_level: string;
  error?: string | null;
}

export interface CashRunwayData {
  ticker?: string;
  // From enhanced endpoint
  historical_cash: number;
  historical_cash_date: string;
  quarterly_operating_cf: number;
  daily_burn_rate: number;
  days_since_report: number;
  prorated_cf: number;
  capital_raises?: {
    total: number;
    count: number;
    details: Array<{
      filing_date: string;
      effective_date?: string;
      gross_proceeds: number;
      net_proceeds?: number | null;
      instrument_type: string;
      shares_issued?: number | null;
      description: string;
      confidence?: number;
    }>;
  };
  estimated_current_cash: number;
  runway_days: number | null;
  runway_months: number | null;
  runway_risk_level: "critical" | "high" | "medium" | "moderate" | "low" | "healthy" | "unknown";
  data_source: string;
  last_updated?: string;
  error?: string | null;
  // Historical data for charting
  cash_history?: Array<{
    date: string;
    cash: number;
    total_assets?: number;
    total_liabilities?: number;
  }>;
  cf_history?: Array<{
    date: string;
    operating_cf: number;
    investing_cf?: number;
    financing_cf?: number;
  }>;
  // Legacy fields for backwards compatibility
  current_cash?: number;
  quarterly_burn_rate?: number;
  estimated_runway_months?: number | null;
  history?: Array<{ date: string; cash: number }>;
  projection?: Array<{ month: number; date: string; estimated_cash: number }>;
}

/**
 * Obtener datos de cash position desde SEC
 * Transforma al formato esperado por CashRunwayChart
 */
export async function getCashPosition(symbol: string): Promise<CashRunwayData | null> {
  try {
    // Use SEC-API.io endpoint ONLY (DilutionTracker methodology)
    const response = await fetch(`${DILUTION_SERVICE_URL}/api/sec-dilution/${symbol}/cash-position?max_quarters=40`);

    if (!response.ok) {
      console.warn(`Cash position not available for ${symbol}`);
      return null;
    }

    const data = await response.json();

    if (data.error) {
      console.warn(`Cash position error for ${symbol}:`, data.error);
      return null;
    }

    // Transform SEC-API.io data to expected format
    const cashHistory = data.cash_history?.sort((a: any, b: any) =>
      new Date(a.date).getTime() - new Date(b.date).getTime()
    ) || [];

    const cfHistory = data.cashflow_history?.sort((a: any, b: any) =>
      new Date(a.date).getTime() - new Date(b.date).getTime()
    ) || [];

    // Get the latest values from history (more accurate than computed)
    const latestCash = cashHistory.length > 0 ? cashHistory[cashHistory.length - 1].cash : data.latest_cash;
    const latestDate = cashHistory.length > 0 ? cashHistory[cashHistory.length - 1].date : data.last_report_date;

    return {
      ticker: symbol,
      historical_cash: latestCash,
      historical_cash_date: latestDate,
      quarterly_operating_cf: data.latest_operating_cf || 0,
      daily_burn_rate: data.daily_burn_rate || 0,
      days_since_report: data.days_since_report || 0,
      prorated_cf: data.prorated_cf || 0,
      capital_raises: data.capital_raises || { total: 0, count: 0, details: [] },
      estimated_current_cash: data.estimated_current_cash || latestCash,
      runway_days: data.runway_days,
      runway_months: data.runway_days ? data.runway_days / 30 : null,
      runway_risk_level: (data.runway_risk_level as CashRunwayData['runway_risk_level']) || 'unknown',
      data_source: data.source || 'sec_xbrl',
      cash_history: cashHistory,
      cf_history: cfHistory,
      // Legacy fields
      current_cash: data.estimated_current_cash || latestCash,
      quarterly_burn_rate: Math.abs(data.latest_operating_cf || 0),
      estimated_runway_months: data.runway_days ? data.runway_days / 30 : null,
      history: cashHistory,
    };
  } catch (error) {
    console.error(`Error fetching cash position for ${symbol}:`, error);
    return null;
  }
}

// ============================================================================
// SEC EDGAR SHARES HISTORY API
// ============================================================================

export interface SharesHistoryData {
  source: string;
  current?: {
    date: string;
    outstanding_shares: number;
    form?: string;
  };
  all_records?: Array<{
    period: string;
    outstanding_shares: number;
    form?: string;
  }>;
  history?: Array<{
    date: string;
    shares: number;
    form?: string;
    filed?: string;
  }>;
  dilution_summary?: {
    "1_year"?: number;
    "3_years"?: number;
    "5_years"?: number;
  };
  error?: string;
}

/**
 * Obtener historical shares outstanding desde SEC EDGAR
 * Fuente gratuita y oficial de la SEC
 */
export async function getSharesHistory(symbol: string): Promise<SharesHistoryData | null> {
  try {
    const response = await fetch(`${DILUTION_SERVICE_URL}/api/sec-dilution/${symbol}/shares-history`, {
      signal: AbortSignal.timeout(15000) // 15s timeout
    });

    if (!response.ok) {
      console.warn(`Shares history not available for ${symbol}`);
      return null;
    }

    const data: SharesHistoryData = await response.json();

    if (data.error) {
      return null;
    }

    return data;
  } catch (error) {
    console.error(`Error fetching shares history for ${symbol}:`, error);
    return null;
  }
}

// ============================================================================
// ASYNC ANALYSIS API
// ============================================================================

interface AsyncAnalysisResponse {
  job_id: string;
  ticker: string;
  status: string;
  poll_url: string;
  ws_channel: string;
}

interface AnalysisStatus {
  job_id: string;
  phase: string;
  phase_message: string;
  progress: number;
  updated_at: string;
  data: Partial<TickerAnalysis>;
  error: string | null;
}

/**
 * Iniciar análisis asíncrono de un ticker
 * Devuelve job_id para consultar el progreso
 */
export async function startAsyncAnalysis(ticker: string): Promise<AsyncAnalysisResponse> {
  const response = await fetch(`${DILUTION_SERVICE_URL}/api/analysis/async/${ticker}/start`, {
    method: 'POST',
  });

  if (!response.ok) {
    throw new Error(`Failed to start async analysis for ${ticker}`);
  }

  return response.json();
}

/**
 * Obtener estado del análisis asíncrono
 */
export async function getAnalysisStatus(ticker: string, jobId: string): Promise<AnalysisStatus> {
  const response = await fetch(`${DILUTION_SERVICE_URL}/api/analysis/async/${ticker}/status/${jobId}`);

  if (!response.ok) {
    throw new Error(`Failed to get analysis status for ${ticker}`);
  }

  return response.json();
}

/**
 * Análisis rápido - solo datos básicos sin deep SEC analysis
 */
export async function getQuickAnalysis(ticker: string): Promise<TickerAnalysis> {
  const response = await fetch(`${DILUTION_SERVICE_URL}/api/analysis/async/${ticker}/quick`);

  if (!response.ok) {
    throw new Error(`Failed to get quick analysis for ${ticker}`);
  }

  return response.json();
}

export type { TickerAnalysis };

