"""
Base classes for workflow nodes.
All nodes must implement the NodeBase interface.
"""
from abc import ABC, abstractmethod
from typing import Dict, Any, Optional, List
from dataclasses import dataclass, field
from enum import Enum
import pandas as pd
import structlog

logger = structlog.get_logger()


class NodeCategory(Enum):
    """Categories of workflow nodes."""
    SOURCE = "source"        # Generates data from scratch
    TRANSFORM = "transform"  # Filters/modifies input data
    ENRICH = "enrich"        # Adds information to each row
    ACTION = "action"        # Final output (display, save, alert)


@dataclass
class NodeConfig:
    """Configuration for a node instance."""
    node_type: str
    config: Dict[str, Any] = field(default_factory=dict)
    

@dataclass 
class NodeResult:
    """Result from node execution."""
    success: bool
    data: Optional[pd.DataFrame] = None
    metadata: Dict[str, Any] = field(default_factory=dict)
    error: Optional[str] = None
    
    def to_dict(self) -> Dict[str, Any]:
        """Serialize result for API response."""
        result = {
            "success": self.success,
            "metadata": self.metadata
        }
        if self.data is not None and not self.data.empty:
            result["data"] = serialize_dataframe(self.data)
        if self.error:
            result["error"] = self.error
        return result


class NodeBase(ABC):
    """Base class for all workflow nodes."""
    
    # Override in subclasses
    name: str = "base"
    category: NodeCategory = NodeCategory.SOURCE
    description: str = ""
    config_schema: Dict[str, Any] = {}
    
    def __init__(self, config: Dict[str, Any], context: Dict[str, Any]):
        """
        Initialize node with configuration.
        
        Args:
            config: Node-specific configuration from workflow
            context: Shared context (llm_client, db, etc.)
        """
        self.config = config
        self.context = context
        self.logger = logger.bind(node=self.name)
    
    @abstractmethod
    async def execute(self, input_data: Optional[pd.DataFrame] = None) -> NodeResult:
        """
        Execute the node logic.
        
        Args:
            input_data: DataFrame from previous node (None for SOURCE nodes)
            
        Returns:
            NodeResult with output DataFrame
        """
        pass
    
    def validate_input(self, input_data: Optional[pd.DataFrame]) -> bool:
        """Validate input data meets requirements."""
        if self.category == NodeCategory.SOURCE:
            return True  # SOURCE nodes don't need input
        
        if self.category in [NodeCategory.TRANSFORM, NodeCategory.ENRICH]:
            if input_data is None or input_data.empty:
                self.logger.warning("node_requires_input", node=self.name)
                return False
        
        return True
    
    def get_config_value(self, key: str, default: Any = None) -> Any:
        """Get configuration value with default."""
        return self.config.get(key, default)


def serialize_dataframe(df: pd.DataFrame, max_rows: int = 500) -> Dict[str, Any]:
    """Serialize DataFrame to dict for API response."""
    import numpy as np
    import math
    
    if df is None or df.empty:
        return {"type": "dataframe", "columns": [], "data": [], "count": 0}
    
    def safe_value(val):
        """Convert value to JSON-safe type."""
        if val is None or pd.isna(val):
            return None
        if isinstance(val, (np.integer,)):
            return int(val)
        if isinstance(val, (np.floating,)):
            f = float(val)
            if math.isnan(f) or math.isinf(f):
                return None
            return f
        if isinstance(val, np.bool_):
            return bool(val)
        if isinstance(val, (dict, list)):
            return str(val)[:100]  # Truncate complex types
        return val
    
    # Convert numpy types to Python types
    records = []
    for _, row in df.head(max_rows).iterrows():
        record = {}
        for col in df.columns:
            record[col] = safe_value(row[col])
        records.append(record)
    
    return {
        "type": "dataframe",
        "columns": df.columns.tolist(),
        "data": records,
        "count": len(df)
    }


def deserialize_dataframe(data: Dict[str, Any]) -> Optional[pd.DataFrame]:
    """Deserialize dict to DataFrame."""
    if not data:
        return None
    
    # Handle nested structures
    if isinstance(data, dict):
        # Direct dataframe format
        if data.get("type") == "dataframe" and "data" in data:
            records = data["data"]
            columns = data.get("columns", [])
            if records and columns:
                return pd.DataFrame(records, columns=columns)
        
        # Look for nested dataframe
        for key in ["data", "tickers", "sectors", "output"]:
            if key in data and isinstance(data[key], dict):
                nested = data[key]
                if nested.get("type") == "dataframe":
                    return deserialize_dataframe(nested)
                    
    return None
