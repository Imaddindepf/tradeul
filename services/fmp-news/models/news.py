"""
FMP News Data Models

Normaliza los items de los feeds de noticias de FMP al mismo shape que
consume el pipeline unificado de noticias (cache Redis + stream + frontend).
"""

import hashlib
import html
import re
from typing import Optional, List
from datetime import datetime, timezone
from zoneinfo import ZoneInfo

from pydantic import BaseModel, Field

# Los endpoints /news/* de FMP devuelven publishedDate en hora del Este;
# /fmp-articles devuelve date en UTC (verificado empíricamente 2026-07-24).
ET = ZoneInfo("America/New_York")

_TAG_RE = re.compile(r"<[^>]+>")
_WS_RE = re.compile(r"\s+")


def _make_id(url: str) -> str:
    """ID estable derivado de la URL (los items de FMP no traen ID propio)"""
    return "fmp_" + hashlib.sha1(url.encode("utf-8")).hexdigest()[:16]


def _to_iso(raw: Optional[str], tz) -> str:
    """'YYYY-MM-DD HH:MM:SS' (naive) -> ISO 8601 con offset"""
    if raw:
        try:
            dt = datetime.strptime(raw.strip(), "%Y-%m-%d %H:%M:%S").replace(tzinfo=tz)
            return dt.isoformat()
        except ValueError:
            pass
    return datetime.now(timezone.utc).isoformat()


def _strip_html(text: str, max_len: int = 500) -> str:
    """Quita tags HTML y colapsa espacios (para el content de fmp-articles)"""
    clean = _WS_RE.sub(" ", _TAG_RE.sub(" ", text)).strip()
    clean = html.unescape(clean)
    return clean[:max_len]


class FMPArticle(BaseModel):
    """
    Artículo de noticias FMP normalizado.

    Campos alineados con el shape que espera el frontend (NewsArticle):
    id/title/author/published/url/tickers/channels/teaser.
    """
    id: str = Field(..., description="ID estable (hash de la URL)")
    title: str = Field(..., description="Título del artículo")
    author: str = Field(default="Unknown", description="Publisher (columna source en la UI)")
    published: str = Field(..., description="Fecha de publicación ISO 8601 con offset")
    url: str = Field(..., description="URL del artículo original")
    source: str = Field(default="fmp", description="Fuente interna del pipeline")
    site: Optional[str] = Field(default=None, description="Dominio del publisher")
    tickers: List[str] = Field(default_factory=list, description="Tickers mencionados")
    channels: List[str] = Field(default_factory=list, description="Feed de origen (filtro channels de la UI)")
    teaser: Optional[str] = Field(default=None, description="Resumen del artículo")
    image: Optional[str] = Field(default=None, description="URL de imagen")

    @property
    def is_reuters(self) -> bool:
        """True si el artículo procede de Reuters (para el feed Top News)"""
        return "reuters" in (self.author or "").lower() or (self.site or "").lower() == "reuters.com"

    @classmethod
    def from_feed_item(cls, data: dict, channel: str) -> Optional["FMPArticle"]:
        """
        Crea un artículo desde un item de los feeds /news/* de FMP
        (stock-latest, press-releases-latest, general-latest, forex-latest).
        """
        url = (data.get("url") or "").strip()
        title = html.unescape(data.get("title") or "").strip()
        if not url or not title:
            return None

        symbol = (data.get("symbol") or "").strip().upper()
        text = data.get("text")

        return cls(
            id=_make_id(url),
            title=title,
            author=(data.get("publisher") or data.get("site") or "Unknown").strip(),
            published=_to_iso(data.get("publishedDate"), ET),
            url=url,
            site=data.get("site"),
            tickers=[symbol] if symbol else [],
            channels=[channel],
            teaser=html.unescape(text).strip() if text else None,
            image=data.get("image"),
        )

    @classmethod
    def from_fmp_article(cls, data: dict, channel: str) -> Optional["FMPArticle"]:
        """
        Crea un artículo desde /fmp-articles (contenido editorial propio de FMP).
        Formato distinto: date en UTC, tickers "NASDAQ:META", content en HTML.
        """
        url = (data.get("link") or "").strip()
        title = html.unescape(data.get("title") or "").strip()
        if not url or not title:
            return None

        # "NASDAQ:META, NYSE:R" -> ["META", "R"]
        tickers = []
        for raw in (data.get("tickers") or "").split(","):
            sym = raw.split(":")[-1].strip().upper()
            if sym:
                tickers.append(sym)

        content = data.get("content")

        return cls(
            id=_make_id(url),
            title=title,
            author=data.get("site") or "Financial Modeling Prep",
            published=_to_iso(data.get("date"), timezone.utc),
            url=url,
            site="financialmodelingprep.com",
            tickers=tickers,
            channels=[channel],
            teaser=_strip_html(content) if content else None,
            image=data.get("image"),
        )
