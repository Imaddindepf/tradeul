"""
Perplexity Finance v3 — Symbiotic Financials Transformer
========================================================
Fetches financials directly from Perplexity's v3 endpoint (same source that
powers https://www.perplexity.ai/finance/<TICKER>/financials) and converts the
raw payload into the SymbioticFinancialData shape that the frontend's
FinancialsContent / SymbioticTable components expect.

This avoids the slow XBRL pipeline of the old `financials` microservice and
gives us the same data the user sees on the Perplexity finance tab, including
rich segment / KPI breakdowns (Bitcoin mining, AI cloud, GPUs, MW, etc.).

Endpoints proxied:
    https://www.perplexity.ai/rest/finance/financials/v3/<TICKER>?period=quarter
    https://www.perplexity.ai/rest/finance/financials/v3/<TICKER>?period=annual
    https://www.perplexity.ai/rest/finance/financials/v3/<TICKER>?period=ttm

Public API of this module:
    fetch_v3(ticker, period)       → raw v3 JSON (with in-memory cache)
    transform_to_symbiotic(...)     → SymbioticFinancialData dict
    transform_segments(...)         → segments + KPIs in SegmentsTable shape
"""

from __future__ import annotations

import asyncio
import re
import time
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Tuple

from shared.utils.logger import get_logger

logger = get_logger(__name__)

# ---------------------------------------------------------------------------
# HTTP fetching (curl_cffi with Chrome impersonation + retries)
# ---------------------------------------------------------------------------

_BASE_URL = "https://www.perplexity.ai/rest/finance/financials/v3"
_BASE_HEADERS = {
    "Accept": "application/json, text/plain, */*",
    "Accept-Language": "en-US,en;q=0.9",
    "Origin": "https://www.perplexity.ai",
    "Sec-Fetch-Dest": "empty",
    "Sec-Fetch-Mode": "cors",
    "Sec-Fetch-Site": "same-origin",
}

_IMPERSONATE_TARGETS = ("chrome", "chrome120", "chrome124", "chrome110", "safari17_0")

_cffi_session = None


def _get_session(target: str = "chrome"):
    global _cffi_session
    if _cffi_session is None:
        from curl_cffi import requests as cffi_requests
        _cffi_session = cffi_requests.Session(impersonate=target)
    return _cffi_session


def _fetch_v3_sync(ticker: str, period: str, wide: bool = True) -> Optional[Dict[str, Any]]:
    """Blocking fetch with Cloudflare-resilient retries. Returns parsed JSON or None.

    `wide=True` requests an explicit fiscal-year window to pull long history
    (actuals only — Perplexity drops forward estimate rows when a window is
    supplied). `wide=False` omits the window, which returns only the ~4 most
    recent periods *plus* the forward analyst-estimate rows (isEstimate=true).
    The two are merged by `fetch_v3_with_estimates` for the key_stats block.
    """
    from curl_cffi import requests as cffi_requests

    global _cffi_session

    headers = {
        **_BASE_HEADERS,
        "Referer": f"https://www.perplexity.ai/finance/{ticker}/financials",
    }

    # Perplexity v3 only returns the 4 most recent periods unless an explicit
    # fiscal-year window is supplied. Request a wide range so we have enough
    # history; the API clamps to the data it actually has (e.g. AAPL → 2005+),
    # and routes/financials.py trims to the caller's `limit`.
    current_year = time.gmtime().tm_year
    p = (period or "").lower()
    params = [f"period={period}"]
    if wide and p.startswith("annual"):
        params.append(f"start_fiscal_year={current_year - 30}")
        params.append(f"end_fiscal_year={current_year + 1}")
    elif wide and p.startswith("quarter"):
        params.append(f"start_fiscal_year={current_year - 10}")
        params.append(f"end_fiscal_year={current_year + 1}")
    # ttm (and wide=False): single/no range — estimates included when wide=False
    url = f"{_BASE_URL}/{ticker}?{'&'.join(params)}"

    # First try the persistent session
    try:
        session = _get_session()
        resp = session.get(url, timeout=20, headers=headers)
        if resp.status_code == 200:
            return resp.json()
    except Exception:  # pragma: no cover - defensive
        pass

    # Rotate impersonation targets if blocked
    for target in _IMPERSONATE_TARGETS:
        try:
            _cffi_session = cffi_requests.Session(impersonate=target)
            resp = _cffi_session.get(url, timeout=20, headers=headers)
            if resp.status_code == 200:
                return resp.json()
        except Exception:
            continue

    _cffi_session = cffi_requests.Session(impersonate="chrome")
    return None


# ---------------------------------------------------------------------------
# In-memory cache
# ---------------------------------------------------------------------------

# BoundedTTLCache: payloads JSON de financials (200KB-1MB por ticker) sin
# evicción contribuian al OOM cronico del proceso.
from bounded_cache import BoundedTTLCache

CACHE_TTL_SECONDS = 60 * 60 * 4  # 4 hours
_cache = BoundedTTLCache(maxsize=256, ttl_seconds=CACHE_TTL_SECONDS)


async def fetch_v3(ticker: str, period: str = "quarter", wide: bool = True) -> Optional[Dict[str, Any]]:
    """Async wrapper around the blocking fetch, with cache."""
    ticker = ticker.upper().strip()
    period = (period or "quarter").lower()
    key = f"{ticker}:{period}" if wide else f"{ticker}:{period}:est"
    cached = _cache.get(key)
    if cached is not None:
        return cached

    data = await asyncio.to_thread(_fetch_v3_sync, ticker, period, wide)
    if data is not None:
        _cache.set(key, data)
    return data


async def fetch_v3_with_estimates(ticker: str, period: str = "quarter") -> Optional[Dict[str, Any]]:
    """Fetch the wide (long-history) payload and merge forward analyst-estimate
    rows into its `key_stats` block.

    Perplexity returns either long history (with a fiscal-year window, actuals
    only) or forward estimates (without a window, short history). We fetch both
    and splice the estimate rows — which only exist on `key_stats` — onto the
    historical payload so the key-stats table can show actuals *and* forward
    consensus (FY/quarter estimates) at once.
    """
    period = (period or "quarter").lower()
    wide = await fetch_v3(ticker, period, wide=True)
    if not wide:
        return wide
    # ttm is a single trailing period — no forward estimates to merge.
    if period.startswith("ttm"):
        return wide

    narrow = await fetch_v3(ticker, period, wide=False)
    if not narrow:
        return wide

    is_annual = period.startswith("annual")
    hist_rows = list(wide.get("key_stats") or [])
    seen = {_period_label(r, is_annual) for r in hist_rows}
    estimate_rows = [
        r for r in (narrow.get("key_stats") or [])
        if r.get("isEstimate") and _period_label(r, is_annual) not in seen
    ]
    if estimate_rows:
        # Shallow-copy so the cached wide payload is not mutated in place.
        merged = dict(wide)
        merged["key_stats"] = hist_rows + estimate_rows
        return merged
    return wide


