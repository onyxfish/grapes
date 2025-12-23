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
    _folded_services: set[str]  # Set of folded service names

    def __init__(self, *args, **kwargs) -> None:
        """Initialize the cluster detail view."""
        super().__init__(*args, **kwargs)
        self._folded_services = set()

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
        # Reset folded state when cluster changes
        if cluster is None:
            self._folded_services = set()
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
            is_folded = service.name in self._folded_services

            # Add service row
            self._add_service_row(table, service, is_folded)

            # Add task rows nested under the service (if not folded)
            if not is_folded:
                for task in service.tasks:
                    self._add_task_row(table, service, task)

                    # Add container rows nested under the task (if multiple containers)
                    if len(task.containers) > 1:
                        for container in task.containers:
                            self._add_container_row(table, service, task, container)

    def _add_service_row(
        self, table: DataTable, service: Service, is_folded: bool
    ) -> None:
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

        # Service name with fold indicator
        fold_icon = "▶" if is_folded else "▼"
        name_display = f"[bold]{fold_icon} {service.name}[/bold]"

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

    def on_data_table_row_selected(self, event: DataTable.RowSelected) -> None:
        """Handle Enter key on a row - toggle fold for service rows."""
        self._toggle_fold_at_cursor()

    def _toggle_fold_at_cursor(self) -> None:
        """Toggle fold/unfold for the selected service."""
        if self.cluster is None:
            return

        try:
            table = self.query_one("#detail-table", DataTable)
        except Exception:
            return

        if table.cursor_row is None:
            return

        # Find what's at the current cursor position
        row_index = 0
        for service in self.cluster.services:
            if row_index == table.cursor_row:
                # Cursor is on a service row - toggle fold
                if service.name in self._folded_services:
                    self._folded_services.remove(service.name)
                else:
                    self._folded_services.add(service.name)

                # Remember cursor row and rebuild table
                saved_row = table.cursor_row
                self._update_table()

                # Restore cursor position
                try:
                    if table.row_count > 0:
                        new_row = min(saved_row, table.row_count - 1)
                        table.move_cursor(row=new_row)
                except Exception:
                    pass
                return

            row_index += 1

            # Skip task/container rows if not folded
            if service.name not in self._folded_services:
                for task in service.tasks:
                    row_index += 1
                    if len(task.containers) > 1:
                        row_index += len(task.containers)

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

        # Walk through the rows to find what's at the cursor position
        row_index = 0
        for service in self.cluster.services:
            if row_index == table.cursor_row:
                return service, None, None
            row_index += 1

            # Check task rows if not folded
            if service.name not in self._folded_services:
                for task in service.tasks:
                    if row_index == table.cursor_row:
                        return service, task, None
                    row_index += 1

                    # Check container rows for multi-container tasks
                    if len(task.containers) > 1:
                        for container in task.containers:
                            if row_index == table.cursor_row:
                                return service, task, container
                            row_index += 1

        return None, None, None
