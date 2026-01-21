"""SQL Examples RAG - Local Implementation"""
import numpy as np
from typing import List, Optional
from dataclasses import dataclass
import structlog

logger = structlog.get_logger(__name__)
_model = None

def _get_model():
    global _model
    if _model is None:
        try:
            from sentence_transformers import SentenceTransformer
            _model = SentenceTransformer('all-MiniLM-L6-v2')
            logger.info("sql_rag_model_loaded", model="all-MiniLM-L6-v2")
        except ImportError:
            logger.error("sentence-transformers not installed")
    return _model

@dataclass
class SQLExample:
    query_es: str
    query_en: str
    sql: str
    description: str

SQL_EXAMPLES: List[SQLExample] = [
    SQLExample("cuantos gappers con gap mayor a 5%", "how many gappers with gap > 5%",
        "WITH y AS (SELECT ticker, close AS pc FROM read_parquet('/data/polygon/day_aggs/{prev_date}.parquet')), t AS (SELECT ticker, open FROM read_parquet('/data/polygon/day_aggs/{date}.parquet')) SELECT COUNT(*) as cnt FROM t JOIN y ON t.ticker = y.ticker WHERE (t.open - y.pc) / y.pc > 0.05;",
        "Count gappers > threshold"),
    SQLExample("top 10 gappers por porcentaje", "top 10 gappers by gap %",
        "WITH y AS (SELECT ticker, close AS pc FROM read_parquet('/data/polygon/day_aggs/{prev_date}.parquet')), t AS (SELECT ticker, open, close, volume FROM read_parquet('/data/polygon/day_aggs/{date}.parquet')) SELECT t.ticker, y.pc, t.open, t.close, t.volume, ROUND((t.open - y.pc) / y.pc * 100, 2) AS gap_pct FROM t JOIN y ON t.ticker = y.ticker WHERE y.pc > 0 ORDER BY gap_pct DESC LIMIT 10;",
        "Top N gappers by gap %"),
    SQLExample("gappers que cerraron debajo del VWAP", "gappers that closed below VWAP",
        "WITH p AS (SELECT ticker, close AS pc FROM read_parquet('/data/polygon/day_aggs/{prev_date}.parquet')), c AS (SELECT ticker, open, high, low, close, volume FROM read_parquet('/data/polygon/day_aggs/{date}.parquet')) SELECT c.ticker, p.pc, c.open, c.close, ROUND((c.open - p.pc) / p.pc * 100, 2) AS gap_pct, ROUND((c.high + c.low + c.close) / 3, 2) AS vwap, c.volume FROM c JOIN p ON c.ticker = p.ticker WHERE (c.open - p.pc) / p.pc > 0.05 AND c.close < (c.high + c.low + c.close) / 3 ORDER BY gap_pct DESC;",
        "Gappers below VWAP"),
    SQLExample("gap ups que cerraron en rojo", "gap ups that closed red",
        "WITH p AS (SELECT ticker, close AS pc FROM read_parquet('/data/polygon/day_aggs/{prev_date}.parquet')), c AS (SELECT ticker, open, close, volume FROM read_parquet('/data/polygon/day_aggs/{date}.parquet')) SELECT c.ticker, p.pc, c.open, c.close, ROUND((c.open - p.pc) / p.pc * 100, 2) AS gap_pct FROM c JOIN p ON c.ticker = p.ticker WHERE (c.open - p.pc) / p.pc > 0.05 AND c.close < c.open ORDER BY gap_pct DESC LIMIT 20;",
        "Gap up reversals"),
    SQLExample("top gainers de la semana", "top weekly gainers",
        "WITH s AS (SELECT ticker, open FROM read_parquet('/data/polygon/day_aggs/{start_date}.parquet')), e AS (SELECT ticker, close, volume FROM read_parquet('/data/polygon/day_aggs/{end_date}.parquet')) SELECT s.ticker, s.open, e.close, ROUND((e.close - s.open) / s.open * 100, 2) AS gain_pct, e.volume FROM s JOIN e ON s.ticker = e.ticker ORDER BY gain_pct DESC LIMIT 10;",
        "Weekly top gainers"),
    SQLExample("top perdedores del dia", "top losers of the day",
        "SELECT ticker, open, close, ROUND((close - open) / open * 100, 2) AS chg_pct, volume FROM read_parquet('/data/polygon/day_aggs/{date}.parquet') WHERE open > 0 ORDER BY chg_pct ASC LIMIT 10;",
        "Top losers"),
    SQLExample("small caps con volumen alto", "small caps high volume",
        "SELECT ticker, close, volume FROM read_parquet('/data/polygon/day_aggs/{date}.parquet') WHERE close < 5 AND volume > 10000000 ORDER BY volume DESC;",
        "Small caps high volume"),
    SQLExample("volumen 3x superior al promedio", "volume 3x average",
        "WITH v AS (SELECT ticker, volume, AVG(volume) OVER (PARTITION BY ticker ORDER BY window_start ROWS BETWEEN 20 PRECEDING AND 1 PRECEDING) AS avg FROM read_parquet('/data/polygon/day_aggs/2026-*.parquet')) SELECT ticker, volume, ROUND(avg) as avg20, ROUND(volume / avg, 2) AS ratio FROM v WHERE window_start >= (SELECT MAX(window_start) FROM v) AND volume > avg * 3 AND avg > 100000 ORDER BY ratio DESC LIMIT 20;",
        "Volume spike 3x"),
    SQLExample("acciones por encima de SMA 200", "stocks above 200 SMA",
        "WITH p AS (SELECT ticker, close, DATE_TRUNC('day', to_timestamp(window_start / 1e9))::DATE AS dt FROM read_parquet(['/data/polygon/day_aggs/2025-*.parquet', '/data/polygon/day_aggs/2026-01-*.parquet'])), sma AS (SELECT ticker, dt, close, AVG(close) OVER (PARTITION BY ticker ORDER BY dt ROWS BETWEEN 199 PRECEDING AND CURRENT ROW) AS sma200, ROW_NUMBER() OVER (PARTITION BY ticker ORDER BY dt) as rn FROM p) SELECT COUNT(*) AS cnt FROM sma WHERE dt = '{date}' AND rn >= 200 AND close > sma200;",
        "Count above SMA 200"),
    SQLExample("golden cross SMA 50 cruza SMA 200", "golden cross SMA 50 crosses SMA 200",
        "WITH d AS (SELECT ticker, close, to_timestamp(window_start / 1e9)::DATE as dt FROM read_parquet('/data/polygon/day_aggs/20*.parquet')), m AS (SELECT ticker, dt, close, AVG(close) OVER (PARTITION BY ticker ORDER BY dt ROWS BETWEEN 199 PRECEDING AND CURRENT ROW) AS s200, AVG(close) OVER (PARTITION BY ticker ORDER BY dt ROWS BETWEEN 49 PRECEDING AND CURRENT ROW) AS s50 FROM d), x AS (SELECT *, LAG(s50) OVER (PARTITION BY ticker ORDER BY dt) AS p50, LAG(s200) OVER (PARTITION BY ticker ORDER BY dt) AS p200 FROM m) SELECT ticker, dt, close, ROUND(s50, 2) AS sma50, ROUND(s200, 2) AS sma200 FROM x WHERE dt BETWEEN '{start_date}' AND '{end_date}' AND s50 > s200 AND p50 <= p200 ORDER BY dt, ticker;",
        "Golden Cross"),
    SQLExample("RSI por debajo de 30 sobreventa", "RSI below 30 oversold",
        "WITH c AS (SELECT ticker, close, close - LAG(close) OVER (PARTITION BY ticker ORDER BY window_start) AS chg, to_timestamp(window_start / 1e9)::DATE as dt FROM read_parquet('/data/polygon/day_aggs/2026-*.parquet')), gl AS (SELECT ticker, dt, close, CASE WHEN chg > 0 THEN chg ELSE 0 END AS g, CASE WHEN chg < 0 THEN ABS(chg) ELSE 0 END AS l FROM c), a AS (SELECT ticker, dt, close, AVG(g) OVER (PARTITION BY ticker ORDER BY dt ROWS BETWEEN 13 PRECEDING AND CURRENT ROW) AS ag, AVG(l) OVER (PARTITION BY ticker ORDER BY dt ROWS BETWEEN 13 PRECEDING AND CURRENT ROW) AS al FROM gl) SELECT ticker, close, ROUND(100 - (100 / (1 + ag / NULLIF(al, 0))), 2) AS rsi FROM a WHERE dt = '{date}' AND al > 0 AND 100 - (100 / (1 + ag / NULLIF(al, 0))) < 30 ORDER BY rsi LIMIT 20;",
        "RSI oversold"),
    SQLExample("top acciones por volatilidad ATR", "top stocks by ATR",
        "WITH t AS (SELECT ticker, high, low, close, LAG(close) OVER (PARTITION BY ticker ORDER BY window_start) AS pc, to_timestamp(window_start / 1e9)::DATE as dt FROM read_parquet('/data/polygon/day_aggs/2026-01-*.parquet')), tr AS (SELECT ticker, dt, close, GREATEST(high - low, ABS(high - pc), ABS(low - pc)) AS tr FROM t WHERE pc IS NOT NULL), atr AS (SELECT ticker, dt, close, AVG(tr) OVER (PARTITION BY ticker ORDER BY dt ROWS BETWEEN 13 PRECEDING AND CURRENT ROW) AS atr14 FROM tr) SELECT ticker, close, ROUND(atr14, 2) AS atr, ROUND(atr14 / close * 100, 2) AS atr_pct FROM atr WHERE dt = '{date}' AND close > 0 ORDER BY atr_pct DESC LIMIT 10;",
        "Top by ATR volatility"),
    SQLExample("nuevo maximo 52 semanas", "52 week high breakout",
        "WITH y AS (SELECT ticker, high, to_timestamp(window_start / 1e9)::DATE as dt FROM read_parquet('/data/polygon/day_aggs/20*.parquet') WHERE to_timestamp(window_start / 1e9) >= CURRENT_DATE - INTERVAL '365 days'), mx AS (SELECT ticker, MAX(CASE WHEN dt < '{date}' THEN high END) AS prev52, MAX(CASE WHEN dt = '{date}' THEN high END) AS today FROM y GROUP BY ticker) SELECT ticker, ROUND(prev52, 2) AS prev_52w, ROUND(today, 2) AS today_high FROM mx WHERE today > prev52 AND prev52 IS NOT NULL ORDER BY (today - prev52) / prev52 DESC;",
        "52-week high breakouts"),
    SQLExample("inside bar pattern", "inside bar consolidation",
        "WITH tw AS (SELECT ticker, high, low, close, volume, LAG(high) OVER (PARTITION BY ticker ORDER BY window_start) AS ph, LAG(low) OVER (PARTITION BY ticker ORDER BY window_start) AS pl, to_timestamp(window_start / 1e9)::DATE as dt FROM read_parquet('/data/polygon/day_aggs/2026-01-*.parquet')) SELECT ticker, high, low, ph AS prev_high, pl AS prev_low, close, volume FROM tw WHERE dt = '{date}' AND high < ph AND low > pl AND ph IS NOT NULL ORDER BY volume DESC LIMIT 20;",
        "Inside bar pattern"),
    SQLExample("3 dias consecutivos subiendo", "3 consecutive up days",
        "WITH d AS (SELECT ticker, close, LAG(close, 1) OVER (PARTITION BY ticker ORDER BY window_start) AS c1, LAG(close, 2) OVER (PARTITION BY ticker ORDER BY window_start) AS c2, LAG(close, 3) OVER (PARTITION BY ticker ORDER BY window_start) AS c3, to_timestamp(window_start / 1e9)::DATE as dt FROM read_parquet('/data/polygon/day_aggs/2026-01-*.parquet')) SELECT ticker, close, ROUND((close - c3) / c3 * 100, 2) AS gain3d FROM d WHERE dt = '{date}' AND close > c1 AND c1 > c2 AND c2 > c3 AND c3 IS NOT NULL ORDER BY gain3d DESC LIMIT 20;",
        "3 consecutive up days"),
    SQLExample("top gainer por cada hora", "top gainer each hour",
        "WITH h AS (SELECT ticker, EXTRACT(HOUR FROM to_timestamp(window_start / 1e9)) AS hr, FIRST(open) AS op, LAST(close) AS cl FROM read_csv_auto('/data/polygon/minute_aggs/{date}.csv.gz') GROUP BY ticker, EXTRACT(HOUR FROM to_timestamp(window_start / 1e9))), c AS (SELECT *, ROUND((cl - op) / op * 100, 2) AS pct FROM h WHERE op > 0), r AS (SELECT *, ROW_NUMBER() OVER (PARTITION BY hr ORDER BY pct DESC) AS rn FROM c) SELECT hr AS hour, ticker, op AS open_price, cl AS close_price, pct AS change_pct FROM r WHERE rn = 1 ORDER BY hr;",
        "Top gainer each hour"),
    SQLExample("subio primera hora bajo power hour", "morning up power hour down",
        "WITH m AS (SELECT ticker, FIRST(open) AS mo, LAST(close) AS mc FROM read_csv_auto('/data/polygon/minute_aggs/{date}.csv.gz') WHERE EXTRACT(HOUR FROM to_timestamp(window_start / 1e9)) = 9 GROUP BY ticker), p AS (SELECT ticker, FIRST(open) AS po, LAST(close) AS pc FROM read_csv_auto('/data/polygon/minute_aggs/{date}.csv.gz') WHERE EXTRACT(HOUR FROM to_timestamp(window_start / 1e9)) = 15 GROUP BY ticker) SELECT m.ticker, ROUND((m.mc - m.mo) / m.mo * 100, 2) AS morning_pct, ROUND((p.pc - p.po) / p.po * 100, 2) AS ph_pct FROM m JOIN p ON m.ticker = p.ticker WHERE m.mc > m.mo AND p.pc < p.po ORDER BY morning_pct DESC LIMIT 20;",
        "Morning strength power hour weakness"),
    SQLExample("top gainers intradiarios con volumen", "top intraday gainers with volume",
        "WITH i AS (SELECT ticker, FIRST(open) AS op, LAST(close) AS cl, SUM(volume) AS vol FROM read_csv_auto('/data/polygon/minute_aggs/{date}.csv.gz') GROUP BY ticker) SELECT ticker, op AS open, cl AS close, vol AS total_volume, ROUND((cl - op) / op * 100, 2) AS gain_pct FROM i WHERE vol > 1000000 AND op > 0 ORDER BY gain_pct DESC LIMIT 10;",
        "Top intraday gainers with volume filter"),
]