def clear_cache(ticker: Optional[str] = None) -> int:
    """Clear cached v3 payloads. Returns the number of keys removed."""
    if ticker is None:
        removed = len(_cache)
        _cache.clear()
        return removed
    ticker = ticker.upper().strip()
    prefix = f"{ticker}:"
    keys = [k for k in _cache.keys() if k.startswith(prefix)]
    for k in keys:
        _cache.pop(k, None)
    return len(keys)


# ---------------------------------------------------------------------------
# Field maps: Perplexity v3 canonical key → frontend ConsolidatedField metadata
# ---------------------------------------------------------------------------
# Tuple format:
#   (perp_key, canonical_key, label, section, importance, display_order,
#    indent_level, is_subtotal, balance, data_type)
#
# - importance: 0-100 (higher = more important; frontend uses it for highlighting/ordering)
# - balance: "debit" => red colour (expenses, debt, liabilities), None => default
# - data_type: "monetary" | "percent" | "perShare" | "shares"

_FieldRow = Tuple[str, str, str, str, int, int, int, bool, Optional[str], str]


INCOME_FIELD_MAP: List[_FieldRow] = [
    # Revenue
    ("income_statement_total_revenues",        "revenue",                "Total Revenue",                "Revenue", 100, 100, 0, True,  None,    "monetary"),
    ("income_statement_other_revenues",        "other_revenue",          "Other Revenue",                "Revenue",  60, 110, 1, False, None,    "monetary"),

    # Cost & Gross Profit
    ("income_statement_cost_of_sales",         "cost_of_revenue",        "Cost of Revenue",              "Cost & Gross Profit",  95, 200, 0, False, "debit", "monetary"),
    ("income_statement_gross_profit",          "gross_profit",           "Gross Profit",                 "Cost & Gross Profit",  93, 210, 0, True,  None,    "monetary"),
    ("ratio_gross_profit_margin",              "gross_profit_margin",    "Gross Profit Margin",          "Cost & Gross Profit",  92, 211, 1, False, None,    "percent"),

    # Operating Expenses
    ("income_statement_research_and_development_expenses",         "rd_expenses",                  "Research & Development",        "Operating Expenses", 89, 300, 1, False, "debit", "monetary"),
    ("income_statement_selling_general_and_administrative_expenses","sga_expenses",                 "Selling, General & Admin.",     "Operating Expenses", 89, 310, 1, False, "debit", "monetary"),
    ("income_statement_selling_and_marketing_expenses",            "selling_marketing",            "Selling & Marketing",           "Operating Expenses", 85, 320, 1, False, "debit", "monetary"),
    ("income_statement_general_and_administrative_expenses",       "general_administrative",       "General & Administrative",      "Operating Expenses", 85, 330, 1, False, "debit", "monetary"),
    ("income_statement_depreciation_and_amortization_expenses",    "depreciation_amortization",    "Depreciation & Amortization",   "Operating Expenses", 83, 340, 1, False, "debit", "monetary"),
    ("income_statement_compensation_expenses",                     "compensation",                 "Compensation Expense",          "Operating Expenses", 70, 350, 1, False, "debit", "monetary"),
    ("income_statement_other_operating_expenses",                  "other_operating_expenses",     "Other Operating Expenses",      "Operating Expenses", 70, 360, 1, False, "debit", "monetary"),

    # Operating Income
    ("income_statement_operating_profit",      "operating_income",       "Operating Income",             "Operating Income",     90, 400, 0, True,  None,    "monetary"),
    ("ratio_operating_margin",                 "operating_margin",       "Operating Margin",             "Operating Income",     88, 401, 1, False, None,    "percent"),
    ("ratio_ebitda_margin",                    "ebitda_margin",          "EBITDA Margin",                "Operating Income",     85, 402, 1, False, None,    "percent"),

    # Non-Operating
    ("income_statement_interest_income",       "interest_income",        "Interest Income",              "Non-Operating",        75, 500, 1, False, None,    "monetary"),
    ("income_statement_interest_expense",      "interest_expense",       "Interest Expense",             "Non-Operating",        80, 510, 1, False, "debit", "monetary"),
    ("income_statement_non_operating_income",  "other_nonoperating",     "Other Non-Operating Income",   "Non-Operating",        65, 520, 1, False, None,    "monetary"),
    ("income_statement_non_operating_income_or_expense", "total_nonoperating", "Total Non-Operating Income / (Expense)", "Non-Operating", 70, 530, 0, True, None, "monetary"),

    # Earnings
    ("income_statement_income_before_provision_for_income_taxes",  "income_before_tax",                  "Income Before Taxes",            "Earnings", 80, 600, 0, True,  None,    "monetary"),
    ("income_statement_provision_for_income_taxes",                "income_tax_provision",               "Income Tax Provision",            "Earnings", 75, 610, 1, False, "debit", "monetary"),
    ("ratio_effective_tax_rate",                                   "effective_tax_rate",                 "Effective Tax Rate",              "Earnings", 70, 611, 2, False, None,    "percent"),
    ("income_statement_consolidated_net_income",                   "consolidated_net_income",            "Consolidated Net Income",         "Earnings", 92, 620, 0, True,  None,    "monetary"),
    ("income_statement_net_income_attributable_to_minority_interests_and_other", "minority_interest_share", "Minority Interest", "Earnings", 60, 625, 1, False, None, "monetary"),
    ("income_statement_net_income_attributable_to_common_shareholders", "net_income",                    "Net Income (to Common)",          "Earnings", 95, 630, 0, True,  None,    "monetary"),
    ("ratio_net_profit_margin",                                    "net_profit_margin",                  "Net Profit Margin",               "Earnings", 90, 631, 1, False, None,    "percent"),

    # Per-Share Data
    ("income_statement_basic_eps",                                  "eps_basic",          "Basic EPS",                     "Per Share Data", 90, 700, 0, False, None, "perShare"),
    ("income_statement_diluted_eps",                                "eps_diluted",        "Diluted EPS",                   "Per Share Data", 92, 710, 0, False, None, "perShare"),
    ("income_statement_basic_weighted_average_shares_outstanding",  "shares_basic",       "Weighted Avg. Shares — Basic",  "Per Share Data", 70, 720, 0, False, None, "shares"),
    ("income_statement_diluted_weighted_average_shares_outstanding","shares_diluted",     "Weighted Avg. Shares — Diluted","Per Share Data", 72, 730, 0, False, None, "shares"),
]


