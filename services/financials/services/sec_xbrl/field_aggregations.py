"""
Field Aggregation Rules - Sistema escalable para detectar y agregar campos relacionados.

Muchas empresas reportan gastos de forma diferente. Por ejemplo:
- AST SpaceMobile reporta parte de su R&D como "OtherGeneralExpense"
- Algunas empresas de retail reportan "CostOfMerchandiseSold" separado de "CostOfGoodsSold"
- Biotech puede reportar R&D en múltiples líneas

Este módulo define reglas de agregación que detectan estos patrones y consolidan
los valores para una comparación más precisa con servicios como TIKR.
"""

from typing import Dict, List, Optional, Any, Callable
from dataclasses import dataclass, field
from enum import Enum

from shared.utils.logger import get_logger

logger = get_logger(__name__)


class AggregationCondition(Enum):
    """Condiciones para aplicar agregación."""
    ALWAYS = "always"                           # Siempre agregar
    SECTOR_MATCH = "sector_match"               # Solo si el sector coincide
    RATIO_THRESHOLD = "ratio_threshold"         # Si el ratio supera umbral
    FIELD_MISSING = "field_missing"             # Si el campo destino está vacío
    FIELD_SMALL = "field_small"                 # Si el campo destino es pequeño


@dataclass
class AggregationRule:
    """
    Define una regla de agregación de campos.
    
    Ejemplo: OtherGeneralExpense → rd_expenses para empresas tech/aerospace
    """
    source_field: str                           # Campo XBRL fuente (e.g., "other_general_expense")
    target_field: str                           # Campo canónico destino (e.g., "rd_expenses")
    condition: AggregationCondition             # Cuándo aplicar
    sectors: List[str] = field(default_factory=list)  # Sectores aplicables
    ratio_threshold: float = 0.5                # Umbral para RATIO_THRESHOLD
    priority: int = 1                           # Mayor = más prioritario
    description: str = ""                       # Descripción de la regla


# =============================================================================
# REGLAS DE AGREGACIÓN POR CAMPO CANÓNICO
# =============================================================================

AGGREGATION_RULES: Dict[str, List[AggregationRule]] = {
    # -------------------------------------------------------------------------
    # R&D EXPENSES - Gastos de investigación y desarrollo
    # -------------------------------------------------------------------------
    "rd_expenses": [
        AggregationRule(
            source_field="other_general_expense",
            target_field="rd_expenses",
            condition=AggregationCondition.SECTOR_MATCH,
            sectors=[
                "Technology", "Aerospace", "Healthcare", "Biotechnology",
                "Pharmaceuticals", "Semiconductors", "Software", 
                "Communication Equipment", "Space", "Defense"
            ],
            description="En sectores tech/aerospace, OtherGeneralExpense suele contener R&D adicional"
        ),
        AggregationRule(
            source_field="technology_and_development_expense",
            target_field="rd_expenses",
            condition=AggregationCondition.ALWAYS,
            description="Concepto alternativo de R&D usado por algunas empresas"
        ),
        AggregationRule(
            source_field="in_process_research_and_development",
            target_field="rd_expenses",
            condition=AggregationCondition.ALWAYS,
            description="R&D en proceso de adquisiciones"
        ),
    ],
    
    # -------------------------------------------------------------------------
    # COST OF REVENUE - Costo de ventas/revenue
    # -------------------------------------------------------------------------
    "cost_of_revenue": [
        AggregationRule(
            source_field="cost_of_merchandise_sold",
            target_field="cost_of_revenue",
            condition=AggregationCondition.FIELD_MISSING,
            description="Alternativa para retail: CostOfMerchandiseSold"
        ),
        AggregationRule(
            source_field="cost_of_services",
            target_field="cost_of_revenue",
            condition=AggregationCondition.ALWAYS,
            sectors=["Services", "Consulting", "IT Services"],
            description="Para empresas de servicios"
        ),
    ],
    
    # -------------------------------------------------------------------------
    # SG&A - Gastos generales y administrativos
    # -------------------------------------------------------------------------
    "sga_expenses": [
        AggregationRule(
            source_field="ga_expenses",
            target_field="sga_expenses",
            condition=AggregationCondition.FIELD_MISSING,
            description="G&A es componente de SG&A"
        ),
        AggregationRule(
            source_field="selling_expense",
            target_field="sga_expenses",
            condition=AggregationCondition.ALWAYS,
            description="Gastos de venta son parte de SG&A"
        ),
    ],
    
    # -------------------------------------------------------------------------
    # OPERATING INCOME - Ingreso operativo
    # -------------------------------------------------------------------------
    "operating_income": [
        # Normalmente calculado, pero algunas empresas lo reportan directamente
    ],
    
    # -------------------------------------------------------------------------
    # DEPRECIATION & AMORTIZATION
    # -------------------------------------------------------------------------
    "depreciation_amortization": [
        AggregationRule(
            source_field="depreciation_expense",
            target_field="depreciation_amortization",
            condition=AggregationCondition.ALWAYS,
            description="Depreciación sola"
        ),
        AggregationRule(
            source_field="amortization_expense",
            target_field="depreciation_amortization",
            condition=AggregationCondition.ALWAYS,
            description="Amortización sola"
        ),
    ],
}


