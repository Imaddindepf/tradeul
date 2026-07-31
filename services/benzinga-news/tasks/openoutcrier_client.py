"""
OpenOutcrier Benzinga Client

Cliente para el feed de Benzinga de OpenOutcrier (canal `type=bz`).

Reemplaza a Polygon como fuente del servicio benzinga-news. OpenOutcrier expone
un feed propietario de BenzingaPro vía short-polling HTTP:

    POST https://openoutcrier.com/load
    Content-Type: application/x-www-form-urlencoded
    body: type=bz&last=<cursor>&direction=post|pre

El acceso Pro se autentica con una cookie de sesión (`hash`). La respuesta es un
array de objetos JSON (a veces doble-encodeados como strings):

    {
      "type": "bz",
      "id": "17830239302525351",   # snowflake, sirve de cursor
      "bz_id": 60260245,           # ID nativo de Benzinga (dedup)
      "date": "Thu, 02 Jul 2026 16:25:10 -0400",
      "title": "...",
      "time": "16:25:10",
      "description": "...",
      "link": "https://www.benzinga.com/...",
      "tickers": "$SURG, $T",
      "timestamp": "1783023930"
    }

Semántica de cursores (verificada en vivo):
- direction="post": devuelve items con id > last (hacia adelante en el tiempo).
- direction="pre":  devuelve items con id < last (hacia atrás en el tiempo).
- last="0" + direction="post": devuelve los ~20 items más recientes.
- Máximo ~20 items por respuesta.

Expone la misma superficie de métodos que el antiguo BenzingaNewsClient para que
el stream manager y los endpoints REST no necesiten cambios de contrato.
"""

import asyncio
from typing import Optional, List, Dict, Any

import httpx
import structlog

from models.news import BenzingaArticle

logger = structlog.get_logger(__name__)

CHANNEL_BENZINGA = "bz"


