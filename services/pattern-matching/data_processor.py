"""
Data Processor for Pattern Matching
Extracts sliding windows from minute aggregates and normalizes them
"""

import os
import gzip
from datetime import datetime, time
from typing import List, Dict, Tuple, Optional, Iterator
from multiprocessing import Pool, cpu_count

import numpy as np
import pandas as pd
import structlog

from config import settings

logger = structlog.get_logger(__name__)


class DataProcessor:
    """
    Processes minute aggregate data into normalized pattern vectors
    
    Each pattern is:
    - A sliding window of N minutes (default: 45)
    - Normalized to cumulative % returns with z-score
    - Associated with metadata (symbol, date, time) and future returns
    """
    
    def __init__(
        self,
        window_size: int = None,
        future_size: int = None,
        step_size: int = None,
        market_open: time = time(9, 30),
        market_close: time = time(16, 0)
    ):
        self.window_size = window_size or settings.window_size
        self.future_size = future_size or settings.future_size
        self.step_size = step_size or settings.step_size
        self.market_open = market_open
        self.market_close = market_close
        
        logger.info(
            "DataProcessor initialized",
            window_size=self.window_size,
            future_size=self.future_size,
            step_size=self.step_size
        )
    
    @staticmethod
    def normalize_pattern(prices: np.ndarray) -> np.ndarray:
        """
        Normalize prices to z-scored cumulative returns
        
        This makes patterns comparable across different price levels
        
        Args:
            prices: Array of close prices
            
        Returns:
            Normalized vector (mean=0, std=1)
        """
        if len(prices) < 2:
            return np.zeros(len(prices), dtype=np.float32)
        
        # Calculate cumulative % returns from first price
        returns = (prices / prices[0] - 1) * 100
        
        # Z-score normalization
        mean = returns.mean()
        std = returns.std()
        
        if std < 1e-8:  # Flat price, avoid division by zero
            return np.zeros(len(returns), dtype=np.float32)
        
        normalized = (returns - mean) / std
        return normalized.astype(np.float32)
    
    @staticmethod
    def calculate_future_returns(
        prices: np.ndarray, 
        last_price: float
    ) -> np.ndarray:
        """Calculate % returns for future prices"""
        return ((prices / last_price) - 1) * 100
    
    def process_daily_file(
        self,
        filepath: str,
        symbols_filter: Optional[List[str]] = None,
        min_volume: int = 1000
    ) -> Tuple[np.ndarray, List[Dict]]:
        """
        Process a single daily CSV file into pattern vectors
        
        Args:
            filepath: Path to .csv.gz file
            symbols_filter: Only process these symbols (None = all)
            min_volume: Minimum total volume to include pattern
            
        Returns:
            vectors: Array of shape (N, window_size)
            metadata: List of dicts with pattern info
        """
        date_str = os.path.basename(filepath).replace('.csv.gz', '')
        
        try:
            # Read compressed CSV
            df = pd.read_csv(filepath, compression='gzip')
            
            # Rename columns if needed (Polygon format)
            if 'window_start' in df.columns:
                df['timestamp'] = pd.to_datetime(df['window_start'], unit='ns')
            
            # Filter market hours
            df['time'] = df['timestamp'].dt.time
            df = df[
                (df['time'] >= self.market_open) & 
                (df['time'] < self.market_close)
            ]
            
            # Filter symbols if specified
            if symbols_filter:
                df = df[df['ticker'].isin(symbols_filter)]
            
            if df.empty:
                return np.array([]), []
            
            vectors = []
            metadata = []
            
            # Process each ticker
            for ticker, group in df.groupby('ticker'):
                group = group.sort_values('timestamp').reset_index(drop=True)
                
                # Need enough data for window + future
                min_length = self.window_size + self.future_size
                if len(group) < min_length:
                    continue
                
                prices = group['close'].values
                volumes = group['volume'].values
                times = group['timestamp'].dt.strftime('%H:%M').values
                
                # Extract sliding windows
                for i in range(0, len(group) - min_length + 1, self.step_size):
                    # Window data
                    window_prices = prices[i:i + self.window_size]
                    window_volume = volumes[i:i + self.window_size].sum()
                    
                    # Skip low volume patterns
                    if window_volume < min_volume:
                        continue
                    
                    # Future data
                    future_start = i + self.window_size
                    future_end = future_start + self.future_size
                    future_prices = prices[future_start:future_end]
                    
                    # Normalize pattern
                    vector = self.normalize_pattern(window_prices)
                    
                    # Skip flat patterns
                    if np.allclose(vector, 0):
                        continue
                    
                    # Calculate future returns
                    last_price = window_prices[-1]
                    future_returns = self.calculate_future_returns(
                        future_prices, last_price
                    ).tolist()
                    
                    vectors.append(vector)
                    metadata.append({
                        'symbol': ticker,
                        'date': date_str,
                        'start_time': times[i],
                        'end_time': times[i + self.window_size - 1],
                        'start_price': float(window_prices[0]),
                        'end_price': float(last_price),
                        'volume': int(window_volume),
                        'future_returns': future_returns,
                    })
            
            logger.info(
                "Processed daily file",
                date=date_str,
                patterns=len(vectors),
                tickers=df['ticker'].nunique()
            )
            
            return np.array(vectors, dtype=np.float32), metadata
            
        except Exception as e:
            logger.error("Error processing file", filepath=filepath, error=str(e))
            return np.array([]), []
    
    def process_multiple_files(
        self,
        filepaths: List[str],
        symbols_filter: Optional[List[str]] = None,
        n_workers: int = None
    ) -> Tuple[np.ndarray, List[Dict]]:
        """
        Process multiple daily files in parallel
        
        Args:
            filepaths: List of file paths
            symbols_filter: Only process these symbols
            n_workers: Number of parallel workers
            
        Returns:
            Combined vectors and metadata
        """
        n_workers = n_workers or max(1, cpu_count() - 1)
        
        logger.info(
            "Processing multiple files",
            files=len(filepaths),
            workers=n_workers
        )
        
        # Prepare arguments for parallel processing
        args = [(fp, symbols_filter) for fp in filepaths]
        
        all_vectors = []
        all_metadata = []
        
        # Process in parallel
        with Pool(n_workers) as pool:
            results = pool.starmap(self.process_daily_file, args)
        
        # Combine results
        for vectors, metadata in results:
            if len(vectors) > 0:
                all_vectors.append(vectors)
                all_metadata.extend(metadata)
        
        if not all_vectors:
            return np.array([]), []
        
        # Assign unique IDs
        for i, meta in enumerate(all_metadata):
            meta['id'] = i
        
        combined_vectors = np.vstack(all_vectors)
        
        logger.info(
            "Processing complete",
            total_patterns=len(combined_vectors),
            total_files=len(filepaths)
        )
        
        return combined_vectors, all_metadata
    
    def get_realtime_pattern(
        self,
        prices: List[float],
        window_size: int = None
    ) -> np.ndarray:
        """
        Normalize a real-time price pattern for searching
        
        Args:
            prices: List of recent close prices
            window_size: Expected window size (for validation)
            
        Returns:
            Normalized vector ready for FAISS search
        """
        window_size = window_size or self.window_size
        
        if len(prices) < window_size:
            raise ValueError(
                f"Need at least {window_size} prices, got {len(prices)}"
            )
        
        # Take last window_size prices
        prices = np.array(prices[-window_size:])
        
        return self.normalize_pattern(prices)


def process_file_wrapper(args):
    """Wrapper for multiprocessing"""
    filepath, symbols_filter, min_volume = args
    processor = DataProcessor()
    return processor.process_daily_file(filepath, symbols_filter, min_volume)


# CLI for testing
if __name__ == "__main__":
    import argparse
    from glob import glob
    
    parser = argparse.ArgumentParser(description="Process minute aggregate files")
    parser.add_argument("--data-dir", type=str, default="./data/minute_aggs")
    parser.add_argument("--limit", type=int, default=5, help="Limit files to process")
    
    args = parser.parse_args()
    
    files = sorted(glob(f"{args.data_dir}/*.csv.gz"))[:args.limit]
    
    if not files:
        print(f"No files found in {args.data_dir}")
        exit(1)
    
    processor = DataProcessor()
    vectors, metadata = processor.process_multiple_files(files)
    
    print(f"\n📊 Processing Results:")
    print(f"  Total patterns: {len(vectors):,}")
    print(f"  Vector shape: {vectors.shape}")
    print(f"  Memory: {vectors.nbytes / 1024**2:.2f} MB")
    
    if metadata:
        print(f"\n  Sample pattern:")
        print(f"    {metadata[0]}")

