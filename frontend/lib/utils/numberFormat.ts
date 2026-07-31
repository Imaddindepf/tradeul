/**
 * Utilidades para formatear y parsear números en filtros (scanner y eventos).
 *
 * Filosofía: el valor REAL siempre se guarda en crudo (acciones, dólares, etc.).
 * La UI solo se encarga de:
 *   - mostrar el crudo de forma compacta y legible (5_000_000 -> "5M")
 *   - aceptar entrada tolerante del usuario ("5m", "5,000,000", "$5", "1.5b")
 *
 * Esto elimina la antigua clase de bugs en la que la "unidad" (K/M/B) era un
 * estado de UI separado que no se persistía y se desincronizaba del valor.
 */

export const UNIT_MUL: Record<string, number> = {
  '': 1,
  K: 1e3,
  M: 1e6,
  B: 1e9,
  T: 1e12,
};

/**
 * Parsea entrada humana tolerante a número crudo.
 * Acepta sufijos k/m/b/t (mayús/minús), separadores de miles, $, % y signos.
 * Ejemplos:
 *  - "5m"          -> 5000000
 *  - "1.5b"        -> 1500000000
 *  - "500k"        -> 500000
 *  - "5,000,000"   -> 5000000
 *  - "$12.50"      -> 12.5
 *  - "-2m"         -> -2000000
 *  - ".5m"         -> 500000
 *  - "" / basura   -> null
 */
export function parseHumanNumber(value: string | number | null | undefined): number | null {
  if (value === null || value === undefined) return null;
  if (typeof value === 'number') return Number.isFinite(value) ? value : null;

  let s = value.trim().toLowerCase();
  if (s === '') return null;

  // Quitar separadores de miles, espacios y símbolos de moneda/porcentaje.
  s = s.replace(/[,\s$%]/g, '');

  const match = s.match(/^(-?\d*\.?\d+)([kmbt]?)$/);
  if (!match) return null;

  const num = parseFloat(match[1]);
  if (!Number.isFinite(num)) return null;

  const mul = UNIT_MUL[(match[2] || '').toUpperCase()] ?? 1;
  return num * mul;
}

/**
 * Parsea el texto de una CELDA de tabla del agente (AutoChart,
 * InteractiveTable, StructuredTable) a número crudo, o null si la celda
 * no es un número puntual.
 *
 * A diferencia de parseHumanNumber (entrada de filtros — NO tocar su
 * semántica: FilterNumInput depende de ella), aquí se aceptan además:
 *   - "**$1.2B**"           -> 1.2e9   (markers de negrita markdown)
 *   - "+69.01%"             -> 69.01   (el % no escala, solo se descarta)
 *   - "2.62x"               -> 2.62    (múltiplos: RVOL, ratios)
 *   - "(2.3M)"              -> -2.3e6  (negativo contable)
 *   - "N/A" / "—" / "-" / "" -> null   (placeholders de "sin dato")
 *   - "$1.02 - $2.28"       -> null    (un rango no es un número puntual)
 * Sufijos K/M/B/T case-insensitive vía UNIT_MUL.
 */
export function parseCellNumber(raw: string | null | undefined): number | null {
  if (raw === null || raw === undefined) return null;

  // Quitar markers de negrita markdown y espacio exterior.
  let s = raw.replace(/\*\*/g, '').trim();
  if (s === '') return null;

  // Placeholders habituales de "sin dato".
  if (/^(n\/?a|null|—|–|-|--)$/i.test(s)) return null;

  // Negativo contable: "(2.3M)" -> -2.3M
  let negative = false;
  const paren = s.match(/^\((.+)\)$/);
  if (paren) {
    negative = true;
    s = paren[1].trim();
  }

  // Quitar moneda, separadores de miles y espacios internos.
  s = s.replace(/[,$\s]/g, '');

  // Número puntual con sufijo opcional. Un rango ("1.02-2.28") o texto
  // no matchean y devuelven null.
  const match = s.match(/^([+-]?)(\d*\.?\d+)(%|x|[kmbt])?$/i);
  if (!match) return null;

  const num = parseFloat(match[1] + match[2]);
  if (!Number.isFinite(num)) return null;

  // "%" y "x" no están en UNIT_MUL -> mul 1 (solo se descartan).
  const mul = UNIT_MUL[(match[3] || '').toUpperCase()] ?? 1;
  return negative ? -num * mul : num * mul;
}

