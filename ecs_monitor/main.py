"""Main entry point for ECS Monitor."""

import argparse
import logging
import sys
from pathlib import Path

from ecs_monitor.config import ConfigError, get_default_config_path, load_config


def setup_logging(verbose: bool = False, debug: bool = False) -> None:
    """Set up logging configuration.

    Args:
        verbose: If True, enable info logging
        debug: If True, enable debug logging
    """
    if debug:
        level = logging.DEBUG
    elif verbose:
        level = logging.INFO
    else:
        level = logging.WARNING
    logging.basicConfig(
        level=level,
        format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
        stream=sys.stderr,
    )


def parse_args() -> argparse.Namespace:
    """Parse command line arguments.

    Returns:
        Parsed arguments namespace
    """
    parser = argparse.ArgumentParser(
        description="ECS Monitor - Single pane TUI for monitoring AWS ECS cluster health",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  ecs-monitor                    # Use config.toml in current directory
  ecs-monitor -c my-config.toml  # Use specific config file
  ecs-monitor -v                 # Enable verbose logging

Configuration:
  Create a config.toml file with your cluster settings:

  [cluster]
  name = "my-cluster"
  region = "us-east-1"
  profile = "default"  # optional

  [refresh]
  interval = 30  # optional, in seconds
        """,
    )

    parser.add_argument(
        "-c",
        "--config",
        type=str,
        default=None,
        help="Path to configuration file (default: ./config.toml)",
    )

    parser.add_argument(
        "-v",
        "--verbose",
        action="store_true",
        help="Enable verbose logging",
    )

    parser.add_argument(
        "--debug",
        action="store_true",
        help="Run in debug mode (test fetch before starting TUI)",
    )

    return parser.parse_args()


def print_status(message: str) -> None:
    """Print a status message to stderr."""
    print(f"[ecs-monitor] {message}", file=sys.stderr)


def run_debug_fetch(config) -> bool:
    """Run a test fetch to debug connectivity issues.

    Args:
        config: Application configuration

    Returns:
        True if successful, False otherwise
    """
    from ecs_monitor.aws.client import AWSClients
    from ecs_monitor.aws.fetcher import ECSFetcher
    from ecs_monitor.aws.metrics import MetricsFetcher

    print_status(f"Testing connection to cluster: {config.cluster.name}")
    print_status(f"Region: {config.cluster.region}")
    if config.cluster.profile:
        print_status(f"Profile: {config.cluster.profile}")

    try:
        print_status("Creating AWS clients...")
        clients = AWSClients(config.cluster)

        print_status("Creating ECS fetcher...")
        fetcher = ECSFetcher(
            clients,
            task_def_cache_ttl=config.refresh.task_definition_interval,
            progress_callback=print_status,
        )

        print_status("Creating metrics fetcher...")
        metrics_fetcher = MetricsFetcher(clients, progress_callback=print_status)

        print_status("Checking Container Insights...")
        insights_enabled = metrics_fetcher.check_container_insights()
        if insights_enabled:
            print_status("Container Insights: ENABLED")
        else:
            print_status(
                "Container Insights: NOT ENABLED (metrics will be unavailable)"
            )

        print_status("Fetching cluster state...")
        cluster = fetcher.fetch_cluster_state()

        print_status(f"Cluster status: {cluster.status}")
        print_status(f"Services found: {len(cluster.services)}")

        total_tasks = sum(len(s.tasks) for s in cluster.services)
        print_status(f"Tasks found: {total_tasks}")

        if insights_enabled and total_tasks > 0:
            print_status("Fetching container metrics...")
            metrics_fetcher.fetch_metrics_for_cluster(cluster)
            print_status("Metrics fetch complete")

        print_status("DEBUG FETCH COMPLETE - All systems operational")
        print_status("")
        print_status("Summary:")
        for service in cluster.services:
            print_status(
                f"  {service.name}: {service.running_count}/{service.desired_count} tasks"
            )

        return True

    except Exception as e:
        print_status(f"ERROR: {e}")
        logging.exception("Debug fetch failed")
        return False


def main() -> int:
    """Main entry point.

    Returns:
        Exit code (0 for success, non-zero for error)
    """
    args = parse_args()
    setup_logging(args.verbose, args.debug)

    # Determine config path
    if args.config:
        config_path = Path(args.config)
    else:
        config_path = get_default_config_path()

    # Load configuration
    try:
        config = load_config(config_path)
    except ConfigError as e:
        print(f"Configuration error: {e}", file=sys.stderr)
        print(
            f"\nPlease create a configuration file at: {config_path}", file=sys.stderr
        )
        print("\nExample config.toml:", file=sys.stderr)
        print(
            """
[cluster]
name = "your-cluster-name"
region = "us-east-1"

[refresh]
interval = 30
        """,
            file=sys.stderr,
        )
        return 1
    except Exception as e:
        print(f"Failed to load configuration: {e}", file=sys.stderr)
        return 1

    # If debug mode, run a test fetch first
    if args.debug:
        print_status("Running in debug mode...")
        success = run_debug_fetch(config)
        if not success:
            return 1
        print_status("")
        print_status("Starting TUI (press Ctrl+C to exit)...")
        print_status("")

    # Create and run the application
    try:
        # Import here to avoid loading TUI dependencies for --help
        from ecs_monitor.ui.app import ECSMonitorApp

        app = ECSMonitorApp(config)
        app.run()
        return 0
    except KeyboardInterrupt:
        return 0
    except Exception as e:
        logging.exception(f"Application error: {e}")
        print(f"Application error: {e}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
