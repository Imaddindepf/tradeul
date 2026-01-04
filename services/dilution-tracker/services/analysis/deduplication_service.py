"""
Deduplication Service
=====================
Funciones para deduplicar y clasificar instrumentos de dilución.

Este módulo maneja:
- Deduplicación de warrants, ATM, Shelf, completed offerings, etc.
- Clasificación de estados (Active, Expired, Exercised, etc.)
- Merge inteligente de registros duplicados
- Filtrado de registros summary/históricos
"""

import json
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from shared.utils.logger import get_logger

logger = get_logger(__name__)


# ===========================================================================
# HELPER FUNCTIONS (moved from grok_normalizers)
# ===========================================================================

def to_hashable(value: Any) -> Any:
    """Convierte cualquier valor a un tipo hashable para usar en sets/dicts."""
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
        return tuple(to_hashable(item) for item in value)
    return str(value)


def normalize_grok_value(value: Any, expected_type: str = "string") -> Any:
    """Normaliza un valor extrayendo el valor real de estructuras anidadas."""
    if value is None:
        return None
        
    if expected_type == "number" and isinstance(value, (int, float)):
        return value
    if expected_type == "string" and isinstance(value, str):
        return value
    if expected_type == "date" and isinstance(value, str):
        return value
    if expected_type == "any" and isinstance(value, (str, int, float, bool)):
        return value
        
    if isinstance(value, dict):
        value_fields = ['value', 'amount', 'price', 'date', 'count', 'number', 
                       'shares', 'quantity', 'total', 'remaining', 'outstanding']
        
        for field in value_fields:
            if field in value:
                return normalize_grok_value(value[field], expected_type)
        
        if len(value) == 1:
            only_value = list(value.values())[0]
            return normalize_grok_value(only_value, expected_type)
        
        return str(value)
        
    if isinstance(value, list):
        if len(value) == 1:
            return normalize_grok_value(value[0], expected_type)
        elif len(value) == 0:
            return None
        else:
            return normalize_grok_value(value[0], expected_type)
    
    if expected_type == "number":
        try:
            cleaned = str(value).replace('$', '').replace(',', '').replace('%', '').strip()
            return float(cleaned)
        except (ValueError, TypeError):
            return None
    
    return str(value)


def safe_get_for_key(d: Dict, key: str, default: Any = None) -> Any:
    """Obtiene un valor de dict de forma segura."""
    if not isinstance(d, dict):
        return default
    return d.get(key, default)


