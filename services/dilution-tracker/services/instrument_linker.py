"""
Instrument Linking System

Este módulo implementa el enlace de instrumentos financieros (ATM, Shelf, Warrants)
a través de múltiples filings SEC para obtener una visión completa de cada instrumento.

PROBLEMA QUE RESUELVE:
- Un ATM se anuncia en un 424B5 con total_capacity=$75M
- Su uso se reporta en 10-Qs posteriores (remaining_capacity)
- Sin enlazar, perdemos la conexión entre estos datos

SOLUCIÓN:
1. Identificar instrumentos en filings iniciales (424B, S-3, S-1, 8-K)
2. Crear ID único para cada instrumento
3. Buscar menciones en filings posteriores (10-Q, 10-K, 8-K)
4. Fusionar datos para visión completa
"""

import re
import hashlib
from typing import Dict, List, Optional, Tuple, Set
from dataclasses import dataclass, field
from datetime import date, datetime
from enum import Enum
import structlog

logger = structlog.get_logger(__name__)


class InstrumentType(Enum):
    ATM = "atm"
    SHELF = "shelf"
    WARRANT = "warrant"
    CONVERTIBLE_NOTE = "convertible_note"
    CONVERTIBLE_PREFERRED = "convertible_preferred"
    EQUITY_LINE = "equity_line"


@dataclass
class InstrumentSignature:
    """
    Firma única de un instrumento para identificarlo a través de múltiples filings.
    
    La firma se construye con datos que NO cambian:
    - ATM: placement_agent + agreement_date
    - Shelf: registration_number OR (filing_date + total_capacity)
    - Warrant: issue_date + exercise_price + series_name
    """
    instrument_type: InstrumentType
    unique_id: str  # Hash MD5 de los campos identificadores
    identifiers: Dict[str, str]  # Campos usados para identificar
    source_filing: str  # Filing donde se identificó por primera vez
    source_date: Optional[str] = None
    
    def __hash__(self):
        return hash(self.unique_id)
    
    def __eq__(self, other):
        if not isinstance(other, InstrumentSignature):
            return False
        return self.unique_id == other.unique_id


@dataclass
class LinkedInstrument:
    """
    Instrumento con datos fusionados de múltiples filings.
    """
    signature: InstrumentSignature
    filings: List[Dict] = field(default_factory=list)  # Lista de filings relacionados
    merged_data: Dict = field(default_factory=dict)  # Datos fusionados
    timeline: List[Dict] = field(default_factory=list)  # Historial de cambios
    
    def add_filing(self, filing_info: Dict, extracted_data: Dict):
        """Agregar un filing y sus datos extraídos al instrumento"""
        self.filings.append({
            "filing": filing_info,
            "data": extracted_data
        })
        self.timeline.append({
            "date": filing_info.get("filing_date"),
            "form_type": filing_info.get("form_type"),
            "data": extracted_data
        })
        # Ordenar timeline por fecha
        self.timeline.sort(key=lambda x: x.get("date", ""), reverse=True)


