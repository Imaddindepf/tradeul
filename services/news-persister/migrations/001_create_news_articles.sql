-- Migration: hypertable news_articles en la TimescaleDB principal (tradeul)
-- Persiste el feed unificado de noticias (stream:benzinga:news):
--   benzinga (OpenOutcrier) + fmp (5 feeds) + polygon
-- OpenOutcrier es la única fuente sin histórico recuperable — sin esta tabla
-- sus artículos se pierden al salir del cache de Redis (2.000 items).
--
-- Búsqueda: search_vec (tsvector generado, title A + teaser B + body C) con
-- índice GIN → full-text real, que ningún proveedor ofrece.
--
-- Compresión a los 180 días (los índices GIN solo sirven en chunks sin
-- comprimir: las búsquedas <6 meses van por índice, las más viejas
-- descomprimen — trade-off deliberado). Retención: 2 años.

CREATE TABLE IF NOT EXISTS news_articles (
    id            TEXT        NOT NULL,             -- bz_<benzinga_id> | fmp_<hash> | poly_<id>
    source        TEXT        NOT NULL,             -- benzinga | fmp | polygon
    title         TEXT        NOT NULL,
    teaser        TEXT,
    body          TEXT,
    url           TEXT        NOT NULL,
    publisher     TEXT,                             -- author/publisher (columna "source" de la UI)
    site          TEXT,                             -- dominio del publisher
    tickers       TEXT[]      NOT NULL DEFAULT '{}',
    channels      TEXT[]      NOT NULL DEFAULT '{}',
    tags          TEXT[]      NOT NULL DEFAULT '{}',
    sentiment     TEXT,                             -- positive | negative | neutral
    insights      JSONB,                            -- sentimiento por ticker (Polygon)
    images        TEXT[],
    ticker_prices JSONB,                            -- precios capturados al publicarse (pipeline)
    published     TIMESTAMPTZ NOT NULL,
    received_at   TIMESTAMPTZ NOT NULL DEFAULT now(),
    search_vec    TSVECTOR GENERATED ALWAYS AS (
        setweight(to_tsvector('english', coalesce(title, '')),  'A') ||
        setweight(to_tsvector('english', coalesce(teaser, '')), 'B') ||
        setweight(to_tsvector('english', left(coalesce(body, ''), 20000)), 'C')
    ) STORED,
    PRIMARY KEY (id, published)                     -- la hypertable exige published en la PK
);

SELECT create_hypertable(
    'news_articles', 'published',
    chunk_time_interval => INTERVAL '7 days',
    if_not_exists => TRUE
);

CREATE INDEX IF NOT EXISTS idx_news_articles_published ON news_articles (published DESC);
CREATE INDEX IF NOT EXISTS idx_news_articles_tickers   ON news_articles USING GIN (tickers);
CREATE INDEX IF NOT EXISTS idx_news_articles_search    ON news_articles USING GIN (search_vec);
CREATE INDEX IF NOT EXISTS idx_news_articles_source    ON news_articles (source, published DESC);
CREATE INDEX IF NOT EXISTS idx_news_articles_url_md5   ON news_articles (md5(url));

-- Compresión columnar (segmentada por fuente) y retención
ALTER TABLE news_articles SET (
    timescaledb.compress,
    timescaledb.compress_orderby   = 'published DESC',
    timescaledb.compress_segmentby = 'source'
);
SELECT add_compression_policy('news_articles', INTERVAL '180 days', if_not_exists => TRUE);
SELECT add_retention_policy('news_articles', INTERVAL '730 days', if_not_exists => TRUE);
