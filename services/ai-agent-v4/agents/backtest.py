"""
Backtest Agent — Dual-mode LLM backtester.

Mode A (Template): Simple strategies → JSON StrategyConfig → rigid engine
Mode B (Code Gen): Complex strategies → Python code → sandbox execution

The LLM decides which mode based on strategy complexity.  Mode B can express
arbitrary logic: slope detection, measured moves, time-of-day filters,
volume analysis, multi-indicator custom conditions, etc.
"""
from __future__ import annotations

import json
import logging
import os
import time
from typing import Any

import httpx
from langchain_core.callbacks import adispatch_custom_event

from agents._llm_retry import llm_invoke_with_retry

logger = logging.getLogger(__name__)


async def _progress(message: str) -> None:
    """Emit a progress event visible to astream_events consumers."""
    try:
        await adispatch_custom_event("backtest_progress", {"message": message})
    except Exception:
        pass

BACKTESTER_URL = os.getenv("BACKTESTER_URL", "http://backtester:8060")
BACKTESTER_TIMEOUT = 300  # 5 min max for long backtests
MAX_TICKERS = 3

_llm = None

STRATEGY_PARSE_PROMPT = """\
<role>
You are a professional quantitative strategy parser for Tradeul. Convert natural language
strategy descriptions into a precise, executable StrategyConfig JSON object.
You have deep expertise in technical analysis, trading strategies, and financial markets.
</role>

<task>
Parse the user's natural language strategy description into a valid StrategyConfig JSON object.
Fill in reasonable defaults when details are not specified. Be generous with assumptions
to produce a working backtest rather than asking for clarification.
</task>

<schema>
StrategyConfig fields:
{{
  "name": "string — descriptive name for the strategy",
  "description": "string — brief description",
  "universe": {{
    "method": "all_us | sector | industry | ticker_list | sql_filter",
    "criteria": {{}},
    "tickers": ["TICKER1", ...] | null,
    "sql_where": "SQL WHERE clause" | null
  }},
  "entry_signals": [
    {{
      "indicator": "close | open | high | low | volume | rsi_14 | sma_20 | sma_50 | ema_9 | ema_21 | atr_14 | vwap | gap_pct | rvol | range_pct | high_20d | low_20d | prev_close | avg_volume_20d",
      "operator": "> | >= | < | <= | == | crosses_above | crosses_below",
      "value": number_or_indicator_name,
      "lookback": null
    }}
  ],
  "entry_timing": "open | close | next_open",
  "exit_rules": [
    {{
      "type": "time | target | stop_loss | trailing_stop | signal | eod",
      "value": number_or_null,
      "signal": null
    }}
  ],
  "timeframe": "1min | 5min | 15min | 30min | 1h | 4h | 1d",
  "start_date": "YYYY-MM-DD",
  "end_date": "YYYY-MM-DD",
  "initial_capital": 100000,
  "max_positions": 10,
  "position_size_pct": 0.10,
  "direction": "long | short | both",
  "slippage_model": "fixed_bps | volume_based | spread_based",
  "slippage_bps": 10.0,
  "commission_per_trade": 0.0,
  "risk_free_rate": 0.05
}}
</schema>

<defaults>
If not specified:
- timeframe: "1d"
- initial_capital: 100000
- max_positions: 10
- position_size_pct: 0.10
- direction: "long"
- entry_timing: "next_open"
- slippage_model: "fixed_bps"
- slippage_bps: 10.0
- commission_per_trade: 0.0
- If no date range specified:
  - For daily ("1d") timeframe: use last 2 years (start_date = 2 years ago, end_date = today)
  - For intraday (1min/5min/etc): use last 30 days MAXIMUM (start_date = 30 days ago, end_date = today)
- Historical daily data is available from Polygon going back to 2003+
- Minute data is only available from late 2024 onwards, and loading more than 30 days is very slow
- IMPORTANT: For intraday strategies, NEVER set a date range longer than 60 days
- For daily backtests use "1d" timeframe; for intraday scalps use "5min" (preferred) or "1min"
- If "stop loss" mentioned without %, assume 5%
- If "target" or "take profit" mentioned without %, assume 10%
- If "trailing stop" mentioned without %, assume 3%
- If "eod" or "end of day" mentioned, add eod exit rule
- Always add a time-based exit of 20 bars if no other time-based exit is specified
- For gap strategies: use gap_pct indicator
- For RSI strategies: use rsi_14
- For moving average crossovers: use crosses_above/crosses_below with sma indicators
- For volume-based: use rvol (relative volume)
</defaults>

<indicators>
Available indicators (use exact names):
- gap_pct: gap percentage from previous close
- rsi_14: 14-period RSI
- close, open, high, low, volume: OHLCV data
- sma_20, sma_50, sma_200: Simple Moving Averages
- atr_14: Average True Range
- rvol: Relative Volume (vs 20-day average)
- range_pct: (high - low) / low as percentage
- high_20d, low_20d: 20-period rolling high/low
- ema_9, ema_21: Exponential Moving Averages
- vwap: Volume-Weighted Average Price
- prev_close: Previous bar close
</indicators>

<examples>
User: "Buy stocks with gap > 5% and volume > 1M, sell after 3 days or at 10% profit/5% stop"
{{
  "name": "Gap Up Momentum",
  "description": "Buy stocks gapping up >5% with high volume, exit on time/target/stop",
  "universe": {{"method": "sql_filter", "sql_where": "avg_volume > 500000 AND avg_close > 1.0"}},
  "entry_signals": [
    {{"indicator": "gap_pct", "operator": ">", "value": 0.05}},
    {{"indicator": "volume", "operator": ">", "value": 1000000}}
  ],
  "entry_timing": "next_open",
  "exit_rules": [
    {{"type": "time", "value": 3}},
    {{"type": "target", "value": 0.10}},
    {{"type": "stop_loss", "value": 0.05}}
  ],
  "timeframe": "1d",
  "start_date": "2024-01-01",
  "end_date": "2025-12-31",
  "initial_capital": 100000,
  "max_positions": 10,
  "position_size_pct": 0.10,
  "direction": "long",
  "slippage_model": "fixed_bps",
  "slippage_bps": 10.0,
  "commission_per_trade": 0.0,
  "risk_free_rate": 0.05
}}

User: "RSI < 30 mean reversion on SPY from 2020 to 2024, sell when RSI > 70"
{{
  "name": "SPY RSI Mean Reversion",
  "description": "Buy SPY when oversold, sell when overbought",
  "universe": {{"method": "ticker_list", "tickers": ["SPY"]}},
  "entry_signals": [
    {{"indicator": "rsi_14", "operator": "<", "value": 30}}
  ],
  "entry_timing": "next_open",
  "exit_rules": [
    {{"type": "signal", "signal": {{"indicator": "rsi_14", "operator": ">", "value": 70}}}},
    {{"type": "time", "value": 20}},
    {{"type": "stop_loss", "value": 0.05}}
  ],
  "timeframe": "1d",
  "start_date": "2020-01-01",
  "end_date": "2024-12-31",
  "initial_capital": 100000,
  "max_positions": 1,
  "position_size_pct": 1.0,
  "direction": "long",
  "slippage_model": "fixed_bps",
  "slippage_bps": 5.0,
  "commission_per_trade": 0.0,
  "risk_free_rate": 0.05
}}
</examples>

<output_format>
Respond with ONLY a valid JSON object matching the StrategyConfig schema.
No explanation, no markdown, just the JSON.
</output_format>
"""


