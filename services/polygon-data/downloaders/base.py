"""
Base Downloader for Polygon Flat Files
"""

import os
from abc import ABC, abstractmethod
from datetime import datetime, timedelta
from typing import List, Optional, Dict
from concurrent.futures import ThreadPoolExecutor

import boto3
from botocore.config import Config
import structlog

from config import settings

logger = structlog.get_logger(__name__)


class BaseDownloader(ABC):
    """
    Base class for Polygon S3 flat file downloaders
    """
    
    # Override in subclasses
    S3_PREFIX: str = ""
    FILE_EXTENSION: str = ".csv.gz"
    
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
        """Generate local path for a specific date"""
        date_str = date.strftime("%Y-%m-%d")
        return f"{self.output_dir}/{date_str}{self.FILE_EXTENSION}"
    
    def download_date(self, date: datetime, force: bool = False) -> Optional[str]:
        """Download data for a specific date"""
        if not self.s3:
            logger.error("S3 client not initialized")
            return None
        
        s3_key = self._get_s3_key(date)
        local_path = self._get_local_path(date)
        date_str = date.strftime("%Y-%m-%d")
        
        # Skip if already exists
        if os.path.exists(local_path) and not force:
            logger.debug("File exists, skipping", date=date_str)
            return local_path
        
        try:
            logger.info("Downloading", date=date_str, s3_key=s3_key)
            self.s3.download_file(self.bucket, s3_key, local_path)
            
            size_mb = os.path.getsize(local_path) / (1024 * 1024)
            logger.info("Downloaded", date=date_str, size_mb=round(size_mb, 2))
            
            return local_path
            
        except self.s3.exceptions.NoSuchKey:
            logger.warning("No data for date", date=date_str)
            return None
        except Exception as e:
            logger.error("Download failed", date=date_str, error=str(e))
            if os.path.exists(local_path):
                os.remove(local_path)
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
    
    def get_stats(self) -> Dict:
        """Get statistics about downloaded files"""
        if not os.path.exists(self.output_dir):
            return {"files_count": 0, "total_size_gb": 0}
        
        files = [f for f in os.listdir(self.output_dir) if f.endswith(self.FILE_EXTENSION)]
        total_size = sum(
            os.path.getsize(os.path.join(self.output_dir, f))
            for f in files
        )
        
        return {
            "data_type": self.__class__.__name__,
            "files_count": len(files),
            "total_size_gb": round(total_size / (1024**3), 2),
            "oldest_date": min(files).replace(self.FILE_EXTENSION, '') if files else None,
            "newest_date": max(files).replace(self.FILE_EXTENSION, '') if files else None,
            "output_dir": self.output_dir,
        }

