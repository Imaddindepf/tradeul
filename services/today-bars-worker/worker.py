#!/usr/bin/env python3
"""
Today Bars Worker

Downloads minute bars for today from Polygon and stores in today.parquet.
- Batch: Every 5 minutes, downloads active tickers from scanner
- On-demand: Exposed API to download specific tickers
- Cleanup: Handled by maintenance service
"""

import os
import asyncio
import httpx
import pandas as pd
import pyarrow.parquet as pq
import pyarrow as pa
from pathlib import Path
from datetime import datetime, timedelta
from typing import List, Set, Optional
import pytz
import structlog
from fastapi import FastAPI, HTTPException
from pydantic import BaseModel
import uvicorn

# Configuration
POLYGON_API_KEY = os.getenv("POLYGON_API_KEY", "vjzI76TMiepqrMZKphpfs3SA54JFkhEx")
SCANNER_URL = os.getenv("SCANNER_URL", "http://scanner:8020")
DATA_DIR = Path(os.getenv("DATA_DIR", "/data/polygon/minute_aggs"))
TODAY_FILE = DATA_DIR / "today.parquet"
BATCH_INTERVAL = int(os.getenv("BATCH_INTERVAL", "300"))  # 5 minutes
ET = pytz.timezone("America/New_York")

# Logging
structlog.configure(
    processors=[
        structlog.processors.TimeStamper(fmt="iso"),
        structlog.processors.JSONRenderer()
    ]
)
logger = structlog.get_logger()

# FastAPI app for on-demand requests
app = FastAPI(title="Today Bars Worker")

# In-memory tracking
cached_tickers: Set[str] = set()
last_batch_time: Optional[datetime] = None


class TickerRequest(BaseModel):
    tickers: List[str]


async def get_scanner_tickers() -> List[str]:
    """Get active tickers from scanner service."""
    try:
        async with httpx.AsyncClient(timeout=10) as client:
            resp = await client.get(f"{SCANNER_URL}/api/scanner/filtered")
            if resp.status_code == 200:
                data = resp.json()
                tickers = [item.get("symbol") for item in data if item.get("symbol")]
                logger.info("scanner_tickers_fetched", count=len(tickers))
                return tickers[:1000]  # Limit to top 1000
    except Exception as e:
        logger.warning("scanner_fetch_failed", error=str(e))
    return []


async def download_ticker_bars(ticker: str, date_str: str) -> pd.DataFrame:
    """Download minute bars for a single ticker from Polygon."""
    url = f"https://api.polygon.io/v2/aggs/ticker/{ticker}/range/1/minute/{date_str}/{date_str}"
    params = {
        "apiKey": POLYGON_API_KEY,
        "adjusted": "true",
        "sort": "asc",
        "limit": "50000"
    }
    
    try:
        async with httpx.AsyncClient(timeout=30) as client:
            resp = await client.get(url, params=params)
            if resp.status_code == 200:
                data = resp.json()
                results = data.get("results", [])
                if results:
                    df = pd.DataFrame(results)
                    df["symbol"] = ticker
                    # Rename columns to match our schema
                    df = df.rename(columns={
                        "t": "window_start",
                        "o": "open",
                        "h": "high",
                        "l": "low",
                        "c": "close",
                        "v": "volume",
                        "n": "transactions"
                    })
                    # Keep only needed columns
                    cols = ["symbol", "window_start", "open", "high", "low", "close", "volume", "transactions"]
                    df = df[[c for c in cols if c in df.columns]]
                    return df
    except Exception as e:
        logger.warning("ticker_download_failed", ticker=ticker, error=str(e))
    
    return pd.DataFrame()


async def download_batch(tickers: List[str]) -> pd.DataFrame:
    """Download minute bars for multiple tickers concurrently."""
    today_str = datetime.now(ET).strftime("%Y-%m-%d")
    
    # Limit concurrency to avoid rate limits
    semaphore = asyncio.Semaphore(10)
    
    async def download_with_semaphore(ticker: str) -> pd.DataFrame:
        async with semaphore:
            return await download_ticker_bars(ticker, today_str)
    
    tasks = [download_with_semaphore(t) for t in tickers]
    results = await asyncio.gather(*tasks)
    
    dfs = [df for df in results if not df.empty]
    if dfs:
        return pd.concat(dfs, ignore_index=True)
    return pd.DataFrame()