_llm_code = None


def _get_llm():
    global _llm
    if _llm is None:
        from langchain_google_genai import ChatGoogleGenerativeAI
        _llm = ChatGoogleGenerativeAI(
            model="gemini-2.0-flash",
            temperature=0.1,
            max_output_tokens=8192,
            response_mime_type="application/json",
        )
    return _llm


def _get_llm_code():
    """LLM for code generation — no JSON mime type, higher token limit."""
    global _llm_code
    if _llm_code is None:
        from langchain_google_genai import ChatGoogleGenerativeAI
        _llm_code = ChatGoogleGenerativeAI(
            model="gemini-2.0-flash",
            temperature=0.15,
            max_output_tokens=16384,
        )
    return _llm_code


# ── Code Generation Prompt ───────────────────────────────────────────────

CODE_GEN_PROMPT = """\
You are an expert quantitative developer writing Python backtesting strategies.

## Your Task
Generate a complete Python function `strategy(bars)` that implements the
trading strategy described by the user.

## Data Available
`bars` is a pandas DataFrame with these columns:
- ticker (str), open, high, low, close, volume (float)
- timestamp (datetime, TIMEZONE=UTC) for intraday OR date (date) for daily
- Pre-computed indicators: sma_20, sma_50, sma_200, ema_9, ema_21, rsi_14,
  atr_14, vwap (may be NaN), prev_close, avg_volume_20d, rvol, gap_pct,
  range_pct, high_20d, low_20d, bar_idx

CRITICAL TIME ZONE INFO: All intraday timestamps are UTC.
- US market open  9:30 AM EST = 14:30 UTC
- US market close 4:00 PM EST = 21:00 UTC
- 10:00 AM EST = 15:00 UTC
- 10:45 AM EST = 15:45 UTC
- 1:30 PM EST  = 18:30 UTC
- 3:30 PM EST  = 20:30 UTC
Convert all EST references to UTC in your code. Use `.hour` and `.minute` on
timestamp objects, NOT string parsing.

## Libraries Available
pandas (as pd), numpy (as np), math, datetime module (datetime, date, timedelta)
These are pre-imported in the execution scope.

## Return Format
Return a list of dicts, each a COMPLETE trade (entry + exit):
{
    "ticker": str,
    "direction": "long" or "short",
    "entry_time": timestamp/date from bars,
    "entry_price": float,
    "exit_time": timestamp/date from bars,
    "exit_price": float,
    "position_pct": float  # fraction of capital (0.0-1.0), default 0.10
}

## Rules — CRITICAL
1. NO LOOK-AHEAD BIAS: Signal on bar[i] → entry at bar[i+1] open.
   NEVER use bar[i] close/high/low for entry — you don't know those until bar ends.
2. You can compute ANY custom indicator (slopes, measured moves, etc.)
3. Handle edge cases: empty data, NaN values, division by zero
4. Process each ticker independently with `for ticker in bars["ticker"].unique():`
   then `df = bars[bars["ticker"] == ticker].reset_index(drop=True)`
5. For intraday: use bars["timestamp"]. For daily: use bars["date"]
6. Every entry MUST have an exit. No open positions at end.
7. ONE position at a time per ticker. Close before opening new.
8. Use `.iloc[i]` for element access (integer index).
9. When comparing Series element-wise, use `.iloc[i]` to get scalars, not raw Series.
10. For slope: `slope = (df["ema_9"].iloc[i] - df["ema_9"].iloc[i-3]) / 3`
11. For day-level (daily low/high): group by `df["timestamp"].dt.date`
12. LIMIT: max ~5-10 trades per day per ticker to be realistic.
13. When checking NaN: use `pd.notna(val)` before comparisons.

## PERFORMANCE — CRITICAL FOR LARGE DATASETS
The data can have 500,000+ bars. Your code MUST be efficient:
- Pre-compute daily groups ONCE: `df["day"] = df["timestamp"].dt.date; days = df.groupby("day")`
- Use vectorized operations (pandas/numpy) wherever possible
- NEVER nest loops over all bars (O(n²) will timeout)
- For each day, extract that day's bars with groupby, not filtering full df
- For rolling averages, use `.rolling()` or `.shift()`, not manual loops
- Keep the main loop over DAYS (max ~60), not over BARS (hundreds of thousands)
- Pattern: `for day, day_bars in days:` then process each day's ~78 bars

## Output
Respond with ONLY the Python code. No markdown fences, no explanation.
Start directly with imports or `def strategy(bars):`.
"""


