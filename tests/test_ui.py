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
from grapes.ui.service_view import ServiceList
from grapes.ui.task_view import TaskList


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


class TestTaskListWidget:
    """Tests for TaskList widget."""

    class TaskListApp(App):
        """Test app for TaskList."""

        def __init__(self, service: Service | None = None):
            super().__init__()
            self._service = service

        def compose(self) -> ComposeResult:
            yield TaskList(id="task-list")

        def on_mount(self) -> None:
            task_list = self.query_one("#task-list", TaskList)
            task_list.service = self._service

    @pytest.mark.asyncio
    async def test_task_list_displays_service(self):
        """Test that task list displays service information."""
        cluster = create_test_cluster()
        service = cluster.services[0]
        app = self.TaskListApp(service=service)

        async with app.run_test():
            task_list = app.query_one("#task-list", TaskList)
            assert task_list.service is not None
            assert task_list.service.name == "web-service"

    @pytest.mark.asyncio
    async def test_task_list_displays_tasks(self):
        """Test that task list displays tasks."""
        cluster = create_test_cluster()
        service = cluster.services[0]
        app = self.TaskListApp(service=service)

        async with app.run_test():
            task_list = app.query_one("#task-list", TaskList)
            assert task_list.service is not None
            assert len(task_list.service.tasks) == 2


class TestServiceListRaceConditions:
    """Tests for ServiceList race condition handling."""

    class ServiceListWithImmediateSetApp(App):
        """Test app that sets services immediately after mounting (like the real app)."""

        def __init__(self, services: list[Service]):
            super().__init__()
            self._services = services

        def compose(self) -> ComposeResult:
            yield ServiceList(id="service-list")

        def on_mount(self) -> None:
            # This mimics what the real app does: mount then immediately set services
            service_list = self.query_one("#service-list", ServiceList)
            service_list.services = self._services

    class ServiceListWithEarlySetApp(App):
        """Test app that sets services before mount completes."""

        def __init__(self, services: list[Service]):
            super().__init__()
            self._services = services

        def compose(self) -> ComposeResult:
            service_list = ServiceList(id="service-list")
            # Set services immediately during compose, before mount
            service_list.services = self._services
            yield service_list

    class ServiceListMultipleUpdatesApp(App):
        """Test app that updates services multiple times."""

        def __init__(self, services: list[Service]):
            super().__init__()
            self._services = services

        def compose(self) -> ComposeResult:
            yield ServiceList(id="service-list")

        def on_mount(self) -> None:
            service_list = self.query_one("#service-list", ServiceList)
            # Update services multiple times rapidly
            service_list.services = []
            service_list.services = self._services[:1] if self._services else []
            service_list.services = self._services

    @pytest.mark.asyncio
    async def test_service_list_populates_when_set_immediately_after_mount(self):
        """Test that ServiceList populates correctly when services are set immediately after mounting.

        This test mimics the real app behavior where services are set right after
        the widget is mounted. This was causing blank tables due to is_mounted being
        False during on_mount().
        """
        cluster = create_test_cluster()
        app = self.ServiceListWithImmediateSetApp(services=cluster.services)

        async with app.run_test():
            service_list = app.query_one("#service-list", ServiceList)
            table = service_list.query_one("#services-table", DataTable)
            # The table should have rows populated
            assert table.row_count == 2
            assert len(service_list.services) == 2

    @pytest.mark.asyncio
    async def test_service_list_handles_early_service_assignment(self):
        """Test that ServiceList handles services being set before mount."""
        cluster = create_test_cluster()
        app = self.ServiceListWithEarlySetApp(services=cluster.services)

        # This should not raise an error
        async with app.run_test():
            service_list = app.query_one("#service-list", ServiceList)
            # After mount completes, services should be accessible
            assert len(service_list.services) == 2

    @pytest.mark.asyncio
    async def test_service_list_handles_multiple_rapid_updates(self):
        """Test that ServiceList handles multiple rapid service updates."""
        cluster = create_test_cluster()
        app = self.ServiceListMultipleUpdatesApp(services=cluster.services)

        # This should not raise an error
        async with app.run_test():
            service_list = app.query_one("#service-list", ServiceList)
            # Final state should reflect last update
            assert len(service_list.services) == 2

    @pytest.mark.asyncio
    async def test_service_list_update_table_before_mount(self):
        """Test that _update_table handles being called before mount."""

        class DirectUpdateApp(App):
            def compose(self) -> ComposeResult:
                yield ServiceList(id="service-list")

        app = DirectUpdateApp()

        async with app.run_test():
            service_list = app.query_one("#service-list", ServiceList)
            # Manually call _update_table - should not raise
            service_list._update_table()


class TestTaskListRaceConditions:
    """Tests for TaskList race condition handling."""

    class TaskListWithEarlySetApp(App):
        """Test app that sets service before mount completes."""

        def __init__(self, service: Service):
            super().__init__()
            self._service = service

        def compose(self) -> ComposeResult:
            task_list = TaskList(id="task-list")
            # Set service immediately during compose, before mount
            task_list.service = self._service
            yield task_list

    class TaskListMultipleUpdatesApp(App):
        """Test app that updates service multiple times."""

        def __init__(self, service: Service):
            super().__init__()
            self._service = service

        def compose(self) -> ComposeResult:
            yield TaskList(id="task-list")

        def on_mount(self) -> None:
            task_list = self.query_one("#task-list", TaskList)
            # Update service multiple times rapidly
            task_list.service = None
            task_list.service = self._service
            task_list.service = None
            task_list.service = self._service

    @pytest.mark.asyncio
    async def test_task_list_handles_early_service_assignment(self):
        """Test that TaskList handles service being set before mount."""
        cluster = create_test_cluster()
        service = cluster.services[0]
        app = self.TaskListWithEarlySetApp(service=service)

        # This should not raise an error
        async with app.run_test():
            task_list = app.query_one("#task-list", TaskList)
            assert task_list.service is not None
            assert task_list.service.name == "web-service"

    @pytest.mark.asyncio
    async def test_task_list_handles_multiple_rapid_updates(self):
        """Test that TaskList handles multiple rapid service updates."""
        cluster = create_test_cluster()
        service = cluster.services[0]
        app = self.TaskListMultipleUpdatesApp(service=service)

        # This should not raise an error
        async with app.run_test():
            task_list = app.query_one("#task-list", TaskList)
            # Final state should reflect last update
            assert task_list.service is not None
            assert task_list.service.name == "web-service"

    @pytest.mark.asyncio
    async def test_task_list_update_table_before_mount(self):
        """Test that _update_table handles being called before mount."""

        class DirectUpdateApp(App):
            def compose(self) -> ComposeResult:
                yield TaskList(id="task-list")

        app = DirectUpdateApp()

        async with app.run_test():
            task_list = app.query_one("#task-list", TaskList)
            # Manually call _update_table - should not raise
            task_list._update_table()
