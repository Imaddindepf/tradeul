"""
MCP Server: Dilution Tracker
SEC filing analysis for stock dilution, warrants, ATM offerings, and cash runway.

Routes map directly to the dilution-tracker service endpoints:
  - /api/sec-dilution/{ticker}/...   → SEC-extracted data (via Grok/LLM pipeline)
  - /api/instrument-context/{ticker} → Curated analyst data (dilutiontracker DB v2)
  - /api/analysis/trending           → Trending tickers by dilution activity
"""
from fastmcp import FastMCP
from clients.http_client import service_get
from config import config

mcp = FastMCP(
    "Tradeul Dilution Tracker",
    instructions=(
        "Stock dilution analysis service that tracks SEC filings for dilution risk. "
        "Two complementary data sources: (1) sec-dilution — LLM-extracted data from SEC EDGAR "
        "filings including warrants, ATM offerings, shelf registrations, convertible notes, "
        "preferred shares, equity lines, S-1 offerings, cash runway; "
        "(2) instrument-context — curated analyst data from dilutiontracker DB with precise "
        "instrument details (ATM capacity, shelf baby-shelf restrictions, warrant exercise prices, "
        "convertible note principals, equity line capacities). "
        "Risk scoring covers: overall_risk, offering_ability, overhead_supply, "
        "historical_dilution, cash_need (each 1-10 scale). "
        "Critical for small-cap and micro-cap analysis where dilution is the #1 risk factor."
    ),
)


# ── Core profile endpoints ────────────────────────────────────────────────────

@mcp.tool()
async def get_sec_dilution_profile(ticker: str) -> dict:
    """Get comprehensive SEC-extracted dilution profile for a ticker.

    Returns the full picture from SEC EDGAR filings (LLM-extracted):
    warrants, ATM offerings, shelf registrations, completed offerings,
    S-1 offerings, convertible notes, convertible preferred shares,
    equity lines, warrant lifecycle events, shares outstanding,
    free float, current price, risk assessment scores, and cache metadata.

    Use this as the primary entry point for dilution analysis.
    """
    try:
        return await service_get(
            config.dilution_tracker_url,
            f"/api/sec-dilution/{ticker.upper()}/profile",
        )
    except Exception as e:
        return {"error": str(e), "ticker": ticker.upper()}


@mcp.tool()
async def get_enhanced_profile(ticker: str) -> dict:
    """Get the enhanced dilution profile with additional enrichment.

    Combines SEC-extracted data with cash position, cash runway calculation,
    and instrument-level detail. More complete than get_sec_dilution_profile
    but may be slower. Use when you need the full picture in one call.
    """
    try:
        return await service_get(
            config.dilution_tracker_url,
            f"/api/sec-dilution/{ticker.upper()}/enhanced-profile",
        )
    except Exception as e:
        return {"error": str(e), "ticker": ticker.upper()}


@mcp.tool()
async def get_instrument_context(ticker: str, include_completed_offerings: bool = True) -> dict:
    """Get curated analyst instrument context from the dilutiontracker v2 database.

    This is the MOST ACCURATE and DETAILED source for instrument data.
    Returns instruments maintained by analysts in the dilutiontracker DB:
    - ticker_info: company name, float_shares, inst_ownership, short_interest,
      market_cap, enterprise_value, cash_per_share, shares_outstanding,
      cash_position, last_price, num_offerings
    - instruments: list of all active instruments with full detail by type:
        ATM: total/remaining ATM capacity, baby-shelf limited flag,
             remaining capacity without baby-shelf, placement agent
        Shelf: total capacity, current raisable amount, baby-shelf restriction,
               outstanding/float shares, highest 60-day close, IB6 values,
               effect/expiration dates, last banker
        Warrant: remaining/total warrants, exercise price, price protection,
                 issue/exercisable/expiration dates, known owners, underwriter
        Convertible Note: remaining/total principal, conversion price,
                          remaining/total shares when converted, maturity date
        Convertible Preferred: remaining dollar amount, conversion price,
                               shares when converted, maturity date
        Equity Line: total/remaining capacity, agreement dates, current shares equiv
        S-1 Offering: anticipated/final deal size, status, warrant coverage,
                      final pricing and shares offered
    - completed_offerings: historical offerings with date, type, method,
      shares, price, warrants, amount raised, bank
    - stats: total instruments, by type breakdown, registered vs pending

    This data is more precise than SEC-extracted data for current instrument status.
    """
    try:
        params = ""
        if include_completed_offerings:
            params = "?include_completed_offerings=true"
        return await service_get(
            config.dilution_tracker_url,
            f"/api/instrument-context/{ticker.upper()}{params}",
        )
    except Exception as e:
        return {"error": str(e), "ticker": ticker.upper()}


