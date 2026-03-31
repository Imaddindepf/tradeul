#!/usr/bin/env python3
"""
Verifica persistencia de context en market_events vs snapshot Redis.

Uso: python3 scripts/verify_alert_context.py
"""
from __future__ import annotations

import json
import os
import subprocess
import sys

KEYS = ("avg_volume_3m", "postmarket_change_percent", "vol_1min")
REDIS_PASSWORD = os.environ.get("REDIS_PASSWORD", "tradeul_redis_secure_2024")


def fetch_events_json() -> list[dict]:
    sql = r"""
    SELECT COALESCE(json_agg(x ORDER BY x.ts DESC), '[]'::json)::text
    FROM (
      SELECT ts, symbol, context
      FROM market_events
      WHERE event_type = 'post_market_high'
        AND ts > NOW() - INTERVAL '24 hours'
      ORDER BY ts DESC
      LIMIT 80
    ) x;
    """
    cmd = [
        "docker",
        "exec",
        "tradeul_timescale",
        "psql",
        "-U",
        "tradeul_user",
        "-d",
        "tradeul",
        "-t",
        "-A",
        "-c",
        sql,
    ]
    out = subprocess.check_output(cmd, text=True, stderr=subprocess.STDOUT).strip()
    return json.loads(out)


def redis_snapshot(symbol: str) -> dict:
    import redis

    r = redis.Redis(
        host=os.environ.get("REDIS_HOST", "localhost"),
        port=int(os.environ.get("REDIS_PORT", "6379")),
        password=REDIS_PASSWORD,
        decode_responses=True,
    )
    raw = r.hget("snapshot:enriched:latest", symbol)
    if not raw:
        return {}
    return json.loads(raw)


def main() -> int:
    try:
        rows = fetch_events_json()
    except subprocess.CalledProcessError as e:
        print("psql error:", e.output)
        return 1
    except json.JSONDecodeError as e:
        print("JSON parse error:", e)
        return 1

    if not rows:
        print("No hay post_market_high en las últimas 24h.")
        return 0

    with_avg = with_pm = with_v1 = 0
    for row in rows:
        ctx = row.get("context") or {}
        if isinstance(ctx, str):
            try:
                ctx = json.loads(ctx)
            except json.JSONDecodeError:
                ctx = {}
        if ctx.get("avg_volume_3m") is not None:
            with_avg += 1
        if ctx.get("postmarket_change_percent") is not None:
            with_pm += 1
        if ctx.get("vol_1min") is not None:
            with_v1 += 1

    n = len(rows)
    print(f"Muestra: últimos {n} eventos post_market_high (24h)")
    print(f"  context con avg_volume_3m:      {with_avg}/{n}")
    print(f"  context con postmarket_change%: {with_pm}/{n}")
    print(f"  context con vol_1min:           {with_v1}/{n}")
    print()

    for row in rows[:5]:
        sym = row["symbol"]
        ctx = row.get("context") or {}
        if isinstance(ctx, str):
            try:
                ctx = json.loads(ctx)
            except json.JSONDecodeError:
                ctx = {}
        snap = redis_snapshot(sym)
        print(f"--- {sym} (ts={row.get('ts')}) ---")
        for k in KEYS:
            c = ctx.get(k)
            s = snap.get(k)
            if c is None:
                tag = "ctx_missing"
            elif s is None:
                tag = "snap_missing"
            else:
                try:
                    fc, fs = float(c), float(s)
                    tag = "OK" if abs(fc - fs) < max(1.0, abs(fs) * 0.02) else f"diff ({fc} vs {fs})"
                except (TypeError, ValueError):
                    tag = "cmp_skip"
            print(f"  {k}: context={c!r} snapshot={s!r}  [{tag}]")
        print()

    print(
        "Tras redeploy del alert engine, las nuevas alertas deberían tener "
        "context completo (merge de snapshot). Filas viejas pueden seguir incompletas."
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
