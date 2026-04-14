"""
Central LLM factory — provider-agnostic.

Priority order:
  1. Google Gemini   — if GOOGLE_API_KEY is set
  2. xAI Grok        — if XAI_API_KEY is set (OpenAI-compatible)

All agents should import `make_llm` from here instead of directly
instantiating ChatGoogleGenerativeAI.

Usage:
    llm = make_llm()                   # fast Flash / Grok mini
    llm = make_llm(tier="pro")        # slower but more capable
    llm = make_llm(max_tokens=2048)   # override output limit
"""
from __future__ import annotations
import os
import logging
from typing import Any

logger = logging.getLogger(__name__)

# Model names per tier per provider
_MODELS = {
    "google": {
        "fast": "gemini-2.0-flash",
        "pro": "gemini-2.5-pro",
    },
    "xai": {
        "fast": "grok-3-mini",
        "pro": "grok-3",
    },
}


def make_llm(
    tier: str = "fast",
    temperature: float = 0.0,
    max_tokens: int = 4096,
    **kwargs: Any,
) -> Any:
    """
    Return a LangChain ChatModel instance using the best available provider.

    Args:
        tier:         "fast" (default) or "pro"
        temperature:  Sampling temperature (0.0 = deterministic)
        max_tokens:   Max output tokens
        **kwargs:     Extra kwargs forwarded to the model constructor

    Returns:
        LangChain ChatModel (ChatGoogleGenerativeAI or ChatOpenAI)

    Raises:
        RuntimeError if no API key is configured.
    """
    google_key = os.getenv("GOOGLE_API_KEY", "").strip()
    xai_key = os.getenv("XAI_API_KEY", "").strip()

    if google_key:
        from langchain_google_genai import ChatGoogleGenerativeAI
        model_name = _MODELS["google"].get(tier, _MODELS["google"]["fast"])
        logger.debug("llm_provider=google model=%s", model_name)
        return ChatGoogleGenerativeAI(
            model=model_name,
            temperature=temperature,
            max_output_tokens=max_tokens,
            google_api_key=google_key,
            **kwargs,
        )

    if xai_key:
        from langchain_openai import ChatOpenAI
        model_name = _MODELS["xai"].get(tier, _MODELS["xai"]["fast"])
        logger.debug("llm_provider=xai model=%s", model_name)
        return ChatOpenAI(
            model=model_name,
            base_url="https://api.x.ai/v1",
            api_key=xai_key,
            temperature=temperature,
            max_tokens=max_tokens,
            **kwargs,
        )

    raise RuntimeError(
        "No LLM API key configured. Set GOOGLE_API_KEY (Gemini) or XAI_API_KEY (Grok) "
        "in the environment."
    )
