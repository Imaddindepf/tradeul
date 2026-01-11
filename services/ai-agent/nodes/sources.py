"""
SOURCE nodes - Generate data from scratch.
These nodes don't require input from previous nodes.
"""
from typing import Dict, Any, Optional
import pandas as pd
from nodes.base import NodeBase, NodeCategory, NodeResult
import structlog

logger = structlog.get_logger()


class MarketScannerNode(NodeBase):
    """
    Scans current market for active tickers.
    Uses get_market_snapshot tool.
    """
    name = "market_scanner"
    category = NodeCategory.SOURCE
    description = "Scan market for active stocks with filters"
    config_schema = {
        "limit": {"type": "int", "default": 100, "min": 10, "max": 500},
        "min_price": {"type": "float", "default": 1.0},
        "max_price": {"type": "float", "default": None},
        "min_volume": {"type": "int", "default": 100000},
        "min_change_pct": {"type": "float", "default": None},
        "sector": {"type": "str", "default": None},
    }
    
    async def execute(self, input_data: Optional[pd.DataFrame] = None) -> NodeResult:
        try:
            from agent.tools import _get_market_snapshot
            
            limit = self.get_config_value("limit", 100)
            min_volume = self.get_config_value("min_volume", 100000)
            min_price = self.get_config_value("min_price", 1.0)
            
            # Use existing tool
            result = await _get_market_snapshot({
                "limit": limit * 2,  # Get extra for filtering
                "filter_type": "all",
                "min_volume": min_volume,
                "min_price": min_price
            }, self.context)
            
            if not result.get("success"):
                return NodeResult(success=False, error=result.get("error", "Failed to scan market"))
            
            df = result.get("data")
            if df is None or (isinstance(df, pd.DataFrame) and df.empty):
                return NodeResult(success=False, error="No market data available")
            
            # Apply additional filters
            max_price = self.get_config_value("max_price")
            if max_price and "price" in df.columns:
                df = df[df["price"] <= max_price]
            
            min_change = self.get_config_value("min_change_pct")
            if min_change and "change_percent" in df.columns:
                df = df[df["change_percent"].abs() >= min_change]
            
            sector = self.get_config_value("sector")
            if sector and "sector" in df.columns:
                df = df[df["sector"].str.contains(sector, case=False, na=False)]
            
            df = df.head(limit)
            
            self.logger.info("market_scanner_complete", rows=len(df))
            
            return NodeResult(
                success=True,
                data=df,
                metadata={"source": "market_scanner", "count": len(df)}
            )
            
        except Exception as e:
            self.logger.error("market_scanner_error", error=str(e))
            return NodeResult(success=False, error=str(e))


class TopMoversNode(NodeBase):
    """
    Get top gaining or losing stocks.
    """
    name = "top_movers"
    category = NodeCategory.SOURCE
    description = "Get top gainers or losers"
    config_schema = {
        "direction": {"type": "str", "default": "up", "options": ["up", "down", "both"]},
        "limit": {"type": "int", "default": 50},
        "min_volume": {"type": "int", "default": 100000},
        "date": {"type": "str", "default": "today"},
    }
    
    async def execute(self, input_data: Optional[pd.DataFrame] = None) -> NodeResult:
        try:
            from agent.tools import _get_top_movers
            
            direction = self.get_config_value("direction", "up")
            limit = self.get_config_value("limit", 50)
            min_volume = self.get_config_value("min_volume", 100000)
            date = self.get_config_value("date", "today")
            
            result = await _get_top_movers({
                "direction": direction,
                "limit": limit,
                "min_volume": min_volume,
                "date": date
            }, self.context)
            
            if not result.get("success"):
                return NodeResult(success=False, error=result.get("error", "Failed to get top movers"))
            
            df = result.get("data")
            if df is None or (isinstance(df, pd.DataFrame) and df.empty):
                return NodeResult(success=False, error="No movers found")
            
            return NodeResult(
                success=True,
                data=df,
                metadata={"source": "top_movers", "direction": direction, "count": len(df)}
            )
            
        except Exception as e:
            self.logger.error("top_movers_error", error=str(e))
            return NodeResult(success=False, error=str(e))


