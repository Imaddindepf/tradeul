#!/usr/bin/env python3
"""
l2replay_core - nucleo del replay Level 2 por venue (Databento).
Extraido del demo local verificado; sin servidor HTTP: lo consume routes/l2replay.py.

Origen — Databento historical, montaje por venue.

Descarga bajo demanda la ventana que pide el usuario (con calentamiento previo
para que el libro no nazca vacio), la conflaciona y la sirve al navegador.

Uso:
    export DATABENTO_API_KEY='db-...'
    python3 server.py            # http://localhost:8765
"""
import os, sys, json, csv, io, time, base64, hashlib, threading, urllib.request, urllib.parse, traceback

# zstd: Databento lo recomienda para transferencia ("recommended for faster
# transfer speeds and smaller files") y factura por el binario SIN comprimir,
# asi que comprimir es gratis. CSV comprime ~10-20x.
try:
    import zstandard as _zstd
except ImportError:      # sin la libreria se degrada a sin compresion
    _zstd = None

# DBN binario nativo: el formato que Databento declara mas rapido ("For
# fastest transfer speed, \'dbn\' is recommended"). 80 B/registro frente a
# ~200+ B de CSV, y decodificador Rust. Si falta la libreria, CSV sigue.
try:
    import databento_dbn as _dbnlib
except ImportError:
    _dbnlib = None
from http.server import ThreadingHTTPServer, BaseHTTPRequestHandler
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta, timezone

import dbn_sanitize as dbn      # saneado de centinelas: TODO el CSV pasa por ahí

try:
    from zoneinfo import ZoneInfo
    ET = ZoneInfo("America/New_York")
except Exception:
    ET = timezone(timedelta(hours=-4))

HERE = os.path.dirname(os.path.abspath(__file__))
CACHE = os.environ.get("L2REPLAY_CACHE_DIR") or os.path.join(HERE, ".l2cache")
os.makedirs(CACHE, exist_ok=True)

API = "https://hist.databento.com/v0/"


def _load_key():
    k = os.environ.get("DATABENTO_API_KEY", "").strip()
    if k:
        return k
    envfile = os.path.join(HERE, ".env")          # ignorado por git
    if os.path.exists(envfile):
        with open(envfile) as f:
            for line in f:
                line = line.strip()
                if line.startswith("DATABENTO_API_KEY"):
                    return line.split("=", 1)[1].strip().strip("'\"")
    return ""


KEY = _load_key()

# dataset -> etiqueta corta que se pinta en la ventana
VENUES = [
    ("XNAS.ITCH",      "NSDQ"),
    ("ARCX.PILLAR",    "ARCA"),
    ("XNYS.PILLAR",    "NYSE"),
    ("IEXG.TOPS",      "IEX"),
    ("BATS.PITCH",     "BZX"),
    ("EDGX.PITCH",     "EDGX"),
    ("MEMX.MEMOIR",    "MEMX"),
    ("BATY.PITCH",     "BYX"),
    ("EDGA.PITCH",     "EDGA"),
    ("XPSX.ITCH",      "PSX"),
    ("XBOS.ITCH",      "BX"),
    ("EPRL.DOM",       "EPRL"),
    ("XCIS.TRADESBBO", "XCIS"),
    ("XCHI.PILLAR",    "XCHI"),
    ("XASE.PILLAR",    "AMEX"),   # NYSE American: faltaba. El ejemplo oficial de
                                  # Databento para NBBO sintético usa estos 15.
]

# Convención de símbolo POR VENUE. En acciones US el mismo valor lleva ticker
# distinto según el venue: Berkshire B es "BRK.B" en los de convención Nasdaq y
# "BRK B" en los de convención CMS. Si no se traduce, la mitad de los venues
# devuelve 404 en silencio y el montaje sale cojo sin avisar.
CMS_DATASETS = {"ARCX.PILLAR", "MEMX.MEMOIR", "XASE.PILLAR",
                "XCHI.PILLAR", "XCIS.TRADESBBO", "XNYS.PILLAR"}


