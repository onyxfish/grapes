"""Cluster data model."""

from dataclasses import dataclass, field
from datetime import datetime

from grapes.models.health import HealthStatus
from grapes.models.service import Service


@dataclass
class Cluster:
    """Represents an ECS cluster."""

    name: str
    arn: str
    region: str
    status: str  # ACTIVE, PROVISIONING, DEPROVISIONING, FAILED, INACTIVE

    services: list[Service] = field(default_factory=list)

    # Cluster-level counts (from describe_clusters with STATISTICS)
    active_services_count: int = 0
    running_tasks_count: int = 0
    pending_tasks_count: int = 0
    registered_container_instances_count: int = 0

    # Metadata
    insights_enabled: bool = False
    last_updated: datetime | None = None

    @property
    def service_count(self) -> int:
        """Get total number of services."""
        return len(self.services)

    @property
    def healthy_service_count(self) -> int:
        """Get count of healthy services."""
        return sum(
            1 for s in self.services if s.calculate_health() == HealthStatus.HEALTHY
        )

    @property
    def health_summary(self) -> str:
        """Get health summary as 'healthy/total Healthy'."""
        return f"{self.healthy_service_count}/{self.service_count} Healthy"

    def calculate_health(self) -> HealthStatus:
        """Calculate overall cluster health based on service health."""
        if not self.services:
            return HealthStatus.UNKNOWN

        unhealthy_count = sum(
            1 for s in self.services if s.calculate_health() == HealthStatus.UNHEALTHY
        )
        warning_count = sum(
            1 for s in self.services if s.calculate_health() == HealthStatus.WARNING
        )
        healthy_count = sum(
            1 for s in self.services if s.calculate_health() == HealthStatus.HEALTHY
        )
        unknown_count = sum(
            1 for s in self.services if s.calculate_health() == HealthStatus.UNKNOWN
        )

        if unhealthy_count > 0:
            return HealthStatus.UNHEALTHY
        elif warning_count > 0:
            return HealthStatus.WARNING
        elif healthy_count == len(self.services):
            return HealthStatus.HEALTHY
        elif unknown_count == len(self.services):
            return HealthStatus.UNKNOWN
        else:
            return HealthStatus.WARNING
