"""
TradeUL Orchestrator Module

The orchestrator is the brain that coordinates:
1. Receiving user queries
2. Using LLM to decide what data is needed (Function Calling)
3. Fetching data from internal services (Scanner, Polygon, TimescaleDB)
4. Injecting data into the sandbox
5. Asking LLM to generate analysis code
6. Executing code in the sandbox
7. Returning results to the user

This module implements the secure pattern where:
- LLM never has direct access to data sources
- All data is serialized and injected as files
- Code execution is completely isolated
"""

from .request_handler import RequestHandler, AnalysisRequest, AnalysisResult

__all__ = ["RequestHandler", "AnalysisRequest", "AnalysisResult"]

