"""
LLM Dilution Verifier
=====================
Servicio de verificación que usa Gemini 3 Pro y Grok 4 con búsqueda en internet
para validar y enriquecer datos de dilución extraídos de SEC filings.

Funcionalidades:
- Verificación cruzada de warrants, convertibles, ATMs
- Detección de datos faltantes
- Validación de ajustes por reverse splits
- Confirmación de ratings de riesgo
"""

import os
import asyncio
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Any, Tuple
from dataclasses import dataclass, field
from enum import Enum
import json

from shared.utils.logger import get_logger

logger = get_logger(__name__)


class VerificationStatus(Enum):
    """Estado de verificación de un dato"""
    CONFIRMED = "confirmed"           # ✅ Confirmado por ambos LLMs
    PARTIALLY_CONFIRMED = "partial"   # ⚠️ Confirmado por un LLM
    NOT_FOUND = "not_found"          # ❓ No encontrado
    DISCREPANCY = "discrepancy"      # ❌ Discrepancia entre LLMs
    MISSING = "missing"              # 🔴 Dato faltante detectado
    CORRECTED = "corrected"          # 🔧 Dato corregido


@dataclass
class VerifiedWarrant:
    """Warrant verificado con metadatos de verificación"""
    series_name: str
    outstanding: Optional[int] = None
    exercise_price: Optional[float] = None
    expiration_date: Optional[str] = None
    issue_date: Optional[str] = None
    status: VerificationStatus = VerificationStatus.NOT_FOUND
    confidence: float = 0.0
    sources: List[str] = field(default_factory=list)
    notes: str = ""
    is_new: bool = False  # True si fue detectado por LLM pero no estaba en datos originales
    original_data: Optional[Dict] = None
    corrections: Optional[Dict] = None


@dataclass
class VerificationResult:
    """Resultado completo de verificación"""
    ticker: str
    verified_at: datetime
    
    # LLM responses
    gemini_response: Optional[str] = None
    grok_response: Optional[str] = None
    
    # Verificaciones
    reverse_split: Optional[Dict] = None
    warrants_verified: List[VerifiedWarrant] = field(default_factory=list)
    warrants_missing: List[VerifiedWarrant] = field(default_factory=list)
    convertibles_verified: List[Dict] = field(default_factory=list)
    
    # Scores
    overall_confidence: float = 0.0
    data_completeness: float = 0.0
    
    # Resumen
    summary: str = ""
    discrepancies: List[str] = field(default_factory=list)
    recommendations: List[str] = field(default_factory=list)
    
    # Raw data
    original_profile: Optional[Dict] = None
    
    def to_dict(self) -> Dict:
        return {
            "ticker": self.ticker,
            "verified_at": self.verified_at.isoformat(),
            "overall_confidence": self.overall_confidence,
            "data_completeness": self.data_completeness,
            "reverse_split": self.reverse_split,
            "warrants_verified": [
                {
                    "series_name": w.series_name,
                    "outstanding": w.outstanding,
                    "exercise_price": w.exercise_price,
                    "status": w.status.value,
                    "confidence": w.confidence,
                    "sources": w.sources,
                    "is_new": w.is_new,
                    "corrections": w.corrections
                }
                for w in self.warrants_verified
            ],
            "warrants_missing": [
                {
                    "series_name": w.series_name,
                    "outstanding": w.outstanding,
                    "exercise_price": w.exercise_price,
                    "sources": w.sources
                }
                for w in self.warrants_missing
            ],
            "summary": self.summary,
            "discrepancies": self.discrepancies,
            "recommendations": self.recommendations
        }


