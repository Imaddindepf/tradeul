"""
ACTION nodes - Final output operations.
Display results, save signals, export data, send alerts.
"""
from typing import Dict, Any, Optional, List
from datetime import datetime
import pandas as pd
from nodes.base import NodeBase, NodeCategory, NodeResult, serialize_dataframe
import structlog

logger = structlog.get_logger()


class ResultsNode(NodeBase):
    """
    Display/output node - presents the final data.
    """
    name = "results"
    category = NodeCategory.ACTION
    description = "Display workflow results"
    config_schema = {
        "title": {"type": "str", "default": "Results"},
        "max_rows": {"type": "int", "default": 100},
        "columns": {"type": "list", "default": None, "description": "Columns to show (null = all)"},
    }
    
    async def execute(self, input_data: Optional[pd.DataFrame] = None) -> NodeResult:
        if input_data is None or input_data.empty:
            return NodeResult(
                success=True,
                data=pd.DataFrame(),
                metadata={"empty": True, "message": "No data to display"}
            )
        
        try:
            df = input_data.copy()
            max_rows = self.get_config_value("max_rows", 100)
            columns = self.get_config_value("columns")
            title = self.get_config_value("title", "Results")
            
            # Filter columns if specified
            if columns:
                valid_cols = [c for c in columns if c in df.columns]
                if valid_cols:
                    df = df[valid_cols]
            
            df = df.head(max_rows)
            
            return NodeResult(
                success=True,
                data=df,
                metadata={
                    "title": title,
                    "count": len(df),
                    "columns": df.columns.tolist()
                }
            )
            
        except Exception as e:
            self.logger.error("results_error", error=str(e))
            return NodeResult(success=False, error=str(e))


class SaveSignalNode(NodeBase):
    """
    Save results as active signals to database.
    """
    name = "save_signal"
    category = NodeCategory.ACTION
    description = "Save results as active signals"
    config_schema = {
        "signal_name": {"type": "str", "default": "Custom Signal"},
        "signal_type": {"type": "str", "default": "OPPORTUNITY"},
        "ttl_hours": {"type": "int", "default": 24, "description": "Hours until signal expires"},
        "max_signals": {"type": "int", "default": 20},
    }
    
    async def execute(self, input_data: Optional[pd.DataFrame] = None) -> NodeResult:
        if input_data is None or input_data.empty:
            return NodeResult(success=False, error="No data to save as signals")
        
        try:
            df = input_data.copy()
            signal_name = self.get_config_value("signal_name", "Custom Signal")
            signal_type = self.get_config_value("signal_type", "OPPORTUNITY")
            ttl_hours = self.get_config_value("ttl_hours", 24)
            max_signals = self.get_config_value("max_signals", 20)
            
            if "symbol" not in df.columns:
                return NodeResult(success=False, error="symbol column required for signals")
            
            df = df.head(max_signals)
            
            # Build signals
            signals = []
            timestamp = datetime.utcnow().isoformat()
            
            for _, row in df.iterrows():
                signal = {
                    "ticker": row["symbol"],
                    "signal_name": signal_name,
                    "signal_type": signal_type,
                    "created_at": timestamp,
                    "ttl_hours": ttl_hours,
                    "data": {
                        "price": row.get("price"),
                        "change_percent": row.get("change_percent"),
                        "volume": row.get("volume_today"),
                        "narrative": row.get("narrative"),
                        "sentiment": row.get("sentiment_label"),
                        "risk_score": row.get("risk_score"),
                        "rank": row.get("rank"),
                    }
                }
                signals.append(signal)
            
            # TODO: Actually save to database
            # For now, return the signals as output
            self.logger.info("save_signal_complete", signals_created=len(signals))
            
            # Add signal metadata to DataFrame
            df["signal_id"] = [f"sig_{i+1}" for i in range(len(df))]
            df["signal_created_at"] = timestamp
            
            return NodeResult(
                success=True,
                data=df,
                metadata={
                    "signals_created": len(signals),
                    "signal_name": signal_name,
                    "expires_in_hours": ttl_hours
                }
            )
            
        except Exception as e:
            self.logger.error("save_signal_error", error=str(e))
            return NodeResult(success=False, error=str(e))


class ExportNode(NodeBase):
    """
    Export data to CSV/JSON format.
    """
    name = "export"
    category = NodeCategory.ACTION
    description = "Export data to file format"
    config_schema = {
        "format": {"type": "str", "default": "csv", "options": ["csv", "json"]},
        "filename": {"type": "str", "default": "workflow_export"},
    }
    
    async def execute(self, input_data: Optional[pd.DataFrame] = None) -> NodeResult:
        if input_data is None or input_data.empty:
            return NodeResult(success=False, error="No data to export")
        
        try:
            df = input_data.copy()
            export_format = self.get_config_value("format", "csv")
            filename = self.get_config_value("filename", "workflow_export")
            
            if export_format == "csv":
                content = df.to_csv(index=False)
                mime_type = "text/csv"
            else:  # json
                content = df.to_json(orient="records", indent=2)
                mime_type = "application/json"
            
            return NodeResult(
                success=True,
                data=df,
                metadata={
                    "export_format": export_format,
                    "filename": f"{filename}.{export_format}",
                    "mime_type": mime_type,
                    "content": content,
                    "size_bytes": len(content)
                }
            )
            
        except Exception as e:
            self.logger.error("export_error", error=str(e))
            return NodeResult(success=False, error=str(e))


class AlertNode(NodeBase):
    """
    Send alert/notification based on results.
    """
    name = "alert"
    category = NodeCategory.ACTION
    description = "Send alert when conditions are met"
    config_schema = {
        "alert_title": {"type": "str", "default": "Workflow Alert"},
        "min_results": {"type": "int", "default": 1, "description": "Min results to trigger alert"},
        "channels": {"type": "list", "default": ["ui"], "options": ["ui", "email", "webhook"]},
    }
    
    async def execute(self, input_data: Optional[pd.DataFrame] = None) -> NodeResult:
        if input_data is None or input_data.empty:
            return NodeResult(
                success=True,
                data=pd.DataFrame(),
                metadata={"alert_triggered": False, "reason": "No data"}
            )
        
        try:
            df = input_data.copy()
            alert_title = self.get_config_value("alert_title", "Workflow Alert")
            min_results = self.get_config_value("min_results", 1)
            channels = self.get_config_value("channels", ["ui"])
            
            alert_triggered = len(df) >= min_results
            
            if alert_triggered:
                # Build alert message
                tickers = df["symbol"].head(10).tolist() if "symbol" in df.columns else []
                
                alert = {
                    "title": alert_title,
                    "message": f"Found {len(df)} results matching criteria",
                    "tickers": tickers,
                    "timestamp": datetime.utcnow().isoformat(),
                    "channels": channels
                }
                
                # TODO: Actually send to channels (email, webhook, etc.)
                self.logger.info("alert_triggered", alert=alert)
            
            return NodeResult(
                success=True,
                data=df,
                metadata={
                    "alert_triggered": alert_triggered,
                    "result_count": len(df),
                    "channels": channels
                }
            )
            
        except Exception as e:
            self.logger.error("alert_error", error=str(e))
            return NodeResult(success=False, error=str(e))


# Registry of ACTION nodes
ACTION_NODES = {
    "results": ResultsNode,
    "save_signal": SaveSignalNode,
    "export": ExportNode,
    "alert": AlertNode,
}
