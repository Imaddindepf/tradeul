"""
When: the agent's single reading of time in a user's question.

Sessions and dates were parsed in four separate places, each with its own list
of phrases, and they disagreed. "after hour" in the singular was understood
here and not there, so the same question was answered in full or in half
depending on which tool the selector happened to pick. Nothing errored; the
answer was simply missing a day.

So the vocabulary lives here, once. Consumers keep their own mapping — one
needs 'amc', another a column name, another a scanner category — but they all
recognise the same words. Adding a phrasing is a one-line change that every
caller inherits.

Two readings of a date coexist on purpose:

    date_reference()  -> the single date a question is *about*
    day_mentions()    -> every date it names, with its position

The second is what makes several windows possible: pairing "after hours" with
its own day needs to know where each was said.
"""
from __future__ import annotations

import re
from datetime import datetime, timedelta


_AMC_KEYWORDS = [
    "after hours", "after-hours", "afterhours",
    "after hour", "after-hour", "afterhour",
    "after the close", "after close", "post market", "post-market",
    "postmarket", "tras el cierre", "al cierre",
    "despues del cierre", "después del cierre",
]

_BMO_KEYWORDS = [
    "premarket", "pre-market", "pre market", "before the open",
    "before open", "antes de la apertura", "antes de abrir", "preapertura",
]

def _detect_time_slot(q: str) -> str | None:
    """'amc' / 'bmo' si la query acota la franja del día; None si no.

    Deliberadamente NO se matchean los códigos sueltos "amc"/"bmo": son
    tickers reales (AMC Entertainment, Bank of Montreal) y en una query
    de trading el token suelto casi siempre es el ticker. Las frases
    multi-palabra de las listas cubren la intención de franja.
    """
    ql = q.lower()
    if any(kw in ql for kw in _AMC_KEYWORDS):
        return "amc"
    if any(kw in ql for kw in _BMO_KEYWORDS):
        return "bmo"
    return None

# Referencias de día relativas, con su posición en el texto: hacen falta
# para emparejar cada franja con SU día cuando la pregunta trae varias
# ("pre market de hoy y after hours de ayer").
_WEEKDAY_NAMES = {
    "monday": 0, "lunes": 0,
    "tuesday": 1, "martes": 1,
    "wednesday": 2, "miércoles": 2, "miercoles": 2,
    "thursday": 3, "jueves": 3,
    "friday": 4, "viernes": 4,
}

_REL_DAY_RE = [
    (re.compile(r"\b(today|hoy|this morning|esta mañana|esta manana)\b"), 0),
    (re.compile(r"\b(yesterday|ayer)\b"), 1),
]


def _shift_business_days(base: datetime, back: int) -> datetime:
    """Retrocede `back` días saltando el fin de semana."""
    d = base - timedelta(days=back)
    if back:
        while d.weekday() >= 5:
            d -= timedelta(days=1)
    return d


def _slot_mentions(text: str) -> list[tuple[int, str]]:
    """(posición, franja) de cada mención de franja, en orden de aparición."""
    tl = text.lower()
    found: list[tuple[int, str]] = []
    for kws, slot in ((_AMC_KEYWORDS, "amc"), (_BMO_KEYWORDS, "bmo")):
        for kw in kws:
            start = tl.find(kw)
            while start != -1:
                found.append((start, slot))
                start = tl.find(kw, start + 1)
    found.sort()
    # Las listas contienen variantes que se solapan ("after hour" dentro de
    # "after hours"): una sola mención no debe contar dos veces.
    deduped: list[tuple[int, str]] = []
    for pos, slot in found:
        if deduped and slot == deduped[-1][1] and pos - deduped[-1][0] < 12:
            continue
        deduped.append((pos, slot))
    return deduped


# Tope de ventanas por consulta. Una pregunta legítima abarca dos o tres
# franjas; más allá de esto lo más probable es un falso positivo del parseo,
# y en todo caso el recorte se reporta en vez de aplicarse en silencio.
_MAX_WINDOWS = 6


