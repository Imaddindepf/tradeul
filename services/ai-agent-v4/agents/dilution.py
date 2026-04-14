"""
Dilution Agent — two-tier analysis system.

TIER 1 (Primary): Our dilution tracker DB — fast, structured, analyst-curated.
  Sources: SEC-extracted data + analyst-curated instrument details.

TIER 2 (Fallback / CS230 Chaining): For tickers NOT in our DB.
  Step 1 [parallel tools]
    ├── sec.search_filings(S-3, 424B5, S-1, 8-K)
    └── financials.get_financial_statements()
  Step 2 [LLM Chain of Thought + few-shot schema]
    └── Extract instruments + risk scores → same output schema as Tier 1
  Output: flagged with source="llm_estimated"

Intent routing (Tier 1):
  DILUTION_OVERVIEW  → get_sec_dilution_profile
  WARRANT_FOCUS      → get_warrants + get_dilution_risk_ratings
  ATM_FOCUS          → get_atm_offerings + get_instrument_context
  SHELF_FOCUS        → get_shelf_registrations + get_instrument_context
  CASH_FOCUS         → get_cash_position + get_cash_runway
  RISK_FOCUS         → get_dilution_risk_ratings + get_dilution_analysis
  HISTORY_FOCUS      → get_shares_history + get_completed_offerings
  FULL_ANALYSIS      → profile + instrument_context + risk_ratings + cash_runway
"""
from __future__ import annotations
import asyncio
import json
import logging
import time
from typing import Any

from agents._mcp_tools import call_mcp_tool
from agents._llm_retry import llm_invoke_with_retry

logger = logging.getLogger(__name__)


# ── Intent detection ──────────────────────────────────────────────────────────

_WARRANT_KW = [
    "warrant", "warrants", "ejercicio", "exercise price", "precio de ejercicio",
    "expiration", "vencimiento", "price protection", "ratchet", "warrantholders",
]
_ATM_KW = [
    "atm", "at-the-market", "at the market", "programa atm", "colocacion continua",
    "placement agent", "agente colocador",
]
_SHELF_KW = [
    "shelf", "s-3", "s3", "registro previo", "estante", "baby shelf", "baby-shelf",
    "registration statement",
]
_CASH_KW = [
    "cash", "caja", "efectivo", "runway", "burn rate", "quema de caja",
    "burn", "meses de caja", "months of cash", "cash position", "posición de caja",
    "cuanto tiene", "cuánto tiene", "dinero", "liquidez",
]
_RISK_KW = [
    "risk", "riesgo", "score", "puntuación", "rating", "calificación",
    "overall risk", "offering ability", "overhead supply", "critical", "crítico",
    "high risk", "alto riesgo", "danger", "peligro",
]
_HISTORY_KW = [
    "history", "historial", "historical", "share count", "acciones emitidas",
    "dilution history", "historial de dilución", "previous offerings",
    "pasadas emisiones", "track record",
]
_INSTRUMENTS_KW = [
    "instruments", "instrumentos", "convertible", "preferred", "equity line",
    "linea de capital", "note", "nota", "pagaré", "pagare", "s-1",
]
_POTENTIAL_KW = [
    "potential dilution", "dilución potencial", "how much dilution", "cuanta dilución",
    "total dilution", "dilución total", "ceiling", "techo", "worst case",
    "peor caso", "maximum dilution", "máxima dilución",
]
_FULL_KW = [
    "full analysis", "análisis completo", "complete", "completo", "deep dive",
    "todo sobre", "full picture", "panorama completo", "all info",
]


def _focus(q: str) -> set[str]:
    """Determine which focus areas the query targets."""
    q = q.lower()
    focuses = set()
    if any(kw in q for kw in _WARRANT_KW):
        focuses.add("warrant")
    if any(kw in q for kw in _ATM_KW):
        focuses.add("atm")
    if any(kw in q for kw in _SHELF_KW):
        focuses.add("shelf")
    if any(kw in q for kw in _CASH_KW):
        focuses.add("cash")
    if any(kw in q for kw in _RISK_KW):
        focuses.add("risk")
    if any(kw in q for kw in _HISTORY_KW):
        focuses.add("history")
    if any(kw in q for kw in _INSTRUMENTS_KW):
        focuses.add("instruments")
    if any(kw in q for kw in _POTENTIAL_KW):
        focuses.add("potential")
    if any(kw in q for kw in _FULL_KW):
        focuses.add("full")
    return focuses


# ── Data humanizers ───────────────────────────────────────────────────────────

def _fmt_money(v: Any, suffix: str = "") -> str:
    """Format a number as human-readable money: 130497000 → '$130.5M'."""
    if v is None:
        return "N/A"
    try:
        n = float(str(v))
    except (ValueError, TypeError):
        return str(v)
    abs_n = abs(n)
    sign = "-" if n < 0 else ""
    if abs_n >= 1e9:
        return f"{sign}${abs_n/1e9:.2f}B{suffix}"
    if abs_n >= 1e6:
        return f"{sign}${abs_n/1e6:.1f}M{suffix}"
    if abs_n >= 1e3:
        return f"{sign}${abs_n/1e3:.1f}K{suffix}"
    return f"{sign}${abs_n:.2f}{suffix}"


