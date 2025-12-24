"""
Services Package - Dilution Tracker
====================================

Estructura:
- core/       - Servicio principal de dilución (SECDilutionService)
- extraction/ - v4 ContextualDilutionExtractor (Gemini long context)
- sec/        - Integración con SEC EDGAR
- data/       - Fuentes de datos externos
- analysis/   - Análisis y deduplicación
- market/     - Cálculos de mercado
- cache/      - Caché Redis y persistencia
- external/   - APIs externas

USO:
    from services.core.sec_dilution_service import SECDilutionService
    from services.extraction.contextual_extractor import get_contextual_extractor
    from services.data.enhanced_data_fetcher import EnhancedDataFetcher
"""

# No importar nada aquí para evitar dependencias circulares
# Usar imports directos desde los módulos específicos