# ── Individual instrument endpoints ──────────────────────────────────────────

@mcp.tool()
async def get_warrants(ticker: str) -> dict:
    """Get all outstanding warrants for a ticker from SEC filings.

    Returns per warrant: exercise price, expiration date, shares underlying,
    series name, status (active/expired/exercised), issue date,
    exercisable date, warrant type, price protection clauses,
    warrant lifecycle events (exercises, cashless exercises, adjustments),
    price adjustment history.

    Key metrics to watch:
    - exercise_price vs current_price: if below current price → in-the-money warrants
      represent immediate dilution risk when exercised
    - expiration_date: warrants near expiry may be exercised in bulk
    - price_protection: 'full ratchet' or 'weighted average' clauses mean
      the exercise price resets lower on new offerings → ongoing dilution risk
    """
    try:
        return await service_get(
            config.dilution_tracker_url,
            f"/api/sec-dilution/{ticker.upper()}/warrants",
        )
    except Exception as e:
        return {"error": str(e), "ticker": ticker.upper()}


@mcp.tool()
async def get_atm_offerings(ticker: str) -> dict:
    """Get at-the-market (ATM) offering details for a ticker.

    ATM offerings allow companies to sell shares gradually at market price
    through a placement agent (typically a bank). The company can activate
    the offering at any time, so remaining capacity = potential dilution.

    Returns: total ATM capacity, remaining capacity, placement agent,
    agreement start date, filing URL, potential shares at current price,
    status, notes.

    Key analysis:
    - remaining_capacity / market_cap = % dilution if fully used
    - Baby-shelf rule: companies with market cap < $75M cannot use standard
      shelf; remaining ATM may be constrained by this rule
    """
    try:
        return await service_get(
            config.dilution_tracker_url,
            f"/api/sec-dilution/{ticker.upper()}/atm-offerings",
        )
    except Exception as e:
        return {"error": str(e), "ticker": ticker.upper()}


@mcp.tool()
async def get_shelf_registrations(ticker: str) -> dict:
    """Get shelf registration (S-3/S-1) details for a ticker.

    Shelf registrations allow companies to issue securities over time
    (typically 3 years) without filing a new registration each time.

    Returns: total capacity, remaining capacity, is_baby_shelf flag,
    filing date, registration type (S-3, S-3/A), expiration date,
    security_type, current_raisable_amount (considering baby-shelf),
    total_amount_raised, total_amount_raised_last_12mo,
    baby_shelf_restriction flag, effect date, last banker.

    Baby-shelf rule (critical for small caps):
    - Companies with public float < $75M are restricted to raising
      at most 1/3 of their public float in any 12-month period
    - When baby_shelf_restriction=True, remaining capacity is LESS than shown
    """
    try:
        return await service_get(
            config.dilution_tracker_url,
            f"/api/sec-dilution/{ticker.upper()}/shelf-registrations",
        )
    except Exception as e:
        return {"error": str(e), "ticker": ticker.upper()}