CRITIQUE_PROMPT = """\
You are a senior quant code reviewer. Review this Python strategy code for:
1. Look-ahead bias (using future data for decisions)
2. Missing edge cases (empty DataFrames, NaN handling)
3. Trades without exits (every entry must have a matching exit)
4. Off-by-one errors in bar indexing
5. Syntax errors or undefined variables

If the code has critical issues, return ONLY the corrected code.
If the code is correct, return it unchanged.
Respond with ONLY the Python code. No markdown, no explanation.
"""


def _strip_backtest_prefix(query: str) -> str:
    q = query.strip()
    if q.lower().startswith("/backtest"):
        q = q[len("/backtest"):].strip()
    return q


_STRATEGY_KEYWORDS = [
    "rsi", "sma", "ema", "macd", "vwap", "atr", "bollinger",
    "gap", "breakout", "crossover", "cross above", "cross below",
    "buy when", "sell when", "comprar cuando", "vender cuando",
    "entry", "exit", "stop loss", "take profit", "trailing",
    "mean reversion", "momentum", "scalp",
    "overbought", "oversold", "sobrecompra", "sobreventa",
    ">", "<", ">=", "<=",
    "above", "below", "por encima", "por debajo",
    "profit target", "stop", "target",
]


def _has_strategy_content(text: str) -> bool:
    """Check if text contains actual trading strategy keywords."""
    t = text.lower()
    return sum(1 for kw in _STRATEGY_KEYWORDS if kw in t) >= 1


def _clean_json(raw: str) -> str:
    """Strip markdown fences and common LLM artifacts from JSON.

    Handles: fenced code blocks, leading text, doubled braces (Gemini bug),
    single-quoted dicts, Python-style True/False/None, trailing commas.
    """
    s = raw.strip()
    if s.startswith("```"):
        s = s.split("\n", 1)[-1]
    if s.endswith("```"):
        s = s.rsplit("```", 1)[0]
    s = s.strip()

    # Gemini sometimes returns doubled braces {{ }} — collapse them
    if "{{" in s:
        s = s.replace("{{", "{").replace("}}", "}")

    first = s.find("{")
    last = s.rfind("}")
    if first != -1 and last != -1 and last > first:
        s = s[first:last + 1]

    if _is_valid_json(s):
        return s

    import re as _re
    fixed = s.replace("True", "true").replace("False", "false").replace("None", "null")
    fixed = _re.sub(r",\s*([\]}])", r"\1", fixed)
    if _is_valid_json(fixed):
        return fixed

    try:
        import ast
        obj = ast.literal_eval(s)
        return json.dumps(obj)
    except Exception:
        pass

    return s


def _is_valid_json(s: str) -> bool:
    try:
        json.loads(s)
        return True
    except (json.JSONDecodeError, ValueError):
        return False


