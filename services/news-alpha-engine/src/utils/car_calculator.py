"""
Cumulative Abnormal Return (CAR) Calculator

This module calculates abnormal returns around news events using
the Market Model methodology, which is the standard in academic
event studies.

CAR = Σ (Actual Return - Expected Return)

Where Expected Return = α + β × Market Return
"""

import numpy as np
import pandas as pd
import polars as pl
from dataclasses import dataclass
from typing import Optional, List, Dict, Tuple
from datetime import datetime, timedelta
from pathlib import Path
import warnings

warnings.filterwarnings('ignore')


@dataclass
class CARResult:
    """Result of CAR calculation for a single event."""
    news_id: str
    ticker: str
    event_date: datetime
    
    # Abnormal returns for different windows
    car_1d: float   # [-1, +1] around event
    car_3d: float   # [0, +3]
    car_5d: float   # [0, +5]
    car_10d: float  # [0, +10]
    
    # Daily abnormal returns
    daily_ar: List[float]
    
    # Statistics
    t_statistic: float
    is_significant: bool  # At 95% confidence
    
    # Model parameters
    alpha: float
    beta: float
    r_squared: float
    
    # Additional info
    estimation_window_start: datetime
    estimation_window_end: datetime
    actual_return_5d: float
    market_return_5d: float


