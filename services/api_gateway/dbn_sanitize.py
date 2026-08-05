#!/usr/bin/env python3
"""Saneado centralizado de los centinelas de Databento (DBN).

Un único sitio donde se traduce el CSV crudo de Databento a valores de Python
con `None` donde el dato no existe. Todo lo que entra al libro o a la interfaz
pasa por aquí; no hay comprobaciones sueltas campo por campo repartidas por el
resto del código.

EL PROBLEMA
-----------
La convención universal de DBN es que un campo nulo o no aplicable **no viene
vacío**: viene con el VALOR MÁXIMO DEL TIPO del campo.

    precio      -> INT64_MAX  = 9223372036854775807
    tamaño      -> UINT32_MAX = 4294967295
    marca de t. -> UINT64_MAX = 18446744073709551615

POR QUÉ MUERDE JUSTO EN CSV
---------------------------
`batch.submit_job` tiene `pretty_px` y `pretty_ts` a FALSE por defecto, y el
codificador CSV de dbn sólo sustituye el centinela por cadena vacía cuando la
bandera correspondiente está a TRUE (rust/dbn/src/encode/csv/serialize.rs):

    pub fn write_px_field<W, const PRETTY_PX: bool>(w, px) {
        if PRETTY_PX {
            if px == UNDEF_PRICE { w.write_field("") } else { w.write_field(fmt_px(px)) }
        } else {
            w.write_field(itoa::Buffer::new().format(px))     // <-- centinela crudo
        }
    }

`write_ts_field` hace lo mismo (y además vacía el 0). Los tamaños **no se
vacían nunca**, ni en modo pretty ni fuera de él. Conclusión: con los ajustes
por defecto los centinelas llegan como enteros literales, y si se escalan por
1e-9 sin filtrarlos sale un precio de 9.223.372.036,85 que gana el toque y
revienta el spread.

Medido en nuestra propia caché (697.420 filas mbp-1): el centinela aparece 17
veces en `ask_px_00` y 8 en `bid_px_00`. Sólo en valores poco líquidos, donde
hay venues con una pata del libro vacía; en los muy líquidos no se ve nunca.
"""

import re

# --------------------------------------------------------------- centinelas
UNDEF_PRICE            = 9223372036854775807      # INT64_MAX
UNDEF_ORDER_SIZE       = 4294967295               # UINT32_MAX
UNDEF_TIMESTAMP        = 18446744073709551615     # UINT64_MAX
UNDEF_STAT_QUANTITY_V3 = 9223372036854775807      # INT64_MAX  (DBN v3)
UNDEF_STAT_QUANTITY_V1 = 2147483647               # INT32_MAX  (DBN v1 y v2)

DBN_VERSION = 3          # versión que sirve la API hoy

PRICE_SCALE = 1_000_000_000       # punto fijo 1e-9
PRICE_DECIMALS = 4                # el tick mínimo de renta variable US es 1e-4

# Cota de cordura para un precio de renta variable. No es un centinela de DBN:
# es la segunda barrera, por si algún día aparece un valor absurdo que no sea
# exactamente INT64_MAX. El centinela escalado (9.223.372.036,85) queda muy por
# encima; el precio de una acción, muy por debajo.
MAX_PLAUSIBLE_PRICE = 1_000_000.0


# ------------------------------------------------------------------ banderas
# `flags` es un CAMPO DE BITS. Se comprueba SIEMPRE con AND, nunca con ==.
#
# El bit 1 (F_PUBLISHER_SPECIFIC) se enciende y se apaga dentro del mismo
# stream, así que `flags == 128` falla en cuanto aparece: los ejemplos de la
# propia documentación de snapshots MBO de Databento traen registros "last"
# normales con flags = 130, no 128.
#
# Medido sobre nuestra caché: `flags` toma los valores 128, 130, 192, 64 y 0.
# `flags == 128` se dejaría fuera 251.702 filas con flags = 192 (LAST|TOB) y
# 81 con flags = 130 (LAST|PUBLISHER_SPECIFIC). `flags & 128` las coge todas.
F_LAST               = 1 << 7    # 128 · último registro del evento para ese instrumento
F_TOB                = 1 << 6    #  64 · registro de tope de libro, no una orden suelta
F_SNAPSHOT           = 1 << 5    #  32 · procede de un replay (servidor de snapshots)
F_MBP                = 1 << 4    #  16 · nivel de precio agregado, no una orden suelta
F_BAD_TS_RECV        = 1 << 3    #   8 · `ts_recv` poco fiable (reloj o reordenación)
F_MAYBE_BAD_BOOK     = 1 << 2    #   4 · hueco irrecuperable detectado en el canal
F_PUBLISHER_SPECIFIC = 1 << 1    #   2 · evento propio del publicador

