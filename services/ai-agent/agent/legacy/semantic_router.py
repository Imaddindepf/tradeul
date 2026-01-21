"""
Semantic Router for TradeUL AI Agent
====================================

Uses lightweight sentence embeddings to understand query intent,
instead of brittle regex patterns.

This is the 2025 approach: semantic understanding without LLM API calls.

Model: all-MiniLM-L6-v2 (~80MB, ~5ms/query on CPU)

Benefits over regex:
- "last week" = "últimos 7 días" = "semana pasada" = "weekly"
- "premarket" = "pre-market" = "antes de apertura" = "4am-9:30am"
- More robust to typos and natural language variation

Usage:
    router = SemanticRouter()
    hint = router.get_data_hint("top stocks of the week")
    # Returns: 'day_aggs'
"""

import numpy as np
from typing import Dict, List, Optional, Tuple
from functools import lru_cache
import structlog

logger = structlog.get_logger(__name__)

# Lazy import to avoid slow startup
_model = None


def _get_model():
    """Lazy load the sentence transformer model."""
    global _model
    if _model is None:
        try:
            from sentence_transformers import SentenceTransformer
            # all-MiniLM-L6-v2: 80MB, 384 dimensions, ~5ms/query
            _model = SentenceTransformer('all-MiniLM-L6-v2')
            logger.info("Loaded semantic router model", model="all-MiniLM-L6-v2")
        except ImportError:
            logger.warning("sentence-transformers not installed, falling back to regex")
            return None
        except Exception as e:
            logger.error("Failed to load semantic model", error=str(e))
            return None
    return _model


