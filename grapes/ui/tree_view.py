"""Unified tree view showing clusters > services > tasks hierarchy."""

import logging
from enum import Enum, auto

from textual.app import ComposeResult
from textual.binding import Binding
from textual.message import Message
from textual.reactive import reactive
from textual.widgets import DataTable, Static

from grapes.models import Cluster, Service, Task, Container, HealthStatus

logger = logging.getLogger(__name__)


class RowType(Enum):
    """Type of row in the tree view."""

    CLUSTER = auto()
    SERVICE = auto()
    TASK = auto()
    CONTAINER = auto()


class RowInfo:
    """Information about a row in the tree view."""

    def __init__(
        self,
        row_type: RowType,
        cluster: Cluster,
        service: Service | None = None,
        task: Task | None = None,
        container: Container | None = None,
    ):
        self.row_type = row_type
        self.cluster = cluster
        self.service = service
        self.task = task
        self.container = container


class ClusterSelected(Message):
    """Message sent when a cluster is selected for data loading."""

    def __init__(self, cluster: Cluster) -> None:
        self.cluster = cluster
        super().__init__()


class TreeView(Static):
    """Widget displaying clusters, services, and tasks in a unified tree."""

    BINDINGS = [
        Binding("tab", "next_sibling", "Next Sibling", show=False),
        Binding("shift+tab", "prev_sibling", "Prev Sibling", show=False),
    ]

    clusters: reactive[list[Cluster]] = reactive(list, always_update=True)
    refresh_countdown: reactive[int] = reactive(0, always_update=True)
    _columns_ready: bool = False
    _folded_clusters: set[str]  # Set of folded cluster names
    _folded_services: set[str]  # Set of folded service keys (cluster_name:service_name)
    _row_map: list[RowInfo]  # Maps row index to row info
    _loaded_clusters: dict[str, Cluster]  # Cluster name -> loaded cluster with services

    def __init__(self, *args, **kwargs) -> None:
        """Initialize the tree view."""
        super().__init__(*args, **kwargs)
        self._folded_clusters = set()
        self._folded_services = set()
        self._row_map = []
        self._loaded_clusters = {}

    def compose(self) -> ComposeResult:
        """Compose the tree view layout."""
        yield Static("[bold]grapes[/bold]", id="tree-title")
        yield DataTable(id="tree-table")

    def on_mount(self) -> None:
        """Set up the data table when mounted."""
        table = self.query_one("#tree-table", DataTable)
        table.cursor_type = "row"
        table.zebra_stripes = False

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

    def watch_clusters(self, clusters: list[Cluster]) -> None:
        """Update table when clusters change."""
        self._update_table()

    def watch_refresh_countdown(self, countdown: int) -> None:
        """Update title when countdown changes."""
        try:
            title = self.query_one("#tree-title", Static)
            if countdown > 0:
                title.update(f"[bold]grapes [{countdown}s][/bold]")
            else:
                title.update("[bold]grapes[/bold]")
        except Exception:
            pass

    def update_cluster_data(self, cluster: Cluster) -> None:
        """Update the data for a specific cluster (services/tasks loaded).

        Args:
            cluster: Cluster with loaded services and tasks
        """
        self._loaded_clusters[cluster.name] = cluster
        self._update_table()

    def _get_service_key(self, cluster_name: str, service_name: str) -> str:
        """Get a unique key for a service."""
        return f"{cluster_name}:{service_name}"

    def _update_table(self) -> None:
        """Update the table with the full hierarchy."""
        if not self._columns_ready:
            return

        try:
            table = self.query_one("#tree-table", DataTable)
        except Exception:
            return

        # Save cursor position
        saved_cursor = table.cursor_row

        table.clear()
        self._row_map = []

        for cluster in self.clusters:
            is_cluster_folded = cluster.name in self._folded_clusters

            # Add cluster row
            self._add_cluster_row(table, cluster, is_cluster_folded)

            # If cluster is not folded and has loaded data, show services
            if not is_cluster_folded:
                loaded_cluster = self._loaded_clusters.get(cluster.name)
                if loaded_cluster and loaded_cluster.services:
                    for service in loaded_cluster.services:
                        service_key = self._get_service_key(cluster.name, service.name)
                        is_service_folded = service_key in self._folded_services

                        # Add service row
                        self._add_service_row(
                            table, loaded_cluster, service, is_service_folded
                        )

                        # Add task rows if service is not folded
                        if not is_service_folded:
                            for task in service.tasks:
                                self._add_task_row(table, loaded_cluster, service, task)

                                # Add container rows for multi-container tasks
                                if len(task.containers) > 1:
                                    for container in task.containers:
                                        self._add_container_row(
                                            table,
                                            loaded_cluster,
                                            service,
                                            task,
                                            container,
                                        )

        # Restore cursor position
        if saved_cursor is not None and table.row_count > 0:
            new_row = min(saved_cursor, table.row_count - 1)
            table.move_cursor(row=new_row)

    def _add_cluster_row(
        self, table: DataTable, cluster: Cluster, is_folded: bool
    ) -> None:
        """Add a cluster row to the table."""
        # Track row info
        self._row_map.append(RowInfo(RowType.CLUSTER, cluster))

        # Fold icon
        fold_icon = "▶" if is_folded else "▼"
        name_display = f"[bold]{fold_icon} {cluster.name}[/bold]"

        # Status styling
        if cluster.status == "ACTIVE":
            status_styled = f"[green]{cluster.status}[/green]"
        elif cluster.status in ("PROVISIONING", "DEPROVISIONING"):
            status_styled = f"[yellow]{cluster.status}[/yellow]"
        else:
            status_styled = f"[red]{cluster.status}[/red]"

        # Health from loaded data if available
        loaded = self._loaded_clusters.get(cluster.name)
        if loaded:
            health = loaded.calculate_health()
            health_styled = self._style_health_symbol(health)
        else:
            health_styled = "[dim]?[/dim]"

        # Tasks display
        tasks_display = f"{cluster.running_tasks_count}/{cluster.pending_tasks_count}"

        table.add_row(
            name_display,
            status_styled,
            health_styled,
            tasks_display,
            "",  # CPU - not applicable at cluster level
            "",  # Mem - not applicable at cluster level
            "",  # Image - not applicable at cluster level
            "",  # Started - not applicable at cluster level
            key=f"cluster_{cluster.name}",
        )

    def _add_service_row(
        self,
        table: DataTable,
        cluster: Cluster,
        service: Service,
        is_folded: bool,
    ) -> None:
        """Add a service row to the table."""
        # Track row info
        self._row_map.append(RowInfo(RowType.SERVICE, cluster, service))

        health = service.calculate_health()
        health_display = service.health_display

        # Style health
        health_styled = self._style_health_text(health, health_display)

        # Style status
        if service.status == "ACTIVE":
            status_styled = f"[green]{service.status}[/green]"
        else:
            status_styled = f"[yellow]{service.status}[/yellow]"

        # Service name with fold indicator (indented under cluster)
        fold_icon = "▶" if is_folded else "▼"
        name_display = f"  {fold_icon} [bold]{service.name}[/bold]"

        table.add_row(
            name_display,
            status_styled,
            health_styled,
            service.tasks_display,
            service.cpu_display,
            service.memory_display,
            service.image_display,
            "",  # No started time for services
            key=f"svc_{cluster.name}_{service.name}",
        )

    def _add_task_row(
        self, table: DataTable, cluster: Cluster, service: Service, task: Task
    ) -> None:
        """Add a task row to the table."""
        # Track row info
        self._row_map.append(RowInfo(RowType.TASK, cluster, service, task))

        health_styled = self._style_health_symbol(task.health_status)
        status_styled = self._style_task_status(task.status)

        # Indented task name with tree character
        name_display = f"      └─ {task.short_id}"

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
            "",  # No image for tasks
            task.started_ago,
            key=f"task_{cluster.name}_{service.name}_{task.id}",
        )

    def _add_container_row(
        self,
        table: DataTable,
        cluster: Cluster,
        service: Service,
        task: Task,
        container: Container,
    ) -> None:
        """Add a container row to the table."""
        # Track row info
        self._row_map.append(
            RowInfo(RowType.CONTAINER, cluster, service, task, container)
        )

        health_styled = self._style_health_symbol(container.health_status)

        # Style container status
        if container.status == "RUNNING":
            status_styled = f"[green]{container.status}[/green]"
        else:
            status_styled = f"[yellow]{container.status}[/yellow]"

        # Triple-indented container name
        name_display = f"          └─ {container.name}"

        table.add_row(
            name_display,
            status_styled,
            health_styled,
            "",
            container.cpu_display,
            container.memory_display,
            "",
            "",
            key=f"container_{cluster.name}_{service.name}_{task.id}_{container.name}",
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
        """Handle Enter key - toggle fold or load cluster data."""
        try:
            table = self.query_one("#tree-table", DataTable)
        except Exception:
            return

        if table.cursor_row is None or table.cursor_row >= len(self._row_map):
            return

        row_info = self._row_map[table.cursor_row]

        if row_info.row_type == RowType.CLUSTER:
            # Check if cluster data is loaded
            if row_info.cluster.name not in self._loaded_clusters:
                # Request cluster data load
                logger.info(f"Loading cluster data: {row_info.cluster.name}")
                self.post_message(ClusterSelected(row_info.cluster))
            else:
                # Toggle fold
                was_folded = row_info.cluster.name in self._folded_clusters
                if was_folded:
                    self._folded_clusters.remove(row_info.cluster.name)
                else:
                    self._folded_clusters.add(row_info.cluster.name)
                logger.debug(
                    f"Cluster {row_info.cluster.name} {'unfolded' if was_folded else 'folded'}"
                )
                self._update_table()

        elif row_info.row_type == RowType.SERVICE:
            # Toggle service fold
            service_key = self._get_service_key(
                row_info.cluster.name, row_info.service.name
            )
            was_folded = service_key in self._folded_services
            if was_folded:
                self._folded_services.remove(service_key)
            else:
                self._folded_services.add(service_key)
            logger.debug(
                f"Service {row_info.service.name} {'unfolded' if was_folded else 'folded'}"
            )
            self._update_table()

    def action_next_sibling(self) -> None:
        """Jump to next row of the same type."""
        self._jump_to_sibling(forward=True)

    def action_prev_sibling(self) -> None:
        """Jump to previous row of the same type."""
        self._jump_to_sibling(forward=False)

    def _jump_to_sibling(self, forward: bool = True) -> None:
        """Jump to next/previous row of the same type.

        Args:
            forward: True to go forward, False to go backward
        """
        try:
            table = self.query_one("#tree-table", DataTable)
        except Exception:
            return

        if table.cursor_row is None or not self._row_map:
            return

        current_row = table.cursor_row
        if current_row >= len(self._row_map):
            return

        current_type = self._row_map[current_row].row_type

        # Search for next/prev row of same type
        if forward:
            search_range = range(current_row + 1, len(self._row_map))
        else:
            search_range = range(current_row - 1, -1, -1)

        for idx in search_range:
            if self._row_map[idx].row_type == current_type:
                table.move_cursor(row=idx)
                return

        # Wrap around if not found
        if forward:
            wrap_range = range(0, current_row)
        else:
            wrap_range = range(len(self._row_map) - 1, current_row, -1)

        for idx in wrap_range:
            if self._row_map[idx].row_type == current_type:
                table.move_cursor(row=idx)
                return

    def get_selected_item(
        self,
    ) -> tuple[Cluster | None, Service | None, Task | None, Container | None]:
        """Get the currently selected item.

        Returns:
            Tuple of (cluster, service, task, container) - service, task, container may be None
        """
        try:
            table = self.query_one("#tree-table", DataTable)
        except Exception:
            return None, None, None, None

        if table.cursor_row is None or table.cursor_row >= len(self._row_map):
            return None, None, None, None

        row_info = self._row_map[table.cursor_row]
        return row_info.cluster, row_info.service, row_info.task, row_info.container

    def get_current_row_type(self) -> RowType | None:
        """Get the type of the currently selected row.

        Returns:
            RowType or None if no selection
        """
        try:
            table = self.query_one("#tree-table", DataTable)
        except Exception:
            return None

        if table.cursor_row is None or table.cursor_row >= len(self._row_map):
            return None

        return self._row_map[table.cursor_row].row_type