BALANCE_FIELD_MAP: List[_FieldRow] = [
    # Current Assets
    ("balance_sheet_cash_and_cash_equivalents",       "cash_and_equivalents",        "Cash & Cash Equivalents",       "Current Assets", 95, 100, 0, False, None,    "monetary"),
    ("balance_sheet_short_term_investments",          "short_term_investments",      "Short-Term Investments",         "Current Assets", 88, 110, 0, False, None,    "monetary"),
    ("balance_sheet_total_cash_and_cash_equivalents", "total_cash",                  "Total Cash + Short-Term Inv.",   "Current Assets", 90, 115, 0, True,  None,    "monetary"),
    ("balance_sheet_accounts_receivable",             "accounts_receivable",         "Accounts Receivable",            "Current Assets", 85, 120, 0, False, None,    "monetary"),
    ("balance_sheet_other_receivables",               "other_receivables",           "Other Receivables",              "Current Assets", 70, 125, 1, False, None,    "monetary"),
    ("balance_sheet_total_trade_receivables",         "total_receivables",           "Total Trade Receivables",        "Current Assets", 80, 128, 0, True,  None,    "monetary"),
    ("balance_sheet_inventories",                     "inventories",                 "Inventories",                    "Current Assets", 85, 130, 0, False, None,    "monetary"),
    ("balance_sheet_other_current_assets",            "other_current_assets",        "Other Current Assets",           "Current Assets", 70, 140, 0, False, None,    "monetary"),
    ("balance_sheet_total_current_assets",            "total_current_assets",        "Total Current Assets",           "Current Assets", 93, 190, 0, True,  None,    "monetary"),

    # Non-Current Assets
    ("balance_sheet_net_property_plant_and_equipment","ppe_net",                     "Property, Plant & Equipment, Net","Non-Current Assets", 90, 200, 0, False, None, "monetary"),
    ("balance_sheet_goodwill",                        "goodwill",                    "Goodwill",                       "Non-Current Assets", 80, 210, 0, False, None,    "monetary"),
    ("balance_sheet_net_intangible_assets",           "intangibles_net",             "Intangible Assets, Net",         "Non-Current Assets", 80, 215, 0, False, None,    "monetary"),
    ("balance_sheet_long_term_investments",           "long_term_investments",       "Long-Term Investments",          "Non-Current Assets", 78, 220, 0, False, None,    "monetary"),
    ("balance_sheet_other_long_term_assets",          "other_long_term_assets",      "Other Long-Term Assets",         "Non-Current Assets", 65, 230, 0, False, None,    "monetary"),
    ("balance_sheet_total_assets",                    "total_assets",                "Total Assets",                   "Non-Current Assets", 95, 290, 0, True,  None,    "monetary"),

    # Current Liabilities
    ("balance_sheet_accounts_payable",                "accounts_payable",            "Accounts Payable",               "Current Liabilities", 85, 300, 0, False, "debit", "monetary"),
    ("balance_sheet_short_term_debt",                 "short_term_debt",             "Short-Term Debt",                "Current Liabilities", 88, 310, 0, False, "debit", "monetary"),
    ("balance_sheet_current_portion_of_leases",       "current_lease_liabilities",   "Current Lease Liabilities",      "Current Liabilities", 70, 315, 0, False, "debit", "monetary"),
    ("balance_sheet_unearned_revenue",                "deferred_revenue",            "Deferred Revenue",               "Current Liabilities", 72, 320, 0, False, "debit", "monetary"),
    ("balance_sheet_other_current_liabilities",       "other_current_liabilities",   "Other Current Liabilities",       "Current Liabilities", 65, 330, 0, False, "debit", "monetary"),
    ("balance_sheet_total_current_liabilities",       "total_current_liabilities",   "Total Current Liabilities",      "Current Liabilities", 92, 390, 0, True,  "debit", "monetary"),

    # Non-Current Liabilities
    ("balance_sheet_long_term_debt",                  "long_term_debt",              "Long-Term Debt",                 "Non-Current Liabilities", 92, 400, 0, False, "debit", "monetary"),
    ("balance_sheet_leases",                          "long_term_leases",            "Long-Term Lease Liabilities",    "Non-Current Liabilities", 75, 410, 0, False, "debit", "monetary"),
    ("balance_sheet_other_long_term_liabilities",     "other_long_term_liabilities", "Other Long-Term Liabilities",    "Non-Current Liabilities", 65, 420, 0, False, "debit", "monetary"),
    ("balance_sheet_total_long_term_liabilities",     "total_long_term_liabilities", "Total Non-Current Liabilities",  "Non-Current Liabilities", 92, 480, 0, True,  "debit", "monetary"),
    ("balance_sheet_total_liabilities",               "total_liabilities",           "Total Liabilities",              "Non-Current Liabilities", 95, 490, 0, True,  "debit", "monetary"),

    # Equity
    ("balance_sheet_common_stock",                    "common_stock",                "Common Stock",                   "Equity", 75, 500, 0, False, None, "monetary"),
    ("balance_sheet_preferred_stock",                 "preferred_stock",             "Preferred Stock",                "Equity", 65, 510, 0, False, None, "monetary"),
    ("balance_sheet_additional_paid_in_capital",      "additional_paid_in_capital",  "Additional Paid-In Capital",     "Equity", 75, 520, 0, False, None, "monetary"),
    ("balance_sheet_retained_earnings",               "retained_earnings",           "Retained Earnings",              "Equity", 85, 530, 0, False, None, "monetary"),
    ("balance_sheet_accumulated_other_comprehensive_income", "aoci",                 "Accumulated OCI",                "Equity", 60, 540, 0, False, None, "monetary"),
    ("balance_sheet_total_common_shareholders_equity","common_equity",               "Total Common Equity",            "Equity", 90, 580, 0, True,  None, "monetary"),
    ("balance_sheet_total_shareholders_equity",       "total_equity",                "Total Shareholders' Equity",     "Equity", 93, 585, 0, True,  None, "monetary"),
    ("balance_sheet_total_liabilities_and_shareholders_equity", "total_liab_and_equity", "Total Liabilities + Equity", "Equity", 95, 590, 0, True,  None, "monetary"),
]


