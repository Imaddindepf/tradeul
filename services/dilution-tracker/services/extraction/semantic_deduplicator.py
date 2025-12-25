"""
Semantic Deduplicator v4.1
===========================
Deduplicación mejorada con:
1. Instrument ID determinista (no depende de embeddings)
2. Fingerprint granular (mes, tipo, size_bucket, price_bucket)
3. Merge inteligente con prioridad de fuentes
4. Embeddings como fallback (no como eje central)

FLUJO:
1. Generar instrument_id determinista para cada instrumento
2. Pre-agrupar por (mes, año, tipo)
3. Dentro de grupo: usar discriminadores adicionales (size, price confidence)
4. Merge con prioridad de fuentes
5. Fallback a embeddings solo si hay ambigüedad
"""

import re
import hashlib
from typing import Dict, List, Tuple, Optional, Set
from dataclasses import dataclass, field
import structlog

logger = structlog.get_logger(__name__)


# Prioridad de fuentes (mayor número = más definitivo)
SOURCE_PRIORITY = {
    '424B4': 100,      # Pricing final
    '6-K': 90,         # Announcement de cierre
    '424B5': 80,       # Prospectus supplement
    '8-K': 70,         # Material event
    '424B3': 60,
    '424B2': 50,
    'S-1': 40,
    'F-1': 40,
    'S-3': 35,
    'F-3': 35,
    'chain': 30,       # Registration chain (puede tener datos preliminares)
    'default': 10
}


@dataclass
class DeduplicationResult:
    """Resultado de la deduplicación"""
    original_count: int
    deduplicated_count: int
    merged_clusters: List[List[Dict]]
    final_instruments: List[Dict]
    debug_info: Dict = field(default_factory=dict)


# ============================================================================
# Utilidades
# ============================================================================

def _get_source_priority(source: str) -> int:
    """Obtiene la prioridad de una fuente"""
    if not source:
        return SOURCE_PRIORITY['default']
    source_upper = source.upper()
    for key, priority in SOURCE_PRIORITY.items():
        if key.upper() in source_upper:
            return priority
    return SOURCE_PRIORITY['default']


def _extract_month_year(text: str) -> Tuple[Optional[str], Optional[int]]:
    """Extrae mes y año de un texto"""
    months = {
        'january': '01', 'february': '02', 'march': '03', 'april': '04',
        'may': '05', 'june': '06', 'july': '07', 'august': '08',
        'september': '09', 'october': '10', 'november': '11', 'december': '12',
        'jan': '01', 'feb': '02', 'mar': '03', 'apr': '04',
        'jun': '06', 'jul': '07', 'aug': '08', 'sep': '09',
        'oct': '10', 'nov': '11', 'dec': '12'
    }
    
    text_lower = text.lower() if text else ''
    month = None
    year = None
    
    for m, num in months.items():
        if m in text_lower:
            month = num
            break
    
    year_match = re.search(r'20\d{2}', text or '')
    if year_match:
        year = int(year_match.group())
    
    return month, year


def _get_warrant_type(warrant: Dict) -> str:
    """Normaliza el tipo de warrant"""
    name = (warrant.get('series_name') or '').lower()
    wtype = (warrant.get('warrant_type') or '').lower()
    
    if 'pre-funded' in name or 'pre-funded' in wtype or 'prefunded' in name:
        return 'pre-funded'
    if 'placement agent' in name or 'placement agent' in wtype:
        return 'placement-agent'
    if 'underwriter' in name or 'underwriter' in wtype:
        return 'underwriter'
    if 'common' in name or 'common' in wtype:
        return 'common'
    
    return 'other'


def _get_size_bucket(total_issued: Optional[int]) -> str:
    """Categoriza el tamaño de emisión en buckets"""
    if total_issued is None:
        return 'unknown'
    try:
        qty = int(total_issued)
        if qty < 1_000_000:
            return '0-1M'
        elif qty < 5_000_000:
            return '1-5M'
        elif qty < 20_000_000:
            return '5-20M'
        else:
            return '>20M'
    except (ValueError, TypeError):
        return 'unknown'


def _get_price_bucket(price: Optional[float], source: str = '') -> Tuple[str, str]:
    """
    Categoriza el precio en buckets.
    Returns: (bucket, confidence)
    
    confidence = 'high' si viene de 424B*, 'low' si viene de chain/otros
    """
    # Determinar confianza basada en fuente
    source_upper = (source or '').upper()
    if any(s in source_upper for s in ['424B4', '424B5', '6-K', '8-K']):
        confidence = 'high'
    else:
        confidence = 'low'
    
    if price is None:
        return ('unknown', confidence)
    
    try:
        p = float(price)
        if p < 0.01:
            return ('sub-penny', confidence)
        elif p < 1:
            return ('sub-dollar', confidence)
        elif p < 5:
            return ('1-5', confidence)
        elif p < 20:
            return ('5-20', confidence)
        elif p < 100:
            return ('20-100', confidence)
        else:
            return ('>100', confidence)
    except (ValueError, TypeError):
        return ('unknown', confidence)


