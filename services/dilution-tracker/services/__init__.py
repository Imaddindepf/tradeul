"""
Services Package - Dilution Tracker

Estructura:
- core/       - Servicio principal de dilución
- grok/       - Integración con Grok AI
- sec/        - Integración con SEC EDGAR
- data/       - Fuentes de datos externos
- analysis/   - Análisis y procesamiento
- market/     - Cálculos de mercado
- extraction/ - Extracción de contenido
- cache/      - Caché y persistencia
- external/   - APIs externas

USO:
    from services.core.sec_dilution_service import SECDilutionService
    from services.grok.grok_pool import GrokPool
    from services.data.enhanced_data_fetcher import EnhancedDataFetcher
"""

# No importar nada aquí para evitar dependencias circulares
# Usar imports directos desde los módulos específicos