CASHFLOW_FIELD_MAP: List[_FieldRow] = [
    # Operating Activities
    ("cash_flow_statement_net_income",                              "net_income_cf",              "Net Income",                       "Operating Activities", 90, 100, 0, False, None,    "monetary"),
    ("cash_flow_statement_depreciation_and_amortization",           "depreciation_amortization_cf","Depreciation & Amortization",      "Operating Activities", 88, 110, 1, False, None,    "monetary"),
    ("cash_flow_statement_share_based_compensation_expense",        "stock_based_compensation",    "Stock-Based Compensation",         "Operating Activities", 82, 120, 1, False, None,    "monetary"),
    ("cash_flow_statement_changes_in_trade_receivables",            "delta_receivables",           "Δ Receivables",                    "Operating Activities", 75, 130, 1, False, None,    "monetary"),
    ("cash_flow_statement_changes_in_inventories",                  "delta_inventories",           "Δ Inventories",                    "Operating Activities", 70, 135, 1, False, None,    "monetary"),
    ("cash_flow_statement_changes_in_accounts_payable",             "delta_payables",              "Δ Accounts Payable",               "Operating Activities", 75, 140, 1, False, None,    "monetary"),
    ("cash_flow_statement_changes_in_accrued_expenses",             "delta_accrued",               "Δ Accrued Expenses",               "Operating Activities", 65, 145, 1, False, None,    "monetary"),
    ("cash_flow_statement_changes_in_unearned_revenue",             "delta_deferred_revenue",      "Δ Deferred Revenue",               "Operating Activities", 70, 150, 1, False, None,    "monetary"),
    ("cash_flow_statement_changes_in_income_taxes_payable",         "delta_income_taxes",          "Δ Income Taxes Payable",           "Operating Activities", 65, 155, 1, False, None,    "monetary"),
    ("cash_flow_statement_other_adjustments",                       "other_op_adjustments",        "Other Operating Adjustments",      "Operating Activities", 60, 165, 1, False, None,    "monetary"),
    ("cash_flow_statement_changes_in_other_operating_activities",   "delta_other_op",              "Δ Other Operating Items",          "Operating Activities", 55, 170, 1, False, None,    "monetary"),
    ("cash_flow_statement_cash_from_operating_activities",          "cash_from_operations",        "Net Cash From Operating Activities","Operating Activities", 95, 190, 0, True,  None,    "monetary"),

    # Investing Activities
    ("cash_flow_statement_purchases_of_property_plant_and_equipment","capex",                      "Capital Expenditures",             "Investing Activities", 92, 200, 0, False, "debit", "monetary"),
    ("cash_flow_statement_proceeds_from_sale_of_property_plant_and_equipment","proceeds_ppe",      "Proceeds from PP&E Sales",         "Investing Activities", 70, 210, 1, False, None,    "monetary"),
    ("cash_flow_statement_purchases_of_intangible_assets",          "purchases_intangibles",       "Purchases of Intangibles",         "Investing Activities", 70, 215, 1, False, "debit", "monetary"),
    ("cash_flow_statement_purchases_of_investments",                "purchases_investments",       "Purchases of Investments",         "Investing Activities", 70, 220, 1, False, "debit", "monetary"),
    ("cash_flow_statement_proceeds_from_sale_of_investments",       "proceeds_investments",        "Proceeds from Investments",        "Investing Activities", 70, 225, 1, False, None,    "monetary"),
    ("cash_flow_statement_payments_for_business_acquisitions",      "acquisitions",                "Business Acquisitions",            "Investing Activities", 75, 230, 1, False, "debit", "monetary"),
    ("cash_flow_statement_proceeds_from_business_divestments",      "divestments",                 "Business Divestments",             "Investing Activities", 65, 235, 1, False, None,    "monetary"),
    ("cash_flow_statement_other_investing_activities",              "other_investing",             "Other Investing Activities",       "Investing Activities", 60, 240, 1, False, None,    "monetary"),
    ("cash_flow_statement_cash_from_investing_activities",          "cash_from_investing",         "Net Cash From Investing Activities","Investing Activities", 92, 290, 0, True,  None,    "monetary"),

    # Financing Activities
    ("cash_flow_statement_issuance_of_long_term_debt",              "issuance_lt_debt",            "Long-Term Debt Issued",            "Financing Activities", 82, 300, 1, False, None,    "monetary"),
    ("cash_flow_statement_repayments_of_long_term_debt",            "repayments_lt_debt",          "Long-Term Debt Repaid",            "Financing Activities", 82, 310, 1, False, "debit", "monetary"),
    ("cash_flow_statement_net_issuance_or_repayments_of_long_term_debt", "net_lt_debt",            "Net Long-Term Debt",               "Financing Activities", 85, 315, 0, True,  None,    "monetary"),
    ("cash_flow_statement_issuance_of_short_term_debt",             "issuance_st_debt",            "Short-Term Debt Issued",           "Financing Activities", 70, 320, 1, False, None,    "monetary"),
    ("cash_flow_statement_repayments_of_short_term_debt",           "repayments_st_debt",          "Short-Term Debt Repaid",           "Financing Activities", 70, 325, 1, False, "debit", "monetary"),
    ("cash_flow_statement_issuance_of_common_shares",               "common_shares_issued",        "Common Shares Issued",             "Financing Activities", 88, 330, 1, False, None,    "monetary"),
    ("cash_flow_statement_repurchases_of_common_shares",            "common_shares_repurchased",   "Common Shares Repurchased",        "Financing Activities", 88, 335, 1, False, "debit", "monetary"),
    ("cash_flow_statement_net_issuance_or_repurchases_of_common_shares", "net_common_shares",      "Net Common Share Activity",        "Financing Activities", 90, 340, 0, True,  None,    "monetary"),
    ("cash_flow_statement_issuance_of_preferred_shares",            "preferred_shares_issued",     "Preferred Shares Issued",          "Financing Activities", 60, 345, 1, False, None,    "monetary"),
    ("cash_flow_statement_repurchases_of_preferred_shares",         "preferred_shares_repurchased","Preferred Shares Repurchased",     "Financing Activities", 60, 350, 1, False, "debit", "monetary"),
    ("cash_flow_statement_net_issuance_or_repurchases_of_preferred_shares", "net_preferred_shares","Net Preferred Share Activity",     "Financing Activities", 65, 355, 0, True,  None,    "monetary"),
    ("cash_flow_statement_common_share_dividends_paid",             "dividends_common",            "Common Dividends Paid",            "Financing Activities", 80, 360, 1, False, "debit", "monetary"),
    ("cash_flow_statement_preferred_share_dividends_paid",          "dividends_preferred",         "Preferred Dividends Paid",         "Financing Activities", 60, 365, 1, False, "debit", "monetary"),
    ("cash_flow_statement_other_financing_activities",              "other_financing",             "Other Financing Activities",       "Financing Activities", 60, 380, 1, False, None,    "monetary"),
    ("cash_flow_statement_cash_from_financing_activities",          "cash_from_financing",         "Net Cash From Financing Activities","Financing Activities", 92, 390, 0, True,  None,    "monetary"),

    # Summary / Free Cash Flow
    ("cash_flow_statement_effect_of_exchange_rate_changes_on_cash_and_cash_equivalents", "fx_effect_on_cash", "FX Effect on Cash", "Free Cash Flow", 50, 400, 1, False, None, "monetary"),
    ("cash_flow_statement_increase_or_decrease_in_cash_cash_equivalents_and_restricted_cash", "net_change_in_cash", "Net Change in Cash", "Free Cash Flow", 88, 410, 0, True, None, "monetary"),
]


