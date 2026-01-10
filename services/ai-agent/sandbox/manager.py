"""
Sandbox Manager

Core component for creating and managing isolated Docker containers
for LLM code execution. Each execution creates an ephemeral container
that is destroyed after completion.

Security Features:
- Network isolation (no internet, no internal network)
- Resource limits (CPU, memory, time)
- Read-only filesystem (except /output)
- Unprivileged execution
- Automatic cleanup on success or failure
"""

import asyncio
import tempfile
import shutil
import uuid
import time
import tarfile
import io
from pathlib import Path
from typing import Dict, Any, Optional, Union
from dataclasses import dataclass
from datetime import datetime
from enum import Enum

import docker
from docker.errors import ContainerError, ImageNotFound, APIError
import structlog

from .config import SandboxConfig, default_config
from .data_injector import DataInjector

logger = structlog.get_logger(__name__)

# Path to DuckDB layer module (relative to this file)
DUCKDB_LAYER_PATH = Path(__file__).parent / "duckdb_layer.py"


class ExecutionStatus(Enum):
    """Status of sandbox execution."""
    SUCCESS = "success"
    ERROR = "error"
    TIMEOUT = "timeout"
    MEMORY_EXCEEDED = "memory_exceeded"
    OUTPUT_TOO_LARGE = "output_too_large"


@dataclass
class ExecutionResult:
    """
    Result of sandbox code execution.
    
    Attributes:
        status: Execution status
        stdout: Standard output from the code
        stderr: Standard error from the code
        exit_code: Container exit code
        output_files: Dictionary of output files {filename: bytes}
        execution_time: Time taken in seconds
        memory_peak: Peak memory usage in bytes (if available)
        error_message: Human-readable error message if failed
    """
    status: ExecutionStatus
    stdout: str
    stderr: str
    exit_code: int
    output_files: Dict[str, bytes]
    execution_time: float
    memory_peak: Optional[int] = None
    error_message: Optional[str] = None
    
    @property
    def success(self) -> bool:
        return self.status == ExecutionStatus.SUCCESS
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "status": self.status.value,
            "success": self.success,
            "stdout": self.stdout,
            "stderr": self.stderr,
            "exit_code": self.exit_code,
            "output_files": list(self.output_files.keys()),
            "execution_time": self.execution_time,
            "memory_peak": self.memory_peak,
            "error_message": self.error_message
        }


