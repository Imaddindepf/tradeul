/**
 * Utilidades para formatear y parsear números en formato humano
 * Soporta: 1b, 1m, 1k, etc.
 */

/**
 * Parsea un valor en formato humano a número
 * Ejemplos:
 * - "1b" -> 1000000000
 * - "1.5m" -> 1500000
 * - "500k" -> 500000
 * - "1000" -> 1000
 */
export function parseHumanNumber(value: string): number | null {
  if (!value || value.trim() === '') return null;
  
  const trimmed = value.trim().toLowerCase();
  
  // Si es solo un número, devolverlo directamente
  if (/^\d+(\.\d+)?$/.test(trimmed)) {
    return parseFloat(trimmed);
  }
  
  // Buscar sufijos: b (billions), m (millions), k (thousands)
  const match = trimmed.match(/^(\d+(?:\.\d+)?)\s*([bkm])?$/);
  if (!match) return null;
  
  const num = parseFloat(match[1]);
  const suffix = match[2];
  
  if (!suffix) return num;
  
  switch (suffix) {
    case 'b':
      return num * 1_000_000_000;
    case 'm':
      return num * 1_000_000;
    case 'k':
      return num * 1_000;
    default:
      return num;
  }
}

/**
 * Formatea un número a formato humano
 * Ejemplos:
 * - 1000000000 -> "1b"
 * - 1500000 -> "1.5m"
 * - 500000 -> "500k"
 * - 1000 -> "1k"
 * - 500 -> "500"
 */
export function formatHumanNumber(value: number | null | undefined): string {
  if (value === null || value === undefined) return '';
  
  const absValue = Math.abs(value);
  
  if (absValue >= 1_000_000_000) {
    const billions = value / 1_000_000_000;
    return billions % 1 === 0 ? `${billions}b` : `${billions.toFixed(1)}b`;
  }
  
  if (absValue >= 1_000_000) {
    const millions = value / 1_000_000;
    return millions % 1 === 0 ? `${millions}m` : `${millions.toFixed(1)}m`;
  }
  
  if (absValue >= 1_000) {
    const thousands = value / 1_000;
    return thousands % 1 === 0 ? `${thousands}k` : `${thousands.toFixed(1)}k`;
  }
  
  return value.toString();
}


