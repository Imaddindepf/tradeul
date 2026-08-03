"""Simulador de cartera sobre disparos L0 (Fase 2 del diseño, MVP intradía).

El principio rector aplicado a la simulación: las ENTRADAS no se estiman —
son los disparos reales del motor vivo (analysis/triggers.py, matcher con
paridad verificada). Este módulo solo simula lo que hace el mercado con esas
entradas: fills, stops y objetivos INTRABAR sobre el minuto de Polygon,
capacidad de cartera por orden cronológico y costes.

Supuestos de ejecución, dichos en voz alta (se devuelven en `assumptions`):
  - Entrada en la APERTURA de la primera barra de minuto posterior al disparo
    («assume fill worse than ideal — next bar open»). Sin look-ahead.
  - Stop y objetivo intrabar; si la barra abre saltándose el stop (gap through)
    el fill es la apertura, no el precio del stop. Si stop y objetivo caben en
    la misma barra, se asume el STOP primero (conservador).
  - Solo sesión regular: disparos fuera de la ventana de entrada se saltan y
    se cuentan. TODO se cierra al fin de sesión (16:00 ET) — sin overnight.
  - Sizing: % fijo del capital INICIAL, acciones enteras, sin piramidar
    (un disparo por símbolo mientras la posición viva), sin compounding.
  - Cortos: sin coste ni disponibilidad de borrow (aviso).

Lo que este MVP no es: un simulador de swing multi-día ni un motor de
optimización. Es el puente medible entre «mi alerta dispara» y «mi alerta
gana dinero con estas salidas».
"""

from __future__ import annotations

import heapq
from bisect import bisect_right
from collections import Counter
from datetime import date, datetime, time
from pathlib import Path
from typing import Dict, List, Optional
from zoneinfo import ZoneInfo

import duckdb

from analysis.triggers import TriggerAnalyzer

_ET = ZoneInfo("America/New_York")
_NS = 1_000_000_000

_DEFAULTS = {
    "direction": "long",          # long | short
    "stop_pct": 5.0,              # % desde el fill
    "target_pct": 10.0,           # % desde el fill
    "max_hold_min": None,         # minutos; None = hasta stop/target/EOD
    "initial_capital": 100_000.0,
    "position_size_pct": 10.0,    # % del capital inicial por posición
    "max_positions": 10,
    "slippage_bps": 10.0,         # por lado
    "commission_per_trade": 0.0,  # por lado
    "entry_from_et": "09:30",     # ventana de entrada (sesión regular)
    "entry_to_et": "15:30",
}

_MAX_SIM_ENTRIES = 100_000


class _DayBars:
    """Barras 1-min de los símbolos de un día, indexadas para bisect."""

    def __init__(self, minute_file: Path, symbols: List[str]):
        self.data: Dict[str, tuple] = {}
        if not minute_file.exists() or not symbols:
            return
        con = duckdb.connect()
        ph = ",".join("?" * len(symbols))
        rows = con.execute(
            f"SELECT ticker, window_start, open, high, low, close "
            f"FROM read_parquet('{minute_file}') WHERE ticker IN ({ph}) "
            f"ORDER BY ticker, window_start", symbols
        ).fetchall()
        cur, ws, o, h, l, c = None, [], [], [], [], []
        for t, w, op, hi, lo, cl in rows:
            if t != cur:
                if cur is not None:
                    self.data[cur] = (ws, o, h, l, c)
                cur, ws, o, h, l, c = t, [], [], [], [], []
            ws.append(int(w)); o.append(float(op)); h.append(float(hi))
            l.append(float(lo)); c.append(float(cl))
        if cur is not None:
            self.data[cur] = (ws, o, h, l, c)


def _hhmm_ns(dt: str, hhmm: str) -> int:
    h, m = hhmm.split(":")
    return int(datetime.combine(date.fromisoformat(dt), time(int(h), int(m)), _ET)
               .timestamp() * _NS)