class SandboxManager:
    """
    Manages sandbox containers for secure code execution.
    
    Usage:
        manager = SandboxManager()
        
        result = await manager.execute(
            code="import pandas as pd; df = pd.read_parquet('/data/input.parquet'); print(df.describe())",
            data={"input": my_dataframe}
        )
        
        if result.success:
            print(result.stdout)
        else:
            print(f"Error: {result.error_message}")
    """
    
    def __init__(
        self,
        config: Optional[SandboxConfig] = None,
        docker_client: Optional[docker.DockerClient] = None
    ):
        """
        Initialize sandbox manager.
        
        Args:
            config: Sandbox configuration (uses default if None)
            docker_client: Docker client (creates from env if None)
        """
        self.config = config or default_config
        self.config.validate()
        
        self._client = docker_client
        self._injector = DataInjector(max_size=self.config.max_input_size)
    
    @property
    def client(self) -> docker.DockerClient:
        """Lazy initialization of Docker client."""
        if self._client is None:
            self._client = docker.from_env()
        return self._client
    
    async def execute(
        self,
        code: str,
        data: Optional[Dict[str, Any]] = None,
        timeout: Optional[int] = None
    ) -> ExecutionResult:
        """
        Execute code in isolated sandbox.
        
        Args:
            code: Python code to execute
            data: Dictionary of data to inject {name: dataframe/dict/str}
            timeout: Execution timeout (uses config default if None)
        
        Returns:
            ExecutionResult with stdout, stderr, output files
        """
        execution_id = str(uuid.uuid4())[:8]
        timeout = timeout or self.config.timeout_seconds
        start_time = time.time()
        
        logger.info(
            "sandbox_execution_start",
            execution_id=execution_id,
            code_length=len(code),
            data_keys=list(data.keys()) if data else [],
            timeout=timeout
        )
        
        # Create temporary directories
        temp_base = Path(tempfile.mkdtemp(prefix=f"sandbox_{execution_id}_"))
        data_dir = temp_base / "data"
        output_dir = temp_base / "output"
        data_dir.mkdir()
        output_dir.mkdir()
        
        container = None
        
        try:
            # Prepare and write data files
            if data:
                files = self._injector.prepare(data)
                self._injector.write_to_directory(files, data_dir)
            
            # Write the code to execute
            code_file = data_dir / "script.py"
            full_code = self._wrap_code(code, list(data.keys()) if data else [])
            code_file.write_text(full_code)
            
            # Run container
            result = await self._run_container(
                execution_id=execution_id,
                data_dir=data_dir,
                output_dir=output_dir,
                timeout=timeout
            )
            
            execution_time = time.time() - start_time
            result.execution_time = execution_time
            
            logger.info(
                "sandbox_execution_complete",
                execution_id=execution_id,
                status=result.status.value,
                execution_time=execution_time,
                exit_code=result.exit_code
            )
            
            return result
            
        except Exception as e:
            execution_time = time.time() - start_time
            logger.error(
                "sandbox_execution_error",
                execution_id=execution_id,
                error=str(e),
                execution_time=execution_time
            )
            
            return ExecutionResult(
                status=ExecutionStatus.ERROR,
                stdout="",
                stderr=str(e),
                exit_code=-1,
                output_files={},
                execution_time=execution_time,
                error_message=str(e)
            )
            
        finally:
            # Cleanup temporary directory
            try:
                shutil.rmtree(temp_base)
            except Exception as e:
                logger.warning("cleanup_failed", path=str(temp_base), error=str(e))
    
    def _wrap_code(self, code: str, data_names: list) -> str:
        """
        Wrap user code with imports and data loading.
        
        The wrapper:
        1. Imports common libraries
        2. Loads DuckDB layer for historical data access
        3. Loads injected data files
        4. Runs user code
        5. Saves any DataFrames to output
        """
        imports = """
import sys
import json
import warnings
from pathlib import Path
from datetime import datetime, timedelta
import pytz

# Suppress warnings for cleaner output
warnings.filterwarnings('ignore')

# Timezone
ET = pytz.timezone('America/New_York')

# Data science imports
import pandas as pd
import numpy as np

# Optional imports (may not be used)
try:
    import matplotlib
    matplotlib.use('Agg')  # Non-interactive backend
    import matplotlib.pyplot as plt
except ImportError:
    plt = None

try:
    import seaborn as sns
except ImportError:
    sns = None

try:
    import duckdb
except ImportError:
    duckdb = None

# Paths
DATA_DIR = Path('/data')
OUTPUT_DIR = Path('/output')

"""
        
        # Load DuckDB layer if available
        duckdb_layer = ""
        if DUCKDB_LAYER_PATH.exists():
            duckdb_layer = f"""
# ============ DUCKDB LAYER FOR HISTORICAL DATA ============
# Provides: get_minute_bars(), get_top_movers(), historical_query(), available_dates()
{DUCKDB_LAYER_PATH.read_text()}
# ============ END DUCKDB LAYER ============
"""
        imports += duckdb_layer
        
        # Generate data loading code
        data_loading = "# Load injected data\n"
        for name in data_names:
            parquet_path = f"DATA_DIR / '{name}.parquet'"
            json_path = f"DATA_DIR / '{name}.json'"
            data_loading += f"""
try:
    {name} = pd.read_parquet({parquet_path})
except FileNotFoundError:
    try:
        with open({json_path}) as f:
            {name} = json.load(f)
    except FileNotFoundError:
        {name} = None
"""
        
        # Output saving helper
        output_helper = """
# Helper to save output
def save_output(data, name='result'):
    \"\"\"Save data to output directory.\"\"\"
    if isinstance(data, pd.DataFrame):
        data.to_parquet(OUTPUT_DIR / f'{name}.parquet')
    elif isinstance(data, (dict, list)):
        with open(OUTPUT_DIR / f'{name}.json', 'w') as f:
            json.dump(data, f, default=str)
    elif isinstance(data, str):
        (OUTPUT_DIR / f'{name}.txt').write_text(data)
    elif plt is not None and hasattr(plt, 'savefig'):
        plt.savefig(OUTPUT_DIR / f'{name}.png', dpi=150, bbox_inches='tight')
        plt.close()

def save_chart(name='chart'):
    \"\"\"Save current matplotlib figure to output directory.\"\"\"
    if plt is not None:
        plt.savefig(OUTPUT_DIR / f'{name}.png', dpi=150, bbox_inches='tight')
        plt.close()

# ============ TECHNICAL INDICATORS ============
def calculate_rsi(prices, period=14):
    \"\"\"Calculate RSI (Relative Strength Index).\"\"\"
    if len(prices) < period + 1:
        return [None] * len(prices)
    deltas = np.diff(prices)
    gains = np.where(deltas > 0, deltas, 0)
    losses = np.where(deltas < 0, -deltas, 0)
    avg_gain = np.convolve(gains, np.ones(period)/period, mode='valid')
    avg_loss = np.convolve(losses, np.ones(period)/period, mode='valid')
    avg_loss = np.where(avg_loss == 0, 0.0001, avg_loss)
    rs = avg_gain / avg_loss
    rsi = 100 - (100 / (1 + rs))
    return [None] * period + list(rsi)

def calculate_sma(prices, period=20):
    \"\"\"Calculate Simple Moving Average.\"\"\"
    if len(prices) < period:
        return [None] * len(prices)
    sma = np.convolve(prices, np.ones(period)/period, mode='valid')
    return [None] * (period - 1) + list(sma)

def calculate_ema(prices, period=20):
    \"\"\"Calculate Exponential Moving Average.\"\"\"
    if len(prices) < period:
        return [None] * len(prices)
    ema = [None] * (period - 1)
    sma = sum(prices[:period]) / period
    ema.append(sma)
    multiplier = 2 / (period + 1)
    for price in prices[period:]:
        ema.append((price - ema[-1]) * multiplier + ema[-1])
    return ema

def calculate_bollinger(prices, period=20, std_dev=2.0):
    \"\"\"Calculate Bollinger Bands.\"\"\"
    sma = calculate_sma(prices, period)
    upper, lower, middle = [], [], []
    for i, s in enumerate(sma):
        if s is None:
            upper.append(None)
            lower.append(None)
            middle.append(None)
        else:
            window = prices[max(0, i-period+1):i+1]
            std = np.std(window) if len(window) >= period else 0
            upper.append(s + std_dev * std)
            lower.append(s - std_dev * std)
            middle.append(s)
    return {'upper': upper, 'middle': middle, 'lower': lower}

def add_technicals(df, indicators=None):
    \"\"\"Add technical indicators to OHLC DataFrame.\"\"\"
    if 'close' not in df.columns:
        return df
    if indicators is None:
        indicators = ['RSI', 'SMA20']
    prices = df['close'].tolist()
    for ind in indicators:
        ind_upper = ind.upper()
        if ind_upper == 'RSI' or ind_upper == 'RSI14':
            df['rsi'] = calculate_rsi(prices, 14)
        elif ind_upper.startswith('SMA'):
            period = int(ind_upper[3:]) if len(ind_upper) > 3 else 20
            df[f'sma{period}'] = calculate_sma(prices, period)
        elif ind_upper.startswith('EMA'):
            period = int(ind_upper[3:]) if len(ind_upper) > 3 else 20
            df[f'ema{period}'] = calculate_ema(prices, period)
        elif ind_upper == 'BOLLINGER' or ind_upper == 'BB':
            bb = calculate_bollinger(prices)
            df['bb_upper'] = bb['upper']
            df['bb_middle'] = bb['middle']
            df['bb_lower'] = bb['lower']
    return df

def save_plotly_chart(plotly_config, name='chart'):
    \"\"\"Save Plotly chart config as JSON for frontend rendering.\"\"\"
    with open(OUTPUT_DIR / f'{name}_plotly.json', 'w') as f:
        json.dump(plotly_config, f, default=str)

"""
        
        # User code section
        user_code = f"""
# ============ USER CODE START ============
{code}
# ============ USER CODE END ============
"""
        
        return imports + data_loading + output_helper + user_code
    
    async def _run_container(
        self,
        execution_id: str,
        data_dir: Path,
        output_dir: Path,
        timeout: int
    ) -> ExecutionResult:
        """
        Run the Docker container and collect results.
        
        Strategy: Use put_archive to copy files into the container,
        then execute the script. This avoids command line length limits
        and works reliably with Docker-in-Docker setups.
        """
        container_name = f"sandbox_{execution_id}"
        container = None
        
        # Get Docker configuration
        docker_config = self.config.to_docker_config()
        docker_config["name"] = container_name
        
        # We'll use a custom entrypoint that waits, then run the script
        # Command will be set after we copy files
        
        try:
            # Create container with Python sleep to keep it alive
            # Note: Dockerfile has ENTRYPOINT ["python"], so we pass Python code
            container = self.client.containers.create(
                command=["-c", "import time; time.sleep(86400)"],
                **docker_config
            )
            
            # Start the container
            container.start()
            
            # Create tar archive with all data files and script
            tar_buffer = io.BytesIO()
            with tarfile.open(fileobj=tar_buffer, mode='w') as tar:
                # Add data files
                for file_path in data_dir.iterdir():
                    arcname = file_path.name
                    tar.add(str(file_path), arcname=arcname)
            
            # Copy files to /data directory in container
            tar_buffer.seek(0)
            container.put_archive('/data', tar_buffer)
            
            # Execute the script inside the container
            try:
                exec_result = await asyncio.wait_for(
                    asyncio.get_event_loop().run_in_executor(
                        None,
                        lambda: container.exec_run(
                            ["python", "/data/script.py"],
                            workdir="/home/sandbox",
                            environment=self.config.environment,
                            demux=True  # Separate stdout and stderr
                        )
                    ),
                    timeout=timeout + 5
                )
            except asyncio.TimeoutError:
                logger.warning("container_timeout", container=container_name)
                return ExecutionResult(
                    status=ExecutionStatus.TIMEOUT,
                    stdout="",
                    stderr=f"Execution timed out after {timeout} seconds",
                    exit_code=-1,
                    output_files={},
                    execution_time=timeout,
                    error_message=f"Timeout after {timeout}s"
                )
            
            exit_code = exec_result.exit_code
            # demux=True returns tuple (stdout, stderr)
            stdout_bytes, stderr_bytes = exec_result.output or (b'', b'')
            stdout = (stdout_bytes or b'').decode('utf-8', errors='replace')
            stderr = (stderr_bytes or b'').decode('utf-8', errors='replace')
            
            # Collect output files from container using docker cp
            output_files = {}
            total_output_size = 0
            
            try:
                # Get archive from /output directory
                bits, stat = container.get_archive('/output')
                
                # Extract files from tar
                tar_bytes = b''.join(bits)
                tar_buffer = io.BytesIO(tar_bytes)
                
                with tarfile.open(fileobj=tar_buffer, mode='r') as tar:
                    for member in tar.getmembers():
                        if member.isfile():
                            # Skip the 'output/' prefix
                            filename = member.name.split('/')[-1] if '/' in member.name else member.name
                            if not filename:
                                continue
                            
                            file_size = member.size
                            total_output_size += file_size
                            
                            if total_output_size > self.config.max_output_size:
                                return ExecutionResult(
                                    status=ExecutionStatus.OUTPUT_TOO_LARGE,
                                    stdout=stdout,
                                    stderr=stderr,
                                    exit_code=exit_code,
                                    output_files={},
                                    execution_time=0,
                                    error_message=f"Output size exceeds limit ({self.config.max_output_size} bytes)"
                                )
                            
                            f = tar.extractfile(member)
                            if f:
                                output_files[filename] = f.read()
                                
            except Exception as e:
                # No output files or error extracting - not fatal
                logger.debug("output_extraction_warning", error=str(e))
            
            # Determine status
            if exit_code == 0:
                status = ExecutionStatus.SUCCESS
                error_message = None
            elif exit_code == 137:  # OOM killed
                status = ExecutionStatus.MEMORY_EXCEEDED
                error_message = "Process killed: memory limit exceeded"
            else:
                status = ExecutionStatus.ERROR
                error_message = stderr.strip() if stderr else f"Exit code: {exit_code}"
            
            return ExecutionResult(
                status=status,
                stdout=stdout,
                stderr=stderr,
                exit_code=exit_code,
                output_files=output_files,
                execution_time=0,  # Will be set by caller
                error_message=error_message
            )
            
        except ImageNotFound:
            raise RuntimeError(
                f"Sandbox image '{self.config.image}' not found. "
                f"Run: docker build -f Dockerfile.sandbox -t {self.config.image} ."
            )
        except APIError as e:
            raise RuntimeError(f"Docker API error: {e}")
        finally:
            # Cleanup container
            try:
                if container:
                    container.remove(force=True)
            except Exception:
                pass
    
    async def ensure_image_exists(self) -> bool:
        """
        Check if sandbox image exists, build if not.
        
        Returns:
            True if image exists or was built successfully
        """
        try:
            self.client.images.get(self.config.image)
            logger.info("sandbox_image_found", image=self.config.image)
            return True
        except ImageNotFound:
            logger.warning("sandbox_image_not_found", image=self.config.image)
            return False
    
    async def build_image(self, dockerfile_path: str = "Dockerfile.sandbox") -> bool:
        """
        Build the sandbox Docker image.
        
        Args:
            dockerfile_path: Path to Dockerfile
        
        Returns:
            True if build successful
        """
        try:
            logger.info("building_sandbox_image", image=self.config.image)
            
            image, logs = self.client.images.build(
                path=".",
                dockerfile=dockerfile_path,
                tag=self.config.image,
                rm=True
            )
            
            for log in logs:
                if 'stream' in log:
                    logger.debug("build_log", message=log['stream'].strip())
            
            logger.info("sandbox_image_built", image=self.config.image)
            return True
            
        except Exception as e:
            logger.error("sandbox_image_build_failed", error=str(e))
            return False
    
    def health_check(self) -> Dict[str, Any]:
        """
        Check sandbox system health.
        
        Returns:
            Dictionary with health status
        """
        health = {
            "docker_available": False,
            "image_exists": False,
            "config_valid": False,
            "errors": []
        }
        
        # Check Docker
        try:
            self.client.ping()
            health["docker_available"] = True
        except Exception as e:
            health["errors"].append(f"Docker not available: {e}")
        
        # Check image
        try:
            self.client.images.get(self.config.image)
            health["image_exists"] = True
        except ImageNotFound:
            health["errors"].append(f"Image not found: {self.config.image}")
        except Exception as e:
            health["errors"].append(f"Image check failed: {e}")
        
        # Check config
        try:
            self.config.validate()
            health["config_valid"] = True
        except ValueError as e:
            health["errors"].append(f"Config invalid: {e}")
        
        health["healthy"] = all([
            health["docker_available"],
            health["image_exists"],
            health["config_valid"]
        ])
        
        return health

