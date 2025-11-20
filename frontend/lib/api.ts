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

export interface PolygonMarketStatus {
  market: 'open' | 'closed' | 'extended-hours';
  serverTime: string;
  earlyHours: boolean;
  afterHours: boolean;
  exchanges: {
    nasdaq?: string;
    nyse?: string;
    otc?: string;
  };
  currencies?: {
    crypto?: string;
    fx?: string;
  };
  indicesGroups?: {
    s_and_p?: string;
    societe_generale?: string;
    msci?: string;
    ftse_russell?: string;
    mstar?: string;
    mstarc?: string;
    nasdaq?: string;
    dow_jones?: string;
    cccy?: string;
    cgi?: string;
  };
}

export async function getMarketStatus(): Promise<PolygonMarketStatus | null> {
  try {
    // Endpoint para status detallado del mercado (Polygon)
    const response = await fetch(`${MARKET_SESSION_URL}/api/session/market-status`);
    
    if (!response.ok) {
      throw new Error('Failed to fetch market status');
    }
    
    return await response.json();
  } catch (error) {
    console.error('Error fetching market status:', error);
    return null;
  }
}