def venue_symbol(dataset, symbol):
    if dataset in CMS_DATASETS:
        return symbol.replace(".", " ")
    return symbol.replace(" ", ".")


LABELS = [lab for _, lab in VENUES]
IDX = {lab: i for i, lab in enumerate(LABELS)}

WARMUP_SEC = 20          # margen previo para llenar el libro sin pintarlo
                         # (el venue más lento medido reporta en 4s)
# Peticiones INTERACTIVAS: un get_range de 1-5 min son pocos MB; si no llega
# en esto, mejor soltar el venue y que vuelva en el siguiente bloque.
FETCH_TIMEOUT = int(os.environ.get("L2REPLAY_FETCH_TIMEOUT", "25"))
BLOCK_DEADLINE = float(os.environ.get("L2REPLAY_BLOCK_DEADLINE", "30"))
CONFLATE_MS = 50         # 20 fps: mas que suficiente para el ojo


def _auth():
    if not KEY:
        raise RuntimeError("Falta DATABENTO_API_KEY en el entorno")
    return "Basic " + base64.b64encode((KEY + ":").encode()).decode()


def _post(endpoint, params, timeout=180):
    req = urllib.request.Request(
        API + endpoint,
        data=urllib.parse.urlencode(params).encode(),
        headers={"Authorization": _auth(),
                 "Content-Type": "application/x-www-form-urlencoded"})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return r.read().decode("utf-8", "replace")


def _post_bytes(endpoint, params, timeout=180):
    req = urllib.request.Request(
        API + endpoint,
        data=urllib.parse.urlencode(params).encode(),
        headers={"Authorization": _auth(),
                 "Content-Type": "application/x-www-form-urlencoded"})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return r.read()


def _get(endpoint, params, timeout=90):
    url = API + endpoint + "?" + urllib.parse.urlencode(params)
    req = urllib.request.Request(url, headers={"Authorization": _auth()})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return json.loads(r.read().decode())


RETRY_CODES = (429, 500, 503, 504)     # el resto son definitivos: no reintentar


def fetch_range(dataset, symbol, schema, start_iso, end_iso):
    """Descarga CSV de un venue, con cache en disco.

    La caché no es una optimización: Databento factura CADA peticion repetida
    ("Duplicate streaming requests will incur repeated charges"), asi que sin
    cache cada replay repetido se vuelve a pagar entero.
    """
    sym = venue_symbol(dataset, symbol)
    key = hashlib.sha1("|".join([dataset, sym, schema, start_iso, end_iso]).encode()).hexdigest()
    path = os.path.join(CACHE, key + ".csv")
    if os.path.exists(path):
        with open(path, "r") as f:
            return f.read(), True
    params = dict(dataset=dataset, symbols=sym, schema=schema,
                  start=start_iso, end=end_iso, encoding="csv", stype_in="raw_symbol")
    if _zstd is not None:
        params["compression"] = "zstd"

    txt = None
    for attempt in range(2):
        try:
            raw = _post_bytes("timeseries.get_range", params, timeout=FETCH_TIMEOUT)
            if _zstd is not None and params.get("compression") == "zstd" and raw:
                try:
                    raw = _zstd.ZstdDecompressor().stream_reader(io.BytesIO(raw)).read()
                except Exception:
                    pass          # respuesta sin comprimir (o vacia): usar tal cual
            txt = raw.decode("utf-8", "replace")
            break
        except urllib.error.HTTPError as e:
            body = e.read().decode("utf-8", "replace")[:200]
            if e.code in (404, 422):   # el simbolo no cotizaba en ese venue ese dia
                txt = ""
                break
            if e.code not in RETRY_CODES or attempt == 1:
                raise RuntimeError("%s %s: %s" % (dataset, e.code, body))
            wait = e.headers.get("Retry-After") if e.headers else None
            time.sleep(min(5.0, float(wait)) if wait and str(wait).isdigit() else 1.0)
        except Exception:
            if attempt == 1:
                raise
            time.sleep(1.0)
    if txt is None:
        raise RuntimeError("%s: sin respuesta tras 2 intentos" % dataset)
    with open(path, "w") as f:
        f.write(txt)
    return txt, False