FLAG_NAMES = [
    (F_LAST, "LAST"), (F_TOB, "TOB"), (F_SNAPSHOT, "SNAPSHOT"), (F_MBP, "MBP"),
    (F_BAD_TS_RECV, "BAD_TS_RECV"), (F_MAYBE_BAD_BOOK, "MAYBE_BAD_BOOK"),
    (F_PUBLISHER_SPECIFIC, "PUBLISHER_SPECIFIC"),
]


def has_flag(flags, mask):
    """Comprueba un bit de `flags`. La ÚNICA forma correcta de mirar el campo.

    Nunca `flags == F_LAST`: los demás bits conviven con él.
    """
    if flags is None:
        return False
    return bool(int(flags) & mask)


def flag_names(flags):
    """Lista legible de los bits encendidos (para depurar y para los tests)."""
    if flags is None:
        return []
    f = int(flags)
    return [name for bit, name in FLAG_NAMES if f & bit]


# -------------------------------------------------------------------- acciones
# Valores y semántica del enum Action de DBN (rust/dbn/src/enums.rs).
A_MODIFY = "M"      # "An existing order was modified: price and/or size."
A_TRADE  = "T"      # "An aggressing order traded. Does not affect the book."
A_FILL   = "F"      # "An existing order was filled. Does not affect the book."
A_CANCEL = "C"      # "An order was fully or partially cancelled."
A_ADD    = "A"      # "A new order was added to the book."
A_CLEAR  = "R"      # "Reset the book; clear all orders for an instrument."
A_NONE   = "N"      # "Has no effect on the book, but may carry flags..."

BOOK_APPLY = "apply"    # el registro actualiza el libro
BOOK_SKIP  = "skip"     # el registro NO toca el libro
BOOK_CLEAR = "clear"    # vaciar el libro de ese instrumento/publicador

_BOOK_EFFECT = {
    A_MODIFY: BOOK_APPLY,
    A_CANCEL: BOOK_APPLY,
    A_ADD:    BOOK_APPLY,
    A_TRADE:  BOOK_SKIP,
    A_FILL:   BOOK_SKIP,
    A_NONE:   BOOK_SKIP,
    A_CLEAR:  BOOK_CLEAR,
}


def book_effect(action):
    """Qué hay que hacer con este registro en el libro.

    `action is None` significa que el esquema NO TRAE columna `action`, y eso
    no es lo mismo que la acción None ('N'): `BboMsg` (bbo-1s, cbbo-1s) no
    tiene ese campo — donde MboMsg y Mbp1Msg llevan `action: c_char`, BboMsg
    lleva un `_reserved: u8`. Un registro BBO es una foto del tope de libro y
    hay que APLICARLO. Confundirlo con 'N' dejaría el modo "1 seg" del montaje
    completamente vacío.

    Una acción desconocida se aplica, no se descarta en silencio: es
    preferible pintar de más que perder el libro entero por un valor nuevo.
    """
    if action is None or action == "":
        return BOOK_APPLY
    return _BOOK_EFFECT.get(action, BOOK_APPLY)


# ------------------------------------------------- clasificación de los campos
# El centinela depende del TIPO del campo, así que lo primero es saber de qué
# tipo es cada columna. Se hace por nombre, una vez, y no en cada uso.
KIND_PRICE     = "price"
KIND_SIZE      = "size"
KIND_TIMESTAMP = "timestamp"
KIND_STAT_QTY  = "stat_qty"
KIND_FLAGS     = "flags"
KIND_CHAR      = "char"
KIND_INT       = "int"
KIND_TEXT      = "text"

# Campos de precio con nombre propio (no acaban en _price ni llevan _px).
_PRICE_NAMES = frozenset((
    "price", "ref_price", "auction_interest_price", "cont_book_clr_price",
    "auct_interest_clr_price", "ssr_filling_price", "ind_match_price",
    "upper_collar", "lower_collar", "max_price_variation",
    "min_price_increment_amount", "price_ratio", "unit_of_measure_qty",
    "display_factor",
))

# Marcas de tiempo con nombre propio, que no empiezan por `ts_`.
_TS_NAMES = frozenset(("expiration", "activation", "auction_time"))

# TRAMPA: `ts_in_delta` empieza por `ts_` pero NO es una marca de tiempo. Es un
# i32 con el desfase en nanosegundos entre la captura y la publicación. Medido
# en la caché, su máximo absoluto es 1.341.907 ns: tratarlo como u64 y
# compararlo con UINT64_MAX no rompe nada hoy, pero es un tipo distinto y no
# tiene por qué comportarse igual mañana.
_NOT_TS = frozenset(("ts_in_delta",))

