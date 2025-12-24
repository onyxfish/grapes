"""ECS data fetching with batching and caching."""

import logging
from collections.abc import Callable
from datetime import datetime, timezone

from grapes.aws.client import AWSClients
from grapes.models import (
    Cluster,
    Container,
    Deployment,
    HealthStatus,
    Service,
    Task,
)
from grapes.utils.ids import extract_task_definition_name

logger = logging.getLogger(__name__)

# Type alias for progress callback
ProgressCallback = Callable[[str], None]


class TaskDefinitionCache:
    """Cache for task definitions with TTL."""

    def __init__(self, ttl_seconds: int = 300):
        self._cache: dict[str, tuple[dict, datetime]] = {}
        self._ttl_seconds = ttl_seconds

    def get(self, task_def_arn: str) -> dict | None:
        """Get cached task definition if not expired."""
        if task_def_arn not in self._cache:
            return None

        data, cached_at = self._cache[task_def_arn]
        age = (datetime.now(timezone.utc) - cached_at).total_seconds()

        if age > self._ttl_seconds:
            del self._cache[task_def_arn]
            return None

        return data

    def set(self, task_def_arn: str, data: dict) -> None:
        """Cache a task definition."""
        self._cache[task_def_arn] = (data, datetime.now(timezone.utc))

    def clear(self) -> None:
        """Clear the cache."""
        self._cache.clear()


