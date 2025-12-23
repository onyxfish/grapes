"""Service list widget for ECS Monitor."""

import logging

from textual.app import ComposeResult
from textual.binding import Binding
from textual.message import Message
from textual.reactive import reactive
from textual.widgets import DataTable, Static

from grapes.models import Service, HealthStatus

logger = logging.getLogger(__name__)


class ServiceSelected(Message):
    """Message sent when a service is selected."""

    def __init__(self, service: Service) -> None:
        self.service = service
        super().__init__()


class ServiceDeselected(Message):
    """Message sent when a service is deselected (Escape pressed)."""

    pass


class ServiceList(Static):
    """Widget displaying list of ECS services."""

    BINDINGS = [
        Binding("enter", "select_service", "View Tasks"),
        Binding("escape", "deselect_service", "Close Tasks", show=False),
    ]

    services: reactive[list[Service]] = reactive(list, always_update=True)
    selected_service_name: reactive[str | None] = reactive(None)
    _columns_ready: bool = False  # Track if columns have been set up

    def compose(self) -> ComposeResult:
        """Compose the service list layout."""
        yield Static("[bold]Services[/bold]", id="services-title")
        yield DataTable(id="services-table")

    def on_mount(self) -> None:
        """Set up the data table when mounted."""
        table = self.query_one("#services-table", DataTable)
        table.cursor_type = "row"
        table.zebra_stripes = True

        # Responsive columns - no fixed width allows auto-sizing
        # Columns will expand to fill available space
        table.add_column("NAME")
        table.add_column("STATUS")
        table.add_column("TASKS")
        table.add_column("HEALTH")
        table.add_column("CPU")
        table.add_column("MEM")
        table.add_column("TASK DEF")
        table.add_column("IMAGE")
        table.add_column("DEPLOYMENT")

        # Mark columns as ready - this will allow watchers to update the table
        self._columns_ready = True

        # Focus the table so it's immediately interactive
        table.focus()

        # Note: We don't call _update_table() here because the reactive watchers
        # will fire after on_mount completes and handle the initial population.
        # Calling it here would cause duplicate rows if services were set before mount.

    def watch_services(self, services: list[Service]) -> None:
        """Update table when services change."""
        self._update_table()

    def watch_selected_service_name(self, name: str | None) -> None:
        """Update table highlighting when selected service changes."""
        self._update_table()

    def _update_table(self) -> None:
        """Update the services table with current data."""
        # Check if columns have been set up (happens in on_mount)
        if not self._columns_ready:
            logger.debug("ServiceList._update_table: columns not ready yet, skipping")
            return

        try:
            table = self.query_one("#services-table", DataTable)
        except Exception:
            logger.debug("ServiceList._update_table: table not found, skipping")
            return

        table.clear()

        for service in self.services:
            health = service.calculate_health()
            health_display = service.health_display

            # Check if this service is selected
            is_selected = service.name == self.selected_service_name

            # Color the health display
            if health == HealthStatus.HEALTHY:
                health_styled = f"[green]{health_display}[/green]"
            elif health == HealthStatus.UNHEALTHY:
                health_styled = f"[red]{health_display}[/red]"
            elif health == HealthStatus.WARNING:
                health_styled = f"[yellow]{health_display}[/yellow]"
            else:
                health_styled = f"[dim]{health_display}[/dim]"

            # Color the status
            if service.status == "ACTIVE":
                status_styled = f"[green]{service.status}[/green]"
            else:
                status_styled = f"[yellow]{service.status}[/yellow]"

            # Add selection indicator to name (without color change to avoid
            # confusion with the table's row cursor highlighting)
            if is_selected:
                name_display = f"▶ {service.name}"
            else:
                name_display = f"  {service.name}"

            table.add_row(
                name_display,
                status_styled,
                service.tasks_display,
                health_styled,
                service.cpu_display,
                service.memory_display,
                service.task_definition,
                service.image_display,
                service.deployment_status,
                key=service.name,
            )

    def get_selected_service(self) -> Service | None:
        """Get the currently selected service."""
        table = self.query_one("#services-table", DataTable)
        if table.cursor_row is None:
            return None

        row_key = table.get_row_at(table.cursor_row)
        if not row_key:
            return None

        # Find service by name
        for service in self.services:
            if service.name == table.get_row_key(row_key):
                return service
        return None

    def action_select_service(self) -> None:
        """Handle service selection."""
        table = self.query_one("#services-table", DataTable)
        if table.cursor_row is not None and self.services:
            # Get service at cursor position
            try:
                row_key = table.get_row_key(table.get_row_at(table.cursor_row))
                for service in self.services:
                    if service.name == row_key:
                        self.post_message(ServiceSelected(service))
                        return
            except Exception:
                pass

            # Fallback: use cursor row index
            if table.cursor_row < len(self.services):
                self.post_message(ServiceSelected(self.services[table.cursor_row]))

    def action_deselect_service(self) -> None:
        """Handle service deselection (Escape key)."""
        self.post_message(ServiceDeselected())

    def on_data_table_row_selected(self, event: DataTable.RowSelected) -> None:
        """Handle row double-click selection."""
        if event.row_key and self.services:
            for service in self.services:
                if service.name == event.row_key.value:
                    self.post_message(ServiceSelected(service))
                    return
