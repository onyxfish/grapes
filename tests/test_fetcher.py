"""Tests for ECS data fetching."""

import pytest
from datetime import datetime, timezone, timedelta
from unittest.mock import MagicMock

from grapes.aws.fetcher import ECSFetcher, TaskDefinitionCache
from grapes.models import HealthStatus


class TestTaskDefinitionCache:
    """Tests for TaskDefinitionCache."""

    def test_set_and_get(self):
        """Test basic set and get operations."""
        cache = TaskDefinitionCache(ttl_seconds=300)
        cache.set("arn:task-def:1", {"family": "my-task"})

        result = cache.get("arn:task-def:1")
        assert result == {"family": "my-task"}

    def test_get_nonexistent(self):
        """Test getting a key that doesn't exist."""
        cache = TaskDefinitionCache(ttl_seconds=300)
        assert cache.get("nonexistent") is None

    def test_cache_expiration(self):
        """Test that cache entries expire after TTL."""
        cache = TaskDefinitionCache(ttl_seconds=1)
        cache.set("arn:task-def:1", {"family": "my-task"})

        # Entry should be available immediately
        assert cache.get("arn:task-def:1") is not None

        # Manually set old timestamp
        old_time = datetime.now(timezone.utc) - timedelta(seconds=2)
        cache._cache["arn:task-def:1"] = ({"family": "my-task"}, old_time)

        # Entry should be expired
        assert cache.get("arn:task-def:1") is None

    def test_expired_entry_removed(self):
        """Test that expired entries are removed from cache on access."""
        cache = TaskDefinitionCache(ttl_seconds=1)
        cache.set("arn:task-def:1", {"family": "my-task"})

        # Set to expired
        old_time = datetime.now(timezone.utc) - timedelta(seconds=2)
        cache._cache["arn:task-def:1"] = ({"family": "my-task"}, old_time)

        # Access to trigger cleanup
        cache.get("arn:task-def:1")

        # Entry should be removed
        assert "arn:task-def:1" not in cache._cache


