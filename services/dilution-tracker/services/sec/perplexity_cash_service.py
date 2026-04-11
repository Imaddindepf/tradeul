"""
Perplexity Cash Service
=======================
Obtiene Cash + Operating CF trimestrales desde Perplexity Finance
e implementa la fórmula EXACTA de DilutionTracker.com extraída de su bundle JS:

  // DT source: bundle.e538ade31aec99bdf7de.js
  a = days_since_last_cash_date
  c = quarterly_ocf / 3 / 30 * a          // prorated CF (daily_burn * days)
  l = historical_cash + c + recent_raises  // estimated current cash
  o = 90 * c / a  → simplifica a quarterly_ocf
  runway_months = l / (-quarterly_ocf) * 3
  > 24mo → Low | > 6mo → Medium | < 6mo → High

Para `recent_raises` usamos CapitalRaiseExtractor (SEC-API.io 8-K Item 3.02)
para capturar notas convertibles, PIPEs y colocaciones privadas desde la última
fecha del BS. ATM intra-trimestre pueden no tener 8-K individual y se excluyen.
DT usa su endpoint privado `/v1/getCashPosition` que también rastrea ATM.
"""

from datetime import datetime, date
from typing import Optional, Dict, List, Any

from shared.utils.logger import get_logger
from shared.utils.redis_client import RedisClient

logger = get_logger(__name__)

CACHE_TTL = 4 * 3600  # 4 horas

_BASE_URL = "https://www.perplexity.ai/rest/finance/financials"
_BASE_HEADERS = {
    "Accept": "application/json, text/plain, */*",
    "Accept-Language": "en-US,en;q=0.9",
    "Origin": "https://www.perplexity.ai",
    "Sec-Fetch-Dest": "empty",
    "Sec-Fetch-Mode": "cors",
    "Sec-Fetch-Site": "same-origin",
}


async def _fetch_raw_async(ticker: str, category: str) -> Optional[Dict]:
    """Fetch quarterly financials from Perplexity using httpx."""
    import httpx

    headers = {
        **_BASE_HEADERS,
        "Referer": f"https://www.perplexity.ai/finance/{ticker}/financials",
        "User-Agent": (
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
            "AppleWebKit/537.36 (KHTML, like Gecko) "
            "Chrome/124.0.0.0 Safari/537.36"
        ),
    }
    url = f"{_BASE_URL}/{ticker}?period=quarter&category={category}"

    async with httpx.AsyncClient(timeout=15.0, follow_redirects=True) as client:
        resp = await client.get(url, headers=headers)
        if resp.status_code == 200:
            return resp.json()
        logger.warning("perplexity_fetch_status",
                       ticker=ticker, category=category, status=resp.status_code)
        return None


def _extract_section(data: Dict, section_type: str) -> List[Dict]:
    for section in data.get("quarter", []):
        if section.get("type") == section_type:
            return section.get("data", [])
    return []


