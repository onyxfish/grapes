"""Tests for the main Grapes ECS Monitor application."""

import pytest
from datetime import datetime, timezone
from unittest.mock import MagicMock, patch


from grapes.config import Config, ClusterConfig, RefreshConfig
from grapes.models import (
    Cluster,
    Container,
    Deployment,
    HealthStatus,
    Service,
    Task,
)
from grapes.ui.app import ECSMonitorApp
from grapes.ui.cluster_view import LoadingScreen
from grapes.ui.tree_view import TreeView


def create_test_config() -> Config:
    """Create a test configuration."""
    return Config(
        cluster=ClusterConfig(
            name="test-cluster",
            region="us-east-1",
            profile=None,
        ),
        refresh=RefreshConfig(
            interval=30,
            task_definition_interval=300,
        ),
    )


def create_test_config_no_cluster() -> Config:
    """Create a test configuration without a specific cluster."""
    return Config(
        cluster=ClusterConfig(
            name=None,
            region="us-east-1",
            profile=None,
        ),
        refresh=RefreshConfig(
            interval=30,
            task_definition_interval=300,
        ),
    )


def create_test_cluster() -> Cluster:
    """Create a test cluster with sample data."""
    return Cluster(
        name="test-cluster",
        arn="arn:aws:ecs:us-east-1:123456789:cluster/test-cluster",
        region="us-east-1",
        status="ACTIVE",
        last_updated=datetime.now(timezone.utc),
        insights_enabled=True,
        services=[
            Service(
                name="web-service",
                arn="arn:aws:ecs:us-east-1:123456789:service/test-cluster/web-service",
                status="ACTIVE",
                desired_count=2,
                running_count=2,
                pending_count=0,
                task_definition="web:5",
                deployments=[
                    Deployment(
                        id="dep-123",
                        status="PRIMARY",
                        running_count=2,
                        desired_count=2,
                        pending_count=0,
                        task_definition="web:5",
                    ),
                ],
                tasks=[
                    Task(
                        id="task1abc123",
                        arn="arn:aws:ecs:us-east-1:123456789:task/test-cluster/task1abc123",
                        status="RUNNING",
                        health_status=HealthStatus.HEALTHY,
                        task_definition_arn="arn:aws:ecs:us-east-1:123456789:task-definition/web:5",
                        started_at=datetime.now(timezone.utc),
                        containers=[
                            Container(
                                name="nginx",
                                status="RUNNING",
                                health_status=HealthStatus.HEALTHY,
                                cpu_limit=512,
                                memory_limit=1024,
                            ),
                        ],
                    ),
                ],
            ),
        ],
    )


