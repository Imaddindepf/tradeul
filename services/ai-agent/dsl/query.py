"""
Query Builder for DSL
Provides a fluent interface for building data queries
"""

from typing import Any, Dict, List, Optional, Tuple, TYPE_CHECKING
from dataclasses import dataclass, field
import pandas as pd

from .column import Condition, col

if TYPE_CHECKING:
    from ..data.data_provider import DataProvider


# Campos permitidos del modelo ScannerTicker
ALLOWED_COLUMNS = [
    # Identity
    'symbol', 'timestamp',
    
    # Prices
    'price', 'bid', 'ask', 'bid_size', 'ask_size',
    'spread', 'spread_percent', 'bid_ask_ratio', 'distance_from_nbbo',
    'open', 'high', 'low', 'prev_close', 'vwap', 'price_vs_vwap',
    
    # Intraday extremes
    'intraday_high', 'intraday_low',
    'price_from_high', 'price_from_low',
    'price_from_intraday_high', 'price_from_intraday_low',
    
    # Changes
    'change', 'change_percent',
    
    # Volume
    'volume', 'volume_today', 'minute_volume',
    'avg_volume_5d', 'avg_volume_10d', 'avg_volume_30d', 'avg_volume_3m',
    'dollar_volume', 'volume_today_pct', 'volume_yesterday_pct',
    'prev_volume',
    
    # Volume windows
    'vol_1min', 'vol_5min', 'vol_10min', 'vol_15min', 'vol_30min',
    
    # Price change windows
    'chg_1min', 'chg_5min', 'chg_10min', 'chg_15min', 'chg_30min',
    
    # Fundamentals
    'market_cap', 'free_float', 'free_float_percent', 'shares_outstanding',
    'sector', 'industry', 'exchange',
    
    # Indicators
    'rvol', 'rvol_slot', 'atr', 'atr_percent',
    
    # Anomaly detection
    'trades_today', 'avg_trades_5d', 'trades_z_score', 'is_trade_anomaly',
    
    # Post-market
    'postmarket_change_percent', 'postmarket_volume',
    
    # Session & scoring
    'session', 'score', 'rank',
    
    # Meta
    'filters_matched', 'last_trade_timestamp'
]

# Fuentes de datos permitidas
ALLOWED_SOURCES = [
    'scanner',          # Todos los tickers filtrados
    'gappers_up',       # Categoría: Gap up
    'gappers_down',     # Categoría: Gap down
    'momentum_up',      # Categoría: Momentum alcista
    'momentum_down',    # Categoría: Momentum bajista
    'anomalies',        # Categoría: Anomalías
    'high_volume',      # Categoría: Alto volumen
    'new_highs',        # Categoría: Nuevos máximos
    'new_lows',         # Categoría: Nuevos mínimos
    'winners',          # Categoría: Ganadores
    'losers',           # Categoría: Perdedores
    'reversals',        # Categoría: Reversals
    'post_market',      # Categoría: Post-market
    'snapshot',         # Snapshot completo (11k+ tickers)
]


class QueryValidationError(Exception):
    """Error de validación de query"""
    pass


@dataclass
class QueryConfig:
    """Configuración de la query"""
    columns: List[str] = field(default_factory=list)
    source: str = 'scanner'
    conditions: List[Condition] = field(default_factory=list)
    order_column: Optional[str] = None
    order_ascending: bool = True
    limit_value: int = 50
    
    # Límites de seguridad
    MAX_LIMIT = 500


