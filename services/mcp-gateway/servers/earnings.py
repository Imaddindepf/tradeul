"""
MCP Server: Earnings

Single upstream: the api_gateway earnings API (/api/v1/earnings/*), the only
live source of the earnings calendar, estimates, actuals and price reaction.
Nothing here reads a database and nothing here writes one.

Two views of that upstream are used, and they are the same provider, so a row
built from both is always internally consistent:

    /api/v1/earnings/calendar?date=      day list: who reports, actuals,
                                         market cap, post-earnings move
    /api/v1/earnings/ticker/{symbol}     per-quarter history: the only view
                                         that carries analyst estimates

Rule that keeps rows honest: surprise percentages are never carried over from
an upstream field into a row whose actual came from elsewhere. They are
derived, here, from the (actual, estimate) pair that ends up in the row. A row
either has both numbers and a surprise computed from them, or no surprise.
"""
import asyncio

from datetime import datetime
from zoneinfo import ZoneInfo

from fastmcp import FastMCP
from clients.day_aggs import day_bars, open_to_close_pct
from clients.http_client import service_get
from config import config
from typing import Optional

_ET = ZoneInfo("America/New_York")
_EARNINGS_API = "/api/v1/earnings"

# Per-ticker completion is the only way to get estimates, so it runs for every
# row that is actually returned. The cap is a safety valve for a pathological
# limit, not a budget: when it bites, the response says so instead of quietly
# serving rows without estimates.
# Qué mide cada porcentaje. Va UNA vez por respuesta, no por fila: cuesta
# unos cientos de caracteres y quita la única razón por la que estos números
# se confunden entre sí. Sin esto, "post_move_pct: -12.1" no dice contra qué
# se mide, y un -12% de hueco a la baja se presenta como caída desde la
# apertura aunque la sesión cerrara al alza (GLW, 2026-07-28: -12,10% contra
# el cierre previo, +3,52% desde la apertura).
_METRIC_DEFINITIONS = {
    "eps_surprise_pct": "(eps_actual - eps_estimate) / |eps_estimate|",
    "revenue_surprise_pct": "(revenue_actual - revenue_estimate) / |revenue_estimate|",
    "open_to_close_pct": (
        "open -> close of the report date. If the report date is today and the "
        "session is still open, it is open -> last price."
    ),
    "post_move_pct": (
        "previous close -> close: the provider's 1-day reaction. Includes the "
        "overnight gap, so it is NOT the move from the open."
    ),
    "live_reaction_pct": (
        "Today, or AMC reports of the LAST closed session: change from the "
        "report-day regular close to the last price. Includes the gap. For "
        "yesterday's AMC reporters this is their post-earnings reaction so "
        "far, still unfolding."
    ),
    "eps_basis": (
        "UNKNOWN. The source does not state whether eps_actual/eps_estimate "
        "are GAAP or adjusted, and the two can differ materially for the same "
        "quarter. Report the beat or miss as given; do not label it GAAP or "
        "non-GAAP, and do not reconcile it against a figure quoted in prose."
    ),
}

_DETAIL_HARD_CAP = 200
_DETAIL_CONCURRENCY = 5

mcp = FastMCP(
    "Tradeul Earnings",
    instructions="Earnings calendar service with scheduled and reported earnings data. "
    "Includes EPS/revenue estimates vs actuals, surprise percentages, and guidance.",
)


def _num(v) -> Optional[float]:
    """Decimal/str → float (JSON-safe); None stays None."""
    if v is None:
        return None
    try:
        return float(v)
    except (TypeError, ValueError):
        return None


def _move_pct(v) -> Optional[float]:
    """Upstream price moves are FRACTIONS (0.0326 = +3.26%); served here as
    percentages, consistent with *_surprise_pct."""
    f = _num(v)
    return None if f is None else round(f * 100.0, 2)