EMPTY_BOOK = (None, 0, None, 0)     # venue sin toque en ninguna de las dos patas


def parse_quotes(txt):
    """CSV -> [(ts_ns, bid_px, bid_sz, ask_px, ask_sz)] con solo los cambios.

    Aquí NO se comprueba ningún centinela a mano: la fila entra por
    `dbn.sanitize_row` y sale con None allí donde Databento dice que no hay
    dato — precio, tamaño y marca de tiempo, cada uno con el suyo. Lo que
    queda en esta función es la semántica del libro, que es otra cosa:

    · Manda la ACCIÓN. Trade ('T'), Fill ('F') y None ('N') no tocan el libro
      —el enum Action de DBN lo dice literalmente, "Does not affect the
      book"— y Clear ('R') tira todo lo que descansa en ese libro. Aplicar
      una ejecución al libro lo movía sin que ninguna orden hubiera cambiado.
    · El libro se lleva por (instrument_id, publisher_id), que es el alcance
      exacto que borra un Clear. Un dataset puede traer más de un publicador.
    · `flags` es un campo de bits y se mira SIEMPRE con AND. F_LAST cierra el
      evento del venue: entre el primer registro y F_LAST el libro está en un
      estado transitorio que puede enseñar niveles cruzados que nunca
      existieron, así que esos registros se aplican pero no se publican.
      Medido sobre nuestra caché: las 1.651.585 filas A/C/M traen F_LAST, y
      las 100.654 que no lo traen son todas ejecuciones, que no tocan libro.
      Aun así hay red: si un feed no marcase F_LAST nunca —`BboMsg` es otro
      tipo de registro y no tiene por qué comportarse como `Mbp1Msg`— se
      publica todo, en vez de dejar el montaje vacío por una bandera que ese
      venue no usa.
    · Un estado sin ninguna pata TAMBIÉN se publica. Antes se descartaba, y
      así se quedaba en pantalla la última cotización buena de un venue que
      ya no cotiza: una cotización rancia que puede seguir ganando el toque.
    """
    if not txt.strip():
        return []
    out = []
    published, pending = {}, {}      # (instrumento, publicador) -> estado / (ts, estado)
    saw_last = False

    for row in csv.DictReader(io.StringIO(txt)):
        rec = dbn.sanitize_row(row)
        ts = dbn.event_ts(rec)
        if ts is None:               # ts_recv y ts_event, los dos centinela
            continue

        effect = dbn.book_effect(rec.get("action"))
        if effect == dbn.BOOK_SKIP:                  # T, F, N
            continue

        key = (rec.get("instrument_id"), rec.get("publisher_id"))
        if effect == dbn.BOOK_CLEAR:                 # R
            state = EMPTY_BOOK
        else:
            bp = dbn.to_tick(rec.get("bid_px_00"))
            ap = dbn.to_tick(rec.get("ask_px_00"))
            bs = rec.get("bid_sz_00") or 0
            asz = rec.get("ask_sz_00") or 0
            # Misma barrera que usa la agregación del toque: precio nulo, cero,
            # absurdo, o con tamaño 0, no es una cotización.
            if not dbn.is_quotable(bp, bs):
                bp, bs = None, 0
            if not dbn.is_quotable(ap, asz):
                ap, asz = None, 0
            state = (bp, bs, ap, asz)

        if dbn.has_flag(rec.get("flags"), dbn.F_LAST):
            saw_last = True
        elif saw_last:
            pending[key] = (ts, state)               # evento a medias: al libro sí,
            continue                                 # al stream todavía no

        pending.pop(key, None)
        if state == published.get(key):
            continue
        published[key] = state
        out.append((ts,) + state)

    for key, (ts, state) in pending.items():         # último evento sin cerrar
        if state != published.get(key):
            out.append((ts,) + state)

    out.sort(key=lambda r: r[0])
    return out


