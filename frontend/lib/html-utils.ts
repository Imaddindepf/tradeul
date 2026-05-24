/**
 * Decode HTML entities using pure regex — zero DOM allocations.
 *
 * Covers all named entities used by Benzinga/news feeds
 * plus numeric (&#NNN;) and hex (&#xHHH;) code points.
 */

const NAMED: Record<string, string> = {
  amp: '&',
  lt: '<',
  gt: '>',
  quot: '"',
  apos: "'",
  nbsp: '\u00A0',
  ndash: '\u2013',
  mdash: '\u2014',
  lsquo: '\u2018',
  rsquo: '\u2019',
  ldquo: '\u201C',
  rdquo: '\u201D',
  bull: '\u2022',
  hellip: '\u2026',
  copy: '\u00A9',
  reg: '\u00AE',
  trade: '\u2122',
  euro: '\u20AC',
  pound: '\u00A3',
  yen: '\u00A5',
  cent: '\u00A2',
  frac12: '\u00BD',
  frac14: '\u00BC',
  frac34: '\u00BE',
  times: '\u00D7',
  divide: '\u00F7',
};

const ENTITY_RE = /&(?:#x([0-9a-fA-F]+)|#(\d+)|([a-zA-Z]+));/g;

export function decodeHtmlEntities(text: string): string {
  if (!text || !text.includes('&')) return text;

  return text.replace(ENTITY_RE, (match, hex, dec, named) => {
    if (hex) return String.fromCodePoint(parseInt(hex, 16));
    if (dec) return String.fromCodePoint(parseInt(dec, 10));
    if (named) return NAMED[named] ?? NAMED[named.toLowerCase()] ?? match;
    return match;
  });
}
