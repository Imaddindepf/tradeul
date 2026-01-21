"""
Section Extractor v4.1
======================
Extrae secciones específicas de SEC filings en vez de recortar arbitrariamente.

SECCIONES OBJETIVO (en orden de prioridad para dilución):
1. DESCRIPTION OF SECURITIES - Warrants, términos
2. THE OFFERING - Pricing, cantidades
3. PLAN OF DISTRIBUTION / UNDERWRITING - Placement agents, términos
4. DILUTION - Impacto en shareholders
5. CAPITALIZATION - Shares outstanding, estructura
6. SELLING STOCKHOLDERS - Holders existentes vendiendo
7. RECENT DEVELOPMENTS - Cierres, ejercicios, eventos
8. USE OF PROCEEDS - Para qué se usa el dinero
9. RISK FACTORS (parcial) - A veces tiene info de warrants
"""

import re
from typing import Dict, List, Tuple, Optional
from dataclasses import dataclass, field
import structlog

logger = structlog.get_logger(__name__)


@dataclass
class ExtractedSection:
    """Una sección extraída del filing"""
    name: str
    content: str
    start_offset: int
    end_offset: int
    confidence: float  # 0.0-1.0, qué tan seguro estamos de que es la sección correcta


@dataclass 
class SectionExtractionResult:
    """Resultado de la extracción de secciones"""
    sections: Dict[str, ExtractedSection]
    total_chars: int
    extracted_chars: int
    coverage_pct: float
    warnings: List[str] = field(default_factory=list)


# Patrones para identificar secciones (case-insensitive)
SECTION_PATTERNS = {
    'description_of_securities': [
        r'DESCRIPTION\s+OF\s+(?:THE\s+)?SECURITIES',
        r'DESCRIPTION\s+OF\s+(?:OUR\s+)?(?:COMMON\s+STOCK|WARRANTS|CAPITAL\s+STOCK)',
        r'SECURITIES\s+BEING\s+OFFERED',
        r'THE\s+SECURITIES\s+WE\s+ARE\s+OFFERING',
    ],
    'the_offering': [
        r'THE\s+OFFERING',
        r'SUMMARY\s+OF\s+THE\s+OFFERING',
        r'TERMS\s+OF\s+THE\s+OFFERING',
        r'OFFERING\s+SUMMARY',
    ],
    'plan_of_distribution': [
        r'PLAN\s+OF\s+DISTRIBUTION',
        r'UNDERWRITING',
        r'UNDERWRITERS?',
    ],
    'dilution': [
        r'DILUTION',
        r'DILUTION\s+AND\s+COMPARATIVE\s+DATA',
    ],
    'capitalization': [
        r'CAPITALIZATION',
        r'CAPITAL\s+STRUCTURE',
    ],
    'selling_stockholders': [
        r'SELLING\s+(?:STOCK|SHARE)HOLDERS?',
        r'SELLING\s+SECURITYHOLDERS?',
    ],
    'recent_developments': [
        r'RECENT\s+DEVELOPMENTS?',
        r'SUBSEQUENT\s+EVENTS?',
        r'RECENT\s+EVENTS?',
    ],
    'use_of_proceeds': [
        r'USE\s+OF\s+PROCEEDS',
    ],
    'risk_factors': [
        r'RISK\s+FACTORS?',
    ],
    'prospectus_summary': [
        r'PROSPECTUS\s+SUMMARY',
        r'SUMMARY\s+OF\s+(?:THE\s+)?PROSPECTUS',
    ],
}

# Tamaño máximo por sección (chars)
MAX_SECTION_SIZE = {
    'description_of_securities': 50000,  # Puede ser larga, tiene términos de warrants
    'the_offering': 30000,
    'plan_of_distribution': 40000,
    'dilution': 20000,
    'capitalization': 15000,
    'selling_stockholders': 30000,
    'recent_developments': 20000,
    'use_of_proceeds': 10000,
    'risk_factors': 15000,  # Solo tomamos parte
    'prospectus_summary': 25000,
}

# Patrones que indican fin de sección (siguiente sección)
SECTION_END_PATTERNS = [
    r'\n\s*(?:PART\s+)?(?:I{1,3}|IV|V|VI|VII|VIII|IX|X)\s*[\.\-]?\s*\n',  # PART I, II, etc.
    r'\n\s*(?:ITEM\s+\d+)',  # ITEM 1, ITEM 2, etc.
]


