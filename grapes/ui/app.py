"""Main Textual application for Grapes ECS Monitor."""

import logging
from enum import Enum, auto

from textual.app import App, ComposeResult
from textual.binding import Binding
from textual.command import Hit, Hits, Provider
from textual.containers import Container
from textual.reactive import reactive
from textual.widgets import Footer
from textual.worker import Worker, WorkerState

from grapes.aws.client import AWSClients
from grapes.aws.fetcher import ECSFetcher
from grapes.aws.metrics import MetricsFetcher
from grapes.config import Config
from grapes.models import Cluster
from grapes.ui.cluster_view import LoadingScreen
from grapes.ui.tree_view import TreeView, ClusterSelected
from grapes.ui.console_link import (
    build_cluster_url,
    build_container_url,
    build_service_url,
    build_task_url,
    open_in_browser,
)
from grapes.ui.debug_console import DebugConsole, TextualLogHandler
from grapes.ui.metrics_panel import MetricsPanel

logger = logging.getLogger(__name__)


class AppView(Enum):
    """Application view states."""

    LOADING = auto()
    MAIN = auto()


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
    """Main Grapes ECS Monitor application."""

    CSS_PATH = "styles.css"

    # Add our custom commands to the default set (which includes theme picker)
    COMMANDS = App.COMMANDS | {ToggleDebugConsoleCommand}

    BINDINGS = [
        Binding("q", "quit", "Quit"),
        Binding("r", "refresh", "Refresh"),
        Binding("o", "open_console", "Open in AWS Console"),
        Binding("v", "toggle_metrics_panel", "Metrics"),
        Binding("d", "toggle_debug_console", "Debug"),
    ]

    # Reactive state
    current_view: reactive[AppView] = reactive(AppView.LOADING)
    clusters: reactive[list[Cluster]] = reactive(list, always_update=True)
    loading: reactive[bool] = reactive(True)
    insights_enabled: reactive[bool] = reactive(False)
    debug_console_visible: reactive[bool] = reactive(False)
    metrics_panel_visible: reactive[bool] = reactive(False)

    # Track which cluster is currently being fetched
    _fetching_cluster: str | None = None

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
        self._cluster_data_worker: Worker | None = None

        # Track if a specific cluster was configured
        self._configured_cluster = config.cluster.name

    def _on_progress(self, message: str) -> None:
        """Handle progress updates from fetchers."""
        if self.loading:
            try:
                loading_screen = self.query_one("#loading", LoadingScreen)
                self.call_from_thread(loading_screen.update_status, message)
            except Exception:
                pass
        logger.debug(f"Progress: {message}")

    def compose(self) -> ComposeResult:
        """Compose the application layout."""
        yield LoadingScreen(id="loading")
        yield Container(
            TreeView(id="tree-view"),
            id="main-container",
        )
        yield MetricsPanel(id="metrics-panel")
        yield DebugConsole(id="debug-console")
        yield Footer()

    def on_mount(self) -> None:
        """Set up the application when mounted."""
        # Set up debug console logging handler
        debug_console = self.query_one("#debug-console", DebugConsole)
        handler = TextualLogHandler(debug_console, self)
        handler.setLevel(logging.INFO)

        root_logger = logging.getLogger()
        root_logger.addHandler(handler)
        if root_logger.level > logging.INFO:
            root_logger.setLevel(logging.INFO)

        # Hide main container initially, show loading
        self.query_one("#main-container").display = False
        self.query_one("#loading").display = True

        # Set up countdown timer
        try:
            tree_view = self.query_one("#tree-view", TreeView)
            tree_view.refresh_countdown = self.config.refresh.interval
        except Exception:
            pass

        # Start initial data fetch
        self._fetch_cluster_list()

        # Set up periodic refresh
        self.set_interval(
            self.config.refresh.interval,
            self._periodic_refresh,
        )

        # Set up countdown updater (every second)
        self.set_interval(1, self._update_countdown)

    def _periodic_refresh(self) -> None:
        """Periodic refresh callback."""
        logger.debug("Periodic refresh triggered")
        if not self.loading and self.current_view == AppView.MAIN:
            self._fetch_cluster_list()
            # Also refresh any loaded clusters
            self._refresh_loaded_clusters()
        # Reset countdown
        try:
            tree_view = self.query_one("#tree-view", TreeView)
            tree_view.refresh_countdown = self.config.refresh.interval
        except Exception:
            pass

    def _update_countdown(self) -> None:
        """Update the refresh countdown timer."""
        if self.loading:
            return
        try:
            tree_view = self.query_one("#tree-view", TreeView)
            if tree_view.refresh_countdown > 0:
                tree_view.refresh_countdown -= 1
        except Exception:
            pass

    def _refresh_loaded_clusters(self) -> None:
        """Refresh data for all loaded clusters."""
        try:
            tree_view = self.query_one("#tree-view", TreeView)
            cluster_names = list(tree_view._loaded_clusters.keys())
            logger.debug(f"Refreshing {len(cluster_names)} loaded clusters")
            for cluster_name in cluster_names:
                self._fetch_cluster_data(cluster_name)
        except Exception as e:
            logger.error(f"Failed to refresh loaded clusters: {e}")

    def _fetch_cluster_list(self) -> None:
        """Fetch the list of clusters."""
        if self._refresh_worker is not None and self._refresh_worker.is_running:
            logger.debug("Refresh already in progress, skipping")
            return

        logger.debug("Starting cluster list fetch")
        self._refresh_worker = self.run_worker(
            self._fetch_clusters_worker,
            name="fetch_clusters",
            exclusive=True,
            thread=True,
        )

    def _fetch_clusters_worker(self) -> list[Cluster]:
        """Fetch clusters in a worker thread."""
        try:
            clusters = self.ecs_fetcher.list_clusters()
            return clusters
        except Exception as e:
            logger.error(f"Failed to fetch clusters: {e}")
            return []

    def _fetch_cluster_data(self, cluster_name: str) -> None:
        """Fetch detailed data for a specific cluster.

        Args:
            cluster_name: Name of the cluster to fetch
        """
        # Don't start a new fetch if one is already running for this cluster
        if self._fetching_cluster == cluster_name:
            logger.debug(f"Already fetching cluster data for {cluster_name}, skipping")
            return

        logger.debug(f"Starting cluster data fetch for: {cluster_name}")
        self._fetching_cluster = cluster_name
        self.aws_clients.set_cluster_name(cluster_name)

        self._cluster_data_worker = self.run_worker(
            self._fetch_cluster_data_worker,
            name="fetch_cluster_data",
            thread=True,
        )

    def _fetch_cluster_data_worker(self) -> Cluster | None:
        """Fetch cluster data in a worker thread."""
        try:
            self.insights_enabled = self.metrics_fetcher.check_container_insights()
            cluster = self.ecs_fetcher.fetch_cluster_state()
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
        elif event.worker.name == "fetch_cluster_data":
            self._handle_cluster_data_result(event)
        elif event.worker.name in (
            "fetch_service_metrics_history",
            "fetch_task_metrics_history",
        ):
            self._handle_metrics_history_result(event)

    def _handle_clusters_fetch_result(self, event: Worker.StateChanged) -> None:
        """Handle result of clusters list fetch."""
        if event.state == WorkerState.SUCCESS:
            result = event.worker.result
            if result is not None:
                self.clusters = result
                logger.debug(f"Fetched {len(self.clusters)} clusters")

                is_initial_load = self.loading

                if self.loading:
                    self.loading = False
                    self.query_one("#loading").display = False
                    self.query_one("#main-container").display = True
                    self.current_view = AppView.MAIN

                # Update tree view
                try:
                    tree_view = self.query_one("#tree-view", TreeView)
                    tree_view.clusters = self.clusters
                except Exception:
                    pass

                # Auto-load configured cluster or single cluster on initial load
                if is_initial_load:
                    if self._configured_cluster:
                        self._fetch_cluster_data(self._configured_cluster)
                    elif len(self.clusters) == 1:
                        self._fetch_cluster_data(self.clusters[0].name)

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
        if event.state == WorkerState.SUCCESS:
            result = event.worker.result
            if result is not None:
                logger.debug(f"Loaded cluster data for: {result.name}")
                try:
                    tree_view = self.query_one("#tree-view", TreeView)
                    tree_view.update_cluster_data(result)
                except Exception:
                    pass

        elif event.state == WorkerState.ERROR:
            logger.error(f"Cluster data fetch failed: {event.worker.error}")
            self.notify(f"Error loading data: {event.worker.error}", severity="error")

        # Clear fetching state
        self._fetching_cluster = None

    def on_cluster_selected(self, event: ClusterSelected) -> None:
        """Handle cluster selection from tree view - load its data."""
        logger.info(f"Cluster selected: {event.cluster.name}")
        self._fetch_cluster_data(event.cluster.name)

    def action_refresh(self) -> None:
        """Handle manual refresh request."""
        logger.info("Manual refresh requested")
        self.notify("Refreshing...")
        self._fetch_cluster_list()
        self._refresh_loaded_clusters()

    def action_open_console(self) -> None:
        """Open the appropriate console URL in a browser."""
        logger.info("Open console requested")
        try:
            tree_view = self.query_one("#tree-view", TreeView)
            cluster, service, task, container = tree_view.get_selected_item()
        except Exception:
            return

        if cluster is None:
            return

        region = self.config.cluster.region
        url = None

        if container is not None and task is not None:
            url = build_container_url(cluster.name, task.id, region)
        elif task is not None:
            url = build_task_url(cluster.name, task.id, region)
        elif service is not None:
            url = build_service_url(cluster.name, service.name, region)
        else:
            url = build_cluster_url(cluster.name, region)

        logger.debug(f"Opening console URL: {url}")
        if url:
            if open_in_browser(url):
                self.notify("Opening in browser...")
            else:
                self.notify(f"Failed to open browser. URL: {url}", severity="warning")

    def action_toggle_debug_console(self) -> None:
        """Toggle the debug console visibility."""
        self.debug_console_visible = not self.debug_console_visible
        if self.debug_console_visible:
            # Close metrics panel when opening debug console (mutually exclusive)
            self.metrics_panel_visible = False
        logger.debug(f"Debug console visibility: {self.debug_console_visible}")

    def watch_debug_console_visible(self, visible: bool) -> None:
        """Update debug console visibility when state changes."""
        logger.debug(f"Setting debug console visible: {visible}")
        console = self.query_one("#debug-console", DebugConsole)
        if visible:
            console.add_class("visible")
        else:
            console.remove_class("visible")

    def action_toggle_metrics_panel(self) -> None:
        """Toggle the metrics panel visibility and load data if needed."""
        logger.debug("Toggle metrics panel requested")
        # Get the currently selected item
        try:
            tree_view = self.query_one("#tree-view", TreeView)
            cluster, service, task, container = tree_view.get_selected_item()
            logger.debug(
                f"Selected: cluster={cluster.name if cluster else None}, service={service.name if service else None}, task={task.short_id if task else None}"
            )
        except Exception:
            logger.warning("Failed to get selected item for metrics panel")
            return

        # Need at least a service to show metrics
        if service is None and task is None:
            self.notify(
                "Select a service, task, or container to view metrics",
                severity="warning",
            )
            return

        # If no specific container, use the first one from the task
        if task is not None and container is None and task.containers:
            container = task.containers[0]

        # Check if the same service/task is selected as currently displayed
        current_service = getattr(self, "_metrics_service", None)
        current_task = getattr(self, "_metrics_task", None)

        # Check for exact match on what's currently displayed
        exact_match = False
        if task is not None and current_task is not None and task.id == current_task.id:
            exact_match = True
        elif (
            task is None
            and service is not None
            and current_service is not None
            and current_task is None
            and service.arn == current_service.arn
        ):
            exact_match = True

        if exact_match and self.metrics_panel_visible:
            # Same selection, close panel
            self.metrics_panel_visible = False
        elif exact_match:
            # Same selection but panel closed, open it
            self.metrics_panel_visible = True
            self.debug_console_visible = False
            if task is not None:
                self._fetch_task_metrics_history(task, container)
            elif service is not None:
                self._fetch_service_metrics_history(service)
        else:
            # Different selection, switch to it (keep panel open)
            if not self.metrics_panel_visible:
                self.metrics_panel_visible = True
                self.debug_console_visible = False
            if task is not None:
                self._fetch_task_metrics_history(task, container)
            elif service is not None:
                self._fetch_service_metrics_history(service)

    def watch_metrics_panel_visible(self, visible: bool) -> None:
        """Update metrics panel visibility when state changes."""
        logger.debug(f"Setting metrics panel visible: {visible}")
        try:
            panel = self.query_one("#metrics-panel", MetricsPanel)
            if visible:
                panel.add_class("visible")
            else:
                panel.remove_class("visible")
        except Exception as e:
            logger.error(f"Failed to toggle metrics panel: {e}")

    def _fetch_service_metrics_history(self, service) -> None:
        """Fetch historical metrics for a service.

        Args:
            service: The service to fetch metrics for
        """
        self._metrics_service = service
        self._metrics_task = None
        self._metrics_container = None
        self.run_worker(
            self._fetch_service_metrics_history_worker,
            name="fetch_service_metrics_history",
            thread=True,
        )

    def _fetch_service_metrics_history_worker(self):
        """Worker to fetch service metrics history."""
        service = self._metrics_service

        cpu_history, mem_history, timestamps, cpu_stats, mem_stats = (
            self.metrics_fetcher.fetch_service_metrics_history(service.name, minutes=60)
        )
        return (
            "service",
            service,
            cpu_history,
            mem_history,
            timestamps,
            cpu_stats,
            mem_stats,
        )

    def _fetch_task_metrics_history(self, task, container) -> None:
        """Fetch historical metrics for a task/container.

        Args:
            task: The task to fetch metrics for
            container: The container (uses first container if None)
        """
        # If no specific container, use the first one
        if container is None and task.containers:
            container = task.containers[0]

        if container is None:
            self.notify("No container found for metrics", severity="warning")
            return

        # Run fetch in a worker to avoid blocking UI
        self._metrics_service = None
        self._metrics_task = task
        self._metrics_container = container
        self.run_worker(
            self._fetch_task_metrics_history_worker,
            name="fetch_task_metrics_history",
            thread=True,
        )

    def _fetch_task_metrics_history_worker(self):
        """Worker to fetch task/container metrics history."""
        task = self._metrics_task
        container = self._metrics_container

        cpu_history, mem_history, timestamps, cpu_stats, mem_stats = (
            self.metrics_fetcher.fetch_container_metrics_history(
                task, container, minutes=60
            )
        )
        return (
            "task",
            task,
            container,
            cpu_history,
            mem_history,
            timestamps,
            cpu_stats,
            mem_stats,
        )

    def _handle_metrics_history_result(self, event: Worker.StateChanged) -> None:
        """Handle result of metrics history fetch."""
        if event.state == WorkerState.SUCCESS:
            result = event.worker.result
            if result is not None:
                result_type = result[0]

                if result_type == "service":
                    (
                        _,
                        service,
                        cpu_history,
                        mem_history,
                        timestamps,
                        cpu_stats,
                        mem_stats,
                    ) = result
                    logger.info(
                        f"Received service metrics: {len(cpu_history)} CPU, "
                        f"{len(mem_history)} memory data points"
                    )
                    try:
                        panel = self.query_one("#metrics-panel", MetricsPanel)
                        panel.set_service_metrics_data(
                            service,
                            cpu_history,
                            mem_history,
                            timestamps,
                            cpu_stats,
                            mem_stats,
                        )
                    except Exception as e:
                        logger.error(f"Failed to update metrics panel: {e}")
                else:
                    (
                        _,
                        task,
                        container,
                        cpu_history,
                        mem_history,
                        timestamps,
                        cpu_stats,
                        mem_stats,
                    ) = result
                    logger.info(
                        f"Received task metrics: {len(cpu_history)} CPU, "
                        f"{len(mem_history)} memory data points"
                    )
                    try:
                        panel = self.query_one("#metrics-panel", MetricsPanel)
                        panel.set_task_metrics_data(
                            task,
                            container,
                            cpu_history,
                            mem_history,
                            timestamps,
                            cpu_stats,
                            mem_stats,
                        )
                    except Exception as e:
                        logger.error(f"Failed to update metrics panel: {e}")

                if not cpu_history and not mem_history:
                    self.notify(
                        "No metrics data available.",
                        severity="warning",
                    )
        elif event.state == WorkerState.ERROR:
            logger.error(f"Metrics history fetch failed: {event.worker.error}")
            self.notify(
                f"Failed to fetch metrics: {event.worker.error}", severity="error"
            )