# Fields that come from the `ratios[]` / `key_stats[]` blocks of the v3 payload
# instead of the income/balance/cashflow blocks. We surface them on the cash-flow
# tab because that's where Free Cash Flow naturally belongs.
_RATIO_FIELDS_FOR_CASHFLOW: List[_FieldRow] = [
    ("calculated_fcf",       "free_cash_flow", "Free Cash Flow",      "Free Cash Flow", 95, 420, 0, True,  None, "monetary"),
    ("ratio_fcf_margin",     "fcf_margin",     "Free Cash Flow Margin","Free Cash Flow", 85, 421, 1, False, None, "percent"),
]


# ---------------------------------------------------------------------------
# Period label helpers
# ---------------------------------------------------------------------------


def _period_label(row: Dict[str, Any], is_annual: bool) -> Optional[str]:
    """
    Turn a v3 statement row into a period string the frontend understands.

    - Annual  -> "2025"        (rendered as FY2025 in the table header)
    - Quarter -> "Q3 2025"     (rendered verbatim, slider uses last 2 chars)
    """
    year = row.get("fiscalYear")
    if year is None:
        date = row.get("date") or ""
        if len(date) >= 4 and date[:4].isdigit():
            year = int(date[:4])
        else:
            return None

    if is_annual:
        return str(year)

    q = row.get("fiscalQuarter")
    if q in (1, 2, 3, 4):
        return f"Q{q} {year}"

    # Fallback: derive quarter from month
    date = row.get("date") or ""
    if len(date) >= 7 and date[5:7].isdigit():
        month = int(date[5:7])
        q = (month - 1) // 3 + 1
        return f"Q{q} {year}"
    return str(year)


def _build_period_index(rows: List[Dict[str, Any]], is_annual: bool) -> Tuple[List[str], Dict[str, int]]:
    """
    Build the canonical period axis (newest-first) plus an index that maps each
    raw row's period label to its column position.
    """
    labelled: List[Tuple[str, str]] = []  # (period_label, date)
    for row in rows:
        label = _period_label(row, is_annual)
        if not label:
            continue
        labelled.append((label, row.get("date") or ""))

    # Deduplicate, keeping the newest occurrence per label
    seen: Dict[str, str] = {}
    for label, date in labelled:
        if label not in seen or date > seen[label]:
            seen[label] = date

    # Sort newest first by `date`
    ordered = sorted(seen.items(), key=lambda kv: kv[1], reverse=True)
    periods = [label for label, _ in ordered]
    return periods, {label: idx for idx, label in enumerate(periods)}


# ---------------------------------------------------------------------------
# Core transform
# ---------------------------------------------------------------------------


def _materialize(
    rows: List[Dict[str, Any]],
    extra_lookup: Dict[str, List[Dict[str, Any]]],
    field_map: List[_FieldRow],
    period_index: Dict[str, int],
    is_annual: bool,
) -> List[Dict[str, Any]]:
    """Build a list of ConsolidatedField dicts from raw rows + field map."""
    if not period_index:
        return []

    column_count = len(period_index)

    # Index extra blocks (ratios, key_stats) by period label for sidecar lookups
    extra_indexed: Dict[str, Dict[str, Dict[str, Any]]] = {}
    for block_name, block_rows in extra_lookup.items():
        idx: Dict[str, Dict[str, Any]] = {}
        for row in block_rows or []:
            label = _period_label(row, is_annual)
            if label:
                idx[label] = row
        extra_indexed[block_name] = idx

    # Index the primary rows by period label so we can resolve any period the
    # axis knows about, even if the source list is empty (e.g. FCF lives only
    # on the `ratios` block).
    primary_indexed: Dict[str, Dict[str, Any]] = {}
    for row in rows:
        label = _period_label(row, is_annual)
        if label and label in period_index:
            primary_indexed[label] = row

    fields: List[Dict[str, Any]] = []

    for (perp_key, canon_key, label, section, importance, display_order,
         indent, is_subtotal, balance, data_type) in field_map:

        values: List[Optional[float]] = [None] * column_count
        has_value = False

        for period_label, col in period_index.items():
            value: Optional[float] = None
            primary = primary_indexed.get(period_label)
            if primary is not None:
                value = primary.get(perp_key)

            if value is None:
                for block_name in ("ratios", "key_stats", "adjusted_metrics"):
                    sidecar = extra_indexed.get(block_name, {}).get(period_label)
                    if sidecar is not None and sidecar.get(perp_key) is not None:
                        value = sidecar.get(perp_key)
                        break

            if value is not None:
                values[col] = value
                has_value = True

        if not has_value:
            continue

        fields.append({
            "key": canon_key,
            "label": label,
            "values": values,
            "importance": importance,
            "source_fields": [perp_key],
            "data_type": data_type,
            "balance": balance,
            "section": section,
            "display_order": display_order,
            "indent_level": indent,
            "is_subtotal": is_subtotal,
        })

    # Stable sort by (section order is handled by the frontend, but we sort by
    # display_order within section so the table renders deterministically).
    fields.sort(key=lambda f: (f.get("section", ""), f.get("display_order", 0)))
    return fields