class ECSFetcher:
    """Fetches ECS cluster data with batching and caching."""

    # API batch limits
    DESCRIBE_SERVICES_BATCH_SIZE = 10
    DESCRIBE_TASKS_BATCH_SIZE = 100

    def __init__(
        self,
        clients: AWSClients,
        task_def_cache_ttl: int = 300,
        progress_callback: ProgressCallback | None = None,
    ):
        """Initialize the fetcher.

        Args:
            clients: AWS clients container
            task_def_cache_ttl: Task definition cache TTL in seconds
            progress_callback: Optional callback for progress updates
        """
        self.clients = clients
        self._task_def_cache = TaskDefinitionCache(ttl_seconds=task_def_cache_ttl)
        self._progress_callback = progress_callback

    def _report_progress(self, message: str) -> None:
        """Report progress if callback is set."""
        if self._progress_callback:
            self._progress_callback(message)

    def set_progress_callback(self, callback: ProgressCallback | None) -> None:
        """Set or clear the progress callback."""
        self._progress_callback = callback

    def list_clusters(self) -> list[Cluster]:
        """List all ECS clusters with basic information.

        Returns:
            List of Cluster objects with basic info (no services/tasks)
        """
        logger.info("Starting to list ECS clusters")
        self._report_progress("Listing clusters...")
        cluster_arns = self._list_cluster_arns()

        if not cluster_arns:
            logger.info("No clusters found")
            return []

        logger.debug(f"Found {len(cluster_arns)} cluster ARNs")
        self._report_progress(
            f"Found {len(cluster_arns)} clusters, fetching details..."
        )
        clusters = self._describe_clusters(cluster_arns)

        return clusters

    def _list_cluster_arns(self) -> list[str]:
        """List all cluster ARNs."""
        cluster_arns = []
        paginator = self.clients.ecs.get_paginator("list_clusters")

        for page in paginator.paginate():
            cluster_arns.extend(page.get("clusterArns", []))

        return cluster_arns

    def _describe_clusters(self, cluster_arns: list[str]) -> list[Cluster]:
        """Describe multiple clusters.

        Args:
            cluster_arns: List of cluster ARNs to describe

        Returns:
            List of Cluster objects with basic info
        """
        if not cluster_arns:
            return []

        # ECS allows up to 100 clusters per describe call
        response = self.clients.ecs.describe_clusters(
            clusters=cluster_arns,
            include=["STATISTICS"],
        )

        clusters = []
        for cluster_data in response.get("clusters", []):
            cluster = Cluster(
                name=cluster_data.get("clusterName", ""),
                arn=cluster_data.get("clusterArn", ""),
                region=self.clients.region,
                status=cluster_data.get("status", "UNKNOWN"),
                services=[],  # We don't fetch services for the list view
                active_services_count=cluster_data.get("activeServicesCount", 0),
                running_tasks_count=cluster_data.get("runningTasksCount", 0),
                pending_tasks_count=cluster_data.get("pendingTasksCount", 0),
                registered_container_instances_count=cluster_data.get(
                    "registeredContainerInstancesCount", 0
                ),
            )
            clusters.append(cluster)

        return clusters

    def fetch_cluster_state(self) -> Cluster:
        """Fetch complete cluster state.

        Returns:
            Cluster object with all services, tasks, and containers
        """
        cluster_name = self.clients.cluster_name
        region = self.clients.region

        logger.info(f"Fetching complete cluster state for: {cluster_name}")

        # Get cluster info
        self._report_progress(f"Describing cluster: {cluster_name}")
        cluster_info = self._describe_cluster(cluster_name)

        # Get all services
        self._report_progress("Listing services...")
        service_arns = self._list_services(cluster_name)
        logger.debug(f"Found {len(service_arns)} service ARNs")
        self._report_progress(
            f"Found {len(service_arns)} services, fetching details..."
        )
        services = self._describe_services_batched(cluster_name, service_arns)

        # Get all tasks for the cluster
        self._report_progress("Listing tasks...")
        task_arns = self._list_tasks(cluster_name)
        logger.debug(f"Found {len(task_arns)} task ARNs")
        self._report_progress(f"Found {len(task_arns)} tasks, fetching details...")
        tasks_by_service = self._describe_tasks_batched(cluster_name, task_arns)

        # Collect service task definition ARNs for image lookup
        service_task_def_arns = set()
        for service_data in services:
            task_def_arn = service_data.get("taskDefinition", "")
            if task_def_arn and self._task_def_cache.get(task_def_arn) is None:
                service_task_def_arns.add(task_def_arn)

        # Fetch any missing task definitions for services
        if service_task_def_arns:
            self._report_progress(
                f"Fetching {len(service_task_def_arns)} service task definitions..."
            )
            for task_def_arn in service_task_def_arns:
                self._describe_task_definition(task_def_arn)

        # Build service objects with tasks
        service_objects = []
        for service_data in services:
            service = self._build_service(service_data)

            # Attach tasks to service
            # Tasks are keyed by group format "service:service-name"
            service_name = service_data.get("serviceName", "")
            service_group_key = f"service:{service_name}"
            service.tasks = tasks_by_service.get(service_group_key, [])

            # Recalculate health now that tasks are attached
            service_objects.append(service)

        # Build cluster object
        cluster = Cluster(
            name=cluster_name,
            arn=cluster_info.get("clusterArn", ""),
            region=region,
            status=cluster_info.get("status", "UNKNOWN"),
            services=service_objects,
            last_updated=datetime.now(timezone.utc),
        )

        return cluster

    def _describe_cluster(self, cluster_name: str) -> dict:
        """Describe the cluster."""
        response = self.clients.ecs.describe_clusters(clusters=[cluster_name])
        clusters = response.get("clusters", [])
        if not clusters:
            return {"status": "NOT_FOUND"}
        return clusters[0]

    def _list_services(self, cluster_name: str) -> list[str]:
        """List all service ARNs in the cluster."""
        service_arns = []
        paginator = self.clients.ecs.get_paginator("list_services")

        for page in paginator.paginate(cluster=cluster_name):
            service_arns.extend(page.get("serviceArns", []))

        return service_arns

    def _describe_services_batched(
        self, cluster_name: str, service_arns: list[str]
    ) -> list[dict]:
        """Describe services in batches of 10."""
        if not service_arns:
            return []

        services = []

        for i in range(0, len(service_arns), self.DESCRIBE_SERVICES_BATCH_SIZE):
            batch = service_arns[i : i + self.DESCRIBE_SERVICES_BATCH_SIZE]
            response = self.clients.ecs.describe_services(
                cluster=cluster_name,
                services=batch,
            )
            services.extend(response.get("services", []))

        return services

    def _list_tasks(self, cluster_name: str) -> list[str]:
        """List all task ARNs in the cluster."""
        task_arns = []
        paginator = self.clients.ecs.get_paginator("list_tasks")

        for page in paginator.paginate(cluster=cluster_name):
            task_arns.extend(page.get("taskArns", []))

        return task_arns

    def _describe_tasks_batched(
        self, cluster_name: str, task_arns: list[str]
    ) -> dict[str, list[Task]]:
        """Describe tasks in batches and group by service ARN.

        Returns:
            Dict mapping service ARN to list of Task objects
        """
        if not task_arns:
            return {}

        tasks_by_service: dict[str, list[Task]] = {}
        task_def_arns_to_fetch: set[str] = set()

        # Fetch task details in batches
        all_task_data = []
        for i in range(0, len(task_arns), self.DESCRIBE_TASKS_BATCH_SIZE):
            batch = task_arns[i : i + self.DESCRIBE_TASKS_BATCH_SIZE]
            response = self.clients.ecs.describe_tasks(
                cluster=cluster_name,
                tasks=batch,
            )
            all_task_data.extend(response.get("tasks", []))

        # Collect task definition ARNs we need to fetch
        for task_data in all_task_data:
            task_def_arn = task_data.get("taskDefinitionArn", "")
            if task_def_arn and self._task_def_cache.get(task_def_arn) is None:
                task_def_arns_to_fetch.add(task_def_arn)

        # Fetch task definitions (cached)
        task_defs = {}
        if task_def_arns_to_fetch:
            self._report_progress(
                f"Fetching {len(task_def_arns_to_fetch)} task definitions..."
            )
        for idx, task_def_arn in enumerate(task_def_arns_to_fetch, 1):
            task_def = self._describe_task_definition(task_def_arn)
            if task_def:
                task_defs[task_def_arn] = task_def

        # Build Task objects
        for task_data in all_task_data:
            task = self._build_task(task_data, task_defs)

            # Group by service ARN (if started by a service)
            group = task_data.get("group", "")
            if group.startswith("service:"):
                # Use the group as key; we'll match services by this later
                service_key = group
            else:
                service_key = "standalone"

            if service_key not in tasks_by_service:
                tasks_by_service[service_key] = []
            tasks_by_service[service_key].append(task)

        return tasks_by_service

    def _describe_task_definition(self, task_def_arn: str) -> dict | None:
        """Describe a task definition with caching."""
        # Check cache first
        cached = self._task_def_cache.get(task_def_arn)
        if cached is not None:
            return cached

        try:
            response = self.clients.ecs.describe_task_definition(
                taskDefinition=task_def_arn
            )
            task_def = response.get("taskDefinition", {})
            self._task_def_cache.set(task_def_arn, task_def)
            return task_def
        except Exception as e:
            logger.warning(f"Failed to describe task definition {task_def_arn}: {e}")
            return None

    def _build_service(self, service_data: dict) -> Service:
        """Build a Service object from API response data."""
        deployments = []
        for dep_data in service_data.get("deployments", []):
            deployment = Deployment(
                id=dep_data.get("id", ""),
                status=dep_data.get("status", ""),
                running_count=dep_data.get("runningCount", 0),
                desired_count=dep_data.get("desiredCount", 0),
                pending_count=dep_data.get("pendingCount", 0),
                task_definition=extract_task_definition_name(
                    dep_data.get("taskDefinition", "")
                ),
                rollout_state=dep_data.get("rolloutState"),
                rollout_state_reason=dep_data.get("rolloutStateReason"),
            )
            deployments.append(deployment)

        # Extract container images from task definition
        images = []
        task_def_arn = service_data.get("taskDefinition", "")
        if task_def_arn:
            task_def = self._task_def_cache.get(task_def_arn)
            if task_def:
                for container_def in task_def.get("containerDefinitions", []):
                    image = container_def.get("image")
                    if image:
                        images.append(image)

        return Service(
            name=service_data.get("serviceName", ""),
            arn=service_data.get("serviceArn", ""),
            status=service_data.get("status", ""),
            desired_count=service_data.get("desiredCount", 0),
            running_count=service_data.get("runningCount", 0),
            pending_count=service_data.get("pendingCount", 0),
            task_definition=extract_task_definition_name(
                service_data.get("taskDefinition", "")
            ),
            deployments=deployments,
            images=images,
        )

    def _build_task(self, task_data: dict, task_defs: dict[str, dict]) -> Task:
        """Build a Task object from API response data."""
        task_def_arn = task_data.get("taskDefinitionArn", "")
        task_def = task_defs.get(task_def_arn) or self._task_def_cache.get(task_def_arn)

        # Build container definitions map for looking up limits
        container_defs = {}
        # Task-level CPU/memory (used by Fargate, optional for EC2)
        task_level_cpu = None
        task_level_memory = None
        if task_def:
            for cdef in task_def.get("containerDefinitions", []):
                container_defs[cdef.get("name", "")] = cdef
            # Task-level resources (in Fargate these are strings like "256" or "0.25 vCPU")
            task_cpu_str = task_def.get("cpu")
            task_mem_str = task_def.get("memory")
            if task_cpu_str:
                try:
                    task_level_cpu = int(task_cpu_str)
                except ValueError:
                    pass
            if task_mem_str:
                try:
                    task_level_memory = int(task_mem_str)
                except ValueError:
                    pass

        # Build containers
        containers = []
        num_containers = len(task_data.get("containers", []))
        for container_data in task_data.get("containers", []):
            container_name = container_data.get("name", "")
            container_def = container_defs.get(container_name, {})

            # Get health status from container
            health_status = HealthStatus.from_ecs_status(
                container_data.get("healthStatus")
            )

            # Get container-level limits, fall back to task-level divided by container count
            # Note: In ECS, cpu=0 means "no limit specified", so treat 0 as None
            cpu_limit = container_def.get("cpu") or None
            memory_limit = (
                container_def.get("memory") or container_def.get("memoryReservation")
            ) or None

            # If no container-level limits, use task-level (divided among containers)
            if cpu_limit is None and task_level_cpu is not None and num_containers > 0:
                cpu_limit = task_level_cpu // num_containers
            if (
                memory_limit is None
                and task_level_memory is not None
                and num_containers > 0
            ):
                memory_limit = task_level_memory // num_containers

            container = Container(
                name=container_name,
                status=container_data.get("lastStatus", "UNKNOWN"),
                health_status=health_status,
                cpu_limit=cpu_limit,
                memory_limit=memory_limit,
                exit_code=container_data.get("exitCode"),
                reason=container_data.get("reason"),
            )
            containers.append(container)

        # Parse timestamps
        started_at = None
        if "startedAt" in task_data:
            started_at = task_data["startedAt"]
            if isinstance(started_at, str):
                started_at = datetime.fromisoformat(started_at.replace("Z", "+00:00"))

        stopped_at = None
        if "stoppedAt" in task_data:
            stopped_at = task_data["stoppedAt"]
            if isinstance(stopped_at, str):
                stopped_at = datetime.fromisoformat(stopped_at.replace("Z", "+00:00"))

        # Get task health from overrides or calculate from containers
        task_health_status = task_data.get("healthStatus")
        if task_health_status:
            health = HealthStatus.from_ecs_status(task_health_status)
        else:
            # Calculate from containers
            health = HealthStatus.UNKNOWN
            if containers:
                healthy = sum(
                    1 for c in containers if c.health_status == HealthStatus.HEALTHY
                )
                unhealthy = sum(
                    1 for c in containers if c.health_status == HealthStatus.UNHEALTHY
                )
                if unhealthy > 0:
                    health = HealthStatus.UNHEALTHY
                elif healthy == len(containers):
                    health = HealthStatus.HEALTHY
                elif healthy > 0:
                    health = HealthStatus.WARNING

        task_arn = task_data.get("taskArn", "")
        task_id = task_arn.split("/")[-1] if "/" in task_arn else task_arn

        return Task(
            id=task_id,
            arn=task_arn,
            status=task_data.get("lastStatus", "UNKNOWN"),
            health_status=health,
            task_definition_arn=task_def_arn,
            started_at=started_at,
            stopped_at=stopped_at,
            stopped_reason=task_data.get("stoppedReason"),
            launch_type=task_data.get("launchType"),
            containers=containers,
        )
