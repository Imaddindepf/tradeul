#!/usr/bin/env python3
"""
Tradeul Replay — demo local: chart + Level 2 + Time & Sales contra UN reloj.

Reutiliza el backend del l2demo (descarga por venue con caché, saneado DBN,
conflación) importándolo, sin tocarlo. Añade:

  · Guardia de gasto: por defecto (spend=0) SOLO se sirve lo que ya está en
    .cache/. Databento factura cada petición nueva; aquí no se paga nada sin
    que el usuario lo active explícitamente.
  · /api/cached      — cuántas de las peticiones de una ventana están en caché.
  · /api/cache_windows — inventario de ventanas ya pagadas (se deduce del
    primer timestamp de cada CSV y se confirma con la misma sha1 del l2demo).

Uso:  python3 replay_demo/server.py 8791
"""
import os, sys, json, csv, io, glob, hashlib, mimetypes, threading, traceback, urllib.parse
import importlib.util
from datetime import datetime, timedelta, timezone
from http.server import ThreadingHTTPServer, BaseHTTPRequestHandler

HERE = os.path.dirname(os.path.abspath(__file__))
L2DIR = os.path.join(os.path.dirname(HERE), "l2demo")
sys.path.insert(0, L2DIR)                      # para que l2demo importe dbn_sanitize

_spec = importlib.util.spec_from_file_location("l2srv", os.path.join(L2DIR, "server.py"))
l2 = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(l2)

try:
    from zoneinfo import ZoneInfo
    ET = ZoneInfo("America/New_York")
except Exception:
    ET = timezone(timedelta(hours=-4))

# ---------------------------------------------------------------- guardia de gasto
# build_window lanza sus fetch en un ThreadPoolExecutor interno, así que la
# señal "no gastes" tiene que ser global. Un lock serializa las cargas (demo
# local: una a la vez) para que la señal no se pise entre peticiones.
BUILD_LOCK = threading.Lock()
SPEND_OK = False
MISSES = set()          # datasets que faltaban en caché durante la última carga

_orig_fetch = l2.fetch_range

def fetch_guarded(dataset, symbol, schema, s_iso, e_iso):
    sym = l2.venue_symbol(dataset, symbol)
    key = hashlib.sha1("|".join([dataset, sym, schema, s_iso, e_iso]).encode()).hexdigest()
    path = os.path.join(l2.CACHE, key + ".csv")
    if os.path.exists(path):
        with open(path) as f:
            return f.read(), True
    if not SPEND_OK:
        MISSES.add(dataset)
        return "", True         # cached=True: que el payload no marque "nuevo"
    return _orig_fetch(dataset, symbol, schema, s_iso, e_iso)

l2.fetch_range = fetch_guarded


def build_guarded(symbol, start_utc, minutes, schema, tape, spend, progress=None):
    global SPEND_OK
    with BUILD_LOCK:
        SPEND_OK = bool(spend)
        MISSES.clear()
        try:
            payload = l2.build_window(symbol, start_utc, minutes, schema, tape, progress=progress)
            lab = dict(l2.VENUES)
            payload["misses"] = sorted(lab.get(ds, ds) for ds in MISSES)
            payload["spend"] = bool(spend)
            return payload
        finally:
            SPEND_OK = False


# ---------------------------------------------------------------- trabajos (async)
JOBS = {}
JLOCK = threading.Lock()

def start_job(symbol, start_utc, minutes, schema, tape, spend):
    jid = hashlib.sha1(os.urandom(8)).hexdigest()[:12]
    with JLOCK:
        JOBS[jid] = {"done": 0, "total": 30, "venue": "", "ready": False,
                     "error": None, "payload": None}

    def run():
        def prog(d, t, labv):
            with JLOCK:
                j = JOBS.get(jid)
                if j:
                    j["done"], j["total"], j["venue"] = d, t, labv
        try:
            p = build_guarded(symbol, start_utc, minutes, schema, tape, spend, progress=prog)
            with JLOCK:
                JOBS[jid]["payload"], JOBS[jid]["ready"] = p, True
        except Exception as e:
            traceback.print_exc()
            with JLOCK:
                JOBS[jid]["error"], JOBS[jid]["ready"] = str(e)[:300], True

    threading.Thread(target=run, daemon=True).start()
    return jid