_RE_LEVEL_PX = re.compile(r"^(bid|ask)_px_\d+$")
_RE_LEVEL_SZ = re.compile(r"^(bid|ask)_(sz|ct)_\d+$")

_INT_NAMES = frozenset((
    "rtype", "publisher_id", "instrument_id", "depth", "sequence",
    "ts_in_delta", "channel_id", "order_id", "priority",
))


def classify(name):
    """Tipo del campo a partir de su nombre. El resultado se cachea."""
    kind = _KIND_CACHE.get(name)
    if kind is None:
        kind = _classify(name)
        _KIND_CACHE[name] = kind
    return kind


def _classify(name):
    if name == "flags":
        return KIND_FLAGS
    if name in ("action", "side", "instrument_class", "stat_type",
                "update_action", "security_update_action"):
        return KIND_CHAR
    if name in _INT_NAMES:
        return KIND_INT
    if name in _TS_NAMES or (name.startswith("ts_") and name not in _NOT_TS):
        return KIND_TIMESTAMP
    if name in _PRICE_NAMES or name.endswith("_price") or _RE_LEVEL_PX.match(name) \
            or name.endswith("_px"):
        return KIND_PRICE
    if name == "quantity":
        return KIND_STAT_QTY
    if name == "size" or name.endswith("_qty") or _RE_LEVEL_SZ.match(name) \
            or name.endswith("_sz") or name.endswith("_ct"):
        return KIND_SIZE
    return KIND_TEXT


_KIND_CACHE = {}


# ------------------------------------------------------------- saneado por tipo
def _to_int(v):
    """Celda CSV -> int, o None si no hay número."""
    if v is None:
        return None
    if isinstance(v, int):
        return v
    s = v.strip() if isinstance(v, str) else v
    if s == "" or s is None:
        return None
    try:
        return int(s)
    except (TypeError, ValueError):
        pass
    try:
        return int(float(s))        # el modo pretty puede traer decimales
    except (TypeError, ValueError):
        return None


def price(v):
    """Precio en punto fijo 1e-9 -> float en unidades de precio, o None.

    Devuelve None sólo para el centinela y para la celda vacía. Un precio
    negativo es legítimo en DBN (spreads, algunos futuros) y se conserva: el
    filtro de "esto no es una cotización de renta variable" es cosa de
    `is_quotable`, no del saneado.
    """
    raw = _to_int(v)
    if raw is None or raw == UNDEF_PRICE:
        return None
    return round(raw / PRICE_SCALE, 9)


def to_tick(px):
    """Redondea al tick un precio YA SANEADO, es decir, uno que sale de
    `sanitize_row`, no una celda cruda.

    La distinción importa: `price()` escala por 1e-9 y `to_tick()` no. Pasarle
    a `price()` un valor que ya escaló `sanitize_row` lo divide por mil
    millones por segunda vez y convierte 193,74 en 1,93e-7. Por eso el saneado
    ocurre UNA vez, al parsear, y de ahí en adelante sólo se redondea.
    """
    return None if px is None else round(px, PRICE_DECIMALS)


def size(v):
    """Tamaño / número de órdenes (u32) -> int, o None si es el centinela."""
    raw = _to_int(v)
    if raw is None or raw == UNDEF_ORDER_SIZE:
        return None
    return raw


def timestamp(v):
    """Marca de tiempo en ns (u64) -> int, o None si es el centinela.

    El 0 también sale como None: el codificador CSV lo vacía en modo pretty
    (`0 | UNDEF_TIMESTAMP => ""`), así que las dos formas del mismo dato tienen
    que dar el mismo resultado. Una marca de tiempo de 0 es la época, no un
    instante de mercado.
    """
    raw = _to_int(v)
    if raw is None or raw == UNDEF_TIMESTAMP or raw == 0:
        return None
    return raw


def stat_quantity(v, dbn_version=DBN_VERSION):
    """Cantidad del esquema `statistics`, cuyo centinela CAMBIÓ de tipo.

    DBN v3 lo subió a i64: el centinela pasó de INT32_MAX (2.147.483.647) a
    INT64_MAX. Un lector que sólo mire el viejo se comerá el nuevo como si
    fuera una cantidad real de 9,2 trillones.
    """
    raw = _to_int(v)
    if raw is None:
        return None
    if raw == UNDEF_STAT_QUANTITY_V3:
        return None
    if dbn_version < 3 and raw == UNDEF_STAT_QUANTITY_V1:
        return None
    return raw


