"""
Indicators Module - Extensible indicator system.

Provides a BaseIndicator interface and IndicatorRegistry for managing
all technical/analytical indicators.

Current indicators (existing files, pre-date this module):
- rvol_calculator.py: Relative Volume by time slot
- volume_window_tracker.py: Rolling volume windows (1m, 5m, 10m, 15m, 30m)
- price_window_tracker.py: Rolling price change windows
- trades_anomaly_detector.py: Z-Score based trades anomaly detection
- trades_count_tracker.py: Daily accumulated trade count
- intraday_tracker.py: Intraday high/low tracking
- ATRCalculator: Average True Range (in shared/utils)

Future indicators (add here):
- RSI(14) from minute bars
- MACD (EMA12 - EMA26) from minute bars
- EMA(9), EMA(21) from minute bars
"""

from .base import BaseIndicator
from .registry import IndicatorRegistry

__all__ = ["BaseIndicator", "IndicatorRegistry"]