async def _parse_strategy(query: str, tickers: list[str] | None = None, max_retries: int = 1) -> dict:
    """Use LLM to parse natural language into StrategyConfig JSON with retry."""
    llm = _get_llm()

    preamble = ""
    if tickers:
        tickers_str = ", ".join(tickers)
        preamble += (
            f"MANDATORY: The user wants to backtest on these specific tickers: {tickers_str}. "
            f"You MUST use universe method \"ticker_list\" with tickers: {json.dumps(tickers)}. "
            f"Do NOT use \"all_us\" or \"sql_filter\" — use \"ticker_list\" with exactly these tickers.\n\n"
        )
    if len(query) > 500:
        preamble += (
            "IMPORTANT: The text below contains educational explanations mixed with trading rules. "
            "Extract ONLY the concrete, actionable entry/exit rules and translate them to the "
            "available indicators. Ignore all explanatory text, theory, and commentary.\n\n"
            "KEY RULES TO EXTRACT:\n"
            "1. Entry signal (what indicator cross/condition triggers a buy)\n"
            "2. Exit rules (target, stop loss, time-based)\n"
            "3. Direction (long/short/both)\n"
            "4. Any specific tickers or timeframe mentioned\n\n"
            "If the strategy mentions indicators we don't have, map to the CLOSEST available ones.\n\n"
        )

    messages = [
        {"role": "system", "content": STRATEGY_PARSE_PROMPT},
        {"role": "user", "content": preamble + query},
    ]

    last_error = None
    for attempt in range(max_retries + 1):
        try:
            response = await llm_invoke_with_retry(llm, messages)
            raw_content = response.content

            # Gemini sometimes returns parsed dicts instead of JSON strings
            if isinstance(raw_content, dict):
                logger.info("Backtest agent: LLM returned dict directly, using as-is")
                return raw_content
            if isinstance(raw_content, list) and len(raw_content) == 1 and isinstance(raw_content[0], dict):
                logger.info("Backtest agent: LLM returned list with single dict")
                return raw_content[0]

            raw_str = str(raw_content) if not isinstance(raw_content, str) else raw_content
            logger.debug("Backtest agent: raw LLM output (%d chars): %.300s", len(raw_str), raw_str)

            cleaned = _clean_json(raw_str)
            return json.loads(cleaned)
        except json.JSONDecodeError as exc:
            last_error = exc
            logger.warning(
                "Backtest agent: JSON parse attempt %d failed — %s | raw type=%s first100=%r",
                attempt + 1, exc, type(raw_content).__name__,
                str(raw_content)[:100] if raw_content else "EMPTY",
            )
            if attempt < max_retries:
                messages.append({"role": "assistant", "content": str(raw_content)})
                messages.append({
                    "role": "user",
                    "content": "Your previous response was not valid JSON. Respond with ONLY a raw JSON object — no markdown, no explanation, no wrapping.",
                })

    raise last_error


async def _call_backtester(strategy_config: dict) -> dict:
    """Call the backtester REST API with the parsed strategy config."""
    tf = strategy_config.get("timeframe", "1d")
    is_intraday = tf in ("1min", "5min", "15min", "30min", "1h")

    request_body = {
        "strategy": strategy_config,
        "include_walk_forward": not is_intraday,
        "walk_forward_splits": 5,
        "include_monte_carlo": not is_intraday,
        "monte_carlo_simulations": 500 if not is_intraday else 0,
        "include_advanced_metrics": True,
        "n_trials_for_dsr": 1,
    }

    async with httpx.AsyncClient(timeout=BACKTESTER_TIMEOUT) as client:
        resp = await client.post(
            f"{BACKTESTER_URL}/api/v1/backtest",
            json=request_body,
        )
        if resp.status_code == 422:
            detail = resp.json().get("detail", resp.text[:300])
            logger.warning("backtester_validation_error", detail=detail)
            raise ValueError(f"Backtester validation error: {detail}")
        resp.raise_for_status()
        return resp.json()


