"""
LLM Classifier for unknown XBRL concepts.

Uses Grok (XAI) to classify XBRL concepts that couldn't be mapped
by cache, regex patterns, or FASB labels.

Key Features:
- Batch classification for efficiency
- Caching of LLM responses
- Confidence scoring
- Human-readable explanations
"""

import os
import asyncio
import json
import logging
from typing import Dict, List, Optional, Tuple
from dataclasses import dataclass

logger = logging.getLogger(__name__)


@dataclass
class LLMClassification:
    """Result of LLM classification."""
    xbrl_concept: str
    canonical_key: str
    confidence: float
    explanation: str
    statement_type: str


# =============================================================================
# PROMPT TEMPLATES
# =============================================================================

SYSTEM_PROMPT = """You are an expert financial analyst and XBRL taxonomy specialist.
Your task is to map XBRL concepts to canonical financial fields.

You have deep knowledge of:
- US-GAAP taxonomy and XBRL standards
- Financial statement structure (Income Statement, Balance Sheet, Cash Flow)
- Industry-specific accounting practices

Always respond in JSON format."""

CLASSIFICATION_PROMPT = """Given the following XBRL concept, map it to the most appropriate canonical field.

XBRL Concept: {concept}
Statement Type: {statement_type}

Available canonical fields for {statement_type} statement:
{available_fields}

Respond with a JSON object:
{{
    "canonical_key": "the_best_matching_field_key",
    "confidence": 0.0 to 1.0,
    "explanation": "Brief explanation of why this mapping makes sense"
}}

If no good match exists, use:
{{
    "canonical_key": "other_nonoperating",
    "confidence": 0.3,
    "explanation": "No direct mapping found - categorized as other"
}}

IMPORTANT:
- Choose the most specific matching field
- Use higher confidence (0.8+) only for clear matches
- Use lower confidence (0.4-0.6) for educated guesses
- Consider common XBRL naming patterns"""

BATCH_PROMPT = """Map each of the following XBRL concepts to the most appropriate canonical field.

Statement Type: {statement_type}

XBRL Concepts to classify:
{concepts}

Available canonical fields:
{available_fields}

Respond with a JSON array:
[
    {{
        "xbrl_concept": "original_concept_name",
        "canonical_key": "matching_field_key",
        "confidence": 0.0 to 1.0,
        "explanation": "Brief explanation"
    }},
    ...
]

IMPORTANT:
- Map each concept to exactly one canonical field
- Use confidence 0.8+ only for clear, obvious matches
- Use confidence 0.4-0.6 for reasonable guesses
- Consider CamelCase patterns (e.g., CostOfGoodsAndServicesSold → cost_of_revenue)"""


# =============================================================================
# CLASSIFIER CLASS
# =============================================================================

