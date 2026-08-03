#!/usr/bin/env python3
"""Vuelca stream:alerts:market entero a JSONL (stdout).

Se ejecuta DENTRO de un contenedor con la lib redis y las env REDIS_*:
    docker exec -i tradeul_alert_worker_0 python3 - < extract_stream_events.py > stream_events.jsonl

Cada línea: {"stream_id": "...", "fields": {campo: valor_string, ...}}
Los valores son los strings crudos del wire — exactamente lo que ve el
websocket_server. No convertir tipos aquí.
"""
import json
import os

import redis

r = redis.Redis(
    host=os.environ.get("REDIS_HOST", "redis"),
    port=int(os.environ.get("REDIS_PORT", "6379")),
    password=os.environ.get("REDIS_PASSWORD"),
    decode_responses=True,
)

for stream_id, fields in r.xrange("stream:alerts:market", "-", "+"):
    print(json.dumps({"stream_id": stream_id, "fields": fields}, ensure_ascii=False))
