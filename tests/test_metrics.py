"""Tests for CloudWatch metrics fetching."""

import pytest
from datetime import datetime, timezone
from unittest.mock import MagicMock

from grapes.aws.metrics import MetricsFetcher
from grapes.models import Cluster, Service, Task, Container, HealthStatus
from grapes.utils.ids import sanitize_metric_id


class TestMetricsFetcher:
    """Tests for MetricsFetcher class."""

    @pytest.fixture
    def mock_clients(self):
        """Create mock AWS clients."""
        clients = MagicMock()
        clients.region = "us-east-1"
        clients.cluster_name = "test-cluster"
        clients.cloudwatch = MagicMock()
        return clients

    @pytest.fixture
    def fetcher(self, mock_clients):
        """Create a MetricsFetcher with mock clients."""
        return MetricsFetcher(mock_clients)

    def test_check_container_insights_enabled(self, fetcher, mock_clients):
        """Test checking Container Insights when enabled."""
        mock_clients.cloudwatch.get_metric_statistics.return_value = {
            "Datapoints": [{"Average": 50.0}]
        }

        result = fetcher.check_container_insights()

        assert result is True
        assert fetcher._insights_enabled is True

    def test_check_container_insights_disabled(self, fetcher, mock_clients):
        """Test checking Container Insights when disabled."""
        mock_clients.cloudwatch.get_metric_statistics.return_value = {"Datapoints": []}

        result = fetcher.check_container_insights()

        assert result is False
        assert fetcher._insights_enabled is False

    def test_check_container_insights_error(self, fetcher, mock_clients):
        """Test checking Container Insights when API fails."""
        mock_clients.cloudwatch.get_metric_statistics.side_effect = Exception(
            "API error"
        )

        result = fetcher.check_container_insights()

        assert result is False
        assert fetcher._insights_enabled is False

    def test_insights_enabled_property_cached(self, fetcher, mock_clients):
        """Test that insights_enabled property caches result."""
        mock_clients.cloudwatch.get_metric_statistics.return_value = {
            "Datapoints": [{"Average": 50.0}]
        }

        # First access
        _ = fetcher.insights_enabled
        # Second access
        _ = fetcher.insights_enabled

        # Should only call API once
        assert mock_clients.cloudwatch.get_metric_statistics.call_count == 1

    def test_fetch_metrics_for_cluster_empty(self, fetcher, mock_clients):
        """Test fetching metrics for cluster with no services."""
        cluster = Cluster(
            name="test-cluster",
            arn="arn:aws:ecs:us-east-1:123:cluster/test-cluster",
            region="us-east-1",
            status="ACTIVE",
            services=[],
        )

        # Should not raise
        fetcher.fetch_metrics_for_cluster(cluster)

    def test_fetch_metrics_for_cluster_with_services(self, fetcher, mock_clients):
        """Test fetching metrics for cluster with services."""
        service = Service(
            name="my-service",
            arn="arn:aws:ecs:us-east-1:123:service/test-cluster/my-service",
            status="ACTIVE",
            desired_count=2,
            running_count=2,
            pending_count=0,
            task_definition="my-task:1",
            deployments=[],
        )

        cluster = Cluster(
            name="test-cluster",
            arn="arn:aws:ecs:us-east-1:123:cluster/test-cluster",
            region="us-east-1",
            status="ACTIVE",
            services=[service],
        )

        # Mock the CloudWatch get_metric_data response
        mock_clients.cloudwatch.get_metric_data.return_value = {
            "MetricDataResults": [
                {"Id": "cpu_my_service", "Values": [50.0], "StatusCode": "Complete"},
                {"Id": "mem_my_service", "Values": [75.0], "StatusCode": "Complete"},
            ]
        }

        # Disable container insights for this test
        fetcher._insights_enabled = False

        fetcher.fetch_metrics_for_cluster(cluster)

        # Verify get_metric_data was called
        assert mock_clients.cloudwatch.get_metric_data.called

    def test_progress_callback(self, mock_clients):
        """Test that progress callback is called."""
        progress_messages = []

        def on_progress(msg):
            progress_messages.append(msg)

        fetcher = MetricsFetcher(mock_clients, progress_callback=on_progress)

        mock_clients.cloudwatch.get_metric_statistics.return_value = {"Datapoints": []}

        fetcher.check_container_insights()

        assert len(progress_messages) > 0
        assert "Container Insights" in progress_messages[0]


