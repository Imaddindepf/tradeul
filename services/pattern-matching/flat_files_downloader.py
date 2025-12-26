"""
Polygon Flat Files Downloader (S3)
Downloads minute aggregates from Polygon's S3-compatible endpoint
"""

import os
import asyncio
from datetime import datetime, timedelta
from typing import List, Optional
from concurrent.futures import ThreadPoolExecutor

import boto3
from botocore.config import Config
import structlog

from config import settings

logger = structlog.get_logger(__name__)


class FlatFilesDownloader:
    """
    Downloads historical minute aggregates from Polygon Flat Files (S3)
    
    Data is organized as:
    s3://flatfiles/us_stocks_sip/minute_aggs_v1/{year}/{month}/{date}.csv.gz
    """
    
    def __init__(
        self,
        access_key: Optional[str] = None,
        secret_key: Optional[str] = None,
        output_dir: Optional[str] = None
    ):
        self.access_key = access_key or settings.polygon_s3_access_key
        self.secret_key = secret_key or settings.polygon_s3_secret_key
        self.output_dir = output_dir or f"{settings.data_dir}/minute_aggs"
        
        # Initialize S3 client
        session = boto3.Session(
            aws_access_key_id=self.access_key,
            aws_secret_access_key=self.secret_key,
        )
        self.s3 = session.client(
            's3',
            endpoint_url=settings.polygon_s3_endpoint,
            config=Config(signature_version='s3v4'),
        )
        self.bucket = settings.polygon_s3_bucket
        
        # Create output directory
        os.makedirs(self.output_dir, exist_ok=True)
        
        logger.info("FlatFilesDownloader initialized", output_dir=self.output_dir)
    
    def _get_s3_key(self, date: datetime) -> str:
        """Generate S3 key for a specific date"""
        year = date.strftime("%Y")
        month = date.strftime("%m")
        date_str = date.strftime("%Y-%m-%d")
        return f"us_stocks_sip/minute_aggs_v1/{year}/{month}/{date_str}.csv.gz"
    
    def _get_local_path(self, date: datetime) -> str:
        """Generate local path for a specific date"""
        date_str = date.strftime("%Y-%m-%d")
        return f"{self.output_dir}/{date_str}.csv.gz"
    
    def download_date(self, date: datetime, force: bool = False) -> Optional[str]:
        """
        Download minute aggregates for a specific date
        
        Args:
            date: Date to download
            force: Force download even if file exists
            
        Returns:
            Local path if successful, None otherwise
        """
        s3_key = self._get_s3_key(date)
        local_path = self._get_local_path(date)
        date_str = date.strftime("%Y-%m-%d")
        
        # Skip if already exists
        if os.path.exists(local_path) and not force:
            logger.debug("File already exists, skipping", date=date_str)
            return local_path
        
        try:
            logger.info("Downloading", date=date_str, s3_key=s3_key)
            self.s3.download_file(self.bucket, s3_key, local_path)
            
            # Verify file size
            size_mb = os.path.getsize(local_path) / (1024 * 1024)
            logger.info("Downloaded successfully", date=date_str, size_mb=round(size_mb, 2))
            
            return local_path
            
        except self.s3.exceptions.NoSuchKey:
            logger.warning("No data for date (weekend/holiday?)", date=date_str)
            return None
        except Exception as e:
            logger.error("Download failed", date=date_str, error=str(e))
            return None
    
    def download_range(
        self,
        start_date: datetime,
        end_date: datetime,
        max_workers: int = 4,
        force: bool = False
    ) -> List[str]:
        """
        Download minute aggregates for a date range
        
        Args:
            start_date: Start date (inclusive)
            end_date: End date (inclusive)
            max_workers: Number of parallel downloads
            force: Force download even if files exist
            
        Returns:
            List of successfully downloaded file paths
        """
        # Generate list of dates
        dates = []
        current = start_date
        while current <= end_date:
            dates.append(current)
            current += timedelta(days=1)
        
        logger.info(
            "Starting download range",
            start=start_date.strftime("%Y-%m-%d"),
            end=end_date.strftime("%Y-%m-%d"),
            total_dates=len(dates),
            workers=max_workers
        )
        
        # Download in parallel
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
            "Download range complete",
            downloaded=len(downloaded),
            total_dates=len(dates),
            success_rate=f"{len(downloaded)/len(dates)*100:.1f}%"
        )
        
        return sorted(downloaded)
    
    def download_last_n_days(self, days: int, force: bool = False) -> List[str]:
        """Download the last N trading days"""
        end_date = datetime.now()
        start_date = end_date - timedelta(days=days)
        return self.download_range(start_date, end_date, force=force)
    
    def list_available_dates(self, year: int, month: Optional[int] = None) -> List[str]:
        """List available dates in S3"""
        prefix = f"us_stocks_sip/minute_aggs_v1/{year}/"
        if month:
            prefix += f"{month:02d}/"
        
        dates = []
        paginator = self.s3.get_paginator('list_objects_v2')
        
        try:
            for page in paginator.paginate(Bucket=self.bucket, Prefix=prefix):
                for obj in page.get('Contents', []):
                    key = obj['Key']
                    if key.endswith('.csv.gz'):
                        # Extract date from key
                        date_str = key.split('/')[-1].replace('.csv.gz', '')
                        dates.append(date_str)
        except Exception as e:
            logger.error("Failed to list dates", error=str(e))
        
        return sorted(dates)
    
    def get_download_stats(self) -> dict:
        """Get statistics about downloaded files"""
        files = [f for f in os.listdir(self.output_dir) if f.endswith('.csv.gz')]
        total_size = sum(
            os.path.getsize(os.path.join(self.output_dir, f)) 
            for f in files
        )
        
        return {
            "files_count": len(files),
            "total_size_gb": round(total_size / (1024**3), 2),
            "oldest_date": min(files).replace('.csv.gz', '') if files else None,
            "newest_date": max(files).replace('.csv.gz', '') if files else None,
        }


# CLI for manual downloads
if __name__ == "__main__":
    import argparse
    
    parser = argparse.ArgumentParser(description="Download Polygon Flat Files")
    parser.add_argument("--days", type=int, default=30, help="Number of days to download")
    parser.add_argument("--start", type=str, help="Start date (YYYY-MM-DD)")
    parser.add_argument("--end", type=str, help="End date (YYYY-MM-DD)")
    parser.add_argument("--force", action="store_true", help="Force re-download")
    parser.add_argument("--workers", type=int, default=4, help="Parallel workers")
    
    args = parser.parse_args()
    
    downloader = FlatFilesDownloader()
    
    if args.start and args.end:
        start = datetime.strptime(args.start, "%Y-%m-%d")
        end = datetime.strptime(args.end, "%Y-%m-%d")
        downloader.download_range(start, end, max_workers=args.workers, force=args.force)
    else:
        downloader.download_last_n_days(args.days, force=args.force)
    
    print("\n📊 Download Stats:")
    print(downloader.get_download_stats())