# =============================================================================
# SECTORES POR SIC/NAICS (para detección automática)
# =============================================================================

SECTOR_KEYWORDS = {
    "Technology": ["software", "tech", "digital", "internet", "cloud", "ai", "data"],
    "Aerospace": ["space", "satellite", "aerospace", "aviation", "rocket"],
    "Healthcare": ["health", "medical", "hospital", "care"],
    "Biotechnology": ["biotech", "bio", "gene", "therapy"],
    "Pharmaceuticals": ["pharma", "drug", "medicine"],
    "Semiconductors": ["semiconductor", "chip", "processor"],
    "Defense": ["defense", "military", "security"],
}


class FieldAggregator:
    """
    Aplica reglas de agregación a datos financieros extraídos.
    
    Uso:
        aggregator = FieldAggregator()
        aggregator.set_company_context(ticker="ASTS", sector="Aerospace")
        enhanced_data = aggregator.apply_aggregations(income_data)
    """
    
    def __init__(self):
        self.rules = AGGREGATION_RULES
        self.ticker: Optional[str] = None
        self.sector: Optional[str] = None
        self.industry: Optional[str] = None
        self._aggregation_log: List[Dict[str, Any]] = []
    
    def set_company_context(
        self, 
        ticker: str,
        sector: Optional[str] = None,
        industry: Optional[str] = None,
        description: Optional[str] = None
    ):
        """
        Establece el contexto de la empresa para aplicar reglas por sector.
        
        Args:
            ticker: Símbolo de la empresa
            sector: Sector de la empresa (e.g., "Technology")
            industry: Industria específica (e.g., "Semiconductors")
            description: Descripción de la empresa para detección automática
        """
        self.ticker = ticker
        self.sector = sector
        self.industry = industry
        
        # Si no hay sector, intentar detectar por descripción
        if not sector and description:
            self.sector = self._detect_sector(description)
            if self.sector:
                logger.info(f"[{ticker}] Auto-detected sector: {self.sector}")
    
    def _detect_sector(self, description: str) -> Optional[str]:
        """Detecta el sector basándose en la descripción de la empresa."""
        description_lower = description.lower()
        
        for sector, keywords in SECTOR_KEYWORDS.items():
            for keyword in keywords:
                if keyword in description_lower:
                    return sector
        return None
    
    def apply_aggregations(
        self, 
        field_data: Dict[str, Any],
        statement_type: str = "income"
    ) -> Dict[str, Any]:
        """
        Aplica reglas de agregación a los datos extraídos.
        
        Args:
            field_data: Diccionario de campos extraídos {field_name: value}
            statement_type: Tipo de estado financiero
            
        Returns:
            Diccionario con valores agregados y metadatos
        """
        self._aggregation_log = []
        enhanced_data = dict(field_data)
        
        for target_field, rules in self.rules.items():
            for rule in rules:
                if self._should_apply_rule(rule, enhanced_data):
                    self._apply_rule(rule, enhanced_data)
        
        return enhanced_data
    
    def _should_apply_rule(self, rule: AggregationRule, data: Dict[str, Any]) -> bool:
        """Determina si una regla debe aplicarse."""
        
        # Verificar que el campo fuente existe y tiene valor
        source_value = data.get(rule.source_field)
        if source_value is None or source_value == 0:
            return False
        
        # Evaluar condición
        if rule.condition == AggregationCondition.ALWAYS:
            return True
            
        elif rule.condition == AggregationCondition.SECTOR_MATCH:
            if not rule.sectors:
                return True
            return (
                self.sector in rule.sectors or 
                self.industry in rule.sectors
            )
            
        elif rule.condition == AggregationCondition.FIELD_MISSING:
            target_value = data.get(rule.target_field)
            return target_value is None or target_value == 0
            
        elif rule.condition == AggregationCondition.FIELD_SMALL:
            target_value = data.get(rule.target_field, 0) or 0
            source_value = data.get(rule.source_field, 0) or 0
            if source_value == 0:
                return False
            # Si el target es menos del 50% del source, probablemente falta agregar
            return target_value < source_value * rule.ratio_threshold
            
        elif rule.condition == AggregationCondition.RATIO_THRESHOLD:
            target_value = data.get(rule.target_field, 0) or 0
            source_value = data.get(rule.source_field, 0) or 0
            if target_value == 0:
                return True
            ratio = source_value / target_value
            return ratio >= rule.ratio_threshold
        
        return False
    
    def _apply_rule(self, rule: AggregationRule, data: Dict[str, Any]):
        """Aplica una regla de agregación."""
        source_value = data.get(rule.source_field, 0) or 0
        target_value = data.get(rule.target_field, 0) or 0
        
        new_value = target_value + source_value
        
        # Log de la agregación
        log_entry = {
            "ticker": self.ticker,
            "rule": f"{rule.source_field} → {rule.target_field}",
            "source_value": source_value,
            "original_target": target_value,
            "new_target": new_value,
            "condition": rule.condition.value,
            "description": rule.description
        }
        self._aggregation_log.append(log_entry)
        
        logger.debug(
            f"[{self.ticker}] Aggregation: {rule.source_field}({source_value:,.0f}) "
            f"→ {rule.target_field} ({target_value:,.0f} + {source_value:,.0f} = {new_value:,.0f})"
        )
        
        # Actualizar el valor
        data[rule.target_field] = new_value
        
        # Marcar que hubo agregación
        if "_aggregations" not in data:
            data["_aggregations"] = {}
        data["_aggregations"][rule.target_field] = {
            "original": target_value,
            "added_from": rule.source_field,
            "added_value": source_value,
            "final": new_value
        }
    
    def get_aggregation_log(self) -> List[Dict[str, Any]]:
        """Retorna el log de agregaciones aplicadas."""
        return self._aggregation_log
    
    def add_custom_rule(self, rule: AggregationRule):
        """Agrega una regla personalizada en runtime."""
        target = rule.target_field
        if target not in self.rules:
            self.rules[target] = []
        self.rules[target].append(rule)
        logger.info(f"Added custom aggregation rule: {rule.source_field} → {target}")


# =============================================================================
# FUNCIÓN HELPER PARA USO RÁPIDO
# =============================================================================

def aggregate_fields(
    field_data: Dict[str, Any],
    ticker: str,
    sector: Optional[str] = None,
    industry: Optional[str] = None
) -> Dict[str, Any]:
    """
    Helper function para aplicar agregaciones rápidamente.
    
    Args:
        field_data: Datos de campos extraídos
        ticker: Símbolo
        sector: Sector (opcional)
        industry: Industria (opcional)
        
    Returns:
        Datos con agregaciones aplicadas
    """
    aggregator = FieldAggregator()
    aggregator.set_company_context(ticker=ticker, sector=sector, industry=industry)
    return aggregator.apply_aggregations(field_data)

