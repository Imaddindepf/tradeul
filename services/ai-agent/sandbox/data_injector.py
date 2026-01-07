"""
Data Injector for Sandbox

Handles serialization of data from various sources to Parquet files
that can be safely injected into the sandbox container.

Parquet is chosen for:
1. Efficient compression (smaller files = faster transfer)
2. Type preservation (dates, numbers, strings stay correct)
3. Fast read/write with PyArrow
4. Columnar storage (efficient for analytics)
"""

import io
import json
import tempfile
import shutil
from pathlib import Path
from typing import Dict, Any, Union, List, Optional
from datetime import datetime

import pandas as pd
import pyarrow as pa
import pyarrow.parquet as pq
import structlog

logger = structlog.get_logger(__name__)


class DataInjector:
    """
    Handles data serialization and injection into sandbox.
    
    Supported input types:
    - pandas.DataFrame → Parquet
    - dict/list → JSON or Parquet (if tabular)
    - str → Text file
    - bytes → Binary file
    
    Usage:
        injector = DataInjector(max_size=100_000_000)  # 100MB limit
        
        # Prepare data for injection
        files = injector.prepare({
            "scanner_data": scanner_df,
            "config": {"symbols": ["AAPL", "GOOGL"]},
            "query": "Analyze volatility"
        })
        
        # files is a dict of {filename: bytes}
    """
    
    def __init__(
        self,
        max_size: int = 100 * 1024 * 1024,
        compression: str = "snappy"
    ):
        """
        Initialize data injector.
        
        Args:
            max_size: Maximum total size of all data in bytes
            compression: Parquet compression algorithm (snappy, gzip, zstd)
        """
        self.max_size = max_size
        self.compression = compression
        self._temp_dir: Optional[Path] = None
    
    def prepare(
        self,
        data: Dict[str, Any],
        include_manifest: bool = True
    ) -> Dict[str, bytes]:
        """
        Prepare data for injection into sandbox.
        
        Args:
            data: Dictionary of {name: data} to inject
            include_manifest: Include manifest.json with file descriptions
        
        Returns:
            Dictionary of {filename: bytes} ready to write to container
        
        Raises:
            ValueError: If data exceeds size limit
        """
        result = {}
        manifest = {
            "created_at": datetime.utcnow().isoformat(),
            "files": []
        }
        
        total_size = 0
        
        for name, value in data.items():
            # Determine file type and serialize
            if isinstance(value, pd.DataFrame):
                filename, content = self._serialize_dataframe(name, value)
            elif isinstance(value, (dict, list)):
                # Check if it's tabular (list of dicts)
                if isinstance(value, list) and value and isinstance(value[0], dict):
                    df = pd.DataFrame(value)
                    filename, content = self._serialize_dataframe(name, df)
                else:
                    filename, content = self._serialize_json(name, value)
            elif isinstance(value, str):
                filename, content = self._serialize_text(name, value)
            elif isinstance(value, bytes):
                filename = f"{name}.bin"
                content = value
            else:
                # Try to convert to JSON
                filename, content = self._serialize_json(name, value)
            
            # Check size
            file_size = len(content)
            total_size += file_size
            
            if total_size > self.max_size:
                raise ValueError(
                    f"Data size ({total_size:,} bytes) exceeds limit ({self.max_size:,} bytes)"
                )
            
            result[filename] = content
            manifest["files"].append({
                "name": filename,
                "original_name": name,
                "size": file_size,
                "type": self._get_type_description(value)
            })
            
            logger.debug(
                "data_serialized",
                name=name,
                filename=filename,
                size=file_size
            )
        
        # Add manifest
        if include_manifest:
            manifest["total_size"] = total_size
            manifest["file_count"] = len(result)
            result["manifest.json"] = json.dumps(manifest, indent=2).encode()
        
        logger.info(
            "data_prepared",
            file_count=len(result),
            total_size=total_size
        )
        
        return result
    
    def _serialize_dataframe(
        self,
        name: str,
        df: pd.DataFrame
    ) -> tuple[str, bytes]:
        """Serialize DataFrame to Parquet bytes."""
        filename = f"{name}.parquet"
        
        # Handle empty DataFrames
        if df.empty:
            # Create with schema but no data
            table = pa.Table.from_pandas(df)
            buffer = io.BytesIO()
            pq.write_table(table, buffer, compression=self.compression)
            return filename, buffer.getvalue()
        
        # Optimize dtypes before serialization
        df = self._optimize_dtypes(df)
        
        # Convert to Parquet
        table = pa.Table.from_pandas(df)
        buffer = io.BytesIO()
        pq.write_table(table, buffer, compression=self.compression)
        
        return filename, buffer.getvalue()
    
    def _serialize_json(
        self,
        name: str,
        data: Any
    ) -> tuple[str, bytes]:
        """Serialize data to JSON bytes."""
        filename = f"{name}.json"
        content = json.dumps(data, default=str, indent=2).encode()
        return filename, content
    
    def _serialize_text(
        self,
        name: str,
        text: str
    ) -> tuple[str, bytes]:
        """Serialize text to bytes."""
        filename = f"{name}.txt"
        return filename, text.encode()
    
    def _optimize_dtypes(self, df: pd.DataFrame) -> pd.DataFrame:
        """
        Optimize DataFrame dtypes for smaller Parquet size.
        
        - Downcast integers
        - Downcast floats
        - Convert object columns to category if low cardinality
        """
        df = df.copy()
        
        for col in df.columns:
            col_type = df[col].dtype
            
            # Downcast integers
            if col_type in ['int64', 'int32']:
                df[col] = pd.to_numeric(df[col], downcast='integer')
            
            # Downcast floats
            elif col_type in ['float64']:
                df[col] = pd.to_numeric(df[col], downcast='float')
            
            # Convert low-cardinality strings to category
            elif col_type == 'object':
                num_unique = df[col].nunique()
                num_total = len(df[col])
                if num_unique / num_total < 0.5:  # Less than 50% unique
                    df[col] = df[col].astype('category')
        
        return df
    
    def _get_type_description(self, value: Any) -> str:
        """Get human-readable type description."""
        if isinstance(value, pd.DataFrame):
            return f"DataFrame ({len(value)} rows, {len(value.columns)} cols)"
        elif isinstance(value, list):
            return f"List ({len(value)} items)"
        elif isinstance(value, dict):
            return f"Dict ({len(value)} keys)"
        elif isinstance(value, str):
            return f"Text ({len(value)} chars)"
        elif isinstance(value, bytes):
            return f"Binary ({len(value)} bytes)"
        return type(value).__name__
    
    def create_temp_directory(self) -> Path:
        """
        Create temporary directory for data files.
        
        Returns:
            Path to temporary directory
        """
        self._temp_dir = Path(tempfile.mkdtemp(prefix="sandbox_data_"))
        return self._temp_dir
    
    def write_to_directory(
        self,
        data: Dict[str, bytes],
        directory: Optional[Path] = None
    ) -> Path:
        """
        Write serialized data to directory.
        
        Args:
            data: Dictionary of {filename: bytes}
            directory: Target directory (creates temp if None)
        
        Returns:
            Path to directory containing files
        """
        if directory is None:
            directory = self.create_temp_directory()
        
        directory = Path(directory)
        directory.mkdir(parents=True, exist_ok=True)
        
        for filename, content in data.items():
            filepath = directory / filename
            filepath.write_bytes(content)
            logger.debug("file_written", path=str(filepath), size=len(content))
        
        return directory
    
    def cleanup(self):
        """Remove temporary directory if created."""
        if self._temp_dir and self._temp_dir.exists():
            shutil.rmtree(self._temp_dir)
            logger.debug("temp_dir_cleaned", path=str(self._temp_dir))
            self._temp_dir = None


