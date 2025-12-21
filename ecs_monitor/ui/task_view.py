"""Unified task and container view widget for ECS Monitor."""

import logging

from textual.app import ComposeResult
from textual.binding import Binding
from textual.message import Message
from textual.reactive import reactive
from textual.widgets import DataTable, Static

from ecs_monitor.models import Service, Task, Container, HealthStatus

logger = logging.getLogger(__name__)


class TaskViewBack(Message):
    """Message sent when user wants to go back to service list."""

    pass


class ServiceDetailView(Static):
    """Widget displaying service details and tasks/containers."""

    BINDINGS = [
        Binding("escape", "go_back", "Back"),
        Binding("c", "copy_url", "Copy Console URL"),
    ]

    service: reactive[Service | None] = reactive(None)
    _columns_ready: bool = False  # Track if columns have been set up

    def compose(self) -> ComposeResult:
        """Compose the service detail layout."""
        yield Static(id="service-header")
        yield Static(id="deployments-section")
        yield Static("[bold]Tasks & Containers[/bold]", id="tasks-title")
        yield DataTable(id="tasks-table")

    def on_mount(self) -> None:
        """Set up the data table when mounted."""
        table = self.query_one("#tasks-table", DataTable)
        table.cursor_type = "row"
        table.zebra_stripes = True

        # Fixed-width columns for unified task+container view
        table.add_column("TASK", width=10)
        table.add_column("STATUS", width=8)
        table.add_column("HEALTH", width=8)
        table.add_column("STARTED", width=10)
        table.add_column("CONTAINER", width=16)
        table.add_column("CPU", width=14)
        table.add_column("MEM", width=16)
        table.add_column("C.HEALTH", width=8)

        # Mark columns as ready
        self._columns_ready = True

        # Now that columns are set up, update the view
        # This handles the case where service was set before mount completed
        self._update_header()
        self._update_deployments()
        self._update_table()

        # Focus the table so it's immediately interactive
        table.focus()

    def watch_service(self, service: Service | None) -> None:
        """Update display when service changes."""
        self._update_header()
        self._update_deployments()
        self._update_table()

    def _update_header(self) -> None:
        """Update the service header."""
        if not self._columns_ready:
            return

        try:
            header = self.query_one("#service-header", Static)
        except Exception:
            return

        if self.service is None:
            header.update("No service selected")
            return

        s = self.service
        header.update(
            f"[bold]Service: {s.name}[/bold]\n"
            f"Status: {s.status}              "
            f"Desired: {s.desired_count}   Running: {s.running_count}\n"
            f"Task Definition: {s.task_definition}"
        )

    def _update_deployments(self) -> None:
        """Update the deployments section."""
        if not self._columns_ready:
            return

        try:
            section = self.query_one("#deployments-section", Static)
        except Exception:
            return

        if self.service is None or not self.service.deployments:
            section.update("")
            return

        lines = ["[bold]Deployments:[/bold]"]
        for dep in self.service.deployments:
            status_display = dep.display_status
            lines.append(
                f"  {dep.status:<10} - {status_display:<14} - {dep.task_definition}"
            )

        section.update("\n".join(lines))

    def _update_table(self) -> None:
        """Update the tasks table with containers."""
        # Check if columns have been set up (happens in on_mount)
        if not self._columns_ready:
            logger.debug(
                "ServiceDetailView._update_table: columns not ready yet, skipping"
            )
            return

        try:
            table = self.query_one("#tasks-table", DataTable)
        except Exception:
            logger.debug("ServiceDetailView._update_table: table not found, skipping")
            return

        table.clear()

        if self.service is None:
            return

        for task in self.service.tasks:
            # Add task row
            health_styled = self._style_health(task.health_status)
            status_styled = self._style_task_status(task.status)

            # First row for task with first container (if any)
            if task.containers:
                first_container = task.containers[0]
                c_health_styled = self._style_health(first_container.health_status)

                table.add_row(
                    task.short_id,
                    status_styled,
                    health_styled,
                    task.started_ago,
                    first_container.name,
                    first_container.cpu_display,
                    first_container.memory_display,
                    c_health_styled,
                    key=f"task_{task.id}_0",
                )

                # Add remaining containers as separate rows
                for i, container in enumerate(task.containers[1:], start=1):
                    c_health_styled = self._style_health(container.health_status)

                    table.add_row(
                        "",  # Empty task column for continuation
                        "",
                        "",
                        "",
                        container.name,
                        container.cpu_display,
                        container.memory_display,
                        c_health_styled,
                        key=f"task_{task.id}_{i}",
                    )
            else:
                # Task with no containers
                table.add_row(
                    task.short_id,
                    status_styled,
                    health_styled,
                    task.started_ago,
                    "-",
                    "-",
                    "-",
                    "-",
                    key=f"task_{task.id}",
                )

    def _style_health(self, health: HealthStatus) -> str:
        """Style health status with color."""
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
        short_status = status[:4] if len(status) > 4 else status
        if status == "RUNNING":
            return f"[green]{short_status}[/green]"
        elif status == "PENDING":
            return f"[yellow]{short_status}[/yellow]"
        elif status == "STOPPED":
            return f"[red]{short_status}[/red]"
        else:
            return f"[dim]{short_status}[/dim]"

    def action_go_back(self) -> None:
        """Handle going back to service list."""
        self.post_message(TaskViewBack())

    def action_copy_url(self) -> None:
        """Copy console URL for selected item."""
        # This will be handled by the app
        pass

    def get_selected_task_and_container(self) -> tuple[Task | None, Container | None]:
        """Get the currently selected task and container (if any)."""
        if self.service is None:
            return None, None

        table = self.query_one("#tasks-table", DataTable)
        if table.cursor_row is None:
            return None, None

        try:
            row_key = table.get_row_key(table.get_row_at(table.cursor_row))
            if row_key and row_key.value:
                key_str = str(row_key.value)
                # Parse key format: "task_{task_id}_{container_idx}" or "task_{task_id}"
                parts = key_str.split("_", 2)
                if len(parts) >= 2:
                    task_id = parts[1] if len(parts) == 2 else "_".join(parts[1:-1])
                    container_idx = (
                        int(parts[-1])
                        if len(parts) > 2 and parts[-1].isdigit()
                        else None
                    )

                    # Find the task
                    for task in self.service.tasks:
                        if task.id == task_id or task.id.startswith(task_id):
                            if container_idx is not None and container_idx < len(
                                task.containers
                            ):
                                return task, task.containers[container_idx]
                            return task, None
        except Exception:
            pass

        return None, None
