"""Production configuration for SphinxOS Nexus."""

import os
from dataclasses import dataclass, field
from typing import Dict, Any, Optional


@dataclass
class DatabaseConfig:
    """Database configuration."""
    chain_file: str = "chain.jsonl"
    state_file: str = "chainstate.db"
    compress_chain: bool = True


@dataclass
class P2PConfig:
    """P2P network configuration."""
    listen_host: str = "0.0.0.0"
    listen_port: int = 8333
    max_peers: int = 125
    gossip_k: int = 3
    default_ttl: float = 60.0
    handshake_timeout: float = 30.0
    chain_data_dir: str = "chaindata"


@dataclass
class MiningConfig:
    """Mining configuration."""
    enabled: bool = False
    threads: int = 4
    stratum_url: str = ""
    stratum_user: str = ""
    stratum_pass: str = ""
    target_height: int = 0


@dataclass
class TreasuryConfig:
    """Treasury configuration."""
    annual_yield_rate: float = 0.05
    deployment_threshold: float = 1000.0
    fee_split_treasury: float = 0.5
    fee_split_operator: float = 0.2
    fee_split_rewards: float = 0.3


@dataclass
class LoggingConfig:
    """Logging configuration."""
    level: str = "INFO"
    file: str = "sphinx_os.log"
    max_size_mb: int = 100
    backup_count: int = 5
    format: str = "%(asctime)s - %(name)s - %(levelname)s - %(message)s"


@dataclass
class ProductionConfig:
    """Main production configuration for SphinxOS Nexus.
    
    Usage:
        config = ProductionConfig.load("config.json")
        # or
        config = ProductionConfig.default()
    """
    environment: str = "production"
    data_dir: str = "./data"
    p2p: P2PConfig = field(default_factory=P2PConfig)
    mining: MiningConfig = field(default_factory=MiningConfig)
    treasury: TreasuryConfig = field(default_factory=TreasuryConfig)
    database: DatabaseConfig = field(default_factory=DatabaseConfig)
    logging: LoggingConfig = field(default_factory=LoggingConfig)
    
    @classmethod
    def default(cls) -> "ProductionConfig":
        """Create default production configuration."""
        return cls()
    
    @classmethod
    def development(cls) -> "ProductionConfig":
        """Create development configuration."""
        config = cls()
        config.environment = "development"
        config.logging.level = "DEBUG"
        config.p2p.max_peers = 10
        return config
    
    @classmethod
    def load(cls, path: str) -> "ProductionConfig":
        """Load configuration from a JSON file.
        
        Args:
            path: Path to the configuration file.
            
        Returns:
            ProductionConfig instance.
        """
        import json
        
        if not os.path.exists(path):
            return cls.default()
        
        with open(path, "r") as f:
            data = json.load(f)
        
        config = cls()
        if "environment" in data:
            config.environment = data["environment"]
        if "data_dir" in data:
            config.data_dir = data["data_dir"]
        
        return config
    
    def save(self, path: str) -> None:
        """Save configuration to a JSON file.
        
        Args:
            path: Path to save the configuration.
        """
        import json
        
        data = {
            "environment": self.environment,
            "data_dir": self.data_dir,
            "p2p": {
                "listen_host": self.p2p.listen_host,
                "listen_port": self.p2p.listen_port,
                "max_peers": self.p2p.max_peers,
            },
            "mining": {
                "enabled": self.mining.enabled,
                "threads": self.mining.threads,
            },
            "treasury": {
                "annual_yield_rate": self.treasury.annual_yield_rate,
                "deployment_threshold": self.treasury.deployment_threshold,
            },
            "logging": {
                "level": self.logging.level,
                "file": self.logging.file,
            },
        }
        
        with open(path, "w") as f:
            json.dump(data, f, indent=2)
    
    def validate(self) -> list:
        """Validate configuration and return list of errors.
        
        Returns:
            List of error messages. Empty if valid.
        """
        errors = []
        
        if self.p2p.listen_port < 1 or self.p2p.listen_port > 65535:
            errors.append(f"Invalid P2P port: {self.p2p.listen_port}")
        
        if self.p2p.max_peers < 1:
            errors.append(f"Invalid max peers: {self.p2p.max_peers}")
        
        if self.mining.threads < 1:
            errors.append(f"Invalid mining threads: {self.mining.threads}")
        
        if self.treasury.annual_yield_rate < 0:
            errors.append(f"Invalid yield rate: {self.treasury.annual_yield_rate}")
        
        if self.treasury.deployment_threshold < 0:
            errors.append(f"Invalid deployment threshold: {self.treasury.deployment_threshold}")
        
        valid_levels = {"DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"}
        if self.logging.level not in valid_levels:
            errors.append(f"Invalid log level: {self.logging.level}")
        
        return errors
