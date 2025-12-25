"""
Instrument Resolver - Event-Sourced Entity Resolution
======================================================
Resuelve conflictos cuando el mismo instrumento aparece en múltiples filings.

Concepto:
- Cada filing es un "evento" en la vida del instrumento
- Los eventos se ordenan cronológicamente
- Cada campo se resuelve con reglas específicas de prioridad

Ejemplo:
  F-1 (2025-12-15): exercise_price=$0.6625 (estimado)
  6-K (2025-12-19): exercise_price=$0.375 (final)
  → Resultado: $0.375 (6-K closing gana para precios)
"""

import re
from datetime import datetime
from typing import Dict, List, Optional, Any, Tuple
from dataclasses import dataclass, field
from collections import defaultdict

import structlog

logger = structlog.get_logger(__name__)


# =============================================================================
# CONFIGURACIÓN DE CONFIANZA POR TIPO DE FILING
# =============================================================================

# Mayor número = mayor confianza para precios/cantidades
FILING_CONFIDENCE_PRICING = {
    "6-K": 100,      # Closing announcement - datos finales
    "8-K": 100,      # Material event - datos finales
    "424B4": 90,     # Final prospectus pricing
    "424B5": 85,     # Prospectus supplement
    "424B3": 80,     # Prospectus supplement
    "F-1/A": 40,     # Amendment - puede tener rangos
    "S-1/A": 40,
    "F-1": 30,       # Initial - estimaciones
    "S-1": 30,
    "F-3": 20,       # Shelf registration
    "S-3": 20,
}

# Mayor número = mayor confianza para términos/condiciones
FILING_CONFIDENCE_TERMS = {
    "F-1": 100,      # Prospectus tiene todos los términos
    "S-1": 100,
    "F-1/A": 95,
    "S-1/A": 95,
    "424B4": 90,
    "424B5": 85,
    "F-3": 80,
    "S-3": 80,
    "6-K": 50,       # Closing puede no tener todos los términos
    "8-K": 50,
}


# =============================================================================
# REGLAS DE RESOLUCIÓN POR CAMPO
# =============================================================================

@dataclass
class FieldResolutionRule:
    """Regla de resolución para un campo específico"""
    strategy: str  # HIGHEST_CONFIDENCE, MOST_RECENT, FIRST_NON_NULL, MERGE_UNIQUE
    confidence_map: Dict[str, int] = field(default_factory=dict)
    prefer_non_estimated: bool = False  # Preferir valores que no sean estimados


FIELD_RULES: Dict[str, FieldResolutionRule] = {
    # Precios y cantidades: preferir closing announcements
    "exercise_price": FieldResolutionRule(
        strategy="HIGHEST_CONFIDENCE",
        confidence_map=FILING_CONFIDENCE_PRICING,
        prefer_non_estimated=True
    ),
    "total_issued": FieldResolutionRule(
        strategy="HIGHEST_CONFIDENCE", 
        confidence_map=FILING_CONFIDENCE_PRICING,
        prefer_non_estimated=True
    ),
    "outstanding": FieldResolutionRule(
        strategy="HIGHEST_CONFIDENCE",
        confidence_map=FILING_CONFIDENCE_PRICING
    ),
    
    # Términos: preferir prospectus original
    "expiration_date": FieldResolutionRule(
        strategy="FIRST_NON_NULL",
        confidence_map=FILING_CONFIDENCE_TERMS
    ),
    "exercisable_date": FieldResolutionRule(
        strategy="FIRST_NON_NULL",
        confidence_map=FILING_CONFIDENCE_TERMS
    ),
    "price_protection": FieldResolutionRule(
        strategy="FIRST_NON_NULL",
        confidence_map=FILING_CONFIDENCE_TERMS
    ),
    "pp_clause": FieldResolutionRule(
        strategy="FIRST_NON_NULL",
        confidence_map=FILING_CONFIDENCE_TERMS
    ),
    
    # Campos que se acumulan
    "known_owners": FieldResolutionRule(
        strategy="MERGE_UNIQUE",
        confidence_map=FILING_CONFIDENCE_PRICING
    ),
    "source_filings": FieldResolutionRule(
        strategy="MERGE_UNIQUE",
        confidence_map={}
    ),
    
    # Campos simples: el más reciente gana
    "series_name": FieldResolutionRule(
        strategy="MOST_RECENT",
        confidence_map=FILING_CONFIDENCE_PRICING
    ),
    "underwriter_agent": FieldResolutionRule(
        strategy="MOST_RECENT",
        confidence_map=FILING_CONFIDENCE_PRICING
    ),
    "issue_date": FieldResolutionRule(
        strategy="MOST_RECENT",
        confidence_map=FILING_CONFIDENCE_PRICING
    ),
}