class InstrumentLinker:
    """
    Sistema de enlace de instrumentos financieros.
    
    Flujo:
    1. identify_instruments() - Identificar instrumentos en filings iniciales
    2. find_related_filings() - Buscar filings que mencionen los instrumentos
    3. link_and_merge() - Fusionar datos de múltiples filings
    """
    
    def __init__(self):
        self.instruments: Dict[str, LinkedInstrument] = {}
        self._stats = {
            "instruments_identified": 0,
            "filings_linked": 0,
            "merges_performed": 0
        }
    
    # ==================== FASE 1: IDENTIFICACIÓN ====================
    
    def identify_instruments(
        self, 
        extracted_data: Dict,
        source_filing: Dict
    ) -> List[InstrumentSignature]:
        """
        Identificar instrumentos en los datos extraídos de un filing.
        
        Args:
            extracted_data: Datos extraídos por Grok (warrants, atm, shelf, etc.)
            source_filing: Información del filing fuente
            
        Returns:
            Lista de firmas de instrumentos identificados
        """
        signatures = []
        
        # Identificar ATMs
        for atm in extracted_data.get("atm_offerings", []):
            sig = self._create_atm_signature(atm, source_filing)
            if sig:
                signatures.append(sig)
                self._register_instrument(sig)
        
        # Identificar Shelfs
        for shelf in extracted_data.get("shelf_registrations", []):
            sig = self._create_shelf_signature(shelf, source_filing)
            if sig:
                signatures.append(sig)
                self._register_instrument(sig)
        
        # Identificar Warrants
        for warrant in extracted_data.get("warrants", []):
            sig = self._create_warrant_signature(warrant, source_filing)
            if sig:
                signatures.append(sig)
                self._register_instrument(sig)
        
        # Identificar Convertible Notes
        for note in extracted_data.get("convertible_notes", []):
            sig = self._create_convertible_signature(note, source_filing, InstrumentType.CONVERTIBLE_NOTE)
            if sig:
                signatures.append(sig)
                self._register_instrument(sig)
        
        logger.info("instruments_identified", 
                   count=len(signatures),
                   source=source_filing.get("form_type"))
        
        return signatures
    
    def _create_atm_signature(self, atm: Dict, source_filing: Dict) -> Optional[InstrumentSignature]:
        """Crear firma única para un ATM"""
        # Campos identificadores para ATM
        agent = self._normalize_string(atm.get("placement_agent", ""))
        agreement_date = atm.get("agreement_date") or atm.get("filing_date") or source_filing.get("filing_date", "")
        total = atm.get("total_capacity", "")
        
        # Necesitamos al menos agent o agreement_date
        if not agent and not agreement_date:
            return None
        
        identifiers = {
            "placement_agent": agent,
            "agreement_date": str(agreement_date)[:10] if agreement_date else "",
            "total_capacity": str(total) if total else ""
        }
        
        unique_id = self._generate_id(InstrumentType.ATM, identifiers)
        
        return InstrumentSignature(
            instrument_type=InstrumentType.ATM,
            unique_id=unique_id,
            identifiers=identifiers,
            source_filing=source_filing.get("form_type", ""),
            source_date=source_filing.get("filing_date", "")
        )
    
    def _create_shelf_signature(self, shelf: Dict, source_filing: Dict) -> Optional[InstrumentSignature]:
        """Crear firma única para un Shelf Registration"""
        # Campos identificadores para Shelf
        reg_number = self._normalize_string(shelf.get("registration_statement", "") or shelf.get("file_number", ""))
        filing_date = shelf.get("effect_date") or shelf.get("filing_date") or source_filing.get("filing_date", "")
        total = shelf.get("total_capacity", "")
        
        # Necesitamos al menos registration_number o filing_date
        if not reg_number and not filing_date:
            return None
        
        identifiers = {
            "registration_statement": reg_number,
            "effect_date": str(filing_date)[:10] if filing_date else "",
            "total_capacity": str(total) if total else ""
        }
        
        unique_id = self._generate_id(InstrumentType.SHELF, identifiers)
        
        return InstrumentSignature(
            instrument_type=InstrumentType.SHELF,
            unique_id=unique_id,
            identifiers=identifiers,
            source_filing=source_filing.get("form_type", ""),
            source_date=source_filing.get("filing_date", "")
        )
    
    def _create_warrant_signature(self, warrant: Dict, source_filing: Dict) -> Optional[InstrumentSignature]:
        """Crear firma única para un Warrant"""
        # Campos identificadores para Warrant
        issue_date = warrant.get("issue_date") or source_filing.get("filing_date", "")
        exercise_price = warrant.get("exercise_price", "")
        series = self._normalize_string(warrant.get("series_name", "") or warrant.get("description", ""))
        outstanding = warrant.get("outstanding", "") or warrant.get("total_issued", "")
        
        if not issue_date and not exercise_price:
            return None
        
        identifiers = {
            "issue_date": str(issue_date)[:10] if issue_date else "",
            "exercise_price": str(exercise_price) if exercise_price else "",
            "series_name": series[:50] if series else "",  # Limitar longitud
            "outstanding": str(outstanding) if outstanding else ""
        }
        
        unique_id = self._generate_id(InstrumentType.WARRANT, identifiers)
        
        return InstrumentSignature(
            instrument_type=InstrumentType.WARRANT,
            unique_id=unique_id,
            identifiers=identifiers,
            source_filing=source_filing.get("form_type", ""),
            source_date=source_filing.get("filing_date", "")
        )
    
    def _create_convertible_signature(
        self, 
        instrument: Dict, 
        source_filing: Dict,
        instrument_type: InstrumentType
    ) -> Optional[InstrumentSignature]:
        """Crear firma única para Convertible Note o Preferred"""
        issue_date = instrument.get("issue_date") or source_filing.get("filing_date", "")
        principal = instrument.get("principal_amount", "") or instrument.get("total_amount", "")
        conversion_price = instrument.get("conversion_price", "")
        
        if not issue_date and not principal:
            return None
        
        identifiers = {
            "issue_date": str(issue_date)[:10] if issue_date else "",
            "principal_amount": str(principal) if principal else "",
            "conversion_price": str(conversion_price) if conversion_price else ""
        }
        
        unique_id = self._generate_id(instrument_type, identifiers)
        
        return InstrumentSignature(
            instrument_type=instrument_type,
            unique_id=unique_id,
            identifiers=identifiers,
            source_filing=source_filing.get("form_type", ""),
            source_date=source_filing.get("filing_date", "")
        )
    
    def _generate_id(self, instrument_type: InstrumentType, identifiers: Dict) -> str:
        """Generar ID único basado en tipo e identificadores"""
        # Crear string consistente para hash
        parts = [instrument_type.value]
        for key in sorted(identifiers.keys()):
            value = identifiers.get(key, "")
            if value:
                parts.append(f"{key}:{value}")
        
        raw = "|".join(parts)
        return hashlib.md5(raw.encode()).hexdigest()[:12]
    
    def _register_instrument(self, signature: InstrumentSignature):
        """Registrar un instrumento en el sistema"""
        if signature.unique_id not in self.instruments:
            self.instruments[signature.unique_id] = LinkedInstrument(signature=signature)
            self._stats["instruments_identified"] += 1
    
    # ==================== FASE 2: BÚSQUEDA DE FILINGS RELACIONADOS ====================
    
    def find_related_mentions(
        self,
        filing_content: str,
        filing_info: Dict
    ) -> List[Tuple[InstrumentSignature, Dict]]:
        """
        Buscar menciones de instrumentos conocidos en un filing.
        
        Args:
            filing_content: Contenido del filing (texto)
            filing_info: Metadata del filing
            
        Returns:
            Lista de (signature, contexto_encontrado)
        """
        mentions = []
        content_lower = filing_content.lower()
        
        for unique_id, linked in self.instruments.items():
            sig = linked.signature
            
            # Buscar según tipo de instrumento
            if sig.instrument_type == InstrumentType.ATM:
                mention = self._find_atm_mention(content_lower, sig)
            elif sig.instrument_type == InstrumentType.SHELF:
                mention = self._find_shelf_mention(content_lower, sig)
            elif sig.instrument_type == InstrumentType.WARRANT:
                mention = self._find_warrant_mention(content_lower, sig)
            else:
                mention = self._find_generic_mention(content_lower, sig)
            
            if mention:
                mentions.append((sig, mention))
                self._stats["filings_linked"] += 1
        
        return mentions
    
    def _find_atm_mention(self, content: str, sig: InstrumentSignature) -> Optional[Dict]:
        """Buscar mención de un ATM específico"""
        agent = sig.identifiers.get("placement_agent", "").lower()
        total = sig.identifiers.get("total_capacity", "")
        
        # Patrones de búsqueda
        patterns = []
        
        if agent:
            # "at the market" + agent name
            patterns.append(rf'at.the.market.*{re.escape(agent)}')
            patterns.append(rf'{re.escape(agent)}.*at.the.market')
            patterns.append(rf'atm.*{re.escape(agent)}')
            patterns.append(rf'sales.agreement.*{re.escape(agent)}')
        
        if total:
            # Buscar el monto total
            total_str = self._format_money_pattern(total)
            if total_str:
                patterns.append(rf'{total_str}.*at.the.market')
                patterns.append(rf'at.the.market.*{total_str}')
        
        for pattern in patterns:
            if re.search(pattern, content):
                # Extraer contexto alrededor de la mención
                match = re.search(pattern, content)
                if match:
                    start = max(0, match.start() - 200)
                    end = min(len(content), match.end() + 200)
                    return {
                        "found": True,
                        "pattern": pattern,
                        "context": content[start:end]
                    }
        
        return None
    
    def _find_shelf_mention(self, content: str, sig: InstrumentSignature) -> Optional[Dict]:
        """Buscar mención de un Shelf específico"""
        reg_number = sig.identifiers.get("registration_statement", "").lower()
        
        if reg_number and reg_number in content:
            # Encontrar contexto
            idx = content.find(reg_number)
            start = max(0, idx - 200)
            end = min(len(content), idx + len(reg_number) + 200)
            return {
                "found": True,
                "pattern": f"registration_number:{reg_number}",
                "context": content[start:end]
            }
        
        return None
    
    def _find_warrant_mention(self, content: str, sig: InstrumentSignature) -> Optional[Dict]:
        """Buscar mención de un Warrant específico"""
        exercise_price = sig.identifiers.get("exercise_price", "")
        series_name = sig.identifiers.get("series_name", "").lower()
        
        patterns = []
        
        if exercise_price:
            price_pattern = self._format_money_pattern(exercise_price)
            if price_pattern:
                patterns.append(rf'warrant.*{price_pattern}')
                patterns.append(rf'{price_pattern}.*warrant')
                patterns.append(rf'exercise.*price.*{price_pattern}')
        
        if series_name and len(series_name) > 3:
            patterns.append(rf'{re.escape(series_name)}.*warrant')
        
        for pattern in patterns:
            if re.search(pattern, content):
                match = re.search(pattern, content)
                if match:
                    start = max(0, match.start() - 200)
                    end = min(len(content), match.end() + 200)
                    return {
                        "found": True,
                        "pattern": pattern,
                        "context": content[start:end]
                    }
        
        return None
    
    def _find_generic_mention(self, content: str, sig: InstrumentSignature) -> Optional[Dict]:
        """Búsqueda genérica para otros tipos de instrumentos"""
        # Usar campos identificadores como patrones de búsqueda
        for key, value in sig.identifiers.items():
            if value and len(str(value)) > 3:
                if str(value).lower() in content:
                    return {"found": True, "pattern": f"{key}:{value}"}
        return None
    
    # ==================== FASE 3: FUSIÓN DE DATOS ====================
    
    def merge_instrument_data(self, signature: InstrumentSignature, new_data: Dict, filing_info: Dict):
        """
        Fusionar nuevos datos con un instrumento existente.
        
        Estrategia de fusión:
        - Campos numéricos: usar el más reciente
        - Campos de texto: usar el más completo
        - Listas: acumular sin duplicar
        """
        if signature.unique_id not in self.instruments:
            return
        
        linked = self.instruments[signature.unique_id]
        linked.add_filing(filing_info, new_data)
        
        # Fusionar datos
        merged = linked.merged_data
        
        for key, value in new_data.items():
            if value is None:
                continue
            
            existing = merged.get(key)
            
            if existing is None:
                # No existe, agregar
                merged[key] = value
            elif isinstance(value, (int, float)) and isinstance(existing, (int, float)):
                # Numérico: usar el más reciente (asumiendo que new_data es más reciente)
                merged[key] = value
            elif isinstance(value, str) and isinstance(existing, str):
                # String: usar el más largo/completo
                if len(value) > len(existing):
                    merged[key] = value
            elif isinstance(value, list) and isinstance(existing, list):
                # Lista: fusionar sin duplicados
                merged[key] = list(set(existing + value))
        
        self._stats["merges_performed"] += 1
        
        logger.debug("instrument_data_merged",
                    instrument_id=signature.unique_id,
                    instrument_type=signature.instrument_type.value,
                    filing=filing_info.get("form_type"))
    
    # ==================== FASE 4: OBTENER DATOS COMPLETOS ====================
    
    def get_complete_instruments(self) -> Dict[str, List[Dict]]:
        """
        Obtener todos los instrumentos con sus datos fusionados.
        
        Returns:
            Dict con listas de instrumentos por tipo
        """
        result = {
            "atm_offerings": [],
            "shelf_registrations": [],
            "warrants": [],
            "convertible_notes": [],
            "convertible_preferred": [],
            "equity_lines": []
        }
        
        for unique_id, linked in self.instruments.items():
            sig = linked.signature
            data = linked.merged_data.copy()
            
            # Agregar metadata de linking
            data["_linked"] = True
            data["_unique_id"] = unique_id
            data["_filings_count"] = len(linked.filings)
            data["_source_filing"] = sig.source_filing
            data["_source_date"] = sig.source_date
            
            # Mapear tipo a lista correspondiente
            type_map = {
                InstrumentType.ATM: "atm_offerings",
                InstrumentType.SHELF: "shelf_registrations",
                InstrumentType.WARRANT: "warrants",
                InstrumentType.CONVERTIBLE_NOTE: "convertible_notes",
                InstrumentType.CONVERTIBLE_PREFERRED: "convertible_preferred",
                InstrumentType.EQUITY_LINE: "equity_lines"
            }
            
            list_key = type_map.get(sig.instrument_type)
            if list_key:
                result[list_key].append(data)
        
        logger.info("complete_instruments_retrieved",
                   atm=len(result["atm_offerings"]),
                   shelf=len(result["shelf_registrations"]),
                   warrants=len(result["warrants"]),
                   stats=self._stats)
        
        return result
    
    def get_instrument_timeline(self, unique_id: str) -> List[Dict]:
        """Obtener el timeline de un instrumento específico"""
        if unique_id in self.instruments:
            return self.instruments[unique_id].timeline
        return []
    
    # ==================== UTILIDADES ====================
    
    def _normalize_string(self, s: str) -> str:
        """Normalizar string para comparación"""
        if not s:
            return ""
        # Remover caracteres especiales, convertir a minúsculas
        s = re.sub(r'[^\w\s]', '', str(s).lower())
        return ' '.join(s.split())  # Normalizar espacios
    
    def _format_money_pattern(self, amount) -> Optional[str]:
        """Crear patrón regex para buscar montos de dinero"""
        try:
            # Convertir a número
            if isinstance(amount, str):
                amount = float(re.sub(r'[^\d.]', '', amount))
            
            if amount >= 1_000_000:
                # Millones: $75M, $75,000,000, 75 million
                millions = amount / 1_000_000
                patterns = [
                    rf'\${millions:.0f}\s*m',
                    rf'\${millions:.1f}\s*m',
                    rf'\${amount:,.0f}',
                    rf'{millions:.0f}\s*million'
                ]
                return '|'.join(patterns)
            elif amount >= 1000:
                return rf'\${amount:,.0f}'
            else:
                return rf'\${amount:.2f}'
        except:
            return None
    
    def get_stats(self) -> Dict:
        """Obtener estadísticas del linker"""
        return self._stats.copy()
    
    def reset(self):
        """Resetear el linker para un nuevo análisis"""
        self.instruments.clear()
        self._stats = {
            "instruments_identified": 0,
            "filings_linked": 0,
            "merges_performed": 0
        }


