"""
FMP API Endpoints Configuration
Maps all available endpoints (v3 and stable) for optimal data fetching
"""

from typing import Dict, List, Optional
from enum import Enum


class FMPEndpointType(str, Enum):
    """Types of FMP endpoints"""
    SINGLE = "single"      # Single ticker endpoint
    BATCH = "batch"        # Batch/bulk endpoint
    SCREENER = "screener"  # Screener/filter endpoint
    ALL = "all"           # Get all available data


class FMPEndpoints:
    """
    FMP API Endpoint Configuration
    
    Prioritizes batch/bulk endpoints for efficiency
    """
    
    # Base URLs
    BASE_V3 = "https://financialmodelingprep.com/api/v3"
    BASE_V4 = "https://financialmodelingprep.com/api/v4"
    BASE_STABLE = "https://financialmodelingprep.com/stable"
    
    # =============================================
    # BULK/BATCH ENDPOINTS (PREFERRED)
    # =============================================
    
    # All shares float (paginated)
    SHARES_FLOAT_ALL = f"{BASE_STABLE}/shares-float-all"  # ?page=0&limit=1000
    
    # Batch market capitalization
    MARKET_CAP_BATCH = f"{BASE_STABLE}/market-capitalization-batch"
    
    # All available traded stocks
    AVAILABLE_TRADED = f"{BASE_V3}/available-traded/list"
    
    # Stock screener (configurable filters)
    STOCK_SCREENER = f"{BASE_V3}/stock-screener"
    
    # Delisted companies
    DELISTED_COMPANIES = f"{BASE_V3}/delisted-companies"
    
    # =============================================
    # SINGLE TICKER ENDPOINTS (FALLBACK)
    # =============================================
    
    # Company profile
    PROFILE = f"{BASE_V3}/profile/{{symbol}}"
    
    # Quote
    QUOTE = f"{BASE_V3}/quote/{{symbol}}"
    
    # Quote short (faster, less data)
    QUOTE_SHORT = f"{BASE_V3}/quote-short/{{symbol}}"
    
    # Historical price (OHLCV)
    HISTORICAL_PRICE = f"{BASE_V3}/historical-price-full/{{symbol}}"
    
    # Key metrics
    KEY_METRICS = f"{BASE_V3}/key-metrics-ttm/{{symbol}}"
    
    # Financial ratios
    RATIOS = f"{BASE_V3}/ratios-ttm/{{symbol}}"
    
    # Income statement
    INCOME_STATEMENT = f"{BASE_V3}/income-statement/{{symbol}}"
    
    # Balance sheet
    BALANCE_SHEET = f"{BASE_V3}/balance-sheet-statement/{{symbol}}"
    
    # Cash flow
    CASH_FLOW = f"{BASE_V3}/cash-flow-statement/{{symbol}}"
    
    # =============================================
    # BATCH ENDPOINTS (MULTIPLE SYMBOLS)
    # =============================================
    
    # Quote batch (up to 100 symbols)
    QUOTE_BATCH = f"{BASE_V3}/quote"  # ?symbols=AAPL,MSFT,GOOGL
    
    # Profile batch
    PROFILE_BATCH = f"{BASE_V3}/profile"  # ?symbols=AAPL,MSFT,GOOGL
    
    # =============================================
    # MARKET DATA
    # =============================================
    
    # Market status
    MARKET_STATUS = f"{BASE_V3}/market-hours"
    
    # Market holidays
    MARKET_HOLIDAYS = f"{BASE_V3}/market-holidays"
    
    # =============================================
    # HELPER METHODS
    # =============================================
    
    @classmethod
    def get_endpoint(cls, endpoint_name: str, **kwargs) -> str:
        """
        Get endpoint URL with optional formatting
        
        Args:
            endpoint_name: Name of the endpoint (e.g., 'PROFILE', 'QUOTE')
            **kwargs: Format parameters (e.g., symbol='AAPL')
        
        Returns:
            Formatted endpoint URL
        
        Example:
            url = FMPEndpoints.get_endpoint('PROFILE', symbol='AAPL')
        """
        endpoint = getattr(cls, endpoint_name, None)
        if endpoint is None:
            raise ValueError(f"Unknown endpoint: {endpoint_name}")
        
        if kwargs:
            return endpoint.format(**kwargs)
        return endpoint
    
    @classmethod
    def get_batch_quote_url(cls, symbols: List[str]) -> str:
        """
        Get batch quote URL for multiple symbols
        
        Args:
            symbols: List of ticker symbols (max 100)
        
        Returns:
            URL with symbols parameter
        """
        if len(symbols) > 100:
            raise ValueError("Maximum 100 symbols allowed per batch request")
        
        symbols_str = ",".join(symbols)
        return f"{cls.QUOTE_BATCH}?symbols={symbols_str}"
    
    @classmethod
    def get_batch_profile_url(cls, symbols: List[str]) -> str:
        """
        Get batch profile URL for multiple symbols
        
        Args:
            symbols: List of ticker symbols (max 100)
        
        Returns:
            URL with symbols parameter
        """
        if len(symbols) > 100:
            raise ValueError("Maximum 100 symbols allowed per batch request")
        
        symbols_str = ",".join(symbols)
        return f"{cls.PROFILE_BATCH}?symbols={symbols_str}"
    
    @classmethod
    def get_shares_float_url(cls, page: int = 0, limit: int = 1000) -> str:
        """
        Get shares float URL with pagination
        
        Args:
            page: Page number (0-indexed)
            limit: Results per page (max 1000)
        
        Returns:
            URL with pagination parameters
        """
        return f"{cls.SHARES_FLOAT_ALL}?page={page}&limit={limit}"


