"""
R2 Downloader - Downloads pattern index files from Cloudflare R2
"""

import os
from pathlib import Path
import boto3
from botocore.config import Config
import structlog

logger = structlog.get_logger(__name__)


class R2Downloader:
    """Downloads pattern matching files from Cloudflare R2"""
    
    FILES = [
        "pattern-matching/patterns_ivfpq.index",
        "pattern-matching/patterns_metadata.db",
    ]
    
    def __init__(self):
        self.endpoint = os.getenv("R2_ENDPOINT")
        self.access_key = os.getenv("R2_ACCESS_KEY_ID")
        self.secret_key = os.getenv("R2_SECRET_ACCESS_KEY")
        self.bucket = os.getenv("R2_BUCKET", "tradeul-data")
        self.data_dir = Path(os.getenv("DATA_DIR", "/app/data"))
        
        if not all([self.endpoint, self.access_key, self.secret_key]):
            logger.warning("R2 credentials not configured - skipping download")
            self.client = None
            return
        
        self.client = boto3.client(
            "s3",
            endpoint_url=self.endpoint,
            aws_access_key_id=self.access_key,
            aws_secret_access_key=self.secret_key,
            config=Config(
                signature_version="s3v4",
                retries={"max_attempts": 3, "mode": "adaptive"}
            ),
        )
    
    def download_if_missing(self) -> bool:
        """
        Download index files from R2 if they don't exist locally.
        Returns True if files are ready (either existed or downloaded).
        """
        if not self.client:
            logger.info("R2 client not configured, checking local files")
            return self._check_local_files()
        
        all_ready = True
        
        for remote_key in self.FILES:
            filename = Path(remote_key).name
            local_path = self.data_dir / filename
            
            if local_path.exists():
                size_mb = local_path.stat().st_size / (1024 * 1024)
                logger.info(f"File exists locally: {filename}", size_mb=round(size_mb, 1))
                continue
            
            logger.info(f"Downloading from R2: {remote_key}")
            
            try:
                # Ensure directory exists
                local_path.parent.mkdir(parents=True, exist_ok=True)
                
                # Get file size for progress
                response = self.client.head_object(Bucket=self.bucket, Key=remote_key)
                total_size = response["ContentLength"]
                total_gb = total_size / (1024 ** 3)
                
                logger.info(f"Starting download", file=filename, size_gb=round(total_gb, 2))
                
                # Download with progress callback
                downloaded = [0]
                
                def progress_callback(bytes_transferred):
                    downloaded[0] += bytes_transferred
                    percent = (downloaded[0] / total_size) * 100
                    if int(percent) % 10 == 0:  # Log every 10%
                        logger.info(f"Download progress: {filename}", percent=round(percent, 1))
                
                self.client.download_file(
                    Bucket=self.bucket,
                    Key=remote_key,
                    Filename=str(local_path),
                    Callback=progress_callback
                )
                
                logger.info(f"Download complete: {filename}", size_gb=round(total_gb, 2))
                
            except Exception as e:
                logger.error(f"Failed to download {filename}", error=str(e))
                all_ready = False
        
        return all_ready
    
    def _check_local_files(self) -> bool:
        """Check if local files exist"""
        for remote_key in self.FILES:
            filename = Path(remote_key).name
            local_path = self.data_dir / filename
            if not local_path.exists():
                logger.warning(f"Missing local file: {filename}")
                return False
        return True
    
    def upload_to_r2(self, local_path: Path, remote_key: str) -> bool:
        """Upload a file to R2 (for updating index)"""
        if not self.client:
            logger.error("R2 client not configured")
            return False
        
        try:
            size_gb = local_path.stat().st_size / (1024 ** 3)
            logger.info(f"Uploading to R2: {remote_key}", size_gb=round(size_gb, 2))
            
            self.client.upload_file(
                Filename=str(local_path),
                Bucket=self.bucket,
                Key=remote_key
            )
            
            logger.info(f"Upload complete: {remote_key}")
            return True
            
        except Exception as e:
            logger.error(f"Failed to upload {remote_key}", error=str(e))
            return False


def ensure_index_files() -> bool:
    """
    Ensure index files are available.
    Downloads from R2 if not present locally.
    """
    downloader = R2Downloader()
    return downloader.download_if_missing()

