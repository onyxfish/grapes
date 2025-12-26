"""Utility functions for handling ECS resource IDs and ARNs."""

import re


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
