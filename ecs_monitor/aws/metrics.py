"""CloudWatch Container Insights metrics fetching."""

import logging
from collections.abc import Callable
from datetime import datetime, timedelta, timezone
from typing import Any

from ecs_monitor.aws.client import AWSClients
from ecs_monitor.models import Cluster, Task, Container
from ecs_monitor.utils.ids import sanitize_metric_id

logger = logging.getLogger(__name__)

# Type alias for progress callback
ProgressCallback = Callable[[str], None]


class MetricsFetcher:
    """Fetches container metrics from CloudWatch Container Insights."""

    # Maximum metrics per GetMetricData call
    MAX_METRICS_PER_CALL = 500

    def __init__(
        self, clients: AWSClients, progress_callback: ProgressCallback | None = None
    ):
        """Initialize the metrics fetcher.

        Args:
            clients: AWS clients container
            progress_callback: Optional callback for progress updates
        """
        self.clients = clients
        self._insights_enabled: bool | None = None
        self._progress_callback = progress_callback

    def _report_progress(self, message: str) -> None:
        """Report progress if callback is set."""
        logger.info(message)
        if self._progress_callback:
            self._progress_callback(message)

    def set_progress_callback(self, callback: ProgressCallback | None) -> None:
        """Set or clear the progress callback."""
        self._progress_callback = callback

    def check_container_insights(self) -> bool:
        """Check if Container Insights is enabled for the cluster.

        Returns:
            True if Container Insights is enabled and has data
        """
        self._report_progress("Checking Container Insights status...")
        try:
            response = self.clients.cloudwatch.get_metric_statistics(
                Namespace="ECS/ContainerInsights",
                MetricName="CpuUtilized",
                Dimensions=[
                    {"Name": "ClusterName", "Value": self.clients.cluster_name}
                ],
                StartTime=datetime.now(timezone.utc) - timedelta(minutes=10),
                EndTime=datetime.now(timezone.utc),
                Period=300,
                Statistics=["Average"],
            )
            # If we get datapoints, Container Insights is enabled
            self._insights_enabled = len(response.get("Datapoints", [])) > 0
            return self._insights_enabled
        except Exception as e:
            logger.warning(f"Failed to check Container Insights: {e}")
            self._insights_enabled = False
            return False

    @property
    def insights_enabled(self) -> bool:
        """Check if Container Insights is enabled (cached)."""
        if self._insights_enabled is None:
            return self.check_container_insights()
        return self._insights_enabled

    def fetch_metrics_for_cluster(self, cluster: Cluster) -> None:
        """Fetch and attach metrics to all containers in the cluster.

        Modifies containers in-place to add cpu_used and memory_used.

        Args:
            cluster: Cluster object with services and tasks populated
        """
        if not self.insights_enabled:
            logger.info("Container Insights not enabled, skipping metrics fetch")
            return

        # Collect all containers that need metrics
        containers_to_fetch: list[tuple[Task, Container]] = []
        for service in cluster.services:
            for task in service.tasks:
                for container in task.containers:
                    if task.status == "RUNNING":
                        containers_to_fetch.append((task, container))

        if not containers_to_fetch:
            logger.debug("No running containers to fetch metrics for")
            return

        self._report_progress(
            f"Fetching metrics for {len(containers_to_fetch)} containers..."
        )

        # Build metric queries
        metric_queries = self._build_metric_queries(cluster.name, containers_to_fetch)

        if not metric_queries:
            return

        # Fetch metrics in batches
        all_results = self._fetch_metrics_batched(metric_queries)

        # Parse and attach results to containers
        self._attach_metrics_to_containers(containers_to_fetch, all_results)

    def _build_metric_queries(
        self,
        cluster_name: str,
        containers: list[tuple[Task, Container]],
    ) -> list[dict[str, Any]]:
        """Build GetMetricData queries for all containers.

        Args:
            cluster_name: Name of the ECS cluster
            containers: List of (task, container) tuples

        Returns:
            List of metric query dictionaries
        """
        queries = []

        for task, container in containers:
            # CPU metric
            cpu_id = sanitize_metric_id(f"cpu_{task.short_id}_{container.name}")
            queries.append(
                {
                    "Id": cpu_id,
                    "MetricStat": {
                        "Metric": {
                            "Namespace": "ECS/ContainerInsights",
                            "MetricName": "CpuUtilized",
                            "Dimensions": [
                                {"Name": "ClusterName", "Value": cluster_name},
                                {"Name": "TaskId", "Value": task.id},
                                {"Name": "ContainerName", "Value": container.name},
                            ],
                        },
                        "Period": 60,
                        "Stat": "Average",
                    },
                    "ReturnData": True,
                }
            )

            # Memory metric
            mem_id = sanitize_metric_id(f"mem_{task.short_id}_{container.name}")
            queries.append(
                {
                    "Id": mem_id,
                    "MetricStat": {
                        "Metric": {
                            "Namespace": "ECS/ContainerInsights",
                            "MetricName": "MemoryUtilized",
                            "Dimensions": [
                                {"Name": "ClusterName", "Value": cluster_name},
                                {"Name": "TaskId", "Value": task.id},
                                {"Name": "ContainerName", "Value": container.name},
                            ],
                        },
                        "Period": 60,
                        "Stat": "Average",
                    },
                    "ReturnData": True,
                }
            )

        return queries

    def _fetch_metrics_batched(
        self, metric_queries: list[dict[str, Any]]
    ) -> dict[str, float | None]:
        """Fetch metrics in batches of MAX_METRICS_PER_CALL.

        Args:
            metric_queries: List of metric query dictionaries

        Returns:
            Dict mapping metric ID to value (or None if no data)
        """
        results: dict[str, float | None] = {}

        now = datetime.now(timezone.utc)
        start_time = now - timedelta(minutes=2)

        for i in range(0, len(metric_queries), self.MAX_METRICS_PER_CALL):
            batch = metric_queries[i : i + self.MAX_METRICS_PER_CALL]

            try:
                response = self.clients.cloudwatch.get_metric_data(
                    MetricDataQueries=batch,
                    StartTime=start_time,
                    EndTime=now,
                )

                for result in response.get("MetricDataResults", []):
                    metric_id = result.get("Id", "")
                    values = result.get("Values", [])

                    if values:
                        # Use most recent value
                        results[metric_id] = values[0]
                    else:
                        results[metric_id] = None

            except Exception as e:
                logger.warning(f"Failed to fetch metrics batch: {e}")
                # Mark all metrics in batch as None
                for query in batch:
                    results[query["Id"]] = None

        return results

    def _attach_metrics_to_containers(
        self,
        containers: list[tuple[Task, Container]],
        metrics: dict[str, float | None],
    ) -> None:
        """Attach fetched metrics to container objects.

        Args:
            containers: List of (task, container) tuples
            metrics: Dict mapping metric ID to value
        """
        for task, container in containers:
            cpu_id = sanitize_metric_id(f"cpu_{task.short_id}_{container.name}")
            mem_id = sanitize_metric_id(f"mem_{task.short_id}_{container.name}")

            cpu_value = metrics.get(cpu_id)
            mem_value = metrics.get(mem_id)

            # Only set if we have actual values (not None)
            if cpu_value is not None:
                # CPU is returned as percentage of vCPU
                container.cpu_used = cpu_value
            else:
                container.cpu_used = None

            if mem_value is not None:
                # Memory is returned in MiB
                container.memory_used = int(mem_value)
            else:
                container.memory_used = None
