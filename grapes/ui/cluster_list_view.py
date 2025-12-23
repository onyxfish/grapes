"""Cluster list widget for Grapes."""

import logging

from textual.app import ComposeResult
from textual.binding import Binding
from textual.message import Message
from textual.reactive import reactive
from textual.widgets import DataTable, Static

from grapes.models import Cluster

logger = logging.getLogger(__name__)


class ClusterSelected(Message):
    """Message sent when a cluster is selected."""

    def __init__(self, cluster: Cluster) -> None:
        self.cluster = cluster
        super().__init__()


class ClusterList(Static):
    """Widget displaying list of ECS clusters."""

    BINDINGS = [
        Binding("enter", "select_cluster", "View Cluster"),
    ]

    clusters: reactive[list[Cluster]] = reactive(list, always_update=True)
    selected_cluster_name: reactive[str | None] = reactive(None)
    _columns_ready: bool = False  # Track if columns have been set up

    def compose(self) -> ComposeResult:
        """Compose the cluster list layout."""
        yield Static("[bold]ECS Clusters[/bold]", id="clusters-title")
        yield DataTable(id="clusters-table")

    def on_mount(self) -> None:
        """Set up the data table when mounted."""
        table = self.query_one("#clusters-table", DataTable)
        table.cursor_type = "row"
        table.zebra_stripes = True

        # Columns for cluster overview - similar to services table
        table.add_column("NAME")
        table.add_column("STATUS")
        table.add_column("SERVICES")
        table.add_column("TASKS (R/P)")
        table.add_column("INSTANCES")
        table.add_column("REGION")

        # Mark columns as ready
        self._columns_ready = True

        # Focus the table so it's immediately interactive
        table.focus()

    def watch_clusters(self, clusters: list[Cluster]) -> None:
        """Update table when clusters change."""
        self._update_table()

    def watch_selected_cluster_name(self, name: str | None) -> None:
        """Update table highlighting when selected cluster changes."""
        self._update_table()

    def _update_table(self) -> None:
        """Update the clusters table with current data."""
        if not self._columns_ready:
            logger.debug("ClusterList._update_table: columns not ready yet, skipping")
            return

        try:
            table = self.query_one("#clusters-table", DataTable)
        except Exception:
            logger.debug("ClusterList._update_table: table not found, skipping")
            return

        table.clear()

        for cluster in self.clusters:
            # Color the status
            if cluster.status == "ACTIVE":
                status_styled = f"[green]{cluster.status}[/green]"
            elif cluster.status in ("PROVISIONING", "DEPROVISIONING"):
                status_styled = f"[yellow]{cluster.status}[/yellow]"
            else:
                status_styled = f"[red]{cluster.status}[/red]"

            # Format tasks as running/pending
            tasks_display = (
                f"{cluster.running_tasks_count}/{cluster.pending_tasks_count}"
            )

            # Check if this cluster is selected
            is_selected = cluster.name == self.selected_cluster_name

            # Add selection indicator to name
            if is_selected:
                name_display = f"▶ {cluster.name}"
            else:
                name_display = f"  {cluster.name}"

            table.add_row(
                name_display,
                status_styled,
                str(cluster.active_services_count),
                tasks_display,
                str(cluster.registered_container_instances_count),
                cluster.region,
                key=cluster.name,
            )

    def get_selected_cluster(self) -> Cluster | None:
        """Get the currently selected cluster."""
        if not self.clusters:
            return None

        table = self.query_one("#clusters-table", DataTable)
        if table.cursor_row is None:
            return None

        # Use cursor row index to get cluster
        if table.cursor_row < len(self.clusters):
            return self.clusters[table.cursor_row]
        return None

    def action_select_cluster(self) -> None:
        """Handle cluster selection."""
        cluster = self.get_selected_cluster()
        if cluster:
            self.post_message(ClusterSelected(cluster))

    def on_data_table_row_selected(self, event: DataTable.RowSelected) -> None:
        """Handle row double-click selection."""
        if event.row_key and self.clusters:
            for cluster in self.clusters:
                if cluster.name == event.row_key.value:
                    self.post_message(ClusterSelected(cluster))
                    return
