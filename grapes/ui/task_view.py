"""Task list widget for ECS Monitor."""

import logging

from textual.app import ComposeResult
from textual.binding import Binding
from textual.message import Message
from textual.reactive import reactive
from textual.widgets import DataTable, Static

from grapes.models import Service, Task, Container, HealthStatus

logger = logging.getLogger(__name__)


class TaskDeselected(Message):
    """Message sent when escape is pressed in task list."""

    pass


class TaskList(Static):
    """Widget displaying tasks and containers for a service."""

    BINDINGS = [
        Binding("escape", "deselect_task", "Back", show=False),
    ]

    service: reactive[Service | None] = reactive(None)
    _columns_ready: bool = False  # Track if columns have been set up

    def compose(self) -> ComposeResult:
        """Compose the task list layout."""
        yield Static("[bold]Tasks & Containers[/bold]", id="tasks-title")
        yield DataTable(id="tasks-table")

    def on_mount(self) -> None:
        """Set up the data table when mounted."""
        table = self.query_one("#tasks-table", DataTable)
        table.cursor_type = "row"
        table.zebra_stripes = True

        # Responsive columns - no fixed width allows auto-sizing
        table.add_column("TASK")
        table.add_column("STATUS")
        table.add_column("HEALTH")
        table.add_column("STARTED")
        table.add_column("CONTAINER")
        table.add_column("CPU")
        table.add_column("MEM")
        table.add_column("C.HEALTH")

        # Mark columns as ready
        self._columns_ready = True

        # Now that columns are set up, update the view
        self._update_table()

        # Focus the table so it's immediately interactive
        table.focus()

    def watch_service(self, service: Service | None) -> None:
        """Update display when service changes."""
        self._update_table()

    def _update_table(self) -> None:
        """Update the tasks table with containers."""
        # Check if columns have been set up (happens in on_mount)
        if not self._columns_ready:
            logger.debug("TaskList._update_table: columns not ready yet, skipping")
            return

        try:
            table = self.query_one("#tasks-table", DataTable)
        except Exception:
            logger.debug("TaskList._update_table: table not found, skipping")
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
        if status == "RUNNING":
            return f"[green]{status}[/green]"
        elif status == "PENDING":
            return f"[yellow]{status}[/yellow]"
        elif status == "STOPPED":
            return f"[red]{status}[/red]"
        else:
            return f"[dim]{status}[/dim]"

    def get_selected_task_and_container(self) -> tuple[Task | None, Container | None]:
        """Get the currently selected task and container (if any)."""
        if self.service is None:
            return None, None

        try:
            table = self.query_one("#tasks-table", DataTable)
        except Exception:
            return None, None

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

    def action_deselect_task(self) -> None:
        """Handle task deselection (Escape key)."""
        if self.service is not None:
            self.post_message(TaskDeselected())
