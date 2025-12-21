"""AWS client initialization and configuration."""

import boto3
from botocore.config import Config as BotoConfig

from ecs_monitor.config import ClusterConfig


def create_ecs_client(cluster_config: ClusterConfig):
    """Create a configured ECS client.

    Args:
        cluster_config: Cluster configuration with region and optional profile

    Returns:
        Configured boto3 ECS client
    """
    boto_config = BotoConfig(
        retries={
            "max_attempts": 10,
            "mode": "adaptive",
        },
        max_pool_connections=10,
    )

    session_kwargs = {}
    if cluster_config.profile:
        session_kwargs["profile_name"] = cluster_config.profile

    session = boto3.Session(**session_kwargs)

    return session.client(
        "ecs",
        region_name=cluster_config.region,
        config=boto_config,
    )


def create_cloudwatch_client(cluster_config: ClusterConfig):
    """Create a configured CloudWatch client.

    Args:
        cluster_config: Cluster configuration with region and optional profile

    Returns:
        Configured boto3 CloudWatch client
    """
    boto_config = BotoConfig(
        retries={
            "max_attempts": 10,
            "mode": "adaptive",
        },
        max_pool_connections=10,
    )

    session_kwargs = {}
    if cluster_config.profile:
        session_kwargs["profile_name"] = cluster_config.profile

    session = boto3.Session(**session_kwargs)

    return session.client(
        "cloudwatch",
        region_name=cluster_config.region,
        config=boto_config,
    )


class AWSClients:
    """Container for AWS clients."""

    def __init__(self, cluster_config: ClusterConfig):
        """Initialize AWS clients.

        Args:
            cluster_config: Cluster configuration
        """
        self.ecs = create_ecs_client(cluster_config)
        self.cloudwatch = create_cloudwatch_client(cluster_config)
        self.region = cluster_config.region
        self.cluster_name = cluster_config.name