class Query:
    """
    Query builder con interfaz fluida para consultar datos del mercado.
    
    Usage:
        total, df = (Query()
            .select('symbol', 'price', 'change_percent', 'rvol_slot')
            .from_source('scanner')
            .where(
                col('change_percent') >= 5,
                col('rvol_slot') >= 2.0
            )
            .order_by('change_percent', ascending=False)
            .limit(25)
            .execute())
    """
    
    def __init__(self):
        self._config = QueryConfig()
        self._data_provider: Optional['DataProvider'] = None
    
    def select(self, *columns: str) -> 'Query':
        """
        Selecciona columnas a retornar.
        
        Args:
            *columns: Nombres de columnas (deben estar en ALLOWED_COLUMNS)
        """
        for col_name in columns:
            if col_name not in ALLOWED_COLUMNS:
                raise QueryValidationError(
                    f"Columna '{col_name}' no permitida. "
                    f"Columnas válidas: {', '.join(sorted(ALLOWED_COLUMNS)[:20])}..."
                )
            if col_name not in self._config.columns:
                self._config.columns.append(col_name)
        return self
    
    def from_source(self, source: str) -> 'Query':
        """
        Especifica la fuente de datos.
        
        Args:
            source: Una de las fuentes en ALLOWED_SOURCES
        """
        if source not in ALLOWED_SOURCES:
            raise QueryValidationError(
                f"Fuente '{source}' no permitida. "
                f"Fuentes válidas: {', '.join(ALLOWED_SOURCES)}"
            )
        self._config.source = source
        return self
    
    def where(self, *conditions: Condition) -> 'Query':
        """
        Añade condiciones de filtro.
        
        Args:
            *conditions: Condiciones creadas con col()
        """
        for condition in conditions:
            if not isinstance(condition, Condition):
                raise QueryValidationError(
                    f"Condición inválida. Usa col('campo') operador valor. "
                    f"Recibido: {type(condition)}"
                )
            if condition.column not in ALLOWED_COLUMNS:
                raise QueryValidationError(
                    f"Columna '{condition.column}' en condición no permitida."
                )
            self._config.conditions.append(condition)
        return self
    
    def order_by(self, column: str, ascending: bool = True) -> 'Query':
        """
        Ordena los resultados.
        
        Args:
            column: Columna para ordenar
            ascending: True para ascendente, False para descendente
        """
        if column not in ALLOWED_COLUMNS:
            raise QueryValidationError(
                f"Columna '{column}' para ordenar no permitida."
            )
        self._config.order_column = column
        self._config.order_ascending = ascending
        return self
    
    def limit(self, n: int) -> 'Query':
        """
        Limita el número de resultados.
        
        Args:
            n: Número máximo de resultados (máximo: 500)
        """
        if n < 1:
            raise QueryValidationError("Limit debe ser >= 1")
        self._config.limit_value = min(n, QueryConfig.MAX_LIMIT)
        return self
    
    def validate(self) -> List[str]:
        """
        Valida la configuración de la query.
        
        Returns:
            Lista de errores (vacía si es válida)
        """
        errors = []
        
        if not self._config.columns:
            errors.append("Debe seleccionar al menos una columna con .select()")
        
        if not self._config.source:
            errors.append("Debe especificar una fuente con .from_source()")
        
        return errors
    
    def to_dict(self) -> Dict[str, Any]:
        """Convierte la query a diccionario para serialización"""
        return {
            'columns': self._config.columns,
            'source': self._config.source,
            'conditions': [
                {
                    'column': c.column,
                    'operator': c.operator.value,
                    'value': c.value,
                    'value2': c.value2
                }
                for c in self._config.conditions
            ],
            'order_column': self._config.order_column,
            'order_ascending': self._config.order_ascending,
            'limit': self._config.limit_value
        }
    
    def to_code(self) -> str:
        """Genera el código DSL representativo de esta query"""
        lines = ["(Query()"]
        
        # Select
        cols = ", ".join(f"'{c}'" for c in self._config.columns)
        lines.append(f"    .select({cols})")
        
        # From
        lines.append(f"    .from_source('{self._config.source}')")
        
        # Where
        if self._config.conditions:
            cond_strs = []
            for c in self._config.conditions:
                if c.operator.value == 'eq':
                    cond_strs.append(f"col('{c.column}') == {repr(c.value)}")
                elif c.operator.value == 'ne':
                    cond_strs.append(f"col('{c.column}') != {repr(c.value)}")
                elif c.operator.value == 'gt':
                    cond_strs.append(f"col('{c.column}') > {repr(c.value)}")
                elif c.operator.value == 'ge':
                    cond_strs.append(f"col('{c.column}') >= {repr(c.value)}")
                elif c.operator.value == 'lt':
                    cond_strs.append(f"col('{c.column}') < {repr(c.value)}")
                elif c.operator.value == 'le':
                    cond_strs.append(f"col('{c.column}') <= {repr(c.value)}")
                elif c.operator.value == 'between':
                    cond_strs.append(f"col('{c.column}').between({repr(c.value)}, {repr(c.value2)})")
                elif c.operator.value == 'isin':
                    cond_strs.append(f"col('{c.column}').isin({repr(c.value)})")
                elif c.operator.value == 'contains':
                    cond_strs.append(f"col('{c.column}').contains({repr(c.value)})")
                elif c.operator.value == 'is_null':
                    cond_strs.append(f"col('{c.column}').is_null()")
                elif c.operator.value == 'not_null':
                    cond_strs.append(f"col('{c.column}').not_null()")
            
            conditions_str = ",\n        ".join(cond_strs)
            lines.append(f"    .where(\n        {conditions_str}\n    )")
        
        # Order
        if self._config.order_column:
            asc_str = "True" if self._config.order_ascending else "False"
            lines.append(f"    .order_by('{self._config.order_column}', ascending={asc_str})")
        
        # Limit
        lines.append(f"    .limit({self._config.limit_value})")
        
        # Execute
        lines.append("    .execute())")
        
        return "\n".join(lines)
    
    async def execute(self, data_provider: 'DataProvider') -> Tuple[int, pd.DataFrame]:
        """
        Ejecuta la query y retorna resultados.
        
        Args:
            data_provider: Proveedor de datos
            
        Returns:
            Tuple de (total_sin_limit, DataFrame_con_resultados)
        """
        # Validar
        errors = self.validate()
        if errors:
            raise QueryValidationError("; ".join(errors))
        
        # Obtener datos de la fuente
        raw_data = await data_provider.get_source_data(self._config.source)
        
        # Filtrar con condiciones
        filtered = []
        for row in raw_data:
            if all(cond.evaluate(row) for cond in self._config.conditions):
                filtered.append(row)
        
        total = len(filtered)
        
        # Ordenar
        if self._config.order_column:
            filtered.sort(
                key=lambda x: x.get(self._config.order_column) or 0,
                reverse=not self._config.order_ascending
            )
        
        # Limitar
        limited = filtered[:self._config.limit_value]
        
        # Crear DataFrame con columnas seleccionadas
        df_data = []
        for row in limited:
            df_data.append({col: row.get(col) for col in self._config.columns})
        
        df = pd.DataFrame(df_data)
        
        # Asegurar que todas las columnas existen
        for col_name in self._config.columns:
            if col_name not in df.columns:
                df[col_name] = None
        
        # Reordenar columnas
        df = df[self._config.columns]
        
        return total, df

