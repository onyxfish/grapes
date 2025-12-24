# AGENTS.md

Guidelines for AI coding agents working on this project.

## Project Overview

Grapes is a TUI application for monitoring AWS ECS clusters. See `README.md` for features, installation, and usage.

## Architecture

```
grapes/
├── aws/           # AWS integration layer
│   ├── client.py  # boto3 client initialization with connection pooling
│   ├── fetcher.py # ECS data fetching with batching and caching
│   └── metrics.py # CloudWatch metrics fetching
├── models/        # Data models (dataclasses)
│   ├── cluster.py # Cluster model
│   ├── service.py # Service and Deployment models
│   ├── task.py    # Task and Container models
│   └── health.py  # HealthStatus enum
├── ui/            # Textual TUI components
│   ├── app.py     # Main application and state management
│   ├── tree_view.py     # Unified hierarchical view (clusters > services > tasks)
│   ├── metrics_panel.py # CPU/memory usage charts for tasks/containers
│   ├── cluster_view.py  # Loading screen and cluster header
│   ├── console_link.py  # AWS Console URL generation
│   ├── debug_console.py
│   └── styles.css
├── utils/
│   └── ids.py     # ARN parsing utilities
├── config.py      # TOML configuration loading
└── main.py        # Entry point
```

## Key Patterns

### Data Flow

1. `ECSFetcher` (aws/fetcher.py) fetches data from AWS APIs
2. Data is converted to model dataclasses (models/)
3. UI widgets (ui/) consume models via Textual's reactive system
4. Background fetching uses Textual workers to avoid blocking the UI

### Threading Model

- AWS API calls are synchronous (boto3) but run in Textual workers
- Workers are spawned via `self.run_worker()` in the App class
- Progress callbacks report status back to the UI thread

### Caching

- Task definitions are cached with configurable TTL (default 300s)
- Cache key is the full task definition ARN
- See `ECSFetcher._get_task_definition_cached()`

### Health Calculation

Health is aggregated bottom-up:
- Container health comes from ECS health checks (no fallbacks)
- Task health is worst of its containers
- Service health is worst of its tasks
- Cluster health is worst of its services

See `HealthStatus` enum in `models/health.py` for ordering.

### UI State Management

- Main app state: `AppView` enum (LOADING, MAIN)
- Single-panel unified tree layout showing clusters > services > tasks
- `TreeView` widget manages hierarchical display with fold/unfold
- Reactive properties trigger UI updates automatically
- `_columns_ready` flag prevents table operations before mount
- `_row_map` tracks row types for navigation

### Tree View Navigation

- Enter key: Toggle fold/unfold on clusters and services, or load cluster data
- Tab key: Jump to next sibling of same type (cluster-to-cluster, service-to-service)
- Shift+Tab: Jump to previous sibling of same type
- Up/Down: Standard row navigation
- V key: Show/hide metrics panel with CPU/memory charts for selected service/task/container

## Development Commands

```bash
uv run grapes             # Run the application
uv run pytest             # Run tests
uv run ruff check .       # Lint code
uv run ruff format .      # Format code
```

## Testing

Tests are in `tests/` using pytest and pytest-asyncio:

- `test_models.py` - Model unit tests
- `test_app.py` - App integration tests
- `test_ui.py` - Widget tests including race condition scenarios

Run tests with: `uv run pytest`

For widget tests, use Textual's `run_test()` pattern:
```python
async with app.run_test() as pilot:
    await pilot.pause()
    # assertions here
```

## Code Style

- Type hints are required on all function signatures
- Use dataclasses for models with `@dataclass` decorator
- Each module should have its own logger: `logger = logging.getLogger(__name__)`
- Docstrings on all public functions
- Follow existing patterns for error handling (graceful degradation)

## AWS API Considerations

- Batch sizes: 10 services/batch, 100 tasks/batch
- CloudWatch metrics: up to 500 per GetMetricData call
- Retry strategy: exponential backoff, max 10 attempts
- Connection pooling: 10 connections per client

## Common Tasks

### Adding a New Model Field

1. Add field to dataclass in `models/`
2. Update `from_aws_response()` class method to parse new field
3. Update relevant UI widget to display the field
4. Add tests in `test_models.py`

### Adding a New UI View

1. Create widget class in `ui/` extending `Static` or `Container`
2. Add compose method returning widget tree
3. Register in app.py's `compose()` or state transition logic
4. Add corresponding `AppView` if needed
5. Add tests in `test_ui.py`

### Adding a New Configuration Option

1. Add field to `Config` dataclass in `config.py`
2. Update `_load_toml()` to parse new field
3. Add validation if needed
4. Document in README.md

## Known Limitations

- No filtering or search functionality
- boto3 is synchronous (runs in workers, not true async)
