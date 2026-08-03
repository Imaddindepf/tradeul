"""Análisis de disparos L0 (Fase 1, §7.1 del diseño): eventos REALES del lake.

Responde «¿mi estrategia es señal o es ruido?» sin motor de cartera: cuántas
veces habría disparado la estrategia BUILD, dónde y cuándo, y qué hizo el
precio 5/15/60 minutos después y al cierre.

Fidelidad, dicha en voz alta (§7.3):
  - Los disparos no se estiman: son las alertas que el motor vivo emitió, con
    las métricas point-in-time que llevaban. El filtrado usa EL MISMO matcher
    portado y verificado contra producción (matching/, paridad 1.113/1.113).
  - Filtros de snapshot (fuente enrichedCache) se evalúan con el slow snapshot
    del cierre del día — aproximación etiquetada; en días sin snapshot se
    OMITEN y se avisa con la lista exacta (nunca en silencio).
  - Filtros de índice (SPY/QQQ/DIA): evaluados desde las barras de minuto del
    ETF en el instante de cada disparo — precisión 1-min frente al segundo del
    vivo (cuya borrosidad interna ya es de 10-30 s). Etiquetado degradado.
  - `aq:` se evalúa por día SOLO si las particiones de ese día llevan
    `quality` (se persiste desde que el fix de persistencia esté desplegado);
    los días sin quality se omiten con aviso.

Los agregados (recuentos, distribuciones, forward returns) se calculan sobre
la POBLACIÓN COMPLETA de disparos; cuando supera `max_triggers`, los forward
returns usan una muestra aleatoria uniforme (reservoir, seed fija) y lo dicen.
"""

from __future__ import annotations

import json
import random
from bisect import bisect_right
from collections import Counter, defaultdict
from datetime import date, datetime, time, timedelta
from pathlib import Path
from typing import Dict, List, Optional, Tuple
from zoneinfo import ZoneInfo

import duckdb

from matching import boundary
from matching.matcher import (
    _chk,
    build_event_payload,
    build_event_subscription,
    enrich_event_from_cache,
    event_passes_subscription,
)
from matching.matcher_defs_generated import (
    INDEX_FILTER_DEFS,
    INDEX_FILTER_WINDOWS,
    SOURCE_SHA256,
)

_ET = ZoneInfo("America/New_York")

# Inverso de ALERT_KEY_TO_COL (services/alert_engine/persistence/__init__.py):
# el lake guarda columnas de BD; el matcher habla las claves del stream.
_COL_TO_KEY = {
    "ts": "timestamp",
    "change_pct": "change_percent",
    "gap_pct": "gap_percent",
    "atr_pct": "atr_percent",
}

_NS = 1_000_000_000
_SAMPLE_SEED = 20260802
# Un valor de índice se considera ausente si la última barra del ETF queda a
# más de esto del instante consultado (huecos de datos, no de mercado).
_INDEX_STALENESS_NS = 10 * 60 * _NS

_PREFIX_TO_SYM = dict(INDEX_FILTER_DEFS)  # spyChg -> SPY, qqqChg -> QQQ, ...
_WINDOW_NS = {"5min": 5, "10min": 10, "15min": 15, "30min": 30}


class _IndexSeries:
    """Series de cierres 1-min de un ETF de índice para un día (+ prev close)."""

    def __init__(self, times: List[int], closes: List[float], prev_close: Optional[float]):
        self.times = times
        self.closes = closes
        self.prev_close = prev_close

    def close_at(self, ts_ns: int) -> Optional[float]:
        i = bisect_right(self.times, ts_ns) - 1
        if i < 0 or ts_ns - self.times[i] > _INDEX_STALENESS_NS:
            return None
        return self.closes[i]

    def chg_window(self, ts_ns: int, minutes: int) -> Optional[float]:
        now = self.close_at(ts_ns)
        then = self.close_at(ts_ns - minutes * 60 * _NS)
        if now is None or then is None or not then:
            return None
        return (now - then) / then * 100

    def chg_today(self, ts_ns: int) -> Optional[float]:
        now = self.close_at(ts_ns)
        if now is None or not self.prev_close:
            return None
        return (now - self.prev_close) / self.prev_close * 100


