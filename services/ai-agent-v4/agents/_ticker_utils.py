"""
Shared ticker extraction utility for all agents.

Centralizes:
- Ticker regex patterns
- Comprehensive stopword list (English + Spanish)
- Common false-positive filtering
"""
from __future__ import annotations
import re

# ── Regex patterns ──────────────────────────────────────────────────
_TICKER_RE = re.compile(r'(?<!\w)\$?([A-Z]{1,5})(?:\s|$|[,;.!?\)])')

# ── Comprehensive stopword list ─────────────────────────────────────
# Words that match ticker-like patterns but are NOT stock symbols.
# Organized by category for maintainability.

_ENGLISH_COMMON = {
    # Pronouns / articles / prepositions
    "I", "A", "AM", "AN", "AS", "AT", "BE", "BY", "DO", "GO", "HE",
    "IF", "IN", "IS", "IT", "ME", "MY", "NO", "OF", "ON", "OR", "SO",
    "TO", "UP", "US", "WE",
    # Common short words
    "ALL", "AND", "ANY", "ARE", "BUT", "CAN", "DAY", "DID", "FOR",
    "GET", "GOT", "HAS", "HAD", "HER", "HIM", "HIS", "HOW", "ITS",
    "LET", "MAY", "NEW", "NOT", "NOW", "OLD", "ONE", "OUR", "OUT",
    "OWN", "RAN", "RUN", "SAY", "SET", "SHE", "THE", "TOO", "TWO",
    "USE", "WAS", "WAY", "WHO", "WHY", "WIN", "WON", "YET", "YOU",
    # 4-5 letter common words
    "ALSO", "BACK", "BEEN", "BEST", "BOTH", "CAME", "COME", "EACH",
    "EVEN", "FIND", "FOUR", "FROM", "GAVE", "GIVE", "GOES", "GONE",
    "GOOD", "HALF", "HAVE", "HERE", "HIGH", "HOLD", "HUGE", "JUST",
    "KEEP", "KNEW", "KNOW", "LAST", "LEFT", "LIKE", "LIST", "LONG",
    "LOOK", "LOSE", "LOST", "LOTS", "MADE", "MAIN", "MAKE", "MANY",
    "MATH", "MORE", "MOST", "MUCH", "MUST", "NAME", "NEAR", "NEED",
    "NEXT", "NINE", "NONE", "ONCE", "ONLY", "OPEN", "OVER", "PAID",
    "PART", "PAST", "PICK", "PLAN", "PLUS", "PULL", "PUSH", "PUTS",
    "RATE", "READ", "REAL", "REST", "RISE", "ROAD", "ROLE", "SAID",
    "SAME", "SAVE", "SEEM", "SELL", "SENT", "SHOW", "SIDE", "SIGN",
    "SOME", "SOON", "STAY", "STEP", "STOP", "SUCH", "SURE", "TAKE",
    "TALK", "TELL", "TERM", "TEXT", "THAN", "THAT", "THEM", "THEN",
    "THEY", "THIS", "TIME", "TOLD", "TOOK", "TURN", "TYPE", "UPON",
    "VERY", "WANT", "WEEK", "WELL", "WENT", "WERE", "WHAT", "WHEN",
    "WILL", "WITH", "WORD", "WORK", "YEAR", "YOUR",
    "ABOUT", "ABOVE", "AFTER", "AGAIN", "BEING", "BELOW", "COULD",
    "DOING", "EIGHT", "EVERY", "FIRST", "FOUND", "GOING", "GREAT",
    "GUESS", "MONEY", "MONTH", "NEVER", "OTHER", "PLACE", "POINT",
    "PRICE", "RIGHT", "SHALL", "SINCE", "STILL", "STOCK", "THEIR",
    "THERE", "THESE", "THING", "THINK", "THREE", "TODAY", "TOTAL",
    "UNDER", "UNTIL", "USING", "VALUE", "WATCH", "WHERE", "WHICH",
    "WHILE", "WHOLE", "WORLD", "WORSE", "WORST", "WOULD", "COULD",
}