class CARCalculator:
    """
    Calculate Cumulative Abnormal Returns using Market Model.
    
    The Market Model estimates expected returns as:
    E[R_i,t] = α_i + β_i × R_m,t
    
    Where:
    - R_i,t = Return of stock i on day t
    - R_m,t = Return of market (benchmark) on day t
    - α_i, β_i = Estimated from regression on estimation window
    """
    
    def __init__(
        self,
        price_data_path: str,
        benchmark: str = "SPY",
        estimation_window: int = 60,
        gap_days: int = 5,
        min_estimation_days: int = 30,
    ):
        """
        Initialize CAR Calculator.
        
        Args:
            price_data_path: Path to Polygon parquet files
            benchmark: Benchmark ticker (SPY, QQQ, IWM, etc.)
            estimation_window: Days to use for estimating α, β
            gap_days: Gap between estimation and event window
            min_estimation_days: Minimum days required for valid estimation
        """
        self.price_data_path = Path(price_data_path)
        self.benchmark = benchmark
        self.estimation_window = estimation_window
        self.gap_days = gap_days
        self.min_estimation_days = min_estimation_days
        
        # Cache for loaded price data
        self._price_cache: Dict[str, pd.DataFrame] = {}
        self._benchmark_data: Optional[pd.DataFrame] = None
    
    def load_price_data(self, ticker: str) -> Optional[pd.DataFrame]:
        """Load price data for a ticker from Polygon parquet files."""
        
        if ticker in self._price_cache:
            return self._price_cache[ticker]
        
        # Try different file patterns
        patterns = [
            f"{ticker}.parquet",
            f"**/{ticker}.parquet",
            f"**/day/{ticker}.parquet",
        ]
        
        for pattern in patterns:
            files = list(self.price_data_path.glob(pattern))
            if files:
                try:
                    df = pl.read_parquet(files[0]).to_pandas()
                    
                    # Normalize column names
                    df.columns = df.columns.str.lower()
                    
                    # Ensure we have required columns
                    if 'date' in df.columns:
                        df['date'] = pd.to_datetime(df['date'])
                        df = df.set_index('date').sort_index()
                    elif 'timestamp' in df.columns:
                        df['date'] = pd.to_datetime(df['timestamp'])
                        df = df.set_index('date').sort_index()
                    
                    # Calculate returns if not present
                    if 'return' not in df.columns:
                        df['return'] = df['close'].pct_change()
                    
                    self._price_cache[ticker] = df
                    return df
                    
                except Exception as e:
                    print(f"Error loading {ticker}: {e}")
                    continue
        
        return None
    
    def load_benchmark_data(self) -> Optional[pd.DataFrame]:
        """Load benchmark (market) data."""
        if self._benchmark_data is not None:
            return self._benchmark_data
        
        self._benchmark_data = self.load_price_data(self.benchmark)
        return self._benchmark_data
    
    def estimate_market_model(
        self,
        stock_returns: pd.Series,
        market_returns: pd.Series,
    ) -> Tuple[float, float, float]:
        """
        Estimate Market Model parameters using OLS regression.
        
        Returns: (alpha, beta, r_squared)
        """
        # Align the series
        aligned = pd.concat([stock_returns, market_returns], axis=1, join='inner')
        aligned.columns = ['stock', 'market']
        aligned = aligned.dropna()
        
        if len(aligned) < self.min_estimation_days:
            return np.nan, np.nan, np.nan
        
        # OLS regression: stock = alpha + beta * market
        X = aligned['market'].values
        y = aligned['stock'].values
        
        # Add constant for alpha
        X_with_const = np.column_stack([np.ones(len(X)), X])
        
        try:
            # Solve using normal equations
            coeffs = np.linalg.lstsq(X_with_const, y, rcond=None)[0]
            alpha, beta = coeffs[0], coeffs[1]
            
            # Calculate R-squared
            y_pred = alpha + beta * X
            ss_res = np.sum((y - y_pred) ** 2)
            ss_tot = np.sum((y - y.mean()) ** 2)
            r_squared = 1 - (ss_res / ss_tot) if ss_tot > 0 else 0
            
            return alpha, beta, r_squared
            
        except Exception:
            return np.nan, np.nan, np.nan
    
    def calculate_car(
        self,
        ticker: str,
        event_date: datetime,
        news_id: str = "",
        windows: List[int] = [1, 3, 5, 10],
    ) -> Optional[CARResult]:
        """
        Calculate CAR for a single news event.
        
        Args:
            ticker: Stock ticker
            event_date: Date of the news event
            news_id: Optional identifier for the news
            windows: List of event windows to calculate [1, 3, 5, 10]
        
        Returns:
            CARResult object or None if calculation fails
        """
        # Load data
        stock_data = self.load_price_data(ticker)
        market_data = self.load_benchmark_data()
        
        if stock_data is None or market_data is None:
            return None
        
        # Convert event_date to pandas timestamp for indexing
        if isinstance(event_date, str):
            event_date = pd.to_datetime(event_date)
        event_date = pd.Timestamp(event_date).normalize()
        
        # Find the actual trading day (event might be on weekend)
        trading_days = stock_data.index
        event_idx = trading_days.get_indexer([event_date], method='ffill')[0]
        
        if event_idx < 0 or event_idx >= len(trading_days):
            return None
        
        actual_event_date = trading_days[event_idx]
        
        # Define estimation window
        est_end_idx = event_idx - self.gap_days
        est_start_idx = est_end_idx - self.estimation_window
        
        if est_start_idx < 0 or est_end_idx < 0:
            return None
        
        # Get estimation window data
        est_start = trading_days[max(0, est_start_idx)]
        est_end = trading_days[max(0, est_end_idx)]
        
        est_stock_returns = stock_data.loc[est_start:est_end, 'return']
        est_market_returns = market_data.loc[est_start:est_end, 'return']
        
        # Estimate model parameters
        alpha, beta, r_squared = self.estimate_market_model(
            est_stock_returns, est_market_returns
        )
        
        if np.isnan(alpha) or np.isnan(beta):
            return None
        
        # Calculate abnormal returns in event window
        max_window = max(windows)
        event_end_idx = min(event_idx + max_window + 1, len(trading_days) - 1)
        event_start_idx = max(event_idx - 1, 0)  # Include day before
        
        event_start = trading_days[event_start_idx]
        event_end = trading_days[event_end_idx]
        
        event_stock_returns = stock_data.loc[event_start:event_end, 'return']
        event_market_returns = market_data.loc[event_start:event_end, 'return']
        
        # Align returns
        aligned = pd.concat([event_stock_returns, event_market_returns], axis=1, join='inner')
        aligned.columns = ['stock', 'market']
        
        if len(aligned) < 2:
            return None
        
        # Calculate expected and abnormal returns
        expected_returns = alpha + beta * aligned['market']
        abnormal_returns = aligned['stock'] - expected_returns
        
        # Calculate CARs for different windows
        daily_ar = abnormal_returns.values.tolist()
        
        # CAR calculations (index 0 = day before event, index 1 = event day)
        car_1d = sum(daily_ar[0:3]) if len(daily_ar) >= 3 else np.nan  # [-1, +1]
        car_3d = sum(daily_ar[1:5]) if len(daily_ar) >= 5 else np.nan  # [0, +3]
        car_5d = sum(daily_ar[1:7]) if len(daily_ar) >= 7 else np.nan  # [0, +5]
        car_10d = sum(daily_ar[1:12]) if len(daily_ar) >= 12 else np.nan  # [0, +10]
        
        # Calculate t-statistic for 5-day CAR
        if len(daily_ar) >= 7:
            ar_std = np.std(daily_ar[1:7])
            t_stat = car_5d / (ar_std * np.sqrt(6)) if ar_std > 0 else 0
        else:
            t_stat = 0
        
        is_significant = abs(t_stat) > 1.96  # 95% confidence
        
        # Actual returns for reference
        actual_return_5d = sum(aligned['stock'].values[1:7]) if len(aligned) >= 7 else np.nan
        market_return_5d = sum(aligned['market'].values[1:7]) if len(aligned) >= 7 else np.nan
        
        return CARResult(
            news_id=news_id,
            ticker=ticker,
            event_date=actual_event_date,
            car_1d=car_1d,
            car_3d=car_3d,
            car_5d=car_5d,
            car_10d=car_10d,
            daily_ar=daily_ar,
            t_statistic=t_stat,
            is_significant=is_significant,
            alpha=alpha,
            beta=beta,
            r_squared=r_squared,
            estimation_window_start=est_start,
            estimation_window_end=est_end,
            actual_return_5d=actual_return_5d,
            market_return_5d=market_return_5d,
        )
    
    def calculate_batch(
        self,
        events: List[Dict],
        progress_callback=None,
    ) -> pd.DataFrame:
        """
        Calculate CAR for a batch of news events.
        
        Args:
            events: List of dicts with 'news_id', 'ticker', 'timestamp'
            progress_callback: Optional callback for progress updates
        
        Returns:
            DataFrame with CAR results
        """
        results = []
        total = len(events)
        
        for i, event in enumerate(events):
            if progress_callback:
                progress_callback(i, total)
            
            result = self.calculate_car(
                ticker=event['ticker'],
                event_date=event['timestamp'],
                news_id=event.get('news_id', f"event_{i}"),
            )
            
            if result:
                results.append({
                    'news_id': result.news_id,
                    'ticker': result.ticker,
                    'event_date': result.event_date,
                    'car_1d': result.car_1d,
                    'car_3d': result.car_3d,
                    'car_5d': result.car_5d,
                    'car_10d': result.car_10d,
                    't_statistic': result.t_statistic,
                    'is_significant': result.is_significant,
                    'alpha': result.alpha,
                    'beta': result.beta,
                    'r_squared': result.r_squared,
                    'actual_return_5d': result.actual_return_5d,
                    'market_return_5d': result.market_return_5d,
                })
        
        return pd.DataFrame(results)