class AnomalyScannerNode(NodeBase):
    """
    Detect unusual volume/price activity.
    Combines volume surge detection with price anomalies.
    """
    name = "anomaly_scanner"
    category = NodeCategory.SOURCE
    description = "Detect unusual market activity (volume spikes, price anomalies)"
    config_schema = {
        "limit": {"type": "int", "default": 50},
        "min_rvol": {"type": "float", "default": 2.0, "description": "Minimum relative volume"},
        "min_change_pct": {"type": "float", "default": 5.0},
        "include_gaps": {"type": "bool", "default": True},
    }
    
    async def execute(self, input_data: Optional[pd.DataFrame] = None) -> NodeResult:
        try:
            from agent.tools import _get_market_snapshot
            
            limit = self.get_config_value("limit", 50)
            min_rvol = self.get_config_value("min_rvol", 2.0)
            min_change = self.get_config_value("min_change_pct", 5.0)
            
            # Get broader market data
            result = await _get_market_snapshot({
                "limit": 500,
                "filter_type": "all"
            }, self.context)
            
            if not result.get("success"):
                return NodeResult(success=False, error="Failed to scan market")
            
            df = result.get("data")
            if df is None or df.empty:
                return NodeResult(success=False, error="No market data available")
            
            # Filter for anomalies
            anomalies = df.copy()
            
            # Volume anomaly: rvol > threshold
            if "rvol" in anomalies.columns:
                anomalies = anomalies[anomalies["rvol"] >= min_rvol]
            
            # Price anomaly: significant change
            if "change_percent" in anomalies.columns:
                anomalies = anomalies[anomalies["change_percent"].abs() >= min_change]
            
            # Sort by combined score (rvol * abs(change))
            if "rvol" in anomalies.columns and "change_percent" in anomalies.columns:
                anomalies["anomaly_score"] = anomalies["rvol"] * anomalies["change_percent"].abs()
                anomalies = anomalies.sort_values("anomaly_score", ascending=False)
            
            anomalies = anomalies.head(limit)
            
            self.logger.info("anomaly_scanner_complete", anomalies_found=len(anomalies))
            
            return NodeResult(
                success=True,
                data=anomalies,
                metadata={"source": "anomaly_scanner", "count": len(anomalies)}
            )
            
        except Exception as e:
            self.logger.error("anomaly_scanner_error", error=str(e))
            return NodeResult(success=False, error=str(e))


class VolumeSurgeNode(NodeBase):
    """
    Detect stocks with unusual volume compared to average.
    """
    name = "volume_surge"
    category = NodeCategory.SOURCE
    description = "Find stocks with volume spikes"
    config_schema = {
        "limit": {"type": "int", "default": 50},
        "min_rvol": {"type": "float", "default": 3.0},
        "min_volume": {"type": "int", "default": 500000},
    }
    
    async def execute(self, input_data: Optional[pd.DataFrame] = None) -> NodeResult:
        try:
            from agent.tools import _get_market_snapshot
            
            limit = self.get_config_value("limit", 50)
            min_rvol = self.get_config_value("min_rvol", 3.0)
            min_volume = self.get_config_value("min_volume", 500000)
            
            result = await _get_market_snapshot({
                "limit": 500,
                "filter_type": "all",
                "min_volume": min_volume
            }, self.context)
            
            if not result.get("success"):
                return NodeResult(success=False, error="Failed to scan market")
            
            df = result.get("data")
            if df is None or df.empty:
                return NodeResult(success=False, error="No market data")
            
            # Filter for volume surge
            surge = df.copy()
            
            if "rvol" in surge.columns:
                surge = surge[surge["rvol"] >= min_rvol]
                surge = surge.sort_values("rvol", ascending=False)
            
            surge = surge.head(limit)
            
            return NodeResult(
                success=True,
                data=surge,
                metadata={"source": "volume_surge", "count": len(surge)}
            )
            
        except Exception as e:
            self.logger.error("volume_surge_error", error=str(e))
            return NodeResult(success=False, error=str(e))


# Registry of SOURCE nodes
SOURCE_NODES = {
    "market_scanner": MarketScannerNode,
    "top_movers": TopMoversNode,
    "anomaly_scanner": AnomalyScannerNode,
    "volume_surge": VolumeSurgeNode,
}
