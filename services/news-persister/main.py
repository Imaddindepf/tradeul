"""
News Persister Service

Consume el Redis Stream `stream:benzinga:news` (feed unificado de noticias:
benzinga/OpenOutcrier + fmp + polygon) mediante consumer group y persiste cada
artículo en la hypertable `news_articles` de la TimescaleDB principal.

Además expone la búsqueda del histórico (`/api/v1/news/history`): full-text
(websearch sobre title+teaser+body) + tickers + fuentes + publisher + fechas,
con paginación por cursor. Es la búsqueda que ningún proveedor ofrece.

Diseño (mismo patrón que openul-persister):
  - NO toca la ruta caliente: los 3 productores siguen publicando a Redis tal cual.
  - Consumer group => si el servicio se cae, retoma desde el último XACK.
  - Batch inserts + ON CONFLICT DO NOTHING => idempotente y eficiente.
  - Pending-claim al arrancar => reprocesa lo entregado-pero-no-confirmado.
"""

import asyncio
import hashlib
import json
import logging
import os
import sys
from contextlib import asynccontextmanager
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Tuple

import asyncpg
import httpx
import redis.asyncio as aioredis
import structlog
import trafilatura
import uvicorn
from fastapi import FastAPI, HTTPException, Query

from config import settings

logging.basicConfig(format="%(message)s", stream=sys.stdout, level=logging.INFO, force=True)

structlog.configure(
    processors=[
        structlog.stdlib.add_log_level,
        structlog.processors.TimeStamper(fmt="iso"),
        structlog.processors.JSONRenderer(),
    ],
    wrapper_class=structlog.stdlib.BoundLogger,
    context_class=dict,
    logger_factory=structlog.PrintLoggerFactory(),
    cache_logger_on_first_use=False,
)

logger = structlog.get_logger(__name__)

MIGRATION_PATH = os.path.join(os.path.dirname(__file__), "migrations", "001_create_news_articles.sql")

_INSERT_SQL = """
INSERT INTO news_articles (
    id, source, title, teaser, body, url, publisher, site,
    tickers, channels, tags, sentiment, insights, images,
    ticker_prices, published, received_at
) VALUES (
    $1, $2, $3, $4, $5, $6, $7, $8,
    $9, $10, $11, $12, $13::jsonb, $14,
    $15::jsonb, $16, $17
)
ON CONFLICT (id, published) DO NOTHING
"""


def _parse_dt(val: Any) -> Optional[datetime]:
    if not val or not isinstance(val, str):
        return None
    try:
        return datetime.fromisoformat(val.replace("Z", "+00:00"))
    except ValueError:
        return None


