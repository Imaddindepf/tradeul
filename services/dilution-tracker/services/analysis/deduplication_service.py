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

from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from shared.utils.logger import get_logger
from services.grok.grok_normalizers import (
    GrokNormalizers,
    normalize_grok_value,
    safe_get_for_key,
    to_hashable,
)

logger = get_logger(__name__)


class DeduplicationService(GrokNormalizers):
    """
    Servicio para deduplicar y clasificar instrumentos de dilución.
    
    Hereda de GrokNormalizers para tener acceso a métodos de normalización.
    """
    
    # ========================================================================
    # WARRANTS
    # ========================================================================
    
    def extract_warrant_type(self, notes: str) -> str:
        """
        Extraer el tipo de warrant de las notes para agrupar duplicados.
        
        Tipos reconocidos: Public, Private, SPA, Pre-Funded, Common, Unknown
        """
        if not notes:
            return "Unknown"
        
        notes_lower = notes.lower()
        
        # Orden importa - más específico primero
        if 'pre-funded' in notes_lower or 'prefunded' in notes_lower:
            return "Pre-Funded"
        if 'spa warrant' in notes_lower or 'securities purchase agreement' in notes_lower:
            return "SPA"
        if 'private' in notes_lower:
            return "Private"
        if 'public' in notes_lower:
            return "Public"
        if 'common warrant' in notes_lower or 'common stock warrant' in notes_lower:
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
            outstanding = self.normalize_grok_value(w.get('outstanding'), 'number')
            potential = self.normalize_grok_value(w.get('potential_new_shares'), 'number')
            
            if outstanding is None and potential is not None:
                w['outstanding'] = potential
            elif outstanding is not None:
                w['outstanding'] = outstanding
        
        # Paso 2: Agrupar por (tipo, exercise_price)
        groups = {}
        for w in warrants:
            try:
                notes = self.normalize_grok_value(w.get('notes'), 'string') or ''
                warrant_type = self.extract_warrant_type(notes)
                exercise_price = self.safe_get_for_key(w, 'exercise_price', 'number')
                
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
                    issue_date = self.safe_get_for_key(w, 'issue_date', 'date') or ''
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
                       self.normalize_grok_value(w.get('notes'), 'string') or ''
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
            notes_raw = self.normalize_grok_value(w.get('notes'), 'string')
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
                    self.safe_get_for_key(w, 'issue_date', 'date'),
                    self.safe_get_for_key(w, 'expiration_date', 'date'),
                    self.to_hashable((self.normalize_grok_value(w.get('notes'), 'string') or '')[:60])
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
                    normalized_price = self.normalize_grok_value(w.get('exercise_price'), 'number')
                    if normalized_price is not None:
                        prices.add(self.to_hashable(normalized_price))
                
                if len(prices) == 1:
                    price = list(prices)[0]
                    for w in group:
                        if self.normalize_grok_value(w.get('exercise_price'), 'number') is None:
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
            notes_raw = self.normalize_grok_value(w.get('notes'), 'string')
            notes_lower = (notes_raw or '').lower()
            if any(keyword in notes_lower for keyword in replacement_notes_keywords):
                issue_date = self.safe_get_for_key(w, 'issue_date', 'date')
                if issue_date:
                    inducement_dates.add(issue_date)
        
        # Clasificar cada warrant
        for w in warrants:
            notes_raw = self.normalize_grok_value(w.get('notes'), 'string')
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
            issue_date = self.safe_get_for_key(w, 'issue_date', 'date')
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
            exercise_price = self.normalize_grok_value(w.get('exercise_price'), 'number')
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
        Clasificar shelf registrations por su estado: Active o Expired.
        """
        now = datetime.now(timezone.utc)
        
        for s in shelfs:
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
                    else:
                        s['status'] = 'Active'
                except Exception as e:
                    logger.warning("shelf_date_parse_failed",
                                 ticker=ticker,
                                 exp_date_str=str(exp_date_str),
                                 error=str(e))
                    s['status'] = 'Active'
            else:
                s['status'] = 'Active'
        
        active_count = sum(1 for s in shelfs if s.get('status') == 'Active')
        expired_count = sum(1 for s in shelfs if s.get('status') == 'Expired')
        
        logger.info("shelf_status_classification",
                   ticker=ticker,
                   total=len(shelfs),
                   active=active_count,
                   expired=expired_count)
        
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
            remaining = self.normalize_grok_value(s.get('remaining_capacity'), 'number')
            total = self.normalize_grok_value(s.get('total_capacity'), 'number')
            reg_stmt = self.safe_get_for_key(s, 'registration_statement', 'string')
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
            reg_stmt = self.safe_get_for_key(s, 'registration_statement', 'string') or 'Unknown'
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
            remaining = self.normalize_grok_value(a.get('remaining_capacity'), 'number')
            total = self.normalize_grok_value(a.get('total_capacity'), 'number')
            agent = self.safe_get_for_key(a, 'placement_agent', 'string')
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
            agent = self.safe_get_for_key(a, 'placement_agent', 'string') or 'Unknown'
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
            shares = self.normalize_grok_value(c.get('shares_issued'), 'number')
            amount = self.normalize_grok_value(c.get('amount_raised'), 'number')
            
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
                offering_type = self.safe_get_for_key(c, 'offering_type', 'string') or ''
                offering_date = self.safe_get_for_key(c, 'offering_date', 'date')
                amount = self.safe_get_for_key(c, 'amount_raised', 'number')
                shares = self.safe_get_for_key(c, 'shares_issued', 'number')
                
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
                filing_date = self.safe_get_for_key(s1, 's1_filing_date', 'date')
                final_size = self.safe_get_for_key(s1, 'final_deal_size', 'number')
                anticipated_size = self.safe_get_for_key(s1, 'anticipated_deal_size', 'number')
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
        Deduplicar convertible notes con merge inteligente.
        """
        merged_by_date = {}
        no_date_notes = []
        
        for n in notes:
            try:
                issue_date = self.safe_get_for_key(n, 'issue_date', 'date')
                
                if not issue_date:
                    no_date_notes.append(n)
                    continue
                
                issue_date_key = str(issue_date)
                
                if issue_date_key not in merged_by_date:
                    merged_by_date[issue_date_key] = n.copy()
                else:
                    base = merged_by_date[issue_date_key]
                    
                    for field in [
                        'total_principal_amount', 'remaining_principal_amount',
                        'conversion_price', 'total_shares_when_converted',
                        'remaining_shares_when_converted', 'maturity_date',
                        'convertible_date', 'underwriter_agent', 'filing_url'
                    ]:
                        if base.get(field) is None and n.get(field) is not None:
                            base[field] = n[field]
                    
                    base_notes = self.normalize_grok_value(base.get('notes'), 'string') or ''
                    new_notes = self.normalize_grok_value(n.get('notes'), 'string') or ''
                    if base_notes and new_notes and base_notes != new_notes:
                        combined = ' / '.join([base_notes, new_notes])
                        base['notes'] = combined
                    elif new_notes and not base_notes:
                        base['notes'] = new_notes
                    
                    logger.debug("convertible_notes_merged",
                                issue_date=issue_date_key,
                                base_principal=base.get('total_principal_amount'))
            except Exception as e:
                logger.warning("convertible_notes_dedup_error", error=str(e))
                no_date_notes.append(n)
        
        return list(merged_by_date.values()) + no_date_notes
    
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
                series = self.safe_get_for_key(p, 'series', 'string')
                issue_date = self.safe_get_for_key(p, 'issue_date', 'date')
                amount = self.safe_get_for_key(p, 'total_dollar_amount_issued', 'number')
                
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
                start_date = self.safe_get_for_key(el, 'agreement_start_date', 'date')
                capacity = self.safe_get_for_key(el, 'total_capacity', 'number')
                    
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