def parse_trades(txt):
    """CSV del esquema `trades` -> [(ts_ns, precio, tamaño)].

    La cinta son ejecuciones: Trade ('T') y Fill ('F'), nada más. El esquema
    `trades` hoy no trae otra cosa, pero filtrarlo aquí evita que una acción
    distinta se cuele como impresión el día que la traiga.
    """
    if not txt.strip():
        return []
    out = []
    for row in csv.DictReader(io.StringIO(txt)):
        rec = dbn.sanitize_row(row)
        act = rec.get("action")
        if act is not None and act not in (dbn.A_TRADE, dbn.A_FILL):
            continue
        ts = dbn.event_ts(rec)
        p = dbn.to_tick(rec.get("price"))
        sz = rec.get("size")
        if ts is None or not dbn.is_quotable(p, sz):
            continue
        out.append((ts, p, sz))
    return out



# ---------------------------------------------------------------------------
# Camino DBN binario nativo. La cache guarda los bytes zstd TAL CUAL llegan
# (.dbnz): minimo disco, y decodificar ~100k registros es cosa de milisegundos.
# ---------------------------------------------------------------------------

def _use_dbn():
    return (_dbnlib is not None and _zstd is not None
            and os.environ.get("L2REPLAY_ENCODING", "dbn").lower() != "csv")


def _dbn_records(data):
    dec = _dbnlib.DBNDecoder()
    dec.write(data)
    return dec.decode()


def fetch_range_dbn(dataset, symbol, schema, start_iso, end_iso):
    """Como fetch_range pero en DBN+zstd. Devuelve (records, cached)."""
    sym = venue_symbol(dataset, symbol)
    key = hashlib.sha1("|".join(["dbn", dataset, sym, schema, start_iso, end_iso]).encode()).hexdigest()
    path = os.path.join(CACHE, key + ".dbnz")
    if os.path.exists(path):
        with open(path, "rb") as f:
            raw = f.read()
        if not raw:
            return [], True
        data = _zstd.ZstdDecompressor().stream_reader(io.BytesIO(raw)).read()
        return _dbn_records(data), True
    params = dict(dataset=dataset, symbols=sym, schema=schema,
                  start=start_iso, end=end_iso,
                  encoding="dbn", compression="zstd", stype_in="raw_symbol")
    raw = None
    for attempt in range(2):
        try:
            raw = _post_bytes("timeseries.get_range", params, timeout=FETCH_TIMEOUT)
            break
        except urllib.error.HTTPError as e:
            e.read()
            if e.code in (404, 422):
                raw = b""
                break
            if e.code not in RETRY_CODES or attempt == 1:
                raise RuntimeError("%s %s (dbn)" % (dataset, e.code))
            wait = e.headers.get("Retry-After") if e.headers else None
            time.sleep(min(5.0, float(wait)) if wait and str(wait).isdigit() else 1.0)
        except Exception:
            if attempt == 1:
                raise
            time.sleep(1.0)
    if raw is None:
        raise RuntimeError("%s: sin respuesta tras 2 intentos (dbn)" % dataset)
    with open(path, "wb") as f:
        f.write(raw)
    if not raw:
        return [], True
    data = _zstd.ZstdDecompressor().stream_reader(io.BytesIO(raw)).read()
    return _dbn_records(data), False


def _rec_ts(r):
    """ts_recv y si no ts_event, ambos filtrando centinela (regla DBN)."""
    ts = getattr(r, "ts_recv", None)
    if ts is None or ts >= dbn.UNDEF_TIMESTAMP or ts <= 0:
        ts = getattr(r, "ts_event", None)
        if ts is None or ts >= dbn.UNDEF_TIMESTAMP or ts <= 0:
            return None
    return ts