def transform_to_symbiotic(
    ticker: str,
    period: str,
    payload: Dict[str, Any],
    *,
    currency_fallback: str = "USD",
) -> Optional[Dict[str, Any]]:
    """
    Convert a Perplexity v3 JSON payload into the SymbioticFinancialData dict
    that FinancialsContent / SymbioticTable consume.
    """
    if not payload:
        return None

    is_annual = (period or "").lower().startswith("annual")

    income_rows = payload.get("income_statement") or []
    balance_rows = payload.get("balance_sheet") or []
    cashflow_rows = payload.get("cash_flow") or []
    ratios_rows = payload.get("ratios") or []
    key_stats_rows = payload.get("key_stats") or []

    # Build the union of all periods seen across statements so the frontend has
    # a single coherent column axis.
    all_rows = income_rows + balance_rows + cashflow_rows
    periods, period_index = _build_period_index(all_rows, is_annual)
    if not periods:
        return None

    # Pull currency from the first statement that exposes it
    currency = currency_fallback
    for row in all_rows:
        c = row.get("reportedCurrency")
        if c:
            currency = c
            break

    extras = {"ratios": ratios_rows, "key_stats": key_stats_rows}

    income = _materialize(income_rows, extras, INCOME_FIELD_MAP, period_index, is_annual)
    balance = _materialize(balance_rows, extras, BALANCE_FIELD_MAP, period_index, is_annual)
    cashflow = _materialize(cashflow_rows, extras, CASHFLOW_FIELD_MAP, period_index, is_annual)
    # Free Cash Flow / FCF margin live on the ratios block
    cashflow += _materialize([], extras, _RATIO_FIELDS_FOR_CASHFLOW, period_index, is_annual)
    cashflow.sort(key=lambda f: (f.get("section", ""), f.get("display_order", 0)))

    return {
        "symbol": ticker.upper(),
        "currency": currency,
        "industry": None,
        "sector": None,
        "source": "perplexity_v3",
        "symbiotic": True,
        "periods": periods,
        "income_statement": income,
        "balance_sheet": balance,
        "cash_flow": cashflow,
        "last_updated": datetime.now(timezone.utc).isoformat(),
    }


# ---------------------------------------------------------------------------
# Ratios / Adjusted Metrics / Key Statistics transforms
#
# These three blocks come from the SAME v3 payload we already fetch for the
# statements, so they add zero extra network cost. Unlike income/balance/cash
# (which need hand-maintained field maps), ratios and adjusted_metrics ship with
# their own metadata (metricName, metricFormat, category) so we render them
# dynamically. Key stats has no metadata block, so we curate a small list.
#
# All three return the same envelope shape the frontend's SymbioticTable
# consumes: {symbol, currency, period, periods, estimate_periods, fields[]}.
# ---------------------------------------------------------------------------

# Day-count ratios that must render as plain numbers, not "x" multiples.
_DAYS_RATIOS = {
    "ratio_dso", "ratio_dpo", "ratio_dio",
    "ratio_cash_conversion_cycle", "ratio_operating_cycle",
}

# Perplexity's ratio categories → table section names. We rename a couple to
# avoid clashing with the income/balance/cashflow section ordering and the
# frontend's hidden "Other" section.
_RATIO_SECTION_REMAP = {
    "Other": "Key Figures",
    "Per Share": "Per-Share Ratios",
}


def _currency_from_payload(payload: Dict[str, Any], fallback: str = "USD") -> str:
    for block in ("key_stats", "adjusted_metrics", "income_statement",
                  "balance_sheet", "cash_flow"):
        for row in payload.get(block) or []:
            cur = row.get("reportedCurrency")
            if cur:
                return cur
    return fallback


def _ratio_data_type(ratio_id: str, metric_format: Optional[str], is_currency: bool) -> str:
    fmt = (metric_format or "").strip().lower()
    if fmt == "%":
        return "percent"
    if ratio_id in _DAYS_RATIOS:
        return "number"
    if fmt == "ratio":
        return "perShare" if is_currency else "multiple"
    if fmt == "number":
        return "monetary" if is_currency else "shares"
    # Unknown / null format
    return "monetary" if is_currency else "number"


def _build_block(
    ticker: str,
    period: str,
    rows: List[Dict[str, Any]],
    specs: List[Dict[str, Any]],
    currency: str,
) -> Optional[Dict[str, Any]]:
    """Generic transform: build SymbioticTable fields from period rows + specs.

    `specs` is a list of {key, label, data_type, section, display_order}.
    """
    is_annual = (period or "").lower().startswith("annual")
    periods, period_index = _build_period_index(rows, is_annual)
    if not periods:
        return None

    row_by_period: Dict[str, Dict[str, Any]] = {}
    for row in rows:
        label = _period_label(row, is_annual)
        if label in period_index and label not in row_by_period:
            row_by_period[label] = row

    estimate_periods = [
        label for label in periods
        if (row_by_period.get(label) or {}).get("isEstimate")
    ]

    fields: List[Dict[str, Any]] = []
    for spec in specs:
        key = spec["key"]
        values: List[Optional[float]] = [None] * len(periods)
        has_value = False
        for label, col in period_index.items():
            row = row_by_period.get(label)
            if row is not None:
                value = row.get(key)
                if isinstance(value, (int, float)):
                    values[col] = float(value)
                    has_value = True
        if not has_value:
            continue
        fields.append({
            "key": key,
            "label": spec["label"],
            "values": values,
            "importance": spec.get("importance", 50),
            "data_type": spec["data_type"],
            "balance": None,
            "section": spec.get("section", "Metrics"),
            "display_order": spec.get("display_order", 0),
            "indent_level": 0,
            "is_subtotal": False,
        })

    fields.sort(key=lambda f: (f.get("section", ""), f.get("display_order", 0)))

    return {
        "symbol": ticker.upper(),
        "currency": currency,
        "source": "perplexity_v3",
        "period": period,
        "periods": periods,
        "estimate_periods": estimate_periods,
        "fields": fields,
        "last_updated": datetime.now(timezone.utc).isoformat(),
    }


