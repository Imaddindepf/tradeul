"""
DSL Functions for AI Agent
Extended functions for historical data, technicals, and SEC data
"""

from typing import List, Dict, Any, Optional
from datetime import datetime
import pandas as pd
import numpy as np

from .display import display_table, create_chart, ChartType


# =============================================
# TECHNICAL INDICATORS
# =============================================

def calculate_rsi(prices: List[float], period: int = 14) -> List[Optional[float]]:
    """Calcula RSI (Relative Strength Index)"""
    if len(prices) < period + 1:
        return [None] * len(prices)
    
    deltas = np.diff(prices)
    gains = np.where(deltas > 0, deltas, 0)
    losses = np.where(deltas < 0, -deltas, 0)
    
    avg_gain = np.convolve(gains, np.ones(period)/period, mode='valid')
    avg_loss = np.convolve(losses, np.ones(period)/period, mode='valid')
    
    # Evitar division por cero
    avg_loss = np.where(avg_loss == 0, 0.0001, avg_loss)
    
    rs = avg_gain / avg_loss
    rsi = 100 - (100 / (1 + rs))
    
    # Padding para mantener longitud
    padding = [None] * period
    return padding + list(rsi)


def calculate_sma(prices: List[float], period: int = 20) -> List[Optional[float]]:
    """Calcula SMA (Simple Moving Average)"""
    if len(prices) < period:
        return [None] * len(prices)
    
    sma = np.convolve(prices, np.ones(period)/period, mode='valid')
    padding = [None] * (period - 1)
    return padding + list(sma)


def calculate_ema(prices: List[float], period: int = 20) -> List[Optional[float]]:
    """Calcula EMA (Exponential Moving Average)"""
    if len(prices) < period:
        return [None] * len(prices)
    
    multiplier = 2 / (period + 1)
    ema = [sum(prices[:period]) / period]  # Primera EMA es SMA
    
    for price in prices[period:]:
        ema.append((price - ema[-1]) * multiplier + ema[-1])
    
    padding = [None] * (period - 1)
    return padding + ema


def calculate_macd(
    prices: List[float],
    fast: int = 12,
    slow: int = 26,
    signal: int = 9
) -> Dict[str, List[Optional[float]]]:
    """Calcula MACD"""
    if len(prices) < slow + signal:
        empty = [None] * len(prices)
        return {"macd": empty, "signal": empty, "histogram": empty}
    
    ema_fast = calculate_ema(prices, fast)
    ema_slow = calculate_ema(prices, slow)
    
    # MACD line
    macd_line = [
        f - s if f is not None and s is not None else None
        for f, s in zip(ema_fast, ema_slow)
    ]
    
    # Filtrar None para calcular signal
    macd_values = [v for v in macd_line if v is not None]
    if len(macd_values) < signal:
        return {"macd": macd_line, "signal": [None]*len(prices), "histogram": [None]*len(prices)}
    
    signal_line = calculate_ema(macd_values, signal)
    
    # Alinear signal_line con macd_line
    padding = [None] * (len(macd_line) - len(signal_line))
    signal_line = padding + signal_line
    
    # Histogram
    histogram = [
        m - s if m is not None and s is not None else None
        for m, s in zip(macd_line, signal_line)
    ]
    
    return {
        "macd": macd_line,
        "signal": signal_line,
        "histogram": histogram
    }


def calculate_bollinger(
    prices: List[float],
    period: int = 20,
    std_dev: float = 2.0
) -> Dict[str, List[Optional[float]]]:
    """Calcula Bollinger Bands"""
    if len(prices) < period:
        empty = [None] * len(prices)
        return {"upper": empty, "middle": empty, "lower": empty}
    
    middle = calculate_sma(prices, period)
    
    upper = []
    lower = []
    
    for i in range(len(prices)):
        if middle[i] is None:
            upper.append(None)
            lower.append(None)
        else:
            window = prices[max(0, i-period+1):i+1]
            std = np.std(window)
            upper.append(middle[i] + std_dev * std)
            lower.append(middle[i] - std_dev * std)
    
    return {
        "upper": upper,
        "middle": middle,
        "lower": lower
    }


def add_technicals(
    df: pd.DataFrame,
    indicators: List[str] = None
) -> pd.DataFrame:
    """
    Agrega indicadores tecnicos a un DataFrame de barras.
    
    Args:
        df: DataFrame con columna 'close'
        indicators: Lista de indicadores ['RSI', 'SMA20', 'EMA20', 'MACD', 'BOLLINGER']
    
    Returns:
        DataFrame con indicadores agregados
    """
    if 'close' not in df.columns:
        return df
    
    if indicators is None:
        indicators = ['RSI', 'SMA20']
    
    prices = df['close'].tolist()
    
    for ind in indicators:
        ind_upper = ind.upper()
        
        if ind_upper == 'RSI' or ind_upper == 'RSI14':
            df['rsi'] = calculate_rsi(prices, 14)
        
        elif ind_upper.startswith('SMA'):
            period = int(ind_upper[3:]) if len(ind_upper) > 3 else 20
            df[f'sma{period}'] = calculate_sma(prices, period)
        
        elif ind_upper.startswith('EMA'):
            period = int(ind_upper[3:]) if len(ind_upper) > 3 else 20
            df[f'ema{period}'] = calculate_ema(prices, period)
        
        elif ind_upper == 'MACD':
            macd = calculate_macd(prices)
            df['macd'] = macd['macd']
            df['macd_signal'] = macd['signal']
            df['macd_hist'] = macd['histogram']
        
        elif ind_upper == 'BOLLINGER' or ind_upper == 'BB':
            bb = calculate_bollinger(prices)
            df['bb_upper'] = bb['upper']
            df['bb_middle'] = bb['middle']
            df['bb_lower'] = bb['lower']
    
    return df


# =============================================
# COMPARISON FUNCTIONS
# =============================================

def compare_performance(
    bars_list: List[Dict[str, Any]],
    symbols: List[str]
) -> pd.DataFrame:
    """
    Compara el rendimiento de multiples simbolos.
    
    Args:
        bars_list: Lista de listas de barras por simbolo
        symbols: Lista de simbolos correspondientes
    
    Returns:
        DataFrame con rendimiento normalizado (base 100)
    """
    if not bars_list or not symbols:
        return pd.DataFrame()
    
    # Crear DataFrame con fechas como indice
    dfs = []
    for bars, symbol in zip(bars_list, symbols):
        if bars:
            df = pd.DataFrame(bars)
            df['symbol'] = symbol
            dfs.append(df)
    
    if not dfs:
        return pd.DataFrame()
    
    # Merge por timestamp
    merged = dfs[0][['timestamp', 'close']].rename(columns={'close': symbols[0]})
    
    for df, symbol in zip(dfs[1:], symbols[1:]):
        temp = df[['timestamp', 'close']].rename(columns={'close': symbol})
        merged = merged.merge(temp, on='timestamp', how='outer')
    
    merged = merged.sort_values('timestamp').reset_index(drop=True)
    
    # Normalizar a base 100
    for symbol in symbols:
        if symbol in merged.columns:
            first_val = merged[symbol].dropna().iloc[0] if not merged[symbol].dropna().empty else 1
            merged[f'{symbol}_norm'] = (merged[symbol] / first_val) * 100
    
    return merged


# =============================================
# EXPORT
# =============================================

__all__ = [
    'calculate_rsi',
    'calculate_sma',
    'calculate_ema',
    'calculate_macd',
    'calculate_bollinger',
    'add_technicals',
    'compare_performance'
]

