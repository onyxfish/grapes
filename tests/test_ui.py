"""Tests for UI components using Textual's testing framework."""

import pytest
from datetime import datetime, timezone

from textual.app import App, ComposeResult
from textual.widgets import DataTable, Static

from grapes.models import (
    Cluster,
    Container,
    Deployment,
    HealthStatus,
    Service,
    Task,
)
from grapes.ui.cluster_view import ClusterHeader, LoadingScreen
from grapes.ui.tree_view import TreeView, RowType


def create_test_cluster() -> Cluster:
    """Create a test cluster with sample data."""
    return Cluster(
        name="test-cluster",
        arn="arn:aws:ecs:us-east-1:123456789:cluster/test-cluster",
        region="us-east-1",
        status="ACTIVE",
        last_updated=datetime.now(timezone.utc),
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
                                cpu_used=10.5,
                                memory_used=256,
                            ),
                        ],
                    ),
                    Task(
                        id="task2def456",
                        arn="arn:aws:ecs:us-east-1:123456789:task/test-cluster/task2def456",
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
                                cpu_used=15.2,
                                memory_used=300,
                            ),
                        ],
                    ),
                ],
            ),
            Service(
                name="api-service",
                arn="arn:aws:ecs:us-east-1:123456789:service/test-cluster/api-service",
                status="ACTIVE",
                desired_count=1,
                running_count=1,
                pending_count=0,
                task_definition="api:3",
                deployments=[
                    Deployment(
                        id="dep-456",
                        status="PRIMARY",
                        running_count=1,
                        desired_count=1,
                        pending_count=0,
                        task_definition="api:3",
                    ),
                ],
                tasks=[
                    Task(
                        id="task3ghi789",
                        arn="arn:aws:ecs:us-east-1:123456789:task/test-cluster/task3ghi789",
                        status="RUNNING",
                        health_status=HealthStatus.HEALTHY,
                        task_definition_arn="arn:aws:ecs:us-east-1:123456789:task-definition/api:3",
                        started_at=datetime.now(timezone.utc),
                        containers=[
                            Container(
                                name="app",
                                status="RUNNING",
                                health_status=HealthStatus.HEALTHY,
                                cpu_limit=256,
                                memory_limit=512,
                            ),
                        ],
                    ),
                ],
            ),
        ],
    )


def create_second_test_cluster() -> Cluster:
    """Create a second test cluster for multi-cluster tests."""
    return Cluster(
        name="prod-cluster",
        arn="arn:aws:ecs:us-east-1:123456789:cluster/prod-cluster",
        region="us-east-1",
        status="ACTIVE",
        last_updated=datetime.now(timezone.utc),
        services=[],
    )


class TestClusterHeaderWidget:
    """Tests for ClusterHeader widget."""

    class ClusterHeaderApp(App):
        """Test app for ClusterHeader."""

        def __init__(self, cluster: Cluster | None = None, insights: bool = True):
            super().__init__()
            self._cluster = cluster
            self._insights = insights

        def compose(self) -> ComposeResult:
            header = ClusterHeader(id="header")
            yield header

        def on_mount(self) -> None:
            header = self.query_one("#header", ClusterHeader)
            header.cluster = self._cluster
            header.insights_enabled = self._insights

    @pytest.mark.asyncio
    async def test_cluster_header_displays_cluster_info(self):
        """Test that cluster header displays cluster information."""
        cluster = create_test_cluster()
        app = self.ClusterHeaderApp(cluster=cluster, insights=True)

        async with app.run_test():
            header = app.query_one("#header", ClusterHeader)
            assert header.cluster is not None
            assert header.cluster.name == "test-cluster"

    @pytest.mark.asyncio
    async def test_cluster_header_shows_insights_warning(self):
        """Test that insights warning is shown when disabled."""
        cluster = create_test_cluster()
        app = self.ClusterHeaderApp(cluster=cluster, insights=False)

        async with app.run_test():
            header = app.query_one("#header", ClusterHeader)
            assert header.insights_enabled is False
            # The warning widget should be visible
            warning = header.query_one("#insights-warning", Static)
            assert warning.display is True

    @pytest.mark.asyncio
    async def test_cluster_header_hides_insights_warning_when_enabled(self):
        """Test that insights warning is hidden when enabled."""
        cluster = create_test_cluster()
        app = self.ClusterHeaderApp(cluster=cluster, insights=True)

        async with app.run_test():
            header = app.query_one("#header", ClusterHeader)
            warning = header.query_one("#insights-warning", Static)
            assert warning.display is False


