"""
Grok Normalizers
================
Funciones para normalizar respuestas de Grok API a nuestro schema estándar.

Grok devuelve datos en formatos inconsistentes:
- {"value": 1.50} en lugar de 1.50
- ["2025-12-31"] en lugar de "2025-12-31"
- Diferentes nombres de campos para el mismo concepto

Este módulo estandariza todos los datos de Grok.
"""

import json
from typing import Any, Dict, List, Optional

from shared.utils.logger import get_logger

logger = get_logger(__name__)


class GrokNormalizers:
    """
    Clase con métodos para normalizar respuestas de Grok API.
    
    Puede usarse como mixin o instancia independiente.
    """
    
    def to_hashable(self, value: Any) -> Any:
        """
        Convierte cualquier valor a un tipo hashable para usar en sets/dicts.
        
        CRÍTICO: Grok a veces devuelve estructuras inesperadas como:
        - {"value": 1.50, "currency": "$"} en lugar de 1.50
        - ["2025-12-31"] en lugar de "2025-12-31"
        - {"date": "2025-12-31", "type": "fixed"} en lugar de "2025-12-31"
        
        Returns:
            Valor hashable (str, int, float, bool, None, o tuple para listas)
        """
        if value is None:
            return None
        if isinstance(value, (str, int, float, bool)):
            return value
        if isinstance(value, dict):
            try:
                return json.dumps(value, sort_keys=True, default=str)
            except (TypeError, ValueError):
                return str(value)
        if isinstance(value, (list, tuple)):
            return tuple(self.to_hashable(item) for item in value)
        return str(value)
    
    def normalize_grok_value(self, value: Any, expected_type: str = "string") -> Any:
        """
        Normaliza un valor de Grok extrayendo el valor real de estructuras anidadas.
        
        Grok a veces devuelve:
        - {"value": X} → extraemos X
        - {"amount": X} → extraemos X
        - {"date": X} → extraemos X
        - [X] → extraemos X (si es lista de un elemento)
        
        Args:
            value: Valor crudo de Grok
            expected_type: "string", "number", "date", "any"
            
        Returns:
            Valor normalizado o None si no se puede extraer
        """
        if value is None:
            return None
            
        # Si ya es del tipo esperado, devolverlo
        if expected_type == "number" and isinstance(value, (int, float)):
            return value
        if expected_type == "string" and isinstance(value, str):
            return value
        if expected_type == "date" and isinstance(value, str):
            return value
        if expected_type == "any" and isinstance(value, (str, int, float, bool)):
            return value
            
        # Si es dict, intentar extraer el valor
        if isinstance(value, dict):
            value_fields = ['value', 'amount', 'price', 'date', 'count', 'number', 
                           'shares', 'quantity', 'total', 'remaining', 'outstanding']
            
            for field in value_fields:
                if field in value:
                    extracted = value[field]
                    return self.normalize_grok_value(extracted, expected_type)
            
            if len(value) == 1:
                only_value = list(value.values())[0]
                return self.normalize_grok_value(only_value, expected_type)
            
            logger.warning("grok_complex_value_normalized", 
                          original_type="dict",
                          keys=list(value.keys())[:5],
                          action="converting_to_string")
            return str(value)
            
        # Si es lista de un solo elemento, extraerlo
        if isinstance(value, list):
            if len(value) == 1:
                return self.normalize_grok_value(value[0], expected_type)
            elif len(value) == 0:
                return None
            else:
                logger.warning("grok_list_value_normalized",
                              list_length=len(value),
                              action="using_first_element")
                return self.normalize_grok_value(value[0], expected_type)
        
        # Fallback: intentar conversión directa
        if expected_type == "number":
            try:
                if isinstance(value, str):
                    cleaned = value.replace('$', '').replace(',', '').replace('%', '').strip()
                    if cleaned:
                        return float(cleaned)
                return None
            except (ValueError, TypeError):
                return None
        
        return str(value) if value is not None else None
    
    def safe_get_for_key(self, item: Dict, field: str, expected_type: str = "any") -> Any:
        """
        Obtiene un valor de un dict de forma segura para usar en keys de deduplicación.
        
        Combina normalize_grok_value y to_hashable para garantizar:
        1. El valor se extrae correctamente de estructuras anidadas
        2. El resultado es siempre hashable
        """
        raw_value = item.get(field)
        normalized = self.normalize_grok_value(raw_value, expected_type)
        return self.to_hashable(normalized)
    
    def normalize_grok_extraction_fields(self, extracted: Dict) -> Dict:
        """
        Normaliza los campos de la respuesta de Grok a nuestro schema estándar.
        
        Args:
            extracted: Respuesta raw de Grok (dict con warrants, atm_offerings, etc.)
            
        Returns:
            Dict normalizado con campos estandarizados
        """
        if not extracted:
            return extracted
        
        if 'warrants' in extracted and isinstance(extracted['warrants'], list):
            extracted['warrants'] = [
                self.normalize_warrant_fields(w) for w in extracted['warrants']
            ]
        
        if 'atm_offerings' in extracted and isinstance(extracted['atm_offerings'], list):
            extracted['atm_offerings'] = [
                self.normalize_atm_fields(a) for a in extracted['atm_offerings']
            ]
        
        if 'shelf_registrations' in extracted and isinstance(extracted['shelf_registrations'], list):
            extracted['shelf_registrations'] = [
                self.normalize_shelf_fields(s) for s in extracted['shelf_registrations']
            ]
        
        if 'completed_offerings' in extracted and isinstance(extracted['completed_offerings'], list):
            extracted['completed_offerings'] = [
                self.normalize_completed_fields(c) for c in extracted['completed_offerings']
            ]
        
        if 's1_offerings' in extracted and isinstance(extracted['s1_offerings'], list):
            extracted['s1_offerings'] = [
                self.normalize_s1_fields(s) for s in extracted['s1_offerings']
            ]
        
        if 'convertible_notes' in extracted and isinstance(extracted['convertible_notes'], list):
            extracted['convertible_notes'] = [
                self.normalize_convertible_note_fields(n) for n in extracted['convertible_notes']
            ]
        
        if 'convertible_preferred' in extracted and isinstance(extracted['convertible_preferred'], list):
            extracted['convertible_preferred'] = [
                self.normalize_convertible_preferred_fields(p) for p in extracted['convertible_preferred']
            ]
        
        if 'equity_lines' in extracted and isinstance(extracted['equity_lines'], list):
            extracted['equity_lines'] = [
                self.normalize_equity_line_fields(e) for e in extracted['equity_lines']
            ]
        
        return extracted
    
    def normalize_warrant_fields(self, w: Dict) -> Dict:
        """
        Normaliza campos de un warrant al schema estándar.
        
        MAPEOS:
        - number, number_issued, shares → outstanding
        - issuance_date, offering_date → issue_date
        - type, description, series → notes
        - strike_price, price → exercise_price
        - expiry, expiry_date → expiration_date
        """
        if not isinstance(w, dict):
            return w
        
        normalized = dict(w)
        
        # === OUTSTANDING ===
        outstanding_aliases = [
            'number', 'number_issued', 'shares', 'total_shares', 
            'warrants_outstanding', 'quantity', 'amount', 'total_issued',
            'shares_issuable', 'warrant_shares', 'common_stock_issuable'
        ]
        if normalized.get('outstanding') is None:
            for alias in outstanding_aliases:
                if alias in normalized and normalized[alias] is not None:
                    normalized['outstanding'] = self.normalize_grok_value(normalized[alias], 'number')
                    break
        
        # === ISSUE_DATE ===
        issue_date_aliases = [
            'issuance_date', 'offering_date', 'filing_date', 'grant_date', 
            'date', 'issued_date', 'effective_date', 'agreement_date'
        ]
        if normalized.get('issue_date') is None:
            for alias in issue_date_aliases:
                if alias in normalized and normalized[alias] is not None:
                    normalized['issue_date'] = self.normalize_grok_value(normalized[alias], 'date')
                    break
        
        # === NOTES ===
        notes_aliases = [
            'type', 'description', 'series', 'name', 'warrant_type', 
            'title', 'terms', 'details', 'summary', 'warrant_name'
        ]
        if normalized.get('notes') is None:
            notes_parts = []
            for alias in notes_aliases:
                if alias in normalized and normalized[alias] is not None:
                    val = self.normalize_grok_value(normalized[alias], 'string')
                    if val and val not in notes_parts:
                        notes_parts.append(str(val))
            if notes_parts:
                normalized['notes'] = ' - '.join(notes_parts)
        
        # === EXERCISE_PRICE ===
        price_aliases = ['strike_price', 'price', 'strike', 'warrant_price', 'per_share_price']
        if normalized.get('exercise_price') is None:
            for alias in price_aliases:
                if alias in normalized and normalized[alias] is not None:
                    normalized['exercise_price'] = self.normalize_grok_value(normalized[alias], 'number')
                    break
        
        # === EXPIRATION_DATE ===
        expiration_aliases = ['expiry', 'expiry_date', 'maturity', 'expiration', 'expires', 'maturity_date']
        if normalized.get('expiration_date') is None:
            for alias in expiration_aliases:
                if alias in normalized and normalized[alias] is not None:
                    normalized['expiration_date'] = self.normalize_grok_value(normalized[alias], 'date')
                    break
        
        # === POTENTIAL_NEW_SHARES ===
        potential_aliases = ['potential_shares', 'dilution_shares', 'max_shares', 'shares_underlying']
        if normalized.get('potential_new_shares') is None:
            for alias in potential_aliases:
                if alias in normalized and normalized[alias] is not None:
                    normalized['potential_new_shares'] = self.normalize_grok_value(normalized[alias], 'number')
                    break
            # Fallback: outstanding = potential_new_shares para warrants
            if normalized.get('potential_new_shares') is None and normalized.get('outstanding') is not None:
                normalized['potential_new_shares'] = normalized['outstanding']
        
        return normalized
    
    def normalize_atm_fields(self, a: Dict) -> Dict:
        """
        Normaliza campos de un ATM offering al schema estándar.
        """
        if not isinstance(a, dict):
            return a
        
        normalized = dict(a)
        
        # === TOTAL_CAPACITY ===
        capacity_aliases = [
            'capacity', 'amount', 'aggregate_offering', 'max_offering', 
            'program_size', 'total_amount', 'aggregate_amount', 'offering_amount'
        ]
        if normalized.get('total_capacity') is None:
            for alias in capacity_aliases:
                if alias in normalized and normalized[alias] is not None:
                    normalized['total_capacity'] = self.normalize_grok_value(normalized[alias], 'number')
                    break
        
        # === REMAINING_CAPACITY ===
        remaining_aliases = ['remaining', 'available', 'unused', 'remaining_amount', 'available_capacity']
        if normalized.get('remaining_capacity') is None:
            for alias in remaining_aliases:
                if alias in normalized and normalized[alias] is not None:
                    normalized['remaining_capacity'] = self.normalize_grok_value(normalized[alias], 'number')
                    break
        
        # === PLACEMENT_AGENT ===
        agent_aliases = [
            'agent', 'underwriter', 'sales_agent', 'placement_agent_name',
            'dealer', 'manager', 'distributor'
        ]
        if normalized.get('placement_agent') is None:
            for alias in agent_aliases:
                if alias in normalized and normalized[alias] is not None:
                    normalized['placement_agent'] = self.normalize_grok_value(normalized[alias], 'string')
                    break
        
        # === FILING_DATE ===
        date_aliases = ['date', 'effective_date', 'agreement_date', 'execution_date']
        if normalized.get('filing_date') is None:
            for alias in date_aliases:
                if alias in normalized and normalized[alias] is not None:
                    normalized['filing_date'] = self.normalize_grok_value(normalized[alias], 'date')
                    break
        
        return normalized
    
    def normalize_shelf_fields(self, s: Dict) -> Dict:
        """
        Normaliza campos de un shelf registration al schema estándar.
        """
        if not isinstance(s, dict):
            return s
        
        normalized = dict(s)
        
        # === TOTAL_CAPACITY ===
        capacity_aliases = [
            'capacity', 'amount', 'aggregate_offering', 'max_offering',
            'registered_amount', 'total_amount', 'offering_amount'
        ]
        if normalized.get('total_capacity') is None:
            for alias in capacity_aliases:
                if alias in normalized and normalized[alias] is not None:
                    normalized['total_capacity'] = self.normalize_grok_value(normalized[alias], 'number')
                    break
        
        # === REMAINING_CAPACITY ===
        remaining_aliases = ['remaining', 'available', 'unused', 'remaining_amount']
        if normalized.get('remaining_capacity') is None:
            for alias in remaining_aliases:
                if alias in normalized and normalized[alias] is not None:
                    normalized['remaining_capacity'] = self.normalize_grok_value(normalized[alias], 'number')
                    break
        
        # === REGISTRATION_STATEMENT ===
        reg_aliases = ['form_type', 'type', 'form', 'statement_type', 'registration_type']
        if normalized.get('registration_statement') is None:
            for alias in reg_aliases:
                if alias in normalized and normalized[alias] is not None:
                    val = self.normalize_grok_value(normalized[alias], 'string')
                    if val:
                        val_upper = str(val).upper().replace(' ', '')
                        if 'S-3' in val_upper or 'S3' in val_upper:
                            normalized['registration_statement'] = 'S-3'
                        elif 'S-1' in val_upper or 'S1' in val_upper:
                            normalized['registration_statement'] = 'S-1'
                        elif 'S-11' in val_upper or 'S11' in val_upper:
                            normalized['registration_statement'] = 'S-11'
                        elif 'F-3' in val_upper or 'F3' in val_upper:
                            normalized['registration_statement'] = 'F-3'
                        elif 'F-1' in val_upper or 'F1' in val_upper:
                            normalized['registration_statement'] = 'F-1'
                        else:
                            normalized['registration_statement'] = val
                    break
        
        # === FILING_DATE ===
        date_aliases = ['date', 'effective_date', 'filed_date', 'registration_date']
        if normalized.get('filing_date') is None:
            for alias in date_aliases:
                if alias in normalized and normalized[alias] is not None:
                    normalized['filing_date'] = self.normalize_grok_value(normalized[alias], 'date')
                    break
        
        # === EXPIRATION_DATE ===
        exp_aliases = ['expiration', 'expiry', 'expires', 'valid_until']
        if normalized.get('expiration_date') is None:
            for alias in exp_aliases:
                if alias in normalized and normalized[alias] is not None:
                    normalized['expiration_date'] = self.normalize_grok_value(normalized[alias], 'date')
                    break
        
        return normalized
    
    def normalize_completed_fields(self, c: Dict) -> Dict:
        """
        Normaliza campos de un completed offering al schema estándar.
        """
        if not isinstance(c, dict):
            return c
        
        normalized = dict(c)
        
        # === SHARES_ISSUED ===
        shares_aliases = ['shares', 'number_of_shares', 'total_shares', 'shares_offered', 'shares_sold']
        if normalized.get('shares_issued') is None:
            for alias in shares_aliases:
                if alias in normalized and normalized[alias] is not None:
                    normalized['shares_issued'] = self.normalize_grok_value(normalized[alias], 'number')
                    break
        
        # === PRICE_PER_SHARE ===
        price_aliases = ['price', 'offering_price', 'share_price', 'per_share']
        if normalized.get('price_per_share') is None:
            for alias in price_aliases:
                if alias in normalized and normalized[alias] is not None:
                    normalized['price_per_share'] = self.normalize_grok_value(normalized[alias], 'number')
                    break
        
        # === AMOUNT_RAISED ===
        amount_aliases = ['amount', 'gross_proceeds', 'proceeds', 'total_raised', 'offering_amount']
        if normalized.get('amount_raised') is None:
            for alias in amount_aliases:
                if alias in normalized and normalized[alias] is not None:
                    normalized['amount_raised'] = self.normalize_grok_value(normalized[alias], 'number')
                    break
        
        # === OFFERING_DATE ===
        date_aliases = ['date', 'closing_date', 'effective_date', 'completion_date']
        if normalized.get('offering_date') is None:
            for alias in date_aliases:
                if alias in normalized and normalized[alias] is not None:
                    normalized['offering_date'] = self.normalize_grok_value(normalized[alias], 'date')
                    break
        
        # === OFFERING_TYPE ===
        type_aliases = ['type', 'offering_name', 'description', 'title']
        if normalized.get('offering_type') is None:
            for alias in type_aliases:
                if alias in normalized and normalized[alias] is not None:
                    normalized['offering_type'] = self.normalize_grok_value(normalized[alias], 'string')
                    break
        
        return normalized
    
    def normalize_s1_fields(self, s: Dict) -> Dict:
        """
        Normaliza campos de un S-1 offering al schema estándar.
        """
        if not isinstance(s, dict):
            return s
        
        normalized = dict(s)
        
        # === S1_FILING_DATE ===
        date_aliases = ['filing_date', 'date', 'effective_date', 'registration_date']
        if normalized.get('s1_filing_date') is None:
            for alias in date_aliases:
                if alias in normalized and normalized[alias] is not None:
                    normalized['s1_filing_date'] = self.normalize_grok_value(normalized[alias], 'date')
                    break
        
        # === DEAL_SIZE ===
        size_aliases = ['deal_size', 'amount', 'offering_amount', 'gross_proceeds', 'total_raised']
        if normalized.get('deal_size') is None:
            for alias in size_aliases:
                if alias in normalized and normalized[alias] is not None:
                    normalized['deal_size'] = self.normalize_grok_value(normalized[alias], 'number')
                    break
        
        # === SHARES_OFFERED ===
        shares_aliases = ['shares_offered', 'shares', 'number_of_shares', 'total_shares']
        if normalized.get('shares_offered') is None:
            for alias in shares_aliases:
                if alias in normalized and normalized[alias] is not None:
                    normalized['shares_offered'] = self.normalize_grok_value(normalized[alias], 'number')
                    break
        
        # === PRICE_RANGE ===
        price_aliases = ['price_range', 'price', 'estimated_price', 'offering_price']
        if normalized.get('price_range') is None:
            for alias in price_aliases:
                if alias in normalized and normalized[alias] is not None:
                    val = normalized[alias]
                    if isinstance(val, (int, float)):
                        normalized['price_range'] = f"${val}"
                    else:
                        normalized['price_range'] = self.normalize_grok_value(val, 'string')
                    break
        
        return normalized
    
    def normalize_convertible_note_fields(self, n: Dict) -> Dict:
        """
        Normaliza campos de un convertible note al schema estándar.
        """
        if not isinstance(n, dict):
            return n
        
        normalized = dict(n)
        
        # === PRINCIPAL_AMOUNT ===
        principal_aliases = ['principal_amount', 'principal', 'amount', 'face_value', 'note_amount']
        if normalized.get('principal_amount') is None:
            for alias in principal_aliases:
                if alias in normalized and normalized[alias] is not None:
                    normalized['principal_amount'] = self.normalize_grok_value(normalized[alias], 'number')
                    break
        
        # === CONVERSION_PRICE ===
        conv_price_aliases = ['conversion_price', 'strike_price', 'price', 'conversion_rate']
        if normalized.get('conversion_price') is None:
            for alias in conv_price_aliases:
                if alias in normalized and normalized[alias] is not None:
                    normalized['conversion_price'] = self.normalize_grok_value(normalized[alias], 'number')
                    break
        
        # === ISSUE_DATE ===
        date_aliases = ['issue_date', 'issuance_date', 'date', 'effective_date']
        if normalized.get('issue_date') is None:
            for alias in date_aliases:
                if alias in normalized and normalized[alias] is not None:
                    normalized['issue_date'] = self.normalize_grok_value(normalized[alias], 'date')
                    break
        
        # === MATURITY_DATE ===
        maturity_aliases = ['maturity_date', 'maturity', 'expiration', 'due_date']
        if normalized.get('maturity_date') is None:
            for alias in maturity_aliases:
                if alias in normalized and normalized[alias] is not None:
                    normalized['maturity_date'] = self.normalize_grok_value(normalized[alias], 'date')
                    break
        
        # === HOLDER ===
        holder_aliases = ['holder', 'investor', 'lender', 'noteholder', 'purchaser']
        if normalized.get('holder') is None:
            for alias in holder_aliases:
                if alias in normalized and normalized[alias] is not None:
                    normalized['holder'] = self.normalize_grok_value(normalized[alias], 'string')
                    break
        
        return normalized
    
    def normalize_convertible_preferred_fields(self, p: Dict) -> Dict:
        """
        Normaliza campos de un convertible preferred al schema estándar.
        """
        if not isinstance(p, dict):
            return p
        
        normalized = dict(p)
        
        # === SERIES ===
        series_aliases = ['series', 'name', 'title', 'designation', 'series_name']
        if normalized.get('series') is None:
            for alias in series_aliases:
                if alias in normalized and normalized[alias] is not None:
                    normalized['series'] = self.normalize_grok_value(normalized[alias], 'string')
                    break
        
        # === TOTAL_DOLLAR_AMOUNT_ISSUED ===
        amount_aliases = [
            'total_dollar_amount_issued', 'amount', 'total_amount', 
            'proceeds', 'gross_proceeds', 'offering_amount'
        ]
        if normalized.get('total_dollar_amount_issued') is None:
            for alias in amount_aliases:
                if alias in normalized and normalized[alias] is not None:
                    normalized['total_dollar_amount_issued'] = self.normalize_grok_value(normalized[alias], 'number')
                    break
        
        # === CONVERSION_PRICE ===
        conv_aliases = ['conversion_price', 'strike_price', 'price', 'conversion_rate']
        if normalized.get('conversion_price') is None:
            for alias in conv_aliases:
                if alias in normalized and normalized[alias] is not None:
                    normalized['conversion_price'] = self.normalize_grok_value(normalized[alias], 'number')
                    break
        
        # === ISSUE_DATE ===
        date_aliases = ['issue_date', 'issuance_date', 'date', 'effective_date']
        if normalized.get('issue_date') is None:
            for alias in date_aliases:
                if alias in normalized and normalized[alias] is not None:
                    normalized['issue_date'] = self.normalize_grok_value(normalized[alias], 'date')
                    break
        
        return normalized
    
    def normalize_equity_line_fields(self, e: Dict) -> Dict:
        """
        Normaliza campos de un equity line al schema estándar.
        """
        if not isinstance(e, dict):
            return e
        
        normalized = dict(e)
        
        # === TOTAL_CAPACITY ===
        capacity_aliases = [
            'total_capacity', 'capacity', 'amount', 'commitment_amount',
            'max_amount', 'facility_size', 'line_amount'
        ]
        if normalized.get('total_capacity') is None:
            for alias in capacity_aliases:
                if alias in normalized and normalized[alias] is not None:
                    normalized['total_capacity'] = self.normalize_grok_value(normalized[alias], 'number')
                    break
        
        # === COUNTERPARTY ===
        counterparty_aliases = ['counterparty', 'investor', 'purchaser', 'buyer', 'provider']
        if normalized.get('counterparty') is None:
            for alias in counterparty_aliases:
                if alias in normalized and normalized[alias] is not None:
                    normalized['counterparty'] = self.normalize_grok_value(normalized[alias], 'string')
                    break
        
        # === AGREEMENT_START_DATE ===
        date_aliases = ['agreement_start_date', 'start_date', 'date', 'effective_date', 'execution_date']
        if normalized.get('agreement_start_date') is None:
            for alias in date_aliases:
                if alias in normalized and normalized[alias] is not None:
                    normalized['agreement_start_date'] = self.normalize_grok_value(normalized[alias], 'date')
                    break
        
        # === AGREEMENT_END_DATE ===
        end_aliases = ['agreement_end_date', 'end_date', 'expiration', 'termination_date']
        if normalized.get('agreement_end_date') is None:
            for alias in end_aliases:
                if alias in normalized and normalized[alias] is not None:
                    normalized['agreement_end_date'] = self.normalize_grok_value(normalized[alias], 'date')
                    break
        
        return normalized


# Singleton instance for convenience
_normalizers = GrokNormalizers()

# Export functions for direct use
to_hashable = _normalizers.to_hashable
normalize_grok_value = _normalizers.normalize_grok_value
safe_get_for_key = _normalizers.safe_get_for_key
normalize_grok_extraction_fields = _normalizers.normalize_grok_extraction_fields
normalize_warrant_fields = _normalizers.normalize_warrant_fields
normalize_atm_fields = _normalizers.normalize_atm_fields
normalize_shelf_fields = _normalizers.normalize_shelf_fields
normalize_completed_fields = _normalizers.normalize_completed_fields
normalize_s1_fields = _normalizers.normalize_s1_fields
normalize_convertible_note_fields = _normalizers.normalize_convertible_note_fields
normalize_convertible_preferred_fields = _normalizers.normalize_convertible_preferred_fields
normalize_equity_line_fields = _normalizers.normalize_equity_line_fields