async def submit_backtest_natural(
    prompt: str,
    tickers: list[str],
    user_id: str | None = None,
) -> dict:
    """
    Parse natural language strategy, enqueue job on backtester, return job_id.
    For use by REST endpoint POST /api/backtest/submit-natural.
    """
    strategy_prompt = _strip_backtest_prefix(prompt)
    if not _has_strategy_content(strategy_prompt):
        raise ValueError("Prompt does not describe a trading strategy. Include entry/exit rules and indicators.")
    if not tickers or len(tickers) > MAX_TICKERS:
        raise ValueError(f"Provide 1–{MAX_TICKERS} tickers.")
    mode = await _classify_strategy_mode(strategy_prompt)
    if mode == "template":
        strategy_config = await _parse_strategy(strategy_prompt, tickers=tickers)
        tf = strategy_config.get("timeframe", "1d")
        is_intraday = tf in ("1min", "5min", "15min", "30min", "1h")
        request_body = {
            "strategy": strategy_config,
            "include_walk_forward": not is_intraday,
            "walk_forward_splits": 5,
            "include_monte_carlo": not is_intraday,
            "monte_carlo_simulations": 500 if not is_intraday else 0,
            "include_advanced_metrics": True,
            "n_trials_for_dsr": 1,
        }
        payload = {"type": "template", "request": request_body}
    else:
        code, metadata = await _generate_strategy_code(strategy_prompt)
        metadata["tickers"] = tickers
        request_body = {
            "code": code,
            "tickers": metadata.get("tickers", tickers),
            "timeframe": metadata.get("timeframe", "5min"),
            "start_date": metadata.get("start_date"),
            "end_date": metadata.get("end_date"),
            "initial_capital": metadata.get("initial_capital", 100_000),
            "slippage_bps": 10.0,
            "commission_per_trade": 0.0,
            "risk_free_rate": 0.05,
            "strategy_name": metadata.get("name", "LLM Strategy"),
            "strategy_description": metadata.get("description", ""),
            "include_advanced_metrics": True,
            "include_monte_carlo": True,
            "monte_carlo_simulations": 500,
        }
        payload = {"type": "code", "request": request_body}
    if user_id:
        payload["user_id"] = user_id
    async with httpx.AsyncClient(timeout=60) as client:
        resp = await client.post(
            f"{BACKTESTER_URL}/api/v1/jobs",
            json=payload,
        )
        if resp.status_code == 429:
            raise ValueError(resp.json().get("detail", resp.text)[:200])
        resp.raise_for_status()
        data = resp.json()
    return {"job_id": data.get("job_id", "")}


# ── Code Generation Path ─────────────────────────────────────────────────

_MODE_CLASSIFIER_PROMPT = """\
You are a strategy complexity classifier for a backtesting engine.

The TEMPLATE engine has these EXACT capabilities — nothing more:
- Entry signals: AND-combined comparisons on these indicators ONLY:
  close, open, high, low, volume, rsi_14, sma_20, sma_50, sma_200,
  ema_9, ema_21, atr_14, vwap, gap_pct, rvol, range_pct, high_20d,
  low_20d, prev_close, avg_volume_20d
- Operators: >, >=, <, <=, ==, crosses_above, crosses_below
- Entry timing: open, close, or next_open (fixed for all trades)
- Exit rules: fixed % stop_loss, fixed % target, fixed % trailing_stop,
  time (N bars), eod (end of day), signal (indicator condition)
- Direction: fixed long OR fixed short for ALL trades (no per-trade switching)
- No time-of-day filtering, no "wait N minutes", no session-based logic
- No dynamic/ATR-based stops (only fixed percentages)
- No multi-step logic ("if X then Y then Z")
- No computed/custom indicators beyond the list above

Classify as "template" ONLY if the strategy can be FULLY expressed with the
capabilities above. If ANY part requires logic beyond template, classify as "code".

When in doubt, choose "code" — it is strictly more capable.

Respond with ONLY one word: "template" or "code"
"""

_mode_classifier_llm = None


def _get_mode_classifier_llm():
    global _mode_classifier_llm
    if _mode_classifier_llm is None:
        from langchain_google_genai import ChatGoogleGenerativeAI
        _mode_classifier_llm = ChatGoogleGenerativeAI(
            model="gemini-2.0-flash-lite",
            temperature=0.0,
            max_output_tokens=8,
        )
    return _mode_classifier_llm


async def _classify_strategy_mode(query: str) -> str:
    """Use a fast LLM call to classify strategy as 'template' or 'code'."""
    llm = _get_mode_classifier_llm()
    messages = [
        {"role": "system", "content": _MODE_CLASSIFIER_PROMPT},
        {"role": "user", "content": query[:1500]},
    ]
    try:
        response = await llm_invoke_with_retry(llm, messages)
        answer = response.content.strip().lower().rstrip(".")
        if answer in ("template", "code"):
            return answer
        logger.warning("Mode classifier returned unexpected: %r, defaulting to code", answer)
        return "code"
    except Exception as e:
        logger.warning("Mode classifier failed (%s), defaulting to code", e)
        return "code"


