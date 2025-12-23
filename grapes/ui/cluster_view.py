"""Cluster header widget for Grapes."""

from textual.app import ComposeResult
from textual.reactive import reactive
from textual.widgets import Static

from grapes.models import Cluster


class ClusterHeader(Static):
    """Widget displaying cluster overview information."""

    cluster: reactive[Cluster | None] = reactive(None)
    insights_enabled: reactive[bool] = reactive(False)

    def compose(self) -> ComposeResult:
        """Compose the cluster header layout."""
        yield Static(id="cluster-info")
        yield Static(id="insights-warning")

    def watch_cluster(self, cluster: Cluster | None) -> None:
        """Update display when cluster data changes."""
        self._update_display()

    def watch_insights_enabled(self, enabled: bool) -> None:
        """Update warning when insights status changes."""
        self._update_display()

    def _update_display(self) -> None:
        """Update the cluster information display."""
        info_widget = self.query_one("#cluster-info", Static)
        warning_widget = self.query_one("#insights-warning", Static)

        if self.cluster is None:
            info_widget.update("Loading cluster information...")
            warning_widget.update("")
            return

        # Format last updated time
        if self.cluster.last_updated:
            last_updated = self.cluster.last_updated.strftime("%Y-%m-%d %H:%M:%S")
        else:
            last_updated = "-"

        # Build cluster info text
        info_text = (
            f"[bold]ECS Cluster:[/bold] {self.cluster.name}\n"
            f"Region: {self.cluster.region}          "
            f"Last Update: {last_updated}\n"
            f"Status: {self.cluster.status}             "
            f"Services: {self.cluster.health_summary}"
        )
        info_widget.update(info_text)

        # Show warning if Container Insights not enabled
        if not self.insights_enabled:
            warning_widget.update(
                "[yellow]⚠ Container Insights: Not enabled - metrics unavailable[/yellow]"
            )
            warning_widget.display = True
        else:
            warning_widget.update("")
            warning_widget.display = False


class LoadingScreen(Static):
    """Loading screen shown during initial data fetch."""

    status_message: reactive[str] = reactive("Initializing...")

    def compose(self) -> ComposeResult:
        """Compose the loading screen."""
        yield Static(id="loading-message")

    def on_mount(self) -> None:
        """Initialize the loading screen."""
        self._update_display()

    def watch_status_message(self, message: str) -> None:
        """Update when status message changes."""
        self._update_display()

    def _update_display(self) -> None:
        """Update the loading screen display."""
        try:
            message = self.query_one("#loading-message", Static)
            message.update(
                f"[bold]Grapes[/bold]\n\n"
                f"Loading cluster data...\n\n"
                f"[cyan]{self.status_message}[/cyan]"
            )
        except Exception:
            pass  # Widget not mounted yet

    def update_status(self, message: str) -> None:
        """Update the loading status message."""
        self.status_message = message