class Persister:
    def __init__(self) -> None:
        self.redis: Optional[aioredis.Redis] = None
        self.pool: Optional[asyncpg.Pool] = None
        self._task: Optional[asyncio.Task] = None
        self._running = False
        self._stats = {
            "rows_inserted": 0,
            "batches": 0,
            "messages_read": 0,
            "skipped": 0,
            "errors": 0,
            "last_insert_at": None,
        }

    # ── Lifecycle ────────────────────────────────────────────────────────
    async def start(self) -> None:
        redis_url = (
            f"redis://:{settings.redis_password}@{settings.redis_host}:{settings.redis_port}"
            if settings.redis_password
            else f"redis://{settings.redis_host}:{settings.redis_port}"
        )
        self.redis = await aioredis.from_url(redis_url, encoding="utf-8", decode_responses=True)
        await self.redis.ping()
        logger.info("redis_connected", host=settings.redis_host)

        self.pool = await asyncpg.create_pool(
            host=settings.postgres_host,
            port=settings.postgres_port,
            user=settings.postgres_user,
            password=settings.postgres_password,
            database=settings.postgres_db,
            min_size=settings.db_min_pool,
            max_size=settings.db_max_pool,
        )
        logger.info("timescale_connected", host=settings.postgres_host, db=settings.postgres_db)

        await self._apply_migration()
        await self._ensure_group()

        self._running = True
        self._task = asyncio.create_task(self._consume_loop())
        logger.info("persister_started", stream=settings.redis_stream_key)

    async def stop(self) -> None:
        self._running = False
        if self._task:
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass
        if self.pool:
            await self.pool.close()
        if self.redis:
            await self.redis.close()
        logger.info("persister_stopped")

    # ── Setup ────────────────────────────────────────────────────────────
    async def _apply_migration(self) -> None:
        try:
            with open(MIGRATION_PATH, "r", encoding="utf-8") as fh:
                sql = fh.read()
            async with self.pool.acquire() as conn:
                await conn.execute(sql)
            logger.info("migration_applied")
        except Exception as exc:  # noqa: BLE001
            logger.error("migration_failed", error=str(exc))
            raise

    async def _ensure_group(self) -> None:
        """Crea el consumer group leyendo desde el inicio del stream (id=0)."""
        try:
            await self.redis.xgroup_create(
                name=settings.redis_stream_key,
                groupname=settings.consumer_group,
                id="0",
                mkstream=True,
            )
            logger.info("consumer_group_created", group=settings.consumer_group)
        except aioredis.ResponseError as exc:
            if "BUSYGROUP" in str(exc):
                logger.info("consumer_group_exists", group=settings.consumer_group)
            else:
                raise

    # ── Consume loop ──────────────────────────────────────────────────────
    async def _consume_loop(self) -> None:
        # 1) Reclamar lo entregado-pero-no-confirmado (id="0") tras un reinicio.
        await self._drain("0")
        # 2) A partir de aquí, solo mensajes nuevos (">").
        while self._running:
            try:
                await self._drain(">")
            except asyncio.CancelledError:
                raise
            except Exception as exc:  # noqa: BLE001
                self._stats["errors"] += 1
                logger.error("consume_loop_error", error=str(exc))
                await asyncio.sleep(2)

    async def _drain(self, start_id: str) -> None:
        while self._running:
            resp = await self.redis.xreadgroup(
                groupname=settings.consumer_group,
                consumername=settings.consumer_name,
                streams={settings.redis_stream_key: start_id},
                count=settings.batch_size,
                block=settings.block_ms,
            )
            if not resp:
                if start_id == "0":
                    return  # backlog drenado
                continue

            entries = resp[0][1]
            if not entries:
                if start_id == "0":
                    return
                continue

            self._stats["messages_read"] += len(entries)

            rows: List[Tuple] = []
            ack_ids: List[str] = []
            for entry_id, fields in entries:
                row = self._build_row(fields)
                if row is not None:
                    rows.append(row)
                else:
                    self._stats["skipped"] += 1
                ack_ids.append(entry_id)  # ack siempre: lo malformado no se reintenta

            if rows:
                await self._insert_batch(rows)

            if ack_ids:
                await self.redis.xack(settings.redis_stream_key, settings.consumer_group, *ack_ids)

            if start_id == "0" and len(entries) < settings.batch_size:
                return

    # ── Normalización de las 3 fuentes ────────────────────────────────────
    def _build_row(self, fields: Dict[str, str]) -> Optional[Tuple]:
        """
        El stream lleva entradas {type, data, timestamp[, ticker_prices]}.
        type=news → data es un artículo de una de las 3 fuentes:
          - benzinga (OpenOutcrier): benzinga_id, sin id ni source
          - fmp:      id=fmp_<hash>, source=fmp
          - polygon:  id=poly_<id>,  source=polygon
        """
        if fields.get("type") != "news":
            return None  # catalyst_alert y otros tipos no se persisten aquí

        try:
            item: Dict[str, Any] = json.loads(fields.get("data", "{}"))
        except json.JSONDecodeError:
            return None

        title = (item.get("title") or "").strip()
        url = (item.get("url") or "").strip()
        if not title or not url:
            return None

        item_id = item.get("id")
        if not item_id:
            bz_id = item.get("benzinga_id")
            item_id = f"bz_{bz_id}" if bz_id else f"url_{hashlib.md5(url.encode()).hexdigest()[:16]}"

        source = item.get("source") or "benzinga"

        published = _parse_dt(item.get("published")) or _parse_dt(fields.get("timestamp"))
        if published is None:
            published = datetime.now(timezone.utc)

        insights = item.get("insights") or None
        ticker_prices_raw = fields.get("ticker_prices")

        images = item.get("images")
        if not images and item.get("image"):
            images = [item["image"]]

        return (
            str(item_id),
            source,
            title,
            item.get("teaser") or None,
            item.get("body") or None,
            url,
            item.get("author") or None,
            item.get("site") or None,
            [t for t in (item.get("tickers") or []) if t],
            [c for c in (item.get("channels") or []) if c],
            [t for t in (item.get("tags") or []) if t],
            item.get("sentiment") or None,
            json.dumps(insights) if insights else None,
            images or None,
            ticker_prices_raw if ticker_prices_raw else None,
            published,
            datetime.now(timezone.utc),
        )

    async def _insert_batch(self, rows: List[Tuple]) -> None:
        async with self.pool.acquire() as conn:
            await conn.executemany(_INSERT_SQL, rows)
        self._stats["rows_inserted"] += len(rows)
        self._stats["batches"] += 1
        self._stats["last_insert_at"] = datetime.now(timezone.utc).isoformat()
        logger.info("batch_inserted", rows=len(rows))

    def stats(self) -> Dict[str, Any]:
        return {**self._stats, "running": self._running}