async def _generate_strategy_code(query: str) -> tuple[str, dict]:
    """Use LLM to generate Python strategy code + extract metadata in parallel."""
    import asyncio

    llm = _get_llm_code()
    meta_llm = _get_llm()

    code_messages = [
        {"role": "system", "content": CODE_GEN_PROMPT},
        {"role": "user", "content": query},
    ]

    meta_messages = [
        {"role": "system", "content": (
            "Extract from this trading strategy description: "
            "name (short), tickers (list, default [\"SPY\"]), "
            "timeframe (1min/5min/1d, default 5min for scalps, 1d for swing), "
            "start_date and end_date (YYYY-MM-DD, default last 30 days for intraday, last 2 years for daily). "
            "Return JSON: {\"name\":str, \"tickers\":[str], \"timeframe\":str, \"start_date\":str, \"end_date\":str}"
        )},
        {"role": "user", "content": query[:500]},
    ]

    # Run code gen + metadata extraction in parallel
    code_task = asyncio.create_task(llm_invoke_with_retry(llm, code_messages))
    meta_task = asyncio.create_task(llm_invoke_with_retry(meta_llm, meta_messages))

    code_response, meta_response = await asyncio.gather(code_task, meta_task)

    code = _clean_code(code_response.content)
    logger.info("Backtest agent: generated %d chars of strategy code", len(code))

    try:
        meta_raw = _clean_json(str(meta_response.content))
        metadata = json.loads(meta_raw)
    except Exception:
        metadata = {}

    # Ensure required fields with sensible defaults
    from datetime import date as _date, timedelta as _td
    today = _date.today()
    tf = metadata.get("timeframe", "5min")
    is_intraday = tf in ("1min", "5min", "15min", "30min", "1h")

    if not metadata.get("name"):
        metadata["name"] = "LLM Strategy"
    if not metadata.get("tickers"):
        metadata["tickers"] = ["SPY"]
    if not metadata.get("timeframe"):
        metadata["timeframe"] = "5min"
    if not metadata.get("start_date"):
        metadata["start_date"] = str(today - _td(days=30 if is_intraday else 730))
    if not metadata.get("end_date"):
        metadata["end_date"] = str(today)

    return code, metadata


def _clean_code(raw: str) -> str:
    """Strip markdown fences from generated code."""
    s = raw.strip()
    if s.startswith("```python"):
        s = s[len("```python"):].strip()
    elif s.startswith("```"):
        s = s[3:].strip()
    if s.endswith("```"):
        s = s[:-3].strip()
    return s


async def _call_code_backtester(code: str, metadata: dict) -> dict:
    """Call the backtester code execution endpoint with progress heartbeats."""
    import asyncio

    request_body = {
        "code": code,
        "tickers": metadata.get("tickers", ["SPY"]),
        "timeframe": metadata.get("timeframe", "5min"),
        "start_date": metadata.get("start_date", "2025-01-20"),
        "end_date": metadata.get("end_date", "2025-02-20"),
        "initial_capital": 100_000,
        "slippage_bps": 10.0,
        "commission_per_trade": 0.0,
        "risk_free_rate": 0.05,
        "strategy_name": metadata.get("name", "LLM Strategy"),
        "strategy_description": metadata.get("description", ""),
        "include_advanced_metrics": True,
        "include_monte_carlo": True,
        "monte_carlo_simulations": 500,
    }

    _HEARTBEAT_MESSAGES = [
        "Loading market data from Polygon FLATS...",
        "Computing technical indicators (SMA, EMA, RSI, ATR, VWAP)...",
        "Executing strategy code in sandbox...",
        "Strategy running — processing bars...",
        "Still executing — complex strategy, please wait...",
        "Still running — large dataset, almost there...",
    ]

    async def _heartbeat_loop(done_event: asyncio.Event):
        """Send periodic progress while the backtester works."""
        for i, msg in enumerate(_HEARTBEAT_MESSAGES):
            delay = 8 if i < 3 else 15
            try:
                await asyncio.wait_for(done_event.wait(), timeout=delay)
                return
            except asyncio.TimeoutError:
                await _progress(msg)
        elapsed = len(_HEARTBEAT_MESSAGES) * 12
        while True:
            try:
                await asyncio.wait_for(done_event.wait(), timeout=20)
                return
            except asyncio.TimeoutError:
                elapsed += 20
                await _progress(f"Backtester still working... ({elapsed}s elapsed)")

    done = asyncio.Event()
    heartbeat_task = asyncio.create_task(_heartbeat_loop(done))

    try:
        async with httpx.AsyncClient(timeout=BACKTESTER_TIMEOUT) as client:
            resp = await client.post(
                f"{BACKTESTER_URL}/api/v1/backtest/code",
                json=request_body,
            )
        done.set()
        await heartbeat_task

        if resp.status_code == 422:
            detail = resp.json().get("detail", resp.text[:300])
            raise ValueError(f"Backtester validation error: {detail}")
        resp.raise_for_status()

        result = resp.json()
        status = result.get("status", "?")
        if status == "success":
            n = result.get("result", {}).get("core_metrics", {}).get("total_trades", 0)
            await _progress(f"Backtester returned: {n} trades — computing advanced metrics...")
        return result
    except Exception:
        done.set()
        heartbeat_task.cancel()
        raise


# ── Main Node (dual-mode) ────────────────────────────────────────────────

