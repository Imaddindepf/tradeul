"""
Capital Raise Extractor
Extracts capital raise amounts from SEC 8-K filings (Item 1.01 and 3.02)
Uses SEC-API.io extractor endpoint
"""

import re
import asyncio
from datetime import datetime, timedelta
from typing import Any, Dict, List, Optional
from dataclasses import dataclass
from decimal import Decimal

import httpx

from shared.config.settings import settings
from shared.utils.logger import get_logger

logger = get_logger(__name__)


@dataclass
class CapitalRaise:
    """Represents a detected capital raise event"""
    filing_date: str
    effective_date: Optional[str]
    form_type: str
    gross_proceeds: Optional[float]
    net_proceeds: Optional[float]
    instrument_type: str  # 'preferred_stock', 'common_stock', 'convertible', 'warrant', 'pipe', etc.
    shares_issued: Optional[int]
    description: str
    filing_url: str
    confidence: float  # 0.0 - 1.0


class CapitalRaiseExtractor:
    """
    Extracts capital raise information from SEC 8-K filings.
    Looks for Item 1.01 (Material Agreements) and Item 3.02 (Unregistered Sales).
    """
    
    def __init__(self):
        self.sec_api_key = settings.SEC_API_IO_KEY
        self.base_url = "https://api.sec-api.io"
    
    async def get_capital_raises_since(
        self, 
        ticker: str, 
        since_date: str,
        cik: Optional[str] = None
    ) -> List[CapitalRaise]:
        """
        Get all capital raises for a ticker since a given date.
        
        Args:
            ticker: Stock ticker symbol
            since_date: ISO date string (YYYY-MM-DD) to search from
            cik: Optional CIK for more precise search
            
        Returns:
            List of CapitalRaise objects detected
        """
        if not self.sec_api_key:
            logger.warning("sec_api_key_missing_for_capital_raises")
            return []
        
        # Build query for 8-K filings with Item 3.02 (Unregistered Sales)
        if cik:
            query = f'cik:{cik} AND formType:"8-K" AND items:"3.02" AND filedAt:[{since_date} TO *]'
        else:
            query = f'ticker:{ticker} AND formType:"8-K" AND items:"3.02" AND filedAt:[{since_date} TO *]'
        
        try:
            async with httpx.AsyncClient(timeout=30.0) as client:
                # Search for 8-K filings with Item 3.02
                search_resp = await client.post(
                    f"{self.base_url}?token={self.sec_api_key}",
                    json={
                        "query": {"query_string": {"query": query}},
                        "from": "0",
                        "size": "20",
                        "sort": [{"filedAt": {"order": "desc"}}]
                    },
                    headers={"Content-Type": "application/json"}
                )
                search_resp.raise_for_status()
                search_data = search_resp.json()
        except Exception as e:
            logger.error("capital_raise_search_failed", ticker=ticker, error=str(e))
            return []
        
        filings = search_data.get("filings", [])
        if not filings:
            logger.info("no_capital_raise_filings_found", ticker=ticker, since=since_date)
            return []
        
        logger.info("capital_raise_filings_found", ticker=ticker, count=len(filings))
        
        # Extract capital raise info from each filing
        capital_raises = []
        for filing in filings:
            raise_info = await self._extract_from_filing(filing)
            if raise_info:
                capital_raises.extend(raise_info)
        
        return capital_raises
    
    async def _extract_from_filing(self, filing: Dict[str, Any]) -> List[CapitalRaise]:
        """Extract capital raise information from a single 8-K filing."""
        filing_url = filing.get("linkToFilingDetails", "")
        filing_date = filing.get("filedAt", "")[:10]
        period = filing.get("periodOfReport", filing_date)
        
        # Extract text from Item 1.01 (Material Agreement)
        item_text = await self._get_item_text(filing_url, "1-1")
        
        if not item_text:
            # Try Item 3.02 directly
            item_text = await self._get_item_text(filing_url, "3-2")
        
        if not item_text:
            logger.warning("could_not_extract_item_text", url=filing_url)
            return []
        
        # Parse the text for capital raise information
        raises = self._parse_capital_raise_text(item_text, filing_date, period, filing_url)
        
        return raises
    
    async def _get_item_text(self, filing_url: str, item: str) -> Optional[str]:
        """Get the text content of a specific 8-K item."""
        try:
            async with httpx.AsyncClient(timeout=30.0) as client:
                url = f"{self.base_url}/extractor?url={filing_url}&item={item}&type=text&token={self.sec_api_key}"
                resp = await client.get(url)
                
                if resp.status_code == 200:
                    return resp.text
                elif resp.status_code == 404:
                    return None
                else:
                    resp.raise_for_status()
        except Exception as e:
            logger.warning("item_text_extraction_failed", url=filing_url, item=item, error=str(e))
        
        return None
    
    def _parse_capital_raise_text(
        self, 
        text: str, 
        filing_date: str,
        effective_date: str,
        filing_url: str
    ) -> List[CapitalRaise]:
        """
        Parse the text to extract capital raise amounts.
        Looks for patterns like:
        - "gross proceeds of $X"
        - "net proceeds of $X"
        - "aggregate purchase price of $X"
        - "X shares of ... for $Y"
        """
        raises = []
        text_lower = text.lower()
        
        # Patterns to match dollar amounts
        # Match: $1,000,000 or $1.5 million or 1,700,000 dollars
        money_patterns = [
            # Pattern: gross proceeds of $X,XXX,XXX
            r'gross proceeds of \$?([\d,]+(?:\.\d+)?)\s*(?:million)?',
            # Pattern: net proceeds of $X,XXX,XXX  
            r'net proceeds of \$?([\d,]+(?:\.\d+)?)\s*(?:million)?',
            # Pattern: aggregate gross proceeds of $X
            r'aggregate (?:gross )?proceeds of \$?([\d,]+(?:\.\d+)?)\s*(?:million)?',
            # Pattern: purchase price of $X
            r'(?:aggregate )?purchase price of \$?([\d,]+(?:\.\d+)?)\s*(?:million)?',
            # Pattern: $X in gross/net proceeds
            r'\$([\d,]+(?:\.\d+)?)\s*(?:million)?\s+in\s+(?:gross|net)\s+proceeds',
        ]
        
        gross_proceeds = None
        net_proceeds = None
        
        for pattern in money_patterns:
            matches = re.finditer(pattern, text_lower)
            for match in matches:
                amount_str = match.group(1).replace(',', '')
                try:
                    amount = float(amount_str)
                    # Check if it says "million"
                    if 'million' in text_lower[match.start():match.end() + 20]:
                        amount *= 1_000_000
                    elif amount < 10000:  # Likely in millions if small number
                        # Check context
                        context = text_lower[max(0, match.start()-50):match.end()+50]
                        if 'million' in context:
                            amount *= 1_000_000
                    
                    # Determine if gross or net
                    context = text_lower[max(0, match.start()-20):match.end()]
                    if 'gross' in context:
                        gross_proceeds = amount
                    elif 'net' in context:
                        net_proceeds = amount
                    elif gross_proceeds is None:
                        gross_proceeds = amount
                        
                except ValueError:
                    continue
        
        # Extract instrument type
        instrument_type = "unknown"
        if "preferred stock" in text_lower:
            instrument_type = "preferred_stock"
        elif "common stock" in text_lower:
            instrument_type = "common_stock"
        elif "convertible" in text_lower:
            instrument_type = "convertible"
        elif "warrant" in text_lower:
            instrument_type = "warrant"
        elif "pipe" in text_lower or "private placement" in text_lower:
            instrument_type = "pipe"
        
        # Extract shares issued
        shares_issued = None
        shares_patterns = [
            r'(\d{1,3}(?:,\d{3})*)\s+shares\s+of',
            r'issued\s+(?:an\s+aggregate\s+of\s+)?(\d{1,3}(?:,\d{3})*)\s+shares',
        ]
        for pattern in shares_patterns:
            match = re.search(pattern, text_lower)
            if match:
                try:
                    shares_issued = int(match.group(1).replace(',', ''))
                    break
                except ValueError:
                    pass
        
        # Create description
        description = self._generate_description(text, instrument_type, gross_proceeds, shares_issued)
        
        # Only create a CapitalRaise if we found monetary amounts
        if gross_proceeds or net_proceeds:
            confidence = 0.9 if (gross_proceeds and net_proceeds) else 0.7
            if shares_issued:
                confidence += 0.05
            if instrument_type != "unknown":
                confidence += 0.05
            
            raise_info = CapitalRaise(
                filing_date=filing_date,
                effective_date=effective_date,
                form_type="8-K",
                gross_proceeds=gross_proceeds,
                net_proceeds=net_proceeds,
                instrument_type=instrument_type,
                shares_issued=shares_issued,
                description=description,
                filing_url=filing_url,
                confidence=min(confidence, 1.0)
            )
            raises.append(raise_info)
            
            logger.info(
                "capital_raise_extracted",
                filing_date=filing_date,
                gross=gross_proceeds,
                net=net_proceeds,
                type=instrument_type,
                confidence=raise_info.confidence
            )
        
        return raises
    
    def _generate_description(
        self,
        text: str,
        instrument_type: str,
        amount: Optional[float],
        shares: Optional[int]
    ) -> str:
        """Generate a human-readable description of the capital raise."""
        parts = []
        
        instrument_names = {
            "preferred_stock": "Preferred Stock",
            "common_stock": "Common Stock",
            "convertible": "Convertible Securities",
            "warrant": "Warrants",
            "pipe": "PIPE",
            "unknown": "Securities"
        }
        
        parts.append(f"{instrument_names.get(instrument_type, 'Securities')} offering")
        
        if amount:
            if amount >= 1_000_000:
                parts.append(f"for ${amount/1_000_000:.1f}M")
            else:
                parts.append(f"for ${amount:,.0f}")
        
        if shares:
            if shares >= 1_000_000:
                parts.append(f"({shares/1_000_000:.1f}M shares)")
            else:
                parts.append(f"({shares:,} shares)")
        
        return " ".join(parts)


async def get_total_capital_raises(
    ticker: str,
    since_date: str,
    cik: Optional[str] = None
) -> Dict[str, Any]:
    """
    Convenience function to get total capital raises since a date.
    
    Returns:
        Dict with total gross/net proceeds and list of individual raises
    """
    extractor = CapitalRaiseExtractor()
    raises = await extractor.get_capital_raises_since(ticker, since_date, cik)
    
    total_gross = sum(r.gross_proceeds or 0 for r in raises)
    total_net = sum(r.net_proceeds or 0 for r in raises)
    
    return {
        "total_gross_proceeds": total_gross,
        "total_net_proceeds": total_net,
        "raise_count": len(raises),
        "raises": [
            {
                "filing_date": r.filing_date,
                "effective_date": r.effective_date,
                "gross_proceeds": r.gross_proceeds,
                "net_proceeds": r.net_proceeds,
                "instrument_type": r.instrument_type,
                "shares_issued": r.shares_issued,
                "description": r.description,
                "confidence": r.confidence,
            }
            for r in raises
        ]
    }


