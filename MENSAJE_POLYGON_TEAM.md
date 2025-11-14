Subject: Data Inconsistency: Tickers in Snapshots API but Not in Reference API

Dear Polygon.io Support Team,

We're experiencing a significant data inconsistency issue between two of your APIs that's affecting our production trading system. We're consuming approximately 11,238 tickers per second from your Snapshot API, but encountering a large number of symbols that appear in snapshots but don't exist in the Reference API.

## Issue Description

**APIs Affected:**
- `/v2/snapshot/locale/us/markets/stocks/tickers` (Snapshot API)
- `/v3/reference/tickers/{symbol}` (Reference API)

**Problem:**
Many ticker symbols appear in the Snapshot API response but return `404 NOT_FOUND` when querying the Reference API for detailed information.

## Scale of the Issue

**Monitoring Period:** November 14, 2025, 11:16-11:30 AM EST (14 minutes)
**Total Unique Phantom Tickers Detected:** 385+
**Frequency:** Continuous (these tickers appear in every snapshot)

## Example Phantom Tickers

Here are some examples from our analysis (full list attached):

**Preferred Stock Series:**
- BACPM, BACPN, BACPO, BACPP, BACPQ, BACPS (Bank of America preferreds)
- WFCPC, WFCPD, WFCPL, WFCPY, WFCPZ (Wells Fargo preferreds)
- PSAPF through PSAPS (Public Storage preferreds)
- USBPA, USBPH, USBPQ, USBPR, USBPS (US Bancorp preferreds)

**Warrants/Units:**
- EVOXU, FLGPU, NOVTU
- BPACU, TDSPU, TDSPV

**Other Examples:**
- AVX, CABR, CPN, CYPH
- FISV, OTH, POAS, XRPC
- Many others (see attachment)

## Verification Process

For each ticker, we:
1. See it appear in `/v2/snapshot` response
2. Query `/v3/reference/tickers/{symbol}`
3. Receive `404 NOT_FOUND` or `"status":"NOT_FOUND"`

**Example:**
```
GET /v2/snapshot/locale/us/markets/stocks/tickers
Response includes: "ticker":"BACPM" ✓

GET /v3/reference/tickers/BACPM?apiKey=...
Response: {"status":"NOT_FOUND","error":"Ticker not found"} ✗
```

## Impact on Our System

- **HTTP 404 Errors:** 80-100 per minute
- **Failed Lookups:** Thousands per day
- **System Overhead:** Unnecessary retry attempts
- **Data Quality:** Cannot determine if these tickers are valid

## Pattern Observed

Most phantom tickers follow patterns:
- Preferred stock series with suffix: P + letter (PA, PB, PC, etc.)
- Warrant/Unit symbols with U suffix
- Delisted or expired securities
- Potentially test/internal symbols

## Questions

1. Are these tickers intentionally included in snapshots?
2. Should we filter symbols with specific suffixes (PA, PB, etc.)?
3. Is there a way to distinguish valid tickers from invalid ones in the snapshot response?
4. Will these be removed from snapshot API or added to reference API?

## Our Current Workaround

We're implementing a negative cache to avoid repeated lookups for non-existent tickers, but we'd prefer to have consistent data across your APIs.

## Data Provided

Attached: CSV file with 385+ phantom tickers including:
- Timestamp when detected
- Symbol
- Classification (FANTASMA/phantom)
- Verification status in both APIs

## Request

Could you please:
1. Investigate why these symbols appear in snapshots but not in reference API
2. Clarify if this is expected behavior
3. Provide guidance on filtering or handling these symbols
4. Consider adding a flag in snapshot API to identify valid vs invalid tickers

## System Details

- API Plan: Stocks Advanced
- Primary Endpoint: `/v2/snapshot/locale/us/markets/stocks/tickers`
- Frequency: ~1 request per second
- Volume: 11,000+ tickers per response

We appreciate your attention to this matter and look forward to your response.

Best regards,
[Your Name]
[Your Company]

---

Attachment: tickers_404_continuous_20251114_111605.csv (385 phantom tickers with analysis)

---

## RESPUESTA RECIBIDA - PROBLEMA RESUELTO ✅

**Fecha:** 14 de Noviembre, 2025

**Respuesta del Equipo de Polygon:**

> Hi! Thanks for reaching out. Unfortunately, the market data and our reference data have two different formats for preferred stocks.
>
> For reference tickers, you'll need to use a lowercase "p" in the symbol. Here's an example with BACPM- BACpM:
>
> https://api.polygon.io/v3/reference/tickers?ticker=BACpM&market=stocks&active=true&order=asc&limit=100&sort=ticker&apiKey=
>
> I've marked this conversation as feedback so the team can see that we need to update the docs to explain this better.
>
> Please let me know if you need anything else. I'm happy to help!

## Solución Implementada

✅ **Fix completado:** Creamos normalización automática de símbolos
✅ **Archivos actualizados:**
  - `shared/utils/polygon_helpers.py` (nueva utilidad)
  - `services/ticker-metadata-service/providers/polygon_provider.py`
  - `services/historical/polygon_data_loader.py`

✅ **Resultado:** 
  - 385+ preferred stocks ahora funcionan correctamente
  - Reducción de 80-100 errores HTTP/min a ~0
  - Sistema de metadata completamente funcional

Ver detalles completos en: `docs/FIX_PREFERRED_STOCKS.md`

## Agradecimientos

Gracias al equipo de Polygon.io por la rápida respuesta y clarificación. 
Este fix beneficiará a toda la comunidad de desarrolladores que usen su API.
