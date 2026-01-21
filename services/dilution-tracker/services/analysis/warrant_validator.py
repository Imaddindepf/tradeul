"""
Warrant Validator
=================
Valida y marca warrants sospechosos que podrían ser falsos positivos.

Reglas de validación:
1. Nombre indica opciones de empleados (no warrants públicos)
2. Sin fecha de emisión/expiración Y sin soporte textual
3. Exercise price parece un año (2020-2030)
4. Cantidad muy pequeña sin contexto legítimo

NOTA: El ratio exercise_price/current_price NO es una buena heurística
porque warrants legítimos antiguos pueden estar deep in-the-money.

La mejor validación es verificar que el precio aparezca en el filing original.
"""

from typing import Dict, List, Tuple, Optional
from decimal import Decimal
from shared.utils.logger import get_logger

logger = get_logger(__name__)


class WarrantValidator:
    """
    Valida warrants y marca los sospechosos.
    """
    
    # Palabras que indican que NO son warrants públicos
    EMPLOYEE_KEYWORDS = [
        'employee', 'stock option', 'rsu', 'restricted stock',
        'incentive', 'compensation', 'esop', 'director', 'officer',
        'performance', 'bonus', 'equity plan', 'stock plan'
    ]
    
    # Nombres típicos de warrants legítimos
    LEGITIMATE_KEYWORDS = [
        'public warrant', 'private warrant', 'underwriter warrant',
        'placement agent', 'series a warrant', 'series b warrant',
        'common warrant', 'penny warrant', 'investor warrant'
    ]
    
    def validate_warrants(
        self, 
        warrants: List[Dict], 
        current_price: float = None,
        ticker: str = ""
    ) -> Tuple[List[Dict], List[Dict]]:
        """
        Valida una lista de warrants y los separa en válidos/sospechosos.
        
        Args:
            warrants: Lista de warrants extraídos
            current_price: Precio actual del stock (para validar exercise price)
            ticker: Ticker para logging
            
        Returns:
            Tuple de (warrants_validados, warrants_sospechosos)
        """
        validated = []
        suspicious = []
        
        for w in warrants:
            issues = self._check_warrant(w, current_price)
            
            if issues:
                # Marcar como sospechoso
                w['_validation_issues'] = issues
                w['_suspicious'] = True
                suspicious.append(w)
                
                logger.warning("warrant_flagged_suspicious",
                             ticker=ticker,
                             series_name=w.get('series_name'),
                             issues=issues,
                             exercise_price=w.get('exercise_price'),
                             outstanding=w.get('outstanding'))
            else:
                w['_suspicious'] = False
                validated.append(w)
        
        if suspicious:
            logger.info("warrant_validation_complete",
                       ticker=ticker,
                       total=len(warrants),
                       valid=len(validated),
                       suspicious=len(suspicious))
        
        return validated, suspicious
    
    def _check_warrant(self, warrant: Dict, current_price: float = None) -> List[str]:
        """
        Verifica un warrant individual y retorna lista de issues.
        """
        issues = []
        
        series_name = (warrant.get('series_name') or '').lower()
        exercise_price = warrant.get('exercise_price')
        outstanding = warrant.get('outstanding')
        issue_date = warrant.get('issue_date')
        expiration_date = warrant.get('expiration_date')
        
        # 1. Verificar si parece opciones de empleados
        if any(kw in series_name for kw in self.EMPLOYEE_KEYWORDS):
            issues.append(f"NAME_SUGGESTS_EMPLOYEE_OPTIONS: '{series_name}'")
        
        # 2. Exercise price analysis
        # APRENDIZAJE: NO penalizar por ratio bajo.
        # Caso ROLR demostró que warrants legítimos pre-IPO pueden tener
        # exercise price muy bajo vs precio actual (ej: $2.37 vs $20).
        # La ÚNICA forma confiable de detectar alucinaciones es verificar
        # que el precio aparezca textualmente en el filing original.
        # 
        # NO añadimos issues por ratio bajo - es una heurística peligrosa.
        
        # 3. Sin fecha de emisión Y sin fecha de expiración
        if not issue_date and not expiration_date:
            issues.append("MISSING_DATES: No issue_date and no expiration_date")
        
        # 4. Cantidad muy pequeña (< 10,000)
        if outstanding and outstanding < 10000:
            issues.append(f"VERY_SMALL_QUANTITY: {outstanding:,} outstanding")
        
        # 5. Cantidad exacta sospechosa (números redondos pequeños)
        if outstanding:
            # Números como 39,172 son sospechosos si no hay contexto
            if outstanding < 50000 and not any(kw in series_name for kw in self.LEGITIMATE_KEYWORDS):
                # Verificar si el nombre es genérico
                if 'existing' in series_name or 'stock purchase' in series_name:
                    issues.append(f"GENERIC_NAME_SMALL_QUANTITY: '{series_name}' with {outstanding:,}")
        
        # 6. Exercise price es un año (error común de extracción)
        if exercise_price:
            try:
                ep = float(exercise_price)
                if 2020 <= ep <= 2030:
                    issues.append(f"EXERCISE_PRICE_LOOKS_LIKE_YEAR: ${exercise_price}")
            except ValueError:
                pass
        
        return issues
    
    def get_confidence_score(self, warrant: Dict, current_price: float = None) -> float:
        """
        Calcula un score de confianza (0.0 - 1.0) para un warrant.
        """
        issues = self._check_warrant(warrant, current_price)
        
        # Base: 1.0
        score = 1.0
        
        # Penalizaciones calibradas
        for issue in issues:
            if 'EMPLOYEE_OPTIONS' in issue:
                score -= 0.5  # Alta: claramente no es warrant público
            elif 'LOOKS_LIKE_YEAR' in issue:
                score -= 0.5  # Alta: error obvio de extracción
            elif 'MISSING_DATES' in issue:
                score -= 0.15  # Moderada: puede ser dato faltante
            elif 'VERY_SMALL_QUANTITY' in issue:
                score -= 0.1  # Baja: puede ser legítimo
            elif 'GENERIC_NAME' in issue:
                score -= 0.1  # Baja: nombre genérico pero puede ser real
            elif 'LOW_PRICE_NO_DATE' in issue:
                score -= 0.2  # Moderada: combinación sospechosa
        
        return max(0.0, min(1.0, score))
    
    def verify_data_in_text(
        self, 
        warrant: Dict, 
        filing_text: str
    ) -> Tuple[bool, float, List[str]]:
        """
        Verifica si los datos del warrant aparecen en el texto del filing.
        Esta es la MEJOR y ÚNICA forma confiable de detectar alucinaciones.
        
        Args:
            warrant: Dict con datos del warrant
            filing_text: Texto del filing original
            
        Returns:
            Tuple de (is_verified, confidence, evidence_found)
        """
        import re
        
        if not filing_text:
            return False, 0.0, []
        
        evidence = []
        checks_passed = 0
        total_checks = 0
        
        # 1. Verificar exercise_price
        exercise_price = warrant.get('exercise_price')
        if exercise_price:
            total_checks += 1
            # Limpiar el precio (remover $, per share, etc)
            price_str = str(exercise_price).replace('$', '').replace(' per share', '').strip()
            try:
                price_num = float(price_str)
                price_formatted = f"{price_num:.2f}"
                
                # Buscar el precio en el texto
                if re.search(rf'\$?\s*{re.escape(price_formatted)}', filing_text, re.IGNORECASE):
                    checks_passed += 1
                    evidence.append(f"Price ${price_formatted} found in text")
            except ValueError:
                pass
        
        # 2. Verificar outstanding/total_issued
        outstanding = warrant.get('outstanding') or warrant.get('total_issued')
        if outstanding:
            total_checks += 1
            # Formatear con y sin comas
            qty_str = f"{outstanding:,}"
            qty_str_no_comma = str(outstanding)
            
            if (re.search(rf'{re.escape(qty_str)}', filing_text) or 
                re.search(rf'{qty_str_no_comma}', filing_text)):
                checks_passed += 1
                evidence.append(f"Quantity {qty_str} found in text")
        
        # 3. Verificar series_name keywords
        series_name = warrant.get('series_name', '')
        if series_name:
            total_checks += 1
            # Extraer palabras clave del nombre
            keywords = [w for w in series_name.lower().split() 
                       if len(w) > 3 and w not in ['warrant', 'warrants', 'common', 'stock']]
            
            if keywords:
                found_keywords = sum(1 for kw in keywords 
                                    if re.search(rf'\b{re.escape(kw)}\b', filing_text, re.IGNORECASE))
                if found_keywords >= len(keywords) // 2:
                    checks_passed += 1
                    evidence.append(f"Keywords from '{series_name}' found")
        
        # Calcular confianza
        if total_checks == 0:
            return False, 0.0, []
        
        confidence = checks_passed / total_checks
        is_verified = confidence >= 0.5  # Al menos 50% de los datos verificados
        
        return is_verified, confidence, evidence


# Función de conveniencia
def validate_and_filter_warrants(
    warrants: List[Dict], 
    current_price: float = None,
    ticker: str = "",
    remove_suspicious: bool = False
) -> List[Dict]:
    """
    Valida warrants y opcionalmente remueve los sospechosos.
    
    Args:
        warrants: Lista de warrants
        current_price: Precio actual
        ticker: Ticker para logging
        remove_suspicious: Si True, remueve warrants sospechosos
        
    Returns:
        Lista de warrants (filtrada si remove_suspicious=True)
    """
    validator = WarrantValidator()
    validated, suspicious = validator.validate_warrants(warrants, current_price, ticker)
    
    if remove_suspicious:
        return validated
    else:
        # Retorna todos pero marcados
        return validated + suspicious