class OpenOutcrierBenzingaClient:
    """Cliente asíncrono para el feed Benzinga (canal bz) de OpenOutcrier."""

    def __init__(
        self,
        base_url: str,
        session_hash: str,
        endpoint: str = "/load",
        page_size: int = 20,
        max_pages: int = 50,
    ):
        """
        Args:
            base_url: Base de OpenOutcrier (e.g. https://openoutcrier.com)
            session_hash: Cookie `hash` de la sesión Pro (bypass del paywall)
            endpoint: Ruta del feed (default /load)
            page_size: Items por respuesta del servidor (~20)
            max_pages: Tope de páginas al paginar para acotar el trabajo
        """
        self.base_url = base_url.rstrip("/")
        self.session_hash = session_hash
        self.endpoint = endpoint
        self.page_size = page_size
        self.max_pages = max_pages

        self._client: Optional[httpx.AsyncClient] = None

        # Rate limiting básico entre requests
        self._last_request_time = 0.0
        self._min_request_interval = 0.1  # 100ms

        self.stats = {
            "requests_made": 0,
            "articles_fetched": 0,
            "errors": 0,
            "last_fetch": None,
        }

        logger.info("openoutcrier_client_initialized", base_url=self.base_url)

    async def _get_client(self) -> httpx.AsyncClient:
        if self._client is None or self._client.is_closed:
            self._client = httpx.AsyncClient(
                base_url=self.base_url,
                timeout=30.0,
                headers={
                    "Accept": "application/json, text/plain, */*",
                    "Content-Type": "application/x-www-form-urlencoded",
                    "User-Agent": "Mozilla/5.0 (Tradeul BenzingaFeed/1.0)",
                    "X-Requested-With": "XMLHttpRequest",
                },
                cookies={"hash": self.session_hash},
            )
        return self._client

    async def close(self):
        if self._client and not self._client.is_closed:
            await self._client.aclose()

    async def _rate_limit(self):
        now = asyncio.get_event_loop().time()
        elapsed = now - self._last_request_time
        if elapsed < self._min_request_interval:
            await asyncio.sleep(self._min_request_interval - elapsed)
        self._last_request_time = asyncio.get_event_loop().time()

    async def _load(self, last: str, direction: str = "post") -> List[Dict[str, Any]]:
        """
        Una llamada cruda a POST /load para el canal bz.

        Returns:
            Lista de dicts (items ya decodificados). [] si no hay novedades o error.
        """
        await self._rate_limit()

        import json as _json

        try:
            client = await self._get_client()
            response = await client.post(
                self.endpoint,
                data={"type": CHANNEL_BENZINGA, "last": str(last), "direction": direction},
            )

            # Sesión expirada / redirección al login => cookie inválida
            if response.status_code in (301, 302, 303, 307, 308):
                logger.error("ooc_session_expired", status=response.status_code)
                self.stats["errors"] += 1
                return []

            response.raise_for_status()

            raw = response.json()
            items: List[Dict[str, Any]] = []
            for entry in raw:
                # El feed a veces devuelve strings JSON dentro del array
                if isinstance(entry, str):
                    try:
                        entry = _json.loads(entry)
                    except _json.JSONDecodeError:
                        continue
                if isinstance(entry, dict):
                    items.append(entry)

            self.stats["requests_made"] += 1
            from datetime import datetime as _dt

            self.stats["last_fetch"] = _dt.now().isoformat()
            return items

        except httpx.HTTPStatusError as e:
            logger.error("ooc_http_error", status=e.response.status_code, detail=str(e))
            self.stats["errors"] += 1
            return []
        except Exception as e:
            logger.error("ooc_load_error", error=str(e))
            self.stats["errors"] += 1
            return []

    def _parse_items(self, items: List[Dict[str, Any]]) -> List[BenzingaArticle]:
        articles: List[BenzingaArticle] = []
        for data in items:
            try:
                articles.append(BenzingaArticle.from_ooc_response(data))
            except Exception as e:
                logger.warning("ooc_article_parse_error", error=str(e))
        self.stats["articles_fetched"] += len(articles)
        return articles

    @staticmethod
    def _dedup_sort(articles: List[BenzingaArticle]) -> List[BenzingaArticle]:
        """Deduplica por benzinga_id y ordena por id descendente (más reciente primero)."""
        seen = set()
        unique = []
        for a in articles:
            if a.benzinga_id in seen:
                continue
            seen.add(a.benzinga_id)
            unique.append(a)
        unique.sort(key=lambda a: a.benzinga_id, reverse=True)
        return unique

    async def _paginate_back(self, limit: int) -> List[BenzingaArticle]:
        """
        Recolecta hasta `limit` artículos hacia atrás en el tiempo partiendo de ahora.
        Usa direction="pre" y va bajando el cursor por el id mínimo de cada página.
        """
        import time as _time

        collected: List[BenzingaArticle] = []
        cursor = str(int(_time.time() * 10_000_000))  # snowflake ≈ unix_seconds * 1e7
        pages = 0

        while len(collected) < limit and pages < self.max_pages:
            items = await self._load(cursor, direction="pre")
            if not items:
                break
            articles = self._parse_items(items)
            if not articles:
                break
            collected.extend(articles)

            min_id = min(a.benzinga_id_cursor for a in articles)
            new_cursor = str(min_id)
            if new_cursor == cursor:
                break
            cursor = new_cursor
            pages += 1

        return self._dedup_sort(collected)[:limit]

    # ── Superficie compatible con el antiguo BenzingaNewsClient ──────────────

    async def fetch_latest_news(self, limit: int = 50) -> List[BenzingaArticle]:
        """Últimas noticias del feed (más recientes primero)."""
        if limit <= self.page_size:
            items = await self._load("0", direction="post")
            return self._dedup_sort(self._parse_items(items))[:limit]
        return await self._paginate_back(limit)

    async def fetch_news_for_ticker(
        self, ticker: str, limit: int = 50, since: Optional[str] = None
    ) -> List[BenzingaArticle]:
        """
        Noticias para un ticker. OpenOutcrier no filtra por ticker en servidor,
        así que traemos un lote amplio y filtramos en memoria.
        """
        ticker = ticker.upper()
        pool = await self._paginate_back(max(limit * 10, 200))
        filtered = [a for a in pool if ticker in (a.tickers or [])]
        return filtered[:limit]

    def get_stats(self) -> Dict[str, Any]:
        return self.stats.copy()