_SPANISH_COMMON = {
    # Articles / prepositions / conjunctions
    "DE", "LA", "EL", "EN", "ES", "UN", "SE", "NO", "SI", "YA", "LE",
    "LO", "AL", "ME", "MI", "TE", "TU",
    # Common 3-letter
    "CON", "DEL", "LAS", "LOS", "MAS", "MIS", "UNA", "POR", "QUE",
    "SER", "SIN", "SON", "SUS", "TAN", "VER", "VEZ",
    # Common 4-letter
    "ALGO", "AQUI", "BAJO", "BIEN", "CADA", "CASO", "COMO", "CREE",
    "DADO", "DAME", "DICE", "DIJO", "ELLA", "ESAS", "ESOS", "ESTA",
    "ESTO", "GRAN", "HACE", "HIZO", "HUBO", "LADO", "MAYO", "MIRA",
    "MODO", "MUYA", "NADA", "OTRA", "OTRO", "PARA", "PASO", "POCO",
    "PUDO", "PUES", "SEMI", "SERA", "SIDO", "SOLO", "TIPO", "TODA",
    "TODO", "TRES", "TUVO", "VALE", "VIDA",
    # Common 5-letter
    "AHORA", "ANTES", "BUSCA", "BUENO", "CIELO", "CREER", "DESDE",
    "DONDE", "ENTRE", "FECHA", "FORMA", "HASTA", "MEJOR", "MISMO",
    "MUCHO", "MUNDO", "NUEVA", "NUEVO", "NUNCA", "PARTE", "PUEDE",
    "QUIEN", "SOBRE", "TANTO", "TIENE", "TODAS", "TODOS", "VIENE",
    # Question words
    "CUAL", "DONDE", "QUIEN",
    # Time words
    "HOY", "DIA", "MES", "AYER", "LUNES",
}

_FINANCIAL_TERMS = {
    # Common financial acronyms that aren't tickers
    "CEO", "CFO", "CTO", "COO", "FDA", "SEC", "IPO", "ETF", "GDP",
    "CPI", "ATH", "ATL", "DD", "EPS", "PE", "API", "AI", "ITM",
    "OTM", "ATM", "RSI", "MACD", "VWAP", "SMA", "EMA", "ADX",
    "BPS", "YOY", "QOQ", "MOM", "FED", "FOMC", "OPEX", "ER",
    "IMO", "FOMO", "FUD", "HODL", "YOLO", "OTC", "NYSE", "AMEX",
    # Common words that look like tickers in financial context
    "BUY", "SELL", "CALL", "PUT", "LONG", "HOLD", "GAIN", "LOSS",
    "BEAR", "BULL", "BOND", "CASH", "DEBT", "DUMP", "EARN", "EDGE",
    "FEAR", "FLOW", "FREE", "FUND", "GOLD", "GROW", "HALT", "HOPE",
    "JUMP", "LOAN", "MOVE", "NEWS", "PEAK", "PUMP", "PUSH", "RISK",
    "SAFE", "SPIN", "SWAP", "TANK", "TOPS", "TRAP", "TRIM", "WEAK",
    "DOWN", "LOW",
}

# Combined set
STOPWORDS = _ENGLISH_COMMON | _SPANISH_COMMON | _FINANCIAL_TERMS


def extract_tickers(query: str) -> list[str]:
    """Extract probable stock tickers from a user query.

    1. Explicit $TICKER mentions (highest confidence)
    2. ALL-CAPS words that pass stopword filtering
    3. Deduplication preserving order

    Returns a list of likely ticker symbols.
    """
    upper = query.upper()

    # Explicit $TICKER mentions — always trust these
    explicit = re.findall(r'\$([A-Z]{1,5})\b', upper)

    # Implicit ALL-CAPS words — filter through stopwords
    implicit = _TICKER_RE.findall(upper)

    # Combine, deduplicate, filter
    combined = list(dict.fromkeys(explicit + implicit))
    return [t for t in combined if t not in STOPWORDS and len(t) >= 2]