class SemanticRouter:
    """
    Semantic router for query classification using embeddings.
    
    Pre-computes embeddings for known categories and compares
    new queries using cosine similarity.
    """
    
    # Category exemplars - queries that clearly belong to each category
    CATEGORY_EXEMPLARS = {
        'day_aggs': [
            # English
            "top stocks of the week",
            "best performers this week",
            "weekly gainers",
            "monthly top stocks",
            "last 7 days performance",
            "stocks that went up this month",
            "biggest winners of the week",
            "performance over last 30 days",
            "daily changes this week",
            "weekly volume analysis",
            "compare stocks week over week",
            "multi-day trend analysis",
            "gap analysis for the week",
            "stocks with 3 consecutive up days",
            # Spanish
            "mejores acciones de la semana",
            "top semanal",
            "rendimiento mensual",
            "últimos 7 días",
            "acciones de esta semana",
            "ganancias semanales",
            "análisis semanal",
            "últimas dos semanas",
            "tendencia de la semana",
            "desde el lunes",
            "esta semana",
            "el mes pasado",
        ],
        'minute_aggs': [
            # English
            "premarket movers",
            "pre-market top gainers",
            "after hours activity",
            "top stocks between 9:30 and 10:30",
            "hourly performance",
            "intraday analysis",
            "morning session gainers",
            "afternoon movers",
            "by hour today",
            "10am to 2pm performance",
            "first hour of trading",
            "last hour gainers",
            "per hour breakdown",
            "opening bell movers",
            # Spanish
            "premarket",
            "antes de apertura",
            "por franja horaria",
            "análisis intradía",
            "por hora",
            "primera hora de trading",
            "movimientos de la mañana",
            "tarde de trading",
            "after hours",
            "horario extendido",
            "sesión de la mañana",
            "entre las 9 y las 10",
        ],
    }
    
    # Similarity threshold - queries below this go to 'auto'
    SIMILARITY_THRESHOLD = 0.45
    
    def __init__(self):
        """Initialize the semantic router."""
        self._model = None
        self._category_embeddings: Dict[str, np.ndarray] = {}
        self._initialized = False
    
    def _ensure_initialized(self) -> bool:
        """Lazy initialization of model and embeddings."""
        if self._initialized:
            return self._model is not None
        
        self._model = _get_model()
        if self._model is None:
            self._initialized = True
            return False
        
        # Pre-compute embeddings for all category exemplars
        for category, exemplars in self.CATEGORY_EXEMPLARS.items():
            embeddings = self._model.encode(exemplars, normalize_embeddings=True)
            self._category_embeddings[category] = embeddings
            logger.debug(
                "Computed category embeddings",
                category=category,
                num_exemplars=len(exemplars)
            )
        
        self._initialized = True
        return True
    
    @lru_cache(maxsize=1000)
    def get_data_hint(self, query: str) -> str:
        """
        Determine the best data source for a query using semantic similarity.
        
        Args:
            query: The user's natural language query
            
        Returns:
            'day_aggs' - Use daily aggregates (week/month analysis)
            'minute_aggs' - Use minute data (intraday/hourly analysis)
            'auto' - Let the LLM decide (query is ambiguous)
        """
        if not self._ensure_initialized():
            # Model not available, return auto
            return 'auto'
        
        # Encode the query
        query_embedding = self._model.encode(query, normalize_embeddings=True)
        
        best_category = 'auto'
        best_score = self.SIMILARITY_THRESHOLD
        
        for category, exemplar_embeddings in self._category_embeddings.items():
            # Compute similarities with all exemplars
            similarities = np.dot(exemplar_embeddings, query_embedding)
            
            # Take the max similarity (best matching exemplar)
            max_similarity = float(np.max(similarities))
            
            if max_similarity > best_score:
                best_score = max_similarity
                best_category = category
        
        logger.debug(
            "Semantic routing",
            query=query[:50],
            category=best_category,
            confidence=round(best_score, 3)
        )
        
        return best_category
    
    def get_data_hint_with_confidence(self, query: str) -> Tuple[str, float]:
        """
        Get data hint with confidence score.
        
        Returns:
            Tuple of (category, confidence_score)
        """
        if not self._ensure_initialized():
            return ('auto', 0.0)
        
        query_embedding = self._model.encode(query, normalize_embeddings=True)
        
        best_category = 'auto'
        best_score = 0.0
        
        for category, exemplar_embeddings in self._category_embeddings.items():
            similarities = np.dot(exemplar_embeddings, query_embedding)
            max_similarity = float(np.max(similarities))
            
            if max_similarity > best_score:
                best_score = max_similarity
                best_category = category
        
        if best_score < self.SIMILARITY_THRESHOLD:
            return ('auto', best_score)
        
        return (best_category, best_score)
    
    def explain_routing(self, query: str) -> Dict:
        """
        Explain why a query was routed to a specific category.
        
        Useful for debugging and understanding model behavior.
        """
        if not self._ensure_initialized():
            return {"error": "Model not available", "fallback": "auto"}
        
        query_embedding = self._model.encode(query, normalize_embeddings=True)
        
        explanation = {
            "query": query,
            "categories": {}
        }
        
        for category, exemplar_embeddings in self._category_embeddings.items():
            similarities = np.dot(exemplar_embeddings, query_embedding)
            
            # Find top 3 matching exemplars
            top_indices = np.argsort(similarities)[-3:][::-1]
            top_matches = [
                {
                    "exemplar": self.CATEGORY_EXEMPLARS[category][i],
                    "similarity": round(float(similarities[i]), 3)
                }
                for i in top_indices
            ]
            
            explanation["categories"][category] = {
                "max_similarity": round(float(np.max(similarities)), 3),
                "mean_similarity": round(float(np.mean(similarities)), 3),
                "top_matches": top_matches
            }
        
        # Determine final routing
        best_cat = max(
            explanation["categories"].keys(),
            key=lambda c: explanation["categories"][c]["max_similarity"]
        )
        best_score = explanation["categories"][best_cat]["max_similarity"]
        
        explanation["routing"] = {
            "category": best_cat if best_score >= self.SIMILARITY_THRESHOLD else "auto",
            "confidence": best_score,
            "threshold": self.SIMILARITY_THRESHOLD
        }
        
        return explanation


# Global singleton instance
_semantic_router: Optional[SemanticRouter] = None


def get_semantic_router() -> SemanticRouter:
    """Get or create the global semantic router instance."""
    global _semantic_router
    if _semantic_router is None:
        _semantic_router = SemanticRouter()
    return _semantic_router


# Convenience function for direct use
def semantic_route(query: str) -> str:
    """
    Quick semantic routing for a query.
    
    Usage:
        from agent.semantic_router import semantic_route
        hint = semantic_route("top stocks of the week")
        # Returns: 'day_aggs'
    """
    return get_semantic_router().get_data_hint(query)
