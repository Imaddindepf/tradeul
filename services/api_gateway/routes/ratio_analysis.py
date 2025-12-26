"""
Ratio Analysis Router
=====================

Análisis de relación entre dos activos:
- Comparación de precios normalizados
- Ratio Y/X con min/max
- Correlación rolling
- Regresión lineal (Beta, Alpha, R², Pearson R)

Endpoint: GET /api/v1/ratio-analysis
"""

from typing import Optional, List
from datetime import datetime, timedelta
from fastapi import APIRouter, HTTPException, Query
import numpy as np

from shared.utils.logger import get_logger
from http_clients import http_clients

logger = get_logger(__name__)

router = APIRouter(prefix="/api/v1/ratio-analysis", tags=["ratio-analysis"])


# ============================================================================
# Helpers - Cálculos estadísticos
# ============================================================================

def calculate_returns(prices: List[float]) -> np.ndarray:
    """Calcular retornos porcentuales diarios."""
    prices_arr = np.array(prices)
    returns = np.diff(prices_arr) / prices_arr[:-1] * 100
    return returns


def calculate_rolling_correlation(
    returns_y: np.ndarray,
    returns_x: np.ndarray,
    window: int
) -> tuple[List[float], List[int]]:
    """
    Calcular correlación rolling entre dos series de retornos.
    Retorna: (valores de correlación, índices válidos)
    """
    n = len(returns_y)
    correlations = []
    valid_indices = []
    
    for i in range(window - 1, n):
        window_y = returns_y[i - window + 1:i + 1]
        window_x = returns_x[i - window + 1:i + 1]
        
        # Calcular correlación de Pearson
        if len(window_y) >= 2 and np.std(window_y) > 0 and np.std(window_x) > 0:
            corr = np.corrcoef(window_y, window_x)[0, 1]
            if not np.isnan(corr):
                correlations.append(round(float(corr), 4))
                valid_indices.append(i)
    
    return correlations, valid_indices


def calculate_regression(
    returns_y: np.ndarray,
    returns_x: np.ndarray
) -> dict:
    """
    Calcular regresión lineal: Y = alpha + beta * X
    
    Retorna:
    - beta: sensibilidad de Y respecto a X
    - alpha: intercepto (retorno excedente)
    - r_squared: coeficiente de determinación
    - pearson_r: correlación de Pearson
    - std_error: error estándar de la regresión
    - std_error_alpha: error estándar de alpha
    - std_error_beta: error estándar de beta
    """
    n = len(returns_y)
    
    if n < 10:
        return None
    
    # Regresión lineal simple usando numpy
    x_mean = np.mean(returns_x)
    y_mean = np.mean(returns_y)
    
    # Beta = Cov(X,Y) / Var(X)
    cov_xy = np.sum((returns_x - x_mean) * (returns_y - y_mean)) / (n - 1)
    var_x = np.sum((returns_x - x_mean) ** 2) / (n - 1)
    
    if var_x == 0:
        return None
    
    beta = cov_xy / var_x
    alpha = y_mean - beta * x_mean
    
    # Predicciones y residuos
    y_pred = alpha + beta * returns_x
    residuals = returns_y - y_pred
    
    # R-squared
    ss_res = np.sum(residuals ** 2)
    ss_tot = np.sum((returns_y - y_mean) ** 2)
    r_squared = 1 - (ss_res / ss_tot) if ss_tot > 0 else 0
    
    # Pearson R
    std_y = np.std(returns_y)
    std_x = np.std(returns_x)
    pearson_r = cov_xy / (std_y * std_x) if (std_y > 0 and std_x > 0) else 0
    
    # Errores estándar
    mse = ss_res / (n - 2) if n > 2 else 0
    std_error = np.sqrt(mse)
    
    se_beta = std_error / np.sqrt(np.sum((returns_x - x_mean) ** 2)) if var_x > 0 else 0
    se_alpha = std_error * np.sqrt(1/n + x_mean**2 / np.sum((returns_x - x_mean) ** 2)) if var_x > 0 else 0
    
    return {
        "beta": round(float(beta), 3),
        "alpha": round(float(alpha), 3),
        "r_squared": round(float(r_squared), 3),
        "pearson_r": round(float(pearson_r), 3),
        "std_error": round(float(std_error), 3),
        "std_error_alpha": round(float(se_alpha), 3),
        "std_error_beta": round(float(se_beta), 3),
    }