def _day_mentions(text: str) -> list[tuple[int, str]]:
    """(posición, fecha ISO) de cada referencia de día del texto.

    Cubre las relativas ("hoy", "ayer"), los días de la semana y las fechas
    explícitas. Hace falta la posición para saber qué día acompaña a qué
    franja cuando la pregunta menciona varias.
    """
    tl = text.lower()
    today = datetime.now()
    found: list[tuple[int, str]] = []

    for rx, back in _REL_DAY_RE:
        for m in rx.finditer(tl):
            found.append((m.start(),
                          _shift_business_days(today, back).strftime("%Y-%m-%d")))

    for name, weekday in _WEEKDAY_NAMES.items():
        for m in re.finditer(r"\b" + name + r"\b", tl):
            back = (today.weekday() - weekday) % 7
            target = today if back == 0 else today - timedelta(days=back)
            found.append((m.start(), target.strftime("%Y-%m-%d")))

    for m in _ISO_DATE_RE.finditer(tl):
        try:
            target = datetime(int(m.group(1)), int(m.group(2)), int(m.group(3)))
            found.append((m.start(), target.strftime("%Y-%m-%d")))
        except ValueError:
            pass

    found.sort()
    deduped: list[tuple[int, str]] = []
    for pos, date in found:
        if deduped and date == deduped[-1][1] and pos - deduped[-1][0] < 12:
            continue
        deduped.append((pos, date))
    return deduped


def _extract_earnings_windows(text: str) -> list[tuple[str | None, str | None]]:
    """Todas las ventanas (fecha, franja) que pide la consulta.

    Antes se colapsaba a una sola y la mitad de la pregunta se perdía sin
    aviso. Ahora se resuelven los cuatro casos que aparecen de verdad:

      - varias franjas y varios días  -> cada franja con su día más cercano,
                                         y los días sueltos como día completo
      - varias franjas, un solo día   -> ese día por cada franja
      - varios días, ninguna franja   -> cada día completo
      - una sola ventana              -> lista vacía; decide la ruta de siempre
    """
    slots = _slot_mentions(text)
    days = _day_mentions(text)

    windows: list[tuple[str | None, str | None]] = []
    if slots:
        # Cada franja se queda con un día distinto mientras queden libres. La
        # cercanía a secas no basta: en "pre market de hoy, after hours de
        # ayer" el día que precede a la segunda franja está más cerca que el
        # que le corresponde, y el orden se invierte entre idiomas ("yesterday
        # after hours" lo pone delante). Repartir días libres acierta en ambos.
        claimed: set[int] = set()
        for pos, slot in slots:
            date = None
            if days:
                free = [i for i in range(len(days)) if i not in claimed]
                pool = free or list(range(len(days)))
                idx = min(pool, key=lambda i: abs(days[i][0] - pos))
                claimed.add(idx)
                date = days[idx][1]
            if (date, slot) not in windows:
                windows.append((date, slot))
        # Un día que no acompaña a ninguna franja se pide entero: "los
        # earnings de hoy y los de ayer after hours" son dos peticiones.
        for i, (_, date) in enumerate(days):
            if i not in claimed and (date, None) not in windows:
                windows.append((date, None))
        # Pedir un día entero ya incluye sus franjas: quedarse con ambos
        # devolvería las mismas compañías dos veces.
        whole_days = {d for d, sl in windows if sl is None}
        windows = [(d, sl) for d, sl in windows
                   if sl is None or d not in whole_days]
    else:
        for _, date in days:
            if (date, None) not in windows:
                windows.append((date, None))

    if len(windows) < 2:
        return []
    if len(windows) > _MAX_WINDOWS:
        from agents._tool_args import warn
        warn(f"la consulta menciona {len(windows)} ventanas; se piden las "
             f"{_MAX_WINDOWS} primeras")
        windows = windows[:_MAX_WINDOWS]
    return windows


