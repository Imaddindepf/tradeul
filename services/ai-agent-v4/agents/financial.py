"""
Financial Agent - Financial statements and SEC filings.

Dos rutas (Fase 3c, piloto de tool-calling nativo):

  - Heurística (default): keywords deciden qué llamar. Solo 2 tools:
      financials.get_financial_statements(symbol, period, limit)
      sec.search_filings(ticker, form_type, date_from, date_to, page_size)

  - Nativa (env AGENT_NATIVE_TOOLS incluye "financial"): el selector LLM
    (agents/_tool_selector, validado por evals/run_tool_selection) elige del
    roster completo (tool_rosters.py) — income/balance/cash_flow aislados,
    get_segments, get_financial_ratios, get_key_stats, get_adjusted_metrics,
    get_recent_filings y get_filing_detail (esta última encadenada tras un
    search para resolver el accession number).
    Cualquier fallo del selector cae a la ruta heurística (fail-safe).

Data cleaning:
  - SEC filings: strip null fields, internal IDs → only metadata rows
  - Financial statements: keep key metrics, human-readable labels

NOTE: Dilution analysis (warrants, ATM, shelf, cash runway, risk scores) is handled
by the dedicated dilution agent — do NOT route dilution queries here.
"""
from __future__ import annotations
import asyncio
import logging
import re
import time
from typing import Any

from agents.mcp_catalog import MCP

logger = logging.getLogger(__name__)


# ── Intent detection ────────────────────────────────────────────────

_SEC_KEYWORDS = [
    "sec", "filing", "filings", "10-k", "10-q", "8-k", "s-1", "s-3",
    "424b", "proxy", "def 14a", "annual report", "quarterly report",
    "edgar", "prospectus", "informe",
]

_FINANCIAL_KEYWORDS = [
    "financial", "financials", "fundamentals", "income", "revenue",
    "balance", "cash flow", "earnings", "profit", "margin",
    "ebitda", "debt", "ratio", "valuation", "sobrevalorada",
    "subvalorada", "fundamentales", "ingresos", "beneficio",
    "ganancias", "estados financieros", "financieros",
]

_QUARTERLY_KEYWORDS = [
    "quarter", "quarterly", "q1", "q2", "q3", "q4",
    "trimestre", "trimestres", "trimestral", "trimestrales",
    "último trimestre", "últimos trimestres",
]


def _wants_sec(q: str) -> bool:
    return any(kw in q.lower() for kw in _SEC_KEYWORDS)

def _wants_financials(q: str) -> bool:
    return any(kw in q.lower() for kw in _FINANCIAL_KEYWORDS)

def _wants_quarterly(q: str) -> bool:
    return any(kw in q.lower() for kw in _QUARTERLY_KEYWORDS)


# ── Data cleaning ───────────────────────────────────────────────────

def _clean_sec_filings(raw: dict) -> list[dict]:
    """Strip SEC filings to metadata-only rows.
    The synthesizer only needs: formType, date, description, accessionNo (for links).
    No internal IDs, no null fields, no document blobs.
    """
    filings = raw.get("filings", [])
    if not filings:
        return []

    cleaned = []
    for f in filings:
        row = {
            "form_type": f.get("formType", ""),
            "filed_date": str(f.get("filedAt", ""))[:10],
            "description": f.get("description", ""),
        }
        if f.get("accessionNo"):
            row["accession_no"] = f["accessionNo"]
        if f.get("periodOfReport"):
            row["period"] = f["periodOfReport"]
        cleaned.append(row)

    return cleaned


def _humanize(n: float | int | None) -> str:
    """Convert raw numbers to human-readable: 130497000000 → '130.5B'."""
    if n is None:
        return "N/A"
    if not isinstance(n, (int, float)):
        return str(n)
    abs_n = abs(n)
    sign = "-" if n < 0 else ""
    if abs_n >= 1e12:
        return f"{sign}{abs_n/1e12:.2f}T"
    if abs_n >= 1e9:
        return f"{sign}{abs_n/1e9:.2f}B"
    if abs_n >= 1e6:
        return f"{sign}{abs_n/1e6:.1f}M"
    if abs_n >= 1e3:
        return f"{sign}{abs_n/1e3:.1f}K"
    if isinstance(n, float):
        return f"{sign}{abs_n:.2f}"
    return f"{sign}{abs_n}"


