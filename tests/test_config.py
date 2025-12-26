"""Tests for configuration loading."""

import pytest
from pathlib import Path

from grapes.config import load_config, ConfigError, get_default_config_path


class TestLoadConfig:
    """Tests for load_config function."""

    def test_load_valid_config(self, tmp_path):
        """Test loading a valid configuration file."""
        config_file = tmp_path / "config.toml"
        config_file.write_text("""
[cluster]
name = "test-cluster"
region = "us-east-1"
profile = "default"

[refresh]
interval = 30
task_definition_interval = 300
""")
        config = load_config(config_file)

        assert config.cluster.name == "test-cluster"
        assert config.cluster.region == "us-east-1"
        assert config.cluster.profile == "default"
        assert config.refresh.interval == 30
        assert config.refresh.task_definition_interval == 300

    def test_load_config_without_optional_cluster_name(self, tmp_path):
        """Test loading config without optional cluster name."""
        config_file = tmp_path / "config.toml"
        config_file.write_text("""
[cluster]
region = "eu-west-1"
""")
        config = load_config(config_file)

        assert config.cluster.name is None
        assert config.cluster.region == "eu-west-1"
        assert config.cluster.profile is None

    def test_load_config_with_default_refresh_values(self, tmp_path):
        """Test that refresh values have sensible defaults."""
        config_file = tmp_path / "config.toml"
        config_file.write_text("""
[cluster]
region = "us-west-2"
""")
        config = load_config(config_file)

        assert config.refresh.interval == 30
        assert config.refresh.task_definition_interval == 300

    def test_load_config_missing_file(self, tmp_path):
        """Test that missing config file raises ConfigError."""
        config_file = tmp_path / "nonexistent.toml"

        with pytest.raises(ConfigError) as exc_info:
            load_config(config_file)
        assert "not found" in str(exc_info.value)

    def test_load_config_invalid_toml(self, tmp_path):
        """Test that invalid TOML raises ConfigError."""
        config_file = tmp_path / "config.toml"
        config_file.write_text("invalid toml [[[")

        with pytest.raises(ConfigError) as exc_info:
            load_config(config_file)
        assert "Invalid TOML" in str(exc_info.value)

    def test_load_config_missing_cluster_section(self, tmp_path):
        """Test that missing [cluster] section raises ConfigError."""
        config_file = tmp_path / "config.toml"
        config_file.write_text("""
[refresh]
interval = 30
""")
        with pytest.raises(ConfigError) as exc_info:
            load_config(config_file)
        assert "[cluster] section" in str(exc_info.value)

    def test_load_config_missing_region(self, tmp_path):
        """Test that missing region raises ConfigError."""
        config_file = tmp_path / "config.toml"
        config_file.write_text("""
[cluster]
name = "my-cluster"
""")
        with pytest.raises(ConfigError) as exc_info:
            load_config(config_file)
        assert "region" in str(exc_info.value)

    def test_load_config_refresh_interval_too_low(self, tmp_path):
        """Test that refresh interval below minimum raises ConfigError."""
        config_file = tmp_path / "config.toml"
        config_file.write_text("""
[cluster]
region = "us-east-1"

[refresh]
interval = 2
""")
        with pytest.raises(ConfigError) as exc_info:
            load_config(config_file)
        assert "at least 5 seconds" in str(exc_info.value)

    def test_load_config_task_def_interval_too_low(self, tmp_path):
        """Test that task definition interval below minimum raises ConfigError."""
        config_file = tmp_path / "config.toml"
        config_file.write_text("""
[cluster]
region = "us-east-1"

[refresh]
task_definition_interval = 30
""")
        with pytest.raises(ConfigError) as exc_info:
            load_config(config_file)
        assert "at least 60 seconds" in str(exc_info.value)


class TestGetDefaultConfigPath:
    """Tests for get_default_config_path function."""

    def test_returns_path_object(self):
        """Test that function returns a Path object."""
        result = get_default_config_path()
        assert isinstance(result, Path)

    def test_returns_local_config_if_exists(self, tmp_path, monkeypatch):
        """Test that local config.toml is preferred."""
        # Create local config
        config_file = tmp_path / "config.toml"
        config_file.write_text("[cluster]\nregion = 'us-east-1'")

        # Change to temp directory
        monkeypatch.chdir(tmp_path)

        result = get_default_config_path()
        assert result == Path("./config.toml")
        assert result.exists()
