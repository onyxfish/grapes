"""Service and Deployment data models."""

from dataclasses import dataclass, field

from grapes.models.health import HealthStatus
from grapes.models.task import Task


@dataclass
class Deployment:
    """Represents an ECS service deployment."""

    id: str
    status: str  # PRIMARY, ACTIVE, INACTIVE
    running_count: int
    desired_count: int
    pending_count: int
    task_definition: str  # name:revision format
    rollout_state: str | None = None  # COMPLETED, IN_PROGRESS, FAILED
    rollout_state_reason: str | None = None

    @property
    def display_status(self) -> str:
        """Get display-friendly deployment status."""
        if self.status == "PRIMARY":
            return f"{self.running_count} running"
        elif self.running_count > 0:
            return f"{self.running_count} stopping"
        elif self.pending_count > 0:
            return f"{self.pending_count} pending"
        else:
            return "draining"


@dataclass
class Service:
    """Represents an ECS service."""

    name: str
    arn: str
    status: str  # ACTIVE, DRAINING, INACTIVE
    desired_count: int
    running_count: int
    pending_count: int
    task_definition: str  # name:revision format

    deployments: list[Deployment] = field(default_factory=list)
    tasks: list[Task] = field(default_factory=list)

    # Container images from task definition
    images: list[str] = field(default_factory=list)

    # Service-level resource utilization (from CloudWatch metrics)
    cpu_used: float | None = None  # CPU percentage
    memory_used: float | None = None  # Memory percentage

    @property
    def tasks_display(self) -> str:
        """Format task counts as 'running/desired'."""
        return f"{self.running_count}/{self.desired_count}"

    @property
    def is_stable(self) -> bool:
        """Check if service has only one PRIMARY deployment and counts match."""
        if len(self.deployments) != 1:
            return False
        if self.deployments[0].status != "PRIMARY":
            return False
        return self.running_count == self.desired_count

    @property
    def deployment_status(self) -> str:
        """Get human-readable deployment status."""
        if self.is_stable:
            return "Stable"
        elif len(self.deployments) > 1:
            return "In Progress"
        elif self.running_count < self.desired_count:
            return "Scaling"
        else:
            return "Updating"

    def calculate_health(self) -> HealthStatus:
        """Calculate service health based on task health statuses.

        Only uses container health checks from tasks, no fallback logic.
        """
        if self.running_count == 0:
            return HealthStatus.UNHEALTHY

        if self.running_count < self.desired_count:
            return HealthStatus.WARNING

        if not self.tasks:
            return HealthStatus.UNKNOWN

        # Count task health statuses
        healthy_count = sum(
            1 for t in self.tasks if t.health_status == HealthStatus.HEALTHY
        )
        unhealthy_count = sum(
            1 for t in self.tasks if t.health_status == HealthStatus.UNHEALTHY
        )
        unknown_count = sum(
            1 for t in self.tasks if t.health_status == HealthStatus.UNKNOWN
        )

        running_tasks = [t for t in self.tasks if t.status == "RUNNING"]

        if unhealthy_count > 0:
            return HealthStatus.WARNING
        elif healthy_count == len(running_tasks) and len(running_tasks) > 0:
            return HealthStatus.HEALTHY
        elif unknown_count == len(running_tasks):
            return HealthStatus.UNKNOWN
        else:
            return HealthStatus.WARNING

    @property
    def health_display(self) -> str:
        """Format health as 'symbol count/total'."""
        if not self.tasks:
            return "? -/-"

        running_tasks = [t for t in self.tasks if t.status == "RUNNING"]
        healthy_count = sum(
            1 for t in running_tasks if t.health_status == HealthStatus.HEALTHY
        )

        health = self.calculate_health()
        return f"{health.symbol} {healthy_count}/{len(running_tasks)}"

    @property
    def image_display(self) -> str:
        """Format container images for display.

        Shows the image name without registry prefix for brevity.
        If multiple images, shows the first one with a count indicator.
        """
        if not self.images:
            return "-"

        # Get the first image and simplify it
        image = self.images[0]

        # Remove registry prefix (everything before the last /)
        # e.g., "123456789.dkr.ecr.us-east-1.amazonaws.com/my-app:latest" -> "my-app:latest"
        if "/" in image:
            image = image.rsplit("/", 1)[-1]

        if len(self.images) > 1:
            return f"{image} (+{len(self.images) - 1})"
        return image

    @property
    def cpu_display(self) -> str:
        """Format CPU usage as percentage."""
        if self.cpu_used is not None:
            return f"{self.cpu_used:.1f}%"
        return "-"

    @property
    def memory_display(self) -> str:
        """Format memory usage as percentage."""
        if self.memory_used is not None:
            return f"{self.memory_used:.1f}%"
        return "-"