def _extract_days(q: str) -> int:
    match = re.search(r'(\d+)\s*(?:days?|dias?)', q.lower())
    if match:
        return min(max(int(match.group(1)), 1), 30)
    return 7

_DATE_NUMERIC_RE = re.compile(
    r'(\d{1,2})[/\-](\d{1,2})[/\-](\d{4})'
)
_ISO_DATE_RE = re.compile(r'(\d{4})[/\-](\d{1,2})[/\-](\d{1,2})')

_MONTH_NAMES = {
    "enero": 1, "january": 1, "jan": 1,
    "febrero": 2, "february": 2, "feb": 2,
    "marzo": 3, "march": 3, "mar": 3,
    "abril": 4, "april": 4, "apr": 4,
    "mayo": 5, "may": 5,
    "junio": 6, "june": 6, "jun": 6,
    "julio": 7, "july": 7, "jul": 7,
    "agosto": 8, "august": 8, "aug": 8,
    "septiembre": 9, "setiembre": 9, "september": 9, "sep": 9, "sept": 9,
    "octubre": 10, "october": 10, "oct": 10,
    "noviembre": 11, "november": 11, "nov": 11,
    "diciembre": 12, "december": 12, "dec": 12,
}
# "18 de julio [de 2026]" / "18 julio"
_DATE_TEXT_ES_RE = re.compile(r'\b(\d{1,2})\s+(?:de\s+)?([a-zá-ú]{3,12})(?:\s+(?:de\s+|del\s+)?(\d{4}))?\b')
# "july 18[, 2026]" / "jul 18th"
_DATE_TEXT_EN_RE = re.compile(r'\b([a-z]{3,9})\s+(\d{1,2})(?:st|nd|rd|th)?(?:,?\s+(\d{4}))?\b')
# Mes a secas: "julio", "en junio de 2026", "june 2026" (sin día). Construido
# desde _MONTH_NAMES para no capturar palabras arbitrarias.
_MONTH_ONLY_RE = re.compile(
    r'\b(' + '|'.join(sorted(_MONTH_NAMES, key=len, reverse=True)) + r')\b'
    r'(?:\s+(?:de\s+|del\s+)?(\d{4}))?'
)


