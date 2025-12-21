"""Service list widget for ECS Monitor."""

from textual.app import ComposeResult
from textual.binding import Binding
from textual.message import Message
from textual.reactive import reactive
from textual.widgets import DataTable, Static

from ecs_monitor.models import Service, HealthStatus


class ServiceSelected(Message):
    """Message sent when a service is selected."""

    def __init__(self, service: Service) -> None:
        self.service = service
        super().__init__()


class ServiceList(Static):
    """Widget displaying list of ECS services."""

    BINDINGS = [
        Binding("enter", "select_service", "View Details"),
        Binding("c", "copy_url", "Copy Console URL"),
    ]

    services: reactive[list[Service]] = reactive(list, always_update=True)

    def compose(self) -> ComposeResult:
        """Compose the service list layout."""
        yield Static("[bold]Services[/bold]", id="services-title")
        yield DataTable(id="services-table")

    def on_mount(self) -> None:
        """Set up the data table when mounted."""
        table = self.query_one("#services-table", DataTable)
        table.cursor_type = "row"
        table.zebra_stripes = True

        # Fixed-width columns
        table.add_column("NAME", width=24)
        table.add_column("STATUS", width=10)
        table.add_column("TASKS", width=8)
        table.add_column("HEALTH", width=10)
        table.add_column("DEPLOYMENT", width=16)

    def watch_services(self, services: list[Service]) -> None:
        """Update table when services change."""
        self._update_table()

    def _update_table(self) -> None:
        """Update the services table with current data."""
        table = self.query_one("#services-table", DataTable)
        table.clear()

        for service in self.services:
            health = service.calculate_health()
            health_display = service.health_display

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

            table.add_row(
                service.name,
                status_styled,
                service.tasks_display,
                health_styled,
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

    def action_copy_url(self) -> None:
        """Copy console URL for selected service."""
        # This will be handled by the app
        pass

    def on_data_table_row_selected(self, event: DataTable.RowSelected) -> None:
        """Handle row double-click selection."""
        if event.row_key and self.services:
            for service in self.services:
                if service.name == event.row_key.value:
                    self.post_message(ServiceSelected(service))
                    return
