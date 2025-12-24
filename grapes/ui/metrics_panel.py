"""Metrics panel widget for displaying CPU and memory charts."""

import logging
import math
from datetime import datetime

from textual.app import ComposeResult
from textual.containers import Horizontal
from textual.reactive import reactive
from textual.widgets import Static

from grapes.models import Service, Task, Container

logger = logging.getLogger(__name__)


class MetricsPanel(Static):
    """Panel displaying CPU and memory usage charts for services/tasks/containers."""

    # Reactive properties for the data
    selected_service: reactive[Service | None] = reactive(None)
    selected_task: reactive[Task | None] = reactive(None)
    selected_container: reactive[Container | None] = reactive(None)
    cpu_history: reactive[list[float]] = reactive(list, always_update=True)
    memory_history: reactive[list[float]] = reactive(list, always_update=True)
    timestamps: reactive[list[datetime]] = reactive(list, always_update=True)
    cpu_stats: reactive[tuple[float, float, float]] = reactive(
        (0, 0, 0), always_update=True
    )
    mem_stats: reactive[tuple[float, float, float]] = reactive(
        (0, 0, 0), always_update=True
    )

    def __init__(self, *args, **kwargs) -> None:
        """Initialize the metrics panel."""
        super().__init__(*args, **kwargs)
        self._mounted = False

    def compose(self) -> ComposeResult:
        """Compose the metrics panel layout."""
        yield Static("", id="metrics-title")
        yield Horizontal(
            Static(
                "",
                id="cpu-chart-container",
                classes="chart-container",
            ),
            Static(
                "",
                id="mem-chart-container",
                classes="chart-container",
            ),
            id="charts-row",
        )
        yield Static("", id="metrics-status")

    def on_mount(self) -> None:
        """Set up the panel when mounted."""
        self._mounted = True
        self._update_display()

    def watch_selected_service(self, service: Service | None) -> None:
        """Update display when service changes."""
        self._update_display()

    def watch_selected_task(self, task: Task | None) -> None:
        """Update display when task changes."""
        self._update_display()

    def watch_selected_container(self, container: Container | None) -> None:
        """Update display when container changes."""
        self._update_display()

    def watch_cpu_history(self, history: list[float]) -> None:
        """Update CPU chart when history changes."""
        self._update_charts()

    def watch_memory_history(self, history: list[float]) -> None:
        """Update memory chart when history changes."""
        self._update_charts()

    def watch_cpu_stats(self, stats: tuple[float, float, float]) -> None:
        """Update CPU chart when stats change."""
        self._update_charts()

    def watch_mem_stats(self, stats: tuple[float, float, float]) -> None:
        """Update memory chart when stats change."""
        self._update_charts()

    def set_service_metrics_data(
        self,
        service: Service,
        cpu_history: list[float],
        memory_history: list[float],
        timestamps: list[datetime],
        cpu_stats: tuple[float, float, float],
        mem_stats: tuple[float, float, float],
    ) -> None:
        """Set metrics data for a service.

        Args:
            service: The service being displayed
            cpu_history: List of CPU usage values (percentages)
            memory_history: List of memory usage values (percentages)
            timestamps: List of timestamps for the data points
            cpu_stats: Tuple of (min, max, avg) CPU statistics from CloudWatch
            mem_stats: Tuple of (min, max, avg) memory statistics from CloudWatch
        """
        self.selected_service = service
        self.selected_task = None
        self.selected_container = None
        self.cpu_history = cpu_history
        self.memory_history = memory_history
        self.timestamps = timestamps
        self.cpu_stats = cpu_stats
        self.mem_stats = mem_stats
        self._update_display()
        self._update_charts()

    def set_task_metrics_data(
        self,
        task: Task,
        container: Container | None,
        cpu_history: list[float],
        memory_history: list[float],
        timestamps: list[datetime],
        cpu_stats: tuple[float, float, float],
        mem_stats: tuple[float, float, float],
    ) -> None:
        """Set metrics data for a task/container.

        Args:
            task: The task being displayed
            container: The container (if specific container selected)
            cpu_history: List of CPU usage values (percentages)
            memory_history: List of memory usage values (MiB)
            timestamps: List of timestamps for the data points
            cpu_stats: Tuple of (min, max, avg) CPU statistics from CloudWatch
            mem_stats: Tuple of (min, max, avg) memory statistics from CloudWatch
        """
        self.selected_service = None
        self.selected_task = task
        self.selected_container = container
        self.cpu_history = cpu_history
        self.memory_history = memory_history
        self.timestamps = timestamps
        self.cpu_stats = cpu_stats
        self.mem_stats = mem_stats
        self._update_display()
        self._update_charts()

    def clear_data(self) -> None:
        """Clear all metrics data."""
        self.selected_service = None
        self.selected_task = None
        self.selected_container = None
        self.cpu_history = []
        self.memory_history = []
        self.timestamps = []
        self._update_display()

    def _update_display(self) -> None:
        """Update the title and status display."""
        if not self._mounted:
            return

        try:
            title = self.query_one("#metrics-title", Static)
            status = self.query_one("#metrics-status", Static)
        except Exception:
            return

        # Determine what we're displaying
        if self.selected_service is not None:
            title_text = f"[bold]Metrics[/bold] - Service: {self.selected_service.name}"
        elif self.selected_task is not None:
            if self.selected_container is not None:
                title_text = (
                    f"[bold]Metrics[/bold] - Task {self.selected_task.short_id} / "
                    f"{self.selected_container.name}"
                )
            else:
                title_text = (
                    f"[bold]Metrics[/bold] - Task {self.selected_task.short_id}"
                )
        else:
            title.update("[bold]Metrics[/bold] - No item selected")
            status.update(
                "Press [bold]v[/bold] on a service, task, or container to view metrics"
            )
            return

        title.update(title_text)

        # Build status line
        if self.cpu_history and self.timestamps:
            time_range = ""
            if len(self.timestamps) >= 2:
                start = self.timestamps[0].strftime("%H:%M")
                end = self.timestamps[-1].strftime("%H:%M")
                time_range = f" ({start} - {end})"

            points = len(self.cpu_history)
            status.update(f"{points} data points{time_range}")
        else:
            status.update("Loading metrics...")

    def _update_charts(self) -> None:
        """Update the sparkline charts."""
        if not self._mounted:
            return

        try:
            cpu_container = self.query_one("#cpu-chart-container", Static)
            mem_container = self.query_one("#mem-chart-container", Static)
        except Exception:
            return

        # Calculate available dimensions for charts
        # Account for title line (2 lines), x-axis (1 line), and spacing (1 line)
        container_height = cpu_container.region.height
        container_width = cpu_container.region.width
        chart_height = max(2, container_height - 4)
        chart_width = max(20, container_width - 8)  # Reserve space for y-axis labels

        # Determine if we're showing service metrics (percentages) or container metrics (MiB for mem)
        is_service = self.selected_service is not None

        # Update CPU chart (always percentage, auto-scale for better visibility)
        if self.cpu_history:
            cpu_min, cpu_max, cpu_avg = self.cpu_stats

            cpu_text = f"[bold cyan]CPU[/bold cyan] [dim]Min: {cpu_min:.1f}% / Avg: {cpu_avg:.1f}% / Max: {cpu_max:.1f}%[/dim]\n\n"
            cpu_bar = self._render_ascii_chart(
                self.cpu_history,
                timestamps=self.timestamps if self.timestamps else None,
                unit="%",
                width=chart_width,
                height=chart_height,
            )
            cpu_container.update(cpu_text + cpu_bar)
        else:
            cpu_container.update("[bold cyan]CPU[/bold cyan]\n[dim]No data[/dim]")

        # Update Memory chart
        if self.memory_history:
            mem_min, mem_max, mem_avg = self.mem_stats

            if is_service:
                # Service memory is percentage, auto-scale for better visibility
                mem_text = f"[bold green]Memory[/bold green] [dim]Min: {mem_min:.1f}% / Avg: {mem_avg:.1f}% / Max: {mem_max:.1f}%[/dim]\n\n"
                mem_bar = self._render_ascii_chart(
                    self.memory_history,
                    timestamps=self.timestamps if self.timestamps else None,
                    unit="%",
                    width=chart_width,
                    height=chart_height,
                )
            else:
                # Container memory is MiB
                limit_str = ""
                chart_max = None
                if self.selected_container and self.selected_container.memory_limit:
                    limit_str = f" / {self.selected_container.memory_limit}M"
                    chart_max = float(self.selected_container.memory_limit)

                mem_text = f"[bold green]Memory[/bold green] [dim]Min: {mem_min:.0f}M / Avg: {mem_avg:.0f}M / Max: {mem_max:.0f}M{limit_str}[/dim]\n\n"
                mem_bar = self._render_ascii_chart(
                    self.memory_history,
                    timestamps=self.timestamps if self.timestamps else None,
                    unit="M",
                    max_val=chart_max,
                    width=chart_width,
                    height=chart_height,
                )

            mem_container.update(mem_text + mem_bar)
        else:
            mem_container.update("[bold green]Memory[/bold green]\n[dim]No data[/dim]")

    def _format_time_ago(self, ts: datetime) -> str:
        """Format a timestamp as 'Xm ago' style.

        Args:
            ts: The timestamp to format

        Returns:
            Formatted string like '5m ago' or 'now'
        """
        now = datetime.now(ts.tzinfo)
        delta = now - ts
        seconds = int(delta.total_seconds())

        if seconds < 60:
            return "now"
        elif seconds < 3600:
            minutes = seconds // 60
            return f"{minutes}m"
        else:
            hours = seconds // 3600
            return f"{hours}h"

    def _render_ascii_chart(
        self,
        values: list[float],
        timestamps: list[datetime] | None = None,
        unit: str = "%",
        width: int = 40,
        height: int = 4,
        max_val: float | None = None,
    ) -> str:
        """Render an ASCII sparkline chart with axis labels.

        Args:
            values: List of values to chart
            timestamps: List of timestamps for x-axis labels
            unit: Unit string for y-axis labels (e.g., '%' or 'M')
            width: Width of the chart in characters (excluding y-axis)
            height: Height of the chart in rows
            max_val: Maximum value for scaling (auto if None)

        Returns:
            ASCII chart string with axis labels
        """
        if not values:
            return "[dim]No data[/dim]"

        # Determine scale
        data_min = min(values)
        data_max = max(values)
        if max_val is None:
            max_val = data_max
        # Round up max value to next whole number
        max_val = math.ceil(max_val)
        # Force y-axis to start at 0 for memory (utilization can't be negative)
        if unit == "M":
            min_val = 0
        else:
            min_val = min(0, data_min)

        if max_val == min_val:
            max_val = min_val + 1  # Avoid division by zero

        mid_val = (max_val + min_val) / 2

        # Format y-axis labels
        if unit == "%":
            y_max_label = f"{max_val:.0f}%"
            y_mid_label = f"{mid_val:.0f}%"
            y_min_label = f"{min_val:.0f}%"
        else:
            y_max_label = f"{max_val:.0f}{unit}"
            y_mid_label = f"{mid_val:.0f}{unit}"
            y_min_label = f"{min_val:.0f}{unit}"

        # Determine y-axis label width (for alignment)
        y_label_width = max(len(y_max_label), len(y_mid_label), len(y_min_label))

        # Resample values to fit width
        if len(values) > width:
            # Downsample by averaging
            step = len(values) / width
            resampled = []
            for i in range(width):
                start_idx = int(i * step)
                end_idx = int((i + 1) * step)
                chunk = values[start_idx:end_idx]
                if chunk:
                    resampled.append(sum(chunk) / len(chunk))
            values = resampled
        elif len(values) < width:
            # Pad with last value
            values = values + [values[-1]] * (width - len(values))

        # Block characters for different heights (eighths)
        blocks = " ▁▂▃▄▅▆▇█"

        # Build chart rows with y-axis labels
        chart_rows = []
        for row in range(height - 1, -1, -1):
            row_chars = []
            for val in values:
                # Normalize value to 0-1 range
                normalized = (val - min_val) / (max_val - min_val)
                # Scale to chart height
                bar_height = normalized * height

                if bar_height >= row + 1:
                    row_chars.append("█")
                elif bar_height > row:
                    fraction = bar_height - row
                    block_idx = int(fraction * 8)
                    block_idx = min(block_idx, 8)
                    row_chars.append(blocks[block_idx])
                else:
                    row_chars.append(" ")

            # Add y-axis label
            if row == height - 1:
                y_label = y_max_label.rjust(y_label_width)
            elif row == height // 2:
                y_label = y_mid_label.rjust(y_label_width)
            elif row == 0:
                y_label = y_min_label.rjust(y_label_width)
            else:
                y_label = " " * y_label_width

            chart_rows.append(
                f"[dim]{y_label}[/dim] │[cyan]{''.join(row_chars)}[/cyan]"
            )

        # Build x-axis time labels
        if timestamps and len(timestamps) >= 2:
            first_ts = timestamps[0]
            last_ts = timestamps[-1]
            mid_idx = len(timestamps) // 2
            mid_ts = timestamps[mid_idx]

            x_min_label = self._format_time_ago(first_ts)
            x_mid_label = self._format_time_ago(mid_ts)
            x_max_label = self._format_time_ago(last_ts)

            # Position labels along the x-axis
            # Account for y-axis label width + separator
            x_axis_start = y_label_width + 2
            mid_pos = width // 2
            end_pos = width - len(x_max_label)

            # Build x-axis line
            x_axis = " " * x_axis_start
            x_axis += x_min_label
            padding_to_mid = mid_pos - len(x_min_label) - len(x_mid_label) // 2
            if padding_to_mid > 0:
                x_axis += " " * padding_to_mid
                x_axis += x_mid_label
                padding_to_end = end_pos - mid_pos - len(x_mid_label) // 2
                if padding_to_end > 0:
                    x_axis += " " * padding_to_end
                    x_axis += x_max_label

            chart_rows.append(f"[dim]{x_axis}[/dim]")

        return "\n".join(chart_rows)
