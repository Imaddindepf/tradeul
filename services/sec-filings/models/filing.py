"""
Modelos Pydantic para SEC Filings
"""
from datetime import date, datetime, time
from typing import Optional, List, Dict, Any
from pydantic import BaseModel, Field


class EntityInfo(BaseModel):
    """Información de una entidad en el filing"""
    companyName: Optional[str] = None
    cik: Optional[str] = None
    irsNo: Optional[str] = None
    stateOfIncorporation: Optional[str] = None
    fiscalYearEnd: Optional[str] = None
    sic: Optional[str] = None
    type: Optional[str] = None
    act: Optional[str] = None
    fileNo: Optional[str] = None
    filmNo: Optional[str] = None


class DocumentFile(BaseModel):
    """Archivo de documento del filing"""
    sequence: Optional[str] = None
    description: Optional[str] = None
    documentUrl: Optional[str] = None
    type: Optional[str] = None
    size: Optional[str] = None


class DataFile(BaseModel):
    """Archivo de datos XBRL"""
    sequence: Optional[str] = None
    description: Optional[str] = None
    documentUrl: Optional[str] = None
    type: Optional[str] = None
    size: Optional[str] = None


class SeriesClass(BaseModel):
    """Serie y clase/contrato"""
    series: Optional[str] = None
    name: Optional[str] = None
    classesContracts: Optional[List[Dict[str, Any]]] = None


class SECFiling(BaseModel):
    """Modelo completo de un SEC Filing"""
    
    # Identificadores
    id: str
    accessionNo: str = Field(..., alias="accessionNo")
    
    # Metadata básica
    formType: str
    filedAt: datetime
    ticker: Optional[str] = None
    cik: str
    companyName: Optional[str] = None
    companyNameLong: Optional[str] = None
    periodOfReport: Optional[date] = None
    description: Optional[str] = None
    
    # Items y clasificaciones
    items: Optional[List[str]] = None
    groupMembers: Optional[List[str]] = None
    
    # Enlaces
    linkToFilingDetails: Optional[str] = None
    linkToTxt: Optional[str] = None
    linkToHtml: Optional[str] = None
    linkToXbrl: Optional[str] = None
    
    # Fechas especiales
    effectivenessDate: Optional[date] = None
    effectivenessTime: Optional[time] = None
    registrationForm: Optional[str] = None
    referenceAccessionNo: Optional[str] = None
    
    # Datos complejos
    entities: Optional[List[EntityInfo]] = None
    documentFormatFiles: Optional[List[DocumentFile]] = None
    dataFiles: Optional[List[DataFile]] = None
    seriesAndClassesContractsInformation: Optional[List[SeriesClass]] = None
    
    class Config:
        populate_by_name = True
        json_encoders = {
            datetime: lambda v: v.isoformat(),
            date: lambda v: v.isoformat() if v else None,
            time: lambda v: v.isoformat() if v else None,
        }


class FilingResponse(BaseModel):
    """Respuesta de API con filing"""
    filing: SECFiling
    message: Optional[str] = None


class FilingsListResponse(BaseModel):
    """Respuesta de API con lista de filings"""
    filings: List[SECFiling]
    total: int
    page: int
    page_size: int
    message: Optional[str] = None


class FilingFilter(BaseModel):
    """Filtros para búsqueda de filings"""
    ticker: Optional[str] = None
    form_type: Optional[str] = None
    cik: Optional[str] = None
    date_from: Optional[date] = None
    date_to: Optional[date] = None
    items: Optional[List[str]] = None
    page: int = Field(default=1, ge=1)
    page_size: int = Field(default=50, ge=1, le=200)


class StreamStatus(BaseModel):
    """Estado del Stream API"""
    connected: bool
    last_filing_received: Optional[datetime] = None
    total_filings_received: int = 0
    uptime_seconds: float = 0.0
    reconnect_count: int = 0


class BackfillStatus(BaseModel):
    """Estado del backfill histórico"""
    is_running: bool
    total_processed: int = 0
    total_inserted: int = 0
    total_updated: int = 0
    total_errors: int = 0
    current_date: Optional[date] = None
    started_at: Optional[datetime] = None
    completed_at: Optional[datetime] = None