# =============================================================================
# GENERACIÓN DE INSTRUMENT ID
# =============================================================================

def generate_instrument_id(
    instrument: Dict[str, Any],
    source_filing: str = ""
) -> str:
    """
    Genera un ID determinista para agrupar el mismo instrumento
    de diferentes filings.
    
    CLAVE: Agrupa por MES + TIPO únicamente.
    
    Razonamiento: En el mismo mes, para el mismo tipo (common/prefunded),
    normalmente hay UN solo offering. El 6-K closing siempre se refiere
    al mismo offering que el F-1 del mismo mes.
    
    Formato: {month_year}:{subtype}
    Ejemplo: "2025-12:common"
    """
    # Extraer mes/año del issue_date
    issue_date = instrument.get('issue_date') or ''
    month_year = issue_date[:7] if issue_date else 'unknown'
    
    # Determinar subtipo
    series_name = (instrument.get('series_name') or '').lower()
    
    if 'pre-funded' in series_name or 'prefunded' in series_name:
        subtype = 'prefunded'
    elif 'placement agent' in series_name:
        subtype = 'placement_agent'
    elif 'underwriter' in series_name:
        subtype = 'underwriter'
    else:
        subtype = 'common'
    
    return f"{month_year}:{subtype}"


def generate_instrument_id_v2(
    instrument: Dict[str, Any],
    filing_metadata: Optional[Dict] = None
) -> str:
    """
    Versión mejorada que agrupa por MES + TIPO.
    
    NO usa fileNo porque:
    - El 6-K closing no siempre tiene el fileNo
    - Los warrants del mismo mes/tipo son del mismo offering
    
    Intenta extraer mes/año de:
    1. issue_date
    2. series_name (e.g., "December 2025 Common Warrants")
    """
    # 1. Mes/Año de emisión
    issue_date = instrument.get('issue_date') or ''
    month_year = None
    
    if issue_date and len(issue_date) >= 7:
        month_year = issue_date[:7]
    else:
        # Intentar extraer del nombre
        name = instrument.get('series_name') or ''
        month_match = re.search(
            r'(January|February|March|April|May|June|July|August|September|October|November|December)\s+(\d{4})',
            name, re.I
        )
        if month_match:
            month_name, year = month_match.groups()
            month_num = {
                'january': '01', 'february': '02', 'march': '03', 'april': '04',
                'may': '05', 'june': '06', 'july': '07', 'august': '08',
                'september': '09', 'october': '10', 'november': '11', 'december': '12'
            }.get(month_name.lower(), '00')
            month_year = f"{year}-{month_num}"
    
    if not month_year:
        month_year = 'unknown'
    
    # 2. Subtipo
    name_lower = (instrument.get('series_name') or '').lower()
    if 'pre-funded' in name_lower or 'prefunded' in name_lower:
        subtype = 'prefunded'
    elif 'placement agent' in name_lower:
        subtype = 'pa'
    elif 'underwriter' in name_lower:
        subtype = 'uw'
    else:
        subtype = 'common'
    
    return f"{month_year}:{subtype}"


# =============================================================================
# EVENT (FILING) DATA STRUCTURE
# =============================================================================

@dataclass
class InstrumentEvent:
    """Representa un "evento" (filing) que aporta datos sobre un instrumento"""
    filing_type: str  # 6-K, F-1, 424B4, etc.
    filing_date: str  # YYYY-MM-DD
    accession_no: str
    data: Dict[str, Any]  # Datos extraídos de este filing
    
    @property
    def pricing_confidence(self) -> int:
        return FILING_CONFIDENCE_PRICING.get(self.filing_type, 10)
    
    @property
    def terms_confidence(self) -> int:
        return FILING_CONFIDENCE_TERMS.get(self.filing_type, 10)


# =============================================================================
# INSTRUMENT RESOLVER
# =============================================================================