@mcp.tool()
async def get_completed_offerings(ticker: str) -> dict:
    """Get historical completed offerings for a ticker.

    Shows the track record of capital raises: dates, types, amounts,
    shares issued, prices paid. Critical for evaluating management's
    dilution history and predicting future behavior.

    Returns per offering: offering_date, offering_type (PIPE, public offering,
    registered direct, S-1, etc.), method (firm commitment, best efforts),
    shares_issued, price_per_share, amount_raised, warrants attached, bank.

    Analysis tips:
    - Frequent offerings at discounts = aggressive dilution pattern
    - Warrants attached to offerings = additional future dilution
    - Price trend across offerings reveals equity story trajectory
    """
    try:
        return await service_get(
            config.dilution_tracker_url,
            f"/api/sec-dilution/{ticker.upper()}/completed-offerings",
        )
    except Exception as e:
        return {"error": str(e), "ticker": ticker.upper()}


# ── Cash & financial position ─────────────────────────────────────────────────

@mcp.tool()
async def get_cash_position(ticker: str) -> dict:
    """Get current cash position and recent capital raises for a ticker.

    Combines: dt_cash_position (analyst-curated quarterly cash in millions),
    dt_cash_meta (burn rate, recent offerings), and SEC XBRL fallback.

    Returns: cash_millions (most recent quarter), period_date, quarterly
    operating cash flow (burn rate proxy), recent_offerings_millions
    (capital raised in recent offerings), last_cash_date.

    Use this to assess: how much cash does the company have right now
    and how long can it sustain operations without a new raise?
    """
    try:
        return await service_get(
            config.dilution_tracker_url,
            f"/api/sec-dilution/{ticker.upper()}/cash-position",
        )
    except Exception as e:
        return {"error": str(e), "ticker": ticker.upper()}


@mcp.tool()
async def get_cash_runway(ticker: str) -> dict:
    """Get enhanced cash runway analysis for a ticker.

    Estimates how many months of cash the company has remaining based on:
    - Current cash position (from dt_cash_position or XBRL)
    - Operating burn rate (from cash_flow statements)
    - Available financing capacity (ATM, shelf, equity lines)
    - Recent capital raises

    Returns: runway_months, cash_position, burn_rate_monthly,
    available_financing, total_runway_with_financing,
    runway_category (CRITICAL < 3mo, LOW 3-6mo, MODERATE 6-12mo,
    ADEQUATE 12-18mo, STRONG > 18mo), data_quality, assumptions.

    This is the single most important metric for micro/small-cap dilution:
    low cash runway = near-certain upcoming offering = near-term dilution.
    """
    try:
        return await service_get(
            config.dilution_tracker_url,
            f"/api/sec-dilution/{ticker.upper()}/cash-runway-enhanced",
        )
    except Exception as e:
        return {"error": str(e), "ticker": ticker.upper()}


# ── Risk scoring ──────────────────────────────────────────────────────────────

@mcp.tool()
async def get_dilution_risk_ratings(ticker: str) -> dict:
    """Get multi-category dilution risk ratings and scores (DilutionTracker methodology).

    Returns risk scores on 5 independent dimensions (each 1-10 scale,
    higher = more risk):

    - overall_risk: composite score across all factors
    - offering_ability_risk: how easily can the company raise more capital?
      (available shelf/ATM capacity relative to market cap)
    - overhead_supply_risk: how much potential selling pressure from warrants,
      convertibles, equity lines currently in-the-money?
    - historical_dilution_risk: how aggressively has management diluted
      shareholders historically? (shares growth over 1y and 2y)
    - cash_need_risk: how urgently does the company need cash?
      (runway months, burn rate, cash per share)

    Risk categories: LOW (1-3), MEDIUM (4-6), HIGH (7-8), CRITICAL (9-10).

    Use this for quick filtering: companies with overall_risk >= 8 are
    at high risk of imminent dilutive offering.
    """
    try:
        return await service_get(
            config.dilution_tracker_url,
            f"/api/sec-dilution/{ticker.upper()}/risk-ratings",
        )
    except Exception as e:
        return {"error": str(e), "ticker": ticker.upper()}


