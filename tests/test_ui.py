"""Tests for UI components using Textual's testing framework."""

import pytest
from datetime import datetime, timezone

from textual.app import App, ComposeResult
from textual.widgets import Static

from ecs_monitor.models import (
    Cluster,
    Container,
    Deployment,
    HealthStatus,
    Service,
    Task,
)
from ecs_monitor.ui.cluster_view import ClusterHeader, LoadingScreen
from ecs_monitor.ui.service_view import ServiceList
from ecs_monitor.ui.task_view import ServiceDetailView


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


class TestServiceListWidget:
    """Tests for ServiceList widget."""

    class ServiceListApp(App):
        """Test app for ServiceList."""

        def __init__(self, services: list[Service] | None = None):
            super().__init__()
            self._services = services or []

        def compose(self) -> ComposeResult:
            yield ServiceList(id="service-list")

        def on_mount(self) -> None:
            service_list = self.query_one("#service-list", ServiceList)
            service_list.services = self._services

    @pytest.mark.asyncio
    async def test_service_list_displays_services(self):
        """Test that service list displays services."""
        cluster = create_test_cluster()
        app = self.ServiceListApp(services=cluster.services)

        async with app.run_test():
            service_list = app.query_one("#service-list", ServiceList)
            assert len(service_list.services) == 2

    @pytest.mark.asyncio
    async def test_service_list_empty(self):
        """Test service list with no services."""
        app = self.ServiceListApp(services=[])

        async with app.run_test():
            service_list = app.query_one("#service-list", ServiceList)
            assert len(service_list.services) == 0


class TestServiceDetailViewWidget:
    """Tests for ServiceDetailView widget."""

    class ServiceDetailApp(App):
        """Test app for ServiceDetailView."""

        def __init__(self, service: Service | None = None):
            super().__init__()
            self._service = service

        def compose(self) -> ComposeResult:
            yield ServiceDetailView(id="service-detail")

        def on_mount(self) -> None:
            detail = self.query_one("#service-detail", ServiceDetailView)
            detail.service = self._service

    @pytest.mark.asyncio
    async def test_service_detail_displays_service(self):
        """Test that service detail displays service information."""
        cluster = create_test_cluster()
        service = cluster.services[0]
        app = self.ServiceDetailApp(service=service)

        async with app.run_test():
            detail = app.query_one("#service-detail", ServiceDetailView)
            assert detail.service is not None
            assert detail.service.name == "web-service"

    @pytest.mark.asyncio
    async def test_service_detail_displays_tasks(self):
        """Test that service detail displays tasks."""
        cluster = create_test_cluster()
        service = cluster.services[0]
        app = self.ServiceDetailApp(service=service)

        async with app.run_test():
            detail = app.query_one("#service-detail", ServiceDetailView)
            assert detail.service is not None
            assert len(detail.service.tasks) == 2