persister = Persister()


@asynccontextmanager
async def lifespan(app: FastAPI):
    logger.info("starting_news_persister")
    await persister.start()
    yield
    logger.info("shutting_down")
    await persister.stop()


app = FastAPI(
    title="News Persister",
    description="Persiste el feed unificado de noticias en TimescaleDB y sirve la búsqueda del histórico",
    version="1.0.0",
    lifespan=lifespan,
)


@app.get("/health")
async def health():
    return {"status": "healthy", "service": "news-persister"}


@app.get("/status")
async def status():
    db_ok = False
    total = None
    try:
        if persister.pool:
            async with persister.pool.acquire() as conn:
                total = await conn.fetchval("SELECT count(*) FROM news_articles")
            db_ok = True
    except Exception:  # noqa: BLE001
        pass
    return {
        "status": "ok" if db_ok and persister._running else "degraded",
        "db": "connected" if db_ok else "disconnected",
        "articles_persisted": total,
        "consumer": persister.stats(),
        "timestamp": datetime.now(timezone.utc).isoformat(),
    }


# ── Búsqueda del histórico ────────────────────────────────────────────────

_LIST_COLS = (
    "id, source, title, teaser, url, publisher, site, tickers, channels, tags, "
    "sentiment, insights, published"
)


def _row_to_article(r: asyncpg.Record, include_body: bool = False) -> Dict[str, Any]:
    """Mapea una fila al shape NewsArticle que consume el frontend."""
    insights = r["insights"]
    if isinstance(insights, str):
        try:
            insights = json.loads(insights)
        except json.JSONDecodeError:
            insights = None

    article: Dict[str, Any] = {
        "id": r["id"],
        "title": r["title"],
        "author": r["publisher"] or "Unknown",
        "published": r["published"].isoformat(),
        "url": r["url"],
        "source": r["source"],
        "site": r["site"],
        "tickers": list(r["tickers"] or []),
        "channels": list(r["channels"] or []),
        "tags": list(r["tags"] or []),
        "teaser": r["teaser"],
        "sentiment": r["sentiment"],
        "insights": insights,
    }
    if include_body:
        article["body"] = r["body"]
    return article


