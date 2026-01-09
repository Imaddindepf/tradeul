"""
Sandbox Configuration

Security-first configuration for the isolated execution environment.
All limits are intentionally conservative - better to fail safe than to allow abuse.
"""

import os
from dataclasses import dataclass, field
from typing import Dict, Any, Optional


@dataclass
class SandboxConfig:
    """
    Configuration for sandbox execution environment.
    
    Security Layers:
    1. Network isolation (network_mode: none)
    2. Resource limits (CPU, memory, disk)
    3. Time limits (execution timeout)
    4. Filesystem isolation (read-only except /output)
    5. Unprivileged user execution
    6. No capabilities or privileged mode
    
    Attributes:
        image: Docker image name for sandbox
        timeout_seconds: Maximum execution time before killing container
        memory_limit: Maximum memory (e.g., "512m", "1g")
        cpu_quota: CPU quota in microseconds per 100ms period (50000 = 50%)
        cpu_period: CPU period in microseconds (default 100000 = 100ms)
        max_output_size: Maximum size of output files in bytes
        max_input_size: Maximum size of input data in bytes
        working_dir: Working directory inside container
        data_mount: Mount point for input data (read-only)
        output_mount: Mount point for output data (read-write)
    """
    
    # Docker image
    image: str = "tradeul-sandbox:latest"
    
    # Time limits
    timeout_seconds: int = 30
    
    # Memory limits (1GB needed for large historical datasets ~2M rows)
    memory_limit: str = "1g"
    memory_swap: str = "1g"  # Same as memory to disable swap
    
    # CPU limits
    cpu_quota: int = 50000      # 50% of one CPU
    cpu_period: int = 100000    # 100ms period
    
    # Size limits
    max_output_size: int = 10 * 1024 * 1024   # 10 MB max output
    max_input_size: int = 100 * 1024 * 1024   # 100 MB max input
    
    # Filesystem
    working_dir: str = "/home/sandbox"
    data_mount: str = "/data"
    output_mount: str = "/output"
    
    # Security flags
    network_disabled: bool = True
    # read_only disabled to allow docker cp before container start
    # Security is primarily from network isolation and capability drops
    read_only_rootfs: bool = False
    privileged: bool = False
    
    # Capabilities to drop (drop ALL for maximum security)
    cap_drop: list = field(default_factory=lambda: ["ALL"])
    
    # Security options
    security_opt: list = field(default_factory=lambda: [
        "no-new-privileges:true"
    ])
    
    # Temp directories to mount as tmpfs (writable but ephemeral)
    # Note: /data and /output are NOT tmpfs because put_archive doesn't work with tmpfs
    # They use the container's writable layer instead (still isolated and destroyed on exit)
    tmpfs_mounts: Dict[str, str] = field(default_factory=lambda: {
        "/tmp": "size=64m,mode=1777",
        "/home/sandbox/.cache": "size=32m,mode=777"
    })
    
    # Environment variables for the sandbox
    environment: Dict[str, str] = field(default_factory=lambda: {
        "PYTHONUNBUFFERED": "1",
        "PYTHONDONTWRITEBYTECODE": "1",
        "MPLCONFIGDIR": "/tmp/matplotlib",
        "HOME": "/home/sandbox"
    })
    
    @classmethod
    def from_env(cls) -> "SandboxConfig":
        """
        Create config from environment variables with sensible defaults.
        
        Environment variables:
            SANDBOX_IMAGE: Docker image name
            SANDBOX_TIMEOUT: Execution timeout in seconds
            SANDBOX_MEMORY: Memory limit (e.g., "512m")
            SANDBOX_CPU_PERCENT: CPU percentage (e.g., 50)
        """
        return cls(
            image=os.getenv("SANDBOX_IMAGE", "tradeul-sandbox:latest"),
            timeout_seconds=int(os.getenv("SANDBOX_TIMEOUT", "30")),
            memory_limit=os.getenv("SANDBOX_MEMORY", "512m"),
            cpu_quota=int(os.getenv("SANDBOX_CPU_PERCENT", "50")) * 1000,
        )
    
    # Historical data volume name (Docker volume with Polygon data)
    historical_data_volume: str = "tradeul_polygon_data"
    historical_data_mount: str = "/data/polygon"
    
    def to_docker_config(self) -> Dict[str, Any]:
        """
        Convert to Docker SDK container configuration.
        
        Returns:
            Dict ready to pass to docker.containers.run()
        """
        config = {
            "image": self.image,
            "network_mode": "none" if self.network_disabled else "bridge",
            "mem_limit": self.memory_limit,
            "memswap_limit": self.memory_swap,
            "cpu_quota": self.cpu_quota,
            "cpu_period": self.cpu_period,
            "read_only": self.read_only_rootfs,
            "privileged": self.privileged,
            "cap_drop": self.cap_drop,
            "security_opt": self.security_opt,
            "working_dir": self.working_dir,
            "environment": self.environment,
            "tmpfs": self.tmpfs_mounts,
            "user": "sandbox",
            "auto_remove": False,  # We handle cleanup manually for logging
            "detach": True,
            # Mount historical data volume (read-only for security)
            "volumes": {
                self.historical_data_volume: {
                    "bind": self.historical_data_mount,
                    "mode": "ro"
                }
            }
        }
        
        return config
    
    def validate(self) -> bool:
        """
        Validate configuration for security.
        
        Raises:
            ValueError: If configuration is insecure
        """
        if not self.network_disabled:
            raise ValueError("Network must be disabled for sandbox security")
        
        if self.privileged:
            raise ValueError("Privileged mode is not allowed for sandbox")
        
        if self.timeout_seconds > 300:
            raise ValueError("Timeout cannot exceed 5 minutes")
        
        if self.max_output_size > 100 * 1024 * 1024:
            raise ValueError("Output size cannot exceed 100MB")
        
        return True


# Default configuration instance
default_config = SandboxConfig()


# Strict configuration for production
production_config = SandboxConfig(
    timeout_seconds=30,
    memory_limit="256m",
    cpu_quota=25000,  # 25% CPU
    max_output_size=5 * 1024 * 1024,  # 5 MB
)


# Development configuration (more lenient for testing)
development_config = SandboxConfig(
    timeout_seconds=60,
    memory_limit="1g",
    cpu_quota=100000,  # 100% CPU
    max_output_size=50 * 1024 * 1024,  # 50 MB
)