def load_existing_data() -> pd.DataFrame:
    """Load existing today.parquet if it exists."""
    if TODAY_FILE.exists():
        try:
            return pd.read_parquet(TODAY_FILE)
        except Exception as e:
            logger.warning("failed_to_load_existing", error=str(e))
    return pd.DataFrame()


def save_data(df: pd.DataFrame):
    """Save data to today.parquet, merging with existing."""
    global cached_tickers
    
    if df.empty:
        return
    
    # Load existing data
    existing = load_existing_data()
    
    if not existing.empty:
        # Combine and deduplicate
        combined = pd.concat([existing, df], ignore_index=True)
        # Remove duplicates based on symbol + window_start
        combined = combined.drop_duplicates(subset=["symbol", "window_start"], keep="last")
    else:
        combined = df
    
    # Ensure directory exists
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    
    # Save to parquet
    combined.to_parquet(TODAY_FILE, index=False)
    
    # Update cached tickers
    cached_tickers = set(combined["symbol"].unique())
    
    logger.info("data_saved", 
        total_rows=len(combined), 
        tickers=len(cached_tickers),
        file=str(TODAY_FILE)
    )


async def batch_update():
    """Periodic batch update of minute bars."""
    global last_batch_time
    
    logger.info("batch_update_starting")
    
    # Get tickers from scanner
    tickers = await get_scanner_tickers()
    
    if not tickers:
        logger.warning("no_tickers_to_download")
        return
    
    # Filter out already cached tickers for efficiency
    # But still download to get latest data
    new_tickers = [t for t in tickers if t not in cached_tickers]
    update_tickers = list(cached_tickers)[:500]  # Update existing cached
    
    all_tickers = list(set(new_tickers + update_tickers))[:1000]
    
    logger.info("downloading_tickers", 
        new=len(new_tickers), 
        update=len(update_tickers),
        total=len(all_tickers)
    )
    
    # Download
    df = await download_batch(all_tickers)
    
    if not df.empty:
        save_data(df)
    
    last_batch_time = datetime.now(ET)
    logger.info("batch_update_complete", rows=len(df))


async def run_batch_loop():
    """Run batch updates on schedule."""
    while True:
        try:
            await batch_update()
        except Exception as e:
            logger.error("batch_update_error", error=str(e))
        
        await asyncio.sleep(BATCH_INTERVAL)


# API Endpoints

@app.get("/health")
async def health():
    return {
        "status": "healthy",
        "cached_tickers": len(cached_tickers),
        "last_batch": last_batch_time.isoformat() if last_batch_time else None,
        "file_exists": TODAY_FILE.exists()
    }


@app.post("/download")
async def download_tickers(request: TickerRequest):
    """On-demand download of specific tickers."""
    if not request.tickers:
        raise HTTPException(400, "No tickers provided")
    
    # Limit to 50 tickers per request
    tickers = request.tickers[:50]
    
    logger.info("on_demand_download", tickers=tickers)
    
    df = await download_batch(tickers)
    
    if not df.empty:
        save_data(df)
        return {
            "success": True,
            "downloaded": len(df["symbol"].unique()),
            "rows": len(df)
        }
    
    return {"success": False, "message": "No data found"}


@app.get("/tickers")
async def list_cached_tickers():
    """List all cached tickers."""
    return {
        "count": len(cached_tickers),
        "tickers": sorted(list(cached_tickers))
    }


@app.on_event("startup")
async def startup():
    """Initialize on startup."""
    global cached_tickers
    
    # Load existing cached tickers
    existing = load_existing_data()
    if not existing.empty:
        cached_tickers = set(existing["symbol"].unique())
        logger.info("loaded_existing_cache", tickers=len(cached_tickers))
    
    # Start batch loop in background
    asyncio.create_task(run_batch_loop())
    logger.info("worker_started", interval=BATCH_INTERVAL)


if __name__ == "__main__":
    uvicorn.run(app, host="0.0.0.0", port=8035)

