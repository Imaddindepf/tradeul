#!/usr/bin/env node
/**
 * Suite del parser numérico por locale (lib/utils/numberFormat.ts).
 *
 * Es la matriz del prototipo NumericField convertida en gate: si alguien
 * toca el parser y un caso de teclado español/americano/alemán cambia de
 * significado, el deploy no pasa. Corre con:
 *     node --experimental-strip-types scripts/check-number-parser.mjs
 */
import { parseLocaleNumber } from '../lib/utils/numberFormat.ts';

const INV = 'INVALID';
const cases = {
  'es-ES': {
    '0,5': 0.5, '2,5': 2.5, '1.000': 1000, '1.000.000': 1000000,
    '1,000': 1, '1.5': 1.5, '0.5': 0.5, '1.234,56': 1234.56,
    '1,234.56': 1234.56, '5m': 5000000, '5M': 5000000, '1,5b': 1500000000,
    '500k': 500000, '10%': 10, '$12.50': 12.5, ' 2 5 ': 25,
    '0': 0, '-2,5': -2.5, '−2,5': -2.5,
    '': null, 'abc': INV, '1.23.45': INV, '1,2,3': INV, '..5': INV,
  },
  'en-US': {
    '0.5': 0.5, '1,000': 1000, '1,000,000': 1000000, '1.000': 1,
    '0,5': 0.5, '1.234,56': 1234.56, '1,234.56': 1234.56,
    '5m': 5000000, '1.5b': 1500000000, '10%': 10, '0': 0,
    '': null, 'abc': INV,
  },
  'de-DE': {
    '0,5': 0.5, '1.000': 1000, '1.234,56': 1234.56, '5m': 5000000,
  },
};

let failed = 0;
let total = 0;
for (const [locale, table] of Object.entries(cases)) {
  for (const [input, expected] of Object.entries(table)) {
    total += 1;
    const r = parseLocaleNumber(input, locale);
    const got = r.invalid ? INV : r.value;
    const want = expected === INV ? INV : expected;
    if (got !== want) {
      failed += 1;
      console.error(`FAIL [${locale}] ${JSON.stringify(input)} -> ${JSON.stringify(got)} (esperado ${JSON.stringify(want)})`);
    }
  }
}

if (failed) {
  console.error(`Parser numérico: ${failed}/${total} casos FALLAN`);
  process.exit(1);
}
console.log(`Parser numérico OK: ${total} casos en ${Object.keys(cases).length} locales`);