@app.get("/api/v1/news/history")
async def news_history(
    q: Optional[str] = Query(None, description="Búsqueda full-text (websearch: comillas, OR, -exclusión)"),
    tickers: Optional[str] = Query(None, description="Tickers separados por coma"),
    sources: Optional[str] = Query(None, description="Fuentes: benzinga,fmp,polygon"),
    publisher: Optional[str] = Query(None, description="Publisher (subcadena, case-insensitive)"),
    channels: Optional[str] = Query(None, description="Canales separados por coma"),
    tags: Optional[str] = Query(None, description="Tags separados por coma"),
    date_from: Optional[str] = Query(None, description="Desde (ISO o YYYY-MM-DD)"),
    date_to: Optional[str] = Query(None, description="Hasta (ISO o YYYY-MM-DD)"),
    before: Optional[str] = Query(None, description="Cursor: published del último item recibido"),
    before_id: Optional[str] = Query(None, description="Cursor: id del último item (desempate)"),
    limit: int = Query(100, ge=1, le=500, description="Número de resultados"),
):
    """
    Búsqueda paginada sobre el histórico unificado (benzinga + fmp + polygon).
    Orden cronológico descendente. Para paginar hacia atrás pasa `before` (+
    `before_id`) del último resultado recibido.
    """
    if not persister.pool:
        raise HTTPException(status_code=503, detail="Service not ready")

    where: List[str] = []
    args: List[Any] = []

    def arg(value: Any) -> str:
        args.append(value)
        return f"${len(args)}"

    if q and q.strip():
        where.append(f"search_vec @@ websearch_to_tsquery('english', {arg(q.strip())})")
    if tickers:
        tick_list = [t.strip().upper() for t in tickers.split(",") if t.strip()]
        if tick_list:
            where.append(f"tickers && {arg(tick_list)}::text[]")
    if sources:
        src_list = [s.strip().lower() for s in sources.split(",") if s.strip()]
        if src_list:
            where.append(f"source = ANY({arg(src_list)}::text[])")
    if publisher and publisher.strip():
        where.append(f"publisher ILIKE {arg('%' + publisher.strip() + '%')}")
    if channels:
        ch_list = [c.strip() for c in channels.split(",") if c.strip()]
        if ch_list:
            where.append(f"channels && {arg(ch_list)}::text[]")
    if tags:
        tag_list = [t.strip() for t in tags.split(",") if t.strip()]
        if tag_list:
            where.append(f"tags && {arg(tag_list)}::text[]")

    dt_from = _parse_dt(date_from) if date_from else None
    if date_from and dt_from is None and len(date_from) == 10:
        dt_from = _parse_dt(date_from + "T00:00:00+00:00")
    dt_to = _parse_dt(date_to) if date_to else None
    if date_to and dt_to is None and len(date_to) == 10:
        dt_to = _parse_dt(date_to + "T23:59:59+00:00")
    if dt_from:
        where.append(f"published >= {arg(dt_from)}")
    if dt_to:
        where.append(f"published <= {arg(dt_to)}")

    dt_before = _parse_dt(before) if before else None
    if dt_before and before_id:
        where.append(f"(published, id) < ({arg(dt_before)}, {arg(before_id)})")
    elif dt_before:
        where.append(f"published < {arg(dt_before)}")

    where_sql = ("WHERE " + " AND ".join(where)) if where else ""
    body_col = ", body" if q else ", NULL as body"  # body solo se transporta si hubo query de texto
    sql = (
        f"SELECT {_LIST_COLS}{body_col} FROM news_articles {where_sql} "
        f"ORDER BY published DESC, id DESC LIMIT {arg(limit)}"
    )

    async with persister.pool.acquire() as conn:
        rows = await conn.fetch(sql, *args)

    results = [_row_to_article(r, include_body=bool(q)) for r in rows]

    next_cursor = None
    if len(rows) == limit:
        last = rows[-1]
        next_cursor = {"before": last["published"].isoformat(), "before_id": last["id"]}

    return {
        "status": "OK",
        "count": len(results),
        "results": results,
        "next_cursor": next_cursor,
    }


# ── Extracción de artículos (lector nativo) ──────────────────────────────
# El frontend renderiza el cuerpo con su propia tipografía (estilo terminal),
# sin iframes ni mandar al usuario fuera. Cache en Redis para no re-golpear
# a los publishers. Whitelist de dominios = anti-SSRF.

EXTRACT_ALLOWED_DOMAINS = (
    "benzinga.com", "reuters.com", "newsfilecorp.com", "globenewswire.com",
    "prnewswire.com", "businesswire.com", "accesswire.com", "acnnewswire.com",
    "fool.com", "zacks.com", "investors.com", "marketwatch.com", "cnbc.com",
    "yahoo.com", "finance.yahoo.com", "seekingalpha.com", "bloomberg.com",
    "barrons.com", "investorplace.com", "247wallst.com", "thestreet.com",
    "fxempire.com", "financialmodelingprep.com",
    "nasdaq.com", "tradingview.com", "usnews.com", "investing.com",
)
EXTRACT_CACHE_PREFIX = "news:extract:"
EXTRACT_TTL_OK = 604800   # 7 días — el contenido de un artículo no cambia
EXTRACT_TTL_FAIL = 3600   # 1 hora — reintentable (bloqueos temporales)

_CHROME_UA = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
)