def _pct(n: float | None) -> str:
    """Format a ratio as a percentage.
    
    Values < 1 are ratios (0.25 → 25.0%), values >= 1 are already percentages (25.0 → 25.0%).
    """
    if n is None:
        return "N/A"
    if abs(n) < 1:
        return f"{n * 100:.1f}%"
    return f"{n:.1f}%"


# Key financial metrics to extract (in order of importance).
# Incluyen los nombres del payload actual del api_gateway Y los del
# microservicio legacy (fallback) — las claves ausentes simplemente se omiten.
_KEY_INCOME = [
    "revenue", "revenue_yoy", "cost_of_revenue", "gross_profit",
    "gross_margin", "gross_profit_margin",
    "sga_expenses", "rd_expenses", "total_operating_expenses",
    "operating_income", "operating_margin",
    "ebitda", "ebitda_margin",
    "net_income", "net_margin", "net_profit_margin",
    "eps_basic", "eps_diluted",
]

_KEY_BALANCE = [
    "total_cash_st_investments", "total_cash",
    "total_receivables", "inventory", "inventories",
    "current_assets", "total_current_assets",
    "ppe", "ppe_net", "total_assets",
    "current_liabilities", "total_current_liabilities",
    "long_term_debt", "total_liabilities",
    "total_equity",
]

_KEY_CASHFLOW = [
    "operating_cf", "cash_from_operations", "capex",
    "free_cf", "free_cash_flow",
    "acquisitions", "dividends_paid", "dividends_common",
    "financing_cf", "cash_from_financing",
    "net_change_cash", "net_change_in_cash",
]

_PCT_KEYS = {
    "revenue_yoy", "gross_margin", "gross_profit_margin", "operating_margin",
    "ebitda_margin", "net_margin", "net_profit_margin", "fcf_margin",
    "effective_tax_rate",
}


def _clean_financial_statements(raw: dict) -> dict:
    """Extract key financial metrics from raw API response.
    
    Transforms 108K chars of raw data (219 items × 15 fields each) into
    ~40 key metrics with human-readable values (~3K chars).
    """
    if not isinstance(raw, dict) or "periods" not in raw:
        return raw

    periods = raw.get("periods", [])
    symbol = raw.get("symbol", "")
    currency = raw.get("currency", "USD")

    # Build a lookup: metric_key → {label, values}
    metric_lookup: dict[str, dict] = {}
    for section_key in ("income_statement", "balance_sheet", "cash_flow"):
        section = raw.get(section_key, [])
        if not isinstance(section, list):
            continue
        for item in section:
            key = item.get("key", "")
            label = item.get("label", key)
            values = item.get("values", [])
            if key and values:
                metric_lookup[key] = {"label": label, "values": values}

    def _extract_section(key_list: list[str]) -> list[dict]:
        rows = []
        for key in key_list:
            entry = metric_lookup.get(key)
            if not entry:
                continue
            is_pct = key in _PCT_KEYS
            fmt_values = [_pct(v) if is_pct else _humanize(v) for v in entry["values"]]
            rows.append({"metric": entry["label"], "values": fmt_values})
        return rows

    return {
        "symbol": symbol,
        "currency": currency,
        "periods": periods,
        "income_statement": _extract_section(_KEY_INCOME),
        "balance_sheet": _extract_section(_KEY_BALANCE),
        "cash_flow": _extract_section(_KEY_CASHFLOW),
    }


# Ratios curados para el synthesizer: el endpoint devuelve ~180 campos por
# ticker — se extrae un set fijo (retornos, liquidez, apalancamiento, capex,
# dividendos y crecimiento) en este orden.
_KEY_RATIOS = [
    "ratio_return_on_invested_capital", "ratio_return_on_equity",
    "ratio_return_on_assets", "ratio_return_on_capital_employed",
    "ratio_current_ratio", "ratio_quick_ratio", "ratio_cash_ratio",
    "calculated_total_debt", "calculated_net_debt", "ratio_debt_to_equity",
    "ratio_cash_flow_to_debt_ratio", "ratio_ebitda_to_interest_expense",
    "ratio_asset_turnover", "ratio_inventory_turnover",
    "ratio_cash_conversion_cycle",
    "ratio_capex_to_revenue", "ratio_rd_to_revenue", "ratio_sbc_to_revenue",
    "calculated_dividends_per_share", "ratio_payout_ratio",
    "growth_earnings_from_cont_operations_1y",
    "growth_cash_from_operations_1y",
]