def _fmt_shares(v: Any) -> str:
    """Format shares: 15000000 → '15.0M shares'."""
    if v is None:
        return "N/A"
    try:
        n = float(str(v))
    except (ValueError, TypeError):
        return str(v)
    if n >= 1e9:
        return f"{n/1e9:.2f}B shares"
    if n >= 1e6:
        return f"{n/1e6:.1f}M shares"
    if n >= 1e3:
        return f"{n/1e3:.1f}K shares"
    return f"{n:.0f} shares"


def _fmt_pct(v: Any) -> str:
    """Format a percentage value."""
    if v is None:
        return "N/A"
    try:
        n = float(str(v))
    except (ValueError, TypeError):
        return str(v)
    return f"{n:.1f}%"


def _risk_label(score: Any) -> str:
    """Convert numeric risk score to labeled string."""
    if score is None:
        return "N/A"
    try:
        s = float(str(score))
    except (ValueError, TypeError):
        return str(score)
    if s <= 3:
        return f"{s:.0f}/10 (LOW)"
    if s <= 6:
        return f"{s:.0f}/10 (MEDIUM)"
    if s <= 8:
        return f"{s:.0f}/10 (HIGH)"
    return f"{s:.0f}/10 (CRITICAL)"


def _clean_profile(raw: dict) -> dict:
    """Distill the SEC dilution profile to key metrics for the synthesizer."""
    if not isinstance(raw, dict) or "error" in raw:
        return raw

    profile = raw.get("profile", {})
    if not profile:
        return raw

    out: dict[str, Any] = {
        "ticker": profile.get("ticker"),
        "company": profile.get("company_name"),
        "current_price": _fmt_money(profile.get("current_price")),
        "shares_outstanding": _fmt_shares(profile.get("shares_outstanding")),
        "free_float": _fmt_shares(profile.get("free_float")),
    }

    # Warrants summary
    warrants = profile.get("warrants", [])
    if warrants:
        active = [w for w in warrants if w.get("status", "").lower() not in ("expired", "exercised")]
        out["warrants"] = {
            "total": len(warrants),
            "active": len(active),
            "summary": [
                {
                    "exercise_price": _fmt_money(w.get("exercise_price")),
                    "outstanding": _fmt_shares(w.get("outstanding")),
                    "expiration": str(w.get("expiration_date", "N/A")),
                    "status": w.get("status", "unknown"),
                    "price_protection": w.get("price_protection"),
                }
                for w in active[:5]
            ],
        }

    # ATM summary
    atm_list = profile.get("atm_offerings", [])
    if atm_list:
        atm = atm_list[0]
        out["atm_offering"] = {
            "total_capacity": _fmt_money(atm.get("total_capacity")),
            "remaining_capacity": _fmt_money(atm.get("remaining_capacity")),
            "potential_shares_at_current_price": _fmt_shares(atm.get("potential_shares_at_current_price")),
            "placement_agent": atm.get("placement_agent"),
            "status": atm.get("status"),
        }

    # Shelf summary
    shelves = profile.get("shelf_registrations", [])
    if shelves:
        out["shelf_registrations"] = [
            {
                "total_capacity": _fmt_money(s.get("total_capacity")),
                "remaining_capacity": _fmt_money(s.get("remaining_capacity")),
                "is_baby_shelf": s.get("is_baby_shelf"),
                "current_raisable": _fmt_money(s.get("current_raisable_amount")),
                "expiration": str(s.get("expiration_date", "N/A")),
                "registration": s.get("registration_statement"),
            }
            for s in shelves[:3]
        ]

    # Convertibles summary
    conv_notes = profile.get("convertible_notes", [])
    if conv_notes:
        out["convertible_notes"] = [
            {
                "remaining_principal": _fmt_money(n.get("remaining_principal_amount")),
                "conversion_price": _fmt_money(n.get("conversion_price")),
                "remaining_shares_if_converted": _fmt_shares(n.get("remaining_shares_when_converted")),
                "maturity": str(n.get("maturity_date", "N/A")),
            }
            for n in conv_notes[:3]
        ]

    # Equity lines
    eq_lines = profile.get("equity_lines", [])
    if eq_lines:
        out["equity_lines"] = [
            {
                "total_capacity": _fmt_money(e.get("total_capacity")),
                "remaining_capacity": _fmt_money(e.get("remaining_capacity")),
                "end_date": str(e.get("agreement_end_date", "N/A")),
            }
            for e in eq_lines[:2]
        ]

    # Risk assessment from profile
    risk = raw.get("risk_assessment")
    if risk:
        out["risk_assessment"] = {
            "overall_risk": _risk_label(risk.get("overall_risk")),
            "offering_ability": _risk_label(risk.get("offering_ability_risk")),
            "overhead_supply": _risk_label(risk.get("overhead_supply_risk")),
            "historical_dilution": _risk_label(risk.get("historical_risk")),
            "cash_need": _risk_label(risk.get("cash_need_risk")),
        }

    # Data quality
    meta = profile.get("metadata", {})
    if meta:
        out["data_freshness"] = {
            "last_scraped": str(meta.get("last_scraped_at", "unknown"))[:10],
            "filings_analyzed": meta.get("filings_analyzed_count", "N/A"),
        }

    out["cached"] = raw.get("cached", False)
    out["is_spac"] = raw.get("is_spac")

    return out


