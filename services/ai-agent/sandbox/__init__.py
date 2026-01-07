"""
TradeUL Sandbox Module

Provides secure, isolated execution environment for LLM-generated code.
The sandbox runs in a Docker container with no network access and limited resources.

Architecture:
    - SandboxManager: Creates and manages ephemeral Docker containers
    - DataInjector: Serializes data to Parquet files for injection
    - SandboxConfig: Security and resource configuration

Usage:
    from sandbox import SandboxManager, SandboxConfig
    
    manager = SandboxManager()
    result = await manager.execute(
        code="df = pd.read_parquet('/data/input.parquet'); print(df.head())",
        data_files={"input.parquet": dataframe}
    )
"""

from .config import SandboxConfig
from .manager import SandboxManager
from .data_injector import DataInjector

__all__ = ["SandboxConfig", "SandboxManager", "DataInjector"]