def _clean_metric_fields(raw: dict, keep: list[str] | None = None) -> dict:
    """Aplana el shape {periods, fields: [{key,label,values,data_type}]} de
    ratios/key-stats/adjusted a filas legibles. `keep` filtra y ordena por
    clave (ratios trae ~180 campos). Formatea según data_type del campo, no
    adivinando por magnitud: un ROIC de 1.35 es 135%, no "1.4%".
    """
    if not isinstance(raw, dict) or not isinstance(raw.get("fields"), list):
        return _shrink(raw)
    fields = raw["fields"]
    if keep is not None:
        order = {k: i for i, k in enumerate(keep)}
        fields = sorted(
            (f for f in fields if f.get("key") in order),
            key=lambda f: order[f["key"]],
        )
    rows = []
    for f in fields:
        vals = f.get("values") or []
        if f.get("data_type") == "percent":
            fmt = [f"{v * 100:.1f}%" if isinstance(v, (int, float)) else "N/A"
                   for v in vals]
        else:
            fmt = [_humanize(v) for v in vals]
        rows.append({"metric": f.get("label") or f.get("key"), "values": fmt})
    out = {
        "symbol": raw.get("symbol"),
        "currency": raw.get("currency"),
        "periods": raw.get("periods"),
        "metrics": rows,
    }
    if raw.get("estimate_periods"):
        out["estimate_periods"] = raw["estimate_periods"]
    return out


# ── Native tool-calling path (Fase 3c pilot) ────────────────────────

_FORM_RE = re.compile(
    r"\b(10-K|10-Q|8-K|S-1|S-3|424B\d?|DEF 14A|SC 13D|SC 13G|6-K|20-F)\b", re.I,
)


def _shrink(obj: Any, max_items: int = 12, max_str: int = 600, depth: int = 0) -> Any:
    """Poda genérica para respuestas sin limpiador dedicado: listas a
    max_items, strings a max_str — el synthesizer no necesita más."""
    if depth > 6:
        return "…"
    if isinstance(obj, dict):
        return {k: _shrink(v, max_items, max_str, depth + 1) for k, v in obj.items()}
    if isinstance(obj, list):
        out = [_shrink(v, max_items, max_str, depth + 1) for v in obj[:max_items]]
        if len(obj) > max_items:
            out.append(f"[+{len(obj) - max_items} more]")
        return out
    if isinstance(obj, str) and len(obj) > max_str:
        return obj[:max_str] + "…"
    return obj


