/**
 * Glosario de abreviaturas/términos de filtros para las "help bubbles".
 *
 * El catálogo de filtros no guarda descripciones, así que definimos aquí las
 * explicaciones de los términos más comunes/ambiguos. La búsqueda es por
 * coincidencia de subcadena sobre la etiqueta (en orden: lo más específico
 * primero) para cubrir variantes como "Avg Daily Volume 5D" o "ATR %".
 */

interface GlossaryEntry {
  /** Subcadenas (en minúscula) que activan esta definición. */
  match: string[];
  en: string;
  es: string;
}

const GLOSSARY: GlossaryEntry[] = [
  { match: ['atr %', 'atr percent'], en: 'Average True Range as a % of price — normalized volatility. Higher = bigger swings.', es: 'Average True Range como % del precio — volatilidad normalizada. Más alto = más movimiento.' },
  { match: ['atr'], en: 'Average True Range — average price movement per bar, in dollars. Higher = more volatile.', es: 'Average True Range — movimiento medio de precio por vela, en dólares. Más alto = más volátil.' },
  { match: ['rvol', 'relative volume'], en: "Relative Volume — today's volume vs its typical average. Above 1 means heavier-than-usual trading.", es: 'Volumen Relativo — volumen de hoy frente a su media habitual. Por encima de 1 = más actividad de lo normal.' },
  { match: ['vwap'], en: 'Volume-Weighted Average Price — the session average price weighted by volume. A key intraday reference.', es: 'Precio Medio Ponderado por Volumen — precio medio de la sesión ponderado por volumen. Referencia intradía clave.' },
  { match: ['dollar volume'], en: 'Dollar Volume — shares traded × price. Total dollar value changing hands.', es: 'Volumen en Dólares — acciones negociadas × precio. Valor total en dólares operado.' },
  { match: ['avg daily volume', 'avg volume', 'average 10', 'average volume'], en: 'Average shares traded per day over the lookback window (e.g. 10D = last 10 days).', es: 'Media de acciones negociadas por día en la ventana indicada (p. ej. 10D = últimos 10 días).' },
  { match: ['float turnover'], en: "Today's volume ÷ float — how many times the tradable float has changed hands today.", es: 'Volumen de hoy ÷ float — cuántas veces ha rotado el float negociable hoy.' },
  { match: ['float'], en: 'Float — shares available for public trading (excludes insider/locked shares). Low float can move fast.', es: 'Float — acciones disponibles para negociar (excluye insiders/bloqueadas). Float bajo puede moverse rápido.' },
  { match: ['shares outstanding'], en: 'Total shares the company has issued, including restricted shares.', es: 'Total de acciones emitidas por la empresa, incluidas las restringidas.' },
  { match: ['market cap'], en: 'Market Capitalization — share price × shares outstanding.', es: 'Capitalización de Mercado — precio × acciones en circulación.' },
  { match: ['spread'], en: 'Bid-ask spread — gap between the best buy and sell price. Wider = less liquid.', es: 'Spread (bid-ask) — diferencia entre el mejor precio de compra y venta. Más ancho = menos líquido.' },
  { match: ['gap'], en: "Gap % — change from yesterday's close to today's open.", es: 'Gap % — variación entre el cierre de ayer y la apertura de hoy.' },
  { match: ['rsi'], en: 'Relative Strength Index (0-100). Above 70 = overbought, below 30 = oversold.', es: 'Índice de Fuerza Relativa (0-100). Por encima de 70 = sobrecompra, por debajo de 30 = sobreventa.' },
  { match: ['adx'], en: 'Average Directional Index — trend strength (0-100). Higher = stronger trend.', es: 'Average Directional Index — fuerza de la tendencia (0-100). Más alto = tendencia más fuerte.' },
  { match: ['macd'], en: 'Moving Average Convergence Divergence — momentum from the difference of two EMAs.', es: 'MACD — momento calculado a partir de la diferencia de dos EMAs.' },
  { match: ['stochastic'], en: 'Stochastic oscillator (0-100) — current price vs its recent high-low range.', es: 'Oscilador estocástico (0-100) — precio actual frente a su rango máximo-mínimo reciente.' },
  { match: ['ema'], en: 'Exponential Moving Average — moving average that weights recent prices more heavily.', es: 'Media Móvil Exponencial — media móvil que da más peso a los precios recientes.' },
  { match: ['sma'], en: 'Simple Moving Average — unweighted average of closing prices over the period.', es: 'Media Móvil Simple — media sin ponderar de los precios de cierre del periodo.' },
  { match: ['bid size'], en: 'Shares offered at the best bid (buy) price.', es: 'Acciones ofrecidas al mejor precio de compra (bid).' },
  { match: ['ask size'], en: 'Shares offered at the best ask (sell) price.', es: 'Acciones ofrecidas al mejor precio de venta (ask).' },
  { match: ['beta'], en: 'Beta — volatility relative to the overall market (1 = moves with the market).', es: 'Beta — volatilidad frente al mercado global (1 = se mueve con el mercado).' },
  { match: ['position in range', 'pos in range', 'pos in 52w', 'position in 52w'], en: "Where price sits within the period's high-low range (0% = low, 100% = high).", es: 'Dónde está el precio dentro del rango máximo-mínimo del periodo (0% = mínimo, 100% = máximo).' },
  { match: ['from open', 'change from open'], en: "Percent change from today's opening price.", es: 'Variación porcentual desde el precio de apertura de hoy.' },
  { match: ['from 52w high'], en: 'Percent distance below the 52-week high (0% = at the high).', es: 'Distancia porcentual por debajo del máximo de 52 semanas (0% = en el máximo).' },
  { match: ['from 52w low'], en: 'Percent distance above the 52-week low.', es: 'Distancia porcentual por encima del mínimo de 52 semanas.' },
  { match: ['distance vwap', 'dist from vwap', 'dist vwap'], en: 'Percent distance of price from VWAP. Positive = above VWAP.', es: 'Distancia porcentual del precio respecto al VWAP. Positivo = por encima del VWAP.' },
  { match: ['distance sma', 'dist sma', 'dist daily sma'], en: 'Percent distance of price from the moving average.', es: 'Distancia porcentual del precio respecto a la media móvil.' },
  { match: ['change %', 'change percent'], en: 'Percent change from the previous close.', es: 'Variación porcentual respecto al cierre anterior.' },
  { match: ['premarket'], en: 'Pre-market session (before 9:30 ET regular open).', es: 'Sesión pre-mercado (antes de la apertura regular a las 9:30 ET).' },
  { match: ['postmarket', 'post market', 'after hour'], en: 'Post-market / after-hours session (after 16:00 ET close).', es: 'Sesión post-mercado / after-hours (después del cierre a las 16:00 ET).' },
  { match: ['z-score', 'z score'], en: 'Standard deviations away from the mean — how unusual the value is.', es: 'Desviaciones estándar respecto a la media — cómo de inusual es el valor.' },
  { match: ['bb position', 'bollinger'], en: 'Position within the Bollinger Bands (0% = lower band, 100% = upper band).', es: 'Posición dentro de las Bandas de Bollinger (0% = banda inferior, 100% = banda superior).' },
  { match: ['consolidation'], en: 'Days the price has traded in a tight range (base building).', es: 'Días que el precio lleva en un rango estrecho (formando base).' },
  { match: ['nbbo'], en: 'National Best Bid and Offer — the best available bid/ask across exchanges.', es: 'National Best Bid and Offer — el mejor bid/ask disponible entre mercados.' },
];