def _compile_pattern(patterns: List[str]) -> re.Pattern:
    """Compila múltiples patrones en uno solo"""
    combined = '|'.join(f'({p})' for p in patterns)
    return re.compile(combined, re.IGNORECASE | re.MULTILINE)


def _find_section_boundaries(text: str, section_name: str, patterns: List[str]) -> Optional[Tuple[int, int, float]]:
    """
    Encuentra los límites de una sección.
    Returns: (start, end, confidence) o None
    """
    compiled = _compile_pattern(patterns)
    
    # Buscar inicio de sección
    match = compiled.search(text)
    if not match:
        return None
    
    start = match.start()
    confidence = 0.9 if match.group().isupper() else 0.7  # Mayor confianza si está en mayúsculas
    
    # Buscar fin de sección (siguiente sección o fin de texto)
    # Buscamos cualquier otro heading de sección después del inicio
    end = len(text)
    
    # Crear patrón combinado de todas las secciones (excepto la actual)
    all_other_patterns = []
    for name, pats in SECTION_PATTERNS.items():
        if name != section_name:
            all_other_patterns.extend(pats)
    
    if all_other_patterns:
        other_sections = _compile_pattern(all_other_patterns)
        next_section = other_sections.search(text, pos=start + len(match.group()) + 100)  # +100 para saltar título
        if next_section:
            end = next_section.start()
    
    # También buscar patrones de fin genéricos
    for end_pattern in SECTION_END_PATTERNS:
        end_match = re.search(end_pattern, text[start + 100:], re.IGNORECASE)
        if end_match:
            potential_end = start + 100 + end_match.start()
            if potential_end < end:
                end = potential_end
    
    # Aplicar límite máximo
    max_size = MAX_SECTION_SIZE.get(section_name, 30000)
    if end - start > max_size:
        end = start + max_size
        confidence *= 0.8  # Reducir confianza si truncamos
    
    return (start, end, confidence)


def extract_sections(text: str, target_sections: Optional[List[str]] = None) -> SectionExtractionResult:
    """
    Extrae secciones específicas de un filing.
    
    Args:
        text: Contenido del filing (HTML limpio o texto)
        target_sections: Lista de secciones a extraer. Si None, extrae todas las relevantes.
    
    Returns:
        SectionExtractionResult con las secciones encontradas
    """
    if target_sections is None:
        # Secciones más importantes para dilución
        target_sections = [
            'description_of_securities',
            'the_offering', 
            'plan_of_distribution',
            'dilution',
            'capitalization',
            'selling_stockholders',
            'recent_developments',
            'prospectus_summary',
        ]
    
    sections: Dict[str, ExtractedSection] = {}
    warnings: List[str] = []
    total_extracted = 0
    
    for section_name in target_sections:
        patterns = SECTION_PATTERNS.get(section_name)
        if not patterns:
            warnings.append(f"Unknown section: {section_name}")
            continue
        
        result = _find_section_boundaries(text, section_name, patterns)
        
        if result:
            start, end, confidence = result
            content = text[start:end]
            
            sections[section_name] = ExtractedSection(
                name=section_name,
                content=content,
                start_offset=start,
                end_offset=end,
                confidence=confidence
            )
            total_extracted += len(content)
            
            logger.debug("section_extracted",
                        section=section_name,
                        chars=len(content),
                        confidence=confidence)
        else:
            warnings.append(f"Section not found: {section_name}")
    
    coverage = total_extracted / len(text) if text else 0
    
    return SectionExtractionResult(
        sections=sections,
        total_chars=len(text),
        extracted_chars=total_extracted,
        coverage_pct=coverage * 100,
        warnings=warnings
    )


