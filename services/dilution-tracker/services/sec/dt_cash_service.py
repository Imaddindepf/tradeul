"""
DT Cash Service
===============
Lee el historial de cash y los inputs para el runway desde las tablas
mantenidas por analistas:

  dt_cash_position  — cash trimestral por ticker (en millones)
  dt_cash_meta      — burn rate, raises y fecha del último reporte

Devuelve el mismo formato que el endpoint /cash-position espera,
compatible con CashRunwayData del frontend.

Fórmula DilutionTracker.com:
  daily_burn    = quarterly_op_cashflow_millions × 1M / 90
  prorated_cf   = daily_burn × days_since_last_report
  est_cash      = historical_cash + prorated_cf + recent_offerings
  runway_days   = est_cash / -daily_burn   (si burn < 0)
"""

import os
from datetime import date, datetime, timezone
from typing import Optional

import asyncpg

from shared.utils.logger import get_logger

logger = get_logger(__name__)

# Remote dilutiontracker DB
REMOTE_DB_HOST = os.getenv("DB_HOST",     "127.0.0.1")
REMOTE_DB_PORT = int(os.getenv("DB_PORT", "55433"))
REMOTE_DB_NAME = os.getenv("DB_NAME",     "dilutiontracker")
REMOTE_DB_USER = os.getenv("DB_USER",     "dilution_admin")
REMOTE_DB_PASS = os.getenv("DB_PASSWORD", "")

M = 1_000_000  # millions → dollars


def _risk_level(runway_days: Optional[float]) -> str:
    if runway_days is None:
        return "unknown"
    if runway_days < 90:
        return "critical"
    if runway_days < 180:
        return "high"
    if runway_days < 365:
        return "medium"
    return "low"


async def get_dt_cash_position(ticker: str, max_quarters: int = 40) -> Optional[dict]:
    """
    Builds the full cash-position response from dt_cash_position + dt_cash_meta.

    Returns None if the ticker has no rows in dt_cash_position.

    Response shape (matches existing /cash-position endpoint):
    {
        "source": "dt_cash_position",
        "ticker": str,
        "cash_history": [{"date": "YYYY-MM-DD", "cash": float}],   # $ not millions
        "cashflow_history": [],
        "latest_cash": float,
        "last_report_date": str,
        "latest_operating_cf": float,
        "daily_burn_rate": float,
        "days_since_report": int,
        "prorated_cf": float,
        "capital_raises": {"total": float, "count": int, "details": []},
        "estimated_current_cash": float,
        "runway_days": int | None,
        "runway_risk_level": str,
    }
    """
    ticker = ticker.upper()

    try:
        conn = await asyncpg.connect(
            host=REMOTE_DB_HOST, port=REMOTE_DB_PORT,
            user=REMOTE_DB_USER, password=REMOTE_DB_PASS,
            database=REMOTE_DB_NAME,
        )
    except Exception as exc:
        logger.error("dt_cash_service_connect_failed", ticker=ticker, error=str(exc))
        return None

    try:
        # ── 1. Historical cash quarters ──────────────────────────────────────
        rows = await conn.fetch(
            """
            SELECT period_date, cash_millions
            FROM dt_cash_position
            WHERE ticker = $1
            ORDER BY period_date ASC
            LIMIT $2
            """,
            ticker, max_quarters,
        )

        if not rows:
            return None

        cash_history = [
            {"date": str(r["period_date"]), "cash": float(r["cash_millions"]) * M}
            for r in rows
        ]

        # ── 2. Meta row ───────────────────────────────────────────────────────
        meta = await conn.fetchrow(
            "SELECT * FROM dt_cash_meta WHERE ticker = $1", ticker
        )

    finally:
        await conn.close()

    # ── 3. Build calc inputs ──────────────────────────────────────────────────
    latest = cash_history[-1]
    latest_cash: float  = latest["cash"]
    last_report_date: str = latest["date"]

    if meta and meta["last_cash_date"]:
        last_report_date = str(meta["last_cash_date"])
        # Use cash value at last_cash_date from history (more precise)
        for h in reversed(cash_history):
            if h["date"] == last_report_date:
                latest_cash = h["cash"]
                break

    quarterly_ocf: float = 0.0
    recent_raises: float = 0.0

    if meta:
        if meta["quarterly_op_cashflow_millions"] is not None:
            quarterly_ocf = float(meta["quarterly_op_cashflow_millions"]) * M
        if meta["recent_offerings_millions"] is not None:
            recent_raises = float(meta["recent_offerings_millions"]) * M

    # Days since last report
    try:
        last_date = date.fromisoformat(last_report_date)
        days_since = (date.today() - last_date).days
    except Exception:
        days_since = 0

    days_since = max(days_since, 1)

    # DT formula
    daily_burn    = quarterly_ocf / 90          # negative if burning cash
    prorated_cf   = daily_burn * days_since
    est_cash      = latest_cash + prorated_cf + recent_raises

    runway_days: Optional[int] = None
    if daily_burn < 0 and est_cash > 0:
        runway_days = int(est_cash / -daily_burn)
    elif daily_burn < 0 and est_cash <= 0:
        runway_days = 0

    logger.debug(
        "dt_cash_position_built",
        ticker=ticker,
        latest_cash=round(latest_cash / M, 2),
        quarterly_ocf_m=round(quarterly_ocf / M, 2),
        days_since=days_since,
        prorated_cf_m=round(prorated_cf / M, 2),
        recent_raises_m=round(recent_raises / M, 2),
        est_cash_m=round(est_cash / M, 2),
        runway_days=runway_days,
        quarters=len(cash_history),
    )

    return {
        "source":               "dt_cash_position",
        "ticker":               ticker,
        "cash_history":         cash_history,
        "cashflow_history":     [],
        "latest_cash":          latest_cash,
        "last_report_date":     last_report_date,
        "latest_operating_cf":  quarterly_ocf,
        "daily_burn_rate":      daily_burn,
        "days_since_report":    days_since,
        "prorated_cf":          round(prorated_cf, 2),
        "capital_raises": {
            "total":   recent_raises,
            "count":   1 if recent_raises > 0 else 0,
            "details": [],
        },
        "estimated_current_cash": round(est_cash, 2),
        "runway_days":          runway_days,
        "runway_risk_level":    _risk_level(runway_days),
    }


