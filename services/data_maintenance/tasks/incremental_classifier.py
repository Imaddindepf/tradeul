"""
Incremental Ticker Classifier
=============================

Daily follow-up to the full TickerClassifierTask run. Keeps the
dual-layer classification (ticker_classification + ticker_themes)
from going stale by re-classifying only what changed:

  1. NEW LISTINGS — active tickers with no ticker_classification row
     (IPOs, spin-offs, new ADRs; e.g. SKHY, FDXF).
  2. RECYCLED TICKERS — symbols whose CIK in tickers_unified no longer
     matches the CIK recorded at classification time (a ticker reused
     by a different company; e.g. SPCX: SPAC ETF -> SpaceX).
  3. MARKET-CAP SANITY — inside each ticker_root group, a share class
     whose implied price (market_cap / shares_outstanding) diverges
     wildly from an actively-trading sibling gets its market_cap
     NULLed so it can't win rankings (e.g. SKHYV "when issued").

Requires ticker_classification.cik (added/backfilled on first run).
"""

import logging
from typing import Dict, List

from tasks.ticker_classifier import TickerClassifierTask

logger = logging.getLogger(__name__)

# A share class is junk when its implied price is this many times away
# from the median implied price of its actively-trading siblings.
SANITY_DIVERGENCE_FACTOR = 4.0


class IncrementalClassifierTask(TickerClassifierTask):

    name = "incremental_classifier"

    _recycled: List[str] = []

    async def execute(self, skip_classified: bool = True) -> Dict:  # noqa: ARG002
        await self._ensure_cik_column()

        sanity = await self._market_cap_sanity_check()

        recycled = await self._find_recycled_symbols()
        if recycled:
            logger.info("incremental_classifier_recycled: %s", recycled)
            # Old themes belong to the previous company; drop them even if
            # the re-classification returns no new themes.
            async with self._pool.acquire() as conn:
                await conn.execute(
                    "DELETE FROM ticker_themes WHERE symbol = ANY($1)", recycled
                )
        self._recycled = recycled

        result = await super().execute(skip_classified=True)

        # Record the CIK we classified against, so future runs can detect
        # the next ticker recycle.
        async with self._pool.acquire() as conn:
            await conn.execute("""
                UPDATE ticker_classification tc
                SET cik = tu.cik
                FROM tickers_unified tu
                WHERE tu.symbol = tc.symbol
                  AND tu.cik IS NOT NULL
                  AND tc.cik IS DISTINCT FROM tu.cik
            """)

        result["recycled_reclassified"] = recycled
        result["market_cap_nulled"] = sanity
        return result

    # ── candidate selection ──────────────────────────────────────

    async def _load_tickers(self, skip_classified: bool) -> List[Dict]:  # noqa: ARG002
        """New active tickers plus recycled ones (CIK changed)."""
        async with self._pool.acquire() as conn:
            rows = await conn.fetch("""
                SELECT tu.symbol, tu.company_name, tu.sector, tu.industry,
                       tu.description, tu.market_cap, tu.is_etf
                FROM tickers_unified tu
                LEFT JOIN ticker_classification tc ON tu.symbol = tc.symbol
                WHERE tu.is_active = true
                  AND (tc.symbol IS NULL OR tu.symbol = ANY($1))
                ORDER BY tu.market_cap DESC NULLS LAST
            """, self._recycled)

        return [
            {
                "symbol": r["symbol"],
                "company_name": r["company_name"] or "",
                "sector": r["sector"] or "",
                "industry": r["industry"] or "",
                "description": r["description"] or "",
                "market_cap": str(r["market_cap"]) if r["market_cap"] else "N/A",
            }
            for r in rows
        ]

    async def _find_recycled_symbols(self) -> List[str]:
        async with self._pool.acquire() as conn:
            rows = await conn.fetch("""
                SELECT tu.symbol
                FROM tickers_unified tu
                JOIN ticker_classification tc ON tu.symbol = tc.symbol
                WHERE tu.is_active = true
                  AND tu.cik IS NOT NULL
                  AND tc.cik IS NOT NULL
                  AND tu.cik <> tc.cik
            """)
        return [r["symbol"] for r in rows]

    # ── one-time schema guard ────────────────────────────────────

    async def _ensure_cik_column(self) -> None:
        async with self._pool.acquire() as conn:
            await conn.execute("""
                ALTER TABLE ticker_classification
                ADD COLUMN IF NOT EXISTS cik VARCHAR(20)
            """)
            await conn.execute("""
                UPDATE ticker_classification tc
                SET cik = tu.cik
                FROM tickers_unified tu
                WHERE tu.symbol = tc.symbol
                  AND tc.cik IS NULL
                  AND tu.cik IS NOT NULL
            """)

    # ── market-cap sanity ────────────────────────────────────────

    async def _market_cap_sanity_check(self) -> List[str]:
        """NULL the market_cap of share classes whose implied price
        diverges >SANITY_DIVERGENCE_FACTOR from an actively-trading
        sibling of the same ticker_root ("when issued" rows etc.)."""
        async with self._pool.acquire() as conn:
            rows = await conn.fetch("""
                WITH implied AS (
                    SELECT symbol, ticker_root, is_actively_trading,
                           market_cap / NULLIF(shares_outstanding, 0) AS px
                    FROM tickers_unified
                    WHERE market_cap IS NOT NULL
                      AND shares_outstanding > 0
                      AND ticker_root IS NOT NULL
                ),
                anchor AS (
                    SELECT ticker_root,
                           PERCENTILE_CONT(0.5) WITHIN GROUP (ORDER BY px) AS ref_px
                    FROM implied
                    WHERE is_actively_trading
                    GROUP BY ticker_root
                )
                UPDATE tickers_unified tu
                SET market_cap = NULL
                FROM implied i, anchor a
                WHERE tu.symbol = i.symbol
                  AND i.ticker_root = a.ticker_root
                  AND NOT i.is_actively_trading
                  AND a.ref_px > 0
                  AND (i.px > a.ref_px * $1 OR i.px * $1 < a.ref_px)
                RETURNING tu.symbol
            """, SANITY_DIVERGENCE_FACTOR)

        nulled = [r["symbol"] for r in rows]
        if nulled:
            logger.warning("market_cap_sanity_nulled: %s", nulled)
        return nulled
