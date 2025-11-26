"""
Benzinga News Data Models
"""

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
    
    class Config:
        json_encoders = {
            datetime: lambda v: v.isoformat() if v else None
        }
    
    @classmethod
    def from_polygon_response(cls, data: dict) -> "BenzingaArticle":
        """
        Crea un artículo desde la respuesta de Polygon API
        """
        return cls(
            benzinga_id=data.get("benzinga_id", 0),
            title=data.get("title", ""),
            author=data.get("author", "Unknown"),
            published=data.get("published", ""),
            last_updated=data.get("last_updated", data.get("published", "")),
            url=data.get("url", ""),
            teaser=data.get("teaser"),
            body=data.get("body"),
            tickers=data.get("tickers") or [],
            channels=data.get("channels") or [],
            tags=data.get("tags") or [],
            images=data.get("images") or [],
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
    limit: int = Field(default=50, ge=1, le=200, description="Límite de resultados")
    sort: str = Field(default="published.desc", description="Ordenamiento")