# Renderer self-hosted (news-renderer / Chromium): renderiza el JS de la página
# y devuelve el HTML final. Resuelve shells JS (MSN, Yahoo…) y anti-bot ligero
# sin depender de servicios externos ni API keys.
RENDERER_URL = os.environ.get("RENDERER_URL", "http://news-renderer:8074")
# Capas pesadas (render de espejos/URL original): rapidas y fiables solo con
# egress US. Por defecto OFF para no penalizar la UX desde datacenter UE.
HEAVY_EXTRACT = os.environ.get("HEAVY_EXTRACT", "false").lower() == "true"


async def _render(url: str) -> Optional[Dict[str, Any]]:
    """Pide a news-renderer la página renderizada: {html, text, title, byline}."""
    try:
        async with httpx.AsyncClient(timeout=90.0) as client:
            resp = await client.get(f"{RENDERER_URL}/render", params={"url": url})
        if resp.status_code != 200:
            return None
        data = resp.json()
        return data if data.get("ok") else None
    except Exception as exc:  # noqa: BLE001
        logger.warning("render_error", url=url[:120], error=str(exc))
        return None


async def _render_text(url: str) -> Optional[Tuple[str, Optional[str], Optional[str]]]:
    """Texto del artículo renderizado (Readability; trafilatura de respaldo).
    Devuelve (text, title, byline) o None."""
    data = await _render(url)
    if not data:
        return None
    text = (data.get("text") or "").strip()
    if len(text) >= 400:
        return text, data.get("title"), data.get("byline")
    # Respaldo: trafilatura sobre el HTML renderizado
    doc = await _bare_extract(data.get("html") or "", url)
    t2 = _doc_text(doc)
    if t2 and len(t2) >= 400:
        get = (lambda k: doc.get(k)) if isinstance(doc, dict) else (lambda k: getattr(doc, k, None))
        return t2, get("title"), get("author")
    return None


async def _bare_extract(html: str, url: str):
    """trafilatura sobre HTML (fuera del event loop). Devuelve el doc o None."""
    try:
        return await asyncio.to_thread(
            trafilatura.bare_extraction, html,
            url=url, favor_precision=True, include_comments=False,
        )
    except Exception:  # noqa: BLE001
        return None


def _doc_text(doc) -> Optional[str]:
    if not doc:
        return None
    text = doc.get("text") if isinstance(doc, dict) else getattr(doc, "text", None)
    return text.strip() if text else None


async def _extract_via_renderer(url: str, host: str, teaser: Optional[str] = None) -> Optional[Dict[str, Any]]:
    """Último recurso: renderiza la URL original con nuestro Chromium y extrae."""
    res = await _render_text(url)
    if not res:
        return None
    text, r_title, r_by = res
    if len(text) < 600:
        return None
    if teaser and not _verify_same_story(teaser, text):
        return None
    logger.info("renderer_hit", host=host)
    return {"ok": True, "title": r_title, "byline": r_by, "date": None, "site": host, "text": text}


def _extract_host_allowed(host: str) -> bool:
    return any(host == d or host.endswith("." + d) for d in EXTRACT_ALLOWED_DOMAINS)


# ── Sindicación: el mismo texto del wire, en un dominio que sí se deja leer ──
# Las historias de Reuters (y otros wires) se republican textualmente bajo
# licencia en portales como Yahoo Finance. Cadena: título → Google News RSS →
# decodificar el link ofuscado de Google → extraer la copia sindicada.

import re as _re
from urllib.parse import quote_plus as _quote_plus


def _norm_tokens(s: str) -> set:
    return {t for t in _re.sub(r"[^a-z0-9 ]", " ", (s or "").lower()).split() if len(t) > 2}


def _slug_tokens(url: str) -> set:
    """Tokens del slug del artículo (sin fecha): estables aunque se retitule."""
    from urllib.parse import urlparse as _urlparse
    path = (_urlparse(url).path or "").rstrip("/")
    slug = path.rsplit("/", 1)[-1]
    slug = _re.sub(r"-\d{4}-\d{2}-\d{2}$", "", slug)  # sufijo de fecha de Reuters
    slug = _re.sub(r"\.html?$", "", slug)
    return {t for t in slug.split("-") if len(t) > 2 and not t.isdigit()}


