"""Utility functions for handling ECS resource IDs and ARNs."""

import re


def shorten_task_id(full_arn_or_id: str) -> str:
    """Extract short ID from task ARN or ID.

    Args:
        full_arn_or_id: Full task ARN or task ID

    Returns:
        First 6 characters of the task ID

    Examples:
        >>> shorten_task_id("arn:aws:ecs:us-east-1:123456789:task/cluster/abc123def456")
        'abc123'
        >>> shorten_task_id("abc123def456ghi789")
        'abc123'
    """
    # Extract just the ID part if it's an ARN
    if "/" in full_arn_or_id:
        task_id = full_arn_or_id.split("/")[-1]
    else:
        task_id = full_arn_or_id

    return task_id[:6]


def extract_task_id_from_arn(task_arn: str) -> str:
    """Extract the full task ID from a task ARN.

    Args:
        task_arn: Full task ARN

    Returns:
        Full task ID (without cluster prefix)

    Example:
        >>> extract_task_id_from_arn("arn:aws:ecs:us-east-1:123456789:task/cluster/abc123def456")
        'abc123def456'
    """
    if "/" in task_arn:
        return task_arn.split("/")[-1]
    return task_arn


def extract_cluster_from_arn(arn: str) -> str:
    """Extract cluster name from an ECS ARN.

    Args:
        arn: Any ECS ARN (cluster, service, task)

    Returns:
        Cluster name

    Examples:
        >>> extract_cluster_from_arn("arn:aws:ecs:us-east-1:123456789:cluster/my-cluster")
        'my-cluster'
        >>> extract_cluster_from_arn("arn:aws:ecs:us-east-1:123456789:service/my-cluster/my-service")
        'my-cluster'
    """
    # Handle cluster ARN
    if ":cluster/" in arn:
        return arn.split("/")[-1]

    # Handle service or task ARN (format: .../cluster-name/resource-name)
    parts = arn.split("/")
    if len(parts) >= 2:
        return parts[-2]

    return arn


def extract_task_definition_name(task_def_arn: str) -> str:
    """Extract task definition name:revision from ARN.

    Args:
        task_def_arn: Full task definition ARN

    Returns:
        Task definition name:revision

    Example:
        >>> extract_task_definition_name("arn:aws:ecs:us-east-1:123:task-definition/my-task:5")
        'my-task:5'
    """
    if "/" in task_def_arn:
        return task_def_arn.split("/")[-1]
    return task_def_arn


def extract_task_definition_version(task_def_arn: str) -> str:
    """Extract just the revision number from task definition ARN.

    Args:
        task_def_arn: Full task definition ARN or name:revision

    Returns:
        Revision number prefixed with colon (e.g., ':5')

    Example:
        >>> extract_task_definition_version("arn:aws:ecs:us-east-1:123:task-definition/my-task:5")
        ':5'
    """
    name = extract_task_definition_name(task_def_arn)
    if ":" in name:
        return ":" + name.split(":")[-1]
    return name


def sanitize_metric_id(s: str) -> str:
    """Sanitize a string for use as a CloudWatch metric ID.

    CloudWatch metric IDs must:
    - Start with a lowercase letter
    - Contain only lowercase letters, numbers, and underscores

    Args:
        s: String to sanitize

    Returns:
        Sanitized string suitable for use as a metric ID
    """
    # Replace non-alphanumeric characters with underscores
    sanitized = re.sub(r"[^a-zA-Z0-9]", "_", s)
    # Convert to lowercase
    sanitized = sanitized.lower()
    # Ensure it starts with a letter
    if sanitized and not sanitized[0].isalpha():
        sanitized = "m_" + sanitized
    return sanitized