def parse_quotes_dbn(records):
    """Registros MBP1 nativos -> mismas tuplas que parse_quotes (CSV).

    Mismas primitivas de dbn_sanitize (to_tick / is_quotable / book_effect /
    F_LAST con red saw_last / dedupe por (instrument, publisher)) para que la
    semantica sea EXACTAMENTE la del camino CSV probado.
    """
    out = []
    published, pending = {}, {}
    saw_last = False
    for r in records:
        if type(r).__name__ != "MBP1Msg":
            continue
        ts = _rec_ts(r)
        if ts is None:
            continue
        act = str(r.action)
        effect = dbn.book_effect(act)
        if effect == dbn.BOOK_SKIP:
            continue
        key = (r.instrument_id, r.publisher_id)
        if effect == dbn.BOOK_CLEAR:
            state = EMPTY_BOOK
        else:
            bp = dbn.price(r.bid_px_00)
            ap = dbn.price(r.ask_px_00)
            bs = dbn.size(r.bid_sz_00) or 0
            asz = dbn.size(r.ask_sz_00) or 0
            if not dbn.is_quotable(bp, bs):
                bp, bs = None, 0
            if not dbn.is_quotable(ap, asz):
                ap, asz = None, 0
            state = (bp, bs, ap, asz)
        if int(r.flags) & dbn.F_LAST:
            saw_last = True
        elif saw_last:
            pending[key] = (ts, state)
            continue
        pending.pop(key, None)
        if state == published.get(key):
            continue
        published[key] = state
        out.append((ts,) + state)
    for key, (ts, state) in pending.items():
        if state != published.get(key):
            out.append((ts,) + state)
    out.sort(key=lambda x: x[0])
    return out


def parse_trades_dbn(records):
    out = []
    for r in records:
        if type(r).__name__ not in ("TradeMsg",):
            continue
        act = str(r.action)
        if act not in (dbn.A_TRADE, dbn.A_FILL):
            continue
        ts = _rec_ts(r)
        p = dbn.price(r.price)
        sz = dbn.size(r.size) or 0
        if ts is None or not dbn.is_quotable(p, sz):
            continue
        out.append((ts, p, sz))
    return out


def trades_from_quotes_csv(txt):
    """Operaciones desde el CSV de mbp-1: las filas con action='T'.

    Verificado sobre los 15 venues: la lista resultante es IDÉNTICA a la del
    esquema `trades`, que por tanto es una petición redundante (y más cara:
    su tarifa por GB es 5x la de mbp-1).
    """
    if not txt.strip():
        return []
    out = []
    for row in csv.DictReader(io.StringIO(txt)):
        if (row.get("action") or "").strip() != dbn.A_TRADE:
            continue
        rec = dbn.sanitize_row(row)
        ts = dbn.event_ts(rec)
        p = dbn.price(row.get("price"))
        sz = dbn.size(row.get("size")) or 0
        if ts is None or not dbn.is_quotable(p, sz):
            continue
        out.append((ts, p, sz))
    return out


def trades_from_records(records):
    """Operaciones desde los registros MBP1 nativos (action='T')."""
    out = []
    for r in records:
        if type(r).__name__ != "MBP1Msg" or str(r.action) != dbn.A_TRADE:
            continue
        ts = _rec_ts(r)
        p = dbn.price(r.price)
        sz = dbn.size(r.size) or 0
        if ts is None or not dbn.is_quotable(p, sz):
            continue
        out.append((ts, p, sz))
    return out


def fetch_venue(dataset, symbol, schema, start_iso, end_iso):
    """UNA sola petición por venue -> (cotizaciones, operaciones, cached)."""
    if _use_dbn():
        recs, cached = fetch_range_dbn(dataset, symbol, schema, start_iso, end_iso)
        return parse_quotes_dbn(recs), trades_from_records(recs), cached
    txt, cached = fetch_range(dataset, symbol, schema, start_iso, end_iso)
    return parse_quotes(txt), trades_from_quotes_csv(txt), cached


def fetch_events(dataset, symbol, schema, start_iso, end_iso):
    """Punto unico de entrada: (eventos_parseados, cached) por el mejor camino."""
    if _use_dbn():
        recs, cached = fetch_range_dbn(dataset, symbol, schema, start_iso, end_iso)
        if schema == "trades":
            return parse_trades_dbn(recs), cached
        return parse_quotes_dbn(recs), cached
    txt, cached = fetch_range(dataset, symbol, schema, start_iso, end_iso)
    if schema == "trades":
        return parse_trades(txt), cached
    return parse_quotes(txt), cached