def find_min_max_indices(values: List[float]) -> tuple[int, int]:
    """Encontrar índices de mínimo y máximo."""
    if not values:
        return 0, 0
    min_idx = int(np.argmin(values))
    max_idx = int(np.argmax(values))
    return min_idx, max_idx


def calculate_zscore(ratio_values: List[float], lookback: int = 60) -> dict:
    """
    Calcular Z-Score del ratio para pair trading.
    Z = (ratio - mean) / std
    
    Señales típicas:
    - Z > 2: Short spread (ratio muy alto, esperar reversión)
    - Z < -2: Long spread (ratio muy bajo, esperar reversión)
    """
    arr = np.array(ratio_values)
    n = len(arr)
    
    if n < lookback:
        lookback = max(20, n // 2)
    
    # Z-Score rolling
    zscores = []
    for i in range(lookback - 1, n):
        window = arr[i - lookback + 1:i + 1]
        mean = np.mean(window)
        std = np.std(window)
        if std > 0:
            z = (arr[i] - mean) / std
            zscores.append(round(float(z), 3))
        else:
            zscores.append(0.0)
    
    # Z-Score actual (último valor)
    current_z = zscores[-1] if zscores else 0.0
    
    # Señal basada en Z-Score
    if current_z >= 2.0:
        signal = "SHORT_SPREAD"
        signal_strength = min(100, int((current_z - 1) * 50))
    elif current_z <= -2.0:
        signal = "LONG_SPREAD"
        signal_strength = min(100, int((abs(current_z) - 1) * 50))
    elif current_z >= 1.0:
        signal = "WEAK_SHORT"
        signal_strength = int((current_z) * 30)
    elif current_z <= -1.0:
        signal = "WEAK_LONG"
        signal_strength = int((abs(current_z)) * 30)
    else:
        signal = "NEUTRAL"
        signal_strength = 0
    
    return {
        "lookback": lookback,
        "values": zscores,
        "current": current_z,
        "mean": round(float(np.mean(arr[-lookback:])), 6),
        "std": round(float(np.std(arr[-lookback:])), 6),
        "signal": signal,
        "signal_strength": signal_strength,
        "upper_band": 2.0,
        "lower_band": -2.0,
    }


def calculate_half_life(ratio_values: List[float]) -> float:
    """
    Calcular Half-Life de mean reversion usando OLS.
    
    Half-life = -ln(2) / ln(theta)
    donde theta es el coeficiente AR(1) del spread.
    
    Interpretación:
    - < 20 días: Mean reversion rápida, bueno para trading
    - 20-60 días: Mean reversion moderada
    - > 60 días: Mean reversion lenta, menos atractivo
    """
    arr = np.array(ratio_values)
    n = len(arr)
    
    if n < 30:
        return None
    
    # Modelo AR(1): ratio[t] = theta * ratio[t-1] + epsilon
    # Calculamos: delta_ratio = theta * ratio_lag + c
    ratio_lag = arr[:-1]
    delta_ratio = np.diff(arr)
    
    # Regresión OLS
    X = ratio_lag
    y = delta_ratio
    
    # theta = Cov(X, y) / Var(X)
    cov = np.cov(X, y)[0, 1]
    var = np.var(X)
    
    if var == 0:
        return None
    
    theta = cov / var
    
    # Half-life
    if theta >= 0:
        return None  # No mean-reverting
    
    half_life = -np.log(2) / theta
    
    return round(float(half_life), 1) if half_life > 0 and half_life < 500 else None


def calculate_hedge_ratio(prices_y: List[float], prices_x: List[float], beta: float) -> dict:
    """
    Calcular hedge ratio óptimo para pair trading.
    
    Por cada $1000 en Y, necesitas vender $X en el otro activo.
    """
    price_y = prices_y[-1]
    price_x = prices_x[-1]
    
    # Hedge ratio basado en beta
    # Si beta = 1.2, por cada 100 acciones de Y, vendemos 120 de X
    hedge_ratio = abs(beta)
    
    # Calcular shares para $10,000 de capital
    capital = 10000
    shares_y = int(capital / (2 * price_y))  # Mitad del capital en Y
    shares_x = int(shares_y * hedge_ratio * (price_y / price_x))
    
    # Dollar neutral
    dollar_y = shares_y * price_y
    dollar_x = shares_x * price_x
    
    return {
        "beta_hedge": round(hedge_ratio, 3),
        "example": {
            "capital": capital,
            "shares_y": shares_y,
            "shares_x": shares_x,
            "dollar_y": round(dollar_y, 2),
            "dollar_x": round(dollar_x, 2),
            "net_exposure": round(dollar_y - dollar_x, 2),
        }
    }


def calculate_rolling_beta(
    returns_y: np.ndarray,
    returns_x: np.ndarray,
    window: int = 60
) -> tuple[List[float], List[int]]:
    """
    Calcular beta rolling para ver estabilidad del hedge ratio.
    """
    n = len(returns_y)
    betas = []
    valid_indices = []
    
    for i in range(window - 1, n):
        wy = returns_y[i - window + 1:i + 1]
        wx = returns_x[i - window + 1:i + 1]
        
        cov = np.cov(wy, wx)[0, 1]
        var = np.var(wx)
        
        if var > 0:
            beta = cov / var
            betas.append(round(float(beta), 3))
            valid_indices.append(i)
    
    return betas, valid_indices


def calculate_spread_stats(
    ratio_values: List[float],
    zscores: List[float],
    entry_threshold: float = 2.0
) -> dict:
    """
    Calcular estadísticas de backtesting simple del spread.
    
    Estrategia: Entrar cuando |Z| > threshold, salir cuando Z cruza 0.
    """
    if len(zscores) < 20:
        return None
    
    trades = []
    position = 0  # 1 = long spread, -1 = short spread, 0 = flat
    entry_z = 0
    entry_idx = 0
    
    # Alinear zscores con ratio (zscore empieza después del lookback)
    offset = len(ratio_values) - len(zscores)
    
    for i, z in enumerate(zscores):
        ratio_idx = i + offset
        
        if position == 0:
            # Buscar entrada
            if z >= entry_threshold:
                position = -1  # Short spread
                entry_z = z
                entry_idx = ratio_idx
            elif z <= -entry_threshold:
                position = 1  # Long spread
                entry_z = z
                entry_idx = ratio_idx
        else:
            # Buscar salida (mean reversion, Z cruza 0)
            if (position == 1 and z >= 0) or (position == -1 and z <= 0):
                # Calcular P&L del trade
                entry_ratio = ratio_values[entry_idx]
                exit_ratio = ratio_values[ratio_idx]
                pnl_pct = ((exit_ratio / entry_ratio) - 1) * 100 * position
                trades.append({
                    "direction": "LONG" if position == 1 else "SHORT",
                    "entry_z": entry_z,
                    "exit_z": z,
                    "pnl_pct": round(pnl_pct, 2),
                    "duration": ratio_idx - entry_idx,
                })
                position = 0
    
    if not trades:
        return {
            "total_trades": 0,
            "win_rate": 0,
            "avg_pnl": 0,
            "avg_duration": 0,
            "sharpe": 0,
            "max_drawdown": 0,
        }
    
    # Calcular estadísticas
    pnls = [t["pnl_pct"] for t in trades]
    wins = [p for p in pnls if p > 0]
    durations = [t["duration"] for t in trades]
    
    # Sharpe simplificado
    avg_pnl = np.mean(pnls)
    std_pnl = np.std(pnls) if len(pnls) > 1 else 1
    sharpe = (avg_pnl / std_pnl) * np.sqrt(252 / np.mean(durations)) if std_pnl > 0 else 0
    
    # Max drawdown
    cumulative = np.cumsum(pnls)
    running_max = np.maximum.accumulate(cumulative)
    drawdown = running_max - cumulative
    max_dd = np.max(drawdown) if len(drawdown) > 0 else 0
    
    return {
        "total_trades": len(trades),
        "win_rate": round(len(wins) / len(trades) * 100, 1),
        "avg_pnl": round(avg_pnl, 2),
        "total_pnl": round(sum(pnls), 2),
        "avg_duration": round(np.mean(durations), 1),
        "sharpe": round(float(sharpe), 2),
        "max_drawdown": round(float(max_dd), 2),
        "best_trade": round(max(pnls), 2),
        "worst_trade": round(min(pnls), 2),
        "trades": trades[-5:],  # Últimos 5 trades
    }


def calculate_volatility_analysis(
    returns_y: np.ndarray,
    returns_x: np.ndarray
) -> dict:
    """
    Análisis de volatilidad comparativa.
    """
    vol_y = np.std(returns_y) * np.sqrt(252)  # Anualizada
    vol_x = np.std(returns_x) * np.sqrt(252)
    
    vol_ratio = vol_y / vol_x if vol_x > 0 else 0
    
    return {
        "y_annual": round(float(vol_y), 2),
        "x_annual": round(float(vol_x), 2),
        "ratio": round(float(vol_ratio), 2),
        "y_daily": round(float(np.std(returns_y)), 3),
        "x_daily": round(float(np.std(returns_x)), 3),
    }


def _get_recommendation(zscore_data: dict, half_life: float, correlation: float) -> str:
    """
    Generar recomendación de trading basada en métricas.
    """
    z = zscore_data["current"]
    signal = zscore_data["signal"]
    
    # Factores positivos y negativos
    factors = []
    
    # Z-Score
    if abs(z) >= 2.0:
        factors.append(f"Strong Z-Score ({z:.2f})")
    elif abs(z) >= 1.5:
        factors.append(f"Moderate Z-Score ({z:.2f})")
    
    # Half-life
    if half_life:
        if half_life < 20:
            factors.append(f"Fast mean reversion ({half_life:.0f}d)")
        elif half_life < 40:
            factors.append(f"Good mean reversion ({half_life:.0f}d)")
        elif half_life > 60:
            factors.append(f"Slow reversion ({half_life:.0f}d) - caution")
    
    # Correlation
    if correlation:
        if correlation >= 0.7:
            factors.append("High correlation - good pair")
        elif correlation >= 0.5:
            factors.append("Moderate correlation")
        elif correlation < 0.3:
            factors.append("Low correlation - risky pair")
    
    if signal in ["LONG_SPREAD", "SHORT_SPREAD"]:
        action = "Consider entry" if half_life and half_life < 40 else "Wait for better setup"
    elif signal in ["WEAK_LONG", "WEAK_SHORT"]:
        action = "Monitor closely"
    else:
        action = "No trade signal"
    
    return f"{action}. {'; '.join(factors[:3])}"


# ============================================================================
# Main Endpoint
# ============================================================================

@router.get("")
async def get_ratio_analysis(
    symbol_y: str = Query(..., description="Symbol Y (buy side)"),
    symbol_x: str = Query(..., description="Symbol X (sell side / benchmark)"),
    period: str = Query("1Y", description="Period: 1M, 3M, 6M, 1Y, 2Y"),
    corr_window: int = Query(120, ge=20, le=252, description="Rolling correlation window (days)")
):
    """
    Análisis de ratio entre dos activos.
    
    Retorna:
    - Precios históricos de ambos activos
    - Ratio Y/X con puntos min/max
    - Correlación rolling
    - Regresión con estadísticas (Beta, Alpha, R², etc.)
    - Puntos para scatter plot
    """
    symbol_y = symbol_y.upper()
    symbol_x = symbol_x.upper()
    
    # Mapeo de período a días
    period_days = {
        "1M": 30,
        "3M": 90,
        "6M": 180,
        "1Y": 365,
        "2Y": 730,
    }
    
    days = period_days.get(period, 365)
    
    try:
        # Calcular fechas
        end_date = datetime.now()
        start_date = end_date - timedelta(days=days + 30)  # Extra días para correlación
        from_date_str = start_date.strftime("%Y-%m-%d")
        to_date_str = end_date.strftime("%Y-%m-%d")
        
        # Obtener datos históricos de ambos símbolos en paralelo
        # Usamos el cliente Polygon con connection pooling
        import asyncio
        
        data_y_task = http_clients.polygon.get_aggregates(
            symbol=symbol_y,
            multiplier=1,
            timespan="day",
            from_date=from_date_str,
            to_date=to_date_str
        )
        data_x_task = http_clients.polygon.get_aggregates(
            symbol=symbol_x,
            multiplier=1,
            timespan="day",
            from_date=from_date_str,
            to_date=to_date_str
        )
        
        data_y, data_x = await asyncio.gather(data_y_task, data_x_task)
        
        # Extraer precios de Polygon (formato: results[].c = close, results[].t = timestamp ms)
        results_y = data_y.get("results", [])
        results_x = data_x.get("results", [])
        
        if not results_y:
            raise HTTPException(status_code=404, detail=f"No data found for {symbol_y}")
        if not results_x:
            raise HTTPException(status_code=404, detail=f"No data found for {symbol_x}")
        
        # Convertir a diccionarios por fecha para alinear
        # Polygon usa timestamp en ms, convertimos a fecha YYYY-MM-DD
        def ts_to_date(ts_ms: int) -> str:
            return datetime.fromtimestamp(ts_ms / 1000).strftime("%Y-%m-%d")
        
        prices_y_dict = {ts_to_date(item["t"]): item["c"] for item in results_y if item.get("c")}
        prices_x_dict = {ts_to_date(item["t"]): item["c"] for item in results_x if item.get("c")}
        
        # Encontrar fechas comunes y ordenar
        common_dates = sorted(set(prices_y_dict.keys()) & set(prices_x_dict.keys()))
        
        # Filtrar por período solicitado
        cutoff_date = start_date.strftime("%Y-%m-%d")
        common_dates = [d for d in common_dates if d >= cutoff_date]
        
        if len(common_dates) < 30:
            raise HTTPException(
                status_code=400, 
                detail=f"Insufficient overlapping data. Found {len(common_dates)} common dates, need at least 30."
            )
        
        # Extraer precios alineados
        dates = common_dates
        prices_y = [prices_y_dict[d] for d in dates]
        prices_x = [prices_x_dict[d] for d in dates]
        
        # Calcular ratio Y/X
        ratio_values = [round(py / px, 6) for py, px in zip(prices_y, prices_x)]
        min_idx, max_idx = find_min_max_indices(ratio_values)
        
        # Calcular retornos
        returns_y = calculate_returns(prices_y)
        returns_x = calculate_returns(prices_x)
        
        # Correlación rolling
        corr_values, corr_indices = calculate_rolling_correlation(
            returns_y, returns_x, corr_window
        )
        corr_dates = [dates[i + 1] for i in corr_indices]  # +1 porque returns tiene un elemento menos
        
        # Regresión
        regression = calculate_regression(returns_y, returns_x)
        
        # Scatter points (retornos para el plot)
        scatter_points = [
            {"x": round(float(rx), 2), "y": round(float(ry), 2)}
            for rx, ry in zip(returns_x, returns_y)
        ]
        
        # === NUEVAS MÉTRICAS AVANZADAS ===
        
        # Z-Score para pair trading
        zscore_data = calculate_zscore(ratio_values, lookback=min(60, len(ratio_values) // 3))
        
        # Half-Life de mean reversion
        half_life = calculate_half_life(ratio_values)
        
        # Hedge ratio óptimo
        beta = regression["beta"] if regression else 1.0
        hedge_ratio = calculate_hedge_ratio(prices_y, prices_x, beta)
        
        # Rolling beta
        rolling_beta_values, rolling_beta_indices = calculate_rolling_beta(returns_y, returns_x, window=60)
        rolling_beta_dates = [dates[i + 1] for i in rolling_beta_indices]
        
        # Volatility analysis
        volatility = calculate_volatility_analysis(returns_y, returns_x)
        
        # Spread backtest stats
        spread_stats = calculate_spread_stats(ratio_values, zscore_data["values"])
        
        # Construir respuesta
        return {
            "status": "ok",
            "symbols": {
                "y": symbol_y,
                "x": symbol_x
            },
            "period": period,
            "data_points": len(dates),
            "prices": {
                "dates": dates,
                "y": {
                    "symbol": symbol_y,
                    "values": [round(p, 2) for p in prices_y],
                    "latest": round(prices_y[-1], 2) if prices_y else None,
                },
                "x": {
                    "symbol": symbol_x,
                    "values": [round(p, 2) for p in prices_x],
                    "latest": round(prices_x[-1], 2) if prices_x else None,
                }
            },
            "ratio": {
                "values": ratio_values,
                "latest": ratio_values[-1] if ratio_values else None,
                "min": {
                    "value": ratio_values[min_idx],
                    "date": dates[min_idx],
                    "index": min_idx
                },
                "max": {
                    "value": ratio_values[max_idx],
                    "date": dates[max_idx],
                    "index": max_idx
                }
            },
            "correlation": {
                "window": corr_window,
                "dates": corr_dates,
                "values": corr_values,
                "latest": corr_values[-1] if corr_values else None,
                "min": round(float(min(corr_values)), 3) if corr_values else None,
                "max": round(float(max(corr_values)), 3) if corr_values else None,
            },
            "regression": regression,
            "scatter": scatter_points,
            
            # === NUEVOS CAMPOS ===
            "zscore": zscore_data,
            "half_life": half_life,
            "hedge_ratio": hedge_ratio,
            "rolling_beta": {
                "window": 60,
                "dates": rolling_beta_dates,
                "values": rolling_beta_values,
                "latest": rolling_beta_values[-1] if rolling_beta_values else None,
                "min": round(float(min(rolling_beta_values)), 3) if rolling_beta_values else None,
                "max": round(float(max(rolling_beta_values)), 3) if rolling_beta_values else None,
            },
            "volatility": volatility,
            "backtest": spread_stats,
            
            # Resumen ejecutivo para traders
            "summary": {
                "signal": zscore_data["signal"],
                "signal_strength": zscore_data["signal_strength"],
                "zscore": zscore_data["current"],
                "half_life_days": half_life,
                "correlation": corr_values[-1] if corr_values else None,
                "beta": regression["beta"] if regression else None,
                "r_squared": regression["r_squared"] if regression else None,
                "vol_ratio": volatility["ratio"],
                "recommendation": _get_recommendation(zscore_data, half_life, corr_values[-1] if corr_values else 0),
            }
        }
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error("ratio_analysis_error", symbol_y=symbol_y, symbol_x=symbol_x, error=str(e))
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/health")
async def health_check():
    """Health check para el router de ratio analysis."""
    return {"status": "healthy", "service": "ratio-analysis"}