# ============================================================================
# Instrument ID Determinista
# ============================================================================

# Alias para compatibilidad con debug_router
def _create_fingerprint(instrument: Dict, inst_type: str = 'warrant') -> str:
    """Alias para generate_instrument_id (compatibilidad)"""
    return generate_instrument_id(instrument, inst_type)


def generate_instrument_id(instrument: Dict, inst_type: str = 'warrant') -> str:
    """
    Genera un ID determinista para el instrumento.
    
    Formato: {type}_{year}_{month}_{subtype}_{size_bucket}[_{price_bucket si high-confidence}]
    
    Ejemplo: warrant_2025_12_common_5-20M_sub-dollar
    """
    # Extraer componentes
    name = instrument.get('series_name') or ''
    month, year = _extract_month_year(name)
    
    # Si no hay mes/año en el nombre, intentar issue_date
    if not month or not year:
        issue_date = instrument.get('issue_date') or ''
        if issue_date and len(issue_date) >= 7:
            year = int(issue_date[:4])
            month = issue_date[5:7]
    
    # Subtype
    if inst_type == 'warrant':
        subtype = _get_warrant_type(instrument)
    else:
        subtype = inst_type
    
    # Size bucket
    size_bucket = _get_size_bucket(instrument.get('total_issued'))
    
    # Price bucket (solo si alta confianza)
    price = instrument.get('exercise_price')
    source = instrument.get('_source') or ''
    price_bucket, price_confidence = _get_price_bucket(price, source)
    
    # Construir ID
    components = [
        inst_type,
        str(year) if year else 'XXXX',
        month if month else 'XX',
        subtype,
        size_bucket
    ]
    
    # Solo incluir precio si es alta confianza y no es unknown
    if price_confidence == 'high' and price_bucket != 'unknown':
        components.append(price_bucket)
    
    return '_'.join(components)


def generate_canonical_id(instrument: Dict, cik: str = '') -> str:
    """
    Genera un ID canónico único para el instrumento.
    Útil para tracking a largo plazo.
    
    Formato: {cik}_{security_type}_{issue_date}_{exercise_price_rounded}_{expiry}
    """
    parts = []
    
    # CIK del emisor
    if cik:
        parts.append(cik)
    
    # Tipo de security
    parts.append(_get_warrant_type(instrument))
    
    # Fecha de emisión
    issue_date = instrument.get('issue_date')
    if issue_date:
        parts.append(str(issue_date)[:10].replace('-', ''))
    else:
        name = instrument.get('series_name') or ''
        month, year = _extract_month_year(name)
        if year and month:
            parts.append(f"{year}{month}")
    
    # Precio redondeado (solo si viene de fuente confiable)
    price = instrument.get('exercise_price')
    source = instrument.get('_source') or ''
    _, price_confidence = _get_price_bucket(price, source)
    if price and price_confidence == 'high':
        try:
            rounded = round(float(price), 3)
            parts.append(f"p{rounded}")
        except (ValueError, TypeError):
            pass
    
    # Fecha de expiración
    expiry = instrument.get('expiration_date')
    if expiry:
        parts.append(str(expiry)[:10].replace('-', ''))
    
    # Hash para unicidad
    raw_id = '_'.join(str(p) for p in parts)
    hash_suffix = hashlib.md5(raw_id.encode()).hexdigest()[:6]
    
    return f"{raw_id}_{hash_suffix}"


# ============================================================================
# Deduplicación Principal
# ============================================================================

