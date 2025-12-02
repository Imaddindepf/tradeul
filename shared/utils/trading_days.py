"""
Trading Days Utilities
Funciones para calcular días hábiles del mercado (excluyendo fines de semana y festivos)
IMPORTANTE: Siempre usa zona horaria de New York, no la del servidor
"""

from datetime import date, datetime, timedelta
from typing import List
from zoneinfo import ZoneInfo

# Zona horaria de NY (mercado US)
NY_TZ = ZoneInfo("America/New_York")

# Festivos 2025 (mercado cerrado)
MARKET_HOLIDAYS = {
    date(2025, 1, 1), date(2025, 1, 20), date(2025, 2, 17), date(2025, 4, 18),
    date(2025, 5, 26), date(2025, 7, 4), date(2025, 9, 1), date(2025, 11, 27), date(2025, 12, 25)
}


def get_today_ny() -> date:
    """Obtener la fecha de hoy en zona horaria de New York"""
    return datetime.now(NY_TZ).date()


def get_trading_days(lookback: int = 10, include_today: bool = True) -> List[date]:
    """
    Obtener días hábiles del mercado US
    
    IMPORTANTE: Usa zona horaria de NY, no la del servidor
    
    Args:
        lookback: Número de días hábiles a obtener
        include_today: Si True, incluye el día de hoy (NY) si es día hábil
        
    Returns:
        Lista de fechas de días hábiles (más recientes primero)
    """
    trading_days = []
    today_ny = get_today_ny()  # Fecha en NY, no del servidor
    days_back = 0 if include_today else 1
    
    while len(trading_days) < lookback:
        check_date = today_ny - timedelta(days=days_back)
        # Excluir fines de semana Y festivos
        if check_date.weekday() < 5 and check_date not in MARKET_HOLIDAYS:
            trading_days.append(check_date)
        days_back += 1
    
    return trading_days


