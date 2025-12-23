"""Unified cluster detail view showing services with nested tasks."""

import logging

from textual.app import ComposeResult
from textual.reactive import reactive
from textual.widgets import DataTable, Static

from grapes.models import Cluster, Service, Task, Container, HealthStatus

logger = logging.getLogger(__name__)


class ClusterDetailView(Static):
    """Widget displaying services and tasks in a unified hierarchical view."""

    cluster: reactive[Cluster | None] = reactive(None)
    _columns_ready: bool = False

    def compose(self) -> ComposeResult:
        """Compose the cluster detail layout."""
        yield Static("[bold]Services & Tasks[/bold]", id="detail-title")
        yield DataTable(id="detail-table")

    def on_mount(self) -> None:
        """Set up the data table when mounted."""
        table = self.query_one("#detail-table", DataTable)
        table.cursor_type = "row"
        table.zebra_stripes = False  # We'll handle styling manually for hierarchy

        # Columns for the unified view
        table.add_column("NAME", key="name")
        table.add_column("STATUS", key="status")
        table.add_column("HEALTH", key="health")
        table.add_column("TASKS", key="tasks")
        table.add_column("CPU", key="cpu")
        table.add_column("MEM", key="mem")
        table.add_column("IMAGE", key="image")
        table.add_column("STARTED", key="started")

        self._columns_ready = True
        self._update_table()
        table.focus()

    def watch_cluster(self, cluster: Cluster | None) -> None:
        """Update display when cluster changes."""
        self._update_table()

    def _update_table(self) -> None:
        """Update the table with services and nested tasks."""
        if not self._columns_ready:
            logger.debug("ClusterDetailView._update_table: columns not ready yet")
            return

        try:
            table = self.query_one("#detail-table", DataTable)
        except Exception:
            logger.debug("ClusterDetailView._update_table: table not found")
            return

        table.clear()

        if self.cluster is None:
            return

        for service in self.cluster.services:
            # Add service row
            self._add_service_row(table, service)

            # Add task rows nested under the service
            for task in service.tasks:
                self._add_task_row(table, service, task)

                # Add container rows nested under the task (if multiple containers)
                if len(task.containers) > 1:
                    for container in task.containers:
                        self._add_container_row(table, service, task, container)

    def _add_service_row(self, table: DataTable, service: Service) -> None:
        """Add a service row to the table."""
        health = service.calculate_health()
        health_display = service.health_display

        # Style health
        health_styled = self._style_health_text(health, health_display)

        # Style status
        if service.status == "ACTIVE":
            status_styled = f"[green]{service.status}[/green]"
        else:
            status_styled = f"[yellow]{service.status}[/yellow]"

        # Service name with icon
        name_display = f"[bold]■ {service.name}[/bold]"

        table.add_row(
            name_display,
            status_styled,
            health_styled,
            service.tasks_display,
            service.cpu_display,
            service.memory_display,
            service.image_display,
            "",  # No started time for services
            key=f"svc_{service.name}",
        )

    def _add_task_row(self, table: DataTable, service: Service, task: Task) -> None:
        """Add a task row to the table."""
        health_styled = self._style_health_symbol(task.health_status)
        status_styled = self._style_task_status(task.status)

        # Indented task name with tree character
        name_display = f"  └─ {task.short_id}"

        # For single-container tasks, show container info inline
        if len(task.containers) == 1:
            container = task.containers[0]
            cpu_display = container.cpu_display
            mem_display = container.memory_display
        else:
            cpu_display = "-"
            mem_display = "-"

        table.add_row(
            name_display,
            status_styled,
            health_styled,
            "",  # No task count for tasks
            cpu_display,
            mem_display,
            "",  # No image for tasks (shown at service level)
            task.started_ago,
            key=f"task_{service.name}_{task.id}",
        )

    def _add_container_row(
        self,
        table: DataTable,
        service: Service,
        task: Task,
        container: Container,
    ) -> None:
        """Add a container row to the table (for multi-container tasks)."""
        health_styled = self._style_health_symbol(container.health_status)

        # Style container status
        if container.status == "RUNNING":
            status_styled = f"[green]{container.status}[/green]"
        else:
            status_styled = f"[yellow]{container.status}[/yellow]"

        # Double-indented container name
        name_display = f"      └─ {container.name}"

        table.add_row(
            name_display,
            status_styled,
            health_styled,
            "",
            container.cpu_display,
            container.memory_display,
            "",  # No image for containers
            "",  # No started time for containers
            key=f"container_{service.name}_{task.id}_{container.name}",
        )

    def _style_health_text(self, health: HealthStatus, text: str) -> str:
        """Style health status text with color."""
        if health == HealthStatus.HEALTHY:
            return f"[green]{text}[/green]"
        elif health == HealthStatus.UNHEALTHY:
            return f"[red]{text}[/red]"
        elif health == HealthStatus.WARNING:
            return f"[yellow]{text}[/yellow]"
        else:
            return f"[dim]{text}[/dim]"

    def _style_health_symbol(self, health: HealthStatus) -> str:
        """Style health status symbol with color."""
        symbol = health.symbol
        if health == HealthStatus.HEALTHY:
            return f"[green]{symbol}[/green]"
        elif health == HealthStatus.UNHEALTHY:
            return f"[red]{symbol}[/red]"
        elif health == HealthStatus.WARNING:
            return f"[yellow]{symbol}[/yellow]"
        else:
            return f"[dim]{symbol}[/dim]"

    def _style_task_status(self, status: str) -> str:
        """Style task status with color."""
        if status == "RUNNING":
            return f"[green]{status}[/green]"
        elif status == "PENDING":
            return f"[yellow]{status}[/yellow]"
        elif status == "STOPPED":
            return f"[red]{status}[/red]"
        else:
            return f"[dim]{status}[/dim]"

    def get_selected_item(self) -> tuple[Service | None, Task | None, Container | None]:
        """Get the currently selected service, task, and/or container.

        Returns:
            Tuple of (service, task, container) - task and container may be None
        """
        if self.cluster is None:
            return None, None, None

        try:
            table = self.query_one("#detail-table", DataTable)
        except Exception:
            return None, None, None

        if table.cursor_row is None:
            return None, None, None

        try:
            row_key = table.get_row_key(table.get_row_at(table.cursor_row))
            if not row_key or not row_key.value:
                return None, None, None

            key_str = str(row_key.value)

            # Parse key format
            if key_str.startswith("svc_"):
                # Service row
                service_name = key_str[4:]
                for service in self.cluster.services:
                    if service.name == service_name:
                        return service, None, None

            elif key_str.startswith("task_"):
                # Task row: task_{service_name}_{task_id}
                parts = key_str[5:].split("_", 1)
                if len(parts) == 2:
                    service_name, task_id = parts
                    for service in self.cluster.services:
                        if service.name == service_name:
                            for task in service.tasks:
                                if task.id == task_id:
                                    return service, task, None

            elif key_str.startswith("container_"):
                # Container row: container_{service_name}_{task_id}_{container_name}
                parts = key_str[10:].split("_", 2)
                if len(parts) == 3:
                    service_name, task_id, container_name = parts
                    for service in self.cluster.services:
                        if service.name == service_name:
                            for task in service.tasks:
                                if task.id == task_id:
                                    for container in task.containers:
                                        if container.name == container_name:
                                            return service, task, container

        except Exception:
            pass

        return None, None, None
