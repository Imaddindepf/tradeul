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

export async function getSECDilutionProfile(symbol: string): Promise<SECDilutionProfileResponse> {
  try {
    // Endpoint REAL: /api/sec-dilution/{ticker}/profile
    const response = await fetch(`${DILUTION_SERVICE_URL}/api/sec-dilution/${symbol}/profile`);

    if (!response.ok) {
      throw new Error(`Failed to fetch SEC dilution profile for ${symbol}`);
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
    // Endpoint REAL: /api/sec-dilution/{ticker}/profile con parámetro refresh=true
    const response = await fetch(`${DILUTION_SERVICE_URL}/api/sec-dilution/${symbol}/profile?refresh=true`);

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

