"""
Base Downloader for Polygon Flat Files

Downloads CSV.gz from Polygon S3 and converts to Parquet for optimal DuckDB performance.
Parquet benefits:
- Columnar format: Read only needed columns
- Binary: No text parsing overhead
- Compressed: zstd compression is fast and efficient
- 10-15x faster queries vs CSV.gz
"""

import os
from abc import ABC, abstractmethod
from datetime import datetime, timedelta
from typing import List, Optional, Dict
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import boto3
from botocore.config import Config
import pandas as pd
import pyarrow as pa
import pyarrow.parquet as pq
import structlog

from config import settings

logger = structlog.get_logger(__name__)


class BaseDownloader(ABC):
    """
    Base class for Polygon S3 flat file downloaders
    
    Downloads CSV.gz from Polygon and converts to Parquet for optimal performance.
    """
    
    # Override in subclasses
    S3_PREFIX: str = ""
    FILE_EXTENSION: str = ".csv.gz"
    PARQUET_EXTENSION: str = ".parquet"
    CONVERT_TO_PARQUET: bool = True  # Enable by default
    KEEP_CSV_AFTER_CONVERT: bool = False  # Delete CSV.gz after conversion to save space
    
    # Parquet compression - zstd is fast and efficient
    PARQUET_COMPRESSION: str = "zstd"
    
    def __init__(
        self,
        access_key: Optional[str] = None,
        secret_key: Optional[str] = None,
        output_dir: Optional[str] = None
    ):
        self.access_key = access_key or settings.polygon_s3_access_key
        self.secret_key = secret_key or settings.polygon_s3_secret_key
        self.output_dir = output_dir or str(settings.data_dir / self._get_subdir())
        
        # Initialize S3 client
        if self.access_key and self.secret_key:
            session = boto3.Session(
                aws_access_key_id=self.access_key,
                aws_secret_access_key=self.secret_key,
            )
            self.s3 = session.client(
                's3',
                endpoint_url=settings.polygon_s3_endpoint,
                config=Config(signature_version='s3v4'),
            )
        else:
            self.s3 = None
            logger.warning("S3 credentials not provided, downloads disabled")
        
        self.bucket = settings.polygon_s3_bucket
        
        # Create output directory
        os.makedirs(self.output_dir, exist_ok=True)
        
        logger.info(
            f"{self.__class__.__name__} initialized",
            output_dir=self.output_dir,
            s3_enabled=self.s3 is not None
        )
    
    @abstractmethod
    def _get_subdir(self) -> str:
        """Get subdirectory name for this data type"""
        pass
    
    @abstractmethod
    def _get_s3_key(self, date: datetime) -> str:
        """Generate S3 key for a specific date"""
        pass
    
    def _get_local_path(self, date: datetime) -> str:
        """Generate local path for CSV.gz file"""
        date_str = date.strftime("%Y-%m-%d")
        return f"{self.output_dir}/{date_str}{self.FILE_EXTENSION}"
    
    def _get_parquet_path(self, date: datetime) -> str:
        """Generate local path for Parquet file"""
        date_str = date.strftime("%Y-%m-%d")
        return f"{self.output_dir}/{date_str}{self.PARQUET_EXTENSION}"
    
    def _convert_csv_to_parquet(self, csv_path: str, parquet_path: str) -> bool:
        """
        Convert CSV.gz to Parquet format.
        
        Benefits:
        - Columnar: DuckDB reads only needed columns
        - Binary: No text parsing (string→float conversion)
        - Compressed: zstd is fast to decompress
        - Predicate pushdown: Filter at file level
        
        Returns True if conversion successful.
        """
        try:
            # Read CSV.gz with pandas (handles gzip automatically)
            df = pd.read_csv(csv_path)
            
            # Convert to Parquet with zstd compression
            # row_group_size optimized for typical queries (by ticker)
            df.to_parquet(
                parquet_path,
                compression=self.PARQUET_COMPRESSION,
                index=False,
                engine='pyarrow'
            )
            
            csv_size = os.path.getsize(csv_path)
            parquet_size = os.path.getsize(parquet_path)
            ratio = parquet_size / csv_size if csv_size > 0 else 0
            
            logger.info(
                "Converted to Parquet",
                csv_path=os.path.basename(csv_path),
                csv_size_mb=round(csv_size / (1024 * 1024), 2),
                parquet_size_mb=round(parquet_size / (1024 * 1024), 2),
                size_ratio=round(ratio, 2)
            )
            
            return True
            
        except Exception as e:
            logger.error("Parquet conversion failed", error=str(e), csv_path=csv_path)
            # Clean up partial parquet file if exists
            if os.path.exists(parquet_path):
                os.remove(parquet_path)
            return False
    
    def download_date(self, date: datetime, force: bool = False) -> Optional[str]:
        """
        Download data for a specific date.
        
        Downloads CSV.gz from Polygon S3, converts to Parquet, returns Parquet path.
        If Parquet already exists and force=False, skips download.
        """
        if not self.s3:
            logger.error("S3 client not initialized")
            return None
        
        s3_key = self._get_s3_key(date)
        csv_path = self._get_local_path(date)
        parquet_path = self._get_parquet_path(date)
        date_str = date.strftime("%Y-%m-%d")
        
        # If Parquet exists and not forcing, return it
        if self.CONVERT_TO_PARQUET and os.path.exists(parquet_path) and not force:
            logger.debug("Parquet exists, skipping", date=date_str)
            return parquet_path
        
        # If CSV exists and not converting to Parquet, return CSV
        if not self.CONVERT_TO_PARQUET and os.path.exists(csv_path) and not force:
            logger.debug("CSV exists, skipping", date=date_str)
            return csv_path
        
        try:
            # Download CSV.gz from S3
            logger.info("Downloading", date=date_str, s3_key=s3_key)
            self.s3.download_file(self.bucket, s3_key, csv_path)
            
            size_mb = os.path.getsize(csv_path) / (1024 * 1024)
            logger.info("Downloaded CSV.gz", date=date_str, size_mb=round(size_mb, 2))
            
            # Convert to Parquet if enabled
            if self.CONVERT_TO_PARQUET:
                success = self._convert_csv_to_parquet(csv_path, parquet_path)
                
                if success:
                    # Optionally delete CSV.gz to save space
                    if not self.KEEP_CSV_AFTER_CONVERT:
                        os.remove(csv_path)
                        logger.debug("Removed CSV.gz after conversion", date=date_str)
                    
                    return parquet_path
                else:
                    # Conversion failed, fall back to CSV
                    logger.warning("Parquet conversion failed, keeping CSV", date=date_str)
                    return csv_path
            
            return csv_path
            
        except self.s3.exceptions.NoSuchKey:
            logger.warning("No data for date", date=date_str)
            return None
        except Exception as e:
            logger.error("Download failed", date=date_str, error=str(e))
            if os.path.exists(csv_path):
                os.remove(csv_path)
            return None
    
    def download_range(
        self,
        start_date: datetime,
        end_date: datetime,
        max_workers: int = 4,
        force: bool = False
    ) -> List[str]:
        """Download data for a date range"""
        dates = []
        current = start_date
        while current <= end_date:
            # Skip weekends
            if current.weekday() < 5:
                dates.append(current)
            current += timedelta(days=1)
        
        logger.info(
            "Starting download range",
            data_type=self.__class__.__name__,
            start=start_date.strftime("%Y-%m-%d"),
            end=end_date.strftime("%Y-%m-%d"),
            trading_days=len(dates),
            workers=max_workers
        )
        
        downloaded = []
        with ThreadPoolExecutor(max_workers=max_workers) as executor:
            futures = {
                executor.submit(self.download_date, date, force): date
                for date in dates
            }
            
            for future in futures:
                result = future.result()
                if result:
                    downloaded.append(result)
        
        logger.info(
            "Download complete",
            downloaded=len(downloaded),
            trading_days=len(dates)
        )
        
        return sorted(downloaded)
    
    def download_last_n_days(self, days: int, force: bool = False) -> List[str]:
        """Download the last N calendar days"""
        end_date = datetime.now()
        start_date = end_date - timedelta(days=days)
        return self.download_range(start_date, end_date, force=force)
    
    def convert_existing_to_parquet(self, max_workers: int = 4, delete_csv: bool = True) -> Dict:
        """
        Convert all existing CSV.gz files to Parquet format.
        
        Use this to migrate existing data to Parquet for better query performance.
        
        Args:
            max_workers: Number of parallel conversion threads
            delete_csv: Whether to delete CSV.gz after successful conversion
            
        Returns:
            Dict with conversion statistics
        """
        if not os.path.exists(self.output_dir):
            return {"error": "Output directory doesn't exist", "converted": 0}
        
        # Find all CSV.gz files without corresponding Parquet
        csv_files = []
        for f in os.listdir(self.output_dir):
            if f.endswith(self.FILE_EXTENSION):
                parquet_name = f.replace(self.FILE_EXTENSION, self.PARQUET_EXTENSION)
                parquet_path = os.path.join(self.output_dir, parquet_name)
                if not os.path.exists(parquet_path):
                    csv_files.append(f)
        
        if not csv_files:
            logger.info("No CSV files to convert", data_type=self.__class__.__name__)
            return {"converted": 0, "skipped": 0, "failed": 0, "message": "All files already converted"}
        
        logger.info(
            "Starting batch conversion to Parquet",
            data_type=self.__class__.__name__,
            files_to_convert=len(csv_files),
            workers=max_workers
        )
        
        results = {"converted": 0, "failed": 0, "space_saved_mb": 0}
        
        def convert_file(csv_name: str) -> bool:
            csv_path = os.path.join(self.output_dir, csv_name)
            parquet_name = csv_name.replace(self.FILE_EXTENSION, self.PARQUET_EXTENSION)
            parquet_path = os.path.join(self.output_dir, parquet_name)
            
            csv_size = os.path.getsize(csv_path)
            success = self._convert_csv_to_parquet(csv_path, parquet_path)
            
            if success and delete_csv:
                os.remove(csv_path)
                return csv_size
            return 0 if success else -1
        
        with ThreadPoolExecutor(max_workers=max_workers) as executor:
            futures = {executor.submit(convert_file, f): f for f in csv_files}
            
            for future in futures:
                result = future.result()
                if result == -1:
                    results["failed"] += 1
                elif result > 0:
                    results["converted"] += 1
                    results["space_saved_mb"] += result / (1024 * 1024)
                else:
                    results["converted"] += 1
        
        results["space_saved_mb"] = round(results["space_saved_mb"], 2)
        
        logger.info(
            "Batch conversion complete",
            data_type=self.__class__.__name__,
            **results
        )
        
        return results
    
    def get_stats(self) -> Dict:
        """Get statistics about downloaded files (both CSV.gz and Parquet)"""
        if not os.path.exists(self.output_dir):
            return {"files_count": 0, "total_size_gb": 0}
        
        all_files = os.listdir(self.output_dir)
        
        csv_files = [f for f in all_files if f.endswith(self.FILE_EXTENSION)]
        parquet_files = [f for f in all_files if f.endswith(self.PARQUET_EXTENSION)]
        
        csv_size = sum(
            os.path.getsize(os.path.join(self.output_dir, f))
            for f in csv_files
        )
        parquet_size = sum(
            os.path.getsize(os.path.join(self.output_dir, f))
            for f in parquet_files
        )
        
        # Get date range from all files
        all_dates = []
        for f in csv_files:
            all_dates.append(f.replace(self.FILE_EXTENSION, ''))
        for f in parquet_files:
            all_dates.append(f.replace(self.PARQUET_EXTENSION, ''))
        all_dates = sorted(set(all_dates))
        
        return {
            "data_type": self.__class__.__name__,
            "csv_files": len(csv_files),
            "parquet_files": len(parquet_files),
            "total_dates": len(all_dates),
            "csv_size_gb": round(csv_size / (1024**3), 3),
            "parquet_size_gb": round(parquet_size / (1024**3), 3),
            "total_size_gb": round((csv_size + parquet_size) / (1024**3), 3),
            "oldest_date": all_dates[0] if all_dates else None,
            "newest_date": all_dates[-1] if all_dates else None,
            "output_dir": self.output_dir,
            "parquet_enabled": self.CONVERT_TO_PARQUET,
        }