class TestLoadingScreenWidget:
    """Tests for LoadingScreen widget."""

    class LoadingScreenApp(App):
        """Test app for LoadingScreen."""

        def compose(self) -> ComposeResult:
            yield LoadingScreen(id="loading")

    @pytest.mark.asyncio
    async def test_loading_screen_mounts(self):
        """Test that loading screen mounts correctly."""
        app = self.LoadingScreenApp()

        async with app.run_test():
            loading = app.query_one("#loading", LoadingScreen)
            assert loading is not None

    @pytest.mark.asyncio
    async def test_loading_screen_update_status(self):
        """Test that loading screen status can be updated."""
        app = self.LoadingScreenApp()

        async with app.run_test():
            loading = app.query_one("#loading", LoadingScreen)
            loading.update_status("Fetching services...")
            assert loading.status_message == "Fetching services..."


class TestTreeViewWidget:
    """Tests for TreeView widget."""

    class TreeViewApp(App):
        """Test app for TreeView."""

        def __init__(self, clusters: list[Cluster] | None = None):
            super().__init__()
            self._clusters = clusters or []

        def compose(self) -> ComposeResult:
            yield TreeView(id="tree-view")

        def on_mount(self) -> None:
            tree_view = self.query_one("#tree-view", TreeView)
            tree_view.clusters = self._clusters

    @pytest.mark.asyncio
    async def test_tree_view_displays_clusters(self):
        """Test that tree view displays clusters."""
        cluster = create_test_cluster()
        app = self.TreeViewApp(clusters=[cluster])

        async with app.run_test():
            tree_view = app.query_one("#tree-view", TreeView)
            assert len(tree_view.clusters) == 1
            assert tree_view.clusters[0].name == "test-cluster"

    @pytest.mark.asyncio
    async def test_tree_view_empty(self):
        """Test tree view with no clusters."""
        app = self.TreeViewApp(clusters=[])

        async with app.run_test():
            tree_view = app.query_one("#tree-view", TreeView)
            assert len(tree_view.clusters) == 0

    @pytest.mark.asyncio
    async def test_tree_view_displays_multiple_clusters(self):
        """Test that tree view displays multiple clusters."""
        cluster1 = create_test_cluster()
        cluster2 = create_second_test_cluster()
        app = self.TreeViewApp(clusters=[cluster1, cluster2])

        async with app.run_test():
            tree_view = app.query_one("#tree-view", TreeView)
            assert len(tree_view.clusters) == 2

    @pytest.mark.asyncio
    async def test_tree_view_update_cluster_data(self):
        """Test that tree view can update cluster data."""
        cluster = create_test_cluster()
        # Create a basic cluster without services for initial display
        basic_cluster = Cluster(
            name="test-cluster",
            arn=cluster.arn,
            region=cluster.region,
            status=cluster.status,
            last_updated=cluster.last_updated,
            services=[],
        )
        app = self.TreeViewApp(clusters=[basic_cluster])

        async with app.run_test():
            tree_view = app.query_one("#tree-view", TreeView)
            # Update with full cluster data
            tree_view.update_cluster_data(cluster)
            assert "test-cluster" in tree_view._loaded_clusters
            assert len(tree_view._loaded_clusters["test-cluster"].services) == 2