/** Limpia ruido de coma flotante y recorta ceros finales. */
function trimFloat(n: number, decimals: number): string {
  return parseFloat(n.toFixed(decimals)).toString();
}

/**
 * Formatea un número crudo a una cadena compacta y legible para mostrar.
 * Ejemplos:
 *  - 5000000     -> "5M"
 *  - 1500000     -> "1.5M"
 *  - 2000000000  -> "2B"
 *  - 500000      -> "500K"
 *  - 1234567     -> "1.23M"
 *  - 12345       -> "12.35K"
 *  - 999         -> "999"
 *  - 5.25        -> "5.25"
 *  - -2000000    -> "-2M"
 */
export function formatCompact(value: number | null | undefined): string {
  if (value === null || value === undefined || !Number.isFinite(value)) return '';
  const a = Math.abs(value);
  if (a >= 1e12) return `${trimFloat(value / 1e12, 2)}T`;
  if (a >= 1e9) return `${trimFloat(value / 1e9, 2)}B`;
  if (a >= 1e6) return `${trimFloat(value / 1e6, 2)}M`;
  if (a >= 1e3) return `${trimFloat(value / 1e3, 2)}K`;
  return trimFloat(value, 4);
}

/**
 * A partir de un valor crudo, elige la unidad de visualización más legible
 * dentro de las opciones permitidas (p. ej. 5_000_000 → 5 + "M").
 */
export function deriveDisplayUnit(
  raw: number,
  unitOpts: readonly string[],
  defaultUnit = '',
): { display: number; unit: string } {
  const opts = unitOpts.length > 0 ? unitOpts : [''];
  const sorted = [...opts].sort(
    (a, b) => (UNIT_MUL[b.toUpperCase()] ?? 1) - (UNIT_MUL[a.toUpperCase()] ?? 1),
  );
  for (const u of sorted) {
    const mul = UNIT_MUL[u.toUpperCase()] ?? 1;
    const d = raw / mul;
    const ad = Math.abs(d);
    if (ad >= 0.01 && ad < 10_000) {
      return { display: parseFloat(d.toPrecision(10)), unit: u };
    }
  }
  const u = opts.includes(defaultUnit) ? defaultUnit : opts[0];
  const mul = UNIT_MUL[u.toUpperCase()] ?? 1;
  return { display: parseFloat((raw / mul).toPrecision(10)), unit: u };
}

/** Convierte valor crudo → número mostrado en la unidad elegida. */
export function rawToDisplay(raw: number | undefined, unit: string): number | undefined {
  if (raw === undefined) return undefined;
  const mul = UNIT_MUL[unit.toUpperCase()] ?? 1;
  return parseFloat((raw / mul).toPrecision(10));
}

/** Convierte número mostrado + unidad → valor crudo para guardar. */
export function displayToRaw(display: number | undefined, unit: string): number | undefined {
  if (display === undefined) return undefined;
  return display * (UNIT_MUL[unit.toUpperCase()] ?? 1);
}

/**
 * Placeholder numérico del catálogo (solo la cifra; la unidad va aparte).
 * p.ej. phMin="10", defU="K" → "10"
 */
export function formatPlaceholder(ph?: string, _defaultUnit?: string): string | undefined {
  if (ph === undefined || ph === null || ph === '') return undefined;
  const base = parseFloat(ph);
  return Number.isFinite(base) ? trimFloat(base, 4) : ph;
}

/**
 * @deprecated Usa formatCompact (mayúsculas) para mostrar y parseHumanNumber
 * para leer. Se mantiene por compatibilidad.
 */
export function formatHumanNumber(value: number | null | undefined): string {
  return formatCompact(value).toLowerCase();
}