async def _exec_native_tool(
    tool: str, ticker: str, *, period: str, limit: int, form_type: str | None,
) -> tuple[str, Any]:
    """Ejecuta una tool del roster con args deterministas (el LLM elige QUÉ
    llamar; los args salen del estado — superficie de fallo mínima).
    Devuelve (result_key, payload)."""
    if tool == "financials.get_financial_statements":
        # El primer fetch de un ticker puede tardar >30s (luego cachea y baja
        # a ~100ms) — timeout ampliado para no perder el cold-start.
        raw = await MCP.financials.get_financial_statements(
            {"symbol": ticker, "period": period, "limit": limit}, timeout=60.0)
        return "financials", _clean_financial_statements(raw)
    if tool == "financials.get_income_statement":
        raw = await MCP.financials.get_income_statement({"symbol": ticker, "period": period})
        return "income_statement", _shrink(raw)
    if tool == "financials.get_balance_sheet":
        raw = await MCP.financials.get_balance_sheet({"symbol": ticker, "period": period})
        return "balance_sheet", _shrink(raw)
    if tool == "financials.get_cash_flow":
        raw = await MCP.financials.get_cash_flow({"symbol": ticker, "period": period})
        return "cash_flow", _shrink(raw)
    if tool == "financials.get_segments":
        raw = await MCP.financials.get_segments({"symbol": ticker})
        return "segments", _shrink(raw)
    if tool == "financials.get_financial_ratios":
        raw = await MCP.financials.get_financial_ratios(
            {"symbol": ticker, "period": period})
        return "ratios", _clean_metric_fields(raw, _KEY_RATIOS)
    if tool == "financials.get_key_stats":
        raw = await MCP.financials.get_key_stats(
            {"symbol": ticker, "period": period})
        return "key_stats", _clean_metric_fields(raw)
    if tool == "financials.get_adjusted_metrics":
        raw = await MCP.financials.get_adjusted_metrics(
            {"symbol": ticker, "period": period})
        return "adjusted_metrics", _clean_metric_fields(raw)
    if tool == "sec.search_filings":
        params: dict[str, Any] = {"ticker": ticker, "page_size": 10}
        if form_type:
            params["form_type"] = form_type
        raw = await MCP.sec.search_filings(params)
        return "sec_filings", _clean_sec_filings(raw)
    if tool == "sec.get_recent_filings":
        raw = await MCP.sec.get_recent_filings({"ticker": ticker, "count": 10})
        return "recent_filings", _clean_sec_filings(raw) or _shrink(raw)
    if tool == "sec.get_filing_detail":
        # Encadenado: resolver el accession number del filing más reciente
        # (del form_type pedido si lo hay) y abrir su detalle.
        params = {"ticker": ticker, "page_size": 5}
        if form_type:
            params["form_type"] = form_type
        search = await MCP.sec.search_filings(params)
        filings = (search or {}).get("filings") or []
        accession = next((f.get("accessionNo") for f in filings if f.get("accessionNo")), None)
        if not accession:
            return "filing_detail", {"error": f"no filing found for {ticker}"
                                     + (f" (form {form_type})" if form_type else "")}
        raw = await MCP.sec.get_filing_detail({"accession_number": accession})
        if isinstance(raw, dict):
            return "filing_detail", {"accession_no": accession, **_shrink(raw)}
        return "filing_detail", {"accession_no": accession, "content": _shrink(raw)}
    raise ValueError(f"unknown tool {tool}")


async def _financial_node_native(state: dict, start_time: float) -> dict | None:
    """Ruta nativa: selector LLM sobre el roster del agente (tool_rosters.py).
    Devuelve None si el selector no dio tools (el caller cae a la heurística)."""
    from agents._tool_selector import select_tools

    query = state.get("query", "")
    task = state.get("agent_task") or query
    tickers = state.get("tickers", [])[:3]

    selected = await select_tools("financial", task)
    if not selected:
        return None

    quarterly = _wants_quarterly(query) or _wants_quarterly(task)
    period = "quarter" if quarterly else "annual"
    limit = 8 if quarterly else 5
    m = _FORM_RE.search(task) or _FORM_RE.search(query)
    form_type = m.group(1).upper() if m else None

    results: dict[str, Any] = {}
    errors: list[str] = []

    async def _run_ticker(ticker: str) -> tuple[str, dict[str, Any], list[str]]:
        data: dict[str, Any] = {}
        errs: list[str] = []
        outs = await asyncio.gather(
            *[_exec_native_tool(t, ticker, period=period, limit=limit, form_type=form_type)
              for t in selected],
            return_exceptions=True,
        )
        for tool, out in zip(selected, outs):
            if isinstance(out, Exception):
                errs.append(f"{tool}/{ticker}: {out}")
            else:
                key, payload = out
                data[key] = payload
        return ticker, data, errs

    if tickers:
        for ticker, data, errs in await asyncio.gather(*[_run_ticker(t) for t in tickers]):
            results[ticker] = data
            errors.extend(errs)
    else:
        # Sin ticker solo tienen sentido las tools de flujo general de filings.
        general = [t for t in selected if t == "sec.get_recent_filings"]
        if not general:
            return None  # la heurística dará el mensaje de "no ticker"
        try:
            raw = await MCP.sec.get_recent_filings({"count": 15})
            results["market"] = {"recent_filings": _clean_sec_filings(raw) or _shrink(raw)}
        except Exception as exc:  # noqa: BLE001
            errors.append(f"sec.get_recent_filings: {exc}")

    if errors:
        results["_errors"] = errors

    elapsed_ms = int((time.time() - start_time) * 1000)
    return {
        "agent_results": {
            "financial": {
                "tickers_analyzed": tickers,
                "native_tools": selected,
                **results,
            },
        },
        "execution_metadata": {
            **(state.get("execution_metadata", {})),
            "financial": {
                "elapsed_ms": elapsed_ms,
                "tickers": tickers,
                "native": True,
                "tools": selected,
                "error_count": len(errors),
            },
        },
    }


