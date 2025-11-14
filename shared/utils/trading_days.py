"""
Trading Days Utilities
Funciones para calcular días hábiles del mercado (excluyendo fines de semana y festivos)
"""

from datetime import date, timedelta
from typing import List

# Festivos 2025
MARKET_HOLIDAYS = {
    date(2025, 1, 1), date(2025, 1, 20), date(2025, 2, 17), date(2025, 4, 18),
    date(2025, 5, 26), date(2025, 7, 4), date(2025, 9, 1), date(2025, 11, 27), date(2025, 12, 25)
}


def get_trading_days(lookback: int = 10) -> List[date]:
    """
    Obtener días hábiles siguiendo lógica PineScript
    
    Args:
        lookback: Número de días hábiles a obtener
        
    Returns:
        Lista de fechas de días hábiles (más recientes primero)
    """
    trading_days = []
    today = date.today()
    days_back = 1
    
    while len(trading_days) < lookback:
        check_date = today - timedelta(days=days_back)
        # Excluir fines de semana Y festivos
        if check_date.weekday() < 5 and check_date not in MARKET_HOLIDAYS:
            trading_days.append(check_date)
        days_back += 1
    
    return trading_days