def _surprise_pct(actual: Optional[float], estimate: Optional[float]) -> Optional[float]:
    """(actual - estimate) / |estimate| in %, None if not computable."""
    if actual is None or not estimate:
        return None
    return round((actual - estimate) / abs(estimate) * 100.0, 2)


def _today() -> str:
    return datetime.now(_ET).strftime("%Y-%m-%d")


async def _calendar(date: str, time_slot: Optional[str] = None,
                    min_importance: Optional[int] = None) -> dict:
    params: dict = {"date": date}
    if time_slot:
        params["time_slot"] = time_slot
    if min_importance is not None:
        params["min_importance"] = min_importance
    return await service_get(config.api_gateway_url, f"{_EARNINGS_API}/calendar",
                             params=params)


# La vista de día no trae consenso: sin estimado no hay sorpresa ni beat/miss.
# Se declara en la firma de las tools Y en su respuesta, porque el selector
# eligió esta vista "para porcentajes de sorpresa" y, al no encontrarlos, la
# sorpresa se dedujo de la prosa — invirtiendo el signo de dos compañías.
_NO_ESTIMATES_NOTE = (
    "This day view carries actuals only: eps_estimate, revenue_estimate and "
    "every surprise percentage are absent because the upstream day feed has "
    "no consensus. Do NOT infer a beat or a miss from the summary text. For "
    "surprises use earnings_get_earnings_results, which completes each row "
    "from the per-ticker view."
)


def _has_actuals(row: dict) -> bool:
    return row.get("eps_actual") is not None or row.get("revenue_actual") is not None


@mcp.tool()
async def get_today_earnings(
    status: Optional[str] = None,
    time_slot: Optional[str] = None,
) -> dict:
    """Get today's earnings calendar.

    Args:
        status: 'scheduled' (pending) or 'reported' (with results)
        time_slot: 'BMO' (before market open) or 'AMC' (after market close)

    Returns per company: symbol, company_name, time_slot, report_time,
    eps_actual, revenue_actual, market_cap, status.

    NO ESTIMATES AND NO SURPRISES: this view cannot answer "who beat" or "who
    surprised most" — it has actuals only. Use get_earnings_results for that.
    """
    try:
        data = await _calendar(_today(), time_slot)
    except Exception as e:
        return {"error": str(e)}
    if status:
        want = status.lower()
        reports = [r for r in (data.get("reports") or [])
                   if (r.get("status") or "").lower() == want]
        data = dict(data, reports=reports, total_count=len(reports))
    return dict(data, estimates_available=False, note=_NO_ESTIMATES_NOTE)


@mcp.tool()
async def get_upcoming_earnings(
    days: int = 7,
    min_importance: Optional[int] = None,
    limit: int = 200,
) -> dict:
    """Get upcoming earnings for the next N days.

    Args:
        days: Number of days ahead (1-30, default 7)
        min_importance: Minimum importance level 0-5 (higher = bigger company).
                        Use 3+ to filter to mid/large-cap names only.
        limit: Max results to return (default 200)

    Useful for planning and anticipating market-moving events.
    """
    params: dict = {"days": max(1, min(int(days), 30)), "limit": limit}
    if min_importance is not None:
        params["min_importance"] = min_importance
    try:
        return await service_get(config.api_gateway_url, f"{_EARNINGS_API}/upcoming",
                                 params=params)
    except Exception as e:
        return {"error": str(e)}


@mcp.tool()
async def get_earnings_by_ticker(ticker: str, limit: int = 12) -> dict:
    """Get earnings history for a specific ticker.

    Per-quarter estimates vs actuals, surprise percentages and the 1-day price
    reaction. This is the view that carries analyst estimates.
    """
    try:
        return await service_get(
            config.api_gateway_url,
            f"{_EARNINGS_API}/ticker/{ticker.upper()}",
            params={"limit": max(1, min(int(limit), 100))},
        )
    except Exception as e:
        return {"error": str(e)}