class LLMClassifier:
    """
    LLM-based classifier for unknown XBRL concepts.
    
    Uses Grok (XAI) for classification when other methods fail.
    Results are cached to avoid repeated API calls.
    """
    
    def __init__(self, model: str = "grok-2-1212"):
        """
        Initialize classifier.
        
        Args:
            model: Grok model to use (default: grok-2-1212)
        """
        self.model = model
        self._client = None
        self._available = False
        self._initialize_client()
    
    def _initialize_client(self):
        """Initialize Grok client if API key is available."""
        api_key = os.getenv("GROK_API_KEY")
        if api_key:
            try:
                from xai_sdk import Client
                self._client = Client(api_key=api_key, timeout=60)
                self._available = True
                logger.info("LLMClassifier: Grok client initialized")
            except ImportError:
                logger.warning("LLMClassifier: xai_sdk not installed")
            except Exception as e:
                logger.warning(f"LLMClassifier: Failed to initialize Grok ({e})")
        else:
            logger.info("LLMClassifier: No GROK_API_KEY, LLM classification disabled")
    
    @property
    def is_available(self) -> bool:
        """Check if LLM classification is available."""
        return self._available and self._client is not None
    
    def _get_available_fields(self, statement_type: str) -> str:
        """Get formatted list of available canonical fields for a statement type."""
        from .schema import INCOME_STATEMENT_SCHEMA, BALANCE_SHEET_SCHEMA, CASH_FLOW_SCHEMA
        
        if statement_type == "income":
            fields = INCOME_STATEMENT_SCHEMA
        elif statement_type == "balance":
            fields = BALANCE_SHEET_SCHEMA
        elif statement_type == "cashflow":
            fields = CASH_FLOW_SCHEMA
        else:
            fields = INCOME_STATEMENT_SCHEMA  # default
        
        # Format as bullet list
        lines = []
        for f in fields:
            lines.append(f"- {f.key}: {f.label} ({f.section})")
        
        return "\n".join(lines)
    
    async def classify_single(
        self,
        xbrl_concept: str,
        statement_type: str = "income"
    ) -> Optional[LLMClassification]:
        """
        Classify a single XBRL concept.
        
        Args:
            xbrl_concept: XBRL concept name
            statement_type: Statement type (income, balance, cashflow)
            
        Returns:
            LLMClassification or None if classification failed
        """
        if not self.is_available:
            return None
        
        available_fields = self._get_available_fields(statement_type)
        prompt = CLASSIFICATION_PROMPT.format(
            concept=xbrl_concept,
            statement_type=statement_type,
            available_fields=available_fields
        )
        
        try:
            response = await self._call_llm(prompt)
            if response:
                data = json.loads(response)
                return LLMClassification(
                    xbrl_concept=xbrl_concept,
                    canonical_key=data.get("canonical_key", "other_nonoperating"),
                    confidence=min(data.get("confidence", 0.5), 0.8),  # Cap at 0.8 for LLM
                    explanation=data.get("explanation", ""),
                    statement_type=statement_type
                )
        except json.JSONDecodeError as e:
            logger.warning(f"LLM response not valid JSON: {e}")
        except Exception as e:
            logger.warning(f"LLM classification failed: {e}")
        
        return None
    
    async def classify_batch(
        self,
        concepts: List[str],
        statement_type: str = "income"
    ) -> Dict[str, LLMClassification]:
        """
        Classify multiple XBRL concepts in a single LLM call.
        
        More efficient for bulk processing.
        
        Args:
            concepts: List of XBRL concept names
            statement_type: Statement type
            
        Returns:
            Dict mapping concept → LLMClassification
        """
        if not self.is_available or not concepts:
            return {}
        
        # Limit batch size
        batch_size = 20
        if len(concepts) > batch_size:
            # Process in chunks
            results = {}
            for i in range(0, len(concepts), batch_size):
                chunk = concepts[i:i + batch_size]
                chunk_results = await self._classify_batch_internal(chunk, statement_type)
                results.update(chunk_results)
            return results
        
        return await self._classify_batch_internal(concepts, statement_type)
    
    async def _classify_batch_internal(
        self,
        concepts: List[str],
        statement_type: str
    ) -> Dict[str, LLMClassification]:
        """Internal batch classification."""
        available_fields = self._get_available_fields(statement_type)
        concepts_list = "\n".join(f"- {c}" for c in concepts)
        
        prompt = BATCH_PROMPT.format(
            statement_type=statement_type,
            concepts=concepts_list,
            available_fields=available_fields
        )
        
        try:
            response = await self._call_llm(prompt)
            if response:
                # Find JSON array in response
                start = response.find("[")
                end = response.rfind("]") + 1
                if start >= 0 and end > start:
                    json_str = response[start:end]
                    data = json.loads(json_str)
                    
                    results = {}
                    for item in data:
                        xbrl_concept = item.get("xbrl_concept", "")
                        if xbrl_concept:
                            results[xbrl_concept] = LLMClassification(
                                xbrl_concept=xbrl_concept,
                                canonical_key=item.get("canonical_key", "other_nonoperating"),
                                confidence=min(item.get("confidence", 0.5), 0.8),
                                explanation=item.get("explanation", ""),
                                statement_type=statement_type
                            )
                    return results
        except json.JSONDecodeError as e:
            logger.warning(f"Batch LLM response not valid JSON: {e}")
        except Exception as e:
            logger.warning(f"Batch LLM classification failed: {e}")
        
        return {}
    
    async def _call_llm(self, prompt: str) -> Optional[str]:
        """
        Make LLM API call.
        
        Args:
            prompt: User prompt
            
        Returns:
            Response text or None
        """
        if not self._client:
            return None
        
        try:
            # Use asyncio.to_thread for sync client
            response = await asyncio.to_thread(
                self._client.chat.completions.create,
                model=self.model,
                messages=[
                    {"role": "system", "content": SYSTEM_PROMPT},
                    {"role": "user", "content": prompt}
                ],
                temperature=0.2,  # Low temperature for consistency
                max_tokens=2000
            )
            
            if response and response.choices:
                return response.choices[0].message.content
            
        except Exception as e:
            logger.error(f"LLM API call failed: {e}")
        
        return None


# =============================================================================
# SINGLETON INSTANCE
# =============================================================================

_classifier: Optional[LLMClassifier] = None


def get_classifier() -> LLMClassifier:
    """Get singleton classifier instance."""
    global _classifier
    if _classifier is None:
        _classifier = LLMClassifier()
    return _classifier