class TestECSFetcher:
    """Tests for ECSFetcher class."""

    @pytest.fixture
    def mock_clients(self):
        """Create mock AWS clients."""
        clients = MagicMock()
        clients.region = "us-east-1"
        clients.cluster_name = "test-cluster"
        clients.ecs = MagicMock()
        return clients

    @pytest.fixture
    def fetcher(self, mock_clients):
        """Create an ECSFetcher with mock clients."""
        return ECSFetcher(mock_clients, task_def_cache_ttl=300)

    def test_list_clusters_empty(self, fetcher, mock_clients):
        """Test listing clusters when none exist."""
        paginator = MagicMock()
        paginator.paginate.return_value = [{"clusterArns": []}]
        mock_clients.ecs.get_paginator.return_value = paginator

        result = fetcher.list_clusters()
        assert result == []

    def test_list_clusters_success(self, fetcher, mock_clients):
        """Test listing clusters successfully."""
        # Mock paginator
        paginator = MagicMock()
        paginator.paginate.return_value = [
            {"clusterArns": ["arn:aws:ecs:us-east-1:123:cluster/cluster-1"]}
        ]
        mock_clients.ecs.get_paginator.return_value = paginator

        # Mock describe_clusters
        mock_clients.ecs.describe_clusters.return_value = {
            "clusters": [
                {
                    "clusterName": "cluster-1",
                    "clusterArn": "arn:aws:ecs:us-east-1:123:cluster/cluster-1",
                    "status": "ACTIVE",
                    "activeServicesCount": 2,
                    "runningTasksCount": 5,
                    "pendingTasksCount": 1,
                }
            ]
        }

        result = fetcher.list_clusters()

        assert len(result) == 1
        assert result[0].name == "cluster-1"
        assert result[0].status == "ACTIVE"
        assert result[0].active_services_count == 2
        assert result[0].running_tasks_count == 5

    def test_fetch_cluster_state(self, fetcher, mock_clients):
        """Test fetching full cluster state."""
        # Mock describe_clusters
        mock_clients.ecs.describe_clusters.return_value = {
            "clusters": [
                {
                    "clusterName": "test-cluster",
                    "clusterArn": "arn:aws:ecs:us-east-1:123:cluster/test-cluster",
                    "status": "ACTIVE",
                }
            ]
        }

        # Mock list_services paginator
        services_paginator = MagicMock()
        services_paginator.paginate.return_value = [
            {
                "serviceArns": [
                    "arn:aws:ecs:us-east-1:123:service/test-cluster/my-service"
                ]
            }
        ]

        # Mock list_tasks paginator
        tasks_paginator = MagicMock()
        tasks_paginator.paginate.return_value = [{"taskArns": []}]

        def get_paginator(operation):
            if operation == "list_services":
                return services_paginator
            elif operation == "list_tasks":
                return tasks_paginator
            return MagicMock()

        mock_clients.ecs.get_paginator.side_effect = get_paginator

        # Mock describe_services
        mock_clients.ecs.describe_services.return_value = {
            "services": [
                {
                    "serviceName": "my-service",
                    "serviceArn": "arn:aws:ecs:us-east-1:123:service/test-cluster/my-service",
                    "status": "ACTIVE",
                    "desiredCount": 2,
                    "runningCount": 2,
                    "pendingCount": 0,
                    "taskDefinition": "arn:aws:ecs:us-east-1:123:task-definition/my-task:1",
                    "deployments": [
                        {
                            "id": "dep-1",
                            "status": "PRIMARY",
                            "runningCount": 2,
                            "desiredCount": 2,
                            "pendingCount": 0,
                            "taskDefinition": "arn:aws:ecs:us-east-1:123:task-definition/my-task:1",
                        }
                    ],
                }
            ]
        }

        # Mock describe_task_definition
        mock_clients.ecs.describe_task_definition.return_value = {
            "taskDefinition": {
                "family": "my-task",
                "containerDefinitions": [{"name": "app", "image": "nginx:latest"}],
            }
        }

        result = fetcher.fetch_cluster_state()

        assert result.name == "test-cluster"
        assert result.status == "ACTIVE"
        assert len(result.services) == 1
        assert result.services[0].name == "my-service"
        assert result.services[0].running_count == 2

    def test_build_task_with_containers(self, fetcher, mock_clients):
        """Test building task with container information."""
        task_data = {
            "taskArn": "arn:aws:ecs:us-east-1:123:task/test-cluster/abc123",
            "taskDefinitionArn": "arn:aws:ecs:us-east-1:123:task-definition/my-task:1",
            "lastStatus": "RUNNING",
            "healthStatus": "HEALTHY",
            "startedAt": datetime.now(timezone.utc),
            "group": "service:my-service",
            "containers": [
                {
                    "name": "app",
                    "lastStatus": "RUNNING",
                    "healthStatus": "HEALTHY",
                }
            ],
        }

        task_def = {
            "containerDefinitions": [
                {
                    "name": "app",
                    "cpu": 256,
                    "memory": 512,
                }
            ]
        }

        task = fetcher._build_task(
            task_data, {"arn:aws:ecs:us-east-1:123:task-definition/my-task:1": task_def}
        )

        assert task.id == "abc123"
        assert task.status == "RUNNING"
        assert task.health_status == HealthStatus.HEALTHY
        assert len(task.containers) == 1
        assert task.containers[0].name == "app"
        assert task.containers[0].cpu_limit == 256
        assert task.containers[0].memory_limit == 512

    def test_build_task_without_health(self, fetcher):
        """Test building task when health status is not set."""
        task_data = {
            "taskArn": "arn:aws:ecs:us-east-1:123:task/test-cluster/abc123",
            "taskDefinitionArn": "",
            "lastStatus": "RUNNING",
            "group": "service:my-service",
            "containers": [
                {
                    "name": "app",
                    "lastStatus": "RUNNING",
                    # No health status
                }
            ],
        }

        task = fetcher._build_task(task_data, {})

        assert task.health_status == HealthStatus.UNKNOWN

    def test_build_service(self, fetcher):
        """Test building service from API response."""
        service_data = {
            "serviceName": "web-api",
            "serviceArn": "arn:aws:ecs:us-east-1:123:service/cluster/web-api",
            "status": "ACTIVE",
            "desiredCount": 3,
            "runningCount": 3,
            "pendingCount": 0,
            "taskDefinition": "arn:aws:ecs:us-east-1:123:task-definition/web:5",
            "deployments": [
                {
                    "id": "dep-primary",
                    "status": "PRIMARY",
                    "runningCount": 3,
                    "desiredCount": 3,
                    "pendingCount": 0,
                    "taskDefinition": "arn:aws:ecs:us-east-1:123:task-definition/web:5",
                    "rolloutState": "COMPLETED",
                }
            ],
        }

        service = fetcher._build_service(service_data)

        assert service.name == "web-api"
        assert service.status == "ACTIVE"
        assert service.running_count == 3
        assert len(service.deployments) == 1
        assert service.deployments[0].rollout_state == "COMPLETED"

    def test_progress_callback(self, mock_clients):
        """Test that progress callback is called."""
        progress_messages = []

        def on_progress(msg):
            progress_messages.append(msg)

        fetcher = ECSFetcher(mock_clients, progress_callback=on_progress)

        # Mock empty response
        paginator = MagicMock()
        paginator.paginate.return_value = [{"clusterArns": []}]
        mock_clients.ecs.get_paginator.return_value = paginator

        fetcher.list_clusters()

        assert len(progress_messages) > 0
        assert "Listing clusters" in progress_messages[0]

    def test_describe_services_batching(self, fetcher, mock_clients):
        """Test that services are described in batches of 10."""
        # Create 15 service ARNs
        service_arns = [f"arn:service/{i}" for i in range(15)]

        mock_clients.ecs.describe_services.return_value = {"services": []}

        fetcher._describe_services_batched("test-cluster", service_arns)

        # Should be called twice (10 + 5)
        assert mock_clients.ecs.describe_services.call_count == 2