# ── Main node ───────────────────────────────────────────────────────

async def financial_node(state: dict) -> dict:
    """Fetch financial data and/or SEC filings based on user intent."""
    start_time = time.time()

    query = state.get("query", "")
    tickers = state.get("tickers", [])

    # ── Fase 3c: ruta nativa tras el flag; cualquier fallo cae aquí abajo ──
    from agents._tool_selector import native_tools_enabled
    if native_tools_enabled("financial"):
        try:
            native = await _financial_node_native(state, start_time)
            if native is not None:
                return native
            logger.info("financial native: selector sin tools — ruta heurística")
        except Exception:  # noqa: BLE001
            logger.exception("financial native path failed — falling back to heuristic")

    results: dict[str, Any] = {}
    errors: list[str] = []

    if not tickers:
        elapsed_ms = int((time.time() - start_time) * 1000)
        return {
            "agent_results": {
                "financial": {
                    "error": "No ticker detected. Please specify a stock symbol (e.g. $AAPL).",
                },
            },
            "execution_metadata": {
                **(state.get("execution_metadata", {})),
                "financial": {"elapsed_ms": elapsed_ms, "tickers": [], "error": "no_ticker"},
            },
        }

    wants_sec = _wants_sec(query)
    wants_fin = _wants_financials(query)
    quarterly = _wants_quarterly(query)

    fetch_financials = wants_fin or (not wants_sec)
    fetch_sec = wants_sec

    async def _fetch_financials_for_ticker(ticker: str) -> tuple[str, dict[str, Any], list[str]]:
        ticker_data: dict[str, Any] = {}
        ticker_errors: list[str] = []

        # 1. Financial statements — cleaned to key metrics only
        if fetch_financials:
            try:
                params: dict[str, Any] = {"symbol": ticker}
                if quarterly:
                    params["period"] = "quarter"
                    params["limit"] = 8
                # El cold-start puede superar los 30s default (ver ruta nativa).
                raw = await MCP.financials.get_financial_statements(params, timeout=60.0)
                ticker_data["financials"] = _clean_financial_statements(raw)
            except Exception as exc:
                ticker_errors.append(f"financials/{ticker}: {exc}")

        # 2. SEC filings — cleaned to metadata rows only
        if fetch_sec:
            try:
                raw = await MCP.sec.search_filings({"ticker": ticker, "page_size": 10})
                ticker_data["sec_filings"] = _clean_sec_filings(raw)
            except Exception as exc:
                ticker_errors.append(f"sec_filings/{ticker}: {exc}")

        return ticker, ticker_data, ticker_errors

    ticker_results = await asyncio.gather(*[
        _fetch_financials_for_ticker(t) for t in tickers[:3]
    ])
    for ticker, ticker_data, ticker_errors in ticker_results:
        results[ticker] = ticker_data
        errors.extend(ticker_errors)

    if errors:
        results["_errors"] = errors

    elapsed_ms = int((time.time() - start_time) * 1000)

    return {
        "agent_results": {
            "financial": {
                "tickers_analyzed": tickers[:3],
                "sec_checked": fetch_sec,
        "financials_checked": fetch_financials,
            "quarterly": quarterly,
                **results,
            },
        },
        "execution_metadata": {
            **(state.get("execution_metadata", {})),
            "financial": {
                "elapsed_ms": elapsed_ms,
                "tickers": tickers[:3],
                "error_count": len(errors),
            },
        },
    }
