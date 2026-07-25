"""
Polygon News Data Models

Normaliza los artículos de /v2/reference/news al shape del pipeline unificado
de noticias, añadiendo la capa exclusiva de Polygon: sentimiento por ticker
(`insights`) y un sentimiento agregado por artículo (`sentiment`).
"""

import html
from collections import Counter
from typing import Optional, List, Dict
from datetime import datetime, timezone

from pydantic import BaseModel, Field


def _aggregate_sentiment(insights: List[Dict]) -> Optional[str]:
    """Sentimiento del artículo: mayoría entre tickers; empate → neutral."""
    votes = Counter(
        (i.get("sentiment") or "").lower()
        for i in insights
        if i.get("sentiment") in ("positive", "negative", "neutral")
    )
    if not votes:
        return None
    top = votes.most_common(2)
    if len(top) > 1 and top[0][1] == top[1][1]:
        return "neutral"
    return top[0][0]


class PolygonArticle(BaseModel):
    """
    Artículo de Polygon normalizado al shape del pipeline
    (id/title/author/published/url/tickers/channels/teaser) + sentiment.
    """
    id: str = Field(..., description="ID estable (poly_ + id de Polygon)")
    title: str = Field(..., description="Título del artículo")
    author: str = Field(default="Unknown", description="Publisher (columna source en la UI)")
    published: str = Field(..., description="Fecha de publicación ISO 8601 UTC")
    url: str = Field(..., description="URL del artículo original")
    source: str = Field(default="polygon", description="Fuente interna del pipeline")
    site: Optional[str] = Field(default=None, description="Dominio del publisher")
    tickers: List[str] = Field(default_factory=list, description="Tickers mencionados")
    channels: List[str] = Field(default_factory=list, description="Feed de origen (filtro channels de la UI)")
    tags: List[str] = Field(default_factory=list, description="Keywords del artículo")
    teaser: Optional[str] = Field(default=None, description="Resumen del artículo")
    image: Optional[str] = Field(default=None, description="URL de imagen")
    sentiment: Optional[str] = Field(default=None, description="Sentimiento agregado: positive|negative|neutral")
    insights: List[Dict] = Field(default_factory=list, description="Sentimiento por ticker con razonamiento")

    @classmethod
    def from_polygon(cls, data: dict) -> Optional["PolygonArticle"]:
        url = (data.get("article_url") or "").strip()
        title = html.unescape(data.get("title") or "").strip()
        raw_id = (data.get("id") or "").strip()
        if not url or not title or not raw_id:
            return None

        publisher = data.get("publisher") or {}
        published = data.get("published_utc") or datetime.now(timezone.utc).isoformat()

        raw_insights = data.get("insights") or []
        insights = [
            {
                "ticker": i.get("ticker"),
                "sentiment": i.get("sentiment"),
                "reasoning": (i.get("sentiment_reasoning") or "")[:400],
            }
            for i in raw_insights
            if i.get("ticker")
        ]

        description = data.get("description")

        return cls(
            id=f"poly_{raw_id[:16]}",
            title=title,
            author=(publisher.get("name") or "Polygon").strip(),
            published=published,
            url=url,
            site=(publisher.get("homepage_url") or "").replace("https://", "").replace("http://", "").strip("/") or None,
            tickers=[t.upper() for t in (data.get("tickers") or []) if t][:12],
            channels=["Polygon"],
            tags=(data.get("keywords") or [])[:10],
            teaser=html.unescape(description).strip() if description else None,
            image=data.get("image_url"),
            sentiment=_aggregate_sentiment(insights),
            insights=insights,
        )
