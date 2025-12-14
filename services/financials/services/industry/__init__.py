"""
Industry Module - Detección y perfiles de industria.

Incluye:
- IndustryDetector: Sistema 100% data-driven (analiza datos financieros)
- IndustryProfile: Perfiles de campos por industria
"""

from .profiles import (
    get_industry_from_sic,
    get_profile_from_sic,
    get_profile_by_name,
    SIC_TO_INDUSTRY,
)

from .detector import (
    IndustryDetector,
    IndustryDetectionResult,
    detect_industry,
    get_industry_detector,
    detect_from_financial_data,
)

__all__ = [
    # Legacy profiles
    "get_industry_from_sic",
    "get_profile_from_sic",
    "get_profile_by_name",
    "SIC_TO_INDUSTRY",
    # Data-driven detector
    "IndustryDetector",
    "IndustryDetectionResult",
    "detect_industry",
    "get_industry_detector",
    "detect_from_financial_data",
]
