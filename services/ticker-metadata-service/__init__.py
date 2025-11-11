"""
Ticker Metadata Service

Servicio especializado en gestión de metadatos de compañías:
- Company profiles (nombre, sector, industria, exchange)
- Market statistics (market cap, float, shares outstanding)
- Trading statistics (average volume, beta, etc)

Responsabilidades:
- Enriquecer metadata desde fuentes externas (Polygon, FMP)
- Mantener cache en Redis
- Persistir en TimescaleDB
- Exponer API REST para otros servicios
"""

__version__ = "1.0.0"

