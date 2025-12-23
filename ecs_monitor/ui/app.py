"""Main Textual application for ECS Monitor."""

import logging
from enum import Enum, auto

from textual.app import App, ComposeResult
from textual.binding import Binding
from textual.command import Hit, Hits, Provider
from textual.containers import Container, Vertical
from textual.reactive import reactive
from textual.widgets import DataTable, Footer
from textual.worker import Worker, WorkerState

from ecs_monitor.aws.client import AWSClients
from ecs_monitor.aws.fetcher import ECSFetcher
from ecs_monitor.aws.metrics import MetricsFetcher
from ecs_monitor.config import Config
from ecs_monitor.models import Cluster, Service
from ecs_monitor.ui.cluster_list_view import (
    ClusterList,
    ClusterSelected,
    ClusterDeselected,
)
from ecs_monitor.ui.cluster_view import LoadingScreen
from ecs_monitor.ui.console_link import (
    build_cluster_url,
    build_container_url,
    build_service_url,
    build_task_url,
    open_in_browser,
)
from ecs_monitor.ui.debug_console import DebugConsole, TextualLogHandler
from ecs_monitor.ui.service_view import ServiceList, ServiceSelected, ServiceDeselected
from ecs_monitor.ui.task_view import TaskList, TaskDeselected

logger = logging.getLogger(__name__)


class AppView(Enum):
    """Application view states."""

    LOADING = auto()
    MAIN = auto()  # Three-panel view