def build_window(symbol, start_dt_utc, minutes, schema, with_tape=True, progress=None, seconds=None):
    """Descarga todos los venues, mezcla y conflaciona en frames de CONFLATE_MS.

    Las 28 peticiones (14 venues x quotes+trades) salen todas a la vez, y se
    informa del avance por `progress` para que la interfaz no parezca colgada.
    """
    dur_s = int(seconds) if seconds else int(minutes) * 60
    warm = start_dt_utc - timedelta(seconds=WARMUP_SEC)
    end = start_dt_utc + timedelta(seconds=dur_s)
    s_iso = warm.strftime("%Y-%m-%dT%H:%M:%SZ")
    e_iso = end.strftime("%Y-%m-%dT%H:%M:%SZ")

    # UNA petición por venue: las operaciones vienen dentro del propio mbp-1.
    tasks = [(ds, lab) for ds, lab in VENUES]

    done = [0]

    def one(t):
        ds, lab = t
        try:
            q, tr, cached = fetch_venue(ds, symbol, schema, s_iso, e_iso)
            out = (lab, q, tr, cached, None)
        except Exception as ex:
            out = (lab, [], [], False, str(ex)[:140])
        done[0] += 1
        if progress:
            progress(done[0], len(tasks), lab)
        return out

    # TODO O NADA: se esperan los 15 venues. Un libro al que le falta un venue
    # no es un libro incompleto, es un libro FALSO: el que falta puede ser
    # justo el que estaba en el toque. El tope de espera lo ponen el timeout
    # por petición y los reintentos, no un plazo que descarte datos.
    with ThreadPoolExecutor(max_workers=len(tasks)) as ex:
        raw = list(ex.map(one, tasks))

    byven = {lab: {"q": [], "t": [], "cached": True, "err": None} for _, lab in VENUES}
    for lab, q, tr, cached, err in raw:
        slot = byven[lab]
        slot["err"] = err
        slot["q"], slot["t"] = q, tr
        if not cached:
            slot["cached"] = False

    # Un venue con error REAL invalida el bloque (todo o nada). Un venue sin
    # datos no es error: el símbolo simplemente no cotizó ahí (404 -> vacío).
    broken = {lab: byven[lab]["err"] for _, lab in VENUES if byven[lab]["err"]}
    if broken:
        raise RuntimeError("bloque incompleto: %s" % ", ".join(broken))

    results = [(lab, byven[lab]["q"], byven[lab]["t"], byven[lab]["cached"], byven[lab]["err"])
               for _, lab in VENUES]

    errors = {lab: err for lab, _, _, _, err in results if err}
    all_cached = all(c for _, _, _, c, _ in results)

    # --- estado inicial del libro al terminar el calentamiento ---
    start_ns = int(start_dt_utc.timestamp() * 1e9)
    end_ns = int(end.timestamp() * 1e9)

    book = {}          # label -> [bp, bs, ap, as]
    events = []        # (ts_ns, venue_idx, bp, bs, ap, as)
    for lab, quotes, _, _, _ in results:
        vi = IDX[lab]
        for ts, bp, bs, ap, asz in quotes:
            if ts < start_ns:
                book[lab] = [bp, bs, ap, asz]      # calentamiento: solo estado
            elif ts <= end_ns:
                events.append((ts, vi, bp, bs, ap, asz))

    trades = []
    for lab, _, tr, _, _ in results:
        vi = IDX[lab]
        for ts, p, sz in tr:
            if start_ns <= ts <= end_ns:
                trades.append((ts, p, sz, vi))
    trades.sort()

    events.sort(key=lambda x: x[0])

    # --- conflacion en cubos de CONFLATE_MS ---
    frames, bucket, cur_b = [], {}, None
    for ts, vi, bp, bs, ap, asz in events:
        b = (ts - start_ns) // (CONFLATE_MS * 1_000_000)
        if cur_b is None:
            cur_b = b
        if b != cur_b:
            if bucket:
                frames.append([cur_b * CONFLATE_MS, list(bucket.values())])
            bucket, cur_b = {}, b
        bucket[vi] = [vi, bp, bs, ap, asz]
    if bucket:
        frames.append([cur_b * CONFLATE_MS, list(bucket.values())])

    tape = [[int((ts - start_ns) / 1e6), p, sz, vi] for ts, p, sz, vi in trades]

    initial = [[IDX[l], v[0], v[1], v[2], v[3]] for l, v in book.items()]

    # Toque consolidado en el instante 0, con la barrera puesta: un venue sin
    # cotización no puede ganarlo. `/api/replay` es una superficie JSON de pleno
    # derecho —la propia interfaz la usa para encadenar bloques—, así que el
    # toque de salida lo calcula el servidor y no cada consumidor por su cuenta.
    opening = [(lab,) + tuple(book.get(lab) or EMPTY_BOOK) for lab in LABELS]
    bbo = dbn.aggregate_bbo(opening)

    return {
        "ok": True,
        "symbol": symbol,
        "schema": schema,
        "venues": LABELS,
        "startUtc": start_dt_utc.strftime("%Y-%m-%dT%H:%M:%SZ"),
        "startEt": start_dt_utc.astimezone(ET).strftime("%Y-%m-%d %H:%M:%S"),
        "durationMs": dur_s * 1000,
        "conflateMs": CONFLATE_MS,
        "initial": initial,
        "bbo": {"bid": bbo["bid"], "bidSz": bbo["bid_sz"], "bidVenues": bbo["bid_venues"],
                "ask": bbo["ask"], "askSz": bbo["ask_sz"], "askVenues": bbo["ask_venues"],
                "spread": bbo["spread"]},
        "frames": frames,
        "tape": tape,
        "cached": all_cached,
        "errors": errors,
    }


