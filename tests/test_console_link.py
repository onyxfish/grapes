"""Tests for AWS Console URL generation."""

from grapes.ui.console_link import (
    build_cluster_url,
    build_service_url,
    build_task_url,
    build_container_url,
)


class TestBuildClusterUrl:
    """Tests for build_cluster_url function."""

    def test_basic_cluster_url(self):
        """Test building a basic cluster URL."""
        url = build_cluster_url("my-cluster", "us-east-1")
        assert (
            url
            == "https://console.aws.amazon.com/ecs/v2/clusters/my-cluster?region=us-east-1"
        )

    def test_cluster_url_different_region(self):
        """Test building cluster URL with different region."""
        url = build_cluster_url("prod-cluster", "eu-west-1")
        assert (
            url
            == "https://console.aws.amazon.com/ecs/v2/clusters/prod-cluster?region=eu-west-1"
        )

    def test_cluster_url_with_special_chars(self):
        """Test cluster URL with cluster name containing special chars."""
        url = build_cluster_url("my-cluster-123", "us-west-2")
        assert (
            url
            == "https://console.aws.amazon.com/ecs/v2/clusters/my-cluster-123?region=us-west-2"
        )


class TestBuildServiceUrl:
    """Tests for build_service_url function."""

    def test_basic_service_url(self):
        """Test building a basic service URL."""
        url = build_service_url("my-cluster", "my-service", "us-east-1")
        expected = "https://console.aws.amazon.com/ecs/v2/clusters/my-cluster/services/my-service?region=us-east-1"
        assert url == expected

    def test_service_url_with_hyphenated_names(self):
        """Test service URL with hyphenated names."""
        url = build_service_url("prod-cluster", "web-api-service", "eu-central-1")
        expected = "https://console.aws.amazon.com/ecs/v2/clusters/prod-cluster/services/web-api-service?region=eu-central-1"
        assert url == expected


class TestBuildTaskUrl:
    """Tests for build_task_url function."""

    def test_basic_task_url(self):
        """Test building a basic task URL."""
        url = build_task_url("my-cluster", "abc123def456", "us-east-1")
        expected = "https://console.aws.amazon.com/ecs/v2/clusters/my-cluster/tasks/abc123def456?region=us-east-1"
        assert url == expected

    def test_task_url_with_full_id(self):
        """Test task URL with full task ID format."""
        task_id = "a1b2c3d4e5f6g7h8i9j0"
        url = build_task_url("cluster-name", task_id, "ap-southeast-1")
        expected = f"https://console.aws.amazon.com/ecs/v2/clusters/cluster-name/tasks/{task_id}?region=ap-southeast-1"
        assert url == expected


class TestBuildContainerUrl:
    """Tests for build_container_url function."""

    def test_basic_container_url(self):
        """Test building a container URL."""
        url = build_container_url("my-cluster", "abc123def456", "us-east-1")
        expected = "https://console.aws.amazon.com/ecs/v2/clusters/my-cluster/tasks/abc123def456?region=us-east-1#containers"
        assert url == expected

    def test_container_url_has_anchor(self):
        """Test that container URL includes #containers anchor."""
        url = build_container_url("cluster", "task-id", "us-west-2")
        assert url.endswith("#containers")
