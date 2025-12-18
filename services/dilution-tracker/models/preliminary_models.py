"""
Models for Preliminary Analysis Response
"""
from typing import Optional, List, Dict, Any
from pydantic import BaseModel
from datetime import datetime


class PreliminaryWarrants(BaseModel):
    found: bool = False
    total_warrants: Optional[int] = None
    avg_exercise_price: Optional[float] = None
    notes: Optional[str] = None


class PreliminaryATM(BaseModel):
    found: bool = False
    active_atm: bool = False
    total_capacity: Optional[float] = None
    remaining_capacity: Optional[float] = None
    notes: Optional[str] = None


class PreliminaryShelf(BaseModel):
    found: bool = False
    active_shelf: bool = False
    total_amount: Optional[float] = None
    expiration_date: Optional[str] = None
    notes: Optional[str] = None


class PreliminaryConvertibles(BaseModel):
    found: bool = False
    convertible_notes: bool = False
    convertible_preferred: bool = False
    total_principal: Optional[float] = None
    conversion_price: Optional[float] = None
    notes: Optional[str] = None


class PreliminaryOffering(BaseModel):
    date: Optional[str] = None
    type: Optional[str] = None
    shares: Optional[int] = None
    price: Optional[float] = None
    amount_raised: Optional[float] = None
    notes: Optional[str] = None


class PreliminaryShareStructure(BaseModel):
    shares_outstanding: Optional[int] = None
    float: Optional[int] = None
    insider_ownership_pct: Optional[float] = None
    institutional_ownership_pct: Optional[float] = None


class PreliminaryCashPosition(BaseModel):
    last_reported_cash: Optional[float] = None
    last_report_date: Optional[str] = None
    quarterly_burn_rate: Optional[float] = None
    estimated_runway_months: Optional[float] = None
    notes: Optional[str] = None


class PreliminarySource(BaseModel):
    title: Optional[str] = None
    url: Optional[str] = None
    date: Optional[str] = None


class PreliminaryDataQuality(BaseModel):
    completeness: str = "UNKNOWN"
    recency: Optional[str] = None
    reliability: str = "UNKNOWN"
    limitations: Optional[str] = None


class PreliminaryAnalysisMetadata(BaseModel):
    source: str = "grok_web_search"
    is_preliminary: bool = True
    generated_at: str = datetime.now().isoformat()
    mode: str = "full"
    disclaimer: str = "This is a preliminary AI analysis. Full SEC data analysis is in progress."


class PreliminaryAnalysisResponse(BaseModel):
    """
    Response model for preliminary dilution analysis.
    Returned when ticker doesn't exist in cache/DB and we use Grok web search.
    """
    ticker: str
    company_name: Optional[str] = None
    analysis_date: Optional[str] = None
    
    # Risk Assessment
    confidence_level: str = "MEDIUM"
    dilution_risk_score: Optional[int] = None
    dilution_risk_level: str = "UNKNOWN"
    
    # Summary
    executive_summary: Optional[str] = None
    key_findings: List[str] = []
    
    # Detailed Analysis
    warrants: Optional[PreliminaryWarrants] = None
    atm_offerings: Optional[PreliminaryATM] = None
    shelf_registrations: Optional[PreliminaryShelf] = None
    convertibles: Optional[PreliminaryConvertibles] = None
    recent_offerings: List[PreliminaryOffering] = []
    share_structure: Optional[PreliminaryShareStructure] = None
    cash_position: Optional[PreliminaryCashPosition] = None
    
    # Risk Factors
    red_flags: List[str] = []
    positive_factors: List[str] = []
    analyst_opinion: Optional[str] = None
    
    # Sources
    sources: List[PreliminarySource] = []
    data_quality: Optional[PreliminaryDataQuality] = None
    
    # Metadata
    _metadata: Optional[PreliminaryAnalysisMetadata] = None
    
    # Status flags for frontend
    is_preliminary: bool = True
    full_analysis_status: str = "pending"  # pending, in_progress, completed, failed
    full_analysis_progress: int = 0  # 0-100
    estimated_completion_minutes: int = 5
    
    # Error handling
    error: Optional[str] = None
    parse_success: bool = True


class DilutionProfileWithPreliminary(BaseModel):
    """
    Combined response that can contain either:
    - Full SEC analysis (is_preliminary = False)
    - Preliminary AI analysis (is_preliminary = True)
    """
    ticker: str
    is_preliminary: bool
    
    # Si es análisis completo (SEC)
    profile: Optional[Dict[str, Any]] = None
    dilution_analysis: Optional[Dict[str, Any]] = None
    
    # Si es análisis preliminar (AI)
    preliminary_analysis: Optional[PreliminaryAnalysisResponse] = None
    
    # Status del análisis completo en background
    full_analysis_job_id: Optional[str] = None
    full_analysis_status: str = "not_started"  # not_started, queued, in_progress, completed, failed
    full_analysis_progress: int = 0
    
    # Frontend display
    banner_message: Optional[str] = None
    banner_type: str = "info"  # info, warning, success
    
    # Cache info
    cached: bool = False
    cache_age_seconds: Optional[int] = None


# Banner messages for frontend
BANNER_MESSAGES = {
    "analyzing": {
        "message": "🔬 Nuestro equipo está realizando un análisis exhaustivo de los filings SEC para {ticker}. Mientras tanto, aquí tienes un análisis preliminar basado en IA.",
        "type": "info"
    },
    "queued": {
        "message": "📋 Análisis de {ticker} en cola. Posición: {position}. Tiempo estimado: {eta} minutos.",
        "type": "info"
    },
    "in_progress": {
        "message": "⚙️ Procesando filings SEC de {ticker}... {progress}% completado.",
        "type": "info"
    },
    "completed": {
        "message": "✅ ¡Análisis completo disponible! Los datos han sido actualizados con información verificada de SEC.",
        "type": "success"
    },
    "failed": {
        "message": "⚠️ No se pudo completar el análisis SEC para {ticker}. Mostrando análisis preliminar de IA.",
        "type": "warning"
    }
}

