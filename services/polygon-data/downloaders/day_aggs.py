"""
Day Aggregates Downloader
Downloads daily OHLCV data from Polygon Flat Files
"""

from datetime import datetime
from config import settings
from .base import BaseDownloader


class DayAggsDownloader(BaseDownloader):
    """
    Downloads daily aggregates from Polygon Flat Files
    
    S3 Path: s3://flatfiles/us_stocks_sip/day_aggs_v1/{year}/{month}/{date}.csv.gz
    
    File format (CSV):
    - ticker: Stock symbol
    - open, high, low, close: OHLC prices
    - volume: Trading volume
    - vwap: Volume weighted average price
    - timestamp: Unix timestamp (nanoseconds) - market open time
    - transactions: Number of transactions
    """
    
    FILE_EXTENSION = ".csv.gz"
    
    def _get_subdir(self) -> str:
        return settings.day_aggs_dir
    
    def _get_s3_key(self, date: datetime) -> str:
        year = date.strftime("%Y")
        month = date.strftime("%m")
        date_str = date.strftime("%Y-%m-%d")
        return f"us_stocks_sip/day_aggs_v1/{year}/{month}/{date_str}.csv.gz"