class PerplexityCashService:
    """
    Cash Need calculator replicando la fórmula exacta de DilutionTracker.com.
    """

    def __init__(self, redis: RedisClient):
        self.redis = redis

    async def get_cash_summary(self, ticker: str) -> Optional[Dict]:
        """
        Fetches quarterly balance sheet + cash flow from Perplexity.

        Returns:
            {
                "ticker": str,
                "quarters": [                     # más-reciente primero
                    {
                        "date": "2025-09-30",
                        "period": "Q3",
                        "year": "2025",
                        "cash": 3009000,          # cashAndCashEquivalents
                        "operating_cf": -10617386 # netCashProvidedByOperatingActivities
                    }, ...
                ],
                "source": "perplexity"
            }
        """
        ticker = ticker.upper()
        cache_key = f"perplexity:cash_summary:{ticker}"

        cached = await self.redis.get(cache_key, deserialize=True)
        if cached:
            return cached

        try:
            import asyncio
            bs_data, cf_data = await asyncio.gather(
                _fetch_raw_async(ticker, "BALANCE_SHEET"),
                _fetch_raw_async(ticker, "CASH_FLOW"),
            )
        except Exception as e:
            logger.warning("perplexity_fetch_failed", ticker=ticker, error=str(e))
            return None

        if not bs_data:
            logger.warning("perplexity_no_balance_sheet", ticker=ticker)
            return None

        bs_rows = _extract_section(bs_data, "BALANCE_SHEET")
        cf_rows = _extract_section(cf_data, "CASH_FLOW") if cf_data else []
        cf_by_date = {row["date"]: row for row in cf_rows if "date" in row}

        quarters = []
        for row in bs_rows:
            d = row.get("date")
            if not d:
                continue
            # DilutionTracker.com methodology: cashAndShortTermInvestments primary,
            # cashAndCashEquivalents as fallback
            cash_st = row.get("cashAndShortTermInvestments")
            cash_eq = row.get("cashAndCashEquivalents")
            cash = cash_st if cash_st is not None else cash_eq
            if cash is None:
                continue
            cf_row = cf_by_date.get(d, {})
            quarters.append({
                "date": d,
                "period": row.get("period"),
                "year": row.get("calendarYear"),
                "cash": int(cash),
                "cash_and_equivalents": int(cash_eq) if cash_eq is not None else None,
                "operating_cf": int(cf_row["netCashProvidedByOperatingActivities"])
                    if cf_row.get("netCashProvidedByOperatingActivities") is not None
                    else None,
            })

        # Sort most-recent first; filter entries where cash > 0 (real data)
        quarters.sort(key=lambda q: q["date"], reverse=True)

        result = {
            "ticker": ticker,
            "quarters": quarters,
            "source": "perplexity",
        }

        if quarters:
            await self.redis.set(cache_key, result, ttl=CACHE_TTL, serialize=True)

        logger.info("perplexity_cash_summary_built",
                    ticker=ticker, quarters=len(quarters),
                    latest_date=quarters[0]["date"] if quarters else None)
        return result

    async def compute_cash_need_inputs(
        self,
        ticker: str,
        recent_raises: float = 0.0,
        _skip_dt_tables: bool = False,
    ) -> Dict[str, Any]:
        """
        Implementa la fórmula EXACTA de DilutionTracker (bundle JS):

          a = days since last_cash_date
          c = quarterly_ocf / 90 * a       (prorated CF = daily_burn × days)
          estimated_cash = historical_cash + c + recent_raises
          quarterly_ocf  (used as burn rate — c/a cancels in the rating formula)
          runway_months  = estimated_cash / (-quarterly_ocf) * 3  (if ocf < 0)

        Args:
            ticker:         Uppercase ticker symbol.
            recent_raises:  Capital raised (USD) AFTER the last balance sheet date.
                            Provided by caller from CapitalRaiseExtractor (SEC 8-K).
                            Net proceeds preferred, gross as fallback.

        Returns dict with all inputs for DilutionTrackerRiskScorer._calculate_cash_need().
        """
        # ── Primary: analyst tables dt_cash_position + dt_cash_meta ──────────
        if not _skip_dt_tables:
            try:
                from services.sec.dt_cash_service import get_dt_cash_need_inputs
                dt_inputs = await get_dt_cash_need_inputs(ticker)
                if dt_inputs:
                    # Override recent_raises with caller-provided value only if larger
                    # (caller may have fresher data from completed_offerings table)
                    if recent_raises > dt_inputs.get("recent_raises", 0):
                        dt_inputs["recent_raises"] = recent_raises
                        prorated_cf = dt_inputs.get("prorated_cf", 0)
                        hist = dt_inputs.get("historical_cash", 0)
                        est = hist + prorated_cf + recent_raises
                        dt_inputs["estimated_current_cash"] = round(est, 2)
                        ocf = dt_inputs.get("quarterly_ocf", 0)
                        if ocf < 0 and est > 0:
                            dt_inputs["runway_months"] = round((est / -ocf) * 3, 2)
                    logger.debug("cash_need_from_dt_tables", ticker=ticker,
                                 source=dt_inputs.get("source"),
                                 runway_months=dt_inputs.get("runway_months"))
                    return dt_inputs
            except Exception as dt_err:
                logger.debug("dt_cash_tables_failed_fallback_perplexity",
                             ticker=ticker, error=str(dt_err))

        # ── Fallback: Perplexity API ──────────────────────────────────────────
        summary = await self.get_cash_summary(ticker)

        _empty = {
            "runway_months": None,
            "has_positive_operating_cf": False,
            "estimated_current_cash": None,
            "annual_burn_rate": None,
            "source": "perplexity_no_data",
            "latest_date": None,
            "days_since_report": None,
        }

        if not summary or not summary.get("quarters"):
            return _empty

        # ── Step 1: Find most-recent quarter with cash > 0 (DT: last non-zero historical cash)
        historical_cash = None
        last_cash_date_str = None
        quarterly_ocf = None

        for q in summary["quarters"]:
            if q.get("cash") and q["cash"] > 0:
                if historical_cash is None:
                    historical_cash = q["cash"]
                    last_cash_date_str = q["date"]
            if quarterly_ocf is None and q.get("operating_cf") is not None:
                quarterly_ocf = q["operating_cf"]

        if historical_cash is None or last_cash_date_str is None:
            return _empty

        # ── Step 2: Days since last cash date (DT variable 'a')
        try:
            last_cash_date = datetime.strptime(last_cash_date_str, "%Y-%m-%d").date()
            days_since = (date.today() - last_cash_date).days
        except Exception:
            return _empty

        if days_since <= 0:
            days_since = 1

        # ── Step 3: Positive CF shortcut
        if quarterly_ocf is None or quarterly_ocf >= 0:
            return {
                "runway_months": None,
                "has_positive_operating_cf": True,
                "estimated_current_cash": historical_cash + recent_raises,
                "annual_burn_rate": 0,
                "source": "perplexity",
                "latest_date": last_cash_date_str,
                "days_since_report": days_since,
                "historical_cash": historical_cash,
                "recent_raises": recent_raises,
                "prorated_cf": 0,
            }

        # ── Step 4: DT formula
        #   c = quarterly_ocf / 90 * days   (prorated CF — burn acumulado desde la última BS)
        #   estimated = historical_cash + c + recent_raises
        #   quarterly_ocf is the burn rate used for runway (c/a terms cancel)
        prorated_cf = quarterly_ocf / 90 * days_since
        estimated_cash = historical_cash + prorated_cf + recent_raises

        # runway_months = estimated_cash / (-quarterly_ocf) * 3
        runway_months = (estimated_cash / -quarterly_ocf) * 3

        logger.debug(
            "cash_need_dt_formula",
            ticker=ticker,
            historical_cash=historical_cash,
            last_cash_date=last_cash_date_str,
            days_since=days_since,
            quarterly_ocf=quarterly_ocf,
            prorated_cf=round(prorated_cf, 0),
            recent_raises=recent_raises,
            estimated_cash=round(estimated_cash, 0),
            runway_months=round(runway_months, 2),
        )

        return {
            "runway_months": round(runway_months, 2),
            "has_positive_operating_cf": False,
            "estimated_current_cash": round(estimated_cash, 0),
            "annual_burn_rate": round(quarterly_ocf * 4, 0),
            "source": "perplexity",
            "latest_date": last_cash_date_str,
            "days_since_report": days_since,
            "historical_cash": historical_cash,
            "recent_raises": recent_raises,
            "prorated_cf": round(prorated_cf, 0),
            "quarterly_ocf": quarterly_ocf,
        }