# =============================================
# RECOMMENDED ENDPOINTS FOR SCANNER
# =============================================

SCANNER_RECOMMENDED_ENDPOINTS = {
    "universe": {
        "endpoint": FMPEndpoints.AVAILABLE_TRADED,
        "type": FMPEndpointType.ALL,
        "description": "Get all available traded stocks (best for initial universe)",
        "rate_limit": "Low (1 call)",
        "priority": 1
    },
    "float_data": {
        "endpoint": FMPEndpoints.SHARES_FLOAT_ALL,
        "type": FMPEndpointType.ALL,
        "description": "Get float data for all stocks (paginated)",
        "rate_limit": "Low (~11 calls for 11k tickers at 1000/page)",
        "priority": 2
    },
    "market_cap": {
        "endpoint": FMPEndpoints.MARKET_CAP_BATCH,
        "type": FMPEndpointType.BATCH,
        "description": "Get market cap in batch",
        "rate_limit": "Low (few calls)",
        "priority": 3
    },
    "quotes": {
        "endpoint": FMPEndpoints.QUOTE_BATCH,
        "type": FMPEndpointType.BATCH,
        "description": "Get quotes in batches of 100",
        "rate_limit": "Medium (~110 calls for 11k tickers)",
        "priority": 4
    },
    "profiles": {
        "endpoint": FMPEndpoints.PROFILE_BATCH,
        "type": FMPEndpointType.BATCH,
        "description": "Get profiles in batches of 100",
        "rate_limit": "Medium (~110 calls for 11k tickers)",
        "priority": 5
    }
}


# =============================================
# LOADING STRATEGY
# =============================================

class LoadingStrategy:
    """
    Optimal loading strategy for 11,000 tickers
    """
    
    @staticmethod
    def get_initial_load_plan() -> List[Dict]:
        """
        Get optimal plan for initial data load
        
        Returns:
            List of steps with endpoints to call
        """
        return [
            {
                "step": 1,
                "name": "Load Universe",
                "endpoint": FMPEndpoints.AVAILABLE_TRADED,
                "estimated_calls": 1,
                "estimated_time": "~5s"
            },
            {
                "step": 2,
                "name": "Load Float Data",
                "endpoint": FMPEndpoints.SHARES_FLOAT_ALL,
                "estimated_calls": 11,  # 11k / 1000 per page
                "estimated_time": "~30s"
            },
            {
                "step": 3,
                "name": "Load Market Caps",
                "endpoint": FMPEndpoints.MARKET_CAP_BATCH,
                "estimated_calls": "varies",
                "estimated_time": "~20s"
            },
            {
                "step": 4,
                "name": "Load Quotes (Batch)",
                "endpoint": FMPEndpoints.QUOTE_BATCH,
                "estimated_calls": 110,  # 11k / 100 per batch
                "estimated_time": "~2-3 min"
            },
            {
                "step": 5,
                "name": "Load Profiles (Batch)",
                "endpoint": FMPEndpoints.PROFILE_BATCH,
                "estimated_calls": 110,
                "estimated_time": "~2-3 min"
            }
        ]
    
    @staticmethod
    def chunk_symbols(symbols: List[str], chunk_size: int = 100) -> List[List[str]]:
        """
        Split symbols into chunks for batch processing
        
        Args:
            symbols: List of ticker symbols
            chunk_size: Size of each chunk
        
        Returns:
            List of symbol chunks
        """
        return [symbols[i:i + chunk_size] for i in range(0, len(symbols), chunk_size)]