class PortfolioSimulator:
    def __init__(self, lake_dir: str = "/data/lake",
                 minute_dir: str = "/data/polygon/minute_aggs") -> None:
        self.analyzer = TriggerAnalyzer(lake_dir=lake_dir, minute_dir=minute_dir)
        self.minute_dir = Path(minute_dir)

    def run(self, strategy: dict, date_from: str, date_to: str,
            config: Optional[dict] = None) -> dict:
        cfg = {**_DEFAULTS, **(config or {})}
        short = cfg["direction"] == "short"
        slip = float(cfg["slippage_bps"]) / 10_000.0
        stop_f = float(cfg["stop_pct"]) / 100.0
        tgt_f = float(cfg["target_pct"]) / 100.0
        commission = float(cfg["commission_per_trade"])
        capital = float(cfg["initial_capital"])
        per_pos = capital * float(cfg["position_size_pct"]) / 100.0
        max_pos = int(cfg["max_positions"])
        hold_ns = (int(cfg["max_hold_min"]) * 60 * _NS) if cfg.get("max_hold_min") else None

        trig = self.analyzer.run(strategy, date_from, date_to, collect_triggers=True)
        entries = trig.pop("triggers_all")
        warnings = list(trig["warnings"])

        skipped = Counter()
        if len(entries) > _MAX_SIM_ENTRIES:
            warnings.append({
                "code": "entries_truncated",
                "detail": f"{len(entries)} disparos: se simulan los primeros {_MAX_SIM_ENTRIES} "
                          "en orden cronológico. Afina los filtros de la estrategia.",
            })
            entries = entries[:_MAX_SIM_ENTRIES]

        trades: List[dict] = []
        open_heap: list = []          # (exit_ts, symbol)
        in_position: set = set()
        bars_by_day: Dict[str, _DayBars] = {}
        symbols_by_day: Dict[str, set] = {}
        for t in entries:
            symbols_by_day.setdefault(t["dt"], set()).add(t["symbol"])

        for t in entries:
            dt, sym, ts = t["dt"], t["symbol"], t["ts_ns"]
            entry_open = _hhmm_ns(dt, cfg["entry_from_et"])
            entry_close = _hhmm_ns(dt, cfg["entry_to_et"])
            eod = _hhmm_ns(dt, "16:00")
            if ts < entry_open or ts > entry_close:
                skipped["session_window"] += 1
                continue
            # liberar posiciones ya cerradas a esta hora
            while open_heap and open_heap[0][0] <= ts:
                _, done_sym = heapq.heappop(open_heap)
                in_position.discard(done_sym)
            if sym in in_position:
                skipped["already_in_position"] += 1
                continue
            if len(in_position) >= max_pos:
                skipped["max_positions"] += 1
                continue

            day = bars_by_day.get(dt)
            if day is None:
                day = _DayBars(self.minute_dir / f"{dt}.parquet",
                               sorted(symbols_by_day[dt]))
                bars_by_day[dt] = day
            series = day.data.get(sym)
            if not series:
                skipped["no_bars"] += 1
                continue
            ws, o, h, l, c = series
            i = bisect_right(ws, ts)          # primera barra POSTERIOR al disparo
            if i >= len(ws) or ws[i] >= eod:
                skipped["no_bars"] += 1
                continue

            fill = o[i] * (1 - slip if short else 1 + slip)
            shares = int(per_pos // fill)
            if shares <= 0:
                skipped["price_over_position_size"] += 1
                continue
            if short:
                stop_px, tgt_px = fill * (1 + stop_f), fill * (1 - tgt_f)
            else:
                stop_px, tgt_px = fill * (1 - stop_f), fill * (1 + tgt_f)
            deadline = ts + hold_ns if hold_ns else None

            exit_px, exit_ws, reason = None, None, None
            for j in range(i, len(ws)):
                if ws[j] >= eod:
                    exit_px, exit_ws, reason = o[j], ws[j], "session_close"
                    break
                if deadline is not None and ws[j] >= deadline:
                    exit_px, exit_ws, reason = o[j], ws[j], "max_hold"
                    break
                if short:
                    if o[j] >= stop_px:
                        exit_px, exit_ws, reason = o[j], ws[j], "stop_gap"
                        break
                    if h[j] >= stop_px:
                        exit_px, exit_ws, reason = stop_px, ws[j], "stop"
                        break
                    if l[j] <= tgt_px:
                        exit_px, exit_ws, reason = tgt_px, ws[j], "target"
                        break
                else:
                    if o[j] <= stop_px:
                        exit_px, exit_ws, reason = o[j], ws[j], "stop_gap"
                        break
                    if l[j] <= stop_px:
                        exit_px, exit_ws, reason = stop_px, ws[j], "stop"
                        break
                    if h[j] >= tgt_px:
                        exit_px, exit_ws, reason = tgt_px, ws[j], "target"
                        break
            if exit_px is None:                # se acabaron las barras del día
                exit_px, exit_ws, reason = c[len(ws) - 1], ws[len(ws) - 1], "last_bar"
            exit_fill = exit_px * (1 + slip if short else 1 - slip)

            gross = (fill - exit_fill if short else exit_fill - fill) * shares
            pnl = gross - 2 * commission
            trades.append({
                "symbol": sym, "dt": dt, "event_type": t["event_type"],
                "entry_ts": t["ts"], "entry_px": round(fill, 4),
                "exit_ts_ns": exit_ws, "exit_px": round(exit_fill, 4),
                "shares": shares, "reason": reason,
                "pnl": round(pnl, 2),
                "ret_pct": round(pnl / (fill * shares) * 100, 4),
            })
            in_position.add(sym)
            heapq.heappush(open_heap, (exit_ws, sym))

        return self._report(trades, skipped, warnings, cfg, capital, trig,
                            date_from, date_to)

    # ── métricas ─────────────────────────────────────────────────────────

    def _report(self, trades, skipped, warnings, cfg, capital, trig,
                date_from, date_to) -> dict:
        if cfg["direction"] == "short":
            warnings.append({
                "code": "short_borrow_ignored",
                "detail": "los cortos se simulan sin coste ni disponibilidad de borrow",
            })
        trades.sort(key=lambda x: x["exit_ts_ns"])
        wins = [x["pnl"] for x in trades if x["pnl"] > 0]
        losses = [x["pnl"] for x in trades if x["pnl"] <= 0]
        gross_win, gross_loss = sum(wins), -sum(losses)

        equity, peak, max_dd = capital, capital, 0.0
        curve: List[tuple] = []
        max_consec_loss, cur_consec = 0, 0
        daily = Counter()
        for x in trades:
            equity += x["pnl"]
            peak = max(peak, equity)
            max_dd = max(max_dd, (peak - equity) / peak * 100 if peak else 0.0)
            curve.append((x["exit_ts_ns"], round(equity, 2)))
            cur_consec = cur_consec + 1 if x["pnl"] <= 0 else 0
            max_consec_loss = max(max_consec_loss, cur_consec)
            daily[x["dt"]] += x["pnl"]

        n = len(trades)
        step = max(1, n // 2000)
        return {
            "strategy": trig["strategy"],
            "range": trig["range"],
            "execution": {k: cfg[k] for k in _DEFAULTS},
            "assumptions": [
                "entrada en la apertura de la barra de minuto siguiente al disparo (sin look-ahead)",
                "stop/objetivo intrabar; gap a través del stop ejecuta a la apertura; stop antes que objetivo en la misma barra",
                "solo sesión regular; todo cerrado a las 16:00 ET (sin overnight)",
                "sizing sobre capital inicial, acciones enteras, sin piramidar ni compounding",
            ],
            "triggers_total": trig["triggers_total"],
            "entries_simulated": n,
            "entries_skipped": dict(skipped),
            "metrics": {
                "trades": n,
                "win_rate": round(len(wins) / n, 4) if n else None,
                "profit_factor": round(gross_win / gross_loss, 3) if gross_loss > 0 else None,
                "total_pnl": round(sum(x["pnl"] for x in trades), 2),
                "total_return_pct": round(sum(x["pnl"] for x in trades) / capital * 100, 3),
                "avg_win": round(gross_win / len(wins), 2) if wins else None,
                "avg_loss": round(-gross_loss / len(losses), 2) if losses else None,
                "expectancy": round(sum(x["pnl"] for x in trades) / n, 2) if n else None,
                "max_drawdown_pct": round(max_dd, 3),
                "max_consecutive_losses": max_consec_loss,
                "by_exit_reason": dict(Counter(x["reason"] for x in trades)),
            },
            "daily_pnl": {d: round(v, 2) for d, v in sorted(daily.items())},
            "equity_curve": curve[::step],
            "trades_sample": trades[:100],
            "per_day": trig["per_day"],
            "warnings": warnings,
            "provenance": {
                **trig.get("provenance", {}),
                "engine": "cartera L2-MVP sobre disparos L0 — entradas reales, ejecución simulada",
            },
        }