def extract_sections_for_dilution(text: str) -> str:
    """
    Extrae y concatena las secciones relevantes para análisis de dilución.
    Retorna texto optimizado para enviar a Gemini.
    """
    result = extract_sections(text)
    
    # Orden de prioridad para concatenación
    priority_order = [
        'prospectus_summary',      # Resumen general
        'the_offering',            # Términos del offering
        'description_of_securities',  # Detalle de warrants
        'plan_of_distribution',    # Underwriters
        'dilution',                # Impacto
        'capitalization',          # Estructura
        'selling_stockholders',    # Sellers
        'recent_developments',     # Eventos recientes
    ]
    
    output_parts = []
    
    for section_name in priority_order:
        if section_name in result.sections:
            section = result.sections[section_name]
            # Agregar header para que Gemini sepa qué sección está leyendo
            header = section_name.upper().replace('_', ' ')
            output_parts.append(f"\n\n=== {header} ===\n\n{section.content}")
    
    # Si no encontramos ninguna sección, devolver texto truncado como fallback
    if not output_parts:
        logger.warning("no_sections_found_fallback_to_truncate", 
                      text_len=len(text))
        return text[:80000]  # Fallback más grande
    
    combined = ''.join(output_parts)
    
    logger.info("sections_extracted_for_dilution",
               sections_found=len(result.sections),
               total_chars=len(combined),
               coverage_pct=f"{result.coverage_pct:.1f}%",
               warnings=result.warnings)
    
    return combined


# ============================================================================
# Extracción de tablas preservando estructura
# ============================================================================

def html_table_to_text(html: str) -> str:
    """
    Convierte tablas HTML a texto preservando estructura con separadores.
    
    Ejemplo input:
        <table><tr><td>Price</td><td>$1.50</td></tr></table>
    
    Ejemplo output:
        | Price | $1.50 |
    """
    # Primero, identificar y procesar tablas
    table_pattern = re.compile(r'<table[^>]*>(.*?)</table>', re.IGNORECASE | re.DOTALL)
    
    def process_table(match):
        table_html = match.group(1)
        rows = []
        
        # Extraer filas
        row_pattern = re.compile(r'<tr[^>]*>(.*?)</tr>', re.IGNORECASE | re.DOTALL)
        for row_match in row_pattern.finditer(table_html):
            row_html = row_match.group(1)
            cells = []
            
            # Extraer celdas (th o td)
            cell_pattern = re.compile(r'<(?:td|th)[^>]*>(.*?)</(?:td|th)>', re.IGNORECASE | re.DOTALL)
            for cell_match in cell_pattern.finditer(row_html):
                cell_content = cell_match.group(1)
                # Limpiar HTML interno
                cell_content = re.sub(r'<[^>]+>', ' ', cell_content)
                cell_content = re.sub(r'\s+', ' ', cell_content).strip()
                cells.append(cell_content)
            
            if cells:
                rows.append('| ' + ' | '.join(cells) + ' |')
        
        if rows:
            # Agregar separador después del header (primera fila)
            if len(rows) > 1:
                header_sep = '|' + '|'.join(['---'] * len(rows[0].split('|')[1:-1])) + '|'
                rows.insert(1, header_sep)
            return '\n' + '\n'.join(rows) + '\n'
        return ''
    
    # Procesar todas las tablas
    result = table_pattern.sub(process_table, html)
    
    return result


