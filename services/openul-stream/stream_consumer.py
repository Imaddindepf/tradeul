"""
X Filtered Stream Consumer

Connects to X API v2 Filtered Stream, parses tweets, and publishes
to Redis Stream + Sorted Set for real-time distribution and persistence.

Flow: X servers --> HTTP stream --> parse JSON --> format --> Redis Stream
"""

import asyncio
import base64
import json
import math
import re
import time
from datetime import datetime, timezone
from typing import Optional, Dict, Any, List
from urllib.parse import urlparse

import httpx
import redis.asyncio as aioredis
import structlog
import orjson

from config import settings

logger = structlog.get_logger(__name__)

X_API_BASE = "https://api.x.com/2"
X_OAUTH2_TOKEN_URL = "https://api.x.com/oauth2/token"
X_STREAM_URL = f"{X_API_BASE}/tweets/search/stream"
X_STREAM_RULES_URL = f"{X_API_BASE}/tweets/search/stream/rules"


class XFilteredStreamConsumer:
    """
    Manages the X Filtered Stream connection lifecycle:
    1. Obtains Bearer token from consumer credentials
    2. Syncs filter rules (from:user for each monitored account)
    3. Connects to streaming endpoint
    4. Parses incoming tweets and publishes to Redis
    """

    def __init__(self, redis_client: aioredis.Redis):
        self._redis = redis_client
        self._bearer_token: Optional[str] = None
        self._running = False
        self._task: Optional[asyncio.Task] = None
        self._recent_hashes: dict[int, float] = {}
        self._stats = {
            "tweets_received": 0,
            "tweets_published": 0,
            "duplicates_skipped": 0,
            "errors": 0,
            "reconnects": 0,
            "connected_since": None,
            "last_tweet_at": None,
        }

    async def get_bearer_token(self) -> str:
        creds = base64.b64encode(
            f"{settings.x_consumer_key}:{settings.x_consumer_secret}".encode()
        ).decode()

        async with httpx.AsyncClient(timeout=10) as client:
            resp = await client.post(
                X_OAUTH2_TOKEN_URL,
                headers={
                    "Authorization": f"Basic {creds}",
                    "Content-Type": "application/x-www-form-urlencoded;charset=UTF-8",
                },
                data={"grant_type": "client_credentials"},
            )
            resp.raise_for_status()
            token = resp.json()["access_token"]
            logger.info("bearer_token_obtained")
            return token

    def _auth_headers(self) -> Dict[str, str]:
        return {"Authorization": f"Bearer {self._bearer_token}"}

    async def _sync_rules(self):
        """Ensure filter rules match monitored_users exactly."""
        async with httpx.AsyncClient(timeout=15) as client:
            # Get existing rules
            resp = await client.get(X_STREAM_RULES_URL, headers=self._auth_headers())
            resp.raise_for_status()
            existing = resp.json().get("data", [])

            desired_rules = {f"from:{u}": u for u in settings.monitored_users}
            existing_values = {r["value"]: r["id"] for r in existing}

            # Delete stale rules
            ids_to_delete = [
                rid for val, rid in existing_values.items() if val not in desired_rules
            ]
            if ids_to_delete:
                await client.post(
                    X_STREAM_RULES_URL,
                    headers=self._auth_headers(),
                    json={"delete": {"ids": ids_to_delete}},
                )
                logger.info("deleted_stale_rules", count=len(ids_to_delete))

            # Add missing rules
            rules_to_add = [
                {"value": val, "tag": tag}
                for val, tag in desired_rules.items()
                if val not in existing_values
            ]
            if rules_to_add:
                resp = await client.post(
                    X_STREAM_RULES_URL,
                    headers=self._auth_headers(),
                    json={"add": rules_to_add},
                )
                resp.raise_for_status()
                data = resp.json()
                created = len(data.get("data", []))
                errors = data.get("errors", [])
                logger.info("rules_synced", created=created, errors=len(errors))
                if errors:
                    for e in errors:
                        logger.warning("rule_error", detail=e)
            else:
                logger.info("rules_already_synced", count=len(existing_values))

    _TICKER_RE = re.compile(r'\$([A-Z]{1,5})\b')
    _RT_PREFIX_RE = re.compile(r'^RT\s+@\w+:\s*', re.IGNORECASE)
    _MENTION_RE = re.compile(r'@\w+')
    _TCO_URL_RE = re.compile(r'https?://t\.co/\S+')

    def _extract_tickers(self, text: str) -> List[str]:
        """Extract $TICKER symbols from text."""
        return list(dict.fromkeys(self._TICKER_RE.findall(text)))

    _X_DOMAINS = {"twitter.com", "x.com", "mobile.twitter.com"}

    def _get_referenced_tweet(self, event: Dict[str, Any]) -> Optional[Dict]:
        """Get the first referenced tweet object from includes."""
        includes = event.get("includes", {})
        tweets = includes.get("tweets", [])
        return tweets[0] if tweets else None

    def _get_referenced_text(self, ref_tweet: Dict[str, Any]) -> Optional[str]:
        """Extract full text from a referenced tweet object."""
        note = ref_tweet.get("note_tweet")
        if note and isinstance(note, dict):
            return note.get("text")
        return ref_tweet.get("text")

    def _resolve_urls(self, text: str, entities: Optional[Dict]) -> tuple[str, List[str]]:
        """
        Replace t.co URLs using entities.urls expanded_url.
        - x.com/twitter.com URLs → removed from text
        - External URLs → kept in text as expanded_url
        Returns (cleaned_text, list_of_external_urls).
        """
        external_urls: List[str] = []
        if not entities:
            text = self._TCO_URL_RE.sub("", text)
            return text.strip(), external_urls

        url_map: dict[str, str] = {}
        for u in entities.get("urls", []):
            tco = u.get("url", "")
            expanded = u.get("expanded_url", "")
            if not tco or not expanded:
                continue
            try:
                domain = urlparse(expanded).netloc.lower().lstrip("www.")
            except Exception:
                domain = ""

            if domain in self._X_DOMAINS:
                url_map[tco] = ""
            else:
                url_map[tco] = expanded
                external_urls.append(expanded)

        for tco, replacement in url_map.items():
            text = text.replace(tco, replacement)

        text = self._TCO_URL_RE.sub("", text)
        return text.strip(), external_urls

    def _extract_media(self, event: Dict[str, Any]) -> List[Dict[str, str]]:
        """Extract media URLs from includes.media."""
        includes = event.get("includes", {})
        media_list = includes.get("media", [])
        result = []
        for m in media_list:
            mtype = m.get("type", "")
            url = m.get("url") or m.get("preview_image_url") or ""
            if url:
                result.append({"type": mtype, "url": url})
        return result

    def _clean_text(self, text: str) -> str:
        """Remove RT prefixes and @mentions from text."""
        text = self._RT_PREFIX_RE.sub("", text)
        text = self._MENTION_RE.sub("", text)
        text = re.sub(r'\s{2,}', ' ', text).strip()
        return text

    def _is_duplicate(self, text: str) -> bool:
        """Check if we've seen near-identical text in the last 10 minutes."""
        now = time.time()
        cutoff = now - 600

        self._recent_hashes = {
            h: ts for h, ts in self._recent_hashes.items() if ts > cutoff
        }

        normalized = re.sub(r'\s+', ' ', text.strip().upper())
        h = hash(normalized[:200])

        if h in self._recent_hashes:
            return True

        self._recent_hashes[h] = now
        return False

    def _parse_tweet(self, event: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        """Parse a streaming event into a normalized news item."""
        data = event.get("data")
        if not data:
            return None

        entities = data.get("entities")
        referenced = data.get("referenced_tweets", [])
        is_rt = any(r.get("type") == "retweeted" for r in referenced)
        is_quote = any(r.get("type") == "quoted" for r in referenced)

        ref_entities = None
        text = data.get("text", "")
        note_tweet = data.get("note_tweet")
        if note_tweet and isinstance(note_tweet, dict):
            text = note_tweet.get("text", text)

        if is_rt or is_quote:
            ref_tweet = self._get_referenced_tweet(event)
            if ref_tweet:
                ref_text = self._get_referenced_text(ref_tweet)
                ref_entities = ref_tweet.get("entities")
                if ref_text:
                    ref_text = self._clean_text(ref_text)
                    if is_rt:
                        text = ref_text
                        entities = ref_entities
                    elif is_quote:
                        own_text = self._clean_text(text)
                        text = f"{own_text}\n{ref_text}" if own_text else ref_text

        text = self._clean_text(text)
        text, external_urls = self._resolve_urls(text, entities)

        if not text:
            return None

        if self._is_duplicate(text):
            self._stats["duplicates_skipped"] += 1
            logger.debug("duplicate_skipped", text_preview=text[:60])
            return None

        media = self._extract_media(event)

        now_utc = datetime.now(timezone.utc)
        tweet_id = data.get("id", "")
        created_at = data.get("created_at", now_utc.isoformat())

        tickers = self._extract_tickers(text)

        item: Dict[str, Any] = {
            "id": f"opn_{tweet_id}",
            "text": text,
            "tickers": tickers,
            "created_at": created_at,
            "received_at": now_utc.isoformat(),
            "received_ts": now_utc.timestamp(),
        }

        if media:
            item["media"] = media
        if external_urls:
            item["urls"] = external_urls

        return item

    async def _get_ticker_snapshot(self, ticker: str) -> Optional[Dict[str, Any]]:
        """Read real-time ticker data from the enriched snapshot hash."""
        try:
            raw = await self._redis.hget("snapshot:enriched:latest", ticker)
            if not raw:
                return None
            return orjson.loads(raw)
        except Exception:
            return None

    async def _subscribe_quotes(self, tickers: List[str]):
        """Ask polygon_ws to subscribe to real-time quotes for tickers."""
        pipe = self._redis.pipeline()
        for t in tickers:
            pipe.xadd(
                "polygon_ws:quote_subscriptions",
                {"symbol": t, "action": "subscribe"},
            )
        await pipe.execute()

    async def _unsubscribe_quotes(self, tickers: List[str]):
        """Ask polygon_ws to unsubscribe from real-time quotes."""
        pipe = self._redis.pipeline()
        for t in tickers:
            pipe.xadd(
                "polygon_ws:quote_subscriptions",
                {"symbol": t, "action": "unsubscribe"},
            )
        await pipe.execute()

    async def _read_latest_quote(self, ticker: str) -> Optional[Dict[str, Any]]:
        """Read the most recent quote for a ticker from the quotes stream."""
        try:
            results = await self._redis.xrevrange(
                "stream:realtime:quotes", "+", "-", count=50,
            )
            for _msg_id, fields in results:
                if fields.get(b"symbol", b"").decode() == ticker:
                    return {
                        "bid": float(fields.get(b"bid_price", 0)),
                        "ask": float(fields.get(b"ask_price", 0)),
                        "bid_size": int(fields.get(b"bid_size", 0)),
                        "ask_size": int(fields.get(b"ask_size", 0)),
                        "ts": int(fields.get(b"timestamp", 0)),
                    }
        except Exception:
            pass
        return None

    def _get_midpoint(self, quote: Dict[str, Any]) -> float:
        bid, ask = quote["bid"], quote["ask"]
        if bid > 0 and ask > 0:
            return (bid + ask) / 2
        return bid or ask

    def _compute_z_score(
        self, change_pct: float, atr_pct: float, delay_seconds: int
    ) -> float:
        """
        Normalize the observed move against expected volatility for the
        measurement window using ATR scaling.

        ATR is a daily measure (~390 trading minutes). We scale it down to
        the observation window and convert to a z-score-like ratio.
        """
        if atr_pct <= 0:
            return abs(change_pct) / 0.5 if change_pct else 0.0

        minutes = max(delay_seconds / 60, 0.5)
        expected_move_pct = atr_pct / math.sqrt(390 / minutes)
        return abs(change_pct) / expected_move_pct if expected_move_pct > 0 else 0.0

    async def _check_price_reactions(self, item: Dict[str, Any]):
        """
        Detect statistically anomalous price reactions to a headline
        using real-time NBBO quotes and ATR-normalized z-scores.

        Polls every POLL_INTERVAL seconds for up to MONITOR_DURATION seconds.
        Publishes a reaction the instant z >= Z_THRESHOLD (once per ticker).
        """
        Z_THRESHOLD = 2.0
        POLL_INTERVAL = 3
        MONITOR_DURATION = 120

        tickers = item.get("tickers", [])
        if not tickers:
            return

        tickers = tickers[:5]

        ref_data: dict[str, dict] = {}
        for ticker in tickers:
            snap = await self._get_ticker_snapshot(ticker)
            if not snap:
                continue
            lt = snap.get("lastTrade", {})
            price = lt.get("p", 0) or snap.get("current_price", 0)
            atr_pct = snap.get("atr_percent", 0) or 0
            if price <= 0:
                continue
            ref_data[ticker] = {"price": price, "atr_pct": atr_pct}

        if not ref_data:
            return

        tracked = list(ref_data.keys())
        await self._subscribe_quotes(tracked)
        await asyncio.sleep(2)

        for ticker in tracked:
            q = await self._read_latest_quote(ticker)
            if q:
                mid = self._get_midpoint(q)
                if mid > 0:
                    ref_data[ticker]["price"] = mid

        logger.info(
            "reaction_tracking_started",
            news_id=item["id"],
            tickers={
                t: {"ref": round(d["price"], 4), "atr%": d["atr_pct"]}
                for t, d in ref_data.items()
            },
        )

        reacted: set[str] = set()
        start = time.monotonic()

        try:
            while time.monotonic() - start < MONITOR_DURATION:
                await asyncio.sleep(POLL_INTERVAL)
                elapsed = int(time.monotonic() - start)

                if len(reacted) == len(ref_data):
                    break

                for ticker, rd in ref_data.items():
                    if ticker in reacted:
                        continue

                    ref_price = rd["price"]
                    atr_pct = rd["atr_pct"]

                    current_price = ref_price
                    q = await self._read_latest_quote(ticker)
                    if q:
                        mid = self._get_midpoint(q)
                        if mid > 0:
                            current_price = mid

                    if current_price == ref_price:
                        snap = await self._get_ticker_snapshot(ticker)
                        if snap:
                            lt = snap.get("lastTrade", {})
                            p = lt.get("p", 0) or snap.get("current_price", 0)
                            if p > 0:
                                current_price = p

                    change_pct = ((current_price - ref_price) / ref_price) * 100
                    z = self._compute_z_score(change_pct, atr_pct, elapsed)

                    if z < Z_THRESHOLD:
                        continue

                    reacted.add(ticker)

                    direction = "up" if change_pct > 0 else "down"
                    arrow = "▲" if change_pct > 0 else "▼"
                    sign = "+" if change_pct > 0 else ""
                    now_utc = datetime.now(timezone.utc)

                    reaction = {
                        "id": f"opn_rx_{item['id']}_{ticker}_{elapsed}s",
                        "text": (
                            f"${ticker} {arrow} {sign}{change_pct:.1f}% "
                            f"${current_price:.2f} (was ${ref_price:.2f}) "
                            f"— {elapsed}s after headline"
                        ),
                        "tickers": [ticker],
                        "type": "reaction",
                        "direction": direction,
                        "change_pct": round(change_pct, 2),
                        "price": round(current_price, 2),
                        "ref_price": round(ref_price, 2),
                        "delay_seconds": elapsed,
                        "ref_id": item["id"],
                        "created_at": now_utc.isoformat(),
                        "received_at": now_utc.isoformat(),
                        "received_ts": now_utc.timestamp(),
                    }

                    await self._publish_to_redis(reaction)
                    logger.info(
                        "reaction_detected",
                        ticker=ticker,
                        z_score=round(z, 2),
                        change_pct=f"{sign}{change_pct:.1f}%",
                        elapsed=f"{elapsed}s",
                    )
        finally:
            await self._unsubscribe_quotes(tracked)

    async def _publish_to_redis(self, item: Dict[str, Any]):
        """Publish a news item to Redis Stream + Sorted Set."""
        pipe = self._redis.pipeline()

        payload = json.dumps(item)

        # 1. XADD to Redis Stream (for SSE consumers)
        pipe.xadd(
            settings.redis_stream_key,
            {"data": payload},
            maxlen=settings.redis_stream_maxlen,
            approximate=True,
        )

        # 2. ZADD to sorted set (for historical queries, scored by timestamp)
        score = item.get("received_ts", time.time())
        pipe.zadd(settings.redis_latest_key, {payload: score})

        # 3. Trim sorted set
        pipe.zremrangebyrank(settings.redis_latest_key, 0, -(settings.redis_latest_maxlen + 1))

        # 4. Pub/Sub for instant broadcast
        pipe.publish("openul:live", payload)

        await pipe.execute()

        self._stats["tweets_published"] += 1
        self._stats["last_tweet_at"] = item.get("received_at")

    async def _stream_loop(self):
        """Main streaming loop with exponential backoff reconnect."""
        backoff = settings.initial_backoff

        while self._running:
            try:
                params = {
                    "tweet.fields": "created_at,text,author_id,public_metrics,entities,note_tweet,referenced_tweets,attachments",
                    "expansions": "author_id,referenced_tweets.id,attachments.media_keys",
                    "user.fields": "username,name",
                    "media.fields": "url,preview_image_url,type",
                }

                stream_timeout = httpx.Timeout(connect=10.0, read=90.0, write=10.0, pool=10.0)
                async with httpx.AsyncClient(timeout=stream_timeout) as client:
                    async with client.stream(
                        "GET",
                        X_STREAM_URL,
                        headers=self._auth_headers(),
                        params=params,
                    ) as response:
                        if response.status_code == 429:
                            retry_after = int(response.headers.get("retry-after", "60"))
                            logger.warning("rate_limited", retry_after=retry_after)
                            await asyncio.sleep(retry_after)
                            continue

                        response.raise_for_status()

                        backoff = settings.initial_backoff
                        self._stats["connected_since"] = datetime.now(timezone.utc).isoformat()
                        logger.info("stream_connected", users=settings.monitored_users)

                        async for line in response.aiter_lines():
                            if not self._running:
                                break
                            if not line.strip():
                                continue

                            try:
                                event = json.loads(line)
                            except json.JSONDecodeError:
                                continue

                            self._stats["tweets_received"] += 1
                            item = self._parse_tweet(event)
                            if item:
                                await self._publish_to_redis(item)
                                logger.info(
                                    "item_published",
                                    id=item["id"],
                                    text_preview=item["text"][:80],
                                )
                                asyncio.create_task(self._check_price_reactions(item))

            except httpx.HTTPStatusError as e:
                self._stats["errors"] += 1
                logger.error("stream_http_error", status=e.response.status_code)
            except (httpx.ReadError, httpx.RemoteProtocolError, httpx.ReadTimeout) as e:
                self._stats["errors"] += 1
                logger.warning("stream_read_error", error=str(e))
            except Exception as e:
                self._stats["errors"] += 1
                logger.error("stream_unexpected_error", error=str(e), type=type(e).__name__)

            if self._running:
                self._stats["reconnects"] += 1
                self._stats["connected_since"] = None
                logger.info("stream_reconnecting", backoff=backoff)
                await asyncio.sleep(backoff)
                backoff = min(backoff * 2, settings.max_backoff)

    async def start(self):
        self._bearer_token = await self.get_bearer_token()
        await self._sync_rules()
        self._running = True
        self._task = asyncio.create_task(self._stream_loop())
        logger.info("consumer_started")

    async def stop(self):
        self._running = False
        if self._task:
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass
        logger.info("consumer_stopped")

    def get_stats(self) -> Dict[str, Any]:
        return {**self._stats, "running": self._running}