class LLMDilutionVerifier:
    """
    Servicio de verificación de datos de dilución usando LLMs con búsqueda web.
    
    Usa Gemini 3 Pro y Grok 4 en paralelo para:
    1. Verificar warrants, convertibles, ATMs extraídos
    2. Detectar datos faltantes
    3. Validar ajustes por reverse splits
    4. Confirmar ratings de riesgo
    """
    
    def __init__(self):
        self.google_api_key = os.getenv("GOOGLE_API_KEY")
        self.grok_api_key = os.getenv("GROK_API_KEY_2") or os.getenv("GROK_API_KEY")
        
        # Cache de verificaciones recientes (evitar llamadas duplicadas)
        self._cache: Dict[str, Tuple[VerificationResult, datetime]] = {}
        self._cache_ttl = timedelta(hours=6)
    
    def _build_verification_prompt(
        self,
        ticker: str,
        company_name: str,
        warrants: List[Dict],
        convertibles: List[Dict],
        atms: List[Dict],
        shelfs: List[Dict],
        shares_outstanding: int,
        current_price: float
    ) -> str:
        """Construye el prompt de verificación para los LLMs"""
        
        today = datetime.now().strftime("%d de %B de %Y")
        
        # Formatear warrants existentes
        warrants_text = ""
        if warrants:
            warrants_text = "\n".join([
                f"  - {w.get('series_name', 'Unknown')}: {w.get('outstanding', '?')} warrants @ ${w.get('exercise_price', '?')}"
                for w in warrants[:10]
            ])
        else:
            warrants_text = "  (Ninguno extraído)"
        
        prompt = f"""Eres un analista financiero forense especializado en dilución. Hoy es {today}.

## TAREA: VERIFICAR DATOS DE DILUCIÓN DE {ticker} ({company_name})

BUSCA EN INTERNET (SEC EDGAR, comunicados de prensa, news financieras) y VERIFICA estos datos:

### DATOS ACTUALES EXTRAÍDOS:
- Ticker: {ticker}
- Shares Outstanding: {shares_outstanding:,}
- Precio Actual: ${current_price:.2f}

### WARRANTS EXTRAÍDOS (a verificar):
{warrants_text}

### PREGUNTAS DE VERIFICACIÓN:

1. **REVERSE SPLIT RECIENTE** (últimos 24 meses):
   - ¿Hubo algún reverse split?
   - Fecha exacta y ratio (ej: 1:10)
   - ¿Los precios de warrants están ajustados correctamente?

2. **WARRANTS FALTANTES**:
   - ¿Hay warrants emitidos en los últimos 6 meses que NO están en la lista?
   - Especialmente buscar: 8-K recientes con emisión de warrants, term loans con warrants

3. **VERIFICAR CADA WARRANT LISTADO**:
   - ¿El número de warrants outstanding es correcto?
   - ¿El precio de ejercicio es correcto (post-split si aplica)?
   - ¿Está activo o ya expiró/se ejerció?

4. **FINANCIAMIENTOS RECIENTES** (últimos 90 días):
   - ¿Hay nuevos préstamos, offerings, o warrants emitidos?
   - ¿Hay 6-K/8-K recientes con dilución?

5. **NASDAQ/DELISTING**:
   - ¿Hay notificaciones de delisting activas?

### FORMATO DE RESPUESTA (JSON):
```json
{{
  "reverse_split": {{
    "found": true/false,
    "date": "YYYY-MM-DD",
    "ratio": "1:10",
    "prices_need_adjustment": true/false
  }},
  "warrants_verified": [
    {{
      "series_name": "nombre",
      "outstanding": 1234567,
      "exercise_price": 0.78,
      "status": "confirmed/corrected/not_found",
      "correction": "explicación si hay corrección",
      "source": "URL o filing"
    }}
  ],
  "warrants_missing": [
    {{
      "series_name": "nombre detectado",
      "outstanding": 1234567,
      "exercise_price": 0.78,
      "issue_date": "YYYY-MM-DD",
      "source": "URL o filing"
    }}
  ],
  "recent_financings": [
    {{
      "date": "YYYY-MM-DD",
      "type": "8-K/6-K/PR",
      "description": "descripción",
      "dilution_impact": "descripción del impacto"
    }}
  ],
  "delisting_risk": {{
    "active_notice": true/false,
    "deadline": "YYYY-MM-DD o null",
    "details": "explicación"
  }},
  "confidence_score": 0.85,
  "summary": "Resumen ejecutivo de 2-3 oraciones"
}}
```

⚠️ IMPORTANTE:
- NO inventes datos. Si no encuentras algo, marca status como "not_found"
- Incluye URLs de fuentes cuando sea posible
- Si detectas warrants que NO están en la lista, añádelos a "warrants_missing"
"""
        return prompt
    
    async def _query_gemini(self, prompt: str) -> Optional[Dict]:
        """Consulta Gemini 3 Pro con Google Search grounding"""
        if not self.google_api_key:
            logger.warning("gemini_api_key_not_configured")
            return None
        
        try:
            from google import genai
            from google.genai import types
            
            client = genai.Client(api_key=self.google_api_key)
            
            response = client.models.generate_content(
                model="gemini-3-pro-preview",
                contents=[types.Content(
                    role="user",
                    parts=[types.Part(text=prompt)]
                )],
                config=types.GenerateContentConfig(
                    temperature=0.1,
                    max_output_tokens=8192,
                    tools=[types.Tool(google_search=types.GoogleSearch())]
                )
            )
            
            text = response.text if response.text else ""
            
            # Intentar extraer JSON de la respuesta
            json_data = self._extract_json(text)
            
            return {
                "raw": text,
                "parsed": json_data,
                "model": "gemini-3-pro-preview"
            }
            
        except Exception as e:
            logger.error("gemini_verification_error", error=str(e))
            return None
    
    async def _query_grok(self, prompt: str) -> Optional[Dict]:
        """Consulta Grok 4 con X.com y Web search"""
        if not self.grok_api_key:
            logger.warning("grok_api_key_not_configured")
            return None
        
        try:
            os.environ['XAI_API_KEY'] = self.grok_api_key
            
            from xai_sdk import Client
            from xai_sdk.chat import user
            from xai_sdk.tools import x_search, web_search
            
            client = Client()
            
            chat = client.chat.create(
                model="grok-4",
                tools=[
                    x_search(from_date=datetime.now() - timedelta(days=365)),
                    web_search()
                ],
                include=["inline_citations"]
            )
            
            chat.append(user(prompt))
            
            content = ""
            for response, chunk in chat.stream():
                if chunk.content:
                    content += chunk.content
            
            # Intentar extraer JSON de la respuesta
            json_data = self._extract_json(content)
            
            return {
                "raw": content,
                "parsed": json_data,
                "model": "grok-4"
            }
            
        except Exception as e:
            logger.error("grok_verification_error", error=str(e))
            return None
    
    def _extract_json(self, text: str) -> Optional[Dict]:
        """Extrae JSON de una respuesta de texto"""
        import re
        
        # Buscar bloques de código JSON
        json_patterns = [
            r'```json\s*(.*?)\s*```',
            r'```\s*(.*?)\s*```',
            r'\{[\s\S]*"warrants_verified"[\s\S]*\}'
        ]
        
        for pattern in json_patterns:
            matches = re.findall(pattern, text, re.DOTALL)
            for match in matches:
                try:
                    # Limpiar el match
                    clean = match.strip()
                    if not clean.startswith('{'):
                        continue
                    return json.loads(clean)
                except json.JSONDecodeError:
                    continue
        
        # Intentar parsear todo el texto como JSON
        try:
            # Buscar el primer { y último }
            start = text.find('{')
            end = text.rfind('}')
            if start != -1 and end != -1:
                return json.loads(text[start:end+1])
        except json.JSONDecodeError:
            pass
        
        return None
    
    def _merge_results(
        self,
        gemini_result: Optional[Dict],
        grok_result: Optional[Dict],
        original_warrants: List[Dict]
    ) -> Tuple[List[VerifiedWarrant], List[VerifiedWarrant], float]:
        """
        Fusiona resultados de Gemini y Grok para crear verificación combinada.
        
        Returns:
            (warrants_verified, warrants_missing, confidence)
        """
        verified = []
        missing = []
        
        gemini_parsed = gemini_result.get("parsed") if gemini_result else None
        grok_parsed = grok_result.get("parsed") if grok_result else None
        
        # Procesar warrants verificados
        gemini_warrants = (gemini_parsed or {}).get("warrants_verified", [])
        grok_warrants = (grok_parsed or {}).get("warrants_verified", [])
        
        # Crear mapa de warrants originales
        original_map = {
            w.get("series_name", "").lower(): w 
            for w in original_warrants
        }
        
        # Procesar verificaciones de Gemini
        processed_names = set()
        
        for gw in gemini_warrants:
            name = gw.get("series_name", "").lower()
            processed_names.add(name)
            
            # Buscar en Grok
            grok_match = next(
                (w for w in grok_warrants if w.get("series_name", "").lower() == name),
                None
            )
            
            # Determinar status
            if grok_match:
                # Ambos LLMs encontraron el warrant
                status = VerificationStatus.CONFIRMED
                confidence = 0.95
            else:
                # Solo Gemini
                status = VerificationStatus.PARTIALLY_CONFIRMED
                confidence = 0.7
            
            # Verificar si hay corrección
            corrections = None
            original = original_map.get(name)
            if original and gw.get("correction"):
                corrections = {
                    "original_price": original.get("exercise_price"),
                    "corrected_price": gw.get("exercise_price"),
                    "reason": gw.get("correction")
                }
                status = VerificationStatus.CORRECTED
            
            verified.append(VerifiedWarrant(
                series_name=gw.get("series_name", "Unknown"),
                outstanding=gw.get("outstanding"),
                exercise_price=gw.get("exercise_price"),
                status=status,
                confidence=confidence,
                sources=[gw.get("source", "Gemini 3 Pro")],
                original_data=original,
                corrections=corrections
            ))
        
        # Procesar warrants de Grok que no estaban en Gemini
        for gkw in grok_warrants:
            name = gkw.get("series_name", "").lower()
            if name not in processed_names:
                processed_names.add(name)
                verified.append(VerifiedWarrant(
                    series_name=gkw.get("series_name", "Unknown"),
                    outstanding=gkw.get("outstanding"),
                    exercise_price=gkw.get("exercise_price"),
                    status=VerificationStatus.PARTIALLY_CONFIRMED,
                    confidence=0.7,
                    sources=[gkw.get("source", "Grok 4")],
                    original_data=original_map.get(name)
                ))
        
        # Procesar warrants FALTANTES (detectados por LLMs pero no en datos originales)
        gemini_missing = (gemini_parsed or {}).get("warrants_missing", [])
        grok_missing = (grok_parsed or {}).get("warrants_missing", [])
        
        all_missing = gemini_missing + grok_missing
        seen_missing = set()
        
        for mw in all_missing:
            name = mw.get("series_name", "").lower()
            if name in seen_missing:
                continue
            seen_missing.add(name)
            
            # Verificar que no esté en originales
            if name not in original_map:
                missing.append(VerifiedWarrant(
                    series_name=mw.get("series_name", "Unknown"),
                    outstanding=mw.get("outstanding"),
                    exercise_price=mw.get("exercise_price"),
                    issue_date=mw.get("issue_date"),
                    status=VerificationStatus.MISSING,
                    confidence=0.8 if any(m.get("series_name", "").lower() == name for m in gemini_missing) and any(m.get("series_name", "").lower() == name for m in grok_missing) else 0.6,
                    sources=[mw.get("source", "LLM Detection")],
                    is_new=True
                ))
        
        # Calcular confianza general
        if gemini_result and grok_result:
            overall_confidence = 0.9
        elif gemini_result or grok_result:
            overall_confidence = 0.7
        else:
            overall_confidence = 0.0
        
        return verified, missing, overall_confidence
    
    async def verify_dilution_profile(
        self,
        ticker: str,
        company_name: str,
        warrants: List[Dict],
        convertibles: List[Dict] = None,
        atms: List[Dict] = None,
        shelfs: List[Dict] = None,
        shares_outstanding: int = 0,
        current_price: float = 0.0,
        force_refresh: bool = False
    ) -> VerificationResult:
        """
        Verifica un perfil de dilución completo usando Gemini 3 Pro y Grok 4.
        
        Args:
            ticker: Símbolo del ticker
            company_name: Nombre de la empresa
            warrants: Lista de warrants extraídos
            convertibles: Lista de convertibles
            atms: Lista de ATMs
            shelfs: Lista de shelf registrations
            shares_outstanding: Acciones en circulación
            current_price: Precio actual
            force_refresh: Forzar nueva verificación (ignorar cache)
        
        Returns:
            VerificationResult con datos verificados y recomendaciones
        """
        logger.info("verification_started", ticker=ticker)
        
        # Check cache
        cache_key = f"{ticker}_{shares_outstanding}_{current_price:.2f}"
        if not force_refresh and cache_key in self._cache:
            cached, cached_at = self._cache[cache_key]
            if datetime.now() - cached_at < self._cache_ttl:
                logger.info("verification_cache_hit", ticker=ticker)
                return cached
        
        # Build prompt
        prompt = self._build_verification_prompt(
            ticker=ticker,
            company_name=company_name,
            warrants=warrants or [],
            convertibles=convertibles or [],
            atms=atms or [],
            shelfs=shelfs or [],
            shares_outstanding=shares_outstanding,
            current_price=current_price
        )
        
        # Query both LLMs in parallel
        logger.info("querying_llms", ticker=ticker)
        gemini_task = self._query_gemini(prompt)
        grok_task = self._query_grok(prompt)
        
        gemini_result, grok_result = await asyncio.gather(
            gemini_task,
            grok_task,
            return_exceptions=True
        )
        
        # Handle exceptions
        if isinstance(gemini_result, Exception):
            logger.error("gemini_exception", error=str(gemini_result))
            gemini_result = None
        if isinstance(grok_result, Exception):
            logger.error("grok_exception", error=str(grok_result))
            grok_result = None
        
        # Merge results
        verified, missing, confidence = self._merge_results(
            gemini_result,
            grok_result,
            warrants or []
        )
        
        # Extract reverse split info
        reverse_split = None
        for result in [gemini_result, grok_result]:
            if result and result.get("parsed"):
                rs = result["parsed"].get("reverse_split")
                if rs and rs.get("found"):
                    reverse_split = rs
                    break
        
        # Build discrepancies and recommendations
        discrepancies = []
        recommendations = []
        
        if missing:
            discrepancies.append(
                f"🔴 {len(missing)} warrant(s) detectados por LLMs pero NO en datos extraídos"
            )
            for m in missing:
                recommendations.append(
                    f"Añadir: {m.series_name} - {m.outstanding:,} warrants @ ${m.exercise_price}" 
                    if m.outstanding and m.exercise_price else f"Investigar: {m.series_name}"
                )
        
        if reverse_split and reverse_split.get("prices_need_adjustment"):
            discrepancies.append(
                f"⚠️ Reverse split {reverse_split.get('ratio')} detectado - verificar ajustes de precios"
            )
        
        # Calculate data completeness
        total_warrants = len(warrants or [])
        verified_count = sum(1 for v in verified if v.status in [VerificationStatus.CONFIRMED, VerificationStatus.CORRECTED])
        data_completeness = (verified_count / total_warrants * 100) if total_warrants > 0 else 0
        
        # Build summary
        summary_parts = []
        if verified:
            confirmed = sum(1 for v in verified if v.status == VerificationStatus.CONFIRMED)
            summary_parts.append(f"✅ {confirmed}/{len(verified)} warrants confirmados")
        if missing:
            summary_parts.append(f"🔴 {len(missing)} warrants faltantes detectados")
        if reverse_split:
            summary_parts.append(f"📊 Split {reverse_split.get('ratio')} en {reverse_split.get('date')}")
        
        summary = " | ".join(summary_parts) if summary_parts else "Verificación completada"
        
        # Create result
        result = VerificationResult(
            ticker=ticker,
            verified_at=datetime.now(),
            gemini_response=gemini_result.get("raw") if gemini_result else None,
            grok_response=grok_result.get("raw") if grok_result else None,
            reverse_split=reverse_split,
            warrants_verified=verified,
            warrants_missing=missing,
            overall_confidence=confidence,
            data_completeness=data_completeness,
            summary=summary,
            discrepancies=discrepancies,
            recommendations=recommendations,
            original_profile={
                "warrants": warrants,
                "shares_outstanding": shares_outstanding,
                "current_price": current_price
            }
        )
        
        # Cache result
        self._cache[cache_key] = (result, datetime.now())
        
        logger.info(
            "verification_completed",
            ticker=ticker,
            confidence=confidence,
            verified_count=len(verified),
            missing_count=len(missing)
        )
        
        return result
    
    async def quick_verify(
        self,
        ticker: str,
        company_name: str,
        warrants_count: int,
        shares_outstanding: int
    ) -> Dict:
        """
        Verificación rápida solo para detectar datos faltantes críticos.
        Usa solo Grok 4 (más rápido) con prompt simplificado.
        """
        if not self.grok_api_key:
            return {"error": "Grok API key not configured"}
        
        prompt = f"""Busca en SEC EDGAR y news los últimos filings de {ticker} ({company_name}).
        
¿Hay NUEVOS warrants emitidos en los últimos 90 días que no están en esta cuenta: {warrants_count} warrants?

Responde en JSON:
{{"new_warrants_found": true/false, "details": "explicación breve", "source": "URL"}}
"""
        
        try:
            result = await self._query_grok(prompt)
            return result.get("parsed") or {"raw": result.get("raw")}
        except Exception as e:
            return {"error": str(e)}


# Singleton
_verifier: Optional[LLMDilutionVerifier] = None

def get_llm_verifier() -> LLMDilutionVerifier:
    """Obtener instancia singleton del verificador"""
    global _verifier
    if _verifier is None:
        _verifier = LLMDilutionVerifier()
    return _verifier