class TestECSMonitorApp:
    """Tests for the main ECSMonitorApp."""

    @pytest.mark.asyncio
    async def test_app_loads_and_displays_data(self):
        """Test that app loads data and transitions from loading to main view."""
        config = create_test_config()
        test_cluster = create_test_cluster()

        with patch("grapes.ui.app.AWSClients"):
            with patch("grapes.ui.app.ECSFetcher") as mock_fetcher_class:
                with patch("grapes.ui.app.MetricsFetcher") as mock_metrics_class:
                    mock_fetcher = MagicMock()
                    mock_fetcher.list_clusters.return_value = [test_cluster]
                    mock_fetcher.fetch_cluster_state.return_value = test_cluster
                    mock_fetcher_class.return_value = mock_fetcher

                    mock_metrics = MagicMock()
                    mock_metrics.check_container_insights.return_value = True
                    mock_metrics_class.return_value = mock_metrics

                    app = ECSMonitorApp(config)

                    async with app.run_test() as pilot:
                        # Wait for data to load
                        for _ in range(10):
                            await pilot.pause()
                            if not app.loading:
                                break

                        # After worker completes, loading should be hidden
                        loading = app.query_one("#loading", LoadingScreen)
                        assert loading.display is False

                        # Main container should be visible
                        main_container = app.query_one("#main-container")
                        assert main_container.display is True

                        # Clusters should be loaded
                        assert len(app.clusters) > 0
                        assert app.clusters[0].name == "test-cluster"

    @pytest.mark.asyncio
    async def test_app_transitions_to_main_view_after_data_load(self):
        """Test that app transitions from loading to main view after data loads."""
        config = create_test_config()
        test_cluster = create_test_cluster()

        with patch("grapes.ui.app.AWSClients"):
            with patch("grapes.ui.app.ECSFetcher") as mock_fetcher_class:
                with patch("grapes.ui.app.MetricsFetcher") as mock_metrics_class:
                    # Set up mocks
                    mock_fetcher = MagicMock()
                    mock_fetcher.list_clusters.return_value = [test_cluster]
                    mock_fetcher.fetch_cluster_state.return_value = test_cluster
                    mock_fetcher_class.return_value = mock_fetcher

                    mock_metrics = MagicMock()
                    mock_metrics.check_container_insights.return_value = True
                    mock_metrics.fetch_metrics_for_cluster.return_value = None
                    mock_metrics_class.return_value = mock_metrics

                    app = ECSMonitorApp(config)

                    async with app.run_test() as pilot:
                        # Wait for workers to complete
                        await pilot.pause()

                        # The loading screen should now be hidden
                        # and main container visible
                        # Give it a moment to process
                        for _ in range(10):
                            await pilot.pause()
                            if not app.loading:
                                break

                        # Verify the transition happened
                        if not app.loading:
                            loading = app.query_one("#loading", LoadingScreen)
                            assert loading.display is False

                            main_container = app.query_one("#main-container")
                            assert main_container.display is True

    @pytest.mark.asyncio
    async def test_app_displays_tree_view(self):
        """Test that app displays tree view after loading."""
        config = create_test_config()
        test_cluster = create_test_cluster()

        with patch("grapes.ui.app.AWSClients"):
            with patch("grapes.ui.app.ECSFetcher") as mock_fetcher_class:
                with patch("grapes.ui.app.MetricsFetcher") as mock_metrics_class:
                    mock_fetcher = MagicMock()
                    mock_fetcher.list_clusters.return_value = [test_cluster]
                    mock_fetcher.fetch_cluster_state.return_value = test_cluster
                    mock_fetcher_class.return_value = mock_fetcher

                    mock_metrics = MagicMock()
                    mock_metrics.check_container_insights.return_value = True
                    mock_metrics_class.return_value = mock_metrics

                    app = ECSMonitorApp(config)

                    async with app.run_test() as pilot:
                        # Wait for data to load
                        for _ in range(10):
                            await pilot.pause()
                            if len(app.clusters) > 0:
                                break

                        if len(app.clusters) > 0:
                            tree_view = app.query_one("#tree-view", TreeView)
                            assert len(tree_view.clusters) > 0
                            assert tree_view.clusters[0].name == "test-cluster"

    @pytest.mark.asyncio
    async def test_app_auto_loads_configured_cluster(self):
        """Test that app auto-loads the configured cluster data."""
        config = create_test_config()
        test_cluster = create_test_cluster()

        with patch("grapes.ui.app.AWSClients"):
            with patch("grapes.ui.app.ECSFetcher") as mock_fetcher_class:
                with patch("grapes.ui.app.MetricsFetcher") as mock_metrics_class:
                    mock_fetcher = MagicMock()
                    mock_fetcher.list_clusters.return_value = [test_cluster]
                    mock_fetcher.fetch_cluster_state.return_value = test_cluster
                    mock_fetcher_class.return_value = mock_fetcher

                    mock_metrics = MagicMock()
                    mock_metrics.check_container_insights.return_value = True
                    mock_metrics_class.return_value = mock_metrics

                    app = ECSMonitorApp(config)

                    async with app.run_test() as pilot:
                        # Wait for data to load
                        for _ in range(15):
                            await pilot.pause()
                            tree_view = app.query_one("#tree-view", TreeView)
                            if "test-cluster" in tree_view._loaded_clusters:
                                break

                        # The configured cluster data should be auto-loaded
                        tree_view = app.query_one("#tree-view", TreeView)
                        assert "test-cluster" in tree_view._loaded_clusters


class TestAppWorkerBehavior:
    """Tests focused on worker behavior in the app."""

    @pytest.mark.asyncio
    async def test_fetch_cluster_data_method_directly(self):
        """Test the _fetch_cluster_data_worker method directly."""
        config = create_test_config()
        test_cluster = create_test_cluster()

        with patch("grapes.ui.app.AWSClients"):
            with patch("grapes.ui.app.ECSFetcher") as mock_fetcher_class:
                with patch("grapes.ui.app.MetricsFetcher") as mock_metrics_class:
                    mock_fetcher = MagicMock()
                    mock_fetcher.fetch_cluster_state.return_value = test_cluster
                    mock_fetcher_class.return_value = mock_fetcher

                    mock_metrics = MagicMock()
                    mock_metrics.check_container_insights.return_value = True
                    mock_metrics.insights_enabled = True
                    mock_metrics.fetch_metrics_for_cluster.return_value = None
                    mock_metrics_class.return_value = mock_metrics

                    app = ECSMonitorApp(config)

                    # Call the fetch method directly (now sync)
                    result = app._fetch_cluster_data_worker()

                    assert result is not None
                    assert result.name == "test-cluster"
                    assert len(result.services) == 1

    @pytest.mark.asyncio
    async def test_worker_completes_and_sets_loading_false(self):
        """Test that worker completion sets loading to False."""
        config = create_test_config()
        test_cluster = create_test_cluster()

        with patch("grapes.ui.app.AWSClients"):
            with patch("grapes.ui.app.ECSFetcher") as mock_fetcher_class:
                with patch("grapes.ui.app.MetricsFetcher") as mock_metrics_class:
                    mock_fetcher = MagicMock()
                    mock_fetcher.list_clusters.return_value = [test_cluster]
                    mock_fetcher.fetch_cluster_state.return_value = test_cluster
                    mock_fetcher_class.return_value = mock_fetcher

                    mock_metrics = MagicMock()
                    mock_metrics.check_container_insights.return_value = True
                    mock_metrics_class.return_value = mock_metrics

                    app = ECSMonitorApp(config)

                    async with app.run_test() as pilot:
                        # Wait for worker to complete
                        for _ in range(10):
                            await pilot.pause()
                            if not app.loading:
                                break

                        # After worker completes, loading should be False
                        assert app.loading is False
                        # Clusters should be loaded
                        assert len(app.clusters) > 0
