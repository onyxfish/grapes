"""Main Textual application for ECS Monitor."""

import logging

from textual.app import App, ComposeResult
from textual.binding import Binding
from textual.command import Hit, Hits, Provider
from textual.containers import Container, Vertical
from textual.reactive import reactive
from textual.widgets import Footer
from textual.worker import Worker, WorkerState

from ecs_monitor.aws.client import AWSClients
from ecs_monitor.aws.fetcher import ECSFetcher
from ecs_monitor.aws.metrics import MetricsFetcher
from ecs_monitor.config import Config
from ecs_monitor.models import Cluster, Service
from ecs_monitor.ui.cluster_view import ClusterHeader, LoadingScreen
from ecs_monitor.ui.console_link import (
    build_cluster_url,
    build_container_url,
    build_service_url,
    build_task_url,
    copy_to_clipboard,
)
from ecs_monitor.ui.debug_console import DebugConsole, TextualLogHandler
from ecs_monitor.ui.service_view import ServiceList, ServiceSelected
from ecs_monitor.ui.task_view import ServiceDetailView, TaskViewBack

logger = logging.getLogger(__name__)


class ToggleDebugConsoleCommand(Provider):
    """Command provider for toggling debug console."""

    async def search(self, query: str) -> Hits:
        """Search for toggle debug console command."""
        matcher = self.matcher(query)

        command = "Toggle Debug Console"
        score = matcher.match(command)
        if score > 0:
            yield Hit(
                score,
                matcher.highlight(command),
                self.app.action_toggle_debug_console,
                help="Show/hide the debug console",
            )


