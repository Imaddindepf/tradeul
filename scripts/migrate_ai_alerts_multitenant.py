#!/usr/bin/env python3
"""
Migración one-shot: alertas IA de single-tenant ('default') a multi-tenant.

Reasigna cada AlertSpec activa a su creador real (sub de Clerk, atribuido con
los JWT de los logs del servicio), actualiza los fires asociados y mueve los
triggers en vivo de Redis del hash triggers:active:default al hash del usuario.

Las specs archivadas (y sus fires) se quedan bajo 'default': son históricas y
no se listan. Ejecutar ANTES de desplegar el ai-agent-v4 multi-tenant, y
reiniciar el servicio después para que recargue el cache de triggers.

Uso:  python3 migrate_ai_alerts_multitenant.py [--dry-run]
"""
import json
import subprocess
import sys

DRY_RUN = "--dry-run" in sys.argv

# spec_id -> user_id de Clerk (atribución por JWT en logs del servicio)
OWNERS = {
    # israel jimenez (isracope@gmail.com)
    "011285904a9642c9a50d99cf08d9a514": "user_3FdrjrGs5Ewcpt4KeESHrrPuQBd",  # VIX/VXN 1min
    "f5e07b1f2b244f7caca7c981d24d7585": "user_3FdrjrGs5Ewcpt4KeESHrrPuQBd",  # Top 10 gappers
    "9868e56d29e54d1aaca44893c901add8": "user_3FdrjrGs5Ewcpt4KeESHrrPuQBd",  # Cruce VWAP RVOL>2
    # Imaddin Amsif (peertopeerhack@gmail.com)
    "e7fb6421adee445dbc353894ddd26fbc": "user_35yNHnXvRwQw22DDb0M5zEKcWsX",  # Spike pre-market
    "e11ba6a0533b4e2e99dd25adffd6c6d0": "user_35yNHnXvRwQw22DDb0M5zEKcWsX",  # Pierde/recupera VWAP
}

PSQL = ["docker", "exec", "-i", "tradeul_timescale",
        "psql", "-U", "tradeul_user", "-d", "tradeul", "-v", "ON_ERROR_STOP=1"]
REDIS = ["docker", "exec", "-e", "REDISCLI_AUTH=tradeul_redis_secure_2024",
         "tradeul_redis", "redis-cli", "-n", "5"]


def psql(sql: str) -> str:
    if DRY_RUN:
        print(f"[dry-run] SQL: {sql.strip()[:160]}")
        return ""
    out = subprocess.run(PSQL, input=sql, capture_output=True, text=True)
    if out.returncode != 0:
        raise RuntimeError(out.stderr)
    return out.stdout


def redis(*args: str) -> str:
    if DRY_RUN and args[0].upper() not in ("HGET", "HKEYS", "KEYS"):
        print(f"[dry-run] REDIS: {' '.join(str(a)[:60] for a in args)}")
        return ""
    out = subprocess.run(REDIS + list(args), capture_output=True, text=True)
    if out.returncode != 0:
        raise RuntimeError(out.stderr)
    return out.stdout.strip()


def main() -> None:
    # ── 1. Postgres: specs + fires ──
    for spec_id, user in OWNERS.items():
        psql(f"""
            UPDATE alert_specs
               SET user_id = '{user}',
                   spec = jsonb_set(spec, '{{user_id}}', '"{user}"')
             WHERE id = '{spec_id}';
            UPDATE alert_fires SET user_id = '{user}' WHERE spec_id = '{spec_id}';
        """)
        print(f"[pg] {spec_id[:8]} -> {user}")

    # ── 2. Redis: mover triggers en vivo al hash del usuario ──
    trigger_ids = [t for t in redis("HKEYS", "triggers:active:default").splitlines() if t]
    for tid in trigger_ids:
        raw = redis("HGET", "triggers:active:default", tid)
        if not raw:
            continue
        cfg = json.loads(raw)
        owner = OWNERS.get(cfg.get("spec_id") or "")
        if not owner:
            print(f"[redis] trigger {tid[:8]} sin dueño conocido (spec_id={cfg.get('spec_id')}) — se queda en default")
            continue
        cfg["user_id"] = owner
        redis("HSET", f"triggers:active:{owner}", tid, json.dumps(cfg))
        redis("HDEL", "triggers:active:default", tid)
        print(f"[redis] trigger {tid[:8]} -> triggers:active:{owner}")

    print("OK — reinicia tradeul_ai_agent_v4 para recargar el cache de triggers.")


if __name__ == "__main__":
    main()
