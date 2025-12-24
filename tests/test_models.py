"""Tests for data models."""

from datetime import datetime, timezone

from grapes.models import (
    Cluster,
    Container,
    Deployment,
    HealthStatus,
    Service,
    Task,
)


class TestHealthStatus:
    """Tests for HealthStatus enum."""

    def test_from_ecs_status_healthy(self):
        """Test conversion from ECS HEALTHY status."""
        assert HealthStatus.from_ecs_status("HEALTHY") == HealthStatus.HEALTHY
        assert HealthStatus.from_ecs_status("healthy") == HealthStatus.HEALTHY

    def test_from_ecs_status_unhealthy(self):
        """Test conversion from ECS UNHEALTHY status."""
        assert HealthStatus.from_ecs_status("UNHEALTHY") == HealthStatus.UNHEALTHY

    def test_from_ecs_status_unknown(self):
        """Test conversion from unknown status."""
        assert HealthStatus.from_ecs_status("UNKNOWN") == HealthStatus.UNKNOWN
        assert HealthStatus.from_ecs_status(None) == HealthStatus.UNKNOWN
        assert HealthStatus.from_ecs_status("SOMETHING_ELSE") == HealthStatus.UNKNOWN

    def test_symbol(self):
        """Test health status symbols."""
        assert HealthStatus.HEALTHY.symbol == "✓"
        assert HealthStatus.UNHEALTHY.symbol == "✗"
        assert HealthStatus.WARNING.symbol == "⚠"
        assert HealthStatus.UNKNOWN.symbol == "?"

    def test_color(self):
        """Test health status colors."""
        assert HealthStatus.HEALTHY.color == "green"
        assert HealthStatus.UNHEALTHY.color == "red"
        assert HealthStatus.WARNING.color == "yellow"
        assert HealthStatus.UNKNOWN.color == "dim"


class TestContainer:
    """Tests for Container model."""

    def test_cpu_display_with_values(self):
        """Test CPU display when both values are present."""
        container = Container(
            name="test",
            status="RUNNING",
            health_status=HealthStatus.HEALTHY,
            cpu_limit=512,
            cpu_used=25.5,
        )
        assert container.cpu_display == "26% / 0.5 vCPU"

    def test_cpu_display_without_usage(self):
        """Test CPU display when usage is not available."""
        container = Container(
            name="test",
            status="RUNNING",
            health_status=HealthStatus.HEALTHY,
            cpu_limit=512,
            cpu_used=None,
        )
        assert container.cpu_display == "- / 0.5 vCPU"

    def test_cpu_display_without_limit(self):
        """Test CPU display when limit is not set."""
        container = Container(
            name="test",
            status="RUNNING",
            health_status=HealthStatus.HEALTHY,
            cpu_limit=None,
            cpu_used=None,
        )
        assert container.cpu_display == "- / -"

    def test_memory_display_with_values(self):
        """Test memory display when both values are present."""
        container = Container(
            name="test",
            status="RUNNING",
            health_status=HealthStatus.HEALTHY,
            memory_limit=1024,
            memory_used=512,
        )
        assert container.memory_display == "512M / 1 GiB"

    def test_memory_display_without_usage(self):
        """Test memory display when usage is not available."""
        container = Container(
            name="test",
            status="RUNNING",
            health_status=HealthStatus.HEALTHY,
            memory_limit=1024,
            memory_used=None,
        )
        assert container.memory_display == "- / 1 GiB"


