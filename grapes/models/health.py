"""Health status enumeration for ECS resources."""

from enum import Enum


class HealthStatus(Enum):
    """Health status for services, tasks, and containers."""

    HEALTHY = "HEALTHY"
    UNHEALTHY = "UNHEALTHY"
    WARNING = "WARNING"
    UNKNOWN = "UNKNOWN"

    @classmethod
    def from_ecs_status(cls, status: str | None) -> "HealthStatus":
        """Convert ECS health status string to HealthStatus enum.

        Args:
            status: ECS health status string (HEALTHY, UNHEALTHY, UNKNOWN, or None)

        Returns:
            Corresponding HealthStatus enum value
        """
        if status is None:
            return cls.UNKNOWN

        status_upper = status.upper()
        if status_upper == "HEALTHY":
            return cls.HEALTHY
        elif status_upper == "UNHEALTHY":
            return cls.UNHEALTHY
        else:
            return cls.UNKNOWN

    @property
    def symbol(self) -> str:
        """Get display symbol for health status."""
        symbols = {
            HealthStatus.HEALTHY: "✓",
            HealthStatus.UNHEALTHY: "✗",
            HealthStatus.WARNING: "⚠",
            HealthStatus.UNKNOWN: "?",
        }
        return symbols[self]

    @property
    def color(self) -> str:
        """Get color name for health status (for Textual/Rich styling)."""
        colors = {
            HealthStatus.HEALTHY: "green",
            HealthStatus.UNHEALTHY: "red",
            HealthStatus.WARNING: "yellow",
            HealthStatus.UNKNOWN: "dim",
        }
        return colors[self]