def _extract_date_reference(q: str) -> tuple[str | None, str | None]:
    """Extract date_from and date_to from natural language references."""
    ql = q.lower()
    today = datetime.now()

    iso_m = _ISO_DATE_RE.search(ql)
    if iso_m:
        y, m, d = int(iso_m.group(1)), int(iso_m.group(2)), int(iso_m.group(3))
        try:
            target = datetime(y, m, d)
            return target.strftime("%Y-%m-%d"), (target + timedelta(days=1)).strftime("%Y-%m-%d")
        except ValueError:
            pass

    num_m = _DATE_NUMERIC_RE.search(ql)
    if num_m:
        a, b, y = int(num_m.group(1)), int(num_m.group(2)), int(num_m.group(3))
        # Sin detección de idioma: se desambigua por valor. a>12 no puede ser
        # mes → día primero (DD/MM); b>12 no puede ser mes → mes primero
        # (MM/DD). Ambiguo (ambos ≤12) → DD/MM, la convención de la casa.
        # El swap del except cubre el resto.
        if b > 12:
            m, d = a, b
        else:
            d, m = a, b
        try:
            target = datetime(y, m, d)
            return target.strftime("%Y-%m-%d"), (target + timedelta(days=1)).strftime("%Y-%m-%d")
        except ValueError:
            d, m = m, d
            try:
                target = datetime(y, m, d)
                return target.strftime("%Y-%m-%d"), (target + timedelta(days=1)).strftime("%Y-%m-%d")
            except ValueError:
                pass

    # Fechas con mes textual: "18 de julio [de 2026]", "july 18[, 2026]",
    # "aug 5". Sin año explícito: año actual, o el anterior si quedaría en
    # el futuro (se pregunta por el pasado).
    for m, d_i, mo_i, y_i in (
        (_DATE_TEXT_ES_RE.search(ql), 1, 2, 3),
        (_DATE_TEXT_EN_RE.search(ql), 2, 1, 3),
    ):
        if m and m.group(mo_i) in _MONTH_NAMES:
            try:
                day = int(m.group(d_i))
                month = _MONTH_NAMES[m.group(mo_i)]
                year = int(m.group(y_i)) if m.group(y_i) else today.year
                target = datetime(year, month, day)
                if not m.group(y_i) and target > today + timedelta(days=1):
                    target = datetime(year - 1, month, day)
                return (target.strftime("%Y-%m-%d"),
                        (target + timedelta(days=1)).strftime("%Y-%m-%d"))
            except ValueError:
                pass

    # Mes a secas ("julio", "en junio", "june 2026") → rango del mes entero,
    # recortado a hoy si el mes está en curso. Sin año: el actual, o el
    # anterior si el mes aún no ha llegado este año. "may" inglés solo se
    # acepta con año explícito (colisiona con el verbo modal).
    m = _MONTH_ONLY_RE.search(ql)
    if m and m.group(1) in _MONTH_NAMES:
        name = m.group(1)
        if not (name == "may" and not m.group(2)):
            month = _MONTH_NAMES[name]
            year = int(m.group(2)) if m.group(2) else today.year
            if not m.group(2) and month > today.month:
                year -= 1
            start = datetime(year, month, 1)
            if month == 12:
                end = datetime(year + 1, 1, 1)
            else:
                end = datetime(year, month + 1, 1)
            end = min(end, today + timedelta(days=1))
            if start <= today:
                return start.strftime("%Y-%m-%d"), end.strftime("%Y-%m-%d")

    day_map = {
        "monday": 0, "lunes": 0,
        "tuesday": 1, "martes": 1,
        "wednesday": 2, "miércoles": 2, "miercoles": 2,
        "thursday": 3, "jueves": 3,
        "friday": 4, "viernes": 4,
    }

    for name, weekday in day_map.items():
        if name in ql:
            days_back = (today.weekday() - weekday) % 7
            # days_back == 0 means "today is that day" → use today, not last week
            if days_back == 0:
                target = today
            else:
                target = today - timedelta(days=days_back)
            return target.strftime("%Y-%m-%d"), (target + timedelta(days=1)).strftime("%Y-%m-%d")

    if "yesterday" in ql or "ayer" in ql:
        yest = today - timedelta(days=1)
        # Skip weekends: if yesterday is Sunday → use Friday
        if yest.weekday() == 6:  # Sunday
            yest = today - timedelta(days=2)
        elif yest.weekday() == 5:  # Saturday
            yest = today - timedelta(days=1)
        return yest.strftime("%Y-%m-%d"), (yest + timedelta(days=1)).strftime("%Y-%m-%d")

    if "last week" in ql or "semana pasada" in ql:
        start = today - timedelta(days=today.weekday() + 7)
        end = start + timedelta(days=5)
        return start.strftime("%Y-%m-%d"), end.strftime("%Y-%m-%d")

    return today.strftime("%Y-%m-%d"), (today + timedelta(days=1)).strftime("%Y-%m-%d")

# ── Public API ──────────────────────────────────────────────────────
# The underscore names above are the historical ones, kept so the move
# stays a move. New code should use these.

AMC_PHRASES: tuple[str, ...] = tuple(_AMC_KEYWORDS)
BMO_PHRASES: tuple[str, ...] = tuple(_BMO_KEYWORDS)
SESSION_PHRASES: tuple[str, ...] = AMC_PHRASES + BMO_PHRASES

detect_slot = _detect_time_slot
slot_mentions = _slot_mentions
day_mentions = _day_mentions
earnings_windows = _extract_earnings_windows
date_reference = _extract_date_reference
lookback_days = _extract_days


def mentions_session(text: str) -> bool:
    """True if the question names a market session at all."""
    return detect_slot(text) is not None