def _clean_risk_ratings(raw: dict) -> dict:
    """Format risk ratings for readability."""
    if not isinstance(raw, dict) or "error" in raw:
        return raw
    return {
        "ticker": raw.get("ticker"),
        "overall_risk": _risk_label(raw.get("overall_risk")),
        "offering_ability_risk": _risk_label(raw.get("offering_ability_risk")),
        "overhead_supply_risk": _risk_label(raw.get("overhead_supply_risk")),
        "historical_dilution_risk": _risk_label(raw.get("historical_dilution_risk")),
        "cash_need_risk": _risk_label(raw.get("cash_need_risk")),
        "summary": raw.get("summary"),
        "updated_at": str(raw.get("updated_at", ""))[:10],
    }


def _clean_cash_runway(raw: dict) -> dict:
    """Format cash runway data."""
    if not isinstance(raw, dict) or "error" in raw:
        return raw
    return {
        "ticker": raw.get("ticker"),
        "runway_months": raw.get("runway_months"),
        "runway_category": raw.get("runway_category"),
        "cash_position": _fmt_money(raw.get("cash_position")),
        "burn_rate_monthly": _fmt_money(raw.get("burn_rate_monthly")),
        "available_financing": _fmt_money(raw.get("available_financing")),
        "total_runway_with_financing": raw.get("total_runway_with_financing"),
        "data_quality": raw.get("data_quality"),
        "last_updated": str(raw.get("last_updated", ""))[:10],
    }


def _clean_dilution_analysis(raw: dict) -> dict:
    """Format potential dilution analysis."""
    if not isinstance(raw, dict) or "error" in raw:
        return raw
    return {
        "ticker": raw.get("ticker"),
        "total_potential_dilution_pct": _fmt_pct(raw.get("total_potential_dilution_pct")),
        "by_instrument": {
            "warrants": _fmt_pct(raw.get("warrants_dilution_pct")),
            "atm": _fmt_pct(raw.get("atm_dilution_pct")),
            "shelf": _fmt_pct(raw.get("shelf_dilution_pct")),
            "convertible_notes": _fmt_pct(raw.get("convertible_notes_dilution_pct")),
            "convertible_preferred": _fmt_pct(raw.get("convertible_preferred_dilution_pct")),
            "equity_lines": _fmt_pct(raw.get("equity_lines_dilution_pct")),
        },
        "assumptions": raw.get("assumptions", {}),
    }


def _clean_instrument_context(raw: dict) -> dict:
    """Clean instrument context: keep key fields, humanize numbers."""
    if not isinstance(raw, dict) or "error" in raw:
        return raw

    ticker_info = raw.get("ticker_info", {})
    out: dict[str, Any] = {
        "company": ticker_info.get("company"),
        "ticker": ticker_info.get("ticker"),
        "shares_outstanding": _fmt_shares(ticker_info.get("shares_outstanding")),
        "float_shares": _fmt_shares(ticker_info.get("float_shares")),
        "market_cap": _fmt_money(ticker_info.get("market_cap")),
        "cash_position": _fmt_money(ticker_info.get("cash_position")),
        "last_price": _fmt_money(ticker_info.get("last_price")),
        "inst_ownership": _fmt_pct(ticker_info.get("inst_ownership")),
        "short_interest": _fmt_pct(ticker_info.get("short_interest")),
        "num_offerings": ticker_info.get("num_offerings"),
    }

    # Instruments by type
    instruments = raw.get("instruments", [])
    by_type: dict[str, list] = {}
    for inst in instruments:
        otype = inst.get("offering_type", "Other")
        details = inst.get("details", {})
        cleaned = {
            "security_name": inst.get("security_name"),
            "card_color": inst.get("card_color"),
            "reg_status": inst.get("reg_status"),
            "last_update": str(inst.get("last_update_date", ""))[:10],
        }
        # Add type-specific key fields
        if otype == "ATM":
            cleaned["total_capacity"] = _fmt_money(details.get("total_atm_capacity"))
            cleaned["remaining_capacity"] = _fmt_money(details.get("remaining_atm_capacity"))
            cleaned["baby_shelf_limited"] = details.get("atm_limited_by_baby_shelf")
            cleaned["remaining_wo_baby_shelf"] = _fmt_money(details.get("remaining_capacity_wo_bs"))
            cleaned["placement_agent"] = details.get("placement_agent")
        elif otype == "Shelf":
            cleaned["total_capacity"] = _fmt_money(details.get("total_shelf_capacity"))
            cleaned["current_raisable"] = _fmt_money(details.get("current_raisable_amount"))
            cleaned["baby_shelf_restriction"] = details.get("baby_shelf_restriction")
            cleaned["expiration"] = str(details.get("expiration_date", ""))[:10]
            cleaned["last_banker"] = details.get("last_banker")
        elif otype == "Warrant":
            cleaned["remaining_warrants"] = _fmt_shares(details.get("remaining_warrants"))
            cleaned["exercise_price"] = _fmt_money(details.get("exercise_price"))
            cleaned["price_protection"] = details.get("price_protection")
            cleaned["expiration"] = str(details.get("expiration_date", ""))[:10]
        elif otype == "Convertible Note":
            cleaned["remaining_principal"] = _fmt_money(details.get("remaining_principal"))
            cleaned["conversion_price"] = _fmt_money(details.get("conversion_price"))
            cleaned["remaining_shares_converted"] = _fmt_shares(details.get("remaining_shares_converted"))
            cleaned["maturity"] = str(details.get("maturity_date", ""))[:10]
        elif otype == "Convertible Preferred":
            cleaned["remaining_dollar_amount"] = _fmt_money(details.get("remaining_dollar_amount"))
            cleaned["conversion_price"] = _fmt_money(details.get("conversion_price"))
            cleaned["remaining_shares_converted"] = _fmt_shares(details.get("remaining_shares_converted"))
        elif otype == "Equity Line":
            cleaned["total_capacity"] = _fmt_money(details.get("total_el_capacity"))
            cleaned["remaining_capacity"] = _fmt_money(details.get("remaining_el_capacity"))
            cleaned["end_date"] = str(details.get("agreement_end_date", ""))[:10]
        elif otype == "S-1 Offering":
            cleaned["status"] = details.get("status")
            cleaned["anticipated_deal_size"] = _fmt_money(details.get("anticipated_deal_size"))
            cleaned["final_deal_size"] = _fmt_money(details.get("final_deal_size"))
            cleaned["underwriter"] = details.get("underwriter")

        by_type.setdefault(otype, []).append(cleaned)

    out["instruments_by_type"] = by_type
    out["stats"] = raw.get("stats", {})

    # Completed offerings summary
    completed = raw.get("completed_offerings", [])
    if completed:
        out["completed_offerings_recent"] = [
            {
                "date": str(c.get("offering_date", ""))[:10],
                "type": c.get("offering_type"),
                "method": c.get("method"),
                "shares": _fmt_shares(c.get("shares")),
                "price": _fmt_money(c.get("price")),
                "amount_raised": _fmt_money(c.get("amount")),
                "bank": c.get("bank"),
                "warrants_attached": c.get("warrants"),
            }
            for c in completed[:5]
        ]

    return out


