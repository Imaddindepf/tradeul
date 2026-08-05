"""
Deterministic query constraints — extracted BEFORE routing, enforced AFTER.

The planner is probabilistic: the same literal query ("top earnings de esta
mañana pre market y de ayer after hour") has been classified EARNINGS_CALENDAR
twice and RANKING a third time, and in run 4b6275b0323b4bc5 (2026-08-04) the
word "earnings" simply vanished from the executed plan — a full-market ranking
was presented as earnings movers, with 9 of 10 rows from companies that never
reported. This module turns the part that must not be a coin flip into an
invariant: if the query names an event source (earnings, for now), that source
is MANDATORY in the routing, whatever the model decided.

Same principle as agents/_when.py for dates: one vocabulary, one place, every
consumer imports it from here (news_events re-exports for its own detection).
No LLM anywhere in this file.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field

# One earnings vocabulary for the whole agent. news_events imports this list;
# do not fork it there again (that fork is how the planner and the agents
# ended up disagreeing about what "counts as earnings").
EARNINGS_KEYWORDS = [
    "earnings", "earning", "eranings", "earningd",  # + the two real-world typos seen in prod
    "eps", "revenue",
    "quarterly", "quarter", "q1", "q2", "q3", "q4",
    "beat", "miss", "guidance", "forecast",
    "resultados", "ganancias", "trimestral", "reportan", "reporta",
    "reportes", "reporte", "reportaron", "presentaron resultados",
]

# Words that mean the user wants the list ORDERED BY PRICE REACTION rather
# than by surprise: "por orden de movimiento", "movers", "más se movieron".
_MOVE_RE = re.compile(
    r"\b(mov(?:imiento|ers?|ed|ement)|se\s+movieron|m[aá]s\s+se\s+m(?:ueven|ovieron)"
    r"|by\s+(?:the\s+)?move|por\s+(?:orden\s+de\s+)?movimiento)\b",
    re.IGNORECASE,
)

# Words that mean the user wants the SURPRISE ordering (beat/miss vs consensus).
_SURPRISE_RE = re.compile(
    r"\b(sorpresa|surprise[sd]?|beat|miss(?:ed)?|sorprendieron)\b",
    re.IGNORECASE,
)

# A ranking-ish word: "top", "mejores", "ordered by", "ordenados por"...
_RANKED_RE = re.compile(
    r"\b(top|best|worst|mejores|peores|mayor(?:es)?|orden(?:a(?:do)?s?)?|ordered|ranking|rank)\b",
    re.IGNORECASE,
)


def _mentions_earnings(q: str) -> bool:
    ql = q.lower()
    return any(kw in ql for kw in EARNINGS_KEYWORDS if " " in kw) or any(
        re.search(rf"\b{re.escape(kw)}\b", ql) for kw in EARNINGS_KEYWORDS if " " not in kw
    )


@dataclass
class QueryConstraints:
    """What the query pins down regardless of the planner's opinion."""
    earnings: bool = False
    # 'move' | 'surprise' | None — how an earnings list should be ranked.
    earnings_sort: str | None = None
    # (date|None, 'amc'|'bmo'|None) windows, straight from agents._when.
    windows: list = field(default_factory=list)

    def to_state(self) -> dict:
        return {
            "earnings": self.earnings,
            "earnings_sort": self.earnings_sort,
            "windows": self.windows,
        }


def extract_constraints(query: str, agent_task: str | None = None) -> QueryConstraints:
    """Deterministic pass over the query (and optional planner task).

    Cheap (regex only), never raises, and NEVER consults an LLM: this is the
    part of routing that must give the same answer every single time.
    """
    text = f"{query} {agent_task or ''}"
    cons = QueryConstraints()

    if _mentions_earnings(text):
        cons.earnings = True
        from agents._when import (
            _detect_time_slot, _extract_earnings_windows, date_reference,
        )
        cons.windows = _extract_earnings_windows(text) or []
        if not cons.windows:
            slot = _detect_time_slot(text)
            date_from, _ = date_reference(text)
            cons.windows = [(date_from, slot)]

        if _SURPRISE_RE.search(text):
            cons.earnings_sort = "surprise"
        elif _MOVE_RE.search(text):
            cons.earnings_sort = "move"
        elif _RANKED_RE.search(text) and any(sl for _, sl in cons.windows):
            # "top earnings after hours" with no explicit axis: the session
            # slot in the ask implies ranking by the session reaction.
            cons.earnings_sort = "move"

    return cons


def covers_earnings(agent_results: dict) -> bool:
    """True if any executed agent actually queried an earnings source.

    Looks for earnings-shaped KEYS (not text content — news prose mentioning
    'earnings' must not count) at any depth of the results dict.
    """
    def _walk(node, depth: int = 0) -> bool:
        if depth > 4 or not isinstance(node, dict):
            return False
        for k, v in node.items():
            if isinstance(k, str) and "earnings" in k.lower():
                return True
            if _walk(v, depth + 1):
                return True
        return False

    return _walk(agent_results)