class CodeGenerator:
    """
    Generates boilerplate code for reading injected data.
    
    The sandbox code needs a standard way to load the data.
    This generates the import statements and data loading code.
    """
    
    @staticmethod
    def generate_loader(files: Dict[str, bytes]) -> str:
        """
        Generate Python code to load all injected data files.
        
        Args:
            files: Dictionary of {filename: bytes}
        
        Returns:
            Python code string
        """
        lines = [
            "# Auto-generated data loader",
            "import pandas as pd",
            "import json",
            "from pathlib import Path",
            "",
            "# Data directory",
            "DATA_DIR = Path('/data')",
            "",
            "# Load data files",
        ]
        
        for filename in files.keys():
            if filename == "manifest.json":
                continue
            
            var_name = Path(filename).stem
            
            if filename.endswith(".parquet"):
                lines.append(f"{var_name} = pd.read_parquet(DATA_DIR / '{filename}')")
            elif filename.endswith(".json"):
                lines.append(f"with open(DATA_DIR / '{filename}') as f:")
                lines.append(f"    {var_name} = json.load(f)")
            elif filename.endswith(".txt"):
                lines.append(f"{var_name} = (DATA_DIR / '{filename}').read_text()")
        
        lines.append("")
        lines.append("# Your analysis code below:")
        lines.append("")
        
        return "\n".join(lines)