class DeduplicationService:
    """
    Servicio para deduplicar y clasificar instrumentos de dilución.
    """
    
    # ========================================================================
    # WARRANTS
    # ========================================================================
    
    def extract_warrant_type(self, notes: str = '', warrant_type: str = '', series_name: str = '') -> str:
        """
        Extraer el tipo de warrant para agrupar duplicados.
        
        FIX v4.3: Ahora busca en warrant_type, series_name Y notes (en ese orden de prioridad).
        Antes solo buscaba en notes, lo que causaba duplicados cuando notes estaba vacío.
        
        Tipos reconocidos: Public, Private, SPA, Pre-Funded, Common, Unknown
        """
        # Combinar todas las fuentes de texto
        combined = f"{warrant_type} {series_name} {notes}".lower()
        
        if not combined.strip():
            return "Unknown"
        
        # Orden importa - más específico primero
        if 'pre-funded' in combined or 'prefunded' in combined:
            return "Pre-Funded"
        if 'spa warrant' in combined or 'securities purchase agreement' in combined:
            return "SPA"
        if 'private' in combined or 'pipe' in combined:
            return "Private"
        if 'public' in combined or 'spac' in combined:
            return "Public"
        if 'placement agent' in combined:
            return "Placement-Agent"
        if 'underwriter' in combined:
            return "Underwriter"
        if 'common warrant' in combined or 'common stock warrant' in combined:
            return "Common"
        
        return "Unknown"
    
    def deduplicate_warrants(self, warrants: List[Dict]) -> List[Dict]:
        """
        Deduplicar warrants inteligentemente por TIPO + exercise_price.
        
        ESTRATEGIA:
        1. Extraer tipo de warrant (Public, Private, SPA, Pre-Funded, Common)
        2. Agrupar por (tipo, exercise_price)
        3. Para cada grupo, tomar el registro más COMPLETO (más campos con datos)
        4. Si hay empate, tomar el más reciente por issue_date
        """
        # Paso 1: Normalizar todos los warrants
        for w in warrants:
            outstanding = normalize_grok_value(w.get('outstanding'), 'number')
            potential = normalize_grok_value(w.get('potential_new_shares'), 'number')
            
            if outstanding is None and potential is not None:
                w['outstanding'] = potential
            elif outstanding is not None:
                w['outstanding'] = outstanding
        
        # Paso 2: Agrupar por (tipo, exercise_price)
        # FIX v4.3: Usar warrant_type, series_name Y notes para extraer tipo
        groups = {}
        for w in warrants:
            try:
                notes = normalize_grok_value(w.get('notes'), 'string') or ''
                wt_field = normalize_grok_value(w.get('warrant_type'), 'string') or ''
                series_name = normalize_grok_value(w.get('series_name'), 'string') or ''
                warrant_type = self.extract_warrant_type(notes, wt_field, series_name)
                exercise_price = safe_get_for_key(w, 'exercise_price', 'number')
                
                # Normalizar precio a 2 decimales para evitar duplicados por precisión
                try:
                    if exercise_price is not None:
                        exercise_price = round(float(exercise_price), 2)
                except (ValueError, TypeError):
                    pass
                
                key = (warrant_type, exercise_price)
                
                if key not in groups:
                    groups[key] = []
                groups[key].append(w)
            except Exception as e:
                logger.warning("warrant_grouping_error", error=str(e))
        
        # Paso 3: Para cada grupo, seleccionar el mejor registro
        unique = []
        for (warrant_type, exercise_price), group in groups.items():
            if len(group) == 1:
                best = group[0]
            else:
                def completeness_score(w):
                    score = 0
                    if w.get('outstanding'):
                        score += 3
                    if w.get('exercise_price'):
                        score += 2
                    if w.get('expiration_date'):
                        score += 2
                    if w.get('issue_date'):
                        score += 1
                    if w.get('potential_new_shares'):
                        score += 1
                    return score
                
                def sort_key(w):
                    score = completeness_score(w)
                    issue_date = safe_get_for_key(w, 'issue_date', 'date') or ''
                    return (score, str(issue_date))
                
                sorted_group = sorted(group, key=sort_key, reverse=True)
                best = sorted_group[0]
                
                if len(group) > 2:
                    logger.info("warrant_dedup_merged",
                               warrant_type=warrant_type,
                               exercise_price=str(exercise_price),
                               merged_count=len(group),
                               selected_outstanding=best.get('outstanding'))
            
            unique.append(best)
        
        logger.info("warrant_dedup_result",
                   input_count=len(warrants),
                   output_count=len(unique),
                   types_found=list(set(self.extract_warrant_type(
                       normalize_grok_value(w.get('notes'), 'string') or '',
                       normalize_grok_value(w.get('warrant_type'), 'string') or '',
                       normalize_grok_value(w.get('series_name'), 'string') or ''
                   ) for w in unique)))
        
        return unique
    
    def filter_summary_warrants(self, warrants: List[Dict]) -> List[Dict]:
        """
        Filtrar warrants "summary" de 10-Q/10-K para evitar doble conteo.
        
        Los 10-Q/10-K suelen tener tablas resumen tipo "warrants outstanding as of X date"
        que agregan todos los warrants. Estos NO deben sumarse al cálculo de dilución.
        """
        filtered = []
        excluded_count = 0
        
        for w in warrants:
            notes_raw = normalize_grok_value(w.get('notes'), 'string')
            notes_lower = (notes_raw or '').lower()
            
            # Detectar si es un resumen agregado
            is_summary = (
                ('as of' in notes_lower and 
                ('outstanding warrants' in notes_lower or 
                 'weighted average' in notes_lower or
                  'total outstanding' in notes_lower or
                  'aggregate' in notes_lower)) or
                'no specific series' in notes_lower
            )
            
            # Detectar eventos históricos (no warrants activos)
            is_historical = (
                'cashless exercise' in notes_lower or
                'exercised' in notes_lower.split()[-10:] or
                'adjustment' in notes_lower or
                'restructuring' in notes_lower or
                'waiver' in notes_lower or
                'amended' in notes_lower and 'exercise price' not in notes_lower
            )
            
            if is_summary or is_historical:
                w['is_summary_row'] = True
                w['exclude_from_dilution'] = True
                excluded_count += 1
                logger.debug("warrant_excluded", 
                           reason="summary" if is_summary else "historical",
                           outstanding=w.get('outstanding'),
                           notes_snippet=notes_lower[:60])
            
            filtered.append(w)
        
        if excluded_count > 0:
            logger.info("warrants_excluded_from_dilution", count=excluded_count)
        
        return filtered
    
    def impute_missing_exercise_prices(self, warrants: List[Dict]) -> List[Dict]:
        """
        Imputar exercise_price faltantes cuando se puede inferir de otros warrants
        de la misma serie (mismo issue_date, expiration_date, y tipo).
        """
        # Agrupar por (issue_date, expiration_date, snippet de notes)
        by_key = {}
        for w in warrants:
            try:
                key = (
                    safe_get_for_key(w, 'issue_date', 'date'),
                    safe_get_for_key(w, 'expiration_date', 'date'),
                    to_hashable((normalize_grok_value(w.get('notes'), 'string') or '')[:60])
                )
                by_key.setdefault(key, []).append(w)
            except Exception as e:
                logger.warning("impute_grouping_error", error=str(e))
                by_key.setdefault(('error', id(w), str(e)[:20]), []).append(w)
        
        imputed_count = 0
        for group in by_key.values():
            try:
                prices = set()
                for w in group:
                    normalized_price = normalize_grok_value(w.get('exercise_price'), 'number')
                    if normalized_price is not None:
                        prices.add(to_hashable(normalized_price))
                
                if len(prices) == 1:
                    price = list(prices)[0]
                    for w in group:
                        if normalize_grok_value(w.get('exercise_price'), 'number') is None:
                            w['exercise_price'] = price
                            if 'imputed_fields' not in w:
                                w['imputed_fields'] = []
                            w['imputed_fields'].append('exercise_price')
                            imputed_count += 1
                            logger.info("exercise_price_imputed",
                                       ticker=w.get('ticker'),
                                       outstanding=w.get('outstanding'),
                                       imputed_price=price,
                                       issue_date=w.get('issue_date'))
            except Exception as e:
                logger.warning("impute_price_error", error=str(e))
        
        if imputed_count > 0:
            logger.info("total_exercise_prices_imputed", count=imputed_count)
        
        return warrants
    
    def classify_warrant_status(self, warrants: List[Dict], ticker: str) -> List[Dict]:
        """
        Clasificar warrants por su estado: Active, Exercised, Replaced, Historical_Summary.
        """
        try:
            return self._classify_warrant_status_impl(warrants, ticker)
        except Exception as e:
            logger.error("warrant_classification_failed", ticker=ticker, error=str(e), 
                        action="returning_unclassified_warrants")
            for w in warrants:
                if 'status' not in w:
                    w['status'] = 'Active'
            return warrants
    
    def _classify_warrant_status_impl(self, warrants: List[Dict], ticker: str) -> List[Dict]:
        """Implementación de clasificación de warrants"""
        # Identificar inducement/replacement deals
        inducement_dates = set()
        replacement_notes_keywords = ['inducement', 'replacement', 'in exchange for', 'existing warrants']
        
        for w in warrants:
            notes_raw = normalize_grok_value(w.get('notes'), 'string')
            notes_lower = (notes_raw or '').lower()
            if any(keyword in notes_lower for keyword in replacement_notes_keywords):
                issue_date = safe_get_for_key(w, 'issue_date', 'date')
                if issue_date:
                    inducement_dates.add(issue_date)
        
        # Clasificar cada warrant
        for w in warrants:
            notes_raw = normalize_grok_value(w.get('notes'), 'string')
            notes_lower = (notes_raw or '').lower()
            
            # 1. Historical Summary (ya detectado)
            if w.get('is_summary_row') or w.get('exclude_from_dilution'):
                w['status'] = 'Historical_Summary'
                continue
            
            # 2. Ejercidos
            exercised_keywords = [
                'exercised', 'fully exercised', 'exercise of',
                'upon exercise', 'warrant exercise'
            ]
            if any(keyword in notes_lower for keyword in exercised_keywords):
                if 'exercise price' not in notes_lower or 'upon exercise' in notes_lower:
                    w['status'] = 'Exercised'
                    continue
            
            # 3. Reemplazados
            issue_date = safe_get_for_key(w, 'issue_date', 'date')
            if issue_date:
                try:
                    later_inducements = [d for d in inducement_dates if str(d) > str(issue_date)]
                except TypeError:
                    later_inducements = []
                
                if later_inducements and not any(keyword in notes_lower for keyword in replacement_notes_keywords):
                    if 'november 2024' in notes_lower or 'series a' in notes_lower:
                        w['status'] = 'Replaced'
                        w['notes'] = (notes_raw or '') + ' [REPLACED by Inducement Warrants]'
                        continue
            
            # 4. Pre-funded con ejercicio mínimo
            exercise_price = normalize_grok_value(w.get('exercise_price'), 'number')
            if exercise_price is not None:
                try:
                    if float(exercise_price) <= 0.01:
                        if 'pre-funded' in notes_lower or 'prefunded' in notes_lower:
                            w['status'] = 'Active'
                            continue
                except (ValueError, TypeError):
                    pass
            
            # 5. Por defecto: Active
            w['status'] = 'Active'
        
        # Log estadísticas
        status_counts = {}
        for w in warrants:
            status = w.get('status', 'Unknown')
            status_counts[status] = status_counts.get(status, 0) + 1
        
        logger.info("warrant_status_classification",
                   ticker=ticker,
                   total=len(warrants),
                   active=status_counts.get('Active', 0),
                   exercised=status_counts.get('Exercised', 0),
                   replaced=status_counts.get('Replaced', 0),
                   historical_summary=status_counts.get('Historical_Summary', 0))
        
        return warrants
    
    def calculate_remaining_warrants(self, warrants: List[Dict]) -> List[Dict]:
        """
        Calculate remaining outstanding for each warrant based on:
        1. 10-Q/10-K exercise updates if available
        2. Fall back to outstanding = remaining if no update data
        """
        if not warrants:
            return warrants
        
        updates = [w for w in warrants if w.get('is_10q_update')]
        originals = [w for w in warrants if not w.get('is_10q_update')]
        
        if not updates:
            for w in originals:
                if w.get('outstanding') and not w.get('remaining'):
                    w['remaining'] = w['outstanding']
            return originals
        
        # Match updates to original warrants by exercise_price
        updates_by_price = {}
        for u in updates:
            price = u.get('exercise_price')
            if price is not None:
                key = str(float(price))
                if key not in updates_by_price:
                    updates_by_price[key] = []
                updates_by_price[key].append(u)
        
        # Apply updates to originals
        for w in originals:
            price = w.get('exercise_price')
            if price is not None:
                key = str(float(price))
                if key in updates_by_price:
                    matching_updates = updates_by_price[key]
                    if matching_updates:
                        latest = max(matching_updates, 
                                    key=lambda x: x.get('issue_date') or '1900-01-01')
                        
                        if latest.get('outstanding') is not None:
                            w['remaining'] = latest['outstanding']
                        if latest.get('exercised_count'):
                            w['exercised'] = w.get('exercised', 0) + latest['exercised_count']
                        if latest.get('expired_count'):
                            w['expired'] = w.get('expired', 0) + latest['expired_count']
                        
                        if w.get('outstanding') and not w.get('total_issued'):
                            w['total_issued'] = w['outstanding']
                        
                        w['last_update_date'] = latest.get('issue_date')
            
            if not w.get('remaining') and w.get('outstanding'):
                w['remaining'] = w['outstanding']
        
        logger.info("remaining_warrants_calculated",
                   originals=len(originals),
                   updates_applied=len([w for w in originals if w.get('exercised') or w.get('expired')]))
        
        return originals
    
    # ========================================================================
    # SHELF REGISTRATIONS
    # ========================================================================
    
    def classify_shelf_status(self, shelfs: List[Dict], ticker: str) -> List[Dict]:
        """
        Clasificar shelf registrations por su estado: Active, Expired, o Resale.
        
        FIX v4.3: Ahora detecta y marca shelfs de RESALE como no dilutivos.
        Un resale shelf permite a shareholders existentes vender sus acciones,
        NO crea nuevas acciones (no es dilutivo).
        """
        now = datetime.now(timezone.utc)
        
        for s in shelfs:
            # Primero verificar si es un resale shelf (no dilutivo)
            series_name = (s.get('series_name') or '').lower()
            notes = (s.get('notes') or '').lower()
            security_type = (s.get('security_type') or '').lower()
            
            # Detectar resale shelfs
            is_resale = (
                'resale' in series_name or
                'resale' in notes or
                'selling stockholder' in notes or
                'selling shareholder' in notes or
                'secondary offering' in notes or
                security_type == 'resale'
            )
            
            if is_resale:
                s['status'] = 'Resale'
                s['is_dilutive'] = False
                s['exclude_from_dilution'] = True
                logger.debug("shelf_marked_resale",
                           ticker=ticker,
                           series_name=s.get('series_name'),
                           reason="Resale shelf - not dilutive")
                continue
            
            # Verificar expiración
            exp_date_str = s.get('expiration_date')
            
            if exp_date_str:
                try:
                    if isinstance(exp_date_str, str):
                        exp_date = datetime.fromisoformat(exp_date_str.replace('Z', '+00:00'))
                    else:
                        exp_date = datetime.combine(exp_date_str, datetime.min.time()).replace(tzinfo=timezone.utc)
                    
                    if exp_date.tzinfo is None:
                        exp_date = exp_date.replace(tzinfo=timezone.utc)
                    
                    if exp_date < now:
                        s['status'] = 'Expired'
                        s['is_dilutive'] = False
                    else:
                        s['status'] = 'Active'
                        s['is_dilutive'] = True
                except Exception as e:
                    logger.warning("shelf_date_parse_failed",
                                 ticker=ticker,
                                 exp_date_str=str(exp_date_str),
                                 error=str(e))
                    s['status'] = 'Active'
                    s['is_dilutive'] = True
            else:
                s['status'] = 'Active'
                s['is_dilutive'] = True
        
        active_count = sum(1 for s in shelfs if s.get('status') == 'Active')
        expired_count = sum(1 for s in shelfs if s.get('status') == 'Expired')
        resale_count = sum(1 for s in shelfs if s.get('status') == 'Resale')
        
        logger.info("shelf_status_classification",
                   ticker=ticker,
                   total=len(shelfs),
                   active=active_count,
                   expired=expired_count,
                   resale=resale_count)
        
        return shelfs
    
    def deduplicate_shelfs(self, shelfs: List[Dict], ticker: str = "") -> List[Dict]:
        """
        Deduplicar shelfs inteligentemente.
        
        ESTRATEGIA:
        1. INCLUIR todos los shelfs (incluso sin capacity - pueden enriquecerse)
        2. Agrupar por registration_statement + effect_date
        3. Para cada grupo, FUSIONAR datos
        """
        if not shelfs:
            return []
        
        shelfs_complete = []
        shelfs_incomplete = []
        
        for s in shelfs:
            remaining = normalize_grok_value(s.get('remaining_capacity'), 'number')
            total = normalize_grok_value(s.get('total_capacity'), 'number')
            reg_stmt = safe_get_for_key(s, 'registration_statement', 'string')
            effect_date = s.get('effect_date') or s.get('filing_date')
            
            if remaining or total:
                s['_has_capacity'] = True
                shelfs_complete.append(s)
            elif reg_stmt or effect_date:
                s['_has_capacity'] = False
                s['_needs_enrichment'] = True
                shelfs_incomplete.append(s)
        
        if shelfs_incomplete:
            logger.info("shelf_needs_enrichment", ticker=ticker, count=len(shelfs_incomplete))
        
        all_shelfs = shelfs_complete + shelfs_incomplete
        
        # Agrupar por registration_statement + effect_date
        groups = {}
        for s in all_shelfs:
            reg_stmt = safe_get_for_key(s, 'registration_statement', 'string') or 'Unknown'
            date_key = str(s.get('effect_date') or s.get('filing_date') or '')[:7]
            group_key = f"{reg_stmt}|{date_key}"
            if group_key not in groups:
                groups[group_key] = []
            groups[group_key].append(s)
        
        # Fusionar grupos
        unique = []
        for group_key, group in groups.items():
            if len(group) == 1:
                unique.append(group[0])
            else:
                merged = self._merge_shelf_records(group)
                unique.append(merged)
                logger.info("shelf_records_merged",
                           ticker=ticker,
                           group_key=group_key,
                           merged_count=len(group))
                
        logger.info("shelf_deduplication", ticker=ticker, total_input=len(shelfs),
                   complete=len(shelfs_complete), incomplete=len(shelfs_incomplete),
                   total_output=len(unique))
        return unique
    
    def _merge_shelf_records(self, records: List[Dict]) -> Dict:
        """Fusionar múltiples registros de Shelf en uno solo."""
        if len(records) == 1:
            return records[0]
        
        def score(s):
            sc = 0
            if s.get('remaining_capacity'):
                sc += 10
            if s.get('total_capacity'):
                sc += 5
            if s.get('expiration_date'):
                sc += 3
            if s.get('registration_statement'):
                sc += 2
            if s.get('filing_date'):
                sc += 1
            return sc
        
        sorted_records = sorted(records, key=score, reverse=True)
        merged = dict(sorted_records[0])
        
        for record in sorted_records[1:]:
            for key, value in record.items():
                if key.startswith('_'):
                    continue
                if merged.get(key) is None and value is not None:
                    merged[key] = value
        
        merged['_merged_from'] = len(records)
        return merged
    
    # ========================================================================
    # ATM OFFERINGS
    # ========================================================================
    
    def classify_atm_status(self, atms: List[Dict], ticker: str) -> List[Dict]:
        """
        Clasificar ATM offerings por su estado: Active, Terminated, Replaced.
        """
        for a in atms:
            existing_status = a.get('status', '').lower()
            
            if 'terminated' in existing_status or 'termination' in existing_status:
                a['status'] = 'Terminated'
            elif 'replaced' in existing_status or 'superseded' in existing_status:
                a['status'] = 'Replaced'
            else:
                a['status'] = 'Active'
        
        status_counts = {}
        for a in atms:
            status = a.get('status', 'Unknown')
            status_counts[status] = status_counts.get(status, 0) + 1
        
        logger.info("atm_status_classification",
                   ticker=ticker,
                   total=len(atms),
                   active=status_counts.get('Active', 0),
                   terminated=status_counts.get('Terminated', 0),
                   replaced=status_counts.get('Replaced', 0))
        
        return atms
    
    def deduplicate_atm(self, atms: List[Dict], ticker: str = "") -> List[Dict]:
        """
        Deduplicar ATM inteligentemente.
        
        ESTRATEGIA:
        1. INCLUIR todos los ATMs (incluso sin capacity - pueden enriquecerse)
        2. Agrupar por placement_agent + agreement_date
        3. Para cada grupo, FUSIONAR datos
        """
        if not atms:
            return []
        
        atms_complete = []
        atms_incomplete = []
        
        for a in atms:
            remaining = normalize_grok_value(a.get('remaining_capacity'), 'number')
            total = normalize_grok_value(a.get('total_capacity'), 'number')
            agent = safe_get_for_key(a, 'placement_agent', 'string')
            date = a.get('agreement_date') or a.get('filing_date')
            
            if remaining or total:
                a['_has_capacity'] = True
                atms_complete.append(a)
            elif agent or date:
                a['_has_capacity'] = False
                a['_needs_enrichment'] = True
                atms_incomplete.append(a)
        
        if atms_incomplete:
            logger.info("atm_needs_enrichment", ticker=ticker, count=len(atms_incomplete))
        
        all_atms = atms_complete + atms_incomplete
        
        # Agrupar por placement_agent + agreement_date
        groups = {}
        for a in all_atms:
            agent = safe_get_for_key(a, 'placement_agent', 'string') or 'Unknown'
            date_key = str(a.get('agreement_date') or a.get('filing_date') or '')[:7]
            group_key = f"{agent}|{date_key}"
            if group_key not in groups:
                groups[group_key] = []
            groups[group_key].append(a)
        
        # Fusionar grupos
        unique = []
        for group_key, group in groups.items():
            if len(group) == 1:
                unique.append(group[0])
            else:
                merged = self._merge_atm_records(group)
                unique.append(merged)
                logger.info("atm_records_merged",
                           ticker=ticker,
                           group_key=group_key,
                           merged_count=len(group))
                
        logger.info("atm_deduplication", ticker=ticker, total_input=len(atms),
                   complete=len(atms_complete), incomplete=len(atms_incomplete),
                   total_output=len(unique))
        return unique
    
    def _merge_atm_records(self, records: List[Dict]) -> Dict:
        """Fusionar múltiples registros de ATM en uno solo."""
        if len(records) == 1:
            return records[0]
        
        def score(a):
            s = 0
            if a.get('remaining_capacity'):
                s += 10
            if a.get('total_capacity'):
                s += 5
            if a.get('placement_agent'):
                s += 2
            if a.get('filing_date'):
                s += 1
            return s
        
        sorted_records = sorted(records, key=score, reverse=True)
        merged = dict(sorted_records[0])
        
        for record in sorted_records[1:]:
            for key, value in record.items():
                if key.startswith('_'):
                    continue
                if merged.get(key) is None and value is not None:
                    merged[key] = value
        
        merged['_merged_from'] = len(records)
        return merged
    
    # ========================================================================
    # COMPLETED OFFERINGS
    # ========================================================================
    
    def deduplicate_completed(self, completed: List[Dict], ticker: str = "") -> List[Dict]:
        """
        Deduplicar completed offerings inteligentemente.
        """
        with_data = []
        without_data = 0
        
        for c in completed:
            shares = normalize_grok_value(c.get('shares_issued'), 'number')
            amount = normalize_grok_value(c.get('amount_raised'), 'number')
            
            if shares or amount:
                with_data.append(c)
            else:
                without_data += 1
        
        if without_data > 0:
            logger.info("completed_filtered_no_data", ticker=ticker, filtered_count=without_data)
        
        seen = set()
        unique = []
        
        for c in with_data:
            try:
                offering_type = safe_get_for_key(c, 'offering_type', 'string') or ''
                offering_date = safe_get_for_key(c, 'offering_date', 'date')
                amount = safe_get_for_key(c, 'amount_raised', 'number')
                shares = safe_get_for_key(c, 'shares_issued', 'number')
                
                key = (offering_type[:30], offering_date, amount or shares)
                
                if key not in seen:
                    seen.add(key)
                    unique.append(c)
            except Exception as e:
                logger.warning("completed_dedup_error", error=str(e))
                unique.append(c)
        
        logger.info("completed_deduplication", ticker=ticker, 
                   input_count=len(completed), output_count=len(unique))
        return unique
    
    # ========================================================================
    # S-1 OFFERINGS
    # ========================================================================
    
    def deduplicate_s1(self, s1_offerings: List[Dict]) -> List[Dict]:
        """
        Deduplicar S-1 offerings por filing_date + deal_size.
        """
        seen = set()
        unique = []
        for s1 in s1_offerings:
            try:
                filing_date = safe_get_for_key(s1, 's1_filing_date', 'date')
                final_size = safe_get_for_key(s1, 'final_deal_size', 'number')
                anticipated_size = safe_get_for_key(s1, 'anticipated_deal_size', 'number')
                deal_size = final_size or anticipated_size
                
                key = (filing_date, deal_size)
                if not filing_date:
                    unique.append(s1)
                elif key not in seen:
                    seen.add(key)
                    unique.append(s1)
            except Exception as e:
                logger.warning("s1_dedup_error", error=str(e))
                unique.append(s1)
        return unique
    
    # ========================================================================
    # CONVERTIBLE NOTES
    # ========================================================================
    
    def deduplicate_convertible_notes(self, notes: List[Dict]) -> List[Dict]:
        """
        Deduplicar convertible notes.
        
        ESTRATEGIA PROFESIONAL:
        1. Filtrar notas con principal <= 0 (no son notas reales)
        2. Agrupar por principal_amount + issue_date (notas con mismo monto/fecha son la misma)
        3. Merge notas del mismo grupo tomando el valor más completo de cada campo
        4. Filtrar notas que son "Incremental" capacity (no emitidas aún)
        
        DilutionTracker muestra notas ACTIVAS, no capacidades futuras.
        """
        if not notes:
            return []
        
        def parse_date_key(date_val) -> str:
            """Extraer YYYY-MM de una fecha para agrupar."""
            if not date_val:
                return 'unknown'
            try:
                if isinstance(date_val, str):
                    return date_val[:7]  # YYYY-MM
                elif hasattr(date_val, 'strftime'):
                    return date_val.strftime('%Y-%m')
            except:
                pass
            return 'unknown'
        
        def normalize_principal(amount) -> str:
            """Normalizar monto a bucket (para agrupar montos similares)."""
            try:
                val = float(amount or 0)
                if val <= 0:
                    return '0'
                # Round to nearest 10K for bucketing
                bucket = round(val / 10000) * 10000
                return str(int(bucket))
            except:
                return '0'
        
        def calculate_completeness(n: Dict) -> int:
            """Calcular score de completitud de una nota."""
            score = 0
            # Campos críticos (más peso)
            if n.get('total_principal_amount'):
                try:
                    if float(n.get('total_principal_amount', 0)) > 0:
                        score += 10
                except:
                    pass
            if n.get('conversion_price'):
                try:
                    if float(n.get('conversion_price', 0)) > 0:
                        score += 10
                except:
                    pass
            if n.get('issue_date'):
                score += 5
            if n.get('maturity_date'):
                score += 5
            # Campos adicionales
            if n.get('known_owners'):
                score += 3
            if n.get('price_protection'):
                score += 3
            if n.get('pp_clause'):
                score += 2
            if n.get('interest_rate'):
                score += 2
            # Bonus for non-generic series_name
            series = str(n.get('series_name', '')).lower()
            if series and 'unnamed' not in series and 'unknown' not in series:
                score += 2
            return score
        
        def get_dedup_key(n: Dict) -> str:
            """Generar clave basada en principal + issue_date."""
            principal_key = normalize_principal(n.get('total_principal_amount'))
            issue_key = parse_date_key(n.get('issue_date'))
            return f"{principal_key}_{issue_key}"
        
        def merge_notes(group: List[Dict]) -> Dict:
            """Fusionar notas del mismo grupo, seleccionando la más completa."""
            if len(group) == 1:
                return group[0].copy()
            
            # Ordenar por completitud (mayor primero)
            sorted_group = sorted(group, key=calculate_completeness, reverse=True)
            best = sorted_group[0].copy()
            
            # Fusionar campos de las otras notas
            for n in sorted_group[1:]:
                for field in ['known_owners', 'price_protection', 'pp_clause', 
                              'floor_price', 'is_toxic', 'variable_rate_adjustment',
                              'underwriter_agent', 'interest_rate', 'conversion_price',
                              'total_principal_amount', 'remaining_principal_amount',
                              'series_name', 'maturity_date', 'convertible_date']:
                    best_val = best.get(field)
                    n_val = n.get(field)
                    # Para números, preferir > 0
                    if field in ['conversion_price', 'total_principal_amount', 'remaining_principal_amount',
                                 'floor_price', 'interest_rate']:
                        try:
                            if (not best_val or float(best_val) <= 0) and n_val and float(n_val) > 0:
                                best[field] = n_val
                        except:
                            pass
                    # Para fechas, preferir no vacío
                    elif field in ['maturity_date', 'convertible_date']:
                        if not best_val and n_val:
                            best[field] = n_val
                    # Para strings, preferir no vacío y más largo
                    elif not best_val and n_val:
                        best[field] = n_val
                    elif best_val and n_val and len(str(n_val)) > len(str(best_val)):
                        best[field] = n_val
            
            return best
        
        def is_incremental_capacity(n: Dict) -> bool:
            """Detectar si es capacidad incremental (no emitida aún)."""
            series = str(n.get('series_name', '')).lower()
            notes_text = str(n.get('notes', '')).lower()
            
            # Incremental = capacity, not issued yet
            if 'incremental' in series or 'incremental' in notes_text:
                # Check if no issue_date (not issued yet)
                if not n.get('issue_date'):
                    return True
            
            return False
        
        # PASO 1: Filtrar notas inválidas
        valid_notes = []
        filtered_reasons = {'zero_principal': 0, 'incremental': 0}
        
        for n in notes:
            principal = normalize_grok_value(n.get('total_principal_amount'), 'number') or 0
            
            if principal <= 0:
                logger.debug("note_filtered_zero_principal", 
                           series=n.get('series_name'))
                filtered_reasons['zero_principal'] += 1
                continue
            
            # Filter out incremental capacity (not issued yet)
            if is_incremental_capacity(n):
                logger.debug("note_filtered_incremental", 
                           series=n.get('series_name'),
                           principal=principal)
                filtered_reasons['incremental'] += 1
                continue
            
            valid_notes.append(n)
        
        if len(notes) != len(valid_notes):
            logger.info("convertible_notes_filtered",
                       input=len(notes),
                       valid=len(valid_notes),
                       filtered=len(notes) - len(valid_notes),
                       reasons=filtered_reasons)
        
        # PASO 2: Agrupar por clave
        groups = {}
        for n in valid_notes:
            key = get_dedup_key(n)
            if key not in groups:
                groups[key] = []
            groups[key].append(n)
        
        # PASO 3: Merge cada grupo
        unique = []
        for key, group in groups.items():
            try:
                merged = merge_notes(group)
                unique.append(merged)
                
                if len(group) > 1:
                    logger.info("convertible_notes_merged",
                                key=key,
                               input_count=len(group),
                               selected_principal=merged.get('total_principal_amount'))
            except Exception as e:
                logger.warning("convertible_notes_merge_error", error=str(e))
                unique.extend(group)
        
        logger.info("convertible_notes_dedup_result",
                   input_count=len(notes),
                   output_count=len(unique))
        
        return unique
    
    # ========================================================================
    # CONVERTIBLE PREFERRED
    # ========================================================================
    
    def deduplicate_convertible_preferred(self, preferred: List[Dict]) -> List[Dict]:
        """
        Deduplicar convertible preferred por series + issue_date.
        """
        seen = set()
        unique = []
        for p in preferred:
            try:
                series = safe_get_for_key(p, 'series', 'string')
                issue_date = safe_get_for_key(p, 'issue_date', 'date')
                amount = safe_get_for_key(p, 'total_dollar_amount_issued', 'number')
                
                key = (series, issue_date, amount)
                if not series or not issue_date:
                    unique.append(p)
                elif key not in seen:
                    seen.add(key)
                    unique.append(p)
            except Exception as e:
                logger.warning("convertible_preferred_dedup_error", error=str(e))
                unique.append(p)
        return unique
    
    # ========================================================================
    # EQUITY LINES
    # ========================================================================
    
    def deduplicate_equity_lines(self, equity_lines: List[Dict]) -> List[Dict]:
        """
        Deduplicar equity lines por agreement_start_date + capacity.
        """
        seen = set()
        unique = []
        for el in equity_lines:
            try:
                start_date = safe_get_for_key(el, 'agreement_start_date', 'date')
                capacity = safe_get_for_key(el, 'total_capacity', 'number')
                    
                key = (start_date, capacity)
                if not start_date:
                    unique.append(el)
                if key not in seen:
                    seen.add(key)
                    unique.append(el)
            except Exception as e:
                logger.warning("equity_lines_dedup_error", error=str(e))
                unique.append(el)
        return unique


# Singleton instance for convenience
_dedup_service = DeduplicationService()

# Export functions for direct use
extract_warrant_type = _dedup_service.extract_warrant_type
deduplicate_warrants = _dedup_service.deduplicate_warrants
filter_summary_warrants = _dedup_service.filter_summary_warrants
impute_missing_exercise_prices = _dedup_service.impute_missing_exercise_prices
classify_warrant_status = _dedup_service.classify_warrant_status
calculate_remaining_warrants = _dedup_service.calculate_remaining_warrants
classify_shelf_status = _dedup_service.classify_shelf_status
deduplicate_shelfs = _dedup_service.deduplicate_shelfs
classify_atm_status = _dedup_service.classify_atm_status
deduplicate_atm = _dedup_service.deduplicate_atm
deduplicate_completed = _dedup_service.deduplicate_completed
deduplicate_s1 = _dedup_service.deduplicate_s1
deduplicate_convertible_notes = _dedup_service.deduplicate_convertible_notes
deduplicate_convertible_preferred = _dedup_service.deduplicate_convertible_preferred
deduplicate_equity_lines = _dedup_service.deduplicate_equity_lines