# ── Tier 2: LLM Fallback Research ────────────────────────────────────────────

def _db_has_no_data(profile_raw: Any, instrument_ctx_raw: Any = None) -> bool:
    """
    Return True when this ticker is NOT in our active dilution tracking DB.

    Key distinction (per product design):
    ┌─────────────────────────────────────────────────────────────────────────┐
    │ Tier 1 (our DB):                                                        │
    │   - Candidate in DB with instruments → full analysis                   │
    │   - Candidate in DB WITHOUT instruments yet → monitoring candidate      │
    │     (low cash / high outstanding, we watch for future events)           │
    │   → Do NOT fall back to EDGAR RAG for these — they are known.          │
    │                                                                         │
    │ Tier 2 (EDGAR RAG):                                                     │
    │   - Company NOT in our tracking DB (e.g. CRWV, large-caps, new IPOs)   │
    │   → Use EDGAR XBRL + cover pages to provide ad-hoc analysis            │
    └─────────────────────────────────────────────────────────────────────────┘

    The authoritative signal is `get_instrument_context` (dilutiontracker DB):
    - Returns {"ticker_info": {...}} → ticker IS in our tracking DB → Tier 1
    - Returns {"detail": "Ticker X not found"} → NOT in our DB → Tier 2

    As a secondary check, if instrument_context result is unavailable, we fall
    back to inspecting the sec profile response for hard error signals only.
    """
    # Primary signal: instrument_context response (dilutiontracker DB)
    if instrument_ctx_raw is not None:
        if isinstance(instrument_ctx_raw, dict):
            # "Ticker X not found" = not in our active tracking DB → Tier 2
            if "detail" in instrument_ctx_raw and "not found" in str(instrument_ctx_raw["detail"]).lower():
                return True
            # Has ticker_info → in our DB → Tier 1
            if instrument_ctx_raw.get("ticker_info"):
                return False
            # Explicit error → also treat as Tier 2
            if "error" in instrument_ctx_raw:
                return True

    # Secondary fallback: check the sec profile response for hard HTTP errors
    if not isinstance(profile_raw, dict):
        return True
    # 404 detail message from the sec-dilution endpoint
    if "detail" in profile_raw:
        return True
    # Explicit error key
    if "error" in profile_raw:
        return True

    return False


_FALLBACK_LLM = None

def _get_fallback_llm():
    global _FALLBACK_LLM
    if _FALLBACK_LLM is None:
        from agents._make_llm import make_llm
        _FALLBACK_LLM = make_llm(tier="fast", temperature=0.0, max_tokens=4096)
    return _FALLBACK_LLM


# ── Tier 2: LLM prompt (RAG quirúrgico — solo cover pages) ──────────────────

