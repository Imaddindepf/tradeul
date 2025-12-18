import type { TickerAnalysis } from './types';

// ENDPOINTS REALES - Dilution Tracker Service (puerto 8009)
const DILUTION_SERVICE_URL = process.env.NEXT_PUBLIC_DILUTION_API_URL || 'http://localhost:8009';

// ============================================================================
// TYPES
// ============================================================================

export interface Warrant {
  id?: string;
  symbol?: string;
  exercise_price?: number;
  expiration_date?: string;
  issue_date?: string;
  outstanding_warrants?: number;
  warrant_type?: string;
  filing_date?: string;
  source_filing?: string;
  filing_url?: string;
  [key: string]: any; // Allow additional dynamic properties
}

export interface ATMOffering {
  id?: string;
  symbol?: string;
  max_amount?: number;
  remaining_capacity?: number;
  status?: string;
  filing_date?: string;
  last_update?: string;
  broker?: string;
  filing_url?: string;
  [key: string]: any; // Allow additional dynamic properties
}

export interface ShelfRegistration {
  id?: string;
  symbol?: string;
  total_amount?: number;
  remaining_capacity?: number;
  status?: string;
  filing_date?: string;
  expiration_date?: string;
  last_update?: string;
  filing_url?: string;
  [key: string]: any; // Allow additional dynamic properties
}

export interface CompletedOffering {
  id?: string;
  symbol?: string;
  offering_date?: string;
  shares_offered?: number;
  price_per_share?: number;
  gross_proceeds?: number;
  offering_type?: string;
  filing_link?: string;
  filing_url?: string;
  [key: string]: any; // Allow additional dynamic properties
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
  current_cash: number;
  quarterly_burn_rate: number;
  estimated_runway_months: number | null;
  runway_risk_level: "critical" | "high" | "medium" | "low" | "unknown";
  history?: Array<{ date: string; cash: number }>;
  projection: Array<{ month: number; date: string; estimated_cash: number }>;
}

/**
 * Obtener datos de cash position desde SEC
 * Transforma al formato esperado por CashRunwayChart
 */
export async function getCashPosition(symbol: string): Promise<CashRunwayData | null> {
  try {
    const response = await fetch(`${DILUTION_SERVICE_URL}/api/sec-dilution/${symbol}/cash-position`);
    
    if (!response.ok) {
      console.warn(`Cash position not available for ${symbol}`);
      return null;
    }
    
    const data: CashPositionResponse = await response.json();
    
    if (data.error || !data.latest_cash) {
      return null;
    }
    
    // Calcular quarterly burn rate desde el daily burn rate
    const quarterlyBurnRate = data.daily_burn_rate * 90; // ~90 días por trimestre
    
    // Calcular runway en meses
    const runwayMonths = data.runway_days ? data.runway_days / 30 : null;
    
    // Preparar historial ordenado de antiguo a nuevo
    const history = data.cash_history
      ?.sort((a, b) => new Date(a.date).getTime() - new Date(b.date).getTime())
      .map(h => ({ date: h.date, cash: h.cash })) || [];
    
    // Crear proyección (próximos 12 meses)
    const projection: Array<{ month: number; date: string; estimated_cash: number }> = [];
    const monthlyBurn = quarterlyBurnRate / 3;
    let currentCash = data.estimated_current_cash;
    const now = new Date();
    
    for (let i = 1; i <= 12; i++) {
      const futureDate = new Date(now);
      futureDate.setMonth(futureDate.getMonth() + i);
      currentCash = Math.max(0, currentCash + monthlyBurn); // monthlyBurn is negative
      projection.push({
        month: i,
        date: futureDate.toISOString().split('T')[0],
        estimated_cash: currentCash
      });
    }
    
    return {
      current_cash: data.estimated_current_cash,
      quarterly_burn_rate: quarterlyBurnRate,
      estimated_runway_months: runwayMonths,
      runway_risk_level: (data.runway_risk_level as CashRunwayData['runway_risk_level']) || 'unknown',
      history,
      projection
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