class InstrumentResolver:
    """
    Resuelve conflictos entre múltiples extracciones del mismo instrumento.
    
    Uso:
        resolver = InstrumentResolver()
        
        # Agregar eventos (extracciones de diferentes filings)
        resolver.add_event("warrant_123", InstrumentEvent(...))
        resolver.add_event("warrant_123", InstrumentEvent(...))
        
        # Resolver a estado final
        final_warrant = resolver.resolve("warrant_123")
    """
    
    def __init__(self):
        self.events: Dict[str, List[InstrumentEvent]] = defaultdict(list)
    
    def add_event(self, instrument_id: str, event: InstrumentEvent):
        """Agrega un evento para un instrumento"""
        self.events[instrument_id].append(event)
    
    def add_instrument(
        self,
        instrument: Dict[str, Any],
        filing_type: str,
        filing_date: str,
        accession_no: str = ""
    ):
        """
        Método conveniente para agregar un instrumento extraído.
        Calcula automáticamente el instrument_id.
        """
        instrument_id = generate_instrument_id_v2(instrument)
        
        event = InstrumentEvent(
            filing_type=filing_type,
            filing_date=filing_date,
            accession_no=accession_no,
            data=instrument
        )
        
        self.add_event(instrument_id, event)
        
        return instrument_id
    
    def resolve(self, instrument_id: str) -> Optional[Dict[str, Any]]:
        """
        Resuelve todos los eventos de un instrumento a su estado final.
        """
        events = self.events.get(instrument_id, [])
        
        if not events:
            return None
        
        if len(events) == 1:
            # Solo un evento, retornar directamente
            result = events[0].data.copy()
            result['_resolved_from'] = 1
            result['_events'] = [e.accession_no for e in events]
            return result
        
        # Ordenar eventos por fecha (más antiguos primero)
        sorted_events = sorted(events, key=lambda e: e.filing_date)
        
        # Resolver campo por campo
        result = {}
        field_sources = {}  # Tracking de qué filing aportó cada campo
        
        # Obtener todos los campos posibles
        all_fields = set()
        for event in sorted_events:
            all_fields.update(event.data.keys())
        
        for field_name in all_fields:
            value, source = self._resolve_field(field_name, sorted_events)
            if value is not None:
                result[field_name] = value
                field_sources[field_name] = source
        
        # Agregar metadata de resolución
        result['_resolved_from'] = len(events)
        result['_events'] = [e.accession_no for e in sorted_events]
        result['_field_sources'] = field_sources
        
        logger.debug("instrument_resolved",
                    instrument_id=instrument_id,
                    events_count=len(events),
                    fields_resolved=len(result))
        
        return result
    
    def _resolve_field(
        self,
        field_name: str,
        events: List[InstrumentEvent]
    ) -> Tuple[Any, str]:
        """
        Resuelve un campo específico aplicando la regla correspondiente.
        
        Returns:
            Tuple de (valor_resuelto, source_filing)
        """
        rule = FIELD_RULES.get(field_name)
        
        if not rule:
            # Sin regla específica: usar el más reciente con valor
            for event in reversed(events):
                value = event.data.get(field_name)
                if value is not None and value != "":
                    return value, event.accession_no
            return None, ""
        
        if rule.strategy == "HIGHEST_CONFIDENCE":
            return self._resolve_highest_confidence(field_name, events, rule)
        
        elif rule.strategy == "MOST_RECENT":
            return self._resolve_most_recent(field_name, events)
        
        elif rule.strategy == "FIRST_NON_NULL":
            return self._resolve_first_non_null(field_name, events)
        
        elif rule.strategy == "MERGE_UNIQUE":
            return self._resolve_merge_unique(field_name, events)
        
        return None, ""
    
    def _resolve_highest_confidence(
        self,
        field_name: str,
        events: List[InstrumentEvent],
        rule: FieldResolutionRule
    ) -> Tuple[Any, str]:
        """
        Resuelve usando la fuente con mayor confianza.
        Si hay empate, usa el más reciente.
        """
        candidates = []
        
        for event in events:
            value = event.data.get(field_name)
            if value is None or value == "":
                continue
            
            # Detectar si es un valor estimado
            is_estimated = False
            if rule.prefer_non_estimated:
                # Valores con "assumed" o rangos son estimados
                if isinstance(value, str) and ('assumed' in value.lower() or '-' in value):
                    is_estimated = True
                # Precios del F-1 antes del pricing son estimados
                if event.filing_type in ['F-1', 'S-1', 'F-1/A', 'S-1/A']:
                    is_estimated = True
            
            confidence = rule.confidence_map.get(event.filing_type, 10)
            
            # Penalizar valores estimados
            if is_estimated:
                confidence -= 50
            
            candidates.append({
                'value': value,
                'confidence': confidence,
                'date': event.filing_date,
                'source': event.accession_no,
                'filing_type': event.filing_type,
                'is_estimated': is_estimated
            })
        
        if not candidates:
            return None, ""
        
        # Ordenar por confianza (desc), luego por fecha (desc)
        candidates.sort(key=lambda c: (c['confidence'], c['date']), reverse=True)
        
        winner = candidates[0]
        
        logger.debug("field_resolved_confidence",
                    field=field_name,
                    winner_value=winner['value'],
                    winner_source=winner['filing_type'],
                    winner_confidence=winner['confidence'],
                    candidates_count=len(candidates))
        
        return winner['value'], winner['source']
    
    def _resolve_most_recent(
        self,
        field_name: str,
        events: List[InstrumentEvent]
    ) -> Tuple[Any, str]:
        """El valor más reciente gana"""
        for event in reversed(events):  # Ya ordenados por fecha
            value = event.data.get(field_name)
            if value is not None and value != "":
                return value, event.accession_no
        return None, ""
    
    def _resolve_first_non_null(
        self,
        field_name: str,
        events: List[InstrumentEvent]
    ) -> Tuple[Any, str]:
        """El primer valor no nulo gana (útil para términos que no cambian)"""
        # Ordenar por confianza de términos
        sorted_by_terms = sorted(
            events,
            key=lambda e: FILING_CONFIDENCE_TERMS.get(e.filing_type, 10),
            reverse=True
        )
        
        for event in sorted_by_terms:
            value = event.data.get(field_name)
            if value is not None and value != "":
                return value, event.accession_no
        return None, ""
    
    def _resolve_merge_unique(
        self,
        field_name: str,
        events: List[InstrumentEvent]
    ) -> Tuple[Any, str]:
        """Combina valores únicos de todas las fuentes, devuelve STRING para Pydantic"""
        all_values = []
        sources = []
        
        for event in events:
            value = event.data.get(field_name)
            if value is None:
                continue
            
            if isinstance(value, list):
                all_values.extend(value)
            elif isinstance(value, str) and value:
                # Separar por comas si es string
                all_values.extend([v.strip() for v in value.split(',') if v.strip()])
            
            sources.append(event.accession_no)
        
        # Eliminar duplicados manteniendo orden
        unique_values = list(dict.fromkeys(all_values))
        
        if not unique_values:
            return None, ""
        
        # IMPORTANTE: Devolver como STRING separado por comas (Pydantic espera str)
        return ', '.join(unique_values), ','.join(sources)
    
    def resolve_all(self) -> List[Dict[str, Any]]:
        """Resuelve todos los instrumentos registrados"""
        results = []
        
        for instrument_id in self.events:
            resolved = self.resolve(instrument_id)
            if resolved:
                resolved['_instrument_id'] = instrument_id
                results.append(resolved)
        
        logger.info("all_instruments_resolved",
                   total_ids=len(self.events),
                   resolved=len(results))
        
        return results


