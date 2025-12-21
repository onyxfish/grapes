# ECS Cluster Monitoring TUI - Implementation Plan

A single-pane TUI for viewing the status of an ECS cluster, written in Python using Textual.

## Project Overview

- **Name**: ecs-monitor
- **Description**: Single pane TUI for monitoring AWS ECS cluster health
- **Stack**: Python 3.11+, Textual, boto3, uv
- **Config**: TOML format
- **Theme**: Dark mode only

## Implementation Progress

### Phase 1: Foundation

- [x] **1.1** Initialize project with uv and create directory structure
  ```
  ecs-monitor/
  ├── pyproject.toml
  ├── config.toml
  ├── ecs_monitor/
  │   ├── __init__.py
  │   ├── main.py
  │   ├── config.py
  │   ├── aws/
  │   │   ├── __init__.py
  │   │   ├── client.py
  │   │   ├── fetcher.py
  │   │   └── metrics.py
  │   ├── models/
  │   │   ├── __init__.py
  │   │   ├── cluster.py
  │   │   ├── service.py
  │   │   ├── task.py
  │   │   └── health.py
  │   ├── ui/
  │   │   ├── __init__.py
  │   │   ├── app.py
  │   │   ├── cluster_view.py
  │   │   ├── service_view.py
  │   │   ├── task_view.py
  │   │   ├── console_link.py
  │   │   └── styles.css
  │   └── utils/
  │       ├── __init__.py
  │       └── ids.py
  └── README.md
  ```

- [x] **1.2** Create pyproject.toml with dependencies
  - textual>=0.47.0
  - boto3>=1.34.0
  - rich>=13.7.0
  - pyperclip>=1.8.2

- [x] **1.3** Create sample config.toml
  ```toml
  [cluster]
  name = "my-ecs-cluster"
  region = "us-east-1"
  profile = "default"

  [refresh]
  interval = 30
  task_definition_interval = 300
  ```

- [x] **1.4** Implement configuration module (config.py)
  - Load TOML using tomllib (Python 3.11+)
  - Schema validation for required fields
  - Default values for optional fields
  - Config dataclass

- [x] **1.5** Implement data models (models/)
  - `HealthStatus` enum: HEALTHY, UNHEALTHY, WARNING, UNKNOWN
  - `Cluster`: name, region, status, services, insights_enabled
  - `Service`: name, status, desired_count, running_count, task_definition, deployments, tasks
  - `Deployment`: status, running_count, desired_count, task_definition
  - `Task`: id, short_id, full_arn, status, health_status, started_at, task_definition_arn, containers
  - `Container`: name, status, health_status, cpu_limit, memory_limit, cpu_used, memory_used

### Phase 2: AWS Integration

- [x] **2.1** Implement AWS client module (aws/client.py)
  - Initialize boto3 ECS client with region/profile
  - Initialize boto3 CloudWatch client
  - Configure adaptive retry strategy (max 10 attempts)
  - Configure connection pooling (max_pool_connections=10)

- [x] **2.2** Implement ECS fetcher module (aws/fetcher.py)
  - `fetch_cluster_state()`: Main orchestrator
  - `list_services()`: Get service ARNs
  - `describe_services_batched()`: Batch fetch (chunks of 10)
  - `list_all_tasks()`: Get all task ARNs for cluster
  - `describe_tasks_batched()`: Batch fetch (chunks of 100)
  - `describe_task_definition()`: Fetch with caching (TTL from config)
  - Parse responses into data models
  - Handle pagination

- [x] **2.3** Implement CloudWatch metrics module (aws/metrics.py)
  - `check_container_insights()`: Verify if enabled on cluster
  - `fetch_container_metrics()`: Batch fetch CPU/Memory for all containers
  - Build batched GetMetricData queries (up to 500 metrics)
  - Parse responses and attach to container models
  - Return None for missing/stale metrics (display as '-')

- [x] **2.4** Implement utilities (utils/ids.py)
  - `shorten_task_id()`: Extract 6-char short ID from ARN
  - `parse_task_arn()`: Extract components for URL building

### Phase 3: UI Foundation

- [x] **3.1** Implement Textual app skeleton (ui/app.py)
  - Main `App` class extending `textual.app.App`
  - Reactive state: `cluster_state = reactive(None)`
  - Background refresh worker with `set_interval()`
  - Loading screen for initial fetch
  - Global key bindings: Q=quit, R=refresh