async def backtest_node(state: dict) -> dict:
    """Parse NL strategy and execute backtest — auto-selects template vs code mode."""
    start_time = time.time()
    query = state.get("query", "")
    language = state.get("language", "en")
    strategy_prompt = _strip_backtest_prefix(query)

    result: dict[str, Any] = {}
    mode = "unknown"

    # ── Guard: no strategy content → return informational response ──
    if not _has_strategy_content(strategy_prompt):
        logger.info("Backtest agent: no strategy content detected, returning info")
        elapsed_ms = int((time.time() - start_time) * 1000)
        if language == "es":
            info_msg = (
                "Para ejecutar un backtest necesito:\n\n"
                "1. **Tickers** (obligatorio, máximo 3): ej. SPY, AAPL, MSFT\n"
                "2. **Estrategia de entrada**: ej. \"comprar cuando RSI < 30\", \"gap up > 5%\"\n"
                "3. **Reglas de salida**: ej. \"vender cuando RSI > 70\", \"stop loss 5%\", \"take profit 10%\"\n"
                "4. **Rango de fechas** (opcional): ej. \"de 2023-01-01 a 2024-12-31\"\n"
                "5. **Timeframe** (opcional): 1d (diario), 5min, 1min\n\n"
                "**Ejemplo:**\n"
                "\"Backtest RSI < 30 mean reversion en SPY, vender cuando RSI > 70, "
                "stop loss 5%, de 2023 a 2024\"\n\n"
                "**Límites:** Máximo 3 tickers por backtest. "
                "Para intradía (1min/5min), máximo 60 días de datos."
            )
        else:
            info_msg = (
                "To run a backtest I need:\n\n"
                "1. **Tickers** (required, max 3): e.g. SPY, AAPL, MSFT\n"
                "2. **Entry strategy**: e.g. \"buy when RSI < 30\", \"gap up > 5%\"\n"
                "3. **Exit rules**: e.g. \"sell when RSI > 70\", \"stop loss 5%\", \"take profit 10%\"\n"
                "4. **Date range** (optional): e.g. \"from 2023-01-01 to 2024-12-31\"\n"
                "5. **Timeframe** (optional): 1d (daily), 5min, 1min\n\n"
                "**Example:**\n"
                "\"Backtest RSI < 30 mean reversion on SPY, sell when RSI > 70, "
                "stop loss 5%, from 2023 to 2024\"\n\n"
                "**Limits:** Max 3 tickers per backtest. "
                "For intraday (1min/5min), max 60 days of data."
            )
        return {
            "agent_results": {
                "backtest": {"status": "info", "message": info_msg},
            },
            "execution_metadata": {
                **(state.get("execution_metadata", {})),
                "backtest": {"elapsed_ms": elapsed_ms, "status": "info", "mode": "info"},
            },
        }

    # ── Guard: check tickers from planner — require explicit tickers (max 3) ──
    planner_tickers = state.get("tickers", [])
    if not planner_tickers:
        logger.info("Backtest agent: no tickers provided, requesting clarification")
        elapsed_ms = int((time.time() - start_time) * 1000)
        if language == "es":
            missing_msg = (
                "Tu estrategia se ve bien, pero necesito saber **en qué ticker(s)** quieres ejecutarla "
                f"(máximo {MAX_TICKERS}).\n\n"
                "Por ejemplo: \"en SPY\", \"en AAPL y MSFT\", \"en QQQ, SPY, IWM\""
            )
        else:
            missing_msg = (
                "Your strategy looks good, but I need to know **which ticker(s)** to run it on "
                f"(max {MAX_TICKERS}).\n\n"
                "For example: \"on SPY\", \"on AAPL and MSFT\", \"on QQQ, SPY, IWM\""
            )
        return {
            "agent_results": {
                "backtest": {"status": "needs_tickers", "message": missing_msg},
            },
            "execution_metadata": {
                **(state.get("execution_metadata", {})),
                "backtest": {"elapsed_ms": elapsed_ms, "status": "needs_tickers", "mode": "validation"},
            },
        }

    if len(planner_tickers) > MAX_TICKERS:
        logger.info("Backtest agent: too many tickers (%d), max %d", len(planner_tickers), MAX_TICKERS)
        elapsed_ms = int((time.time() - start_time) * 1000)
        if language == "es":
            limit_msg = (
                f"Has indicado {len(planner_tickers)} tickers, pero el máximo permitido es **{MAX_TICKERS}**.\n\n"
                f"Tickers recibidos: {', '.join(planner_tickers)}\n\n"
                f"Por favor, elige máximo {MAX_TICKERS} tickers para el backtest."
            )
        else:
            limit_msg = (
                f"You specified {len(planner_tickers)} tickers, but the maximum allowed is **{MAX_TICKERS}**.\n\n"
                f"Tickers received: {', '.join(planner_tickers)}\n\n"
                f"Please choose up to {MAX_TICKERS} tickers for the backtest."
            )
        return {
            "agent_results": {
                "backtest": {"status": "too_many_tickers", "message": limit_msg},
            },
            "execution_metadata": {
                **(state.get("execution_metadata", {})),
                "backtest": {"elapsed_ms": elapsed_ms, "status": "too_many_tickers", "mode": "validation"},
            },
        }

    try:
        await _progress("Analyzing strategy complexity...")
        mode = await _classify_strategy_mode(strategy_prompt)
        use_code = mode == "code"
        logger.info("Backtest agent: mode=%s, prompt=%d chars, tickers=%s", mode, len(strategy_prompt), planner_tickers)

        if use_code:
            await _progress("Complex strategy detected — generating Python code with Gemini 2.5 Pro...")
            code, metadata = await _generate_strategy_code(strategy_prompt)

            metadata["tickers"] = planner_tickers
            tickers = planner_tickers
            tf = metadata.get("timeframe", "5min")
            n_tickers = len(tickers)
            ticker_preview = ", ".join(tickers[:5])
            if n_tickers > 5:
                ticker_preview += f" +{n_tickers - 5} more"
            await _progress(
                f"Code generated ({len(code):,} chars). "
                f"Sending to backtester: {ticker_preview} | {tf} | "
                f"{metadata.get('start_date', '?')} to {metadata.get('end_date', '?')}"
            )
            bt_response = await _call_code_backtester(code, metadata)

            if bt_response.get("status") == "error":
                first_error = bt_response.get("error", "")
                await _progress(f"First attempt failed — self-healing: {first_error[:120]}...")
                logger.warning("Backtest agent: first code attempt failed, retrying with fix: %s", first_error[:200])
                fix_llm = _get_llm_code()
                fix_messages = [
                    {"role": "system", "content": CRITIQUE_PROMPT},
                    {"role": "user", "content": f"This code failed with error: {first_error[:300]}\n\nOriginal code:\n{code}"},
                ]
                await _progress("Generating fixed code with critique agent...")
                fix_response = await llm_invoke_with_retry(fix_llm, fix_messages)
                fixed_code = _clean_code(fix_response.content)
                if len(fixed_code) > 50 and "def strategy" in fixed_code:
                    await _progress(f"Retrying with fixed code ({len(fixed_code):,} chars)...")
                    bt_response = await _call_code_backtester(fixed_code, metadata)
        else:
            await _progress("Simple strategy — parsing to StrategyConfig template...")
            strategy_config = await _parse_strategy(strategy_prompt, tickers=planner_tickers)
            name = strategy_config.get("name", "?")
            await _progress(f"Template parsed: \"{name}\" — executing backtest...")
            bt_response = await _call_backtester(strategy_config)

        if bt_response.get("status") == "error":
            error_msg = bt_response.get("error", "Backtest failed")

            if mode == "template" and "zero trades" in error_msg.lower():
                await _progress("Template produced zero trades — falling back to code generation...")
                mode = "code_fallback"
                code, metadata = await _generate_strategy_code(strategy_prompt)
                metadata["tickers"] = planner_tickers
                await _progress(f"Fallback code generated ({len(code):,} chars), executing...")
                bt_response = await _call_code_backtester(code, metadata)
                if bt_response.get("status") == "error":
                    raise RuntimeError(bt_response.get("error", "Backtest failed"))
            else:
                raise RuntimeError(error_msg)

        bt_result = bt_response.get("result", {})
        n_trades = bt_result.get("core_metrics", {}).get("total_trades", 0)
        ret_pct = bt_result.get("core_metrics", {}).get("total_return_pct", 0) * 100
        elapsed_s = int(time.time() - start_time)
        await _progress(
            f"Backtest complete: {n_trades} trades, {ret_pct:+.2f}% return ({elapsed_s}s)"
        )

        result = {
            "status": "success",
            "backtest_result": bt_result,
            "mode": mode,
        }
        logger.info(
            "Backtest agent [%s]: completed — %d trades, %.2f%% return",
            mode, n_trades, ret_pct,
        )

    except json.JSONDecodeError as exc:
        logger.error("Backtest agent: JSON parse error — %s", exc)
        result = {
            "status": "error",
            "error": f"No se pudo interpretar la estrategia: {exc}",
        }
    except httpx.HTTPStatusError as exc:
        logger.error("Backtest agent: API error %s", exc.response.status_code)
        result = {
            "status": "error",
            "error": f"Error del servicio de backtesting ({exc.response.status_code})",
        }
    except httpx.ConnectError:
        logger.error("Backtest agent: cannot connect to backtester")
        result = {
            "status": "error",
            "error": "Servicio de backtesting no disponible",
        }
    except Exception as exc:
        logger.error("Backtest agent [%s]: error — %s", mode, exc)
        result = {
            "status": "error",
            "error": str(exc),
        }

    elapsed_ms = int((time.time() - start_time) * 1000)

    return {
        "agent_results": {
            "backtest": result,
        },
        "execution_metadata": {
            **(state.get("execution_metadata", {})),
            "backtest": {
                "elapsed_ms": elapsed_ms,
                "status": result.get("status", "unknown"),
                "mode": mode,
            },
        },
    }
