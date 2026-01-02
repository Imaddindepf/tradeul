"""
Dynamic Indicator Calculator

Generates SQL for calculating indicators with custom parameters on-the-fly.
Used when users request non-standard periods (e.g., SMA(10) instead of SMA(20)).
"""

from typing import Dict, Any, List, Optional, Tuple
import structlog

logger = structlog.get_logger(__name__)

# Standard pre-computed periods (already in screener_data)
PRECOMPUTED_PERIODS = {
    'sma': [20, 50, 200],
    'ema': [20],
    'rsi': [14],
    'atr': [14, 10],
    'adx': [14],
    'bb': [20],  # Bollinger Bands
    'keltner': [20],
}

# Simple indicators that can be calculated dynamically with any period
# Complex indicators (RSI, ADX, MACD) require pre-computation
SIMPLE_DYNAMIC_INDICATORS = {'sma', 'ema', 'atr', 'vol_avg'}

# Indicator SQL templates for dynamic calculation (only simple ones)
INDICATOR_TEMPLATES = {
    'sma': """
        AVG(close) OVER (
            PARTITION BY symbol 
            ORDER BY date 
            ROWS {period_minus_1} PRECEDING
        )
    """,
    'ema': """
        AVG(close) OVER (
            PARTITION BY symbol 
            ORDER BY date 
            ROWS {period_minus_1} PRECEDING
        )
    """,  # Approximation using SMA (true EMA requires recursion)
    'atr': """
        AVG(high - low) OVER (
            PARTITION BY symbol 
            ORDER BY date 
            ROWS {period_minus_1} PRECEDING
        )
    """,
    'vol_avg': """
        AVG(volume) OVER (
            PARTITION BY symbol 
            ORDER BY date 
            ROWS {period_minus_1} PRECEDING
        )
    """,
}


def is_precomputed(field: str, params: Optional[Dict[str, Any]]) -> bool:
    """
    Check if an indicator with given params is already pre-computed.
    Returns True if we can use the fast screener_data table.
    
    Complex indicators (RSI, ADX, MACD) always use precomputed values
    because dynamic calculation is too complex/slow.
    """
    if not params:
        return True  # No custom params = use precomputed
    
    period = params.get('period')
    if not period:
        return True
    
    # Map field to indicator type
    indicator_type = None
    if field.startswith('sma'):
        indicator_type = 'sma'
    elif field.startswith('ema'):
        indicator_type = 'ema'
    elif field.startswith('rsi'):
        indicator_type = 'rsi'
    elif field.startswith('atr'):
        indicator_type = 'atr'
    elif field.startswith('adx') or field.startswith('plus_di') or field.startswith('minus_di'):
        indicator_type = 'adx'
    elif 'volume' in field.lower() or field == 'avg_volume_20':
        indicator_type = 'vol_avg'
    
    if not indicator_type:
        return True  # Unknown indicator, assume precomputed
    
    # Complex indicators always use precomputed (dynamic is too slow/complex)
    if indicator_type not in SIMPLE_DYNAMIC_INDICATORS:
        return True
    
    # Check if this period is already precomputed
    precomputed = PRECOMPUTED_PERIODS.get(indicator_type, [])
    return period in precomputed


def extract_custom_indicators(filters: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """
    Extract filters that require dynamic calculation.
    Returns list of custom indicator definitions.
    """
    custom = []
    for f in filters:
        params = f.get('params')
        if params and not is_precomputed(f.get('field', ''), params):
            custom.append({
                'field': f.get('field'),
                'params': params,
                'alias': _generate_alias(f.get('field'), params),
            })
    return custom


def _generate_alias(field: str, params: Dict[str, Any]) -> str:
    """Generate SQL alias for custom indicator"""
    period = params.get('period', 0)
    base = field.split('_')[0] if '_' in field else field
    return f"custom_{base}_{period}"


def generate_dynamic_cte(custom_indicators: List[Dict[str, Any]]) -> Tuple[str, Dict[str, str]]:
    """
    Generate CTE SQL for calculating custom indicators.
    
    Returns:
        Tuple of (CTE SQL string, mapping of original field to alias)
    """
    if not custom_indicators:
        return "", {}
    
    alias_map = {}
    select_parts = []
    
    for ind in custom_indicators:
        field = ind['field']
        params = ind['params']
        alias = ind['alias']
        period = params.get('period', 14)
        period_minus_1 = period - 1
        
        # Determine indicator type and get template
        template = None
        if 'sma' in field.lower():
            template = INDICATOR_TEMPLATES.get('sma')
        elif 'ema' in field.lower():
            template = INDICATOR_TEMPLATES.get('ema')
        elif 'atr' in field.lower():
            template = INDICATOR_TEMPLATES.get('atr')
        elif 'vol' in field.lower() or 'volume' in field.lower():
            template = INDICATOR_TEMPLATES.get('vol_avg')
        
        if not template:
            logger.warning("unsupported_dynamic_indicator", field=field)
            continue
        
        sql_expr = template.format(period_minus_1=period_minus_1)
        select_parts.append(f"({sql_expr}) as {alias}")
        alias_map[field] = alias
    
    if not select_parts:
        return "", {}
    
    # Build CTE that calculates custom indicators from daily_prices
    cte_sql = f"""
    WITH custom_indicators AS (
        SELECT DISTINCT ON (symbol)
            symbol,
            date,
            {', '.join(select_parts)}
        FROM daily_prices
        WHERE date >= CURRENT_DATE - INTERVAL '7 days'
        WINDOW w AS (PARTITION BY symbol ORDER BY date)
        ORDER BY symbol, date DESC
    )
    """
    
    return cte_sql, alias_map


def build_hybrid_query(
    base_where: str,
    custom_indicators: List[Dict[str, Any]],
    sort_by: str,
    sort_order: str,
    limit: int,
    symbols_filter: str = ""
) -> str:
    """
    Build a hybrid query that joins precomputed data with dynamically calculated indicators.
    """
    if not custom_indicators:
        # No custom indicators, use simple query
        return f"""
        SELECT *
        FROM screener_data
        WHERE {base_where}
          {symbols_filter}
        ORDER BY {sort_by} {sort_order.upper()} NULLS LAST
        LIMIT {limit}
        """
    
    cte_sql, alias_map = generate_dynamic_cte(custom_indicators)
    
    # Replace field references in WHERE clause with aliases
    modified_where = base_where
    for original, alias in alias_map.items():
        # Replace field name with alias from CTE
        modified_where = modified_where.replace(f"({original}", f"(c.{alias}")
    
    query = f"""
    {cte_sql}
    SELECT s.*, {', '.join(f'c.{ind["alias"]}' for ind in custom_indicators)}
    FROM screener_data s
    JOIN custom_indicators c ON s.symbol = c.symbol
    WHERE {modified_where}
      {symbols_filter}
    ORDER BY {sort_by} {sort_order.upper()} NULLS LAST
    LIMIT {limit}
    """
    
    return query