- [x] **3.2** Implement cluster header widget (ui/cluster_view.py)
  - Display cluster name, region, status
  - Last update timestamp
  - Service health summary (X/Y healthy)
  - Container Insights warning banner (if disabled)

- [x] **3.3** Implement console URL module (ui/console_link.py)
  - `build_cluster_url(cluster, region)`
  - `build_service_url(cluster, service, region)`
  - `build_task_url(cluster, task_arn, region)`
  - `build_container_url(cluster, task_arn, region)`
  - Clipboard copy function with pyperclip

### Phase 4: Interactive UI

- [x] **4.1** Implement service list widget (ui/service_view.py)
  - DataTable with fixed-width columns
  - Columns: Name, Status, Tasks (X/Y), Health, Deployment
  - Color coding by health status
  - Selection handling
  - Enter to expand/drill down
  - C key to copy console URL

- [x] **4.2** Implement unified task+container widget (ui/task_view.py)
  - Hierarchical display (tasks with containers nested)
  - Task columns: Short ID, Status, Health, Started
  - Container columns: Name, CPU (usage/limit), Memory (usage/limit), Health
  - Show ALL deployment details
  - Show '-' for missing metrics
  - C key context-aware (task vs container URL)
  - Esc to go back

- [x] **4.3** Create dark mode styles (ui/styles.css)
  - Dark background theme
  - Health status colors:
    - Green: Healthy (✓)
    - Yellow: Warning (⚠)
    - Red: Unhealthy (✗)
    - Gray: Unknown (?)
  - Fixed-width column styling
  - Borders, spacing, headers
  - Loading screen styles

### Phase 5: Polish

- [x] **5.1** Implement main entry point (main.py)
  - Argument parsing: --config flag (default: ./config.toml)
  - Load and validate config
  - Initialize AWS clients
  - Check Container Insights status
  - Run Textual app
  - Graceful shutdown on Ctrl+C

- [x] **5.2** Add error handling and edge cases
  - Network errors: Show in status bar, retry
  - Throttling: Exponential backoff, increase interval
  - No services: Show "No services found"
  - No tasks: Show "No tasks running"
  - Container Insights disabled: Warning banner, hide metrics
  - Invalid config: Fail fast with clear message
  - Missing IAM permissions: Show specific error

- [x] **5.3** Create README.md with setup instructions
  - Installation with uv
  - Configuration example
  - Required IAM permissions
  - Enabling Container Insights
  - Usage instructions
  - Keyboard shortcuts reference

### Phase 6: Testing

- [ ] **6.1** Test with real ECS cluster
- [ ] **6.2** Test with Container Insights enabled/disabled
- [ ] **6.3** Test various cluster sizes
- [ ] **6.4** Test error scenarios (network, throttling)
- [ ] **6.5** Test console URL generation and clipboard
- [ ] **6.6** Validate API call volume and rate limits

## Configuration Schema

```toml
[cluster]
name = "my-ecs-cluster"      # Required: ECS cluster name
region = "us-east-1"         # Required: AWS region
profile = "default"          # Optional: AWS profile name

[refresh]
interval = 30                # Optional: API poll interval in seconds (default: 30)
task_definition_interval = 300  # Optional: Task def cache TTL in seconds (default: 300)
```

## Required IAM Permissions

```json
{
  "Version": "2012-10-17",
  "Statement": [
    {
      "Effect": "Allow",
      "Action": [
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

## Keyboard Shortcuts

| Key | Action |
|-----|--------|
| ↓/↑ | Navigate list |
| Enter | Expand/drill down |
| Esc | Go back |
| C | Copy AWS Console URL to clipboard |
| R | Force refresh |
| Q | Quit |

## API Call Budget

For 5 services, 25 tasks, 50 containers:
- ListServices: 1 call
- DescribeServices: 1 call (batch 10)
- ListTasks: 1 call
- DescribeTasks: 1 call (batch 100)
- DescribeTaskDefinition: ~5 calls (cached)
- GetMetricData: 1 call (100 metrics batched)

**Average: ~10 API calls/minute** (well within rate limits)

## Notes

- Container health: Use ECS healthStatus only (no fallback)
- Metrics: Always show '-' when unavailable (never stale data)
- Task IDs: Display first 6 characters
- Deployments: Show ALL (PRIMARY, ACTIVE, etc.)
- Theme: Dark mode only