class TestMetricsFetcherHistoryMethods:
    """Tests for historical metrics fetching methods."""

    @pytest.fixture
    def mock_clients(self):
        """Create mock AWS clients."""
        clients = MagicMock()
        clients.region = "us-east-1"
        clients.cluster_name = "test-cluster"
        clients.cloudwatch = MagicMock()
        return clients

    @pytest.fixture
    def fetcher(self, mock_clients):
        """Create a MetricsFetcher with mock clients."""
        f = MetricsFetcher(mock_clients)
        f._insights_enabled = True
        return f

    def test_fetch_service_metrics_history(self, fetcher, mock_clients):
        """Test fetching service metrics history."""
        service_name = "my-service"
        cpu_id = sanitize_metric_id(f"svc_hist_cpu_{service_name}")
        mem_id = sanitize_metric_id(f"svc_hist_mem_{service_name}")

        mock_clients.cloudwatch.get_metric_data.return_value = {
            "MetricDataResults": [
                {
                    "Id": cpu_id,
                    "Values": [50.0, 55.0, 60.0],
                    "Timestamps": [
                        datetime(2024, 1, 1, 12, 0, 0, tzinfo=timezone.utc),
                        datetime(2024, 1, 1, 12, 1, 0, tzinfo=timezone.utc),
                        datetime(2024, 1, 1, 12, 2, 0, tzinfo=timezone.utc),
                    ],
                    "StatusCode": "Complete",
                },
                {
                    "Id": mem_id,
                    "Values": [70.0, 75.0, 80.0],
                    "Timestamps": [
                        datetime(2024, 1, 1, 12, 0, 0, tzinfo=timezone.utc),
                        datetime(2024, 1, 1, 12, 1, 0, tzinfo=timezone.utc),
                        datetime(2024, 1, 1, 12, 2, 0, tzinfo=timezone.utc),
                    ],
                    "StatusCode": "Complete",
                },
            ]
        }

        cpu_history, mem_history, timestamps, cpu_stats, mem_stats = (
            fetcher.fetch_service_metrics_history(service_name, minutes=60)
        )

        assert len(cpu_history) == 3
        assert len(mem_history) == 3
        assert len(timestamps) == 3
        assert cpu_stats is not None
        assert mem_stats is not None

    def test_fetch_container_metrics_history(self, fetcher, mock_clients):
        """Test fetching container metrics history."""
        task = Task(
            id="abc123",
            arn="arn:aws:ecs:us-east-1:123:task/test-cluster/abc123",
            status="RUNNING",
            health_status=HealthStatus.HEALTHY,
            task_definition_arn="arn:aws:ecs:us-east-1:123:task-definition/my-task:1",
            containers=[],
        )

        container = Container(
            name="app",
            status="RUNNING",
            health_status=HealthStatus.HEALTHY,
            cpu_limit=256,
            memory_limit=512,
        )

        # Use the correct metric IDs that the fetcher generates
        cpu_id = sanitize_metric_id(f"hist_cpu_{task.short_id}_{container.name}")
        mem_id = sanitize_metric_id(f"hist_mem_{task.short_id}_{container.name}")

        mock_clients.cloudwatch.get_metric_data.return_value = {
            "MetricDataResults": [
                {
                    "Id": cpu_id,
                    "Values": [10.0, 15.0, 20.0],
                    "Timestamps": [
                        datetime(2024, 1, 1, 12, 0, 0, tzinfo=timezone.utc),
                        datetime(2024, 1, 1, 12, 1, 0, tzinfo=timezone.utc),
                        datetime(2024, 1, 1, 12, 2, 0, tzinfo=timezone.utc),
                    ],
                    "StatusCode": "Complete",
                },
                {
                    "Id": mem_id,
                    "Values": [100.0, 150.0, 200.0],
                    "Timestamps": [
                        datetime(2024, 1, 1, 12, 0, 0, tzinfo=timezone.utc),
                        datetime(2024, 1, 1, 12, 1, 0, tzinfo=timezone.utc),
                        datetime(2024, 1, 1, 12, 2, 0, tzinfo=timezone.utc),
                    ],
                    "StatusCode": "Complete",
                },
            ]
        }

        cpu_history, mem_history, timestamps, cpu_stats, mem_stats = (
            fetcher.fetch_container_metrics_history(task, container, minutes=60)
        )

        assert len(cpu_history) == 3
        assert len(mem_history) == 3
        assert len(timestamps) == 3

    def test_fetch_service_metrics_history_empty(self, fetcher, mock_clients):
        """Test fetching service metrics history when no data available."""
        mock_clients.cloudwatch.get_metric_data.return_value = {
            "MetricDataResults": [
                {"Id": "cpu", "Values": [], "Timestamps": [], "StatusCode": "Complete"},
                {"Id": "mem", "Values": [], "Timestamps": [], "StatusCode": "Complete"},
            ]
        }

        cpu_history, mem_history, timestamps, cpu_stats, mem_stats = (
            fetcher.fetch_service_metrics_history("my-service", minutes=60)
        )

        assert cpu_history == []
        assert mem_history == []
        assert timestamps == []