def transform_ratios(ticker: str, period: str, payload: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    """Transform the `ratios` block (146 metrics) using its own metadata."""
    if not payload:
        return None
    rows = payload.get("ratios") or []
    meta = (payload.get("ratios_metadata") or {}).get("metrics") or []
    if not rows or not meta:
        return None

    specs: List[Dict[str, Any]] = []
    for order, m in enumerate(meta):
        ratio_id = m.get("ratioId")
        if not ratio_id:
            continue
        category = m.get("category") or "Other"
        specs.append({
            "key": ratio_id,
            "label": m.get("metricName") or ratio_id,
            "data_type": _ratio_data_type(ratio_id, m.get("metricFormat"), bool(m.get("isCurrency"))),
            "section": _RATIO_SECTION_REMAP.get(category, category),
            "display_order": order,
        })

    return _build_block(ticker, period, rows, specs, _currency_from_payload(payload))


def _adjusted_data_type(m: Dict[str, Any]) -> str:
    fmt = (m.get("metricFormat") or "").strip().lower()
    if fmt == "%":
        return "percent"
    if m.get("isPerShare"):
        return "perShare"
    if fmt == "number":
        return "monetary" if m.get("isCurrency") else "number"
    return "monetary" if m.get("isCurrency") else "number"


def _adjusted_section(m: Dict[str, Any]) -> str:
    if (m.get("metricFormat") or "").strip() == "%":
        return "Adjusted Margins"
    if m.get("isPerShare"):
        return "Adjusted Per Share"
    return "Adjusted Metrics"


def transform_adjusted(ticker: str, period: str, payload: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    """Transform the `adjusted_metrics` (non-GAAP) block using its metadata."""
    if not payload:
        return None
    rows = payload.get("adjusted_metrics") or []
    meta = (payload.get("adjusted_metrics_metadata") or {}).get("metrics") or []
    if not rows or not meta:
        return None

    specs: List[Dict[str, Any]] = []
    for order, m in enumerate(meta):
        metric_id = m.get("metricId")
        if not metric_id:
            continue
        specs.append({
            "key": metric_id,
            "label": m.get("metricName") or metric_id,
            "data_type": _adjusted_data_type(m),
            "section": _adjusted_section(m),
            "display_order": order,
        })

    return _build_block(ticker, period, rows, specs, _currency_from_payload(payload))


# Curated layout for the key_stats block (no metadata block is provided by v3).
# (key, label, data_type, section)
_KEY_STATS_SPECS: List[Tuple[str, str, str, str]] = [
    ("key_stats_market_cap",         "Market Cap",          "monetary", "Size & Valuation"),
    ("key_stats_enterprise_value",   "Enterprise Value",    "monetary", "Size & Valuation"),
    ("key_stats_total_revenues",     "Total Revenue",       "monetary", "Profitability"),
    ("key_stats_revenue_growth",     "Revenue Growth",      "percent",  "Profitability"),
    ("key_stats_gross_profit",       "Gross Profit",        "monetary", "Profitability"),
    ("key_stats_gross_margin",       "Gross Margin",        "percent",  "Profitability"),
    ("key_stats_ebitda",             "EBITDA",              "monetary", "Profitability"),
    ("key_stats_ebitda_margin",      "EBITDA Margin",       "percent",  "Profitability"),
    ("key_stats_net_income",         "Net Income",          "monetary", "Profitability"),
    ("key_stats_net_margin",         "Net Margin",          "percent",  "Profitability"),
    ("key_stats_operating_cash_flow","Operating Cash Flow", "monetary", "Cash Flow & Liquidity"),
    ("key_stats_free_cash_flow",     "Free Cash Flow",      "monetary", "Cash Flow & Liquidity"),
    ("key_stats_capex",              "Capital Expenditures","monetary", "Cash Flow & Liquidity"),
    ("key_stats_cash",               "Cash & Equivalents",  "monetary", "Cash Flow & Liquidity"),
    ("key_stats_total_debt",         "Total Debt",          "monetary", "Cash Flow & Liquidity"),
    ("key_stats_diluted_eps",        "Diluted EPS",         "perShare", "Per Share & Growth"),
    ("key_stats_eps_growth",         "EPS Growth",          "percent",  "Per Share & Growth"),
]


def transform_key_stats(ticker: str, period: str, payload: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    """Transform the `key_stats` block (incl. forward estimate periods)."""
    if not payload:
        return None
    rows = payload.get("key_stats") or []
    if not rows:
        return None

    specs = [
        {"key": key, "label": label, "data_type": dtype, "section": section, "display_order": order}
        for order, (key, label, dtype, section) in enumerate(_KEY_STATS_SPECS)
    ]
    return _build_block(ticker, period, rows, specs, _currency_from_payload(payload))


# ---------------------------------------------------------------------------
# Segments transform — matches the SegmentsTable contract
# ---------------------------------------------------------------------------


def _format_year_label(row: Dict[str, Any]) -> Optional[str]:
    """Segments table groups by fiscal year (string)."""
    year = row.get("fiscalYear")
    if year is not None:
        return str(year)
    date = row.get("date") or ""
    if len(date) >= 4 and date[:4].isdigit():
        return date[:4]
    return None


def _format_quarter_label(row: Dict[str, Any]) -> Optional[str]:
    """Quarterly label, e.g. 'Q3 2026'."""
    year = _format_year_label(row)
    if not year:
        return None
    q = row.get("fiscalQuarter")
    if q in (1, 2, 3, 4):
        return f"Q{q} {year}"
    date = row.get("date") or ""
    if len(date) >= 7 and date[5:7].isdigit():
        month = int(date[5:7])
        return f"Q{(month - 1) // 3 + 1} {year}"
    return None


def _sum_quarterly_to_annual(values: Dict[str, List[float]]) -> Dict[str, float]:
    """Aggregate quarterly values per fiscal year by sum (revenue-style metrics)."""
    return {year: sum(v for v in vals if v is not None) for year, vals in values.items() if vals}


def _latest_per_year(values: Dict[str, List[Tuple[str, float]]]) -> Dict[str, float]:
    """Take the most recent value per year (used for snapshot metrics like MW/EHs/GPUs)."""
    out: Dict[str, float] = {}
    for year, entries in values.items():
        # entries are (date, value); pick max-date
        entries = [(d, v) for d, v in entries if v is not None]
        if not entries:
            continue
        entries.sort(key=lambda kv: kv[0], reverse=True)
        out[year] = entries[0][1]
    return out


def _segment_unit_meta(info: Dict[str, Any]) -> Dict[str, Any]:
    """Derive display metadata for a segment / KPI metric.

    Preserves whether the series is monetary (report currency) vs a physical
    count / capacity (Units, MW, GPUs, …) so the FE never paints € on units.
    """
    name = (info.get("metricName") or info.get("metricId") or "").strip()
    fmt = (info.get("metricFormat") or "").strip().lower()
    is_currency = bool(info.get("isCurrency"))

    if fmt == "%":
        data_type = "percent"
    elif is_currency:
        data_type = "monetary"
    else:
        data_type = "number"

    unit_label: Optional[str] = None
    if data_type == "number":
        # Prefer an explicit parenthetical unit in the name, e.g. "(Units)".
        m = re.search(r"\(([^)]+)\)\s*$", name)
        if m:
            unit_label = m.group(1).strip()
        elif fmt and fmt not in ("number", "ratio"):
            unit_label = info.get("metricFormat")

    return {
        "data_type": data_type,
        "is_currency": is_currency,
        "unit_label": unit_label,
    }


def transform_segments(
    ticker: str,
    payload: Dict[str, Any],
    period: str = "annual",
) -> Optional[Dict[str, Any]]:
    """
    Convert the v3 `segments` + `segments_metadata` blocks into the shape that
    SegmentsTable expects:
        {
          symbol, currency, period, period_end, filing_date,
          segments: {
            revenue: { segmentName: { periodLabel: value } },
            operating_income: { segmentName: { periodLabel: value } },
          },
          geography: { revenue: {}, operating_income: {} },
          products:  { revenue: {} },
          metric_meta: { segmentName: { data_type, is_currency, unit_label } },
        }

    `period`: "annual" groups by fiscal year (revenue summed across quarters);
    "quarterly" keeps one column per fiscal quarter (values passed through).
    """
    if not payload:
        return None

    is_quarterly = (period or "").lower().startswith("quarter")

    segments_rows: List[Dict[str, Any]] = payload.get("segments") or []
    metadata = payload.get("segments_metadata") or {}
    if not segments_rows:
        return None

    metric_info: Dict[str, Dict[str, Any]] = {
        m.get("metricId"): m
        for m in metadata.get("metrics", [])
        if m.get("metricId")
    }

    # ── Bucket metric values by metricId × period label ───────────────────
    # Annual: currency-segment values are summed across quarters (revenue);
    # KPI / capacity values are snapshots → take the latest in the year.
    # Quarterly: every quarter is its own column, values pass through.
    revenue_buckets: Dict[str, Dict[str, List[float]]] = {}
    kpi_buckets: Dict[str, Dict[str, List[Tuple[str, float]]]] = {}

    def _classify(info: Dict[str, Any]) -> str:
        mtype = (info.get("metricType") or "").lower()
        if mtype == "segment":
            return "revenue"
        if mtype == "kpi":
            return "kpi"
        # Fallback: monetary segments → revenue, anything else → kpi
        return "revenue" if info.get("isCurrency") else "kpi"

    for row in segments_rows:
        label = _format_quarter_label(row) if is_quarterly else _format_year_label(row)
        date_str = row.get("date") or ""
        if not label:
            continue

        for metric_id, info in metric_info.items():
            value = row.get(metric_id)
            if value is None:
                continue
            bucket = _classify(info)
            if bucket == "revenue":
                revenue_buckets.setdefault(metric_id, {}).setdefault(label, []).append(value)
            else:
                kpi_buckets.setdefault(metric_id, {}).setdefault(label, []).append((date_str, value))

    if not revenue_buckets and not kpi_buckets:
        return None

    # Preserve metadata ordering when possible: walk segmentGroups so the FE
    # renders Revenue / KPI lines in the order Perplexity itself uses.
    ordered_metric_ids: List[str] = []
    seen_ids: set[str] = set()
    for group in metadata.get("segmentGroups", []) or []:
        for m in group.get("metrics", []) or []:
            mid = m.get("metricId")
            if mid and mid not in seen_ids:
                ordered_metric_ids.append(mid)
                seen_ids.add(mid)
    for mid in metric_info.keys():
        if mid not in seen_ids:
            ordered_metric_ids.append(mid)
            seen_ids.add(mid)

    def _reduce_revenue(bucket: Dict[str, List[float]]) -> Dict[str, float]:
        if is_quarterly:
            # One row per quarter — take the latest reported value for the label.
            return {label: vals[-1] for label, vals in bucket.items() if vals}
        return _sum_quarterly_to_annual(bucket)

    business_revenue: Dict[str, Dict[str, float]] = {}
    kpi_block: Dict[str, Dict[str, float]] = {}
    metric_meta: Dict[str, Dict[str, Any]] = {}
    for metric_id in ordered_metric_ids:
        info = metric_info.get(metric_id, {})
        name = info.get("metricName") or metric_id
        meta = _segment_unit_meta(info)
        if metric_id in revenue_buckets:
            business_revenue[name] = _reduce_revenue(revenue_buckets[metric_id])
            # Revenue / segment lines are monetary even if metadata is sparse.
            metric_meta[name] = {**meta, "data_type": "monetary", "is_currency": True}
        if metric_id in kpi_buckets:
            kpi_block[name] = _latest_per_year(kpi_buckets[metric_id])
            # KPIs keep their derived type (units, MW, %, …) — never force currency.
            metric_meta[name] = meta

    # Most recent statement date (used in the FE info text)
    latest_date = max((row.get("date") or "" for row in segments_rows), default="")

    return {
        "symbol": ticker.upper(),
        "currency": _currency_from_payload(payload),
        "period": "quarterly" if is_quarterly else "annual",
        "filing_date": latest_date,
        "period_end": latest_date,
        "segments": {
            "revenue": business_revenue,
            "operating_income": {},
        },
        # We reuse the geography slot for KPIs (Bitcoin mined, GPUs, MW, etc.)
        # to surface them without touching the FE component.
        "geography": {
            "revenue": kpi_block,
        },
        "products": {
            "revenue": {},
        },
        "metric_meta": metric_meta,
    }
