"""
Market Internals Calculator — índices sintéticos TRDL INDEX.

Calcula internals de mercado al estilo $TICK / $ADD de NYSE a partir del
universo enriquecido que ya procesa el EnrichmentPipeline en cada ciclo (~5s):

    TRDL:TICK   upticks − downticks del ciclo (acciones NYSE common stock)
    TRDL:TICKC  TICK acumulativo del día (suma de cierres de minuto, RTH)
    TRDL:ADD    advancers − decliners del día (verdes − rojas vs prev close)

Los valores se publican como "tickers sintéticos" para reutilizar el pipeline
existente:
  - hash market:internals:latest        → consumo directo (paneles, filtros)
  - stream:realtime:aggregates          → websocket_server los difunde como
                                          chart_aggregate (chart en vivo)
  - tabla minute_bars (TimescaleDB)     → histórico para el chart REST
                                          (api_gateway sirve TRDL:* desde ahí)

El TICK oficial de NYSE se calcula trade a trade desde el SIP; el nuestro es
muestreado por ciclo, así que los extremos absolutos difieren, pero la forma,
las divergencias y el acumulativo son operables.
"""

import time
from datetime import datetime
from typing import Dict, List, Optional

from shared.utils.logger import get_logger

logger = get_logger(__name__)

# Símbolos sintéticos (exchange virtual "TRDL INDEX")
SYM_TICK = "TRDL:TICK"
SYM_TICKC = "TRDL:TICKC"
SYM_ADD = "TRDL:ADD"

INTERNALS_HASH_KEY = "market:internals:latest"
AGGREGATES_STREAM = "stream:realtime:aggregates"

# Universo: common stocks de NYSE (como el $TICK clásico)
UNIVERSE_EXCHANGE = "XNYS"
UNIVERSE_TYPE = "CS"

# Ignorar precios de trades más viejos que esto (símbolos zombi intradía)
STALE_TRADE_NS = 10 * 60 * 1_000_000_000  # 10 min en ns