def _char(v):
    if v is None:
        return None
    s = v.strip() if isinstance(v, str) else v
    return s or None


def sanitize_row(row, dbn_version=DBN_VERSION):
    """LA función de saneado: fila CSV cruda -> dict tipado, con None en todo
    campo cuyo valor sea el centinela de su tipo.

    Se llama una vez por fila, en el momento de parsear, antes de que el
    registro llegue al libro o a la interfaz. Ningún consumidor vuelve a mirar
    si un valor "es 9223372036854775807".
    """
    out = {}
    for name, raw in row.items():
        if name is None:            # columnas de más: csv.DictReader las mete en None
            continue
        kind = classify(name)
        if kind == KIND_PRICE:
            out[name] = price(raw)
        elif kind == KIND_SIZE:
            out[name] = size(raw)
        elif kind == KIND_TIMESTAMP:
            out[name] = timestamp(raw)
        elif kind == KIND_STAT_QTY:
            out[name] = stat_quantity(raw, dbn_version)
        elif kind == KIND_FLAGS:
            out[name] = _to_int(raw) or 0
        elif kind == KIND_CHAR:
            out[name] = _char(raw)
        elif kind == KIND_INT:
            out[name] = _to_int(raw)
        else:
            out[name] = raw.strip() if isinstance(raw, str) else raw
    return out


def event_ts(rec):
    """Instante que ordena el registro, en ns, o None si no hay ninguno válido.

    Se usa `ts_recv` (el reloj de Databento) y no `ts_event` (el del venue):
    medido sobre 1,78 M de filas de nuestra caché, `ts_recv` viene
    estrictamente creciente mientras que `ts_event` retrocede en 411 filas,
    hasta 1,45 ms. Con `ts_event` se aplicaba un estado viejo encima de uno
    nuevo.

    Excepción: si el venue marca F_BAD_TS_RECV, él mismo está avisando de que
    su `ts_recv` no es fiable (reloj o reordenación), y ahí `ts_event` es mejor
    que un valor que sabemos malo.
    """
    ts_recv = rec.get("ts_recv")
    ts_event = rec.get("ts_event")
    if has_flag(rec.get("flags"), F_BAD_TS_RECV):
        return ts_event if ts_event is not None else ts_recv
    return ts_recv if ts_recv is not None else ts_event


# ------------------------------------------------------- agregación del libro
def is_quotable(px, sz):
    """¿Este lado de un venue es una cotización de verdad?

    Es la barrera que impide que un venue sin libro gane el toque:

      · precio None      -> centinela ya saneado, o columna ausente
      · precio <= 0      -> nivel vacío, no una cotización
      · precio absurdo   -> por si algo escapa al saneado (segunda barrera)
      · tamaño None o 0  -> nivel vacío aunque venga un precio; los tamaños
                            NO se vacían nunca en CSV, ni en modo pretty
    """
    if px is None or sz is None:
        return False
    if px <= 0 or px >= MAX_PLAUSIBLE_PRICE:
        return False
    return sz > 0


def aggregate_bbo(levels):
    """Mejor bid y mejor ask entre venues.

    `levels` es un iterable de (venue, bid_px, bid_sz, ask_px, ask_sz).

    Un precio nulo NO PUEDE ganar: los lados que no pasan `is_quotable` se
    descartan ANTES de ordenar. Es el fallo que ya nos comimos — un venue sin
    cotización daba un "mejor bid" de 9.223.372.036,85 — y por eso el filtro va
    antes del `min`/`max` y no después.

    Empata por orden de venue, igual que hace el montaje en el navegador, para
    que servidor y cliente elijan siempre el mismo.
    """
    bids, asks = [], []
    for i, (venue, bp, bs, ap, asz) in enumerate(levels):
        if is_quotable(bp, bs):
            bids.append((-bp, i, venue, bp, bs))     # -bp: el bid más alto manda
        if is_quotable(ap, asz):
            asks.append((ap, i, venue, ap, asz))
    bids.sort()
    asks.sort()

    def pack(rows, side):
        if not rows:
            return {side: None, side + "_sz": None, side + "_venues": []}
        _, _, venue, px, sz = rows[0]
        return {side: px, side + "_sz": sz,
                side + "_venues": [r[2] for r in rows if r[3] == px]}

    out = {}
    out.update(pack(bids, "bid"))
    out.update(pack(asks, "ask"))
    out["spread"] = (round(out["ask"] - out["bid"], PRICE_DECIMALS)
                     if out["bid"] is not None and out["ask"] is not None else None)
    return out