class TestTask:
    """Tests for Task model."""

    def test_short_id(self):
        """Test short ID extraction."""
        task = Task(
            id="abc123def456ghi789",
            arn="arn:aws:ecs:us-east-1:123456789:task/cluster/abc123def456ghi789",
            status="RUNNING",
            health_status=HealthStatus.HEALTHY,
            task_definition_arn="arn:aws:ecs:us-east-1:123456789:task-definition/web:5",
        )
        assert task.short_id == "abc123"

    def test_short_id_from_arn_format(self):
        """Test short ID extraction when ID contains slashes."""
        task = Task(
            id="cluster/abc123def456ghi789",
            arn="arn:aws:ecs:us-east-1:123456789:task/cluster/abc123def456ghi789",
            status="RUNNING",
            health_status=HealthStatus.HEALTHY,
            task_definition_arn="arn:aws:ecs:us-east-1:123456789:task-definition/web:5",
        )
        assert task.short_id == "abc123"

    def test_task_definition_name(self):
        """Test task definition name extraction."""
        task = Task(
            id="abc123",
            arn="arn:aws:ecs:us-east-1:123456789:task/cluster/abc123",
            status="RUNNING",
            health_status=HealthStatus.HEALTHY,
            task_definition_arn="arn:aws:ecs:us-east-1:123456789:task-definition/web-service:5",
        )
        assert task.task_definition_name == "web-service:5"

    def test_task_definition_version(self):
        """Test task definition version extraction."""
        task = Task(
            id="abc123",
            arn="arn:aws:ecs:us-east-1:123456789:task/cluster/abc123",
            status="RUNNING",
            health_status=HealthStatus.HEALTHY,
            task_definition_arn="arn:aws:ecs:us-east-1:123456789:task-definition/web-service:5",
        )
        assert task.task_definition_version == ":5"

    def test_started_ago_seconds(self):
        """Test started_ago for tasks started seconds ago."""
        now = datetime.now(timezone.utc)
        task = Task(
            id="abc123",
            arn="arn:aws:ecs:us-east-1:123456789:task/cluster/abc123",
            status="RUNNING",
            health_status=HealthStatus.HEALTHY,
            task_definition_arn="arn:aws:ecs:us-east-1:123456789:task-definition/web:5",
            started_at=now,
        )
        assert "s ago" in task.started_ago or task.started_ago == "0s ago"

    def test_started_ago_none(self):
        """Test started_ago when started_at is None."""
        task = Task(
            id="abc123",
            arn="arn:aws:ecs:us-east-1:123456789:task/cluster/abc123",
            status="RUNNING",
            health_status=HealthStatus.HEALTHY,
            task_definition_arn="arn:aws:ecs:us-east-1:123456789:task-definition/web:5",
            started_at=None,
        )
        assert task.started_ago == "-"

    def test_calculate_health_all_healthy(self):
        """Test health calculation when all containers are healthy."""
        task = Task(
            id="abc123",
            arn="arn:aws:ecs:us-east-1:123456789:task/cluster/abc123",
            status="RUNNING",
            health_status=HealthStatus.UNKNOWN,
            task_definition_arn="arn:aws:ecs:us-east-1:123456789:task-definition/web:5",
            containers=[
                Container(
                    name="app", status="RUNNING", health_status=HealthStatus.HEALTHY
                ),
                Container(
                    name="sidecar", status="RUNNING", health_status=HealthStatus.HEALTHY
                ),
            ],
        )
        assert task.calculate_health() == HealthStatus.HEALTHY

    def test_calculate_health_some_unhealthy(self):
        """Test health calculation when some containers are unhealthy."""
        task = Task(
            id="abc123",
            arn="arn:aws:ecs:us-east-1:123456789:task/cluster/abc123",
            status="RUNNING",
            health_status=HealthStatus.UNKNOWN,
            task_definition_arn="arn:aws:ecs:us-east-1:123456789:task-definition/web:5",
            containers=[
                Container(
                    name="app", status="RUNNING", health_status=HealthStatus.HEALTHY
                ),
                Container(
                    name="sidecar",
                    status="RUNNING",
                    health_status=HealthStatus.UNHEALTHY,
                ),
            ],
        )
        assert task.calculate_health() == HealthStatus.UNHEALTHY

    def test_calculate_health_no_containers(self):
        """Test health calculation with no containers."""
        task = Task(
            id="abc123",
            arn="arn:aws:ecs:us-east-1:123456789:task/cluster/abc123",
            status="RUNNING",
            health_status=HealthStatus.UNKNOWN,
            task_definition_arn="arn:aws:ecs:us-east-1:123456789:task-definition/web:5",
            containers=[],
        )
        assert task.calculate_health() == HealthStatus.UNKNOWN


