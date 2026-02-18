"""
AI Agent V5 - Full Test Battery
Runs queries against the WebSocket endpoint and captures results.
"""
import asyncio
import json
import sys
import time
import websockets

WS_URI = "ws://localhost:8031/ws/chat/test-battery"

async def run_query(query: str, idx: int) -> dict:
    """Run a single query and return structured result."""
    thread_id = f"battery-{idx}-{int(time.time())}"
    try:
        async with websockets.connect(WS_URI, close_timeout=5) as ws:
            await ws.send(json.dumps({"query": query, "thread_id": thread_id}))

            start = time.time()
            nodes_started = []
            nodes_done = []
            final = None
            error = None

            while True:
                try:
                    msg = await asyncio.wait_for(ws.recv(), timeout=90)
                    data = json.loads(msg)

                    if data["type"] == "node_started":
                        nodes_started.append(data["node"])
                    elif data["type"] == "node_completed":
                        nodes_done.append(data["node"])
                    elif data["type"] == "final_response":
                        final = data["response"]
                        break
                    elif data["type"] == "error":
                        error = data["message"]
                        break
                except asyncio.TimeoutError:
                    error = "TIMEOUT (90s)"
                    break

            elapsed = round(time.time() - start, 1)
            agents = [n for n in nodes_started if n not in ("query_planner", "synthesizer")]

            return {
                "idx": idx,
                "query": query,
                "elapsed_s": elapsed,
                "agents": agents,
                "response_len": len(final) if final else 0,
                "response_preview": (final[:600] if final else ""),
                "error": error,
            }
    except Exception as e:
        return {
            "idx": idx,
            "query": query,
            "elapsed_s": 0,
            "agents": [],
            "response_len": 0,
            "response_preview": "",
            "error": str(e),
        }


async def run_batch(queries: list[tuple[int, str]]):
    """Run a batch of queries sequentially."""
    results = []
    for idx, query in queries:
        r = await run_query(query, idx)
        # Print compact result
        status = "ERROR" if r["error"] else "OK"
        agents_str = ",".join(r["agents"]) if r["agents"] else "none"
        print(f"[{r['idx']:2d}] {status} {r['elapsed_s']:5.1f}s agents=[{agents_str}] len={r['response_len']:5d} | {r['query'][:60]}")
        if r["error"]:
            print(f"     ERROR: {r['error'][:200]}")
        results.append(r)
    return results


async def main():
    start_idx = int(sys.argv[1]) if len(sys.argv) > 1 else 0
    end_idx = int(sys.argv[2]) if len(sys.argv) > 2 else 999

    ALL_QUERIES = [
        # BATCH 1: Market Data (0-9)
        (1, "top 50 gainers today"),
        (2, "top losers del día con volumen > 1M"),
        (3, "qué acciones están en halt ahora mismo?"),
        (4, "dame los gappers de hoy con precio > $5"),
        (5, "show me stocks with RSI below 30 and volume above 2M"),
        (6, "NVDA current price and technicals"),
        (7, "compare TSLA and AAPL current data"),
        (8, "what are the momentum runners right now?"),
        (9, "stocks with highest relative volume today"),
        (10, "dame las 20 acciones con mayor gap down hoy"),
        # BATCH 2: Historical (10-13)
        (11, "AAPL daily data last 5 days"),
        (12, "show me TSLA minute bars from yesterday"),
        (13, "top movers last friday"),
        (14, "datos diarios de NVDA de la última semana"),
        # BATCH 3: News (14-18)
        (15, "latest market news"),
        (16, "TSLA news today"),
        (17, "qué noticias hay de NVDA?"),
        (18, "what happened with RIME today?"),
        (19, "noticias recientes del mercado"),
        # BATCH 4: Earnings (19-25)
        (20, "what companies report earnings this week?"),
        (21, "qué empresas reportan earnings esta semana?"),
        (22, "NVDA earnings history last quarters"),
        (23, "when does AAPL report earnings next?"),
        (24, "who reports earnings tomorrow?"),
        (25, "empresas que reportaron earnings mejor de lo esperado esta semana"),
        (26, "earnings calendar for next 14 days"),
        # BATCH 5: Financial (26-30)
        (27, "TSLA income statement last 3 years"),
        (28, "NVDA quarterly revenue and EPS last 4 quarters"),
        (29, "AAPL balance sheet"),
        (30, "compare MSFT and GOOGL revenue growth"),
        (31, "dame el estado de resultados trimestral de AMZN"),
        # BATCH 6: SEC (31-34)
        (32, "recent SEC filings for TSLA"),
        (33, "AAPL 10-K filings"),
        (34, "qué filings ha hecho NVDA en la SEC recientemente?"),
        (35, "show me MSFT 8-K filings from this month"),
        # BATCH 7: Events (35-41)
        (36, "recent market events"),
        (37, "TSLA events today"),
        (38, "what stocks had halts last friday?"),
        (39, "VWAP crosses today for NVDA"),
        (40, "qué acciones tuvieron breakout el viernes?"),
        (41, "volume spikes yesterday with price above $10"),
        (42, "event stats for today"),
        # BATCH 8: Screener (42-45)
        (43, "stocks with RSI below 30 and market cap above 1B"),
        (44, "find tech stocks with P/E below 15"),
        (45, "acciones del sector salud con volumen relativo > 3"),
        (46, "small caps under $5 with high volume"),
        # BATCH 9: Research (46-49)
        (47, "what is the market sentiment on NVDA right now?"),
        (48, "analyst ratings for TSLA"),
        (49, "deep dive on AMD competitive position vs NVDA"),
        (50, "cuál es el sentimiento del mercado sobre AAPL?"),
        # BATCH 10: Multi-agent (50-54)
        (51, "complete analysis of NVDA including financials, recent news and sentiment"),
        (52, "TSLA: price, recent news, earnings, and SEC filings"),
        (53, "qué está pasando con AAPL? dame precio, noticias y análisis técnico"),
        (54, "compare NVDA vs AMD: financials, technicals, and sentiment"),
        (55, "top gainers today with their latest news"),
        # BATCH 11: Edge cases (55-62)
        (56, "qué noticias hubo de RIME?"),
        (57, "ha hecho Tesla algo interesante?"),
        (58, "what about AI stocks?"),
        (59, "hello"),
        (60, "qué hora es en el mercado?"),
        (61, "dame todo de una empresa que no existe: $XYZZ"),
        (62, "cuál es la mejor acción para comprar hoy?"),
        (63, "stocks crossing SMA 200 today"),
        # BATCH 12: Quant (63-65)
        (64, "backtest: buy NVDA when RSI < 30, sell when RSI > 70, last year"),
        (65, "calculate TSLA 20-day moving average vs 50-day"),
        (66, "correlación entre NVDA y AMD últimos 6 meses"),
    ]

    batch = [(i, q) for i, q in ALL_QUERIES if start_idx <= i <= end_idx]
    if not batch:
        print(f"No queries in range {start_idx}-{end_idx}")
        return

    print(f"Running {len(batch)} queries (#{batch[0][0]}-#{batch[-1][0]})")
    print("=" * 100)
    results = await run_batch(batch)

    # Save results
    outfile = f"/tmp/battery_{start_idx}_{end_idx}.json"
    with open(outfile, "w") as f:
        json.dump(results, f, ensure_ascii=False, indent=2)
    print(f"\nResults saved to {outfile}")


if __name__ == "__main__":
    asyncio.run(main())
