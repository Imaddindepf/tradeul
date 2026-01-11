"""
TRANSFORM nodes - Filter, sort, limit, and modify data.
These nodes require input from previous nodes.
"""
from typing import Dict, Any, Optional, List
import pandas as pd
from nodes.base import NodeBase, NodeCategory, NodeResult
import structlog

logger = structlog.get_logger()


class SmartFilterNode(NodeBase):
    """
    Apply multiple filter conditions to input data.
    Highly configurable with dynamic conditions.
    """
    name = "smart_filter"
    category = NodeCategory.TRANSFORM
    description = "Filter data by multiple conditions"
    config_schema = {
        "conditions": {
            "type": "list",
            "description": "List of filter conditions",
            "example": [
                {"column": "price", "operator": ">=", "value": 5},
                {"column": "volume_today", "operator": ">=", "value": 1000000},
                {"column": "change_percent", "operator": ">=", "value": 3}
            ]
        },
        "logic": {"type": "str", "default": "AND", "options": ["AND", "OR"]},
    }
    
    async def execute(self, input_data: Optional[pd.DataFrame] = None) -> NodeResult:
        if not self.validate_input(input_data):
            return NodeResult(success=False, error="Input data required")
        
        try:
            df = input_data.copy()
            original_count = len(df)
            
            conditions = self.get_config_value("conditions", [])
            logic = self.get_config_value("logic", "AND")
            
            if not conditions:
                # No conditions = pass through
                return NodeResult(
                    success=True,
                    data=df,
                    metadata={"filtered": 0, "passed": len(df)}
                )
            
            # Build masks for each condition
            masks = []
            for cond in conditions:
                col = cond.get("column")
                op = cond.get("operator", ">=")
                val = cond.get("value")
                
                if col not in df.columns:
                    self.logger.warning("filter_column_not_found", column=col)
                    continue
                
                if op == ">=":
                    mask = df[col] >= val
                elif op == ">":
                    mask = df[col] > val
                elif op == "<=":
                    mask = df[col] <= val
                elif op == "<":
                    mask = df[col] < val
                elif op == "==":
                    mask = df[col] == val
                elif op == "!=":
                    mask = df[col] != val
                elif op == "contains":
                    mask = df[col].astype(str).str.contains(str(val), case=False, na=False)
                elif op == "in":
                    mask = df[col].isin(val if isinstance(val, list) else [val])
                else:
                    continue
                
                masks.append(mask)
            
            if masks:
                if logic == "AND":
                    combined_mask = masks[0]
                    for m in masks[1:]:
                        combined_mask = combined_mask & m
                else:  # OR
                    combined_mask = masks[0]
                    for m in masks[1:]:
                        combined_mask = combined_mask | m
                
                df = df[combined_mask]
            
            self.logger.info("smart_filter_complete", 
                           original=original_count, 
                           filtered=len(df),
                           conditions_applied=len(masks))
            
            return NodeResult(
                success=True,
                data=df,
                metadata={
                    "original_count": original_count,
                    "filtered_count": len(df),
                    "removed": original_count - len(df)
                }
            )
            
        except Exception as e:
            self.logger.error("smart_filter_error", error=str(e))
            return NodeResult(success=False, error=str(e))


class SortNode(NodeBase):
    """
    Sort data by one or more columns.
    """
    name = "sort"
    category = NodeCategory.TRANSFORM
    description = "Sort data by columns"
    config_schema = {
        "columns": {"type": "list", "default": ["change_percent"]},
        "ascending": {"type": "bool", "default": False},
    }
    
    async def execute(self, input_data: Optional[pd.DataFrame] = None) -> NodeResult:
        if not self.validate_input(input_data):
            return NodeResult(success=False, error="Input data required")
        
        try:
            df = input_data.copy()
            
            columns = self.get_config_value("columns", ["change_percent"])
            ascending = self.get_config_value("ascending", False)
            
            # Filter to existing columns
            valid_cols = [c for c in columns if c in df.columns]
            
            if valid_cols:
                df = df.sort_values(by=valid_cols, ascending=ascending)
            
            return NodeResult(
                success=True,
                data=df,
                metadata={"sorted_by": valid_cols, "ascending": ascending}
            )
            
        except Exception as e:
            self.logger.error("sort_error", error=str(e))
            return NodeResult(success=False, error=str(e))


class LimitNode(NodeBase):
    """
    Limit output to top N rows.
    """
    name = "limit"
    category = NodeCategory.TRANSFORM
    description = "Limit to top N results"
    config_schema = {
        "limit": {"type": "int", "default": 20, "min": 1, "max": 500},
    }
    
    async def execute(self, input_data: Optional[pd.DataFrame] = None) -> NodeResult:
        if not self.validate_input(input_data):
            return NodeResult(success=False, error="Input data required")
        
        try:
            limit = self.get_config_value("limit", 20)
            df = input_data.head(limit)
            
            return NodeResult(
                success=True,
                data=df,
                metadata={"limit": limit, "count": len(df)}
            )
            
        except Exception as e:
            return NodeResult(success=False, error=str(e))


