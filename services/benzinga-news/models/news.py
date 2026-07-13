"""
Benzinga News Data Models
"""

import html
from typing import Optional, List
from datetime import datetime
from pydantic import BaseModel, Field


class BenzingaArticle(BaseModel):
    """
    Modelo de artículo de noticias de Benzinga
    Basado en la respuesta de Polygon.io /benzinga/v2/news
    """
    benzinga_id: int = Field(..., description="Identificador único de Benzinga")
    title: str = Field(..., description="Título del artículo")
    author: str = Field(..., description="Autor del artículo")
    published: str = Field(..., description="Fecha de publicación ISO 8601")
    last_updated: str = Field(..., description="Última actualización ISO 8601")
    url: str = Field(..., description="URL del artículo original")
    
    # Campos opcionales
    teaser: Optional[str] = Field(default=None, description="Resumen/teaser del artículo")
    body: Optional[str] = Field(default=None, description="Contenido completo del artículo")
    tickers: Optional[List[str]] = Field(default_factory=list, description="Tickers mencionados")
    channels: Optional[List[str]] = Field(default_factory=list, description="Categorías/canales")
    tags: Optional[List[str]] = Field(default_factory=list, description="Tags del artículo")
    images: Optional[List[str]] = Field(default_factory=list, description="URLs de imágenes")

    # Cursor propio de OpenOutcrier (snowflake id). Sirve para paginar el feed.
    # exclude=True => no se serializa en model_dump_json (no llega al frontend ni al cache).
    benzinga_id_cursor: int = Field(default=0, exclude=True, description="ID snowflake de OpenOutcrier (cursor de polling)")
    
    class Config:
        json_encoders = {
            datetime: lambda v: v.isoformat() if v else None
        }
    
    @classmethod
    def from_polygon_response(cls, data: dict) -> "BenzingaArticle":
        """
        Crea un artículo desde la respuesta de Polygon API.
        Decodifica entidades HTML (&#39; → ', &amp; → &, etc.)
        """
        # Decodificar entidades HTML en título y teaser
        title = data.get("title", "")
        if title:
            title = html.unescape(title)
        
        teaser = data.get("teaser")
        if teaser:
            teaser = html.unescape(teaser)
        
        return cls(
            benzinga_id=data.get("benzinga_id", 0),
            title=title,
            author=data.get("author", "Unknown"),
            published=data.get("published", ""),
            last_updated=data.get("last_updated", data.get("published", "")),
            url=data.get("url", ""),
            teaser=teaser,
            body=data.get("body"),
            tickers=data.get("tickers") or [],
            channels=data.get("channels") or [],
            tags=data.get("tags") or [],
            images=data.get("images") or [],
        )

    @classmethod
    def from_ooc_response(cls, data: dict) -> "BenzingaArticle":
        """
        Crea un artículo desde la respuesta del canal `bz` de OpenOutcrier.

        Mapeo de campos OOC -> BenzingaArticle:
            bz_id       -> benzinga_id       (dedup, ID nativo de Benzinga)
            id          -> benzinga_id_cursor (snowflake, cursor de polling)
            title       -> title
            description -> teaser
            link        -> url
            date        -> published (RFC 2822, se normaliza a ISO 8601)
            tickers     -> tickers ("$SURG, $T" -> ["SURG", "T"])
        """
        from datetime import datetime, timezone
        from email.utils import parsedate_to_datetime

        title = data.get("title", "") or ""
        if title:
            title = html.unescape(title)

        teaser = data.get("description")
        if teaser:
            teaser = html.unescape(teaser)

        # Normalizar fecha RFC 2822 ("Thu, 02 Jul 2026 16:25:10 -0400") a ISO 8601.
        published_iso = ""
        raw_date = data.get("date")
        if raw_date:
            try:
                published_iso = parsedate_to_datetime(raw_date).astimezone(timezone.utc).isoformat()
            except (TypeError, ValueError):
                published_iso = ""
        if not published_iso:
            ts = data.get("timestamp")
            if ts:
                try:
                    published_iso = datetime.fromtimestamp(int(ts), tz=timezone.utc).isoformat()
                except (TypeError, ValueError, OSError):
                    published_iso = ""
        if not published_iso:
            published_iso = datetime.now(timezone.utc).isoformat()

        # Tickers: string "$SURG, $T" -> ["SURG", "T"]
        tickers: List[str] = []
        raw_tickers = data.get("tickers")
        if isinstance(raw_tickers, str) and raw_tickers.strip():
            for tok in raw_tickers.split(","):
                sym = tok.strip().lstrip("$").upper()
                if sym:
                    tickers.append(sym)
        elif isinstance(raw_tickers, list):
            for tok in raw_tickers:
                sym = str(tok).strip().lstrip("$").upper()
                if sym:
                    tickers.append(sym)

        def _to_int(v) -> int:
            try:
                return int(v)
            except (TypeError, ValueError):
                return 0

        return cls(
            benzinga_id=_to_int(data.get("bz_id")),
            benzinga_id_cursor=_to_int(data.get("id")),
            title=title,
            author=data.get("author", "Benzinga"),
            published=published_iso,
            last_updated=published_iso,
            url=data.get("link", "") or "",
            teaser=teaser,
            body=None,
            tickers=tickers,
            channels=[],
            tags=[],
            images=[],
        )


class NewsFilterParams(BaseModel):
    """
    Parámetros de filtrado para búsqueda de noticias
    """
    tickers: Optional[str] = Field(default=None, description="Tickers separados por coma")
    channels: Optional[str] = Field(default=None, description="Canales/categorías")
    tags: Optional[str] = Field(default=None, description="Tags del artículo")
    author: Optional[str] = Field(default=None, description="Nombre del autor")
    published_after: Optional[str] = Field(default=None, description="Publicado después de (ISO 8601)")
    published_before: Optional[str] = Field(default=None, description="Publicado antes de (ISO 8601)")
    limit: int = Field(default=50, ge=1, le=1000, description="Límite de resultados")
    sort: str = Field(default="published.desc", description="Ordenamiento")

