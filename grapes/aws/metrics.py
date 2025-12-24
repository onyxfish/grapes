"""CloudWatch Container Insights metrics fetching."""

import logging
from collections.abc import Callable
from datetime import datetime, timedelta, timezone
from typing import Any

from grapes.aws.client import AWSClients
from grapes.models import Cluster, Service, Task, Container
from grapes.utils.ids import sanitize_metric_id

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
        if self._progress_callback:
            self._progress_callback(message)

    def set_progress_callback(self, callback: ProgressCallback | None) -> None:
        """Set or clear the progress callback."""
        self._progress_callback = callback

    def check_container_insights(self) -> bool:
        """Check if Container Insights is enabled for cluster.

        Returns:
            True if Container Insights is enabled and has data
        """
        logger.debug(
            f"Checking Container Insights for cluster: {self.clients.cluster_name}"
        )
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
            logger.info(f"Container Insights enabled: {self._insights_enabled}")
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
        """Fetch and attach metrics to all services and containers in cluster.

        Modifies services and containers in-place to add cpu_used and memory_used.

        Args:
            cluster: Cluster object with services and tasks populated
        """
        logger.info(f"Fetching metrics for cluster: {cluster.name}")
        # Always fetch service-level metrics (doesn't require Container Insights)
        self._fetch_service_metrics(cluster)

        # Only fetch container-level metrics if Container Insights is enabled
        if self.insights_enabled:
            self._fetch_container_metrics(cluster)
        else:
            logger.info("Container Insights not enabled, skipping container metrics")

    def _fetch_service_metrics(self, cluster: Cluster) -> None:
        """Fetch service-level CPU and memory utilization metrics.

        Uses AWS/ECS namespace metrics which are always available.

        Args:
            cluster: Cluster object with services populated
        """
        if not cluster.services:
            logger.debug("No services to fetch metrics for")
            return

        logger.debug(f"Fetching service metrics for {len(cluster.services)} services")
        self._report_progress(
            f"Fetching metrics for {len(cluster.services)} services..."
        )

        # Build metric queries for services
        metric_queries = self._build_service_metric_queries(
            cluster.name, cluster.services
        )

        if not metric_queries:
            logger.debug("No metric queries built for services")
            return

        # Fetch metrics in batches
        all_results = self._fetch_metrics_batched(metric_queries)
        logger.debug(f"Received {len(all_results)} service metric results")

        # Attach results to services
        self._attach_metrics_to_services(cluster.services, all_results)

    def _fetch_container_metrics(self, cluster: Cluster) -> None:
        """Fetch container-level metrics from Container Insights.

        Args:
            cluster: Cluster object with services and tasks populated
        """
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
        metric_queries = self._build_container_metric_queries(
            cluster.name, containers_to_fetch
        )

        if not metric_queries:
            return

        # Fetch metrics in batches
        all_results = self._fetch_metrics_batched(metric_queries)

        # Parse and attach results to containers
        self._attach_metrics_to_containers(containers_to_fetch, all_results)

    def _build_service_metric_queries(
        self,
        cluster_name: str,
        services: list[Service],
    ) -> list[dict[str, Any]]:
        """Build GetMetricData queries for service-level metrics.

        Uses AWS/ECS namespace which is always available (no Container Insights needed).

        Args:
            cluster_name: Name of the ECS cluster
            services: List of Service objects

        Returns:
            List of metric query dictionaries
        """
        queries = []

        for service in services:
            # CPU utilization metric
            cpu_id = sanitize_metric_id(f"svc_cpu_{service.name}")
            queries.append(
                {
                    "Id": cpu_id,
                    "MetricStat": {
                        "Metric": {
                            "Namespace": "AWS/ECS",
                            "MetricName": "CPUUtilization",
                            "Dimensions": [
                                {"Name": "ClusterName", "Value": cluster_name},
                                {"Name": "ServiceName", "Value": service.name},
                            ],
                        },
                        "Period": 60,
                        "Stat": "Average",
                    },
                    "ReturnData": True,
                }
            )

            # Memory utilization metric
            mem_id = sanitize_metric_id(f"svc_mem_{service.name}")
            queries.append(
                {
                    "Id": mem_id,
                    "MetricStat": {
                        "Metric": {
                            "Namespace": "AWS/ECS",
                            "MetricName": "MemoryUtilization",
                            "Dimensions": [
                                {"Name": "ClusterName", "Value": cluster_name},
                                {"Name": "ServiceName", "Value": service.name},
                            ],
                        },
                        "Period": 60,
                        "Stat": "Average",
                    },
                    "ReturnData": True,
                }
            )

        return queries

    def _build_container_metric_queries(
        self,
        cluster_name: str,
        containers: list[tuple[Task, Container]],
    ) -> list[dict[str, Any]]:
        """Build GetMetricData queries for container-level metrics.

        Uses ECS/ContainerInsights namespace (requires Container Insights).

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

    def _attach_metrics_to_services(
        self,
        services: list[Service],
        metrics: dict[str, float | None],
    ) -> None:
        """Attach fetched metrics to service objects.

        Args:
            services: List of Service objects
            metrics: Dict mapping metric ID to value
        """
        for service in services:
            cpu_id = sanitize_metric_id(f"svc_cpu_{service.name}")
            mem_id = sanitize_metric_id(f"svc_mem_{service.name}")

            cpu_value = metrics.get(cpu_id)
            mem_value = metrics.get(mem_id)

            # Set values (None if no data)
            service.cpu_used = cpu_value
            service.memory_used = mem_value

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

    def fetch_service_metrics_history(
        self,
        service_name: str,
        minutes: int = 60,
    ) -> tuple[
        list[float],
        list[float],
        list[datetime],
        tuple[float, float, float],
        tuple[float, float, float],
    ]:
        """Fetch historical metrics for a service.

        Uses AWS/ECS namespace which is always available (no Container Insights needed).

        Args:
            service_name: Name of service
            minutes: Number of minutes of history to fetch

        Returns:
            Tuple of (cpu_history, memory_history, timestamps, cpu_stats, mem_stats)
            where stats is (min, max, avg)
        """
        cluster_name = self.clients.cluster_name
        if not cluster_name:
            logger.warning("No cluster name set, cannot fetch metrics history")
            return [], [], [], (0, 0, 0), (0, 0, 0)

        now = datetime.now(timezone.utc)
        start_time = now - timedelta(minutes=minutes)

        logger.info(
            f"Fetching service metrics history for {service_name} "
            f"from {start_time} to {now}"
        )

        # Build queries for CPU and memory using AWS/ECS namespace
        cpu_id = sanitize_metric_id(f"svc_hist_cpu_{service_name}")
        cpu_min_id = sanitize_metric_id(f"svc_hist_cpu_min_{service_name}")
        cpu_max_id = sanitize_metric_id(f"svc_hist_cpu_max_{service_name}")
        mem_id = sanitize_metric_id(f"svc_hist_mem_{service_name}")
        mem_min_id = sanitize_metric_id(f"svc_hist_mem_min_{service_name}")
        mem_max_id = sanitize_metric_id(f"svc_hist_mem_max_{service_name}")

        queries = [
            {
                "Id": cpu_id,
                "MetricStat": {
                    "Metric": {
                        "Namespace": "AWS/ECS",
                        "MetricName": "CPUUtilization",
                        "Dimensions": [
                            {"Name": "ClusterName", "Value": cluster_name},
                            {"Name": "ServiceName", "Value": service_name},
                        ],
                    },
                    "Period": 60,  # 1-minute resolution
                    "Stat": "Average",
                },
                "ReturnData": True,
            },
            {
                "Id": cpu_min_id,
                "MetricStat": {
                    "Metric": {
                        "Namespace": "AWS/ECS",
                        "MetricName": "CPUUtilization",
                        "Dimensions": [
                            {"Name": "ClusterName", "Value": cluster_name},
                            {"Name": "ServiceName", "Value": service_name},
                        ],
                    },
                    "Period": 60,
                    "Stat": "Minimum",
                },
                "ReturnData": True,
            },
            {
                "Id": cpu_max_id,
                "MetricStat": {
                    "Metric": {
                        "Namespace": "AWS/ECS",
                        "MetricName": "CPUUtilization",
                        "Dimensions": [
                            {"Name": "ClusterName", "Value": cluster_name},
                            {"Name": "ServiceName", "Value": service_name},
                        ],
                    },
                    "Period": 60,
                    "Stat": "Maximum",
                },
                "ReturnData": True,
            },
            {
                "Id": mem_id,
                "MetricStat": {
                    "Metric": {
                        "Namespace": "AWS/ECS",
                        "MetricName": "MemoryUtilization",
                        "Dimensions": [
                            {"Name": "ClusterName", "Value": cluster_name},
                            {"Name": "ServiceName", "Value": service_name},
                        ],
                    },
                    "Period": 60,
                    "Stat": "Average",
                },
                "ReturnData": True,
            },
            {
                "Id": mem_min_id,
                "MetricStat": {
                    "Metric": {
                        "Namespace": "AWS/ECS",
                        "MetricName": "MemoryUtilization",
                        "Dimensions": [
                            {"Name": "ClusterName", "Value": cluster_name},
                            {"Name": "ServiceName", "Value": service_name},
                        ],
                    },
                    "Period": 60,
                    "Stat": "Minimum",
                },
                "ReturnData": True,
            },
            {
                "Id": mem_max_id,
                "MetricStat": {
                    "Metric": {
                        "Namespace": "AWS/ECS",
                        "MetricName": "MemoryUtilization",
                        "Dimensions": [
                            {"Name": "ClusterName", "Value": cluster_name},
                            {"Name": "ServiceName", "Value": service_name},
                        ],
                    },
                    "Period": 60,
                    "Stat": "Maximum",
                },
                "ReturnData": True,
            },
        ]

        try:
            response = self.clients.cloudwatch.get_metric_data(
                MetricDataQueries=queries,
                StartTime=start_time,
                EndTime=now,
            )

            # Parse results - CloudWatch returns newest first by default
            cpu_data: dict[datetime, float] = {}
            mem_data: dict[datetime, float] = {}

            cpu_min: float | None = None
            cpu_max: float | None = None
            cpu_avg: float | None = None
            mem_min: float | None = None
            mem_max: float | None = None
            mem_avg: float | None = None

            for result in response.get("MetricDataResults", []):
                metric_id = result.get("Id", "")
                values = result.get("Values", [])
                times = result.get("Timestamps", [])

                logger.debug(
                    f"Service metric {metric_id}: {len(values)} values, "
                    f"{len(times)} timestamps"
                )

                if metric_id == cpu_id:
                    for ts, val in zip(times, values):
                        cpu_data[ts] = val
                elif metric_id == cpu_min_id:
                    if values:
                        cpu_min = min(values)
                elif metric_id == cpu_max_id:
                    if values:
                        cpu_max = max(values)
                elif metric_id == mem_id:
                    for ts, val in zip(times, values):
                        mem_data[ts] = val
                elif metric_id == mem_min_id:
                    if values:
                        mem_min = min(values)
                elif metric_id == mem_max_id:
                    if values:
                        mem_max = max(values)

            # Merge timestamps and sort chronologically (oldest first)
            all_timestamps = sorted(set(cpu_data.keys()) | set(mem_data.keys()))

            if not all_timestamps:
                logger.warning(f"No metrics data found for service {service_name}")
                return [], [], [], (0, 0, 0), (0, 0, 0)

            # Build aligned lists
            cpu_values: list[float] = []
            mem_values: list[float] = []
            timestamps: list[datetime] = []

            for ts in all_timestamps:
                cpu_val = cpu_data.get(ts, 0.0)
                mem_val = mem_data.get(ts, 0.0)

                timestamps.append(ts)
                cpu_values.append(cpu_val)
                mem_values.append(mem_val)

            # Calculate averages if not provided
            cpu_avg_final = (
                cpu_avg
                if cpu_avg is not None
                else (sum(cpu_values) / len(cpu_values))
                if cpu_values
                else 0.0
            )
            mem_avg_final = (
                mem_avg
                if mem_avg is not None
                else (sum(mem_values) / len(mem_values))
                if mem_values
                else 0.0
            )

            cpu_stats = (cpu_min or 0.0, cpu_max or 0.0, cpu_avg_final)
            mem_stats = (mem_min or 0.0, mem_max or 0.0, mem_avg_final)

            logger.info(
                f"Fetched {len(cpu_values)} historical data points for "
                f"service {service_name}"
            )

            return cpu_values, mem_values, timestamps, cpu_stats, mem_stats

        except Exception as e:
            logger.error(f"Failed to fetch service metrics history: {e}")
            import traceback

            logger.debug(traceback.format_exc())
            return [], [], [], (0, 0, 0), (0, 0, 0)

        now = datetime.now(timezone.utc)
        start_time = now - timedelta(minutes=minutes)

        logger.info(
            f"Fetching service metrics history for {service_name} "
            f"from {start_time} to {now}"
        )

        # Build queries for CPU and memory using AWS/ECS namespace
        cpu_id = sanitize_metric_id(f"svc_hist_cpu_{service_name}")
        mem_id = sanitize_metric_id(f"svc_hist_mem_{service_name}")

        queries = [
            {
                "Id": cpu_id,
                "MetricStat": {
                    "Metric": {
                        "Namespace": "AWS/ECS",
                        "MetricName": "CPUUtilization",
                        "Dimensions": [
                            {"Name": "ClusterName", "Value": cluster_name},
                            {"Name": "ServiceName", "Value": service_name},
                        ],
                    },
                    "Period": 60,  # 1-minute resolution
                    "Stat": "Average",
                },
                "ReturnData": True,
            },
            {
                "Id": mem_id,
                "MetricStat": {
                    "Metric": {
                        "Namespace": "AWS/ECS",
                        "MetricName": "MemoryUtilization",
                        "Dimensions": [
                            {"Name": "ClusterName", "Value": cluster_name},
                            {"Name": "ServiceName", "Value": service_name},
                        ],
                    },
                    "Period": 60,
                    "Stat": "Average",
                },
                "ReturnData": True,
            },
        ]

        try:
            response = self.clients.cloudwatch.get_metric_data(
                MetricDataQueries=queries,
                StartTime=start_time,
                EndTime=now,
            )

            # Parse results - CloudWatch returns newest first by default
            cpu_data: dict[datetime, float] = {}
            mem_data: dict[datetime, float] = {}

            for result in response.get("MetricDataResults", []):
                metric_id = result.get("Id", "")
                values = result.get("Values", [])
                times = result.get("Timestamps", [])

                logger.debug(
                    f"Service metric {metric_id}: {len(values)} values, "
                    f"{len(times)} timestamps"
                )

                if metric_id == cpu_id:
                    for ts, val in zip(times, values):
                        cpu_data[ts] = val
                elif metric_id == mem_id:
                    for ts, val in zip(times, values):
                        mem_data[ts] = val

            # Merge timestamps and sort chronologically (oldest first)
            all_timestamps = sorted(set(cpu_data.keys()) | set(mem_data.keys()))

            if not all_timestamps:
                logger.warning(f"No metrics data found for service {service_name}")
                return [], [], []

            # Build aligned lists
            cpu_values: list[float] = []
            mem_values: list[float] = []
            timestamps: list[datetime] = []

            for ts in all_timestamps:
                cpu_val = cpu_data.get(ts, 0.0)
                mem_val = mem_data.get(ts, 0.0)

                timestamps.append(ts)
                cpu_values.append(cpu_val)
                mem_values.append(mem_val)

            logger.info(
                f"Fetched {len(cpu_values)} historical data points for "
                f"service {service_name}"
            )

            return cpu_values, mem_values, timestamps

        except Exception as e:
            logger.error(f"Failed to fetch service metrics history: {e}")
            import traceback

            logger.debug(traceback.format_exc())
            return [], [], []

    def fetch_container_metrics_history(
        self,
        task: Task,
        container: Container,
        minutes: int = 60,
    ) -> tuple[
        list[float],
        list[float],
        list[datetime],
        tuple[float, float, float],
        tuple[float, float, float],
    ]:
        """Fetch historical metrics for a specific container.

        Args:
            task: The task containing container
            container: The container to fetch metrics for
            minutes: Number of minutes of history to fetch

        Returns:
            Tuple of (cpu_history, memory_history, timestamps, cpu_stats, mem_stats)
            where stats is (min, max, avg)
        """
        cluster_name = self.clients.cluster_name
        if not cluster_name:
            logger.warning("No cluster name set, cannot fetch metrics history")
            return [], [], [], (0, 0, 0), (0, 0, 0)

        now = datetime.now(timezone.utc)
        start_time = now - timedelta(minutes=minutes)

        logger.info(
            f"Fetching metrics history for {task.short_id}/{container.name} "
            f"from {start_time} to {now}"
        )

        # Build queries for CPU and memory
        cpu_id = sanitize_metric_id(f"hist_cpu_{task.short_id}_{container.name}")
        cpu_min_id = sanitize_metric_id(
            f"hist_cpu_min_{task.short_id}_{container.name}"
        )
        cpu_max_id = sanitize_metric_id(
            f"hist_cpu_max_{task.short_id}_{container.name}"
        )
        mem_id = sanitize_metric_id(f"hist_mem_{task.short_id}_{container.name}")
        mem_min_id = sanitize_metric_id(
            f"hist_mem_min_{task.short_id}_{container.name}"
        )
        mem_max_id = sanitize_metric_id(
            f"hist_mem_max_{task.short_id}_{container.name}"
        )

        queries = [
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
                    "Period": 60,  # 1-minute resolution
                    "Stat": "Average",
                },
                "ReturnData": True,
            },
            {
                "Id": cpu_min_id,
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
                    "Stat": "Minimum",
                },
                "ReturnData": True,
            },
            {
                "Id": cpu_max_id,
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
                    "Stat": "Maximum",
                },
                "ReturnData": True,
            },
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
            },
            {
                "Id": mem_min_id,
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
                    "Stat": "Minimum",
                },
                "ReturnData": True,
            },
            {
                "Id": mem_max_id,
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
                    "Stat": "Maximum",
                },
                "ReturnData": True,
            },
        ]

        try:
            response = self.clients.cloudwatch.get_metric_data(
                MetricDataQueries=queries,
                StartTime=start_time,
                EndTime=now,
            )

            # Parse results - CloudWatch returns newest first by default
            cpu_data: dict[datetime, float] = {}
            mem_data: dict[datetime, float] = {}

            cpu_min: float | None = None
            cpu_max: float | None = None
            cpu_avg: float | None = None
            mem_min: float | None = None
            mem_max: float | None = None
            mem_avg: float | None = None

            for result in response.get("MetricDataResults", []):
                metric_id = result.get("Id", "")
                values = result.get("Values", [])
                times = result.get("Timestamps", [])

                logger.debug(
                    f"Metric {metric_id}: {len(values)} values, {len(times)} timestamps"
                )

                if metric_id == cpu_id:
                    for ts, val in zip(times, values):
                        cpu_data[ts] = val
                elif metric_id == cpu_min_id:
                    if values:
                        cpu_min = min(values)
                elif metric_id == cpu_max_id:
                    if values:
                        cpu_max = max(values)
                elif metric_id == mem_id:
                    for ts, val in zip(times, values):
                        mem_data[ts] = val
                elif metric_id == mem_min_id:
                    if values:
                        mem_min = min(values)
                elif metric_id == mem_max_id:
                    if values:
                        mem_max = max(values)

            # Merge timestamps and sort chronologically (oldest first)
            all_timestamps = sorted(set(cpu_data.keys()) | set(mem_data.keys()))

            if not all_timestamps:
                logger.warning(
                    f"No metrics data found for {task.short_id}/{container.name}. "
                    "Container Insights may not be enabled."
                )
                return [], [], [], (0, 0, 0), (0, 0, 0)

            # Build aligned lists
            cpu_values: list[float] = []
            mem_values: list[float] = []
            timestamps: list[datetime] = []

            for ts in all_timestamps:
                # Only include timestamps where we have both metrics
                # or use 0 as placeholder if one is missing
                cpu_val = cpu_data.get(ts, 0.0)
                mem_val = mem_data.get(ts, 0.0)

                timestamps.append(ts)
                cpu_values.append(cpu_val)
                mem_values.append(mem_val)

            # Calculate averages if not provided
            cpu_avg_final = (
                cpu_avg
                if cpu_avg is not None
                else (sum(cpu_values) / len(cpu_values))
                if cpu_values
                else 0.0
            )
            mem_avg_final = (
                mem_avg
                if mem_avg is not None
                else (sum(mem_values) / len(mem_values))
                if mem_values
                else 0.0
            )

            cpu_stats = (cpu_min or 0.0, cpu_max or 0.0, cpu_avg_final)
            mem_stats = (mem_min or 0.0, mem_max or 0.0, mem_avg_final)

            logger.info(
                f"Fetched {len(cpu_values)} historical data points for "
                f"{task.short_id}/{container.name}"
            )

            return cpu_values, mem_values, timestamps, cpu_stats, mem_stats

        except Exception as e:
            logger.error(f"Failed to fetch container metrics history: {e}")
            import traceback

            logger.debug(traceback.format_exc())
            return [], [], [], (0, 0, 0), (0, 0, 0)

        now = datetime.now(timezone.utc)
        start_time = now - timedelta(minutes=minutes)

        logger.info(
            f"Fetching metrics history for {task.short_id}/{container.name} "
            f"from {start_time} to {now}"
        )

        # Build queries for CPU and memory
        cpu_id = sanitize_metric_id(f"hist_cpu_{task.short_id}_{container.name}")
        mem_id = sanitize_metric_id(f"hist_mem_{task.short_id}_{container.name}")

        queries = [
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
                    "Period": 60,  # 1-minute resolution
                    "Stat": "Average",
                },
                "ReturnData": True,
            },
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
            },
        ]

        try:
            response = self.clients.cloudwatch.get_metric_data(
                MetricDataQueries=queries,
                StartTime=start_time,
                EndTime=now,
            )

            # Parse results - CloudWatch returns newest first by default
            cpu_data: dict[datetime, float] = {}
            mem_data: dict[datetime, float] = {}

            for result in response.get("MetricDataResults", []):
                metric_id = result.get("Id", "")
                values = result.get("Values", [])
                times = result.get("Timestamps", [])

                logger.debug(
                    f"Metric {metric_id}: {len(values)} values, {len(times)} timestamps"
                )

                if metric_id == cpu_id:
                    for ts, val in zip(times, values):
                        cpu_data[ts] = val
                elif metric_id == mem_id:
                    for ts, val in zip(times, values):
                        mem_data[ts] = val

            # Merge timestamps and sort chronologically (oldest first)
            all_timestamps = sorted(set(cpu_data.keys()) | set(mem_data.keys()))

            if not all_timestamps:
                logger.warning(
                    f"No metrics data found for {task.short_id}/{container.name}. "
                    "Container Insights may not be enabled."
                )
                return [], [], []

            # Build aligned lists
            cpu_values: list[float] = []
            mem_values: list[float] = []
            timestamps: list[datetime] = []

            for ts in all_timestamps:
                # Only include timestamps where we have both metrics
                # or use 0 as placeholder if one is missing
                cpu_val = cpu_data.get(ts, 0.0)
                mem_val = mem_data.get(ts, 0.0)

                timestamps.append(ts)
                cpu_values.append(cpu_val)
                mem_values.append(mem_val)

            logger.info(
                f"Fetched {len(cpu_values)} historical data points for "
                f"{task.short_id}/{container.name}"
            )

            return cpu_values, mem_values, timestamps

        except Exception as e:
            logger.error(f"Failed to fetch container metrics history: {e}")
            import traceback

            logger.debug(traceback.format_exc())
            return [], [], []