_RAG_SYSTEM = """\
You are a senior dilution analyst. You receive STRUCTURED financial data (already extracted,
no LLM needed) and SHORT cover-page excerpts from SEC filings.

Your job: extract dilutive instrument terms from the cover page text, then combine with the
structured financial data to build a complete dilution profile.

IMPORTANT ABOUT XBRL DATA:
- The XBRL share counts are extracted from EDGAR and should be accurate, BUT:
  - For dual/multi-class companies (Class A, Class B, etc.), values are already SUMMED across classes.
  - "pre_ipo_periods_excluded" tells you how many pre-IPO quarters were removed from history.
  - "ipo_date_approx" tells you when the company went public — ONLY compare post-IPO share counts.
  - NEVER compare pre-IPO private share structure to post-IPO public float.
  - If shares_change_pct is provided, it is computed only over the public (post-IPO) period.
- For instrument details (warrants, ATM, shelf, M&A), extract ONLY what appears in cover pages.
- Set fields to null if not found. NEVER invent numbers.

WHAT TO LOOK FOR IN COVER PAGES:

S-3 / F-3: Shelf registration — look for total offering size, security types.
  Baby shelf applies if public float < $75M (company may not raise > 1/3 float in 12mo).
424B4 / 424B5: Completed offering — shares issued, price/share, warrants attached, underwriter.
S-1 / F-1: IPO or primary offering — total deal size, warrants, lock-up.
8-K: Warrant issuance / PIPE / convertible note — look for exercise price, maturity, conversion.
ATM: Phrase "at the market" in S-3 or 424B3 — total program size, placement agent.
S-4 / S-4/A: Business combination (M&A) — shares registered for acquisition.
  Look for: exchange ratio, number of shares to be issued, target company name, deal value.
  This is a MAJOR dilutive event. Report in completed_offerings with method="stock_acquisition".

RISK SCORING (1-10):
- offering_ability: Can the company easily raise more? (1=no shelf, 10=large shelf+ATM active)
- overhead_supply: Warrant/convertible/M&A share selling pressure vs. float (1=none, 10=>50% float)
- historical_dilution: Share count growth in XBRL POST-IPO history (1=stable, 10=doubled+ since IPO)
- cash_need: Urgency from XBRL cash/burn data (1=18+ months runway, 10=<3 months or negative CF)
- overall_risk: Weighted composite (offering_ability*0.2 + overhead_supply*0.3 + historical*0.2 + cash_need*0.3)

OUTPUT: strict JSON only, no markdown fences.
{
  "ticker": "XXXX",
  "company_name": "...",
  "data_source": "edgar_rag",
  "confidence": "high|medium|low",
  "analysis_notes": "what was found, key caveats",
  "warrants": [{"series_name":null,"outstanding":null,"exercise_price":null,"expiration_date":null,"issue_date":null,"status":"active","price_protection":"none"}],
  "atm_offerings": [{"total_capacity":null,"placement_agent":null,"filing_date":null,"status":"active"}],
  "shelf_registrations": [{"total_capacity":null,"is_baby_shelf":null,"filing_date":null,"expiration_date":null,"registration_statement":"S-3","security_type":null}],
  "convertible_notes": [{"total_principal_amount":null,"conversion_price":null,"maturity_date":null,"issue_date":null}],
  "equity_lines": [],
  "completed_offerings": [{"offering_date":null,"offering_type":null,"method":null,"shares_issued":null,"price_per_share":null,"amount_raised":null,"bank":null}],
  "risk_scores": {"overall_risk":"Medium","overall_score":5,"offering_ability":"Low","offering_ability_score":3,"overhead_supply":"Low","overhead_supply_score":2,"historical_dilution":"Medium","historical_dilution_score":5,"cash_need":"High","cash_need_score":7}
}
"""


