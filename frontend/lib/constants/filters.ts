/**
 * Constantes para filtros de datos de mercado
 */

// ============================================================================
// SECURITY TYPES (Polygon API)
// ============================================================================
export const SECURITY_TYPES = [
  { value: 'CS', label: 'Common Stock (CS)' },
  { value: 'ETF', label: 'ETF' },
  { value: 'PFD', label: 'Preferred Stock (PFD)' },
  { value: 'WARRANT', label: 'Warrant' },
  { value: 'ADRC', label: 'ADR Common (ADRC)' },
  { value: 'UNIT', label: 'Unit' },
  { value: 'RIGHT', label: 'Rights' },
] as const;

// ============================================================================
// SECTORS (GICS Level 1)
// ============================================================================
export const SECTORS = [
  { value: 'Technology', label: 'Technology' },
  { value: 'Healthcare', label: 'Healthcare' },
  { value: 'Financials', label: 'Financials' },
  { value: 'Consumer Discretionary', label: 'Consumer Discretionary' },
  { value: 'Consumer Staples', label: 'Consumer Staples' },
  { value: 'Industrials', label: 'Industrials' },
  { value: 'Energy', label: 'Energy' },
  { value: 'Materials', label: 'Materials' },
  { value: 'Real Estate', label: 'Real Estate' },
  { value: 'Communication Services', label: 'Communication Services' },
  { value: 'Utilities', label: 'Utilities' },
] as const;

// ============================================================================
// INDUSTRIES (GICS Level 3 - Most Common)
// ============================================================================
export const INDUSTRIES = [
  // Technology
  { value: 'Software', label: 'Software', sector: 'Technology' },
  { value: 'Semiconductors', label: 'Semiconductors', sector: 'Technology' },
  { value: 'IT Services', label: 'IT Services', sector: 'Technology' },
  { value: 'Technology Hardware', label: 'Technology Hardware', sector: 'Technology' },
  { value: 'Electronic Equipment', label: 'Electronic Equipment', sector: 'Technology' },
  
  // Healthcare
  { value: 'Biotechnology', label: 'Biotechnology', sector: 'Healthcare' },
  { value: 'Pharmaceuticals', label: 'Pharmaceuticals', sector: 'Healthcare' },
  { value: 'Healthcare Equipment', label: 'Healthcare Equipment', sector: 'Healthcare' },
  { value: 'Healthcare Providers', label: 'Healthcare Providers', sector: 'Healthcare' },
  { value: 'Life Sciences', label: 'Life Sciences', sector: 'Healthcare' },
  
  // Financials
  { value: 'Banks', label: 'Banks', sector: 'Financials' },
  { value: 'Insurance', label: 'Insurance', sector: 'Financials' },
  { value: 'Capital Markets', label: 'Capital Markets', sector: 'Financials' },
  { value: 'Financial Services', label: 'Financial Services', sector: 'Financials' },
  
  // Consumer Discretionary
  { value: 'Retail', label: 'Retail', sector: 'Consumer Discretionary' },
  { value: 'Automobiles', label: 'Automobiles', sector: 'Consumer Discretionary' },
  { value: 'Hotels & Restaurants', label: 'Hotels & Restaurants', sector: 'Consumer Discretionary' },
  { value: 'Media & Entertainment', label: 'Media & Entertainment', sector: 'Consumer Discretionary' },
  
  // Consumer Staples
  { value: 'Food & Beverage', label: 'Food & Beverage', sector: 'Consumer Staples' },
  { value: 'Household Products', label: 'Household Products', sector: 'Consumer Staples' },
  { value: 'Tobacco', label: 'Tobacco', sector: 'Consumer Staples' },
  
  // Industrials
  { value: 'Aerospace & Defense', label: 'Aerospace & Defense', sector: 'Industrials' },
  { value: 'Construction', label: 'Construction', sector: 'Industrials' },
  { value: 'Industrial Conglomerates', label: 'Industrial Conglomerates', sector: 'Industrials' },
  { value: 'Transportation', label: 'Transportation', sector: 'Industrials' },
  
  // Energy
  { value: 'Oil & Gas', label: 'Oil & Gas', sector: 'Energy' },
  { value: 'Energy Equipment', label: 'Energy Equipment', sector: 'Energy' },
  
  // Materials
  { value: 'Chemicals', label: 'Chemicals', sector: 'Materials' },
  { value: 'Metals & Mining', label: 'Metals & Mining', sector: 'Materials' },
  
  // Real Estate
  { value: 'REITs', label: 'REITs', sector: 'Real Estate' },
  { value: 'Real Estate Management', label: 'Real Estate Management', sector: 'Real Estate' },
  
  // Communication Services
  { value: 'Telecommunications', label: 'Telecommunications', sector: 'Communication Services' },
  { value: 'Media', label: 'Media', sector: 'Communication Services' },
  
  // Utilities
  { value: 'Electric Utilities', label: 'Electric Utilities', sector: 'Utilities' },
  { value: 'Gas Utilities', label: 'Gas Utilities', sector: 'Utilities' },
  { value: 'Water Utilities', label: 'Water Utilities', sector: 'Utilities' },
] as const;

export type SecurityType = typeof SECURITY_TYPES[number]['value'];
export type Sector = typeof SECTORS[number]['value'];
export type Industry = typeof INDUSTRIES[number]['value'];