class FocusPanel(Enum):
    """Which panel currently has focus."""

    CLUSTERS = auto()
    SERVICES = auto()
    TASKS = auto()


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

    # Add our custom commands to the default set (which includes theme picker)
    COMMANDS = App.COMMANDS | {ToggleDebugConsoleCommand}

    BINDINGS = [
        Binding("q", "quit", "Quit"),
        Binding("r", "refresh", "Refresh"),
        Binding("o", "open_console", "Open in AWS Console"),
        Binding("d", "toggle_debug_console", "Debug"),
        Binding("escape", "go_back", "Back"),
    ]

    # Reactive state
    current_view: reactive[AppView] = reactive(AppView.LOADING)
    focus_panel: reactive[FocusPanel] = reactive(FocusPanel.CLUSTERS)
    clusters: reactive[list[Cluster]] = reactive(list, always_update=True)
    selected_cluster: reactive[Cluster | None] = reactive(None)
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

        # Track if a specific cluster was configured
        self._configured_cluster = config.cluster.name

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
        """Compose the application layout with three panels."""
        yield LoadingScreen(id="loading")
        # Three-panel vertical layout
        yield Vertical(
            Container(
                ClusterList(id="cluster-list"),
                id="clusters-panel",
            ),
            Container(
                ServiceList(id="service-list"),
                id="services-panel",
            ),
            Container(
                TaskList(id="task-list"),
                id="tasks-panel",
            ),
            id="main-container",
        )
        yield DebugConsole(id="debug-console")
        yield Footer()

    def on_mount(self) -> None:
        """Set up the application when mounted."""
        # Set up debug console logging handler
        debug_console = self.query_one("#debug-console", DebugConsole)
        handler = TextualLogHandler(debug_console, self)

        # Always capture INFO and above for the debug console
        handler.setLevel(logging.INFO)

        # Add handler to root logger
        root_logger = logging.getLogger()
        root_logger.addHandler(handler)

        # Ensure root logger level allows INFO messages through
        if root_logger.level > logging.INFO:
            root_logger.setLevel(logging.INFO)

        # Hide main container initially, show loading
        self.query_one("#main-container").display = False
        self.query_one("#loading").display = True

        # Start initial data fetch - always fetch cluster list first
        self._fetch_cluster_list()

        # Set up periodic refresh
        self.set_interval(
            self.config.refresh.interval,
            self._periodic_refresh,
        )

    def _periodic_refresh(self) -> None:
        """Periodic refresh callback."""
        if not self.loading and self.current_view == AppView.MAIN:
            # Refresh cluster list
            self._fetch_cluster_list()
            # Refresh selected cluster details if any
            if self.selected_cluster is not None:
                self._fetch_cluster_data()

    def _fetch_cluster_list(self) -> None:
        """Fetch the list of clusters."""
        if self._refresh_worker is not None and self._refresh_worker.is_running:
            logger.debug("Refresh already in progress, skipping")
            return

        self._refresh_worker = self.run_worker(
            self._fetch_clusters_worker,
            name="fetch_clusters",
            exclusive=True,
            thread=True,
        )

    def _fetch_clusters_worker(self) -> list[Cluster]:
        """Fetch clusters in a worker thread.

        Returns:
            List of Cluster objects
        """
        try:
            clusters = self.ecs_fetcher.list_clusters()
            return clusters
        except Exception as e:
            logger.error(f"Failed to fetch clusters: {e}")
            return []

    def _fetch_cluster_data(self) -> None:
        """Trigger a data refresh for the selected cluster."""
        if self.selected_cluster is None:
            return

        if self._refresh_worker is not None and self._refresh_worker.is_running:
            logger.debug("Refresh already in progress, skipping")
            return

        self._refresh_worker = self.run_worker(
            self._fetch_cluster_data_worker,
            name="refresh_data",
            exclusive=True,
            thread=True,
        )

    def _fetch_cluster_data_worker(self) -> Cluster | None:
        """Fetch cluster data in a worker thread.

        Returns:
            Cluster object or None on error
        """
        try:
            # Check Container Insights on first load for this cluster
            self.insights_enabled = self.metrics_fetcher.check_container_insights()

            # Fetch ECS data
            cluster = self.ecs_fetcher.fetch_cluster_state()

            # Fetch metrics
            self.metrics_fetcher.fetch_metrics_for_cluster(cluster)

            cluster.insights_enabled = self.insights_enabled

            return cluster

        except Exception as e:
            logger.error(f"Failed to fetch cluster data: {e}")
            return None

    def on_worker_state_changed(self, event: Worker.StateChanged) -> None:
        """Handle worker state changes."""
        if event.worker.name == "fetch_clusters":
            self._handle_clusters_fetch_result(event)
        elif event.worker.name == "refresh_data":
            self._handle_cluster_data_result(event)

    def _handle_clusters_fetch_result(self, event: Worker.StateChanged) -> None:
        """Handle result of clusters list fetch."""
        logger.debug(f"Clusters fetch worker state: {event.state}")

        if event.state == WorkerState.SUCCESS:
            result = event.worker.result
            if result is not None:
                self.clusters = result
                logger.debug(f"Fetched {len(self.clusters)} clusters")

                # Transition to main view if still loading
                if self.loading:
                    self.loading = False
                    self.query_one("#loading").display = False
                    self.query_one("#main-container").display = True
                    self.current_view = AppView.MAIN

                # Update cluster list widget
                try:
                    cluster_list = self.query_one("#cluster-list", ClusterList)
                    cluster_list.clusters = self.clusters
                except Exception:
                    pass

                # If a cluster was configured, auto-select it (but don't change focus)
                if self._configured_cluster and self.selected_cluster is None:
                    for cluster in self.clusters:
                        if cluster.name == self._configured_cluster:
                            self._select_cluster_without_focus(cluster)
                            break

                # Always focus the cluster list on startup
                self._focus_clusters_panel()
            else:
                logger.warning("Clusters fetch returned None")

        elif event.state == WorkerState.ERROR:
            logger.error(f"Clusters fetch failed: {event.worker.error}")
            if self.loading:
                try:
                    loading = self.query_one("#loading", LoadingScreen)
                    loading.update_status(f"Error: {event.worker.error}")
                except Exception:
                    pass
            self.notify(
                f"Error loading clusters: {event.worker.error}", severity="error"
            )

    def _handle_cluster_data_result(self, event: Worker.StateChanged) -> None:
        """Handle result of cluster data fetch."""
        logger.debug(f"Worker state changed: {event.state}")

        if event.state == WorkerState.SUCCESS:
            result = event.worker.result
            logger.debug(f"Worker completed successfully, result: {result}")

            if result is not None:
                # Update selected cluster with fresh data
                self.selected_cluster = result

                # Update service list
                self._update_service_list()

                # Update task list if a service is selected
                self._update_task_list()
            else:
                logger.warning("Worker returned None result")

        elif event.state == WorkerState.ERROR:
            logger.error(f"Worker failed with error: {event.worker.error}")
            self.notify(f"Error loading data: {event.worker.error}", severity="error")

    def _update_service_list(self) -> None:
        """Update the service list with current cluster data."""
        try:
            service_list = self.query_one("#service-list", ServiceList)
            if self.selected_cluster:
                service_list.services = self.selected_cluster.services
                # Update selection indicator
                service_list.selected_service_name = (
                    self.selected_service.name if self.selected_service else None
                )
            else:
                service_list.services = []
                service_list.selected_service_name = None
        except Exception:
            pass

    def _update_task_list(self) -> None:
        """Update the task list with current service data."""
        try:
            task_list = self.query_one("#task-list", TaskList)
            if self.selected_service and self.selected_cluster:
                # Find the updated service in the cluster data
                for service in self.selected_cluster.services:
                    if service.name == self.selected_service.name:
                        self.selected_service = service
                        task_list.service = service
                        return
            task_list.service = self.selected_service
        except Exception:
            pass

    def _select_cluster(self, cluster: Cluster, change_focus: bool = True) -> None:
        """Select a cluster and load its services.

        Args:
            cluster: Cluster to select
            change_focus: Whether to change focus to the services panel
        """
        logger.info(f"Selected cluster: {cluster.name}")
        self.selected_cluster = cluster

        # Update cluster list selection indicator
        try:
            cluster_list = self.query_one("#cluster-list", ClusterList)
            cluster_list.selected_cluster_name = cluster.name
            # Only hide cursor if we're changing focus away
            if change_focus:
                clusters_table = cluster_list.query_one("#clusters-table", DataTable)
                clusters_table.show_cursor = False
        except Exception:
            pass

        # Clear service selection
        self.selected_service = None
        self._update_task_list()

        # Set the cluster name in AWS clients and fetch data
        self.aws_clients.set_cluster_name(cluster.name)
        self._fetch_cluster_data()

        # Focus services panel if requested
        if change_focus:
            self._focus_services_panel()

    def _select_cluster_without_focus(self, cluster: Cluster) -> None:
        """Select a cluster without changing focus.

        Args:
            cluster: Cluster to select
        """
        self._select_cluster(cluster, change_focus=False)

    def _deselect_cluster(self) -> None:
        """Deselect the current cluster."""
        self.selected_cluster = None
        self.selected_service = None

        # Clear cluster selection indicator
        try:
            cluster_list = self.query_one("#cluster-list", ClusterList)
            cluster_list.selected_cluster_name = None
            # Restore cursor visibility
            clusters_table = cluster_list.query_one("#clusters-table", DataTable)
            clusters_table.show_cursor = True
        except Exception:
            pass

        # Clear service list
        try:
            service_list = self.query_one("#service-list", ServiceList)
            service_list.services = []
            service_list.selected_service_name = None
        except Exception:
            pass

        # Clear task list
        try:
            task_list = self.query_one("#task-list", TaskList)
            task_list.service = None
        except Exception:
            pass

        # Focus clusters panel
        self._focus_clusters_panel()

    def _select_service(self, service: Service) -> None:
        """Select a service and show its tasks.

        Args:
            service: Service to select
        """
        logger.info(f"Selected service: {service.name}")
        self.selected_service = service

        # Update service list selection indicator
        try:
            service_list = self.query_one("#service-list", ServiceList)
            service_list.selected_service_name = service.name
            # Hide cursor in services table
            services_table = service_list.query_one("#services-table", DataTable)
            services_table.show_cursor = False
        except Exception:
            pass

        # Update task list
        try:
            task_list = self.query_one("#task-list", TaskList)
            task_list.service = service
        except Exception:
            pass

        # Focus tasks panel
        self._focus_tasks_panel()

    def _deselect_service(self) -> None:
        """Deselect the current service."""
        self.selected_service = None

        # Clear service selection indicator
        try:
            service_list = self.query_one("#service-list", ServiceList)
            service_list.selected_service_name = None
            # Restore cursor visibility
            services_table = service_list.query_one("#services-table", DataTable)
            services_table.show_cursor = True
        except Exception:
            pass

        # Clear task list
        try:
            task_list = self.query_one("#task-list", TaskList)
            task_list.service = None
        except Exception:
            pass

        # Focus services panel
        self._focus_services_panel()

    def _focus_clusters_panel(self) -> None:
        """Focus the clusters panel."""
        self.focus_panel = FocusPanel.CLUSTERS
        try:
            cluster_list = self.query_one("#cluster-list", ClusterList)
            clusters_table = cluster_list.query_one("#clusters-table", DataTable)
            clusters_table.focus()
        except Exception:
            pass

    def _focus_services_panel(self) -> None:
        """Focus the services panel."""
        self.focus_panel = FocusPanel.SERVICES
        try:
            service_list = self.query_one("#service-list", ServiceList)
            services_table = service_list.query_one("#services-table", DataTable)
            services_table.focus()
        except Exception:
            pass

    def _focus_tasks_panel(self) -> None:
        """Focus the tasks panel."""
        self.focus_panel = FocusPanel.TASKS
        try:
            task_list = self.query_one("#task-list", TaskList)
            tasks_table = task_list.query_one("#tasks-table", DataTable)
            tasks_table.focus()
        except Exception:
            pass

    def on_cluster_selected(self, event: ClusterSelected) -> None:
        """Handle cluster selection from the cluster list."""
        self._select_cluster(event.cluster)

    def on_cluster_deselected(self, event: ClusterDeselected) -> None:
        """Handle cluster deselection."""
        self._deselect_cluster()

    def on_service_selected(self, event: ServiceSelected) -> None:
        """Handle service selection."""
        self._select_service(event.service)

    def on_service_deselected(self, event: ServiceDeselected) -> None:
        """Handle service deselection or going back to clusters."""
        if self.selected_service is not None:
            # A service was selected, deselect it
            self._deselect_service()
        else:
            # No service selected, go back to clusters
            self._deselect_cluster()

    def on_task_deselected(self, event: TaskDeselected) -> None:
        """Handle task deselection (escape from task panel)."""
        self._deselect_service()

    def action_go_back(self) -> None:
        """Handle escape key to go back through the hierarchy."""
        if self.focus_panel == FocusPanel.TASKS and self.selected_service is not None:
            # From tasks panel, go back to services
            self._deselect_service()
        elif (
            self.focus_panel == FocusPanel.SERVICES
            and self.selected_cluster is not None
        ):
            # From services panel, go back to clusters
            self._deselect_cluster()
        # From clusters panel, do nothing (or could quit)

    def action_refresh(self) -> None:
        """Handle manual refresh request."""
        self.notify("Refreshing...")
        self._fetch_cluster_list()
        if self.selected_cluster is not None:
            self._fetch_cluster_data()

    def action_open_console(self) -> None:
        """Open the appropriate console URL in a browser."""
        if self.selected_cluster is None:
            return

        region = self.config.cluster.region
        cluster_name = self.selected_cluster.name
        url = None

        if self.selected_service is not None:
            # Check if there's a selected task in the task list
            try:
                task_list = self.query_one("#task-list", TaskList)
                task, container = task_list.get_selected_task_and_container()

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
            # Check if there's a highlighted service in the service list
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
            if open_in_browser(url):
                self.notify("Opening in browser...")
            else:
                self.notify(f"Failed to open browser. URL: {url}", severity="warning")

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
