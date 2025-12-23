"""AWS Console URL generation and clipboard functionality."""

import logging
import webbrowser

try:
    import pyperclip

    PYPERCLIP_AVAILABLE = True
except ImportError:
    PYPERCLIP_AVAILABLE = False

logger = logging.getLogger(__name__)


def build_cluster_url(cluster_name: str, region: str) -> str:
    """Build AWS Console URL for a cluster.

    Args:
        cluster_name: ECS cluster name
        region: AWS region

    Returns:
        AWS Console URL for the cluster
    """
    return (
        f"https://console.aws.amazon.com/ecs/v2/clusters/{cluster_name}?region={region}"
    )


def build_service_url(cluster_name: str, service_name: str, region: str) -> str:
    """Build AWS Console URL for a service.

    Args:
        cluster_name: ECS cluster name
        service_name: ECS service name
        region: AWS region

    Returns:
        AWS Console URL for the service
    """
    return f"https://console.aws.amazon.com/ecs/v2/clusters/{cluster_name}/services/{service_name}?region={region}"


def build_task_url(cluster_name: str, task_id: str, region: str) -> str:
    """Build AWS Console URL for a task.

    Args:
        cluster_name: ECS cluster name
        task_id: Full task ID (not ARN)
        region: AWS region

    Returns:
        AWS Console URL for the task
    """
    return f"https://console.aws.amazon.com/ecs/v2/clusters/{cluster_name}/tasks/{task_id}?region={region}"


def build_container_url(cluster_name: str, task_id: str, region: str) -> str:
    """Build AWS Console URL for a container (task page with containers section).

    Args:
        cluster_name: ECS cluster name
        task_id: Full task ID (not ARN)
        region: AWS region

    Returns:
        AWS Console URL for the container section of a task
    """
    return f"https://console.aws.amazon.com/ecs/v2/clusters/{cluster_name}/tasks/{task_id}?region={region}#containers"


def copy_to_clipboard(text: str) -> bool:
    """Copy text to system clipboard.

    Args:
        text: Text to copy

    Returns:
        True if successful, False otherwise
    """
    if not PYPERCLIP_AVAILABLE:
        logger.warning("pyperclip not available, clipboard copy not supported")
        return False

    try:
        pyperclip.copy(text)  # type: ignore[possibly-undefined]
        return True
    except Exception as e:
        logger.warning(f"Failed to copy to clipboard: {e}")
        return False


def open_in_browser(url: str) -> bool:
    """Open URL in the default web browser.

    Args:
        url: URL to open

    Returns:
        True if successful, False otherwise
    """
    try:
        webbrowser.open(url)
        return True
    except Exception as e:
        logger.warning(f"Failed to open browser: {e}")
        return False
