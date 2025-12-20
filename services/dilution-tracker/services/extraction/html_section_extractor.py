"""
HTML Section Extractor
======================
Funciones para extraer secciones específicas de filings HTML de SEC.

Este módulo extrae:
- Secciones de warrants de 10-Q/10-K
- Secciones de ATM de 10-Q/10-K
- Información de ejercicio de warrants
- Uso de ATM (cantidad vendida)
"""

import asyncio
import json
import re
from typing import Any, Dict, List, Optional

from shared.utils.logger import get_logger

logger = get_logger(__name__)


class HTMLSectionExtractor:
    """
    Extrae secciones específicas de filings HTML de SEC.
    """
    
    def __init__(self, grok_pool: Any = None, grok_api_key: str = None):
        """
        Args:
            grok_pool: Pool de clientes Grok para llamadas paralelas
            grok_api_key: API key de Grok (fallback)
        """
        self._grok_pool = grok_pool
        self.grok_api_key = grok_api_key
    
    def extract_warrant_section(self, html_content: str) -> Optional[str]:
        """
        Extract only the warrant-related section from a 10-Q/10-K filing.
        
        OPTIMIZADO: Usa regex simple primero (rápido), solo usa BeautifulSoup si necesario.
        
        Returns:
            The warrant section text, or None if not found
        """
        if not html_content:
            return None
        
        try:
            content_size = len(html_content)
            
            # SKIP archivos muy grandes (>2MB)
            if content_size > 2_000_000:
                logger.debug("warrant_section_skip_large_file", size_mb=content_size/1_000_000)
                return None
            
            # FAST PATH: Primero verificar si hay "warrant" en el contenido
            if 'warrant' not in html_content.lower():
                return None
            
            # Buscar secciones relevantes con regex simple
            warrant_patterns = [
                r'(?is)<table[^>]*>(?:[^<]*<[^>]*>)*[^<]*warrant[^<]*(?:<[^>]*>[^<]*)*</table>',
                r'(?is)warrant[^<]{0,500}(?:exercised|expired|outstanding)[^<]{0,500}',
            ]
            
            sections = []
            for pattern in warrant_patterns:
                matches = re.findall(pattern, html_content[:500000])  # Solo primeros 500KB
                for match in matches[:3]:  # Máximo 3 matches por patrón
                    if len(match) > 50:
                        sections.append(match)
            
            if sections:
                combined = '\n\n'.join(sections)
                # Solo retornar si tiene keywords de ejercicio
                if any(kw in combined.lower() for kw in ['exercised', 'expired', 'outstanding']):
                    # Limpiar HTML básico
                    clean = re.sub(r'<[^>]+>', ' ', combined)
                    clean = re.sub(r'\s+', ' ', clean).strip()
                    return clean[:20000]
            
            return None
            
        except Exception as e:
            logger.warning("extract_warrant_section_error", error=str(e))
            return None
    
    async def extract_warrant_exercises(
        self, 
        ticker: str, 
        company_name: str, 
        warrant_sections: List[Dict]
    ) -> List[Dict]:
        """
        Extract warrant exercise information from 10-Q/10-K warrant sections.
        
        Args:
            ticker: Stock ticker
            company_name: Company name
            warrant_sections: List of {form_type, filing_date, content} dicts
            
        Returns:
            List of warrant exercise records
        """
        if not warrant_sections:
            return []
        
        if not self._grok_pool and not self.grok_api_key:
            logger.warning("no_grok_client_for_warrant_exercises")
            return []
        
        try:
            from xai_sdk import Client
            from xai_sdk.chat import user, system
            
            # Combine all sections into one prompt
            sections_text = "\n\n".join([
                f"=== {s['form_type']} filed {s['filing_date']} ===\n{s['content'][:5000]}"
                for s in warrant_sections
            ])
            
            prompt = f"""
Analyze these warrant sections from {company_name} ({ticker}) SEC filings and extract EXERCISE information.

{sections_text}

Extract ONLY exercise/expiration events. Return JSON:
{{
  "warrant_updates": [
    {{
      "filing_date": "YYYY-MM-DD",
      "period_end": "YYYY-MM-DD (e.g., 09/30/2024)",
      "warrants_exercised": number or null,
      "warrants_expired": number or null,
      "warrants_outstanding_end": number (outstanding at end of period),
      "exercise_price": number or null,
      "notes": "brief description of the warrant activity"
    }}
  ]
}}

IMPORTANT:
- Focus on CHANGES (exercises, expirations), not just outstanding counts
- If a filing says "X warrants were exercised" - that's what we want
- If it just says "Y warrants outstanding" with no changes, include with exercised=null
- Return empty list if no warrant exercise info found
"""
            
            try:
                if self._grok_pool:
                    client, _, pool_idx = await self._grok_pool.get_client()
                else:
                    client, pool_idx = None, None
                
                if not client:
                    client = Client(api_key=self.grok_api_key)
                
                def _make_request():
                    chat = client.chat.create(model="grok-3-fast", temperature=0.1, max_tokens=2000)
                    chat.append(user(prompt))
                    return chat.sample()
                
                response = await asyncio.get_event_loop().run_in_executor(None, _make_request)
                
                if self._grok_pool and pool_idx is not None:
                    self._grok_pool.release(pool_idx, success=True)
                
                response_text = response.content
                
                # Parse JSON response
                json_match = re.search(r'\{[\s\S]*\}', response_text)
                if json_match:
                    data = json.loads(json_match.group(0))
                    updates = data.get('warrant_updates', [])
                    
                    exercises = []
                    for u in updates:
                        if u.get('warrants_exercised') or u.get('warrants_expired'):
                            exercises.append({
                                'issue_date': u.get('period_end') or u.get('filing_date'),
                                'outstanding': u.get('warrants_outstanding_end'),
                                'exercise_price': u.get('exercise_price'),
                                'notes': f"10-Q Update: {u.get('notes', '')} | Exercised: {u.get('warrants_exercised', 0)} | Expired: {u.get('warrants_expired', 0)}",
                                'status': 'Update',
                                'is_10q_update': True,
                                'exercised_count': u.get('warrants_exercised'),
                                'expired_count': u.get('warrants_expired')
                            })
                    
                    return exercises
                
            except Exception as e:
                logger.warning("extract_warrant_exercises_grok_error", ticker=ticker, error=str(e))
                if self._grok_pool and pool_idx is not None:
                    self._grok_pool.release(pool_idx, success=False, error=str(e))
            
            return []
            
        except Exception as e:
            logger.warning("extract_warrant_exercises_error", ticker=ticker, error=str(e))
            return []
    
    def extract_atm_section(self, html_content: str) -> Optional[str]:
        """
        Extract the ATM-related section from a 10-Q/10-K filing.
        
        Returns:
            The ATM section text, or None if not found
        """
        if not html_content:
            return None
        
        try:
            content_lower = html_content.lower()
            
            # Skip if no ATM-related keywords
            has_atm = any(kw in content_lower for kw in [
                'at-the-market', 'at the market', ' atm ', 'atm program', 
                'sales agreement', 'equity distribution'
            ])
            if not has_atm:
                return None
            
            # Limpiar HTML primero
            clean_text = re.sub(r'<[^>]+>', ' ', html_content)
            clean_text = re.sub(r'\s+', ' ', clean_text)
            
            # Patterns mejorados para encontrar ATM usage
            atm_patterns = [
                # Patrón 1: "sold X shares ... $Y million ... at-the-market"
                r'(?is)(?:sold|issued|sold\s+and\s+issued)[^.]{0,300}(?:\$[\d,\.]+\s*(?:million|M|billion)?)[^.]{0,200}(?:at-the-market|at\s+the\s+market|atm|sales\s+agreement)',
                
                # Patrón 2: "$X million ... under ... ATM"
                r'(?is)\$[\d,\.]+\s*(?:million|M)?[^.]{0,150}(?:under|pursuant|through)[^.]{0,100}(?:at-the-market|at\s+the\s+market|atm)',
                
                # Patrón 3: "ATM program" seguido de montos
                r'(?is)(?:at-the-market|atm)\s*(?:program|offering|agreement|facility)[^.]{0,500}',
                
                # Patrón 4: Sección de "Liquidity" que mencione ATM
                r'(?is)(?:liquidity|capital\s+resources)[^.]{0,2000}(?:at-the-market|at\s+the\s+market|atm)[^.]{0,1000}',
                
                # Patrón 5: Gross proceeds seguido de ATM
                r'(?is)(?:gross\s+proceeds|net\s+proceeds|aggregate\s+proceeds)[^.]{0,300}(?:at-the-market|at\s+the\s+market|atm)',
                
                # Patrón 6: "During the period ... ATM"
                r'(?is)(?:during\s+the\s+(?:three|six|nine|twelve)\s+months)[^.]{0,500}(?:at-the-market|at\s+the\s+market|atm)[^.]{0,300}',
            ]
            
            sections = []
            for pattern in atm_patterns:
                try:
                    matches = re.findall(pattern, clean_text[:2_000_000])
                    for match in matches[:3]:
                        if len(match) > 50:
                            sections.append(match)
                except:
                    continue
            
            if sections:
                combined = '\n\n'.join(set(sections))
                combined = re.sub(r'\s+', ' ', combined).strip()
                
                if len(combined) > 100:
                    logger.debug("atm_section_extracted", length=len(combined))
                    return combined[:20000]
            
            return None
            
        except Exception as e:
            logger.warning("extract_atm_section_error", error=str(e))
            return None
    
    async def extract_atm_usage_from_section(
        self, 
        ticker: str, 
        atm_section: str,
        filing_date: str
    ) -> Optional[float]:
        """
        Extract ATM USAGE amount from a 10-Q section.
        
        CRITICAL: Distinguir entre:
        - USAGE: "we sold shares for gross proceeds of $70M under our ATM" → $70M USADO
        - CAPACITY: "ATM program with capacity of $75M" → $75M TOTAL (NO USAR)
        
        Returns:
            Total ATM usage (amount SOLD) in dollars, or None if not found
        """
        if not atm_section:
            return None
        
        try:
            section_lower = atm_section.lower()
            
            # Frases que indican CAPACIDAD (no queremos capturar)
            capacity_indicators = [
                'capacity of', 'up to $', 'maximum of', 'aggregate offering',
                'may offer', 'may sell', 'pursuant to which we may'
            ]
            
            # Frases que indican USAGE REAL (sí queremos capturar)
            usage_indicators = [
                'we sold', 'we issued', 'sold and issued', 'gross proceeds of',
                'net proceeds of', 'aggregate sales of', 'received proceeds',
                'during the', 'for the period', 'months ended'
            ]
            
            has_usage_context = any(ind in section_lower for ind in usage_indicators)
            
            if not has_usage_context:
                logger.debug("atm_section_no_usage_context", ticker=ticker, 
                            section_preview=atm_section[:200])
                return None
            
            # Patrones específicos para USAGE (no capacity)
            usage_patterns = [
                # "we sold X shares ... for gross proceeds of $Y million"
                r'(?:sold|issued)[^$]{0,100}(?:gross|net|aggregate)\s*proceeds\s*of\s*\$\s*([\d,\.]+)\s*(million|M)?',
                
                # "received proceeds of $Y million from sales"
                r'(?:received|realized)\s*proceeds\s*of\s*\$\s*([\d,\.]+)\s*(million|M)?',
                
                # "aggregate sales of $Y million under"
                r'aggregate\s*sales\s*of\s*\$\s*([\d,\.]+)\s*(million|M)?',
                
                # "$Y million in gross proceeds ... sold under"
                r'\$\s*([\d,\.]+)\s*(million|M)?[^.]{0,50}(?:in\s*)?(?:gross|net)\s*proceeds[^.]{0,100}(?:sold|issued)',
            ]
            
            max_usage = 0
            for pattern in usage_patterns:
                matches = re.findall(pattern, atm_section, re.IGNORECASE)
                for match in matches:
                    try:
                        amount_str = match[0].replace(',', '')
                        amount = float(amount_str)
                        
                        # Apply multiplier
                        multiplier = match[1].lower() if len(match) > 1 and match[1] else ''
                        if multiplier in ['million', 'm']:
                            amount *= 1_000_000
                        elif amount < 1000:  # Likely already in millions
                            amount *= 1_000_000
                        
                        # Sanity check: ATM usage razonable es < $500M
                        if 0 < amount < 500_000_000:
                            if amount > max_usage:
                                max_usage = amount
                                logger.debug("atm_usage_candidate", ticker=ticker, 
                                           amount=amount, pattern=pattern[:50])
                    except:
                        continue
            
            if max_usage > 0:
                logger.info("atm_usage_regex_found", ticker=ticker, amount=max_usage, 
                           filing_date=filing_date)
                return max_usage
            
            # Si no encontramos con regex pero hay contexto de usage, usar Grok
            if has_usage_context:
                logger.debug("atm_usage_trying_grok", ticker=ticker)
                usage = await self.extract_atm_usage_with_grok(ticker, atm_section, filing_date)
                return usage
            
            return None
            
        except Exception as e:
            logger.warning("extract_atm_usage_error", ticker=ticker, error=str(e))
            return None
    
    async def extract_atm_usage_with_grok(
        self, 
        ticker: str, 
        atm_section: str,
        filing_date: str
    ) -> Optional[float]:
        """
        Use Grok to extract ATM usage when regex fails.
        """
        if not self._grok_pool and not self.grok_api_key:
            return None
        
        try:
            from xai_sdk import Client
            from xai_sdk.chat import user, system
            
            prompt = f"""
Analyze this section from a {ticker} SEC filing dated {filing_date} and extract ATM (At-The-Market) usage information.

TEXT:
{atm_section[:5000]}

QUESTION: What is the TOTAL gross proceeds raised under the ATM program mentioned in this text?

Return ONLY a JSON object:
{{
  "atm_gross_proceeds": <number in dollars or null>,
  "period": "<time period covered, e.g., 'nine months ended Sep 30, 2025'>",
  "confidence": "<high/medium/low>"
}}

IMPORTANT:
- Extract the DOLLAR AMOUNT of shares sold under the ATM
- Convert millions to full numbers: "$70.0 million" = 70000000
- If unclear or not found, return null
"""
            
            try:
                if self._grok_pool:
                    client, _, pool_idx = await self._grok_pool.get_client()
                else:
                    client, pool_idx = None, None
                
                if not client:
                    client = Client(api_key=self.grok_api_key, timeout=30)
                
                chat = client.chat.create(model="grok-3-fast", temperature=0)
                chat.append(system("You are a financial data extraction expert. Return ONLY valid JSON."))
                chat.append(user(prompt))
                response = chat.sample()
                
                if self._grok_pool and pool_idx is not None:
                    self._grok_pool.release(pool_idx, success=True)
                
                # Parse response
                json_match = re.search(r'\{[\s\S]*\}', response.content)
                if json_match:
                    data = json.loads(json_match.group(0))
                    proceeds = data.get('atm_gross_proceeds')
                    if proceeds and proceeds > 0:
                        logger.info("atm_usage_grok_found", ticker=ticker, 
                                   amount=proceeds, period=data.get('period'))
                        return float(proceeds)
                
            except Exception as e:
                logger.warning("extract_atm_usage_grok_error", ticker=ticker, error=str(e))
                if self._grok_pool and pool_idx is not None:
                    self._grok_pool.release(pool_idx, success=False, error=str(e))
            
            return None
            
        except Exception as e:
            logger.warning("extract_atm_usage_with_grok_error", ticker=ticker, error=str(e))
            return None


# Singleton instance
_extractor: Optional[HTMLSectionExtractor] = None


def get_html_section_extractor(
    grok_pool: Any = None, 
    grok_api_key: str = None
) -> HTMLSectionExtractor:
    """Get or create HTML section extractor instance"""
    global _extractor
    if _extractor is None:
        _extractor = HTMLSectionExtractor(grok_pool, grok_api_key)
    return _extractor

