"""
News Renderer Service

Navegador headless (Playwright/Chromium) self-hosted que renderiza el JavaScript
de una página y devuelve el HTML final. Sustituye a servicios externos tipo Jina:
sin API key, sin límites, sin que el tráfico salga a un tercero.

Resuelve dos casos que un fetch HTTP plano no puede:
  1. Shells JS (MSN, Yahoo…) donde el cuerpo del artículo se pinta client-side.
  2. Publishers con anti-bot ligero, con fingerprint de navegador real + stealth.

Un único Chromium persistente; cada request usa su propio contexto (aislado) y
página, con semáforo de concurrencia para acotar RAM. news-persister lo llama
como capa de extracción; la extracción del texto (trafilatura) se queda allí.
"""

import asyncio
import logging
import os
import re
import time
import sys
from contextlib import asynccontextmanager
from typing import Optional

import structlog
import uvicorn
from fastapi import FastAPI, Query
from playwright.async_api import async_playwright, Browser, Playwright

from config import settings

logging.basicConfig(format="%(message)s", stream=sys.stdout, level=logging.INFO, force=True)
structlog.configure(
    processors=[
        structlog.stdlib.add_log_level,
        structlog.processors.TimeStamper(fmt="iso"),
        structlog.processors.JSONRenderer(),
    ],
    wrapper_class=structlog.stdlib.BoundLogger,
    logger_factory=structlog.PrintLoggerFactory(),
    cache_logger_on_first_use=False,
)
logger = structlog.get_logger(__name__)

_READABILITY_JS = open(os.path.join(os.path.dirname(__file__), "readability.js"),
                        encoding="utf-8").read()
_READABILITY_RUN = """() => {
  try {
    const documentClone = document.cloneNode(true);
    const r = new Readability(documentClone).parse();
    return r ? {title: r.title, byline: r.byline, text: r.textContent} : null;
  } catch (e) { return null; }
}"""

_UA = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
)

# Anti-headless mínimo: navigator.webdriver=false + plugins/languages plausibles.
# Suficiente para shells JS (MSN/Yahoo) y anti-bot ligero; no promete DataDome duro.
_STEALTH_JS = """
Object.defineProperty(navigator, 'webdriver', { get: () => undefined });
Object.defineProperty(navigator, 'plugins', { get: () => [1, 2, 3, 4, 5] });
Object.defineProperty(navigator, 'languages', { get: () => ['en-US', 'en'] });
window.chrome = { runtime: {} };
"""


# Selectores/textos de los banners de cookies mas comunes (IP datacenter UE).
# Aceptarlos es lo que hace un usuario normal para leer la pagina.
_ACCEPT_SELECTORS = (
    "#onetrust-accept-btn-handler",
    ".fc-cta-consent",
    "button.fc-button.fc-cta-consent",
    "[aria-label='Accept all']",
    "button[mode='primary']",
)
_ACCEPT_TEXTS = re.compile(
    r"^(accept all|accept|i agree|agree|i accept|allow all|consent|"
    r"aceptar todo|aceptar|hyv\u00e4ksy kaikki|hyv\u00e4ksy|zustimmen|"
    r"alle akzeptieren|tout accepter|accepter)$",
    re.I,
)


async def _accept_consent(page) -> bool:
    """Intenta cerrar un banner de cookies. True si pulso algo."""
    for sel in _ACCEPT_SELECTORS:
        try:
            el = page.locator(sel).first
            if await el.count() and await el.is_visible():
                await el.click(timeout=3000)
                return True
        except Exception:  # noqa: BLE001
            pass
    for frame in page.frames:
        try:
            btn = frame.get_by_role("button", name=_ACCEPT_TEXTS)
            if await btn.count():
                await btn.first.click(timeout=3000)
                return True
        except Exception:  # noqa: BLE001
            pass
    return False


def _parse_proxy(raw: str) -> Optional[dict]:
    """Devuelve el dict de proxy para Playwright, o None. Acepta:
       - Webshare: "ip:puerto:usuario:password"
       - URL:      "http://usuario:password@host:puerto" | "http://host:puerto"
    """
    raw = (raw or "").strip()
    if not raw:
        return None
    # Formato Webshare: 4 partes separadas por ':' y sin esquema
    if "://" not in raw and raw.count(":") == 3:
        ip, port, user, pwd = raw.split(":")
        return {"server": f"http://{ip}:{port}", "username": user, "password": pwd}
    # Formato URL
    from urllib.parse import urlparse
    if "://" not in raw:
        raw = "http://" + raw
    u = urlparse(raw)
    if not u.hostname:
        return None
    proxy = {"server": f"{u.scheme}://{u.hostname}:{u.port or 80}"}
    if u.username:
        proxy["username"] = u.username
        proxy["password"] = u.password or ""
    return proxy