class ECSMonitorApp(App):
    """Main ECS Monitor application."""

    CSS_PATH = "styles.css"

    COMMANDS = {ToggleDebugConsoleCommand}

    BINDINGS = [
        Binding("q", "quit", "Quit"),
        Binding("r", "refresh", "Refresh"),
        Binding("c", "copy_url", "Copy URL"),
        Binding("escape", "go_back", "Back"),
    ]

    # Reactive state
    cluster: reactive[Cluster | None] = reactive(None)
    selected_service: reactive[Service | None] = reactive(None)
    loading: reactive[bool] = reactive(True)
    insights_enabled: reactive[bool] = reactive(False)
    debug_console_visible: reactive[bool] = reactive(False)

    def __init__(
        self,
        config: Config,
        **kwargs,
    ):
        """Initialize the application.

        Args:
            config: Application configuration
            **kwargs: Additional arguments for App
        """
        super().__init__(**kwargs)
        self.config = config

        # Initialize AWS clients
        self.aws_clients = AWSClients(config.cluster)
        self.ecs_fetcher = ECSFetcher(
            self.aws_clients,
            task_def_cache_ttl=config.refresh.task_definition_interval,
            progress_callback=self._on_progress,
        )
        self.metrics_fetcher = MetricsFetcher(
            self.aws_clients,
            progress_callback=self._on_progress,
        )

        # Track active workers
        self._refresh_worker: Worker | None = None

    def _on_progress(self, message: str) -> None:
        """Handle progress updates from fetchers."""
        # Update loading screen if we're still loading
        if self.loading:
            try:
                loading_screen = self.query_one("#loading", LoadingScreen)
                # Use call_from_thread since this may be called from worker
                self.call_from_thread(loading_screen.update_status, message)
            except Exception:
                pass  # Loading screen might not exist
        logger.debug(f"Progress: {message}")

    def compose(self) -> ComposeResult:
        """Compose the application layout."""
        yield LoadingScreen(id="loading")
        yield Vertical(
            ClusterHeader(id="cluster-header"),
            Container(id="main-content"),
            id="main-container",
        )
        yield DebugConsole(id="debug-console")
        yield Footer()

    def on_mount(self) -> None:
        """Set up the application when mounted."""
        # Set up debug console logging handler
        debug_console = self.query_one("#debug-console", DebugConsole)
        handler = TextualLogHandler(debug_console)

        # Always capture INFO and above for the debug console
        # This ensures useful logs are visible when the console is toggled on
        handler.setLevel(logging.INFO)

        # Add handler to root logger
        root_logger = logging.getLogger()
        root_logger.addHandler(handler)

        # Ensure root logger level allows INFO messages through
        # (handlers can't receive messages filtered by the logger level)
        if root_logger.level > logging.INFO:
            root_logger.setLevel(logging.INFO)

        # Hide main container initially, show loading
        self.query_one("#main-container").display = False
        self.query_one("#loading").display = True

        # Start initial data fetch
        self.refresh_data()

        # Set up periodic refresh
        self.set_interval(
            self.config.refresh.interval,
            self._periodic_refresh,
        )

    def _periodic_refresh(self) -> None:
        """Periodic refresh callback."""
        if not self.loading:
            self.refresh_data()

    def refresh_data(self) -> None:
        """Trigger a data refresh."""
        if self._refresh_worker is not None and self._refresh_worker.is_running:
            logger.debug("Refresh already in progress, skipping")
            return

        self._refresh_worker = self.run_worker(
            self._fetch_cluster_data,
            name="refresh_data",
            exclusive=True,
            thread=True,  # Run in thread to not block event loop
        )

    def _fetch_cluster_data(self) -> Cluster | None:
        """Fetch cluster data in a worker thread.

        Note: This is a sync function that runs in a thread via run_worker(thread=True).
        The boto3 calls are synchronous and would block the event loop if run async.

        Returns:
            Cluster object or None on error
        """
        try:
            # Check Container Insights on first load
            if self.cluster is None:
                self.insights_enabled = self.metrics_fetcher.check_container_insights()

            # Fetch ECS data
            cluster = self.ecs_fetcher.fetch_cluster_state()

            # Fetch metrics (service metrics always, container metrics if insights enabled)
            self.metrics_fetcher.fetch_metrics_for_cluster(cluster)

            cluster.insights_enabled = self.insights_enabled

            return cluster

        except Exception as e:
            logger.error(f"Failed to fetch cluster data: {e}")
            # Note: notify() might not work from thread, log instead
            return None

    def on_worker_state_changed(self, event: Worker.StateChanged) -> None:
        """Handle worker state changes."""
        if event.worker.name == "refresh_data":
            logger.debug(f"Worker state changed: {event.state}")

            if event.state == WorkerState.SUCCESS:
                result = event.worker.result
                logger.debug(f"Worker completed successfully, result: {result}")

                if result is not None:
                    self.cluster = result

                    # Update UI state
                    if self.loading:
                        self.loading = False
                        self.query_one("#loading").display = False
                        self.query_one("#main-container").display = True
                        self._show_service_list()

                    # Update header
                    header = self.query_one("#cluster-header", ClusterHeader)
                    header.cluster = self.cluster
                    header.insights_enabled = self.insights_enabled

                    # Update current view
                    self._update_current_view()
                else:
                    logger.warning("Worker returned None result")

            elif event.state == WorkerState.ERROR:
                logger.error(f"Worker failed with error: {event.worker.error}")
                if self.loading:
                    # Show error on loading screen
                    try:
                        loading = self.query_one("#loading", LoadingScreen)
                        loading.update_status(f"Error: {event.worker.error}")
                    except Exception:
                        pass
                self.notify(
                    f"Error loading data: {event.worker.error}", severity="error"
                )

    def _show_service_list(self) -> None:
        """Show the service list view."""
        self.selected_service = None
        content = self.query_one("#main-content", Container)
        content.remove_children()
        service_list = ServiceList(id="service-list")
        content.mount(service_list)
        # Immediately populate if we have cluster data
        if self.cluster:
            service_list.services = self.cluster.services

    def _show_service_detail(self, service: Service) -> None:
        """Show the service detail view.

        Args:
            service: Service to display
        """
        self.selected_service = service
        content = self.query_one("#main-content", Container)
        content.remove_children()

        detail_view = ServiceDetailView(id="service-detail")
        content.mount(detail_view)
        detail_view.service = service

    def _update_current_view(self) -> None:
        """Update the current view with latest data."""
        if self.selected_service is not None:
            # Update service detail view
            self._update_service_detail()
        else:
            # Update service list
            self._update_service_list()

    def _update_service_list(self) -> None:
        """Update the service list with current cluster data."""
        try:
            service_list = self.query_one("#service-list", ServiceList)
            if self.cluster:
                service_list.services = self.cluster.services
        except Exception:
            pass  # View might not exist yet

    def _update_service_detail(self) -> None:
        """Update the service detail view with current data."""
        if self.selected_service is None or self.cluster is None:
            return

        # Find the updated service in the new cluster data
        for service in self.cluster.services:
            if service.name == self.selected_service.name:
                self.selected_service = service
                try:
                    detail_view = self.query_one("#service-detail", ServiceDetailView)
                    detail_view.service = service
                except Exception:
                    pass
                break

    def on_service_selected(self, event: ServiceSelected) -> None:
        """Handle service selection."""
        self._show_service_detail(event.service)

    def on_task_view_back(self, event: TaskViewBack) -> None:
        """Handle going back from task view."""
        self._show_service_list()

    def action_go_back(self) -> None:
        """Handle escape key to go back."""
        if self.selected_service is not None:
            self._show_service_list()

    def action_refresh(self) -> None:
        """Handle manual refresh request."""
        self.notify("Refreshing...")
        self.refresh_data()

    def action_copy_url(self) -> None:
        """Copy the appropriate console URL to clipboard."""
        if self.cluster is None:
            return

        region = self.config.cluster.region
        cluster_name = self.config.cluster.name
        url = None

        if self.selected_service is not None:
            # We're in service detail view
            try:
                detail_view = self.query_one("#service-detail", ServiceDetailView)
                task, container = detail_view.get_selected_task_and_container()

                if container is not None and task is not None:
                    url = build_container_url(cluster_name, task.id, region)
                elif task is not None:
                    url = build_task_url(cluster_name, task.id, region)
                else:
                    url = build_service_url(
                        cluster_name, self.selected_service.name, region
                    )
            except Exception:
                url = build_service_url(
                    cluster_name, self.selected_service.name, region
                )
        else:
            # We're in service list view
            try:
                service_list = self.query_one("#service-list", ServiceList)
                selected = service_list.get_selected_service()
                if selected:
                    url = build_service_url(cluster_name, selected.name, region)
                else:
                    url = build_cluster_url(cluster_name, region)
            except Exception:
                url = build_cluster_url(cluster_name, region)

        if url:
            if copy_to_clipboard(url):
                self.notify("Console URL copied to clipboard")
            else:
                self.notify(f"URL: {url}", severity="warning")

    def action_toggle_debug_console(self) -> None:
        """Toggle the debug console visibility."""
        self.debug_console_visible = not self.debug_console_visible

    def watch_debug_console_visible(self, visible: bool) -> None:
        """Update debug console visibility when state changes."""
        console = self.query_one("#debug-console", DebugConsole)
        if visible:
            console.add_class("visible")
        else:
            console.remove_class("visible")
