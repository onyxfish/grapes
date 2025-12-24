"""Task and Container data models."""

from dataclasses import dataclass, field
from datetime import datetime

from grapes.models.health import HealthStatus


@dataclass
class Container:
    """Represents an ECS container within a task."""

    name: str
    status: str  # RUNNING, PENDING, STOPPED, etc.
    health_status: HealthStatus

    # Resource limits (from task definition)
    cpu_limit: int | None = None  # CPU units
    memory_limit: int | None = None  # Memory in MiB

    # Resource utilization (from CloudWatch metrics)
    cpu_used: float | None = None  # CPU percentage
    memory_used: int | None = None  # Memory in MiB

    # Additional info
    exit_code: int | None = None
    reason: str | None = None

    @property
    def cpu_display(self) -> str:
        """Format CPU as 'usage% / X vCPU' or '- / X vCPU'."""
        if self.cpu_limit is not None:
            vcpu = self.cpu_limit / 1024
            if vcpu == int(vcpu):
                limit_str = f"{int(vcpu)} vCPU"
            else:
                limit_str = f"{vcpu} vCPU"
        else:
            limit_str = "-"

        if self.cpu_used is not None:
            return f"{self.cpu_used:.0f}% / {limit_str}"
        return f"- / {limit_str}"

    @property
    def memory_display(self) -> str:
        """Format memory as 'usedM / X GiB/MiB' or '- / X GiB/MiB'."""
        if self.memory_limit is not None:
            if self.memory_limit >= 1024:
                gib = self.memory_limit / 1024
                if gib == int(gib):
                    limit_str = f"{int(gib)} GiB"
                else:
                    limit_str = f"{gib} GiB"
            else:
                limit_str = f"{self.memory_limit} MiB"
        else:
            limit_str = "-"

        if self.memory_used is not None:
            return f"{self.memory_used}M / {limit_str}"
        return f"- / {limit_str}"


@dataclass
class Task:
    """Represents an ECS task."""

    id: str  # Full task ID
    arn: str  # Full task ARN
    status: str  # RUNNING, PENDING, STOPPED, etc.
    health_status: HealthStatus
    task_definition_arn: str
    started_at: datetime | None = None
    stopped_at: datetime | None = None
    stopped_reason: str | None = None
    launch_type: str | None = None  # FARGATE, EC2

    containers: list[Container] = field(default_factory=list)

    @property
    def short_id(self) -> str:
        """Get shortened task ID (first 6 characters)."""
        # Task ID is the last part of the ARN after the final /
        task_id = self.id
        if "/" in task_id:
            task_id = task_id.split("/")[-1]
        return task_id[:6]

    @property
    def task_definition_name(self) -> str:
        """Extract task definition name:revision from ARN."""
        # Format: arn:aws:ecs:region:account:task-definition/name:revision
        if "/" in self.task_definition_arn:
            return self.task_definition_arn.split("/")[-1]
        return self.task_definition_arn

    @property
    def task_definition_version(self) -> str:
        """Extract just the revision number from task definition."""
        name = self.task_definition_name
        if ":" in name:
            return ":" + name.split(":")[-1]
        return name

    @property
    def started_ago(self) -> str:
        """Get human-readable time since task started."""
        if self.started_at is None:
            return "-"

        now = datetime.now(self.started_at.tzinfo)
        delta = now - self.started_at

        seconds = int(delta.total_seconds())
        if seconds < 60:
            return f"{seconds}s ago"
        elif seconds < 3600:
            minutes = seconds // 60
            return f"{minutes}m ago"
        elif seconds < 86400:
            hours = seconds // 3600
            return f"{hours}h ago"
        else:
            days = seconds // 86400
            return f"{days}d ago"

    def calculate_health(self) -> HealthStatus:
        """Calculate task health based on container health statuses.

        Only uses container health checks, no fallback logic.
        """
        if not self.containers:
            return HealthStatus.UNKNOWN

        healthy_count = sum(
            1 for c in self.containers if c.health_status == HealthStatus.HEALTHY
        )
        unhealthy_count = sum(
            1 for c in self.containers if c.health_status == HealthStatus.UNHEALTHY
        )
        unknown_count = sum(
            1 for c in self.containers if c.health_status == HealthStatus.UNKNOWN
        )

        if unhealthy_count > 0:
            return HealthStatus.UNHEALTHY
        elif healthy_count == len(self.containers):
            return HealthStatus.HEALTHY
        elif unknown_count == len(self.containers):
            return HealthStatus.UNKNOWN
        else:
            return HealthStatus.WARNING