def clean_html_for_llm(html: str, aggressive: bool = True) -> str:
    """
    Limpieza AGRESIVA de HTML para minimizar tokens enviados a Gemini.
    
    Reducción típica: ~51% del tamaño original.
    
    Elementos removidos:
    - CSS inline (style="...") - ¡47% del ahorro!
    - CSS blocks (<style>...</style>)
    - Scripts (<script>...</script>)
    - Comentarios HTML (<!-- -->)
    - Tags iXBRL (ix:*) - preserva contenido
    - Imágenes (<img>, especialmente base64)
    - SVG inline
    - Atributos class= (referencias CSS)
    - Whitespace excesivo
    
    Elementos PRESERVADOS:
    - Texto de contenido
    - Estructura de tablas (convertidas a markdown)
    - Saltos de línea semánticos
    - Números y valores financieros
    
    Args:
        html: HTML original del SEC filing
        aggressive: Si True, aplica limpieza máxima (recomendado)
    
    Returns:
        Texto limpio optimizado para LLM
    """
    text = html
    
    # =========================================================================
    # FASE 1: REMOVER ELEMENTOS QUE NO APORTAN INFORMACIÓN (orden importante)
    # =========================================================================
    
    # 1.1 Scripts (pueden contener mucho código)
    text = re.sub(r'<script[^>]*>.*?</script>', '', text, flags=re.DOTALL | re.IGNORECASE)
    
    # 1.2 CSS blocks (<style>...</style>)
    text = re.sub(r'<style[^>]*>.*?</style>', '', text, flags=re.DOTALL | re.IGNORECASE)
    
    # 1.3 Head section (meta, links, etc.)
    text = re.sub(r'<head[^>]*>.*?</head>', '', text, flags=re.DOTALL | re.IGNORECASE)
    
    # 1.4 Comentarios HTML (<!-- ... -->) - pueden ser largos
    text = re.sub(r'<!--.*?-->', '', text, flags=re.DOTALL)
    
    # 1.5 SVG inline (pueden ser muy grandes)
    text = re.sub(r'<svg[^>]*>.*?</svg>', '', text, flags=re.DOTALL | re.IGNORECASE)
    
    # 1.6 Imágenes (especialmente base64 que pueden ser 100KB+)
    text = re.sub(r'<img[^>]*>', '', text, flags=re.IGNORECASE)
    
    # 1.7 Noscript sections
    text = re.sub(r'<noscript[^>]*>.*?</noscript>', '', text, flags=re.DOTALL | re.IGNORECASE)
    
    if aggressive:
        # =====================================================================
        # FASE 2: REMOVER ATRIBUTOS DE PRESENTACIÓN (¡47% del ahorro!)
        # =====================================================================
        
        # 2.1 CSS inline (style="...") - EL MAYOR AHORRO
        text = re.sub(r'\s+style="[^"]*"', '', text, flags=re.IGNORECASE)
        text = re.sub(r"\s+style='[^']*'", '', text, flags=re.IGNORECASE)
        
        # 2.2 Atributos class= (referencias a CSS ya removido)
        text = re.sub(r'\s+class="[^"]*"', '', text, flags=re.IGNORECASE)
        text = re.sub(r"\s+class='[^']*'", '', text, flags=re.IGNORECASE)
        
        # 2.3 Atributos id= (no necesarios para extracción)
        text = re.sub(r'\s+id="[^"]*"', '', text, flags=re.IGNORECASE)
        
        # 2.4 Atributos data-* (metadata de frontend)
        text = re.sub(r'\s+data-[a-z-]+="[^"]*"', '', text, flags=re.IGNORECASE)
        
        # 2.5 Atributos de tamaño/presentación
        text = re.sub(r'\s+(?:width|height|align|valign|bgcolor|border|cellpadding|cellspacing)="[^"]*"', '', text, flags=re.IGNORECASE)
    
    # =========================================================================
    # FASE 3: LIMPIAR TAGS iXBRL (preservando contenido numérico)
    # =========================================================================
    
    # Tags iXBRL como <ix:nonFraction ...>VALUE</ix:nonFraction> -> VALUE
    text = re.sub(r'<ix:[^>]+>', '', text, flags=re.IGNORECASE)
    text = re.sub(r'</ix:[^>]+>', '', text, flags=re.IGNORECASE)
    
    # =========================================================================
    # FASE 4: CONVERTIR ESTRUCTURA HTML A TEXTO MARKDOWN-LIKE
    # =========================================================================
    
    # 4.1 Convertir tablas a formato texto tabular
    text = html_table_to_text(text)
    
    # 4.2 Convertir elementos de bloque a saltos de línea
    text = re.sub(r'<br\s*/?>', '\n', text, flags=re.IGNORECASE)
    text = re.sub(r'</p>', '\n\n', text, flags=re.IGNORECASE)
    text = re.sub(r'</div>', '\n', text, flags=re.IGNORECASE)
    text = re.sub(r'</tr>', '\n', text, flags=re.IGNORECASE)
    text = re.sub(r'<li[^>]*>', '\n• ', text, flags=re.IGNORECASE)
    text = re.sub(r'</li>', '', text, flags=re.IGNORECASE)
    
    # 4.3 Convertir headers a texto con marcador
    for i in range(1, 7):
        text = re.sub(rf'<h{i}[^>]*>(.*?)</h{i}>', rf'\n\n## \1\n\n', text, flags=re.IGNORECASE | re.DOTALL)
    
    # 4.4 Preservar strong/bold/emphasis
    text = re.sub(r'<(?:strong|b)[^>]*>(.*?)</(?:strong|b)>', r'**\1**', text, flags=re.IGNORECASE | re.DOTALL)
    text = re.sub(r'<(?:em|i)[^>]*>(.*?)</(?:em|i)>', r'*\1*', text, flags=re.IGNORECASE | re.DOTALL)
    
    # 4.5 Remover tags HTML restantes
    text = re.sub(r'<[^>]+>', ' ', text)
    
    # =========================================================================
    # FASE 5: DECODIFICAR ENTIDADES HTML
    # =========================================================================
    
    # Entidades comunes
    html_entities = {
        '&nbsp;': ' ',
        '&amp;': '&',
        '&lt;': '<',
        '&gt;': '>',
        '&quot;': '"',
        '&apos;': "'",
        '&#8217;': "'",
        '&#8216;': "'",
        '&#8220;': '"',
        '&#8221;': '"',
        '&#8211;': '–',
        '&#8212;': '—',
        '&mdash;': '—',
        '&ndash;': '–',
        '&rsquo;': "'",
        '&lsquo;': "'",
        '&rdquo;': '"',
        '&ldquo;': '"',
        '&bull;': '•',
        '&copy;': '©',
        '&reg;': '®',
        '&trade;': '™',
        '&deg;': '°',
        '&plusmn;': '±',
        '&times;': '×',
        '&divide;': '÷',
        '&cent;': '¢',
        '&pound;': '£',
        '&euro;': '€',
        '&yen;': '¥',
    }
    
    for entity, char in html_entities.items():
        text = text.replace(entity, char)
    
    # Entidades numéricas restantes (&#NNN; o &#xNNN;)
    text = re.sub(r'&#x([0-9a-fA-F]+);', lambda m: chr(int(m.group(1), 16)), text)
    text = re.sub(r'&#(\d+);', lambda m: chr(int(m.group(1))), text)
    
    # =========================================================================
    # FASE 6: NORMALIZAR WHITESPACE
    # =========================================================================
    
    # 6.1 Colapsar espacios/tabs múltiples a uno solo
    text = re.sub(r'[ \t]+', ' ', text)
    
    # 6.2 Colapsar múltiples newlines a máximo 2
    text = re.sub(r'\n\s*\n\s*\n+', '\n\n', text)
    
    # 6.3 Remover espacios al inicio de líneas
    text = re.sub(r'^\s+', '', text, flags=re.MULTILINE)
    
    # 6.4 Remover espacios al final de líneas
    text = re.sub(r'\s+$', '', text, flags=re.MULTILINE)
    
    return text.strip()