class TestTreeViewNavigation:
    """Tests for TreeView navigation."""

    class TreeViewNavApp(App):
        """Test app for TreeView navigation."""

        def __init__(self, clusters: list[Cluster]):
            super().__init__()
            self._clusters = clusters

        def compose(self) -> ComposeResult:
            yield TreeView(id="tree-view")

        def on_mount(self) -> None:
            tree_view = self.query_one("#tree-view", TreeView)
            tree_view.clusters = self._clusters
            # Load the cluster data
            for cluster in self._clusters:
                tree_view.update_cluster_data(cluster)

    @pytest.mark.asyncio
    async def test_tree_view_get_selected_item(self):
        """Test that tree view can return the selected item."""
        cluster = create_test_cluster()
        app = self.TreeViewNavApp(clusters=[cluster])

        async with app.run_test():
            tree_view = app.query_one("#tree-view", TreeView)
            # First row should be the cluster
            selected_cluster, service, task, container = tree_view.get_selected_item()
            assert selected_cluster is not None
            assert selected_cluster.name == "test-cluster"
            assert service is None
            assert task is None

    @pytest.mark.asyncio
    async def test_tree_view_row_type_detection(self):
        """Test that tree view correctly identifies row types."""
        cluster = create_test_cluster()
        app = self.TreeViewNavApp(clusters=[cluster])

        async with app.run_test():
            tree_view = app.query_one("#tree-view", TreeView)
            # First row should be a cluster
            row_type = tree_view.get_current_row_type()
            assert row_type == RowType.CLUSTER


class TestTreeViewRaceConditions:
    """Tests for TreeView race condition handling."""

    class TreeViewWithImmediateSetApp(App):
        """Test app that sets clusters immediately after mounting."""

        def __init__(self, clusters: list[Cluster]):
            super().__init__()
            self._clusters = clusters

        def compose(self) -> ComposeResult:
            yield TreeView(id="tree-view")

        def on_mount(self) -> None:
            tree_view = self.query_one("#tree-view", TreeView)
            tree_view.clusters = self._clusters

    class TreeViewWithEarlySetApp(App):
        """Test app that sets clusters before mount completes."""

        def __init__(self, clusters: list[Cluster]):
            super().__init__()
            self._clusters = clusters

        def compose(self) -> ComposeResult:
            tree_view = TreeView(id="tree-view")
            tree_view.clusters = self._clusters
            yield tree_view

    class TreeViewMultipleUpdatesApp(App):
        """Test app that updates clusters multiple times."""

        def __init__(self, clusters: list[Cluster]):
            super().__init__()
            self._clusters = clusters

        def compose(self) -> ComposeResult:
            yield TreeView(id="tree-view")

        def on_mount(self) -> None:
            tree_view = self.query_one("#tree-view", TreeView)
            tree_view.clusters = []
            tree_view.clusters = self._clusters[:1] if self._clusters else []
            tree_view.clusters = self._clusters

    @pytest.mark.asyncio
    async def test_tree_view_populates_when_set_immediately_after_mount(self):
        """Test that TreeView populates correctly when clusters are set immediately."""
        cluster = create_test_cluster()
        app = self.TreeViewWithImmediateSetApp(clusters=[cluster])

        async with app.run_test():
            tree_view = app.query_one("#tree-view", TreeView)
            table = tree_view.query_one("#tree-table", DataTable)
            # The table should have at least the cluster row
            assert table.row_count >= 1
            assert len(tree_view.clusters) == 1

    @pytest.mark.asyncio
    async def test_tree_view_handles_early_cluster_assignment(self):
        """Test that TreeView handles clusters being set before mount."""
        cluster = create_test_cluster()
        app = self.TreeViewWithEarlySetApp(clusters=[cluster])

        async with app.run_test():
            tree_view = app.query_one("#tree-view", TreeView)
            assert len(tree_view.clusters) == 1

    @pytest.mark.asyncio
    async def test_tree_view_handles_multiple_rapid_updates(self):
        """Test that TreeView handles multiple rapid cluster updates."""
        cluster = create_test_cluster()
        app = self.TreeViewMultipleUpdatesApp(clusters=[cluster])

        async with app.run_test():
            tree_view = app.query_one("#tree-view", TreeView)
            assert len(tree_view.clusters) == 1

    @pytest.mark.asyncio
    async def test_tree_view_update_table_before_mount(self):
        """Test that _update_table handles being called before mount."""

        class DirectUpdateApp(App):
            def compose(self) -> ComposeResult:
                yield TreeView(id="tree-view")

        app = DirectUpdateApp()

        async with app.run_test():
            tree_view = app.query_one("#tree-view", TreeView)
            tree_view._update_table()