class TriggerAnalyzer:
    def __init__(
        self,
        lake_dir: str = "/data/lake",
        minute_dir: str = "/data/polygon/minute_aggs",
        horizons_min: tuple = (5, 15, 60),
    ) -> None:
        self.events_dir = Path(lake_dir) / "events"
        self.snapshot_dir = Path(lake_dir) / "reference" / "enriched_close"
        self.minute_dir = Path(minute_dir)
        self.horizons_min = horizons_min

    # ── público ──────────────────────────────────────────────────────────

    def run(self, strategy: dict, date_from: str, date_to: str,
            max_triggers: int = 20000, collect_triggers: bool = False) -> dict:
        """`collect_triggers=True` añade `triggers_all` (la población entera,
        ordenada cronológicamente) para el simulador de cartera. Solo memoria:
        no cambia recuentos ni forward returns."""
        problems = boundary.validate_strategy(strategy)
        if problems["unknown_events"] or problems["unknown_filters"]:
            raise ValueError(json.dumps(problems))

        event_types = strategy.get("event_types") or []
        if not event_types:
            raise ValueError(json.dumps({"error": "event_types vacío: el análisis L0 necesita al menos un tipo"}))

        sources = boundary.classify_filters(strategy)
        warnings: List[dict] = []
        base_filters = {k: v for k, v in strategy.items() if k != "event_types"}

        # aq: — evaluable por día solo si ese día persiste `quality`
        aq_filters = {k: base_filters.pop(k) for k in sorted(base_filters)
                      if sources.get(k) == "quality"}
        # índices — evaluados aparte, desde el minuto del ETF
        index_filters = {k: base_filters.pop(k) for k in sorted(base_filters)
                         if sources.get(k) == "index"}
        index_sub = build_event_subscription(index_filters) if index_filters else None
        index_checks = self._active_index_checks(index_sub) if index_sub else []
        if index_filters:
            warnings.append({
                "code": "index_filters_from_minute",
                "filters": sorted(index_filters),
                "detail": "evaluados desde barras 1-min del ETF en el instante del disparo "
                          "(el vivo usa ventanas de 1 s con borrosidad 10-30 s): degradado, no omitido",
            })

        snapshot_keys = sorted(k for k, s in sources.items() if s == "snapshot" and k in base_filters)

        dts = self._trading_days(date_from, date_to)
        rng = random.Random(_SAMPLE_SEED)
        all_triggers: List[dict] = []
        reservoir: List[dict] = []
        sample_chrono: List[dict] = []
        seen = 0
        by_type: Counter = Counter()
        by_hour: Counter = Counter()
        by_symbol: Counter = Counter()
        per_day: Dict[str, dict] = {}
        days_no_quality: List[str] = []

        for dt in dts:
            day = self._analyze_day(dt, event_types, base_filters, snapshot_keys,
                                    aq_filters, index_checks)
            per_day[dt] = day["status"]
            if aq_filters and not day["status"].get("quality"):
                days_no_quality.append(dt)
            if collect_triggers:
                all_triggers.extend(day["triggers"])
            for t in day["triggers"]:
                seen += 1
                by_type[t["event_type"]] += 1
                by_hour[t["hour_et"]] += 1
                by_symbol[t["symbol"]] += 1
                if len(sample_chrono) < 200:
                    sample_chrono.append(t)
                # reservoir uniforme (Algorithm R) para forward returns
                if len(reservoir) < max_triggers:
                    reservoir.append(t)
                else:
                    j = rng.randrange(seen)
                    if j < max_triggers:
                        reservoir[j] = t

        sampled = seen > len(reservoir)
        if sampled:
            warnings.append({
                "code": "forward_returns_sampled",
                "detail": f"población de {seen} disparos: forward returns sobre muestra "
                          f"aleatoria uniforme de {len(reservoir)} (seed {_SAMPLE_SEED}); "
                          "los recuentos y distribuciones usan la población completa",
            })
        days_no_snapshot = [d for d, s in per_day.items() if snapshot_keys and not s["snapshot"]]
        if days_no_snapshot:
            warnings.append({
                "code": "snapshot_filters_skipped",
                "filters": snapshot_keys,
                "days": days_no_snapshot,
                "detail": "sin slow snapshot ese día: esos filtros no se aplicaron",
            })
        if snapshot_keys:
            warnings.append({
                "code": "snapshot_filters_approximated",
                "filters": snapshot_keys,
                "detail": "evaluados con el snapshot del CIERRE del día (aproximación etiquetada)",
            })
        if days_no_quality:
            warnings.append({
                "code": "aq_filters_skipped",
                "filters": sorted(aq_filters),
                "days": days_no_quality,
                "detail": "esas particiones no llevan `quality` (no se persistía): aq: no aplicado esos días",
            })

        fwd = self._forward_returns(reservoir)
        fwd["population_n"] = seen
        fwd["sampled"] = sampled

        extra = {}
        if collect_triggers:
            all_triggers.sort(key=lambda t: t["ts_ns"])
            extra["triggers_all"] = all_triggers

        return {
            **extra,
            "strategy": strategy,
            "range": {"from": date_from, "to": date_to, "days_analyzed": list(per_day)},
            "triggers_total": seen,
            "per_day": per_day,
            "by_type": dict(by_type),
            "by_hour_et": dict(sorted(by_hour.items())),
            "top_symbols": dict(by_symbol.most_common(20)),
            "forward_returns": fwd,
            "triggers_sample": sample_chrono,
            "warnings": warnings,
            "provenance": {
                "source": "L0 — eventos reales del lake (fidelidad 1.0 por definición)",
                "matcher_defs_sha256": SOURCE_SHA256,
                "generated_at": datetime.now(tz=_ET).isoformat(),
            },
        }

    # ── índices ──────────────────────────────────────────────────────────

    def _active_index_checks(self, index_sub: dict) -> List[Tuple[str, str, Optional[int], object, object]]:
        """[(sym, window_label, minutos|None=today, lo, hi)] con algún límite activo."""
        checks = []
        for prefix, sym in INDEX_FILTER_DEFS:
            for w_camel, _field in INDEX_FILTER_WINDOWS:
                lo = index_sub.get(f"{prefix}{w_camel}Min")
                hi = index_sub.get(f"{prefix}{w_camel}Max")
                if lo is None and hi is None:
                    continue
                minutes = _WINDOW_NS.get(w_camel.lower())
                checks.append((sym, w_camel, minutes, lo, hi))
        return checks

    def _load_index_series(self, dt: str, symbols: List[str]) -> Dict[str, _IndexSeries]:
        minute_file = self.minute_dir / f"{dt}.parquet"
        if not minute_file.exists() or not symbols:
            return {}
        prev_file = self._prev_minute_file(dt)
        con = duckdb.connect()
        out: Dict[str, _IndexSeries] = {}
        ph = ",".join("?" * len(symbols))
        rows = con.execute(
            f"SELECT ticker, window_start, close FROM read_parquet('{minute_file}') "
            f"WHERE ticker IN ({ph}) ORDER BY ticker, window_start", symbols
        ).fetchall()
        prev_closes: Dict[str, float] = {}
        if prev_file is not None:
            prev_dt = prev_file.stem[:10]
            cutoff = int(datetime.combine(date.fromisoformat(prev_dt), time(16, 0), _ET)
                         .timestamp() * _NS)
            prows = con.execute(
                f"SELECT ticker, max_by(close, window_start) FROM read_parquet('{prev_file}') "
                f"WHERE ticker IN ({ph}) AND window_start <= {cutoff} GROUP BY ticker", symbols
            ).fetchall()
            prev_closes = {t: c for t, c in prows}
        series: Dict[str, Tuple[List[int], List[float]]] = defaultdict(lambda: ([], []))
        for ticker, ws, close in rows:
            series[ticker][0].append(int(ws))
            series[ticker][1].append(float(close))
        for sym in symbols:
            times, closes = series.get(sym, ([], []))
            out[sym] = _IndexSeries(times, closes, prev_closes.get(sym))
        return out

    def _prev_minute_file(self, dt: str) -> Optional[Path]:
        # todo el rango del lake (jul-2026) tiene el minuto en parquet
        d = date.fromisoformat(dt)
        for _ in range(7):
            d -= timedelta(days=1)
            p = self.minute_dir / f"{d.isoformat()}.parquet"
            if p.exists():
                return p
        return None

    # ── por día ──────────────────────────────────────────────────────────

    def _trading_days(self, date_from: str, date_to: str) -> List[str]:
        d0, d1 = date.fromisoformat(date_from), date.fromisoformat(date_to)
        out = []
        d = d0
        while d <= d1:
            if (self.events_dir / f"dt={d.isoformat()}").is_dir():
                out.append(d.isoformat())
            d += timedelta(days=1)
        return out

    def _analyze_day(self, dt: str, event_types: List[str],
                     base_filters: dict, snapshot_keys: List[str],
                     aq_filters: dict, index_checks: list) -> dict:
        parts = [self.events_dir / f"dt={dt}" / f"event_type={t}"
                 for t in event_types]
        globs = [str(p / "*.parquet") for p in parts if p.is_dir()]
        status = {"events_scanned": 0, "triggers": 0, "snapshot": False,
                  "types_present": len(globs)}
        if not globs:
            return {"triggers": [], "status": status}

        con = duckdb.connect()
        rows = con.execute(
            "SELECT * FROM read_parquet(?, union_by_name=true)", [globs]
        ).fetchall()
        cols = [d[0] for d in con.execute(
            "SELECT * FROM read_parquet(?, union_by_name=true) LIMIT 0", [globs]
        ).description]
        status["events_scanned"] = len(rows)

        snap_file = self.snapshot_dir / f"dt={dt}" / "enriched_close.parquet"
        cache: Dict[str, dict] = {}
        day_filters = dict(base_filters)
        if snap_file.exists() and snapshot_keys:
            symbols = sorted({r[cols.index("symbol")] for r in rows})
            sdf = con.execute(
                f"SELECT * FROM read_parquet('{snap_file}') WHERE symbol IN "
                f"({','.join('?' * len(symbols))})", symbols
            ).df()
            scols = sdf.columns.tolist()
            for rec in sdf.itertuples(index=False):
                d = {k: v for k, v in zip(scols, rec) if v is not None and v == v}
                cache[d["symbol"]] = d
            status["snapshot"] = True
        elif snapshot_keys:
            for k in snapshot_keys:
                day_filters.pop(k, None)
        elif snap_file.exists():
            status["snapshot"] = True

        # aq: solo si este día persiste quality
        day_has_quality = "quality" in cols
        status["quality"] = day_has_quality
        if aq_filters and day_has_quality:
            day_filters.update(aq_filters)

        index_series = (self._load_index_series(dt, sorted({c[0] for c in index_checks}))
                        if index_checks else {})

        sub = build_event_subscription({"event_types": event_types, **day_filters})
        watch_fields = sorted({
            f for k in day_filters
            if (f := boundary.event_field_for(k)) is not None
        })
        null_counts = {f: 0 for f in watch_fields}
        triggers = []
        index_rejected = 0
        for r in rows:
            evt_fields = {}
            for c, v in zip(cols, r):
                if c == "dt" or v is None:
                    continue
                key = _COL_TO_KEY.get(c, c)
                evt_fields[key] = v.isoformat() if c == "ts" else v
            for f in watch_fields:
                if evt_fields.get(f) is None:
                    null_counts[f] += 1
            payload = build_event_payload(evt_fields)
            enrich_event_from_cache(payload, cache)
            if not event_passes_subscription(payload, sub, cache):
                continue
            ts = datetime.fromisoformat(evt_fields["timestamp"])
            ts_ns = int(ts.timestamp() * _NS)
            if index_checks:
                ok = True
                for sym, w_camel, minutes, lo, hi in index_checks:
                    serie = index_series.get(sym)
                    if serie is None:
                        v = None
                    elif minutes is None:
                        v = serie.chg_today(ts_ns)
                    else:
                        v = serie.chg_window(ts_ns, minutes)
                    # misma semántica que el matcher: chkEvt estricto/invertido
                    if not _chk(v, lo, hi):
                        ok = False
                        break
                if not ok:
                    index_rejected += 1
                    continue
            et = ts.astimezone(_ET)
            triggers.append({
                "ts": evt_fields["timestamp"],
                "ts_ns": ts_ns,
                "dt": dt,
                "hour_et": et.hour,
                "symbol": evt_fields["symbol"],
                "event_type": evt_fields["event_type"],
                "price": payload.get("price"),
                "change_percent": payload.get("change_percent"),
                "rvol": payload.get("rvol"),
            })
        status["triggers"] = len(triggers)
        if index_checks:
            status["index_rejected"] = index_rejected
        if rows:
            degraded = {f: round(c / len(rows), 3) for f, c in null_counts.items()
                        if c / len(rows) > 0.5}
            if degraded:
                # agujero de datos: el filtro descartó por AUSENCIA, no por valor
                status["data_holes"] = degraded
        return {"triggers": triggers, "status": status}

    # ── forward returns ──────────────────────────────────────────────────

    def _forward_returns(self, triggers: List[dict]) -> dict:
        usable = [t for t in triggers if t.get("price")]
        horizons = [(f"{m}min", m * 60 * _NS) for m in self.horizons_min]
        stats: Dict[str, list] = {h: [] for h, _ in horizons}
        stats["close"] = []

        by_dt: Dict[str, list] = defaultdict(list)
        for t in usable:
            by_dt[t["dt"]].append(t)

        con = duckdb.connect()
        for dt, day_triggers in by_dt.items():
            minute_file = self.minute_dir / f"{dt}.parquet"
            if not minute_file.exists():
                continue
            symbols = sorted({t["symbol"] for t in day_triggers})
            con.execute("DROP TABLE IF EXISTS bars")
            con.execute(
                f"CREATE TEMP TABLE bars AS SELECT ticker, window_start, close "
                f"FROM read_parquet('{minute_file}') WHERE ticker IN "
                f"({','.join('?' * len(symbols))})", symbols
            )
            close_et = int(datetime.combine(date.fromisoformat(dt), time(16, 0), _ET)
                           .timestamp() * _NS)
            # una fila por (disparo, horizonte) con la diana como COLUMNA:
            # el ASOF JOIN de DuckDB exige la desigualdad entre columnas
            probe_rows = []
            for t in day_triggers:
                for name, delta_ns in horizons:
                    probe_rows.append((name, t["symbol"], t["ts_ns"],
                                       t["ts_ns"] + delta_ns, t["price"]))
                if t["ts_ns"] < close_et:
                    probe_rows.append(("close", t["symbol"], t["ts_ns"],
                                       close_et, t["price"]))
            con.execute("DROP TABLE IF EXISTS trg")
            con.execute(
                "CREATE TEMP TABLE trg(horizon TEXT, symbol TEXT, ts_ns BIGINT, "
                "target_ns BIGINT, price DOUBLE)"
            )
            con.executemany("INSERT INTO trg VALUES (?, ?, ?, ?, ?)", probe_rows)
            rows = con.execute(
                f"SELECT t.horizon, t.price, b.close FROM trg t "
                f"ASOF JOIN bars b ON t.symbol = b.ticker AND b.window_start <= t.target_ns "
                f"WHERE b.window_start >= t.ts_ns - {60 * _NS}"
            ).fetchall()
            for name, p, fwd in rows:
                if p and fwd is not None:
                    stats[name].append((fwd - p) / p * 100)

        out = {}
        for name, vals in stats.items():
            if not vals:
                out[name] = {"n": 0}
                continue
            vals.sort()
            n = len(vals)
            out[name] = {
                "n": n,
                "mean_pct": round(sum(vals) / n, 4),
                "median_pct": round(vals[n // 2], 4),
                "win_rate": round(sum(1 for v in vals if v > 0) / n, 4),
                "p10_pct": round(vals[int(n * 0.10)], 4),
                "p90_pct": round(vals[min(int(n * 0.90), n - 1)], 4),
            }
        return out


def _cli() -> None:
    import argparse
    import sys

    ap = argparse.ArgumentParser(description="Análisis de disparos L0 sobre el lake")
    ap.add_argument("--strategy-json", required=True,
                    help="JSON inline o @fichero con {event_types, ...filters}")
    ap.add_argument("--from", dest="date_from", required=True)
    ap.add_argument("--to", dest="date_to", required=True)
    ap.add_argument("--lake-dir", default="/data/lake")
    ap.add_argument("--minute-dir", default="/data/polygon/minute_aggs")
    args = ap.parse_args()

    raw = args.strategy_json
    strategy = json.loads(Path(raw[1:]).read_text() if raw.startswith("@") else raw)
    engine = TriggerAnalyzer(lake_dir=args.lake_dir, minute_dir=args.minute_dir)
    try:
        result = engine.run(strategy, args.date_from, args.date_to)
    except ValueError as e:
        print(f"422 — estrategia no válida: {e}", file=sys.stderr)
        sys.exit(1)
    json.dump(result, sys.stdout, indent=2, ensure_ascii=False, default=str)
    print()


if __name__ == "__main__":
    _cli()