class TestDeployment:
    """Tests for Deployment model."""

    def test_display_status_primary_running(self):
        """Test display status for PRIMARY deployment with running tasks."""
        deployment = Deployment(
            id="dep-123",
            status="PRIMARY",
            running_count=3,
            desired_count=3,
            pending_count=0,
            task_definition="web:5",
        )
        assert deployment.display_status == "3 running"

    def test_display_status_active_stopping(self):
        """Test display status for ACTIVE deployment (old version draining)."""
        deployment = Deployment(
            id="dep-456",
            status="ACTIVE",
            running_count=2,
            desired_count=0,
            pending_count=0,
            task_definition="web:4",
        )
        assert deployment.display_status == "2 stopping"

    def test_display_status_pending(self):
        """Test display status when tasks are pending."""
        deployment = Deployment(
            id="dep-789",
            status="ACTIVE",
            running_count=0,
            desired_count=3,
            pending_count=2,
            task_definition="web:5",
        )
        assert deployment.display_status == "2 pending"


class TestService:
    """Tests for Service model."""

    def test_tasks_display(self):
        """Test tasks display format."""
        service = Service(
            name="web-service",
            arn="arn:aws:ecs:us-east-1:123456789:service/cluster/web-service",
            status="ACTIVE",
            desired_count=3,
            running_count=2,
            pending_count=1,
            task_definition="web:5",
        )
        assert service.tasks_display == "2/3"

    def test_is_stable_true(self):
        """Test is_stable when service is stable."""
        service = Service(
            name="web-service",
            arn="arn:aws:ecs:us-east-1:123456789:service/cluster/web-service",
            status="ACTIVE",
            desired_count=3,
            running_count=3,
            pending_count=0,
            task_definition="web:5",
            deployments=[
                Deployment(
                    id="dep-123",
                    status="PRIMARY",
                    running_count=3,
                    desired_count=3,
                    pending_count=0,
                    task_definition="web:5",
                ),
            ],
        )
        assert service.is_stable is True

    def test_is_stable_false_multiple_deployments(self):
        """Test is_stable when multiple deployments exist."""
        service = Service(
            name="web-service",
            arn="arn:aws:ecs:us-east-1:123456789:service/cluster/web-service",
            status="ACTIVE",
            desired_count=3,
            running_count=3,
            pending_count=0,
            task_definition="web:5",
            deployments=[
                Deployment(
                    id="dep-123",
                    status="PRIMARY",
                    running_count=2,
                    desired_count=3,
                    pending_count=1,
                    task_definition="web:5",
                ),
                Deployment(
                    id="dep-456",
                    status="ACTIVE",
                    running_count=1,
                    desired_count=0,
                    pending_count=0,
                    task_definition="web:4",
                ),
            ],
        )
        assert service.is_stable is False

    def test_deployment_status_stable(self):
        """Test deployment_status when stable."""
        service = Service(
            name="web-service",
            arn="arn:aws:ecs:us-east-1:123456789:service/cluster/web-service",
            status="ACTIVE",
            desired_count=3,
            running_count=3,
            pending_count=0,
            task_definition="web:5",
            deployments=[
                Deployment(
                    id="dep-123",
                    status="PRIMARY",
                    running_count=3,
                    desired_count=3,
                    pending_count=0,
                    task_definition="web:5",
                ),
            ],
        )
        assert service.deployment_status == "Stable"

    def test_deployment_status_in_progress(self):
        """Test deployment_status during deployment."""
        service = Service(
            name="web-service",
            arn="arn:aws:ecs:us-east-1:123456789:service/cluster/web-service",
            status="ACTIVE",
            desired_count=3,
            running_count=3,
            pending_count=0,
            task_definition="web:5",
            deployments=[
                Deployment(
                    id="dep-123",
                    status="PRIMARY",
                    running_count=2,
                    desired_count=3,
                    pending_count=1,
                    task_definition="web:5",
                ),
                Deployment(
                    id="dep-456",
                    status="ACTIVE",
                    running_count=1,
                    desired_count=0,
                    pending_count=0,
                    task_definition="web:4",
                ),
            ],
        )
        assert service.deployment_status == "In Progress"

    def test_calculate_health_all_healthy(self):
        """Test service health when all tasks are healthy."""
        service = Service(
            name="web-service",
            arn="arn:aws:ecs:us-east-1:123456789:service/cluster/web-service",
            status="ACTIVE",
            desired_count=2,
            running_count=2,
            pending_count=0,
            task_definition="web:5",
            tasks=[
                Task(
                    id="task1",
                    arn="arn:aws:ecs:us-east-1:123456789:task/cluster/task1",
                    status="RUNNING",
                    health_status=HealthStatus.HEALTHY,
                    task_definition_arn="arn:aws:ecs:us-east-1:123456789:task-definition/web:5",
                ),
                Task(
                    id="task2",
                    arn="arn:aws:ecs:us-east-1:123456789:task/cluster/task2",
                    status="RUNNING",
                    health_status=HealthStatus.HEALTHY,
                    task_definition_arn="arn:aws:ecs:us-east-1:123456789:task-definition/web:5",
                ),
            ],
        )
        assert service.calculate_health() == HealthStatus.HEALTHY

    def test_calculate_health_no_running_tasks(self):
        """Test service health when no tasks are running."""
        service = Service(
            name="web-service",
            arn="arn:aws:ecs:us-east-1:123456789:service/cluster/web-service",
            status="ACTIVE",
            desired_count=2,
            running_count=0,
            pending_count=0,
            task_definition="web:5",
            tasks=[],
        )
        assert service.calculate_health() == HealthStatus.UNHEALTHY