class SemanticDeduplicator:
    """
    Deduplicador semántico v4.1
    
    Usa IDs deterministas como eje principal, embeddings como fallback.
    """
    
    def __init__(self, gemini_client=None, similarity_threshold: float = 0.85):
        """
        Args:
            gemini_client: Cliente de Gemini para embeddings (opcional)
            similarity_threshold: Umbral de similitud para clustering (default 0.85)
        """
        self.gemini = gemini_client
        self.similarity_threshold = similarity_threshold
        self.last_merged_clusters: List[List[Dict]] = []
        self.debug_info: Dict = {}
    
    def deduplicate(self, instruments: List[Dict], 
                    inst_type: str = 'warrant',
                    threshold: float = 0.85) -> DeduplicationResult:
        """
        Deduplica instrumentos usando IDs deterministas.
        
        Args:
            instruments: Lista de instrumentos a deduplicar
            inst_type: Tipo de instrumento
            threshold: Umbral de similitud para embeddings (fallback)
        
        Returns:
            DeduplicationResult
        """
        if not instruments:
            return DeduplicationResult(
                original_count=0,
                deduplicated_count=0,
                merged_clusters=[],
                final_instruments=[]
            )
        
        logger.info("deduplication_started",
                   count=len(instruments),
                   inst_type=inst_type)
        
        # Paso 1: Generar IDs para todos los instrumentos
        for inst in instruments:
            inst['_dedup_id'] = generate_instrument_id(inst, inst_type)
        
        # Paso 2: Agrupar por dedup_id
        groups: Dict[str, List[Dict]] = {}
        for inst in instruments:
            dedup_id = inst['_dedup_id']
            if dedup_id not in groups:
                groups[dedup_id] = []
            groups[dedup_id].append(inst)
        
        self.debug_info['groups_by_id'] = {k: len(v) for k, v in groups.items()}
        
        # Paso 3: Merge dentro de cada grupo
        final_instruments = []
        merged_clusters = []
        
        for dedup_id, group in groups.items():
            if len(group) == 1:
                # Solo uno, no hay que mergear
                final_instruments.append(group[0])
                merged_clusters.append(group)
            else:
                # Mergear grupo
                merged = self._merge_group(group, inst_type)
                final_instruments.append(merged)
                merged_clusters.append(group)
        
        self.last_merged_clusters = merged_clusters
        
        # Paso 4: Verificar si hay grupos que deberían mergearse pero tienen IDs diferentes
        # (Fallback para casos ambiguos - deshabilitado por ahora para simplicidad)
        
        result = DeduplicationResult(
            original_count=len(instruments),
            deduplicated_count=len(final_instruments),
            merged_clusters=merged_clusters,
            final_instruments=final_instruments,
            debug_info=self.debug_info
        )
        
        logger.info("deduplication_complete",
                   original=result.original_count,
                   deduplicated=result.deduplicated_count,
                   groups=len(groups))
        
        return result
    
    def _merge_group(self, group: List[Dict], inst_type: str) -> Dict:
        """
        Mergea un grupo de instrumentos duplicados.
        Prioriza fuentes más definitivas.
        """
        if len(group) == 1:
            return group[0]
        
        # Ordenar por prioridad de fuente (mayor primero)
        sorted_group = sorted(
            group,
            key=lambda x: _get_source_priority(x.get('_source', '')),
            reverse=True
        )
        
        # Base: el de mayor prioridad
        merged = dict(sorted_group[0])
        
        # Completar campos faltantes desde otras fuentes
        for inst in sorted_group[1:]:
            for key, value in inst.items():
                if key.startswith('_'):
                    continue
                
                # Solo completar si el campo está vacío
                if merged.get(key) in [None, '', [], {}]:
                    if value not in [None, '', [], {}]:
                        merged[key] = value
        
        # Agregar metadata de merge
        merged['_sources'] = list(set(
            inst.get('_source', 'unknown') 
            for inst in group 
            if inst.get('_source')
        ))
        merged['_merged_from'] = len(group)
        merged['_dedup_ids'] = list(set(
            inst.get('_dedup_id', '') 
            for inst in group
        ))
        
        return merged
    
    # Método de compatibilidad con la API anterior
    async def deduplicate_warrants(self, warrants: List[Dict], threshold: float = 0.85) -> List[Dict]:
        """
        API de compatibilidad con versión anterior.
        """
        result = self.deduplicate(warrants, 'warrant', threshold)
        return result.final_instruments


# ============================================================================
# Funciones de utilidad para dedup sin instanciar clase
# ============================================================================

def deduplicate_instruments(instruments: List[Dict], 
                           inst_type: str = 'warrant') -> List[Dict]:
    """
    Función simple para deduplicar sin instanciar la clase.
    """
    deduplicator = SemanticDeduplicator()
    result = deduplicator.deduplicate(instruments, inst_type)
    return result.final_instruments


def should_merge(inst1: Dict, inst2: Dict, inst_type: str = 'warrant') -> Tuple[bool, str]:
    """
    Determina si dos instrumentos deberían mergearse.
    
    Returns:
        (should_merge: bool, reason: str)
    """
    id1 = generate_instrument_id(inst1, inst_type)
    id2 = generate_instrument_id(inst2, inst_type)
    
    if id1 == id2:
        return (True, f"Same dedup_id: {id1}")
    
    # Verificar si difieren solo en campos de baja confianza
    # (ej: mismo mes/año/tipo pero diferente size porque una fuente no tenía el dato)
    parts1 = id1.split('_')
    parts2 = id2.split('_')
    
    # Si tipo, año y mes coinciden, posible duplicado
    if len(parts1) >= 4 and len(parts2) >= 4:
        if parts1[:4] == parts2[:4]:
            # Mismo tipo, año, mes, subtype
            # Verificar si size es la única diferencia
            if parts1[4] == 'unknown' or parts2[4] == 'unknown':
                return (True, f"Same period/type, one has unknown size")
    
    return (False, "Different instruments")