async def get_dt_cash_need_inputs(ticker: str) -> Optional[dict]:
    """
    Returns the inputs needed by PerplexityCashService.compute_cash_need_inputs()
    reading from dt_cash_position + dt_cash_meta instead of Perplexity.

    Returns None if ticker not in dt_cash_position.

    Shape:
    {
        "runway_months": float | None,
        "has_positive_operating_cf": bool,
        "estimated_current_cash": float,
        "annual_burn_rate": float,
        "source": "dt_cash_position",
        "latest_date": str,
        "days_since_report": int,
        "historical_cash": float,
        "recent_raises": float,
        "prorated_cf": float,
        "quarterly_ocf": float,
    }
    """
    result = await get_dt_cash_position(ticker, max_quarters=40)
    if not result:
        return None

    quarterly_ocf  = result["latest_operating_cf"]
    prorated_cf    = result["prorated_cf"]
    recent_raises  = result["capital_raises"]["total"]
    est_cash       = result["estimated_current_cash"]
    days_since     = result["days_since_report"]
    latest_date    = result["last_report_date"]
    historical_cash = result["latest_cash"]

    has_positive_cf = quarterly_ocf >= 0

    runway_months: Optional[float] = None
    if result["runway_days"] is not None:
        runway_months = round(result["runway_days"] / 30, 2)

    return {
        "runway_months":            runway_months,
        "has_positive_operating_cf": has_positive_cf,
        "estimated_current_cash":   round(est_cash, 2),
        "annual_burn_rate":         round(quarterly_ocf * 4, 2),
        "source":                   "dt_cash_position",
        "latest_date":              latest_date,
        "days_since_report":        days_since,
        "historical_cash":          historical_cash,
        "recent_raises":            recent_raises,
        "prorated_cf":              prorated_cf,
        "quarterly_ocf":            quarterly_ocf,
    }
