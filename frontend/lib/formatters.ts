/**
 * Formatting utilities for displaying numbers, prices, percentages, etc.
 */

export function formatNumber(value: number | null | undefined): string {
  if (value === null || value === undefined || isNaN(value)) return '-';
  
  if (value >= 1_000_000_000) {
    return `${(value / 1_000_000_000).toFixed(2)}B`;
  } else if (value >= 1_000_000) {
    return `${(value / 1_000_000).toFixed(2)}M`;
  } else if (value >= 1_000) {
    return `${(value / 1_000).toFixed(2)}K`;
  }
  
  return value.toLocaleString('en-US');
}

export function formatPrice(value: number | null | undefined): string {
  if (value === null || value === undefined || isNaN(value)) return '-';
  
  if (value >= 1000) {
    return `$${value.toFixed(2)}`;
  } else if (value >= 1) {
    return `$${value.toFixed(2)}`;
  } else if (value >= 0.01) {
    return `$${value.toFixed(3)}`;
  } else {
    return `$${value.toFixed(4)}`;
  }
}

export function formatPercent(value: number | null | undefined): string {
  if (value === null || value === undefined || isNaN(value)) return '-';
  
  const sign = value > 0 ? '+' : '';
  return `${sign}${value.toFixed(2)}%`;
}

export function formatRVOL(value: number | null | undefined): string {
  if (value === null || value === undefined || isNaN(value)) return '-';
  
  return `${value.toFixed(2)}x`;
}

export function formatChange(value: number | null | undefined): string {
  if (value === null || value === undefined || isNaN(value)) return '-';
  
  const sign = value > 0 ? '+' : '';
  return `${sign}${value.toFixed(2)}`;
}

export function formatVolume(value: number | null | undefined): string {
  return formatNumber(value);
}

export function formatMarketCap(value: number | null | undefined): string {
  return formatNumber(value);
}
