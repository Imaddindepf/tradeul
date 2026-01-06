"""
Display Functions for DSL
Provides functions to display results as tables and charts
"""

from typing import Any, Dict, List, Optional, Union
from dataclasses import dataclass, field
from enum import Enum
import pandas as pd


class ChartType(str, Enum):
    """Tipos de gráficos soportados"""
    BAR = "bar"
    SCATTER = "scatter"
    LINE = "line"
    HEATMAP = "heatmap"
    PIE = "pie"
    CANDLESTICK = "candlestick"
    OHLC = "ohlc"


@dataclass
class TableOutput:
    """Resultado de display_table"""
    title: str
    columns: List[str]
    rows: List[Dict[str, Any]]
    total: int
    type: str = "table"


@dataclass
class ChartOutput:
    """Resultado de create_chart"""
    title: str
    chart_type: ChartType
    plotly_config: Dict[str, Any]
    type: str = "chart"


@dataclass
class StatsOutput:
    """Resultado de print_stats"""
    title: str
    stats: Dict[str, Dict[str, float]]
    type: str = "stats"


@dataclass
class MissingDataOutput:
    """Resultado cuando los datos no están disponibles"""
    symbol: str
    message: str
    request_id: str
    can_retry: bool
    estimated_wait_seconds: int
    type: str = "missing_data"


# Registro global de outputs (para capturar en ejecución)
_outputs: List[Union[TableOutput, ChartOutput, StatsOutput, MissingDataOutput]] = []


def clear_outputs():
    """Limpia los outputs registrados"""
    global _outputs
    _outputs = []


def get_outputs() -> List[Union[TableOutput, ChartOutput, StatsOutput, MissingDataOutput]]:
    """Retorna los outputs registrados"""
    return _outputs.copy()


def display_missing_data(
    symbol: str,
    message: str,
    request_id: str = "pending",
    can_retry: bool = True,
    estimated_wait_seconds: int = 5
) -> MissingDataOutput:
    """
    Muestra un mensaje de datos faltantes.
    
    El frontend puede usar esto para:
    - Mostrar un mensaje informativo
    - Esperar y reintentar automáticamente
    - Suscribirse a un callback cuando los datos estén disponibles
    
    Args:
        symbol: Símbolo del ticker
        message: Mensaje descriptivo
        request_id: ID de la solicitud de ingesta
        can_retry: Si el frontend puede reintentar
        estimated_wait_seconds: Tiempo estimado de espera
    
    Returns:
        MissingDataOutput
    """
    output = MissingDataOutput(
        symbol=symbol,
        message=message,
        request_id=request_id,
        can_retry=can_retry,
        estimated_wait_seconds=estimated_wait_seconds
    )
    
    _outputs.append(output)
    return output


def display_table(
    df: pd.DataFrame,
    title: str = "Results",
    columns: Optional[List[str]] = None
) -> TableOutput:
    """
    Muestra un DataFrame como tabla.
    
    Args:
        df: DataFrame con los datos
        title: Título de la tabla
        columns: Lista de columnas a mostrar (None = todas)
    
    Returns:
        TableOutput con los datos formateados
    """
    # Manejar DataFrame vacío o None
    if df is None or df.empty:
        output = TableOutput(
            title=title,
            columns=[],
            rows=[],
            total=0
        )
        _outputs.append(output)
        return output
    
    if columns:
        display_df = df[columns] if all(c in df.columns for c in columns) else df
    else:
        display_df = df
    
    # Convertir a lista de diccionarios
    rows = display_df.to_dict(orient='records')
    
    # Formatear valores para JSON
    formatted_rows = []
    for row in rows:
        formatted = {}
        for k, v in row.items():
            if pd.isna(v):
                formatted[k] = None
            elif isinstance(v, float):
                formatted[k] = round(v, 2) if abs(v) < 1e10 else v
            else:
                formatted[k] = v
        formatted_rows.append(formatted)
    
    output = TableOutput(
        title=title,
        columns=list(display_df.columns),
        rows=formatted_rows,
        total=len(formatted_rows)
    )
    
    _outputs.append(output)
    return output


class ChartLimitError(Exception):
    """Error cuando hay demasiados datos para graficar"""
    pass


# Límite máximo de puntos de datos para evitar colapsar el navegador
MAX_CHART_POINTS = 500