# ---------------------------------------------------------------- pasado (velas 1 s)
# El gráfico necesita historia DETRÁS del instante de arranque para que el rango
# visible nazca lleno, no vacío llenándose. Eso NO se pide a los 15 feeds por
# plaza (serían euros por unas horas): se pide al consolidado en velas de 1 s,
# que para una sesión entera cuesta ~0,009 $. Cada ventana pide en su moneda.
# EQUS.MINI parecía la elección obvia (es la consolidación propia de Databento),
# pero NO trae las operaciones fuera de mercado. Medido en el premarket de NVDA
# del 1-jul: EQUS.MINI 193 velas de 1 s frente a 8.863 de XNAS.BASIC — 46 veces
# menos. El premarket lo dominan los cruces off-exchange, que reporta FINRA, y
# XNAS.BASIC sí incluye esos publicadores (FINC/FINN) además de la familia
# Nasdaq. Con EQUS.MINI el gráfico salía como cuatro puntos sueltos.
# Día completo: 0,024 $ frente a 0,009 $. Merece la pena de largo.
HIST_DATASET = "XNAS.BASIC"


def parse_ohlcv(txt):
    """CSV de ohlcv-1s -> [[ts_ms, o, h, l, c, v], ...] ascendente."""
    if not txt.strip():
        return []
    out = []
    for row in csv.DictReader(io.StringIO(txt)):
        try:
            ts = int(row["ts_event"])
            # price() escala 1e-9 y filtra el centinela; to_tick() NO escala
            # (eso lo hace sanitize_row). Confundirlos convierte 193,74 en 1,9e-7.
            o = l2.dbn.to_tick(l2.dbn.price(row["open"]))
            h = l2.dbn.to_tick(l2.dbn.price(row["high"]))
            lo = l2.dbn.to_tick(l2.dbn.price(row["low"]))
            c = l2.dbn.to_tick(l2.dbn.price(row["close"]))
            v = int(row["volume"])
        except Exception:
            continue
        # Volumen 0 = NO hubo operación en ese segundo. Esas filas existen en
        # XNAS.BASIC con precios rancios (se repetía 200,09 con el mercado a
        # 197) y, si se dejan pasar, marcan máximos que nunca se negociaron.
        # Una vela sin volumen no puede fijar el rango: se descarta entera.
        if None in (o, h, lo, c) or v <= 0 or not l2.dbn.is_quotable(c, v):
            continue
        out.append([ts // 1_000_000, o, h, lo, c, v])
    out.sort(key=lambda r: r[0])
    return out


def fetch_history(symbol, start_utc, session_open_utc, spend):
    """Velas de 1 s desde la apertura de sesión hasta el arranque del replay."""
    global SPEND_OK
    if session_open_utc >= start_utc:
        return [], True
    s_iso = session_open_utc.strftime("%Y-%m-%dT%H:%M:%SZ")
    e_iso = start_utc.strftime("%Y-%m-%dT%H:%M:%SZ")
    with BUILD_LOCK:
        SPEND_OK = bool(spend)
        MISSES.clear()
        try:
            txt, _ = l2.fetch_range(HIST_DATASET, symbol, "ohlcv-1s", s_iso, e_iso)
            falta = HIST_DATASET in MISSES
        finally:
            SPEND_OK = False
    return parse_ohlcv(txt), not falta


# ---------------------------------------------------------------- sondas de caché
def window_iso(start_utc, minutes):
    warm = start_utc - timedelta(seconds=l2.WARMUP_SEC)
    end = start_utc + timedelta(minutes=minutes)
    return warm.strftime("%Y-%m-%dT%H:%M:%SZ"), end.strftime("%Y-%m-%dT%H:%M:%SZ")


def cached_counts(symbol, start_utc, minutes, schema, tape):
    s_iso, e_iso = window_iso(start_utc, minutes)
    schemas = [schema] + (["trades"] if tape else [])
    hits = total = 0
    missing = []
    for ds, labv in l2.VENUES:
        sym = l2.venue_symbol(ds, symbol)
        for sch in schemas:
            key = hashlib.sha1("|".join([ds, sym, sch, s_iso, e_iso]).encode()).hexdigest()
            total += 1
            if os.path.exists(os.path.join(l2.CACHE, key + ".csv")):
                hits += 1
            else:
                missing.append(labv)
    return {"hits": hits, "total": total, "missing": sorted(set(missing))}


_WINDOWS_CACHE = {"stamp": None, "data": None}

def cache_windows(extra_symbol=None):
    """Inventario de ventanas ya pagadas. Deduce el arranque por el primer ts
    de cada CSV y lo confirma con la MISMA fórmula de clave que el l2demo."""
    files = glob.glob(os.path.join(l2.CACHE, "*.csv"))
    stamp = (len(files), max((os.path.getmtime(f) for f in files), default=0), extra_symbol)
    if _WINDOWS_CACHE["stamp"] == stamp:
        return _WINDOWS_CACHE["data"]

    names = {os.path.basename(f)[:-4] for f in files}
    secs = set()
    for f in files:
        try:
            with open(f) as fh:
                fh.readline()
                row = fh.readline()
                if row.strip():
                    secs.add(int(row.split(",")[0]) // 1_000_000_000)
        except Exception:
            pass
    clusters = []
    for s in sorted(secs):
        if not clusters or s - clusters[-1] > 3:
            clusters.append(s)

    syms = ["NVDA", "BJDX", "TSLA", "AAPL", "SPY", "CRWV", "META", "AMD", "AMZN", "QQQ"]
    if extra_symbol and extra_symbol not in syms:
        syms.append(extra_symbol)

    out = []
    for c in clusters:
        for k in range(0, 6):
            warm = datetime.fromtimestamp(c - k, tz=timezone.utc)
            s_iso = warm.strftime("%Y-%m-%dT%H:%M:%SZ")
            for mins in (1, 5, 15, 30, 60, 120):
                e_iso = (warm + timedelta(seconds=l2.WARMUP_SEC, minutes=mins)).strftime("%Y-%m-%dT%H:%M:%SZ")
                for sym in syms:
                    for sch in ("mbp-1", "bbo-1s"):
                        hq = sum(1 for ds, _ in l2.VENUES
                                 if hashlib.sha1("|".join([ds, l2.venue_symbol(ds, sym), sch, s_iso, e_iso]).encode()).hexdigest() in names)
                        if hq < 12:
                            continue
                        ht = sum(1 for ds, _ in l2.VENUES
                                 if hashlib.sha1("|".join([ds, l2.venue_symbol(ds, sym), "trades", s_iso, e_iso]).encode()).hexdigest() in names)
                        start_user = warm + timedelta(seconds=l2.WARMUP_SEC)
                        et = start_user.astimezone(ET)
                        out.append({"symbol": sym, "schema": sch, "minutes": mins,
                                    "date": et.strftime("%Y-%m-%d"), "time": et.strftime("%H:%M:%S"),
                                    "quotes": hq, "trades": ht, "totalVenues": len(l2.VENUES)})
    # dedup (una misma ventana matchea con varios k)
    seen, uniq = set(), []
    for w in out:
        key = (w["symbol"], w["schema"], w["minutes"], w["date"], w["time"])
        if key not in seen:
            seen.add(key)
            uniq.append(w)
    uniq.sort(key=lambda w: (w["date"], w["time"], w["minutes"]))
    _WINDOWS_CACHE["stamp"], _WINDOWS_CACHE["data"] = stamp, uniq
    return uniq


# ---------------------------------------------------------------- HTTP
def parse_common(q):
    symbol = q.get("symbol", ["NVDA"])[0].upper().strip()
    date = q.get("date", ["2026-07-01"])[0]
    tm = q.get("time", ["09:35:00"])[0]
    if len(tm) == 5:
        tm += ":00"
    minutes = max(1, min(120, int(q.get("minutes", ["5"])[0])))
    schema = q.get("schema", ["mbp-1"])[0]
    if schema not in ("mbp-1", "bbo-1s"):
        schema = "mbp-1"
    tape = q.get("tape", ["1"])[0] != "0"
    spend = q.get("spend", ["0"])[0] == "1"
    naive = datetime.strptime(date + " " + tm, "%Y-%m-%d %H:%M:%S")
    if naive.weekday() >= 5:
        raise ValueError("fin de semana: mercado cerrado")
    start_utc = naive.replace(tzinfo=ET).astimezone(timezone.utc)
    return symbol, start_utc, minutes, schema, tape, spend


class Handler(BaseHTTPRequestHandler):
    def log_message(self, *a):
        pass

    def _send(self, code, body, ctype="application/json", cache="no-store"):
        data = body if isinstance(body, bytes) else body.encode()
        self.send_response(code)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(data)))
        self.send_header("Cache-Control", cache)
        self.end_headers()
        self.wfile.write(data)

    def do_GET(self):
        u = urllib.parse.urlparse(self.path)
        q = urllib.parse.parse_qs(u.query)
        try:
            if u.path in ("/", "/index.html"):
                with open(os.path.join(HERE, "index.html"), "rb") as f:
                    return self._send(200, f.read(), "text/html; charset=utf-8")

            if u.path == "/api/health":
                return self._send(200, json.dumps({"ok": True, "venues": l2.LABELS,
                                                   "key": bool(l2.KEY)}))

            if u.path == "/api/cache_windows":
                sym = q.get("symbol", [None])[0]
                return self._send(200, json.dumps({"ok": True, "windows": cache_windows(sym)}))

            if u.path == "/api/cached":
                symbol, start_utc, minutes, schema, tape, _ = parse_common(q)
                c = cached_counts(symbol, start_utc, minutes, schema, tape)
                return self._send(200, json.dumps({"ok": True, **c}))

            if u.path == "/api/history":
                symbol, start_utc, minutes, schema, tape, spend = parse_common(q)
                # apertura de sesión (o premarket si lo piden) del MISMO día ET
                et_day = start_utc.astimezone(ET)
                oh, om = (4, 0) if q.get("pre", ["0"])[0] == "1" else (9, 30)
                open_utc = et_day.replace(hour=oh, minute=om, second=0,
                                          microsecond=0).astimezone(timezone.utc)
                bars, ok = fetch_history(symbol, start_utc, open_utc, spend)
                return self._send(200, json.dumps({
                    "ok": True, "cached": ok, "bars": bars,
                    "openUtc": open_utc.strftime("%Y-%m-%dT%H:%M:%SZ")},
                    separators=(",", ":")))

            if u.path == "/api/cost":
                symbol, start_utc, minutes, schema, tape, _ = parse_common(q)
                usd = l2.estimate_cost(symbol, start_utc, minutes, schema, tape)
                return self._send(200, json.dumps({"ok": True, "usd": usd}))

            if u.path == "/api/start":
                symbol, start_utc, minutes, schema, tape, spend = parse_common(q)
                jid = start_job(symbol, start_utc, minutes, schema, tape, spend)
                return self._send(200, json.dumps({"ok": True, "job": jid}))

            if u.path == "/api/progress":
                jid = q.get("job", [""])[0]
                with JLOCK:
                    j = JOBS.get(jid)
                    if not j:
                        return self._send(200, json.dumps({"ok": False, "error": "job desconocido"}))
                    return self._send(200, json.dumps({"ok": True, "done": j["done"],
                                                       "total": j["total"], "venue": j["venue"],
                                                       "ready": j["ready"], "error": j["error"]}))

            if u.path == "/api/result":
                jid = q.get("job", [""])[0]
                with JLOCK:
                    j = JOBS.pop(jid, None)
                if not j:
                    return self._send(200, json.dumps({"ok": False, "error": "job desconocido"}))
                if j["error"]:
                    return self._send(200, json.dumps({"ok": False, "error": j["error"]}))
                return self._send(200, json.dumps(j["payload"], separators=(",", ":")))

            if u.path == "/api/replay":       # síncrono, para el encadenado
                symbol, start_utc, minutes, schema, tape, spend = parse_common(q)
                payload = build_guarded(symbol, start_utc, minutes, schema, tape, spend)
                return self._send(200, json.dumps(payload, separators=(",", ":")))

            # estáticos de /vendor (la Charting Library): confinados bajo HERE/vendor
            if u.path.startswith("/vendor/"):
                rel = urllib.parse.unquote(u.path.lstrip("/"))
                root = os.path.realpath(os.path.join(HERE, "vendor"))
                full = os.path.realpath(os.path.join(HERE, rel))
                if not full.startswith(root + os.sep):
                    return self._send(403, json.dumps({"ok": False, "error": "forbidden"}))
                if os.path.isfile(full):
                    ct = mimetypes.guess_type(full)[0] or "application/octet-stream"
                    with open(full, "rb") as f:
                        return self._send(200, f.read(), ct, cache="public, max-age=3600")
                return self._send(404, json.dumps({"ok": False, "error": "not found"}))

            return self._send(404, json.dumps({"ok": False, "error": "not found"}))
        except Exception as e:
            traceback.print_exc()
            return self._send(200, json.dumps({"ok": False, "error": str(e)[:300]}))


if __name__ == "__main__":
    port = int(sys.argv[1]) if len(sys.argv) > 1 else 8791
    print("Tradeul Replay demo  ->  http://localhost:%d" % port)
    print("caché l2demo: %s (%d ficheros)" % (l2.CACHE, len(glob.glob(os.path.join(l2.CACHE, '*.csv')))))
    ThreadingHTTPServer(("127.0.0.1", port), Handler).serve_forever()
