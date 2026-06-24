-- Migration: tabla openul_news en la BD separada `openul`
-- Ejecutar contra: DB_HOST / openul
-- Autor: tradeul | Persiste el stream Redis `openul:news` (noticias + reacciones)

CREATE TABLE IF NOT EXISTS openul_news (
    id            TEXT        PRIMARY KEY,                  -- opn_<tweet> | trd_<src> | opn_rx_<...>
    stream_id     TEXT,                                     -- id del Redis Stream (<ms>-<seq>)
    type          TEXT        NOT NULL DEFAULT 'news',      -- 'news' | 'reaction'
    text          TEXT        NOT NULL,
    tickers       TEXT[]      NOT NULL DEFAULT '{}',
    source        TEXT,                                     -- tradeul | external | ...
    created_at    TIMESTAMPTZ,                              -- timestamp de la fuente
    received_at   TIMESTAMPTZ NOT NULL,                     -- cuando lo ingesto openul-stream
    media         JSONB,                                    -- [{type,url}, ...]
    urls          TEXT[],                                   -- urls externas

    -- Campos especificos de reacciones de precio (type = 'reaction')
    ref_id        TEXT,                                     -- id de la noticia que disparo la reaccion
    direction     TEXT,                                     -- 'up' | 'down'
    change_pct    DOUBLE PRECISION,
    price         DOUBLE PRECISION,
    ref_price     DOUBLE PRECISION,
    delay_seconds INTEGER,

    inserted_at   TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_openul_news_received_at ON openul_news (received_at DESC);
CREATE INDEX IF NOT EXISTS idx_openul_news_tickers     ON openul_news USING GIN (tickers);
CREATE INDEX IF NOT EXISTS idx_openul_news_type        ON openul_news (type);

-- Opcional (si la extension TimescaleDB esta disponible en este servidor):
-- SELECT create_hypertable('openul_news', 'received_at', if_not_exists => TRUE,
--                          migrate_data => TRUE, chunk_time_interval => INTERVAL '7 days');
