# Grapes

> **Warning**
> This project is an experiment in AI-assisted development. The code was generated without human review and should not be trusted for production use. That said, Grapes is read-only and makes no modifications to your AWS resources, so there's no harm in trying it!

A single-pane TUI (Text User Interface) for monitoring AWS ECS cluster health. Built with Python and Textual.

## Features

- **Cluster Selection**: View all accessible ECS clusters and select one to monitor
- **Real-time Monitoring**: View cluster, service, task, and container status at a glance
- **Health Indicators**: Visual health status (✓ Healthy, ⚠ Warning, ✗ Unhealthy, ? Unknown)
- **Container Metrics**: CPU and memory utilization from CloudWatch Container Insights
- **Deployment Tracking**: See all deployments (PRIMARY, ACTIVE, etc.) with task definition versions
- **AWS Console Integration**: One-key access to open resources in AWS Console
- **Keyboard Navigation**: Fast, keyboard-driven interface
- **Dark Mode**: Easy on the eyes for extended monitoring sessions

## Requirements

- Python 3.11+
- AWS credentials configured (via environment, ~/.aws/credentials, or IAM role)
- CloudWatch Container Insights enabled (optional, for CPU/memory metrics)

## Installation

Install from PyPI:

```bash
pip install grapes-ecs
```

Or using [uv](https://github.com/astral-sh/uv):

```bash
uv tool install grapes-ecs
```

Then run:

```bash
grapes
```

### Development Installation

```bash
# Clone the repository
git clone <repository-url>
cd grapes

# Install dependencies
uv sync

# Run the application
uv run grapes
```

## Configuration

Create a `config.toml` file in your current directory or at `~/.config/grapes/config.toml`:

```toml
[cluster]
name = "my-ecs-cluster"      # Optional: ECS cluster name (if omitted, select from list)
region = "us-east-1"         # Required: AWS region
profile = "default"          # Optional: AWS profile name

[refresh]
interval = 30                # Optional: API poll interval in seconds (default: 30)
task_definition_interval = 300  # Optional: Task def cache TTL in seconds (default: 300)
```

If you omit the `name` field, Grapes will show a list of all clusters in the region, and you can select one to view.

Run with a specific config file:

```bash
grapes -c /path/to/config.toml
```

## Keyboard Shortcuts

| Key | Action |
|-----|--------|
| ↓/↑ | Navigate list |
| Enter | Select cluster / View service details |
| Esc | Go back (cluster list / service list) |
| O | Open in AWS Console |
| R | Force refresh data |
| D | Toggle debug console |
| Q | Quit |

## Required IAM Permissions

The following IAM permissions are required:

```json
{
  "Version": "2012-10-17",
  "Statement": [
    {
      "Effect": "Allow",
      "Action": [
        "ecs:ListClusters",
        "ecs:DescribeClusters",
        "ecs:ListServices",
        "ecs:DescribeServices",
        "ecs:ListTasks",
        "ecs:DescribeTasks",
        "ecs:DescribeTaskDefinition"
      ],
      "Resource": "*"
    },
    {
      "Effect": "Allow",
      "Action": [
        "cloudwatch:GetMetricData",
        "cloudwatch:GetMetricStatistics"
      ],
      "Resource": "*"
    }
  ]
}
```

## Enabling Container Insights

For CPU and memory metrics, enable Container Insights on your cluster:

```bash
aws ecs update-cluster-settings \
  --cluster my-cluster \
  --settings name=containerInsights,value=enabled \
  --region us-east-1
```

If Container Insights is not enabled, Grapes will display a warning and show `-` for metrics.

## Health Status

Grapes determines health based on ECS container health checks:

- **✓ Healthy**: All containers report healthy
- **⚠ Warning**: Some containers unhealthy or desired != running count
- **✗ Unhealthy**: All containers unhealthy or no running tasks
- **? Unknown**: Health checks not configured

No fallback logic is used - only actual container health check results are displayed.

## Metrics Display

When Container Insights is enabled:
- **CPU**: Displayed as `usage% / limit_units` (e.g., `12% / 512`)
- **Memory**: Displayed as `usedM / limitM` (e.g., `256M / 1024M`)

Metrics are fetched from CloudWatch and may have 1-2 minutes of lag. Missing or stale metrics are always shown as `-`.

## Development

```bash
# Install dev dependencies
uv sync

# Run linting
uv run ruff check .

# Run tests
uv run pytest
```

## License

MIT
