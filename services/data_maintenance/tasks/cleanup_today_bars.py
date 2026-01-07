"""
Cleanup Today Bars

Removes the today.parquet file at midnight ET.
Polygon flat files are downloaded automatically in the morning with the official data.
"""

import os
from pathlib import Path
from datetime import datetime
import structlog

logger = structlog.get_logger()


async def cleanup_today_bars() -> dict:
    """
    Remove today.parquet file.
    
    This should run at midnight ET when:
    - The day officially ends
    - Polygon's official flat file will be available in the morning
    
    Returns:
        dict with status and file info
    """
    today_file = Path("/data/polygon/minute_aggs/today.parquet")
    
    result = {
        "task": "cleanup_today_bars",
        "timestamp": datetime.now().isoformat(),
        "file_path": str(today_file),
        "action": None,
        "size_mb": 0
    }
    
    if today_file.exists():
        try:
            # Get file size before deletion
            size_bytes = today_file.stat().st_size
            result["size_mb"] = round(size_bytes / (1024 * 1024), 2)
            
            # Delete the file
            today_file.unlink()
            
            result["action"] = "deleted"
            logger.info("today_bars_cleaned", 
                file=str(today_file), 
                size_mb=result["size_mb"]
            )
            
        except Exception as e:
            result["action"] = "error"
            result["error"] = str(e)
            logger.error("today_bars_cleanup_failed", 
                file=str(today_file), 
                error=str(e)
            )
    else:
        result["action"] = "not_found"
        logger.info("today_bars_not_found", file=str(today_file))
    
    return result