def create_chart(
    df: pd.DataFrame,
    chart_type: str = "bar",
    x: str = None,
    y: str = None,
    title: str = "Chart",
    size: Optional[str] = None,
    color: Optional[str] = None,
    labels: Optional[Dict[str, str]] = None,
    # Parámetros para gráficos de velas (candlestick/OHLC)
    open: Optional[str] = None,
    high: Optional[str] = None,
    low: Optional[str] = None,
    close: Optional[str] = None
) -> ChartOutput:
    """
    Crea un gráfico Plotly.
    
    Args:
        df: DataFrame con los datos
        chart_type: Tipo de gráfico ('bar', 'scatter', 'line', 'heatmap', 'pie', 'candlestick', 'ohlc')
        x: Columna para eje X (timestamp para candlestick)
        y: Columna para eje Y
        title: Título del gráfico
        size: Columna para tamaño de puntos (scatter)
        color: Columna para color
        labels: Diccionario de etiquetas personalizadas
        open: Columna para precio de apertura (candlestick/ohlc)
        high: Columna para precio máximo (candlestick/ohlc)
        low: Columna para precio mínimo (candlestick/ohlc)
        close: Columna para precio de cierre (candlestick/ohlc)
    
    Returns:
        ChartOutput con la configuración de Plotly
    
    Raises:
        ChartLimitError: Si hay más de MAX_CHART_POINTS puntos de datos
    """
    # GUARDRAIL: Verificar que el DataFrame no esté vacío
    if df is None or df.empty:
        raise ValueError("No hay datos para graficar. El DataFrame está vacío.")
    
    # GUARDRAIL: Verificar que las columnas existen
    if x and x not in df.columns:
        available = list(df.columns)
        raise KeyError(f"Columna '{x}' no existe. Columnas disponibles: {available}")
    if y and y not in df.columns:
        available = list(df.columns)
        raise KeyError(f"Columna '{y}' no existe. Columnas disponibles: {available}")
    
    # GUARDRAIL: Limitar puntos de datos para no colapsar el navegador
    if len(df) > MAX_CHART_POINTS:
        raise ChartLimitError(
            f"Demasiados datos para graficar ({len(df)} puntos). "
            f"Por favor filtra a menos de {MAX_CHART_POINTS} puntos usando .limit() o .where()."
        )
    
    chart_type_enum = ChartType(chart_type.lower())
    labels = labels or {}
    
    plotly_config = {
        "data": [],
        "layout": {
            "title": {"text": title},
            "template": "plotly_dark",
            "paper_bgcolor": "rgba(0,0,0,0)",
            "plot_bgcolor": "rgba(0,0,0,0)",
            "font": {"color": "#e5e5e5"},
            "margin": {"t": 50, "b": 50, "l": 50, "r": 20}
        }
    }
    
    if chart_type_enum == ChartType.BAR:
        x_data = df[x].tolist() if x else df.index.tolist()
        y_data = df[y].tolist() if y else []
        
        plotly_config["data"].append({
            "type": "bar",
            "x": x_data,
            "y": y_data,
            "marker": {
                "color": _get_bar_colors(y_data),
                "line": {"width": 0}
            }
        })
        plotly_config["layout"]["xaxis"] = {"title": labels.get(x, x) if x else ""}
        plotly_config["layout"]["yaxis"] = {"title": labels.get(y, y) if y else ""}
    
    elif chart_type_enum == ChartType.SCATTER:
        x_data = df[x].tolist() if x else []
        y_data = df[y].tolist() if y else []
        
        trace = {
            "type": "scatter",
            "mode": "markers",
            "x": x_data,
            "y": y_data,
            "text": df['symbol'].tolist() if 'symbol' in df.columns else None,
            "hoverinfo": "text+x+y",
            "marker": {
                "color": "#3b82f6",
                "opacity": 0.7
            }
        }
        
        if size and size in df.columns:
            sizes = df[size].fillna(0).tolist()
            max_size = max(sizes) if sizes else 1
            if max_size > 0:
                normalized = [max(5, min(40, (s / max_size) * 40)) for s in sizes]
                trace["marker"]["size"] = normalized
        
        if color and color in df.columns:
            trace["marker"]["color"] = df[color].tolist()
            trace["marker"]["colorscale"] = "RdYlGn"
            trace["marker"]["showscale"] = True
        
        plotly_config["data"].append(trace)
        plotly_config["layout"]["xaxis"] = {"title": labels.get(x, x) if x else ""}
        plotly_config["layout"]["yaxis"] = {"title": labels.get(y, y) if y else ""}
    
    elif chart_type_enum == ChartType.LINE:
        x_data = df[x].tolist() if x else df.index.tolist()
        y_data = df[y].tolist() if y else []
        
        plotly_config["data"].append({
            "type": "scatter",
            "mode": "lines+markers",
            "x": x_data,
            "y": y_data,
            "line": {"color": "#3b82f6", "width": 2},
            "marker": {"size": 6}
        })
        plotly_config["layout"]["xaxis"] = {"title": labels.get(x, x) if x else ""}
        plotly_config["layout"]["yaxis"] = {"title": labels.get(y, y) if y else ""}
    
    elif chart_type_enum == ChartType.PIE:
        values = df[y].tolist() if y else []
        labels_data = df[x].tolist() if x else []
        
        plotly_config["data"].append({
            "type": "pie",
            "values": values,
            "labels": labels_data,
            "hole": 0.4,
            "textposition": "inside",
            "textinfo": "label+percent"
        })
    
    elif chart_type_enum == ChartType.HEATMAP:
        if x and y:
            pivot = df.pivot_table(index=y, columns=x, aggfunc='size', fill_value=0)
            plotly_config["data"].append({
                "type": "heatmap",
                "z": pivot.values.tolist(),
                "x": pivot.columns.tolist(),
                "y": pivot.index.tolist(),
                "colorscale": "RdYlGn"
            })
    
    elif chart_type_enum == ChartType.CANDLESTICK:
        # Gráfico de velas japonesas
        # Detectar automáticamente columnas OHLC si no se especifican
        open_col = open or 'open'
        high_col = high or 'high'
        low_col = low or 'low'
        close_col = close or 'close'
        x_col = x or 'time' if 'time' in df.columns else 'timestamp'
        
        # Convertir timestamp si es necesario
        if x_col in df.columns:
            x_data = df[x_col].tolist()
            # Si es timestamp numérico, convertir a ISO string para Plotly
            if len(x_data) > 0 and isinstance(x_data[0], (int, float)):
                import datetime
                x_data = [datetime.datetime.fromtimestamp(t).isoformat() for t in x_data]
        else:
            x_data = df.index.tolist()
        
        plotly_config["data"].append({
            "type": "candlestick",
            "x": x_data,
            "open": df[open_col].tolist() if open_col in df.columns else [],
            "high": df[high_col].tolist() if high_col in df.columns else [],
            "low": df[low_col].tolist() if low_col in df.columns else [],
            "close": df[close_col].tolist() if close_col in df.columns else [],
            "increasing": {"line": {"color": "#22c55e"}, "fillcolor": "#22c55e"},
            "decreasing": {"line": {"color": "#ef4444"}, "fillcolor": "#ef4444"}
        })
        
        plotly_config["layout"]["xaxis"] = {
            "title": "Fecha/Hora",
            "type": "date",
            "rangeslider": {"visible": False}
        }
        plotly_config["layout"]["yaxis"] = {"title": "Precio ($)"}
    
    elif chart_type_enum == ChartType.OHLC:
        # Gráfico OHLC (barras)
        open_col = open or 'open'
        high_col = high or 'high'
        low_col = low or 'low'
        close_col = close or 'close'
        x_col = x or 'time' if 'time' in df.columns else 'timestamp'
        
        if x_col in df.columns:
            x_data = df[x_col].tolist()
            if len(x_data) > 0 and isinstance(x_data[0], (int, float)):
                import datetime
                x_data = [datetime.datetime.fromtimestamp(t).isoformat() for t in x_data]
        else:
            x_data = df.index.tolist()
        
        plotly_config["data"].append({
            "type": "ohlc",
            "x": x_data,
            "open": df[open_col].tolist() if open_col in df.columns else [],
            "high": df[high_col].tolist() if high_col in df.columns else [],
            "low": df[low_col].tolist() if low_col in df.columns else [],
            "close": df[close_col].tolist() if close_col in df.columns else [],
            "increasing": {"line": {"color": "#22c55e"}},
            "decreasing": {"line": {"color": "#ef4444"}}
        })
        
        plotly_config["layout"]["xaxis"] = {
            "title": "Fecha/Hora",
            "type": "date",
            "rangeslider": {"visible": False}
        }
        plotly_config["layout"]["yaxis"] = {"title": "Precio ($)"}
    
    output = ChartOutput(
        title=title,
        chart_type=chart_type_enum,
        plotly_config=plotly_config
    )
    
    _outputs.append(output)
    return output


