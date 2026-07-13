import type { CompanyMetadata } from './types';

// ENDPOINTS REALES
const API_GATEWAY_URL = process.env.NEXT_PUBLIC_API_URL || 'http://localhost:8000';
const MARKET_SESSION_URL = process.env.NEXT_PUBLIC_MARKET_SESSION_URL || 'http://localhost:8002';

export async function getCompanyMetadata(symbol: string): Promise<CompanyMetadata> {
  try {
    // Endpoint REAL: /api/v1/ticker/{symbol}/metadata en API Gateway
    const response = await fetch(`${API_GATEWAY_URL}/api/v1/ticker/${symbol}/metadata`);
    
    if (!response.ok) {
      throw new Error(`Failed to fetch metadata for ${symbol}`);
    }
    
    const data = await response.json();
    return data;
  } catch (error) {
    console.error(`Error fetching metadata for ${symbol}:`, error);
    throw error;
  }
}

export async function getMarketSession() {
  try {
    // Endpoint REAL: /api/session/current en Market Session Service (puerto 8002)
    const response = await fetch(`${MARKET_SESSION_URL}/api/session/current`);
    
    if (!response.ok) {
      throw new Error('Failed to fetch market session');
    }
    
    return await response.json();
  } catch (error) {
    console.error('Error fetching market session:', error);
    throw error;
  }
}

export interface MarketHoliday {
  date: string;              // YYYY-MM-DD
  name: string;
  exchange: string;
  is_early_close: boolean;
  early_close_time: string | null; // "13:00:00"
}

/**
 * Festivos y half-days próximos (fuente: market_session → Polygon).
 * Alimenta el calendario de lib/marketTime para que sesiones y velas
 * diarias respeten cierres anticipados (13:00 ET) y días de cierre total.
 */
export async function getMarketHolidays(daysAhead = 60): Promise<MarketHoliday[]> {
  try {
    const response = await fetch(`${MARKET_SESSION_URL}/api/holidays?days_ahead=${daysAhead}`);
    if (!response.ok) {
      throw new Error('Failed to fetch market holidays');
    }
    const data = await response.json();
    return Array.isArray(data?.holidays) ? data.holidays : [];
  } catch (error) {
    console.error('Error fetching market holidays:', error);
    return [];
  }
}