class SQLExamplesRAG:
    def __init__(self):
        self._model = None
        self._example_embeddings: Optional[np.ndarray] = None
        self._initialized = False
    
    def _ensure_initialized(self) -> bool:
        if self._initialized:
            return self._model is not None
        self._model = _get_model()
        if self._model is None:
            self._initialized = True
            return False
        all_queries = []
        for ex in SQL_EXAMPLES:
            all_queries.append(ex.query_es)
            all_queries.append(ex.query_en)
        self._example_embeddings = self._model.encode(all_queries, normalize_embeddings=True)
        self._initialized = True
        logger.info("sql_rag_initialized", num_examples=len(SQL_EXAMPLES))
        return True
    
    def get_similar_examples(self, query: str, top_k: int = 3) -> List[SQLExample]:
        if not self._ensure_initialized():
            return []
        query_embedding = self._model.encode(query, normalize_embeddings=True)
        similarities = np.dot(self._example_embeddings, query_embedding)
        top_indices = np.argsort(similarities)[-top_k * 2:][::-1]
        seen = set()
        result = []
        for idx in top_indices:
            ex_idx = idx // 2
            if ex_idx not in seen and len(result) < top_k:
                seen.add(ex_idx)
                result.append(SQL_EXAMPLES[ex_idx])
        logger.debug("similar_examples_found", query=query[:50], num_found=len(result))
        return result
    
    def format_examples_for_prompt(self, examples: List[SQLExample]) -> str:
        if not examples:
            return ""
        lines = ["## SIMILAR SQL EXAMPLES (verified working):\n"]
        for i, ex in enumerate(examples, 1):
            lines.append(f"### Example {i}: {ex.description}")
            lines.append(f"Query: \"{ex.query_en}\"")
            lines.append(f"```sql\n{ex.sql}\n```\n")
        lines.append("Use these patterns. Adapt dates as needed.")
        return "\n".join(lines)

_rag_instance: Optional[SQLExamplesRAG] = None

def get_sql_examples_rag() -> SQLExamplesRAG:
    global _rag_instance
    if _rag_instance is None:
        _rag_instance = SQLExamplesRAG()
    return _rag_instance
