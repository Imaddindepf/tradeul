"""
Daily Pattern Index Updater
Incrementally adds new days to the FAISS index without rebuilding
"""

import os
import gzip
import csv
import sqlite3
from datetime import datetime, timedelta
from typing import List, Optional, Tuple

import numpy as np
import faiss
import structlog

from config import settings
from flat_files_downloader import FlatFilesDownloader

logger = structlog.get_logger(__name__)


class DailyUpdater:
    """
    Incrementally updates the pattern index with new days
    
    Process:
    1. Check for new flat files from Polygon
    2. Download if not present locally
    3. Extract patterns from the new day
    4. Add to existing FAISS index
    5. Add metadata to SQLite
    """
    
    def __init__(
        self,
        index_dir: str = None,
        data_dir: str = None,
        window_size: int = 45,
    ):
        self.index_dir = index_dir or settings.index_dir
        self.data_dir = data_dir or settings.data_dir
        self.window_size = window_size
        
        self.index_path = f"{self.index_dir}/patterns_ivfpq.index"
        self.metadata_path = f"{self.index_dir}/patterns_metadata.db"
        self.trajectories_path = f"{self.index_dir}/patterns_trajectories.npy"
        self.flats_dir = f"{self.data_dir}/minute_aggs"
        
        self.downloader = FlatFilesDownloader()
        
        logger.info("DailyUpdater initialized", 
                   index_dir=self.index_dir,
                   flats_dir=self.flats_dir)
    
    def get_indexed_dates(self) -> set:
        """Get dates already in the index from SQLite"""
        if not os.path.exists(self.metadata_path):
            return set()
        
        conn = sqlite3.connect(self.metadata_path)
        cursor = conn.execute("SELECT DISTINCT date FROM patterns")
        dates = {row[0] for row in cursor.fetchall()}
        conn.close()
        return dates
    
    def get_available_flat_dates(self) -> set:
        """Get dates available as local flat files"""
        if not os.path.exists(self.flats_dir):
            return set()
        
        dates = set()
        for f in os.listdir(self.flats_dir):
            if f.endswith('.csv.gz'):
                date_str = f.replace('.csv.gz', '')
                dates.add(date_str)
        return dates
    
    def find_missing_dates(self) -> List[str]:
        """Find dates with flat files but not in index"""
        indexed = self.get_indexed_dates()
        available = self.get_available_flat_dates()
        missing = available - indexed
        return sorted(list(missing))
    
    @staticmethod
    def normalize_pattern(prices: np.ndarray) -> np.ndarray:
        """Normalize prices to z-scored cumulative returns"""
        if len(prices) < 2:
            return np.zeros(len(prices), dtype=np.float32)
        
        returns = (prices / prices[0] - 1) * 100
        mean = returns.mean()
        std = returns.std()
        
        if std < 1e-8:
            return np.zeros(len(returns), dtype=np.float32)
        
        return ((returns - mean) / std).astype(np.float32)
    
    def extract_patterns_from_flat(
        self, 
        date_str: str
    ) -> Tuple[np.ndarray, List[dict]]:
        """
        Extract patterns from a flat file
        
        Returns:
            vectors: numpy array of pattern vectors
            metadata: list of metadata dicts
        """
        file_path = f"{self.flats_dir}/{date_str}.csv.gz"
        
        if not os.path.exists(file_path):
            logger.warning("Flat file not found", date=date_str)
            return np.array([]), []
        
        # Read and organize data by ticker
        ticker_data = {}
        
        with gzip.open(file_path, 'rt') as f:
            reader = csv.DictReader(f)
            for row in reader:
                ticker = row['ticker']
                if ticker not in ticker_data:
                    ticker_data[ticker] = []
                
                ticker_data[ticker].append({
                    'timestamp': int(row['window_start']),
                    'close': float(row['close']),
                })
        
        # Extract patterns for each ticker
        vectors = []
        metadata = []
        
        for ticker, bars in ticker_data.items():
            # Sort by timestamp
            bars = sorted(bars, key=lambda x: x['timestamp'])
            
            if len(bars) < self.window_size + 15:  # Need window + future
                continue
            
            prices = np.array([b['close'] for b in bars])
            
            # Slide window
            for i in range(len(bars) - self.window_size - 15 + 1):
                window_prices = prices[i:i + self.window_size]
                future_prices = prices[i + self.window_size:i + self.window_size + 15]
                
                # Normalize pattern
                pattern = self.normalize_pattern(window_prices)
                
                if np.any(np.isnan(pattern)) or np.all(pattern == 0):
                    continue
                
                # Calculate future returns (15 points)
                if len(future_prices) >= 15 and window_prices[-1] > 0:
                    future_returns = ((future_prices / window_prices[-1]) - 1) * 100
                    final_return = float(future_returns[-1])
                else:
                    future_returns = np.zeros(15, dtype=np.float32)
                    final_return = 0.0
                
                # Get time from timestamp (convert to ET)
                ts = bars[i]['timestamp'] // 1_000_000_000
                bar_time = datetime.utcfromtimestamp(ts)
                # Rough ET conversion
                bar_time = bar_time - timedelta(hours=5)
                time_str = bar_time.strftime('%H:%M')
                
                vectors.append(pattern)
                metadata.append({
                    'symbol': ticker,
                    'date': date_str,
                    'start_time': time_str,
                    'final_return': final_return,
                    'future_returns': future_returns.astype(np.float32),
                })
        
        if vectors:
            vectors = np.vstack(vectors).astype('float32')
        else:
            vectors = np.array([]).reshape(0, self.window_size).astype('float32')
        
        logger.info("Extracted patterns", 
                   date=date_str, 
                   n_patterns=len(metadata),
                   n_tickers=len(ticker_data))
        
        return vectors, metadata
    
    def add_to_index(
        self, 
        vectors: np.ndarray, 
        metadata: List[dict]
    ) -> int:
        """Add new vectors and metadata to existing index"""
        if len(vectors) == 0:
            return 0
        
        # Load existing index
        if not os.path.exists(self.index_path):
            logger.error("Index not found", path=self.index_path)
            return 0
        
        index = faiss.read_index(self.index_path)
        start_id = index.ntotal
        
        # Add vectors to FAISS
        index.add(vectors)
        
        # Save updated index
        faiss.write_index(index, self.index_path)
        logger.info("Updated FAISS index", 
                   new_vectors=len(vectors),
                   total_vectors=index.ntotal)
        
        # Add metadata to SQLite
        conn = sqlite3.connect(self.metadata_path)
        cursor = conn.cursor()
        
        batch = [
            (start_id + i, m['symbol'], m['date'], m['start_time'], m['final_return'])
            for i, m in enumerate(metadata)
        ]
        
        cursor.executemany(
            'INSERT INTO patterns VALUES (?,?,?,?,?)', 
            batch
        )
        conn.commit()
        conn.close()
        
        logger.info("Updated SQLite metadata", new_entries=len(metadata))
        
        # Add trajectories to .npy file (append to memmap)
        if os.path.exists(self.trajectories_path):
            # Get current size
            existing = np.memmap(self.trajectories_path, dtype='float32', mode='r')
            current_count = len(existing) // 15
            del existing
            
            # Expand file and add new trajectories
            new_trajectories = np.array([m['future_returns'] for m in metadata], dtype='float32')
            
            expanded = np.memmap(
                self.trajectories_path, 
                dtype='float32', 
                mode='r+',
                shape=(current_count + len(metadata), 15)
            )
            expanded[current_count:] = new_trajectories
            expanded.flush()
            del expanded
            
            logger.info("Updated trajectories file", 
                       new_entries=len(metadata),
                       total_entries=current_count + len(metadata))
        else:
            logger.warning("Trajectories file not found, skipping", path=self.trajectories_path)
        
        return len(vectors)
    
    def update_date(self, date_str: str) -> int:
        """Update index with a specific date"""
        logger.info("Processing date", date=date_str)
        
        # Extract patterns
        vectors, metadata = self.extract_patterns_from_flat(date_str)
        
        if len(vectors) == 0:
            logger.warning("No patterns extracted", date=date_str)
            return 0
        
        # Add to index
        added = self.add_to_index(vectors, metadata)
        
        return added
    
    def check_and_download_new(self) -> List[str]:
        """Check Polygon for new flats and download them"""
        # Check last 7 days for any missing flats
        end_date = datetime.now()
        start_date = end_date - timedelta(days=7)
        
        downloaded = self.downloader.download_range(
            start_date, 
            end_date,
            max_workers=2
        )
        
        return downloaded
    
    def run_daily_update(self) -> dict:
        """
        Run the daily update process
        
        1. Download any new flats from Polygon
        2. Find dates not yet in index
        3. Process and add them
        """
        logger.info("Starting daily update")
        
        # Step 1: Download new flats
        downloaded = self.check_and_download_new()
        logger.info("Downloaded flats", count=len(downloaded))
        
        # Step 2: Find missing dates
        missing = self.find_missing_dates()
        logger.info("Found missing dates", dates=missing)
        
        # Step 3: Process each missing date
        total_added = 0
        processed_dates = []
        
        for date_str in missing:
            try:
                added = self.update_date(date_str)
                if added > 0:
                    total_added += added
                    processed_dates.append(date_str)
            except Exception as e:
                logger.error("Failed to process date", date=date_str, error=str(e))
        
        result = {
            "downloaded_flats": len(downloaded),
            "missing_dates": missing,
            "processed_dates": processed_dates,
            "patterns_added": total_added,
            "timestamp": datetime.now().isoformat(),
        }
        
        logger.info("Daily update complete", **result)
        return result


# CLI for manual runs
if __name__ == "__main__":
    import argparse
    import json
    
    parser = argparse.ArgumentParser(description="Daily Pattern Index Updater")
    parser.add_argument("--check", action="store_true", help="Only check for missing dates")
    parser.add_argument("--date", type=str, help="Update specific date (YYYY-MM-DD)")
    parser.add_argument("--download", action="store_true", help="Download new flats only")
    
    args = parser.parse_args()
    
    updater = DailyUpdater()
    
    if args.check:
        missing = updater.find_missing_dates()
        print(f"Missing dates: {missing}")
    elif args.date:
        added = updater.update_date(args.date)
        print(f"Added {added} patterns for {args.date}")
    elif args.download:
        downloaded = updater.check_and_download_new()
        print(f"Downloaded: {downloaded}")
    else:
        result = updater.run_daily_update()
        print(json.dumps(result, indent=2))