class MarketInternalsCalculator:
    """
    Mantiene el estado intradía de los internals y los publica cada ciclo.

    Uso: el EnrichmentPipeline llama a `on_cycle()` al final de cada ciclo
    con el dict completo de tickers enriquecidos y el metadata cache.
    """

    def __init__(self, redis_client, timescale_client=None):
        self.redis = redis_client
        self.db = timescale_client

        # Precio del ciclo anterior por símbolo (para upticks/downticks)
        self._last_prices: Dict[str, float] = {}

        # Fecha ET de la sesión actual (para reset diario)
        self._session_date: Optional[str] = None

        # TICK acumulativo: suma de cierres de minuto completados (solo RTH)
        self._cum_closed: float = 0.0
        self._current_minute: Optional[int] = None   # epoch-minute en curso
        self._current_minute_tick: float = 0.0       # último TICK del minuto

        # Velas de 1 min en formación por símbolo: {sym: [o, h, l, c]}
        self._bars: Dict[str, List[float]] = {}
        self._bars_minute: Optional[int] = None
        self._pending_rows: List[tuple] = []  # (symbol, ts_ms, o, h, l, c, v)

        self._table_ready = False

    # ------------------------------------------------------------------
    async def on_cycle(
        self,
        enriched: Dict[str, dict],
        metadata: Dict[str, dict],
        now_et: datetime,
    ) -> None:
        """Calcular y publicar internals para este ciclo. Nunca lanza."""
        try:
            await self._on_cycle_inner(enriched, metadata, now_et)
        except Exception as e:
            logger.error("market_internals_cycle_error", error=str(e))

    async def _on_cycle_inner(
        self,
        enriched: Dict[str, dict],
        metadata: Dict[str, dict],
        now_et: datetime,
    ) -> None:
        date_str = now_et.strftime("%Y-%m-%d")
        if self._session_date != date_str:
            self._reset_day(date_str)

        now_ns = time.time_ns()
        upticks = downticks = 0
        advancers = decliners = 0
        sampled = 0
        new_prices: Dict[str, float] = {}

        for symbol, row in enriched.items():
            meta = metadata.get(symbol)
            if not meta:
                continue
            if meta.get("exchange") != UNIVERSE_EXCHANGE:
                continue
            if meta.get("security_type") != UNIVERSE_TYPE:
                continue

            lt = row.get("lastTrade")
            price = lt.get("p") if isinstance(lt, dict) else None
            if not price or price <= 0:
                continue
            ts = lt.get("t") if isinstance(lt, dict) else None
            if ts and now_ns - ts > STALE_TRADE_NS:
                # Sin trades recientes: no aporta al TICK de este ciclo
                continue

            sampled += 1
            new_prices[symbol] = price

            prev = self._last_prices.get(symbol)
            if prev is not None:
                if price > prev:
                    upticks += 1
                elif price < prev:
                    downticks += 1

            chg = row.get("todaysChangePerc")
            if chg is None:
                chg = row.get("premarket_change_percent")
            if chg is not None:
                if chg > 0:
                    advancers += 1
                elif chg < 0:
                    decliners += 1

        # Actualizar baseline de precios (incluye símbolos nuevos del ciclo)
        self._last_prices.update(new_prices)

        if sampled < 50:
            # Universo dormido (madrugada/festivo): no publicar ruido
            return

        tick = float(upticks - downticks)
        add = float(advancers - decliners)

        # ── TICK acumulativo (suma de cierres de minuto, solo RTH) ──
        epoch_min = int(now_et.timestamp()) // 60
        in_rth = (9, 30) <= (now_et.hour, now_et.minute) < (16, 0)

        if self._current_minute is None:
            self._current_minute = epoch_min
        elif epoch_min != self._current_minute:
            # Cerró un minuto: consolidar su último TICK en el acumulado
            if self._was_rth_minute(self._current_minute):
                self._cum_closed += self._current_minute_tick
            self._current_minute = epoch_min
        self._current_minute_tick = tick if in_rth else 0.0

        tick_cum = self._cum_closed + (tick if in_rth else 0.0)

        values = {SYM_TICK: tick, SYM_TICKC: tick_cum, SYM_ADD: add}

        # ── Publicaciones ──
        await self._publish_hash(values, advancers, decliners, sampled, now_et)
        await self._publish_aggregates(values, sampled, now_ns)
        self._update_bars(values, sampled, epoch_min)
        await self._flush_bars()

    # ------------------------------------------------------------------
    def _reset_day(self, date_str: str) -> None:
        logger.info("market_internals_day_reset", date=date_str)
        self._session_date = date_str
        self._last_prices.clear()
        self._cum_closed = 0.0
        self._current_minute = None
        self._current_minute_tick = 0.0
        self._bars.clear()
        self._bars_minute = None

    @staticmethod
    def _was_rth_minute(epoch_min: int) -> bool:
        """¿El minuto (epoch) cae dentro de RTH 9:30–16:00 ET?"""
        from zoneinfo import ZoneInfo
        d = datetime.fromtimestamp(epoch_min * 60, tz=ZoneInfo("America/New_York"))
        return (9, 30) <= (d.hour, d.minute) < (16, 0)

    # ------------------------------------------------------------------
    async def _publish_hash(self, values, advancers, decliners, sampled, now_et):
        import orjson
        mapping = {}
        for sym, val in values.items():
            mapping[sym] = orjson.dumps({
                "symbol": sym,
                "value": round(val, 2),
                "advancers": advancers,
                "decliners": decliners,
                "sampled": sampled,
                "ts": now_et.isoformat(),
            }).decode()
        await self.redis.client.hset(INTERNALS_HASH_KEY, mapping=mapping)
        await self.redis.client.expire(INTERNALS_HASH_KEY, 3600)

    async def _publish_aggregates(self, values, sampled, now_ns):
        """XADD al stream de aggregates → websocket_server → chart en vivo."""
        now_ms = now_ns // 1_000_000
        for sym, val in values.items():
            bar = self._bars.get(sym)
            o, h, l = (bar[0], bar[1], bar[2]) if bar else (val, val, val)
            payload = {
                "symbol": sym,
                "open": str(round(o, 2)),
                "high": str(round(max(h, val), 2)),
                "low": str(round(min(l, val), 2)),
                "close": str(round(val, 2)),
                "volume": str(sampled),
                "volume_accumulated": str(sampled),
                "vwap": str(round(val, 2)),
                "avg_trade_size": "0",
                "trades": str(sampled),
                "timestamp_start": str(now_ms - 5000),
                "timestamp_end": str(now_ms),
                "otc": "false",
            }
            try:
                await self.redis.publish_to_stream(AGGREGATES_STREAM, payload)
            except Exception as e:
                logger.debug("internals_stream_publish_error", symbol=sym, error=str(e))

    # ------------------------------------------------------------------
    def _update_bars(self, values: Dict[str, float], sampled: int, epoch_min: int) -> None:
        """OHLC de 1 min a partir de las muestras por ciclo (estilo TOS)."""
        if self._bars_minute is None:
            self._bars_minute = epoch_min

        if epoch_min != self._bars_minute:
            # Minuto cerrado → encolar filas para TimescaleDB
            ts_ms = self._bars_minute * 60 * 1000
            for sym, bar in self._bars.items():
                self._pending_rows.append(
                    (sym, ts_ms, bar[0], bar[1], bar[2], bar[3], sampled)
                )
            self._bars.clear()
            self._bars_minute = epoch_min

        for sym, val in values.items():
            bar = self._bars.get(sym)
            if bar is None:
                self._bars[sym] = [val, val, val, val]
            else:
                bar[1] = max(bar[1], val)
                bar[2] = min(bar[2], val)
                bar[3] = val

    async def _flush_bars(self) -> None:
        if not self._pending_rows or self.db is None:
            return
        rows, self._pending_rows = self._pending_rows, []
        try:
            await self.db.executemany(
                """
                INSERT INTO minute_bars (symbol, ts, open, high, low, close, volume)
                VALUES ($1, $2, $3, $4, $5, $6, $7)
                ON CONFLICT DO NOTHING
                """,
                rows,
            )
        except Exception as e:
            logger.error("internals_bars_persist_error", error=str(e), rows=len(rows))