class Renderer:
    def __init__(self) -> None:
        self._pw: Optional[Playwright] = None
        self._browser: Optional[Browser] = None
        self._sem = asyncio.Semaphore(settings.max_concurrency)
        self._lock = asyncio.Lock()

    async def start(self) -> None:
        self._pw = await async_playwright().start()
        await self._launch()
        logger.info("renderer_started", concurrency=settings.max_concurrency)

    async def _launch(self) -> None:
        launch_kwargs = {
            "headless": True,
            "args": [
                "--no-sandbox",
                "--disable-dev-shm-usage",
                "--disable-gpu",
                "--disable-blink-features=AutomationControlled",
            ],
        }
        # Egress US opcional: elimina los muros GDPR y acelera todo (proxy del usuario)
        proxy = _parse_proxy(settings.proxy_url)
        if proxy:
            launch_kwargs["proxy"] = proxy
            logger.info("proxy_enabled", server=proxy["server"])
        self._browser = await self._pw.chromium.launch(**launch_kwargs)

    async def stop(self) -> None:
        if self._browser:
            await self._browser.close()
        if self._pw:
            await self._pw.stop()
        logger.info("renderer_stopped")

    async def _ensure_browser(self) -> Browser:
        if self._browser and self._browser.is_connected():
            return self._browser
        async with self._lock:
            if not (self._browser and self._browser.is_connected()):
                logger.warning("browser_relaunch")
                await self._launch()
        return self._browser

    async def render(self, url: str) -> dict:
        async with self._sem:
            browser = await self._ensure_browser()
            context = await browser.new_context(
                user_agent=_UA,
                locale="en-US",
                viewport={"width": 1366, "height": 900},
                java_script_enabled=True,
            )
            try:
                await context.add_init_script(_STEALTH_JS)
                page = await context.new_page()
                # Bloquea imágenes/media/fuentes: no las necesitamos y ahorran RAM/tiempo
                await page.route(
                    "**/*",
                    lambda route: route.abort()
                    if route.request.resource_type in ("image", "media", "font")
                    else route.continue_(),
                )
                resp = await page.goto(url, wait_until="commit", timeout=settings.nav_timeout_ms)
                status = resp.status if resp else 0

                # Cadena de muros de cookies (Google News → consent → publisher →
                # consent del publisher). Aceptamos cada banner con esperas cortas
                # y fijas: networkidle se cuelga en sitios pesados (Yahoo, 55s).
                # 1) Cierra pasarelas (Google News, muros de cookies) mientras la URL
                #    este en un host-puerta. Acotado a 12s.
                gate_deadline = time.monotonic() + 12.0
                while time.monotonic() < gate_deadline:
                    host = page.url.split("/")[2] if "://" in page.url else ""
                    on_gateway = ("consent." in host or "guce." in host or "google.com" in host)
                    accepted = await _accept_consent(page)
                    if on_gateway or accepted:
                        try:
                            await page.wait_for_load_state("domcontentloaded", timeout=6000)
                        except Exception:  # noqa: BLE001
                            pass
                        await page.wait_for_timeout(600)
                        continue
                    break

                # 2) Inyecta Readability y sondea el DOM hasta que el CUERPO real
                #    aparezca (adaptativo): ligeras vuelven rapido, SPAs esperan lo
                #    justo. Tope 22s → nunca se cuelga.
                try:
                    await page.add_script_tag(content=_READABILITY_JS)
                except Exception:  # noqa: BLE001
                    pass
                article = None
                body_deadline = time.monotonic() + 22.0
                while time.monotonic() < body_deadline:
                    try:
                        article = await page.evaluate(_READABILITY_RUN)
                    except Exception:  # noqa: BLE001
                        article = None
                    if article and len((article.get("text") or "")) >= 800:
                        break
                    # por si aparece un banner tardio en el publisher
                    await _accept_consent(page)
                    await page.wait_for_timeout(1200)

                html = await page.content()
                final_url = page.url
                return {
                    "ok": True,
                    "status": status,
                    "final_url": final_url,
                    "html": html,
                    "title": (article or {}).get("title"),
                    "byline": (article or {}).get("byline"),
                    "text": (article or {}).get("text"),
                }
            except Exception as exc:  # noqa: BLE001
                logger.warning("render_failed", url=url[:120], error=str(exc))
                return {"ok": False, "status": 0, "html": None, "error": str(exc)}
            finally:
                await context.close()


renderer = Renderer()


@asynccontextmanager
async def lifespan(app: FastAPI):
    logger.info("starting_news_renderer")
    await renderer.start()
    yield
    await renderer.stop()


app = FastAPI(title="News Renderer", version="1.0.0", lifespan=lifespan)


@app.get("/health")
async def health():
    ok = bool(renderer._browser and renderer._browser.is_connected())
    return {"status": "healthy" if ok else "degraded", "service": "news-renderer"}


@app.get("/render")
async def render(url: str = Query(..., description="URL a renderizar con JS")):
    """Renderiza la página con Chromium y devuelve el HTML final (post-JS)."""
    return await renderer.render(url)


if __name__ == "__main__":
    uvicorn.run("main:app", host="0.0.0.0", port=settings.service_port, log_level=settings.log_level.lower())