# ── Historical data ───────────────────────────────────────────────────────────

@mcp.tool()
async def get_shares_history(ticker: str) -> dict:
    """Get shares outstanding history over time from SEC EDGAR XBRL.

    Shows how the share count has evolved: increases = dilution events,
    decreases = share buybacks or reverse splits.

    Returns time series of: date, shares_outstanding, form_type (10-K/10-Q),
    filed_date. Also includes calculated dilution percentages:
    dilution_1y (% change over 1 year), dilution_2y (% change over 2 years).

    Analysis: consistent share count growth > 20% annually is a red flag
    for aggressive dilution. Compare with completed_offerings to correlate
    offering events with share count increases.
    """
    try:
        return await service_get(
            config.dilution_tracker_url,
            f"/api/sec-dilution/{ticker.upper()}/shares-history",
        )
    except Exception as e:
        return {"error": str(e), "ticker": ticker.upper()}


@mcp.tool()
async def get_dilution_analysis(ticker: str) -> dict:
    """Calculate total potential dilution percentage for a ticker.

    Quantifies EXACTLY how much dilution could occur if all outstanding
    dilutive instruments were exercised/converted at current prices.

    Returns breakdown by instrument type:
    - warrants_dilution_pct: % new shares from warrant exercises
    - atm_dilution_pct: % new shares if full ATM capacity used
    - shelf_dilution_pct: % new shares from shelf registrations
    - convertible_notes_dilution_pct: % from note conversions
    - convertible_preferred_dilution_pct: % from preferred conversions
    - equity_lines_dilution_pct: % from equity line draws
    - total_potential_dilution_pct: sum of all above
    - assumptions: current_price, shares_outstanding used

    Example interpretation: total_potential_dilution_pct = 45% means
    existing shareholders could be diluted by 45% if all instruments
    are exercised — this is the 'dilution ceiling'.
    """
    try:
        return await service_get(
            config.dilution_tracker_url,
            f"/api/sec-dilution/{ticker.upper()}/dilution-analysis",
        )
    except Exception as e:
        return {"error": str(e), "ticker": ticker.upper()}


@mcp.tool()
async def get_sec_filings(ticker: str, page: int = 1, limit: int = 20, form_type: str | None = None) -> dict:
    """Get paginated SEC filings for a ticker from the dilution tracker database.

    Filings are classified into categories: financial (10-K, 10-Q),
    offering (S-1, S-3, 424B5), ownership (SC 13D/G), proxy (DEF 14A),
    disclosure (8-K).

    Each filing has: filing_type, filing_date, report_date, title, category,
    is_offering_related flag, is_dilutive flag, URL to SEC EDGAR.

    Use form_type to filter: e.g. form_type='S-3' for shelf registrations,
    form_type='424B5' for prospectus supplements (direct dilution events),
    form_type='10-Q' for quarterly reports.
    """
    try:
        url = f"/api/sec-dilution/{ticker.upper()}/filings?page={page}&limit={limit}"
        if form_type:
            url += f"&form_type={form_type}"
        return await service_get(config.dilution_tracker_url, url)
    except Exception as e:
        return {"error": str(e), "ticker": ticker.upper()}


@mcp.tool()
async def get_trending_dilution(limit: int = 50) -> dict:
    """Get trending tickers ranked by recent dilution activity.

    Returns tickers with the most recent SEC filing activity related
    to dilutive instruments. Useful for scanning which companies are
    actively filing shelf registrations, prospectus supplements,
    or new warrant agreements.

    Returns list of: ticker, company_name, last_scraped_at, filing_count,
    recent_offering_count, trending_score.
    """
    try:
        return await service_get(
            config.dilution_tracker_url,
            f"/api/analysis/trending?limit={limit}",
        )
    except Exception as e:
        return {"error": str(e)}