# =============================================================================
# FUNCIONES DE CONVENIENCIA
# =============================================================================

def resolve_instrument_duplicates(
    instruments: List[Dict[str, Any]],
    filing_metadata: Optional[Dict] = None
) -> List[Dict[str, Any]]:
    """
    Función conveniente para resolver duplicados en una lista de instrumentos.
    
    Args:
        instruments: Lista de instrumentos (posiblemente duplicados)
        filing_metadata: Metadata opcional del filing
    
    Returns:
        Lista de instrumentos únicos con conflictos resueltos
    """
    resolver = InstrumentResolver()
    
    for inst in instruments:
        # Extraer metadata del filing del source
        source = inst.get('source_filing') or inst.get('_source') or ''
        
        # Parsear source para obtener filing_type y date
        filing_type = "unknown"
        filing_date = ""
        accession = ""
        
        if ':' in source:
            parts = source.split(':')
            if parts[0] == 'chain':
                filing_type = "F-1"  # Asumir F-1 para chains
                if len(parts) > 1:
                    accession = parts[1]
            else:
                filing_type = parts[0]
                if len(parts) > 1:
                    filing_date = parts[1]
                if len(parts) > 2:
                    accession = parts[2]
        
        # Usar issue_date si no tenemos filing_date
        if not filing_date:
            filing_date = inst.get('issue_date') or '1900-01-01'
        
        resolver.add_instrument(
            instrument=inst,
            filing_type=filing_type,
            filing_date=filing_date,
            accession_no=accession or source
        )
    
    return resolver.resolve_all()


# =============================================================================
# EJEMPLO DE USO
# =============================================================================

if __name__ == "__main__":
    # Ejemplo con los warrants de diciembre 2025
    warrants = [
        {
            "series_name": "December 2025 Common Warrants",
            "exercise_price": 0.6625,
            "total_issued": 7547170,
            "issue_date": "2025-12-17",
            "expiration_date": "2030-12-17",
            "source_filing": "chain:333-291955",
        },
        {
            "series_name": "December 2025 Common Warrants (Units)",
            "exercise_price": 0.375,
            "total_issued": 16000000,
            "issue_date": "2025-12-17",
            "expiration_date": "2030-12-17",
            "source_filing": "6-K:2025-12-19:0001104659-25-123289",
        }
    ]
    
    resolved = resolve_instrument_duplicates(warrants)
    
    print("RESULTADO:")
    for w in resolved:
        print(f"  {w.get('series_name')}: ${w.get('exercise_price')} x {w.get('total_issued'):,}")
        print(f"    Resuelto de: {w.get('_resolved_from')} eventos")
        print(f"    Field sources: {w.get('_field_sources', {})}")