async def _dilution_fallback_research(
    ticker: str,
    focuses: set[str],
    ticker_info: dict,
) -> dict:
    """
    Tier 2 fallback: RAG-based dilution analysis for tickers not in our DB.

    Architecture (CS230 RAG quirúrgico — 10x cheaper/faster than reading full filings):
      Step 1 [structured, 0 tokens]: EDGAR XBRL → shares outstanding + cash/burn
      Step 2 [structured, 0 tokens]: EDGAR submissions → recent dilutive filing list
      Step 3 [minimal text, ~600 tok each]: cover pages of S-3/424B5/8-K only
      Step 4 [LLM with focused context]: extract instruments + risk from cover pages

    Token comparison:
      Old: 30 filings × ~1500 tokens each = ~45,000 tokens → slow + expensive
      New: XBRL structured + N × 600-token cover pages = ~5,000 tokens → fast + cheap
    """
    from langchain_core.messages import SystemMessage, HumanMessage
    from agents._edgar_client import (
        get_cik, get_submissions, get_company_facts,
        get_cover_page, summarize_xbrl,
    )

    llm = _get_fallback_llm()
    company = ticker_info.get("company_name", ticker_info.get("company", ticker))
    logger.info("dilution_fallback_start ticker=%s", ticker)

    # ── Step 1: Resolve CIK ───────────────────────────────────────────────────
    cik = await get_cik(ticker)
    if not cik:
        logger.warning("dilution_fallback_no_cik ticker=%s", ticker)
        return {
            "ticker": ticker, "source": "edgar_rag",
            "error": f"Could not resolve EDGAR CIK for {ticker}. May not be an SEC-registered company.",
        }

    # ── Step 2 & 3: Parallel — XBRL facts + recent filings list ─────────────
    facts_task = get_company_facts(cik)
    subs_task = get_submissions(cik)
    facts_raw, subs = await asyncio.gather(facts_task, subs_task)

    # Structured financial data (no LLM needed)
    ipo_date = subs.get("ipo_date")  # None for established companies, date string for recent IPOs
    xbrl_summary = summarize_xbrl(facts_raw, ipo_date=ipo_date)
    company_name = subs.get("name", company)
    filings = subs.get("filings", [])

    logger.info(
        "dilution_fallback_edgar cik=%s filings=%d xbrl_shares=%s",
        cik, len(filings),
        bool(xbrl_summary.get("shares_outstanding_latest")),
    )

    # ── Step 4: Fetch cover pages in parallel (only first 4KB per filing) ────
    # Priority: S-4 (M&A) > S-3/F-3 (shelf) > 424Bx > S-1 > 8-K. Cap at 10 cover pages.
    _FORM_PRIORITY = {
        "S-4": 0, "S-4/A": 0,           # Business combination — highest priority
        "S-3": 1, "F-3": 1, "S-3/A": 1, # Shelf registrations
        "424B5": 2, "424B4": 2,          # Prospectus supplements
        "S-1": 3, "F-1": 3, "S-1/A": 3, # Primary offerings
        "8-K": 4,                        # Material events
    }
    sorted_filings = sorted(filings, key=lambda f: _FORM_PRIORITY.get(f["form"], 9))[:10]

    cover_tasks = [
        get_cover_page(cik, f["accn"], f["primary_doc"])
        for f in sorted_filings
        if f.get("primary_doc")
    ]
    cover_pages_raw = await asyncio.gather(*cover_tasks)

    # Build cover page context: "DATE | FORM\n{text}\n---"
    cover_sections = []
    for filing, text in zip(sorted_filings, cover_pages_raw):
        if text:
            cover_sections.append(
                f"[{filing['date']} | {filing['form']}]\n{text[:2000]}"
            )
    cover_text = "\n---\n".join(cover_sections) if cover_sections else "No cover pages retrieved."

    # ── Step 5: LLM with compact context ─────────────────────────────────────
    human_msg = f"""TICKER: {ticker}
COMPANY: {company_name}
EDGAR CIK: {cik}

=== STRUCTURED FINANCIAL DATA (from EDGAR XBRL — 100% accurate, do not modify) ===
{json.dumps(xbrl_summary, indent=2)}

=== DILUTIVE FILING COVER PAGES (extract instrument terms from these) ===
{cover_text}

Extract all dilutive instruments and risk scores. Only use data explicitly present above.
"""

    messages = [
        SystemMessage(content=_RAG_SYSTEM),
        HumanMessage(content=human_msg),
    ]

    try:
        response = await llm_invoke_with_retry(llm, messages)
        raw_text = response.content.strip()
        if raw_text.startswith("```"):
            raw_text = raw_text.split("```")[1]
            if raw_text.lower().startswith("json"):
                raw_text = raw_text[4:]
            raw_text = raw_text.strip()
        extracted = json.loads(raw_text)
    except (json.JSONDecodeError, Exception) as exc:
        logger.warning("dilution_fallback_llm_error ticker=%s error=%s", ticker, exc)
        extracted = {
            "ticker": ticker, "company_name": company_name,
            "data_source": "edgar_rag", "confidence": "low",
            "analysis_notes": f"LLM parse error: {exc}",
            "warrants": [], "atm_offerings": [], "shelf_registrations": [],
            "convertible_notes": [], "equity_lines": [], "completed_offerings": [],
            "risk_scores": {},
        }

    # ── Step 6: Format into standard profile schema ───────────────────────────
    risk = extracted.get("risk_scores", {})
    warrants = extracted.get("warrants", [])
    atm_list = extracted.get("atm_offerings", [])
    shelves = extracted.get("shelf_registrations", [])
    conv_notes = extracted.get("convertible_notes", [])
    eq_lines = extracted.get("equity_lines", [])
    completed = extracted.get("completed_offerings", [])

    result: dict[str, Any] = {
        "ticker": ticker,
        "company": company_name,
        "source": "edgar_rag",
        "confidence": extracted.get("confidence", "medium"),
        "analysis_notes": extracted.get("analysis_notes", ""),
        "data_freshness": {
            "method": "EDGAR XBRL + cover pages (RAG)",
            "filings_analyzed": len(cover_sections),
            "xbrl_cash_period": (xbrl_summary.get("cash_latest") or {}).get("period"),
            "xbrl_shares_period": (xbrl_summary.get("shares_outstanding_latest") or {}).get("period"),
        },
    }

    # XBRL-derived structured data (most accurate)
    shares_latest = xbrl_summary.get("shares_outstanding_latest", {})
    cash_latest = xbrl_summary.get("cash_latest", {})
    if shares_latest.get("shares"):
        result["shares_outstanding"] = _fmt_shares(shares_latest["shares"])
        result["shares_history"] = xbrl_summary.get("shares_history", [])
        result["shares_change_pct"] = xbrl_summary.get("shares_change_pct")
    if cash_latest.get("usd"):
        runway_months = xbrl_summary.get("estimated_runway_months")
        result["cash_runway"] = {
            "estimated_cash": _fmt_money(cash_latest["usd"]),
            "data_period": cash_latest.get("period"),
            "quarterly_operating_cf": _fmt_money(xbrl_summary.get("quarterly_operating_cf")),
            "runway_months": runway_months,
            "runway_category": (
                "CRITICAL" if runway_months and runway_months < 3
                else "LOW" if runway_months and runway_months < 6
                else "MODERATE" if runway_months and runway_months < 12
                else "ADEQUATE" if runway_months else "N/A"
            ),
        }

    # LLM-extracted instrument data
    if warrants:
        result["warrants"] = {
            "total": len(warrants),
            "active": len([w for w in warrants if (w.get("status") or "active") == "active"]),
            "summary": [
                {
                    "series": w.get("series_name"),
                    "exercise_price": _fmt_money(w.get("exercise_price")),
                    "outstanding": _fmt_shares(w.get("outstanding")),
                    "expiration": str(w.get("expiration_date") or "N/A"),
                    "price_protection": w.get("price_protection", "none"),
                }
                for w in warrants[:5] if w.get("exercise_price") is not None
            ],
        }

    if atm_list:
        a = atm_list[0]
        result["atm_offering"] = {
            "total_capacity": _fmt_money(a.get("total_capacity")),
            "placement_agent": a.get("placement_agent"),
            "filing_date": str(a.get("filing_date") or ""),
            "status": a.get("status", "active"),
        }

    if shelves:
        result["shelf_registrations"] = [
            {
                "total_capacity": _fmt_money(s.get("total_capacity")),
                "is_baby_shelf": s.get("is_baby_shelf"),
                "filing_date": str(s.get("filing_date") or ""),
                "expiration": str(s.get("expiration_date") or ""),
                "registration": s.get("registration_statement"),
            }
            for s in shelves[:3] if s.get("total_capacity") is not None
        ]

    if conv_notes:
        result["convertible_notes"] = [
            {
                "principal": _fmt_money(n.get("total_principal_amount")),
                "conversion_price": _fmt_money(n.get("conversion_price")),
                "maturity": str(n.get("maturity_date") or ""),
            }
            for n in conv_notes[:3] if n.get("total_principal_amount") is not None
        ]

    if completed:
        result["completed_offerings_recent"] = [
            {
                "date": str(c.get("offering_date") or ""),
                "type": c.get("offering_type"),
                "method": c.get("method"),
                "shares": _fmt_shares(c.get("shares_issued")),
                "price": _fmt_money(c.get("price_per_share")),
                "amount_raised": _fmt_money(c.get("amount_raised")),
                "bank": c.get("bank"),
            }
            for c in completed[:5] if c.get("amount_raised") is not None
        ]

    if risk:
        result["risk_assessment"] = {
            "overall_risk": f"{risk.get('overall_risk','N/A')} ({risk.get('overall_score','?')}/10)",
            "offering_ability": f"{risk.get('offering_ability','N/A')} ({risk.get('offering_ability_score','?')}/10)",
            "overhead_supply": f"{risk.get('overhead_supply','N/A')} ({risk.get('overhead_supply_score','?')}/10)",
            "historical_dilution": f"{risk.get('historical_dilution','N/A')} ({risk.get('historical_dilution_score','?')}/10)",
            "cash_need": f"{risk.get('cash_need','N/A')} ({risk.get('cash_need_score','?')}/10)",
        }

    logger.info(
        "dilution_fallback_complete ticker=%s warrants=%d shelves=%d cover_pages=%d",
        ticker, len(warrants), len(shelves), len(cover_sections),
    )
    return result


