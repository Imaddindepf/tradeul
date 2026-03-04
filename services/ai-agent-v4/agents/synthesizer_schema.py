"""
Structured output schema for the Synthesizer agent.

Defines the Pydantic models that Gemini 2.5 Flash uses via constrained
decoding (response_schema) to guarantee valid, parseable output.

Architecture: Hybrid JSON structure + markdown content per section.
- Tables arrive as typed JSON arrays (never broken by truncation)
- Text content is short markdown scoped to a single section
- The frontend renders each Section independently
"""
from __future__ import annotations

from pydantic import BaseModel, Field


class MetricsCard(BaseModel):
    """Compact KPI block shown at the top for specific tickers."""
    ticker: str
    company_name: str = ""
    sector: str = ""
    price: str = ""
    change: str = ""
    volume: str = ""
    rvol: str = ""
    rsi: str = ""
    vwap_dist: str = ""
    adx: str = ""
    week52_range: str = ""
    float_shares: str = ""
    market_cap: str = ""


class TableRow(BaseModel):
    """A single row in a data table, represented as label-value pairs."""
    cells: list[str] = Field(default_factory=list)


class DataTable(BaseModel):
    """Structured table data — impossible to break via truncation."""
    headers: list[str] = Field(default_factory=list)
    rows: list[TableRow] = Field(default_factory=list)


class Section(BaseModel):
    """One logical section of the response.

    `content` is short markdown (one section's worth, not a full document).
    `table` is optional structured data that the frontend renders natively.
    `bullets` are key takeaway points rendered as a styled list.
    """
    title: str = ""
    content: str = ""
    table: DataTable | None = None
    bullets: list[str] = Field(default_factory=list)


class Citation(BaseModel):
    """A source reference."""
    title: str = ""
    url: str = ""


class SynthesizerResponse(BaseModel):
    """Top-level structured response from the synthesizer.

    The frontend receives this as JSON and renders each field with
    dedicated UI components — no markdown parsing needed for structure.
    """
    session_context: str = ""
    metrics: MetricsCard | None = None
    sections: list[Section] = Field(default_factory=list)
    citations: list[Citation] = Field(default_factory=list)
    key_takeaways: list[str] = Field(default_factory=list)