def clean_html_preserve_structure(html: str) -> str:
    """
    Alias para compatibilidad hacia atrás.
    Usa clean_html_for_llm con configuración agresiva.
    """
    return clean_html_for_llm(html, aggressive=True)


# ============================================================================
# Extracción de evidencias (snippets) para provenance
# ============================================================================

def extract_evidence_snippet(text: str, value: str, context_chars: int = 100) -> Optional[Dict]:
    """
    Busca un valor en el texto y extrae snippet de evidencia alrededor.
    
    Args:
        text: Texto completo
        value: Valor a buscar (ej: "$1.50", "16,000,000")
        context_chars: Caracteres de contexto a cada lado
    
    Returns:
        Dict con snippet, offset_start, offset_end o None si no encontrado
    """
    if not value:
        return None
    
    # Escapar caracteres especiales de regex
    escaped_value = re.escape(str(value))
    
    # Buscar el valor
    match = re.search(escaped_value, text, re.IGNORECASE)
    if not match:
        # Intentar sin formato (ej: buscar "16000000" si no encuentra "16,000,000")
        normalized_value = re.sub(r'[,\s]', '', str(value))
        match = re.search(normalized_value, re.sub(r'[,\s]', '', text), re.IGNORECASE)
        if not match:
            return None
    
    start = max(0, match.start() - context_chars)
    end = min(len(text), match.end() + context_chars)
    
    snippet = text[start:end]
    
    # Limpiar snippet (quitar saltos de línea excesivos)
    snippet = re.sub(r'\s+', ' ', snippet).strip()
    
    # Agregar elipsis si truncamos
    if start > 0:
        snippet = '...' + snippet
    if end < len(text):
        snippet = snippet + '...'
    
    return {
        'snippet': snippet,
        'offset_start': match.start(),
        'offset_end': match.end(),
        'matched_text': match.group()
    }


def find_all_evidence(text: str, values: Dict[str, str]) -> Dict[str, Optional[Dict]]:
    """
    Busca múltiples valores y retorna evidencias para cada uno.
    
    Args:
        text: Texto completo
        values: Dict de {field_name: value_to_find}
    
    Returns:
        Dict de {field_name: evidence_dict or None}
    """
    evidence = {}
    for field_name, value in values.items():
        evidence[field_name] = extract_evidence_snippet(text, value)
    return evidence