class MergeNode(NodeBase):
    """
    Merge multiple DataFrames (from multiple inputs).
    Used when node has multiple incoming connections.
    """
    name = "merge"
    category = NodeCategory.TRANSFORM
    description = "Combine multiple data sources"
    config_schema = {
        "mode": {"type": "str", "default": "concat", "options": ["concat", "intersect", "union"]},
        "dedupe_column": {"type": "str", "default": "symbol"},
    }
    
    async def execute(self, input_data: Optional[pd.DataFrame] = None) -> NodeResult:
        # For merge, we need multiple inputs - handled specially by executor
        if input_data is None or input_data.empty:
            return NodeResult(success=False, error="No input data to merge")
        
        try:
            mode = self.get_config_value("mode", "concat")
            dedupe_col = self.get_config_value("dedupe_column", "symbol")
            
            df = input_data
            
            # Deduplicate if column exists
            if dedupe_col in df.columns:
                df = df.drop_duplicates(subset=[dedupe_col], keep="first")
            
            return NodeResult(
                success=True,
                data=df,
                metadata={"mode": mode, "count": len(df)}
            )
            
        except Exception as e:
            return NodeResult(success=False, error=str(e))


class RankingNode(NodeBase):
    """
    Create a composite ranking score.
    """
    name = "ranking"
    category = NodeCategory.TRANSFORM
    description = "Create composite ranking from multiple factors"
    config_schema = {
        "factors": {
            "type": "list",
            "description": "Columns and weights for ranking",
            "example": [
                {"column": "change_percent", "weight": 0.4},
                {"column": "rvol", "weight": 0.3},
                {"column": "sentiment_score", "weight": 0.3}
            ]
        },
        "ascending": {"type": "bool", "default": False},
        "limit": {"type": "int", "default": 20},
    }
    
    async def execute(self, input_data: Optional[pd.DataFrame] = None) -> NodeResult:
        if not self.validate_input(input_data):
            return NodeResult(success=False, error="Input data required")
        
        try:
            df = input_data.copy()
            factors = self.get_config_value("factors", [])
            ascending = self.get_config_value("ascending", False)
            limit = self.get_config_value("limit", 20)
            
            if not factors:
                # Default ranking by change_percent
                if "change_percent" in df.columns:
                    df["rank_score"] = df["change_percent"].abs()
                else:
                    df["rank_score"] = range(len(df))
            else:
                # Composite score
                df["rank_score"] = 0.0
                total_weight = sum(f.get("weight", 1.0) for f in factors)
                
                for factor in factors:
                    col = factor.get("column")
                    weight = factor.get("weight", 1.0) / total_weight
                    
                    if col in df.columns:
                        # Normalize column to 0-1 range
                        col_min = df[col].min()
                        col_max = df[col].max()
                        if col_max > col_min:
                            normalized = (df[col] - col_min) / (col_max - col_min)
                            df["rank_score"] += normalized * weight
            
            # Sort and limit
            df = df.sort_values("rank_score", ascending=ascending)
            df["rank"] = range(1, len(df) + 1)
            df = df.head(limit)
            
            return NodeResult(
                success=True,
                data=df,
                metadata={"ranked": True, "count": len(df)}
            )
            
        except Exception as e:
            self.logger.error("ranking_error", error=str(e))
            return NodeResult(success=False, error=str(e))


class SectorClassifierNode(NodeBase):
    """
    Classify tickers into synthetic sectors using LLM.
    """
    name = "sector_classifier"
    category = NodeCategory.TRANSFORM
    description = "Classify tickers into thematic sectors (AI-powered)"
    config_schema = {
        "max_sectors": {"type": "int", "default": 15},
    }
    
    async def execute(self, input_data: Optional[pd.DataFrame] = None) -> NodeResult:
        if not self.validate_input(input_data):
            return NodeResult(success=False, error="Input data required")
        
        try:
            from agent.tools import _classify_synthetic_sectors
            from nodes.base import serialize_dataframe
            
            max_sectors = self.get_config_value("max_sectors", 15)
            
            # Serialize input for the tool
            input_serialized = serialize_dataframe(input_data)
            
            result = await _classify_synthetic_sectors({
                "max_sectors": max_sectors,
                "input_data": input_serialized
            }, self.context)
            
            if not result.get("success"):
                return NodeResult(success=False, error=result.get("error", "Classification failed"))
            
            # Get the classified tickers DataFrame
            tickers_df = result.get("tickers")
            if isinstance(tickers_df, pd.DataFrame) and not tickers_df.empty:
                return NodeResult(
                    success=True,
                    data=tickers_df,
                    metadata={
                        "sector_count": result.get("sector_count", 0),
                        "ticker_count": len(tickers_df)
                    }
                )
            
            # Fallback: return sectors performance
            sectors = result.get("sectors")
            if isinstance(sectors, pd.DataFrame):
                return NodeResult(
                    success=True,
                    data=sectors,
                    metadata={"sector_count": len(sectors)}
                )
            
            return NodeResult(success=False, error="No classification results")
            
        except Exception as e:
            self.logger.error("sector_classifier_error", error=str(e))
            return NodeResult(success=False, error=str(e))


# Registry of TRANSFORM nodes
TRANSFORM_NODES = {
    "smart_filter": SmartFilterNode,
    "sort": SortNode,
    "limit": LimitNode,
    "merge": MergeNode,
    "ranking": RankingNode,
    "sector_classifier": SectorClassifierNode,
}