# ── Main node ─────────────────────────────────────────────────────────────────

async def dilution_node(state: dict) -> dict:
    """Fetch dilution analysis from the Tradeul dilution tracker service."""
    start_time = time.time()

    query = state.get("query", "")
    agent_task = state.get("agent_task", query)
    tickers = state.get("tickers", [])

    if not tickers:
        elapsed_ms = int((time.time() - start_time) * 1000)
        return {
            "agent_results": {
                "dilution": {
                    "error": (
                        "No ticker detected. Please specify a stock symbol "
                        "(e.g. $NVAX, $MARA, $ILUS)."
                    ),
                },
            },
            "execution_metadata": {
                **(state.get("execution_metadata", {})),
                "dilution": {"elapsed_ms": elapsed_ms, "tickers": [], "error": "no_ticker"},
            },
        }

    focuses = _focus(agent_task)
    results: dict[str, Any] = {}
    errors: list[str] = []
    ticker_str = ", ".join(f"${t}" for t in tickers[:3])

    # ── Progress event helper ──────────────────────────────────────────────────
    async def _progress(msg: str) -> None:
        """Emit a custom progress event visible in the chat UI step indicator."""
        try:
            from langchain_core.callbacks import adispatch_custom_event  # noqa: PLC0415
            await adispatch_custom_event("dilution_progress", {"message": msg})
        except Exception:
            pass  # Never block the agent if progress dispatch fails

    async def _fetch_for_ticker(ticker: str) -> tuple[str, dict, list[str]]:
        """Determine tools to call based on focus, then call them in parallel."""
        t_data: dict[str, Any] = {}
        t_errors: list[str] = []
        calls: list[tuple[str, str, dict]] = []  # (key, tool_name, args)

        # Determine which tools to call based on detected focus
        is_full = "full" in focuses or not focuses
        # Default (no specific keyword) → SEC profile covers most use cases

        if is_full:
            # Full analysis: enhanced profile + instrument context + risk
            calls = [
                ("profile", "get_sec_dilution_profile", {"ticker": ticker}),
                ("instrument_context", "get_instrument_context", {"ticker": ticker}),
                ("risk_ratings", "get_dilution_risk_ratings", {"ticker": ticker}),
                ("cash_runway", "get_cash_runway", {"ticker": ticker}),
                ("dilution_analysis", "get_dilution_analysis", {"ticker": ticker}),
            ]
        else:
            # Always get base profile + instrument_context (the latter is the
            # authoritative signal for whether this ticker is in our tracking DB)
            calls.append(("profile", "get_sec_dilution_profile", {"ticker": ticker}))
            calls.append(("instrument_context", "get_instrument_context", {"ticker": ticker}))

            if "warrant" in focuses:
                calls.append(("warrants_detail", "get_warrants", {"ticker": ticker}))

            if "atm" in focuses or "shelf" in focuses:
                calls.append(("instrument_context", "get_instrument_context", {"ticker": ticker}))

            if "cash" in focuses:
                calls.append(("cash_position", "get_cash_position", {"ticker": ticker}))
                calls.append(("cash_runway", "get_cash_runway", {"ticker": ticker}))

            if "risk" in focuses:
                calls.append(("risk_ratings", "get_dilution_risk_ratings", {"ticker": ticker}))

            if "history" in focuses:
                calls.append(("shares_history", "get_shares_history", {"ticker": ticker}))
                calls.append(("completed_offerings", "get_completed_offerings", {"ticker": ticker}))

            if "instruments" in focuses:
                calls.append(("instrument_context", "get_instrument_context", {"ticker": ticker}))

            if "potential" in focuses:
                calls.append(("dilution_analysis", "get_dilution_analysis", {"ticker": ticker}))
                calls.append(("risk_ratings", "get_dilution_risk_ratings", {"ticker": ticker}))

        # Deduplicate calls by key
        seen_keys: set[str] = set()
        unique_calls = []
        for call in calls:
            if call[0] not in seen_keys:
                seen_keys.add(call[0])
                unique_calls.append(call)

        # Execute all calls concurrently
        async def _call(key: str, tool: str, args: dict):
            try:
                raw = await call_mcp_tool("dilution", tool, args)
                return key, raw, None
            except Exception as exc:
                return key, None, str(exc)

        fetch_results = await asyncio.gather(*[
            _call(k, t, a) for k, t, a in unique_calls
        ])

        profile_raw = None
        for key, raw, err in fetch_results:
            if err:
                t_errors.append(f"dilution/{ticker}/{key}: {err}")
                continue
            # Apply type-specific cleaners
            if key == "profile":
                profile_raw = raw  # keep reference for fallback check
                t_data[key] = _clean_profile(raw)
            elif key == "risk_ratings":
                t_data[key] = _clean_risk_ratings(raw)
            elif key == "cash_runway":
                t_data[key] = _clean_cash_runway(raw)
            elif key == "dilution_analysis":
                t_data[key] = _clean_dilution_analysis(raw)
            elif key == "instrument_context":
                t_data[key] = _clean_instrument_context(raw)
            else:
                # warrants_detail, shares_history, completed_offerings,
                # cash_position — keep raw (already structured)
                t_data[key] = raw

        # ── Tier 2 Fallback: ticker NOT in our active tracking DB ─────────
        # Signal: instrument_context returned "not found" (dilutiontracker DB).
        # Companies in our DB without current instruments are MONITORING CANDIDATES
        # — they should stay in Tier 1 (we know them and watch them).
        # Only companies we've never tracked get EDGAR RAG.
        instrument_ctx_raw = t_data.get("instrument_context")
        if instrument_ctx_raw is None:
            # instrument_context call failed (went to t_errors) — use the raw error
            # Look for it in errors to decide
            ic_error = next(
                (e for e in t_errors if f"/{ticker}/instrument_context" in e), None
            )
            if ic_error and "not found" in ic_error.lower():
                instrument_ctx_raw = {"detail": "not found"}
        if _db_has_no_data(profile_raw, instrument_ctx_raw):
            logger.info("dilution_fallback_triggered ticker=%s existing_keys=%s", ticker, list(t_data.keys()))
            await _progress(f"${ticker} no está en nuestra BD — buscando en EDGAR (XBRL + filings)…")
            # Grab basic ticker info from the profile error response (if any)
            ticker_info_extra = profile_raw or {}
            fallback = await _dilution_fallback_research(ticker, focuses, ticker_info_extra)
            await _progress(f"${ticker}: análisis EDGAR completado ({(fallback.get('data_freshness') or {}).get('filings_analyzed', 0)} filings leídos)")
            # Merge: keep existing financial data (cash_position, cash_runway, shares_history),
            # overlay with EDGAR RAG instrument data (warrants, shelf, ATM, etc.)
            t_data["profile"] = fallback
            t_data["_tier"] = "edgar_rag"
            t_data["_note"] = (
                f"{ticker} has no instrument data in our dilution tracker yet. "
                "Instrument analysis (warrants, shelf, ATM) was generated via EDGAR RAG "
                "(XBRL structured data + filing cover pages). "
                "Financial data (cash/runway) comes from our XBRL database where available."
            )

        return ticker, t_data, t_errors

    # ── Emit initial progress so the UI shows the step immediately ────────────
    focus_label = ", ".join(sorted(focuses)[:3]) if focuses else "overview"
    await _progress(f"Consultando base de datos de dilución para {ticker_str} ({focus_label})…")

    # Fetch for up to 3 tickers in parallel
    ticker_results = await asyncio.gather(*[
        _fetch_for_ticker(t) for t in tickers[:3]
    ])

    for ticker, t_data, t_errors in ticker_results:
        results[ticker] = t_data
        errors.extend(t_errors)

    if errors:
        results["_errors"] = errors

    elapsed_ms = int((time.time() - start_time) * 1000)

    return {
        "agent_results": {
            "dilution": {
                "tickers_analyzed": tickers[:3],
                "focuses_detected": list(focuses) if focuses else ["overview"],
                **results,
            },
        },
        "execution_metadata": {
            **(state.get("execution_metadata", {})),
            "dilution": {
                "elapsed_ms": elapsed_ms,
                "tickers": tickers[:3],
                "focuses": list(focuses),
                "error_count": len(errors),
            },
        },
    }