def _verify_same_story(teaser: Optional[str], text: str) -> bool:
    """
    La sindicación de un wire es literal: el cuerpo del espejo contiene las
    frases del teaser original. Otra historia del mismo tema, no. Se exige que
    ≥40% de los 3-gramas del teaser aparezcan verbatim en el texto extraído.
    """
    if not teaser or len(teaser) < 60:
        return True  # sin teaser no se puede verificar: se acepta el mejor match
    norm = lambda s: _re.sub(r"[^a-z0-9 ]", " ", s.lower())
    t_words = norm(teaser).split()
    grams = [" ".join(t_words[i:i + 3]) for i in range(0, min(len(t_words) - 2, 40))]
    if not grams:
        return True
    hay = norm(text)
    hits = sum(1 for g in grams if g in hay)
    return hits / len(grams) >= 0.4


def _verify_same_story(teaser: Optional[str], text: str) -> bool:
    """
    La sindicación de un wire es literal: el cuerpo del espejo contiene las
    frases del teaser original. Otra historia del mismo tema, no. Se exige que
    ≥40% de los 3-gramas del teaser aparezcan verbatim en el texto extraído.
    """
    if not teaser or len(teaser) < 60:
        return True  # sin teaser no se puede verificar: se acepta el mejor match
    norm = lambda s: _re.sub(r"[^a-z0-9 ]", " ", s.lower())
    t_words = norm(teaser).split()
    grams = [" ".join(t_words[i:i + 3]) for i in range(0, min(len(t_words) - 2, 40))]
    if not grams:
        return True
    hay = norm(text)
    hits = sum(1 for g in grams if g in hay)
    return hits / len(grams) >= 0.4


async def _extract_via_syndication(title: Optional[str], teaser: Optional[str], host: str, orig_url: str) -> Optional[Dict[str, Any]]:
    """
    Busca la copia sindicada del wire (Yahoo, Investing, Nasdaq... republican
    el texto literal bajo licencia) via Google News RSS, que da fuente y
    titulo fiables, y renderiza cada candidato con nuestro Chromium (que sigue
    el redirect de Google y aterriza en el articulo). Verificacion final por
    3-gramas del teaser: nunca devuelve otra historia.
    """
    if not title or len(title) < 20:
        return None
    want_title = _norm_tokens(title)
    if not want_title:
        return None
    import xml.etree.ElementTree as ET
    from urllib.parse import urlparse as _urlparse
    root_dom = host.split(".", 1)[-1] if host.count(".") > 1 else host

    async with httpx.AsyncClient(timeout=20.0, follow_redirects=True,
                                 headers={"User-Agent": _CHROME_UA}) as client:
        try:
            rss = await client.get(
                "https://news.google.com/rss/search",
                params={"q": title, "hl": "en-US", "gl": "US", "ceid": "US:en"},
            )
            root = ET.fromstring(rss.text)
        except Exception:  # noqa: BLE001
            return None

        candidates: List[Tuple[float, float, str, str]] = []
        for item in list(root.iter("item"))[:10]:
            gl = item.findtext("link") or ""
            if not gl:
                continue
            it_title = (item.findtext("title") or "").rsplit(" - ", 1)[0]
            overlap = len(want_title & _norm_tokens(it_title)) / max(1, len(want_title))
            src_el = item.find("source")
            src_host = (_urlparse(src_el.get("url")).hostname or "").lower() if src_el is not None else ""
            if overlap < 0.55 or src_host.endswith(root_dom):
                continue
            # Boost a los espejos que republican el texto literal del wire
            prio = 1.0 if any(m in src_host for m in (
                "yahoo.com", "msn.com", "nasdaq.com", "investing.com", "tradingview.com")) else 0.0
            candidates.append((prio, overlap, gl, src_host))

        # Solo espejos verbatim del wire (prio=1): rapido y verificable. Si no hay
        # ninguno, retornamos ya y el visor muestra la tarjeta nativa (teaser).
        candidates = [c for c in candidates if c[0] >= 1.0]
        candidates.sort(reverse=True)
        logger.info("syndication_gnews", title=title[:50], candidates=len(candidates))
        if not candidates:
            return None
        for _prio, overlap, gl, src_host in candidates[:2]:
            res = await _render_text(gl)
            if not res:
                continue
            text, r_title, r_by = res
            if len(text) < 600:
                continue
            if not _verify_same_story(teaser, text):
                logger.info("syndication_rejected", copy=src_host, overlap=round(overlap, 2))
                continue
            logger.info("syndication_hit", original=host, copy=src_host, overlap=round(overlap, 2))
            return {
                "ok": True,
                "title": r_title or title,
                "byline": r_by,
                "date": None,
                "site": host,
                "text": text,
            }
    return None