/**
 * Devuelve la definición de un término de filtro para el idioma dado, o
 * undefined si no hay entrada en el glosario.
 */
export function filterHelp(label: string, locale?: string): string | undefined {
  if (!label) return undefined;
  const l = label.toLowerCase();
  const isEs = (locale || '').toLowerCase().startsWith('es');
  for (const entry of GLOSSARY) {
    if (entry.match.some(m => l.includes(m))) {
      return isEs ? entry.es : entry.en;
    }
  }
  return undefined;
}

/** Umbral: ningún valor (acción) de un único título alcanza 1.000 millones. */
const IMPLAUSIBLE_SHARE_COUNT = 1e9;

/**
 * Detecta si un valor de filtro es implausiblemente alto para un recuento de
 * acciones (volumen / float / acciones en circulación), que es la equivocación
 * típica de unidades (escribir 5B en vez de 5M). Devuelve el texto de aviso o
 * undefined. Excluye campos en $ (dollar volume, market cap) y en % donde 1B+
 * sí puede ser legítimo.
 */
export function implausibleHint(
  label: string,
  suf: string | undefined,
  value: number | null | undefined,
  locale?: string,
): string | undefined {
  if (value == null || !Number.isFinite(value)) return undefined;
  if (suf === '$' || suf === '%' || suf === 'x') return undefined;
  const l = label.toLowerCase();
  if (l.includes('dollar') || l.includes('market cap') || l.includes('%') || l.includes('percent')) {
    return undefined;
  }
  const isShareCount =
    (l.includes('volume') && !l.includes('dollar')) ||
    l.includes('float') ||
    l.includes('shares') ||
    l.includes('bid size') ||
    l.includes('ask size') ||
    l.includes('trades');
  if (!isShareCount) return undefined;
  if (Math.abs(value) < IMPLAUSIBLE_SHARE_COUNT) return undefined;
  const isEs = (locale || '').toLowerCase().startsWith('es');
  return isEs
    ? 'Muy alto para un número de acciones (1B+). Casi ningún título negocia tanto — ¿querías decir K (mil) o M (millón)? Un filtro así no devolverá resultados.'
    : 'Very high for a share count (1B+). Almost no stock trades this much — did you mean K (thousand) or M (million)? A filter like this returns no results.';
}
