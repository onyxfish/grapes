"""Configuration loading and validation for ECS Monitor."""

import tomllib
from dataclasses import dataclass
from pathlib import Path


@dataclass
class ClusterConfig:
    """Cluster configuration."""

    name: str | None  # Optional - if None, user selects from list
    region: str
    profile: str | None = None


@dataclass
class RefreshConfig:
    """Refresh interval configuration."""

    interval: int = 30  # seconds
    task_definition_interval: int = 300  # seconds


@dataclass
class Config:
    """Main configuration container."""

    cluster: ClusterConfig
    refresh: RefreshConfig


class ConfigError(Exception):
    """Configuration error."""

    pass


def load_config(config_path: str | Path) -> Config:
    """Load and validate configuration from TOML file.

    Args:
        config_path: Path to the configuration file

    Returns:
        Validated Config object

    Raises:
        ConfigError: If configuration is invalid or missing required fields
    """
    path = Path(config_path)

    if not path.exists():
        raise ConfigError(f"Configuration file not found: {path}")

    try:
        with open(path, "rb") as f:
            data = tomllib.load(f)
    except tomllib.TOMLDecodeError as e:
        raise ConfigError(f"Invalid TOML in configuration file: {e}")

    # Validate cluster section
    if "cluster" not in data:
        raise ConfigError("Missing required [cluster] section in configuration")

    cluster_data = data["cluster"]

    if "region" not in cluster_data:
        raise ConfigError("Missing required 'region' in [cluster] section")

    cluster_config = ClusterConfig(
        name=cluster_data.get("name"),  # Optional - if None, user selects from list
        region=cluster_data["region"],
        profile=cluster_data.get("profile"),
    )

    # Parse refresh section (optional with defaults)
    refresh_data = data.get("refresh", {})
    refresh_config = RefreshConfig(
        interval=refresh_data.get("interval", 30),
        task_definition_interval=refresh_data.get("task_definition_interval", 300),
    )

    # Validate refresh intervals
    if refresh_config.interval < 5:
        raise ConfigError("Refresh interval must be at least 5 seconds")
    if refresh_config.task_definition_interval < 60:
        raise ConfigError(
            "Task definition refresh interval must be at least 60 seconds"
        )

    return Config(cluster=cluster_config, refresh=refresh_config)


def get_default_config_path() -> Path:
    """Get the default configuration file path.

    Searches in order:
    1. ./config.toml
    2. ~/.config/ecs-monitor/config.toml
    """
    # Check current directory first
    local_config = Path("./config.toml")
    if local_config.exists():
        return local_config

    # Check user config directory
    user_config = Path.home() / ".config" / "ecs-monitor" / "config.toml"
    if user_config.exists():
        return user_config

    # Default to local (will fail with helpful error if not found)
    return local_config