class TestCluster:
    """Tests for Cluster model."""

    def test_service_count(self):
        """Test service count."""
        cluster = Cluster(
            name="my-cluster",
            arn="arn:aws:ecs:us-east-1:123456789:cluster/my-cluster",
            region="us-east-1",
            status="ACTIVE",
            services=[
                Service(
                    name="web",
                    arn="arn:aws:ecs:us-east-1:123456789:service/cluster/web",
                    status="ACTIVE",
                    desired_count=1,
                    running_count=1,
                    pending_count=0,
                    task_definition="web:1",
                ),
                Service(
                    name="api",
                    arn="arn:aws:ecs:us-east-1:123456789:service/cluster/api",
                    status="ACTIVE",
                    desired_count=1,
                    running_count=1,
                    pending_count=0,
                    task_definition="api:1",
                ),
            ],
        )
        assert cluster.service_count == 2

    def test_health_summary(self):
        """Test health summary formatting."""
        cluster = Cluster(
            name="my-cluster",
            arn="arn:aws:ecs:us-east-1:123456789:cluster/my-cluster",
            region="us-east-1",
            status="ACTIVE",
            services=[
                Service(
                    name="web",
                    arn="arn:aws:ecs:us-east-1:123456789:service/cluster/web",
                    status="ACTIVE",
                    desired_count=1,
                    running_count=1,
                    pending_count=0,
                    task_definition="web:1",
                    tasks=[
                        Task(
                            id="task1",
                            arn="arn:aws:ecs:us-east-1:123456789:task/cluster/task1",
                            status="RUNNING",
                            health_status=HealthStatus.HEALTHY,
                            task_definition_arn="arn:aws:ecs:us-east-1:123456789:task-definition/web:1",
                        ),
                    ],
                ),
            ],
        )
        assert cluster.health_summary == "1/1 Healthy"