def classify_impact(car_5d: float) -> Tuple[str, str]:
    """
    Classify the impact direction and magnitude.
    
    Returns: (direction, magnitude)
    """
    # Direction
    if car_5d > 0.01:
        direction = "up"
    elif car_5d < -0.01:
        direction = "down"
    else:
        direction = "neutral"
    
    # Magnitude
    abs_car = abs(car_5d)
    if abs_car > 0.10:
        magnitude = "high"
    elif abs_car > 0.03:
        magnitude = "medium"
    else:
        magnitude = "low"
    
    return direction, magnitude


# ============================================
# Example usage
# ============================================

if __name__ == "__main__":
    # Example
    calculator = CARCalculator(
        price_data_path="/data/polygon/day",
        benchmark="SPY",
    )
    
    # Single event
    result = calculator.calculate_car(
        ticker="AAPL",
        event_date="2024-01-15",
        news_id="test_001",
    )
    
    if result:
        print(f"CAR Results for {result.ticker}:")
        print(f"  CAR 1d: {result.car_1d:.4f}")
        print(f"  CAR 5d: {result.car_5d:.4f}")
        print(f"  T-stat: {result.t_statistic:.2f}")
        print(f"  Significant: {result.is_significant}")
        print(f"  Beta: {result.beta:.3f}")