@mcp.tool()
async def get_earnings_by_date(date: str, time_slot: Optional[str] = None) -> dict:
    """Get earnings for a specific date (YYYY-MM-DD).

    Args:
        date: 'YYYY-MM-DD'
        time_slot: optional 'BMO' or 'AMC'

    Returns all companies reporting on that date, scheduled and reported.

    NO ESTIMATES AND NO SURPRISES: this view cannot answer "who beat", "who
    missed" or "who surprised most" — it has actuals only, and inferring a
    surprise from the summary text gets the sign wrong. Use
    get_earnings_results for anything comparing actual against estimate.
    """
    try:
        data = await _calendar(date, time_slot)
        return dict(data, estimates_available=False, note=_NO_ESTIMATES_NOTE)
    except Exception as e:
        return {"error": str(e)}


@mcp.tool()
async def get_earnings_results(
    date: Optional[str] = None,
    time_slot: Optional[str] = None,
    sort_by: str = "surprise",
    sort_order: str = "desc",
    limit: int = 40,
) -> dict:
    """Get actual reported earnings results for a given day.

    Who has ALREADY reported (vs the calendar, who WILL report) and how the
    numbers came in: EPS/revenue actual vs estimate, surprise percentages and
    price reaction. Sorted server-side, compact rows.

    Args:
        date: 'YYYY-MM-DD' (default: today, US/Eastern)
        time_slot: 'amc' (after market close) or 'bmo' (before market open)
        sort_by: 'surprise' (EPS surprise %, default), 'mkt_cap', or 'move'.
            'move' ranks the reporters by their price reaction — THE tool for
            "top earnings movers": for today it uses the live session reaction
            (post-market move for AMC reports, regular-session move for BMO);
            for past dates it uses post_move_pct (prev close -> close).
        sort_order: 'desc' (default) or 'asc' ('asc' + 'move' = biggest losers)
        limit: Max rows to return (default 40)

    Returns per company: symbol, company, time_slot, eps_estimate, eps_actual,
    eps_surprise_pct, revenue_estimate, revenue_actual, revenue_surprise_pct,
    report_date, market_cap, open_to_close_pct, post_move_pct,
    live_reaction_pct. Every row carries its own report_date, so rows from
    different days can be merged or re-sorted without losing which session
    they belong to.

    The three percentages measure DIFFERENT things and must not be compared
    with each other or merged into one column. Every response carries a
    `metric_definitions` block stating what each one is measured against —
    read it before labelling a column. In particular, `post_move_pct` includes
    the overnight gap and is not the move from the open; `open_to_close_pct`
    is. A null means "not available", never "no move".

    A surprise is present only when both the actual and the estimate are
    present, and is computed from those two numbers. A null estimate means the
    consensus was not published, so no beat/miss can be stated for that line.

    This is the ONLY earnings view with estimates and surprises: the day
    calendar has none. Use this one for "who beat", "who missed" or "who
    surprised most".
    """
    if time_slot and time_slot.upper() not in ("AMC", "BMO"):
        return {"error": "time_slot must be 'amc' or 'bmo'"}
    if sort_by not in ("surprise", "mkt_cap", "move"):
        return {"error": "sort_by must be 'surprise', 'mkt_cap' or 'move'"}
    if sort_order not in ("desc", "asc"):
        return {"error": "sort_order must be 'desc' or 'asc'"}
    slot = time_slot.upper() if time_slot else None

    if not date:
        date = _today()
    try:
        report_date = datetime.strptime(date, "%Y-%m-%d").date()
    except ValueError:
        return {"error": "Invalid date format (YYYY-MM-DD)"}

    try:
        cal = await _calendar(date, slot)
    except Exception as e:
        return {"error": f"calendar: {e}"}

    reports = [r for r in (cal.get("reports") or [])
               if isinstance(r, dict) and r.get("symbol")]
    reported = [r for r in reports if _has_actuals(r)]
    pending = [r for r in reports if not _has_actuals(r)]

    limit_n = max(1, min(int(limit), 200))

    # Build a row for EVERY reported company. The cut happens AFTER the
    # requested sort key exists on the rows: cutting by market cap first threw
    # away exactly the rows the ranking asked for (2026-08-04: 89 AMC
    # reporters, limit 40 → the 49 smallest caps — where the big after-hours
    # moves live — never reached the ranking).
    rows: dict[str, dict] = {}
    for r in reported:
        sym = r["symbol"].upper()
        rows[sym] = {
            "symbol": sym,
            # La fecha va EN LA FILA, no sólo en la cabecera de la respuesta.
            # Una fila anónima se puede fusionar, reordenar o mezclar con las
            # de otro día y acabar atribuida al día equivocado; con su fecha
            # encima, eso no puede pasar.
            "report_date": r.get("report_date") or date,
            "company": r.get("company_name"),
            "time_slot": r.get("time_slot"),
            # Hora exacta: 'DURING' no dice cuándo, y "durante la sesión" no
            # es ni pre-market ni after-hours. Sin esto, un reporte de las
            # 10:30 se lee como si hubiera sido antes de abrir.
            "report_time": r.get("report_time"),
            # Un EPS sin su trimestre no se puede comparar con nada. Varía
            # dentro del mismo día (Q1..Q4 conviven), así que va por fila.
            "fiscal_period": r.get("fiscal_period"),
            "fiscal_year": r.get("fiscal_year"),
            "status": r.get("status"),
            "eps_estimate": None,
            "eps_actual": _num(r.get("eps_actual")),
            "eps_surprise_pct": None,
            "revenue_estimate": None,
            "revenue_actual": _num(r.get("revenue_actual")),
            "revenue_surprise_pct": None,
            "post_move_pct": _move_pct(r.get("post_earnings_move_1d")),
            "market_cap": _num(r.get("market_cap")),
            "_currency": r.get("currency"),
        }

    is_today = report_date == datetime.now(_ET).date()

    # 'move' needs the live session reaction BEFORE sorting in two cases:
    # the date is today, or it is the LAST closed session — the provider's
    # post_earnings_move_1d arrives a day late (verified 2026-08-05 premarket:
    # 0/89 AMC rows of the prior evening had it), and for those AMC reporters
    # todaysChangePerc IS their reaction so far (change vs the report-day
    # close). One HMGET covers every reporter at once.
    live_move_used = False
    if sort_by == "move" and rows:
        is_last_session = False
        if not is_today:
            try:
                from clients.day_aggs import resolve_date
                is_last_session = date == resolve_date("yesterday")
            except Exception:
                is_last_session = False
        if is_today or is_last_session:
            try:
                import orjson
                from clients.redis_client import get_redis
                rd = await get_redis()
                raws = await rd.hmget("snapshot:enriched:latest", list(rows))
                for sym, raw in zip(rows, raws):
                    if not raw:
                        continue
                    snap = orjson.loads(raw)
                    row = rows[sym]
                    slot_r = (row.get("time_slot") or "").upper()
                    if is_today:
                        if slot_r == "BMO":
                            row["live_reaction_pct"] = _num(snap.get("todaysChangePerc"))
                        else:
                            row["live_reaction_pct"] = _num(snap.get("postmarket_change_percent"))
                    elif slot_r != "BMO":
                        # AMC de la última sesión: todaysChangePerc mide contra
                        # el cierre del día del reporte — SU reacción, aún viva.
                        # Para los BMO de ayer NO vale (mediría otra cosa).
                        row["live_reaction_pct"] = _num(snap.get("todaysChangePerc"))
                live_move_used = True
            except Exception:
                pass  # best-effort: rows sort as key-missing and coverage says so

    def _sort_value(row: dict):
        if sort_by == "mkt_cap":
            return row.get("market_cap")
        if sort_by == "move":
            if is_today:
                return row.get("live_reaction_pct")
            pm = row.get("post_move_pct")
            return pm if pm is not None else row.get("live_reaction_pct")
        return row.get("eps_surprise_pct")

    def _ranked(values: list[dict]) -> list[dict]:
        # None-last regardless of direction: a missing key never wins a rank.
        sign = -1.0 if sort_order == "desc" else 1.0
        return sorted(values, key=lambda r: (
            _sort_value(r) is None, sign * (_sort_value(r) or 0.0)))

    # Estimates live only on the per-ticker view, so completed rows get a
    # lookup. What it returns replaces the day-view numbers wholesale: actual
    # and estimate then come from the same view, and the surprise computed
    # below is a property of that pair.
    sem = asyncio.Semaphore(_DETAIL_CONCURRENCY)

    async def _complete(sym: str) -> bool:
        async with sem:
            try:
                hist = await service_get(
                    config.api_gateway_url,
                    f"{_EARNINGS_API}/ticker/{sym}",
                    params={"limit": 8},
                )
            except Exception:
                return False  # best-effort: a missing detail never fails the tool
        for ev in hist.get("earnings") or []:
            if not isinstance(ev, dict) or str(ev.get("report_date")) != date:
                continue
            eps_act = _num(ev.get("eps_actual"))
            rev_act = _num(ev.get("revenue_actual"))
            if eps_act is None and rev_act is None:
                return False
            row = rows[sym]
            row["eps_estimate"] = _num(ev.get("eps_estimate"))
            row["eps_actual"] = eps_act
            row["revenue_estimate"] = _num(ev.get("revenue_estimate"))
            row["revenue_actual"] = rev_act
            if ev.get("time_slot"):
                row["time_slot"] = ev.get("time_slot")
            if ev.get("post_earnings_move_1d") is not None:
                row["post_move_pct"] = _move_pct(ev.get("post_earnings_move_1d"))
            return True
        return False

    async def _run_completion(symbols: list[str]) -> int:
        if not symbols:
            return 0
        done = await asyncio.gather(*(_complete(s) for s in symbols))
        return sum(1 for ok in done if ok)

    skipped = 0
    if sort_by == "surprise":
        # The sort key IS the estimate pair: it has to exist before the cut,
        # so every reported row gets completed (the hard cap is the valve for
        # a pathological day, and it reports itself instead of hiding).
        targets = list(rows)[:_DETAIL_HARD_CAP]
        skipped = len(rows) - len(targets)
        completed = await _run_completion(targets)
        for row in rows.values():
            row["eps_surprise_pct"] = _surprise_pct(row["eps_actual"], row["eps_estimate"])
            row["revenue_surprise_pct"] = _surprise_pct(row["revenue_actual"],
                                                        row["revenue_estimate"])
        out_rows = _ranked(list(rows.values()))[:limit_n]
    else:
        # mkt_cap and move sort on keys the day view / snapshot already carry:
        # rank the FULL reported set, cut, and complete only the returned rows
        # — the per-ticker fan-out stays at `limit` calls.
        out_rows = _ranked(list(rows.values()))[:limit_n]
        targets = [r["symbol"] for r in out_rows]
        completed = await _run_completion(targets)
        for row in out_rows:
            row["eps_surprise_pct"] = _surprise_pct(row["eps_actual"], row["eps_estimate"])
            row["revenue_surprise_pct"] = _surprise_pct(row["revenue_actual"],
                                                        row["revenue_estimate"])

    # Movimiento apertura -> cierre de la sesión del reporte. Es la pregunta
    # que más se hace ("cómo se movió desde que abrió") y hasta ahora no se
    # podía responder para una fecha pasada: sólo existía post_move_pct, que
    # mide otra cosa. Los ficheros diarios son de cierre, así que hoy no tiene
    # fichero y se resuelve más abajo desde el snapshot.
    if out_rows:
        try:
            bars = day_bars(date, [r["symbol"] for r in out_rows])
            for row in out_rows:
                pct = open_to_close_pct(bars.get(row["symbol"]) or {})
                if pct is not None:
                    row["open_to_close_pct"] = pct
        except Exception:
            pass  # best-effort: sin barras, la fila sale sin ese campo

    # Same-day price reaction from the enriched snapshot: the earnings source
    # only carries the NEXT day's move, which arrives late. For today's rows
    # the reaction is the post-market move for AMC, the regular-session move
    # for BMO. Best-effort: if the cache is down, rows just lack the field.
    if out_rows and is_today:
        try:
            import orjson
            from clients.redis_client import get_redis
            r = await get_redis()
            raws = await r.hmget(
                "snapshot:enriched:latest", [row["symbol"] for row in out_rows]
            )
            for row, raw in zip(out_rows, raws):
                if not raw:
                    continue
                snap = orjson.loads(raw)
                if (row.get("time_slot") or "").upper() == "BMO":
                    row["live_reaction_pct"] = _num(snap.get("todaysChangePerc"))
                else:
                    row["live_reaction_pct"] = _num(snap.get("postmarket_change_percent"))
                # Hoy no hay fichero diario todavía: el mismo tramo sale del
                # snapshot, donde day.o/day.c son apertura y último precio.
                if row.get("open_to_close_pct") is None:
                    day = snap.get("day")
                    if isinstance(day, dict):
                        pct = open_to_close_pct(
                            {"open": day.get("o"), "close": day.get("c")})
                        if pct is not None:
                            row["open_to_close_pct"] = pct
        except Exception:
            pass

    # Una cifra monetaria sin moneda es ambigua por naturaleza. Si toda la
    # respuesta comparte moneda se declara una vez; si se mezclan, cada fila
    # lleva la suya. Así la identidad no cuesta payload cuando no hace falta.
    monedas = {r.get("_currency") for r in out_rows if r.get("_currency")}
    if len(monedas) == 1:
        for r in out_rows:
            r.pop("_currency", None)
    else:
        for r in out_rows:
            r["currency"] = r.pop("_currency", None)

    covered = sum(1 for r in out_rows if _sort_value(r) is not None)
    out = {
        "date": date,
        "time_slot": slot,
        "sort_by": sort_by,
        "sort_order": sort_order,
        # Rows in the returned set that actually carry the requested sort key.
        # 0 means the ranking is nominal: say so instead of presenting order.
        "sort_key_coverage": f"{covered}/{len(out_rows)}",
        "count": len(out_rows),
        # Scheduled but not yet reported, straight from the day view.
        "scheduled_pending": len(pending),
        # How many returned rows carry a published consensus. Well below
        # `count` means the consensus is genuinely missing upstream.
        "with_estimates": sum(1 for r in out_rows if r["eps_estimate"] is not None),
        # Qué significa cada porcentaje de las filas de arriba.
        "metric_definitions": _METRIC_DEFINITIONS,
        "results": out_rows,
    }
    if sort_by == "move":
        if is_today:
            out["move_key"] = "live_reaction_pct"
        elif live_move_used:
            out["move_key"] = (
                "post_move_pct, with live_reaction_pct fallback (change vs the "
                "report-day close) for rows where the provider's 1-day move is "
                "not published yet"
            )
        else:
            out["move_key"] = "post_move_pct"
    if out_rows and covered == 0:
        out["sort_key_available"] = False
        out["sort_note"] = (
            f"no returned row carries the '{sort_by}' key for {date}: the rows "
            "are NOT meaningfully ordered — do not present them as a ranking"
        )
    if len(monedas) == 1:
        out["currency"] = next(iter(monedas))
    if skipped:
        out["truncated"] = (
            f"{skipped} reported row(s) beyond the completion cap of "
            f"{_DETAIL_HARD_CAP} were ranked without estimates"
        )
    if targets and completed < len(targets):
        out["partial"] = (
            f"per-ticker completion failed for {len(targets) - completed} of "
            f"{len(targets)} row(s); those rows carry day-view actuals only"
        )
    return out