@app.get("/api/v1/news/extract")
async def news_extract(url: str = Query(..., description="URL del artículo a extraer")):
    """
    Extrae el cuerpo legible de un artículo (trafilatura) para renderizarlo
    nativo en la UI. {ok, title, byline, date, site, text} — text con párrafos
    separados por saltos de línea. ok=false si el dominio no está permitido,
    el publisher bloquea (p. ej. Reuters/DataDome) o no hay texto extraíble.
    """
    from urllib.parse import urlparse

    parsed = urlparse(url)
    host = (parsed.hostname or "").lower()
    if parsed.scheme not in ("http", "https") or not host or not _extract_host_allowed(host):
        return {"ok": False, "reason": "domain_not_allowed", "site": host}

    cache_key = EXTRACT_CACHE_PREFIX + hashlib.md5(url.encode()).hexdigest()
    if persister.redis:
        cached = await persister.redis.get(cache_key)
        if cached:
            try:
                return json.loads(cached)
            except json.JSONDecodeError:
                pass

    result: Dict[str, Any]
    try:
        async with httpx.AsyncClient(timeout=15.0, follow_redirects=True) as client:
            resp = await client.get(url, headers={
                "User-Agent": _CHROME_UA,
                "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
                "Accept-Language": "en-US,en;q=0.9",
            })
        if resp.status_code != 200:
            result = {"ok": False, "reason": f"http_{resp.status_code}", "site": host}
        else:
            # trafilatura es CPU-bound síncrono → fuera del event loop
            doc = await asyncio.to_thread(
                trafilatura.bare_extraction, resp.text,
                url=url, favor_precision=True, include_comments=False,
            )
            text = (doc or {}).get("text") if isinstance(doc, dict) else getattr(doc, "text", None)
            if not text or len(text.strip()) < 200:
                result = {"ok": False, "reason": "no_content", "site": host}
            else:
                get = (lambda k: doc.get(k)) if isinstance(doc, dict) else (lambda k: getattr(doc, k, None))
                result = {
                    "ok": True,
                    "title": get("title"),
                    "byline": get("author"),
                    "date": get("date"),
                    "site": get("sitename") or host,
                    "text": text.strip(),
                }
    except Exception as exc:  # noqa: BLE001
        logger.warning("extract_failed", url=url[:120], error=str(exc))
        result = {"ok": False, "reason": "fetch_error", "site": host}

    # Fallback 1: sindicación — el mismo texto del wire en un dominio legible
    # (título desde nuestra propia tabla; gratis y self-hosted). Capa pesada.
    if not result.get("ok") and HEAVY_EXTRACT and persister.pool:
        try:
            async with persister.pool.acquire() as conn:
                row = await conn.fetchrow(
                    "SELECT title, teaser FROM news_articles WHERE url = $1 ORDER BY published DESC LIMIT 1", url
                )
            syndicated = await _extract_via_syndication(
                row["title"] if row else None, row["teaser"] if row else None, host, url
            )
            if syndicated:
                result = syndicated
        except Exception as exc:  # noqa: BLE001
            logger.warning("syndication_error", error=str(exc))

    # Fallback 2: renderer self-hosted (Chromium) sobre la URL original. Capa pesada.
    if not result.get("ok") and HEAVY_EXTRACT:
        rendered = await _extract_via_renderer(url, host)
        if rendered:
            result = rendered

    if persister.redis:
        ttl = EXTRACT_TTL_OK if result.get("ok") else EXTRACT_TTL_FAIL
        await persister.redis.set(cache_key, json.dumps(result), ex=ttl)

    return result


if __name__ == "__main__":
    uvicorn.run(
        "main:app",
        host="0.0.0.0",
        port=settings.service_port,
        reload=False,
        log_level=settings.log_level.lower(),
    )