def estimate_cost(symbol, start_dt_utc, minutes, schema, with_tape=True):
    warm = start_dt_utc - timedelta(seconds=WARMUP_SEC)
    end = start_dt_utc + timedelta(minutes=minutes)
    s_iso = warm.strftime("%Y-%m-%dT%H:%M:%SZ")
    e_iso = end.strftime("%Y-%m-%dT%H:%M:%SZ")

    def one(item):
        ds, _ = item
        tot = 0.0
        for sch in (schema,):     # las operaciones vienen dentro de mbp-1
            try:
                kw = dict(dataset=ds, symbols=symbol, schema=sch, start=s_iso,
                          end=e_iso, stype_in="raw_symbol", mode="historical")
                tot += float(_get("metadata.get_cost", kw))
            except Exception:
                pass
        return tot

    with ThreadPoolExecutor(max_workers=len(VENUES)) as ex:
        return round(sum(ex.map(one, VENUES)), 4)


# ---------------------------------------------------------------- trabajos
JOBS = {}
JOBS_LOCK = threading.Lock()


def start_job(symbol, start_utc, minutes, schema, tape, seconds=None):
    jid = hashlib.sha1(("%s%s%s%s%s%s" % (symbol, start_utc, minutes, schema, tape, os.urandom(4)))
                       .encode()).hexdigest()[:12]
    with JOBS_LOCK:
        JOBS[jid] = {"done": 0, "total": len(VENUES), "venue": "",
                     "ready": False, "error": None, "payload": None}

    def run():
        def prog(d, t, lab):
            with JOBS_LOCK:
                j = JOBS.get(jid)
                if j:
                    j["done"], j["total"], j["venue"] = d, t, lab
        try:
            p = build_window(symbol, start_utc, minutes, schema, tape, progress=prog, seconds=seconds)
            with JOBS_LOCK:
                JOBS[jid]["payload"] = p
                JOBS[jid]["ready"] = True
        except Exception as e:
            traceback.print_exc()
            with JOBS_LOCK:
                JOBS[jid]["error"] = str(e)[:300]
                JOBS[jid]["ready"] = True

    threading.Thread(target=run, daemon=True).start()
    return jid