# ==================== FUNCIÓN DE ALTO NIVEL ====================

async def link_instruments_across_filings(
    filings_with_data: List[Tuple[Dict, Dict]],
    ticker: str
) -> Dict:
    """
    Función de alto nivel para enlazar instrumentos a través de múltiples filings.
    
    Args:
        filings_with_data: Lista de (filing_info, extracted_data)
        ticker: Ticker symbol
        
    Returns:
        Dict con instrumentos fusionados
    """
    linker = InstrumentLinker()
    
    # Fase 1: Identificar instrumentos en cada filing
    logger.info("instrument_linking_started", ticker=ticker, filings_count=len(filings_with_data))
    
    for filing_info, extracted_data in filings_with_data:
        linker.identify_instruments(extracted_data, filing_info)
    
    # Fase 2: Buscar menciones cruzadas
    # (Para filings que no extrajeron instrumentos pero los mencionan)
    for filing_info, extracted_data in filings_with_data:
        content = filing_info.get("content", "")
        if content:
            mentions = linker.find_related_mentions(content, filing_info)
            for sig, mention_info in mentions:
                # Extraer datos adicionales del contexto
                # (En una implementación completa, aquí llamaríamos a Grok
                # con el contexto específico para extraer datos actualizados)
                pass
    
    # Fase 3 & 4: Obtener instrumentos completos
    result = linker.get_complete_instruments()
    
    logger.info("instrument_linking_completed", 
               ticker=ticker,
               stats=linker.get_stats())
    
    return result

