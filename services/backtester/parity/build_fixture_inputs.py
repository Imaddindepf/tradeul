#!/usr/bin/env python3
"""Construye los inputs de los fixtures de paridad del matcher.

Entrada:  stream_events.jsonl (dump crudo de stream:alerts:market)
Salida:   inputs.jsonl — casos (evento, enriched, suscripción) listos para que
          freeze_matcher_verdicts.js les congele el veredicto del código VIVO.

Estratificación (determinista, seed fija):
  - por estrategia real (user_alert_strategies) × tipo suscrito: hasta K eventos
  - controles negativos: eventos de tipos NO suscritos (debe rechazar por tipo)
  - estrategias con aq:: eventos de ese tipo en el espectro de quality (bajo/medio/alto)
  - sintéticos derivados de casos reales (etiquetados), para forzar las
    semánticas raras: rango invertido, valor ausente en modo estricto, aq±

El enriched de cada evento es su `context` congelado en market_events
(el enriched del símbolo en el instante del disparo) — el sustituto más fiel
del enrichedCache que vio el websocket.

Uso (en el host, desde services/backtester/parity/):
    python3 build_fixture_inputs.py stream_events.jsonl inputs.jsonl
"""
from __future__ import annotations

import json
import random
import subprocess
import sys
from collections import defaultdict

K_PER_TYPE = 3
K_NEGATIVE = 3
K_AQ_SPECTRUM = 3
K_SYNTH_BASE = 12

PSQL = [
    "docker", "exec", "-i", "tradeul_timescale",
    "psql", "-U", "tradeul_user", "-d", "tradeul", "-At",
]


def psql_json(sql: str) -> list:
    out = subprocess.run(PSQL + ["-c", sql], capture_output=True, text=True, check=True)
    return [json.loads(line) for line in out.stdout.splitlines() if line.strip()]


def fetch_contexts(ids: list, ts_min: str, ts_max: str) -> dict:
    """context jsonb por id, vía VALUES + join sobre la PK (id, ts)."""
    values = ",".join("('" + i.replace("'", "''") + "')" for i in ids)
    sql = (
        "WITH ids(id) AS (VALUES " + values + ") "
        "SELECT row_to_json(t) FROM ("
        "SELECT m.id, m.context FROM market_events m JOIN ids i ON m.id = i.id "
        f"WHERE m.ts >= '{ts_min}'::timestamptz - interval '1 hour' "
        f"AND m.ts <= '{ts_max}'::timestamptz + interval '1 hour'"
        ") t;"
    )
    out = subprocess.run(PSQL + ["-q", "-f", "-"], input=sql, capture_output=True, text=True, check=True)
    ctx = {}
    for line in out.stdout.splitlines():
        if line.strip():
            row = json.loads(line)
            ctx[row["id"]] = row["context"] or {}
    return ctx


def main() -> None:
    stream_path, out_path = sys.argv[1], sys.argv[2]
    rng = random.Random(20260802)

    events = []
    with open(stream_path) as f:
        for line in f:
            events.append(json.loads(line)["fields"])
    by_type: dict = defaultdict(list)
    for e in events:
        by_type[e["event_type"]].append(e)
    for lst in by_type.values():
        lst.sort(key=lambda e: e.get("id", ""))
    all_types = sorted(by_type)
    print(f"stream: {len(events)} eventos, {len(all_types)} tipos", file=sys.stderr)

    strategies = psql_json(
        "SELECT row_to_json(t) FROM (SELECT id, name, event_types, filters "
        "FROM user_alert_strategies ORDER BY id) t"
    )
    print(f"estrategias: {len(strategies)}", file=sys.stderr)

    cases = []

    def add_case(origin, strategy, evt, mutation=None, sub_override=None):
        filters = dict(strategy["filters"] or {})
        if sub_override:
            filters.update(sub_override)
        cases.append({
            "case_id": f"c{len(cases):05d}",
            "origin": origin,
            "mutation": mutation,
            "strategy_id": strategy["id"],
            "strategy_name": strategy["name"],
            "sub_data": {"event_types": strategy["event_types"] or [], **filters},
            "event_fields": evt,
        })

    for s in strategies:
        subscribed = [t for t in (s["event_types"] or []) if t in by_type]
        for t in subscribed:
            for evt in rng.sample(by_type[t], min(K_PER_TYPE, len(by_type[t]))):
                add_case("real", s, evt)
        # controles negativos: tipos que la estrategia NO pide
        others = [t for t in all_types if t not in set(s["event_types"] or [])]
        for t in rng.sample(others, min(K_NEGATIVE, len(others))):
            add_case("real_negative_type", s, rng.choice(by_type[t]))
        # espectro de quality para cada aq:
        for key in (s["filters"] or {}):
            if key.startswith("aq:"):
                t = key[3:]
                if t in by_type:
                    pool = sorted(by_type[t], key=lambda e: float(e.get("quality", 0)))
                    idxs = sorted({0, len(pool) // 2, len(pool) - 1})
                    for i in idxs[:K_AQ_SPECTRUM]:
                        add_case("real_aq_spectrum", s, pool[i])

    # ── sintéticos: mismas parejas reales, semánticas raras forzadas ──
    real_cases = [c for c in cases if c["origin"] == "real"]
    for base in rng.sample(real_cases, min(K_SYNTH_BASE, len(real_cases))):
        s = next(x for x in strategies if x["id"] == base["strategy_id"])
        evt = dict(base["event_fields"])
        price = float(evt.get("price", 0) or 0)
        if price > 0:
            # rango invertido que PASA (v >= lo) y que FALLA (fuera por ambos lados)
            add_case("synthetic", s, evt, "inverted_range_pass",
                     {"min_price": round(price - 0.01, 4), "max_price": round(price - 0.02, 4)})
            add_case("synthetic", s, evt, "inverted_range_fail",
                     {"min_price": round(price + 5, 4), "max_price": round(max(price - 5, 0.01), 4)})
        # modo estricto: filtro activo + valor ausente ⇒ descarta
        evt_nocap = {k: v for k, v in evt.items() if k != "market_cap"}
        add_case("synthetic", s, evt_nocap, "strict_missing_value", {"min_market_cap": 1})
        # aq: justo por encima / por debajo de la quality real
        q = float(evt.get("quality", 0) or 0)
        t = evt["event_type"]
        add_case("synthetic", s, evt, "aq_below_pass", {f"aq:{t}": max(q - 1, 0)})
        add_case("synthetic", s, evt, "aq_above_fail", {f"aq:{t}": q + 1})

    # ── contexts para los ids usados ──
    used_ids = sorted({c["event_fields"]["id"] for c in cases if "id" in c["event_fields"]})
    ts_values = sorted(e["timestamp"] for e in events if "timestamp" in e)
    contexts = fetch_contexts(used_ids, ts_values[0], ts_values[-1]) if used_ids else {}
    print(f"contexts recuperados: {len(contexts)}/{len(used_ids)}", file=sys.stderr)

    n_ctx = 0
    with open(out_path, "w") as f:
        for c in cases:
            enriched = contexts.get(c["event_fields"].get("id"))
            if c.get("mutation") == "strict_missing_value" and enriched:
                enriched = {k: v for k, v in enriched.items() if k != "market_cap"}
            c["enriched"] = enriched
            n_ctx += 1 if enriched else 0
            f.write(json.dumps(c, ensure_ascii=False) + "\n")

    types_covered = sorted({c["event_fields"]["event_type"] for c in cases})
    print(f"casos: {len(cases)} ({n_ctx} con enriched) · tipos cubiertos: {len(types_covered)}",
          file=sys.stderr)


if __name__ == "__main__":
    main()