def _get_bar_colors(values: List[float]) -> List[str]:
    """Genera colores para barras (verde positivo, rojo negativo)"""
    colors = []
    for v in values:
        if v is None or (isinstance(v, float) and pd.isna(v)):
            colors.append("#6b7280")
        elif v >= 0:
            colors.append("#22c55e")
        else:
            colors.append("#ef4444")
    return colors


def print_stats(
    df: pd.DataFrame,
    columns: Optional[List[str]] = None,
    title: str = "Statistics"
) -> StatsOutput:
    """
    Calcula y muestra estadísticas de columnas numéricas.
    
    Args:
        df: DataFrame con los datos
        columns: Lista de columnas a analizar (None = todas las numéricas)
        title: Título
    
    Returns:
        StatsOutput con las estadísticas
    """
    if columns:
        numeric_df = df[columns].select_dtypes(include=['float64', 'int64', 'float', 'int'])
    else:
        numeric_df = df.select_dtypes(include=['float64', 'int64', 'float', 'int'])
    
    stats = {}
    for col_name in numeric_df.columns:
        col_data = numeric_df[col_name].dropna()
        if len(col_data) > 0:
            stats[col_name] = {
                "min": round(float(col_data.min()), 2),
                "max": round(float(col_data.max()), 2),
                "mean": round(float(col_data.mean()), 2),
                "median": round(float(col_data.median()), 2),
                "std": round(float(col_data.std()), 2) if len(col_data) > 1 else 0,
                "count": int(len(col_data))
            }
    
    output = StatsOutput(
        title=title,
        stats=stats
    )
    
    _outputs.append(output)
    return output

