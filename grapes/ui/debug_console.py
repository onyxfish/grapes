"""Debug console widget for displaying application logs."""

import logging
from typing import TYPE_CHECKING

from textual.app import ComposeResult
from textual.widgets import RichLog, Static

if TYPE_CHECKING:
    from textual.app import App


class TextualLogHandler(logging.Handler):
    """Custom log handler that routes logs to RichLog widget."""

    def __init__(self, console: "DebugConsole", app: "App"):
        """Initialize the handler.

        Args:
            console: DebugConsole widget to route logs to
            app: The Textual App instance (stored directly to avoid thread issues)
        """
        super().__init__()
        self.console = console
        self._app = app
        # Format: timestamp - level - logger - message
        self.setFormatter(
            logging.Formatter(
                "%(asctime)s - %(levelname)-8s - %(name)s - %(message)s",
                datefmt="%H:%M:%S",
            )
        )

    def emit(self, record: logging.LogRecord) -> None:
        """Emit a log record to the console.

        Args:
            record: Log record to emit
        """
        try:
            message = self.format(record)
            # Thread-safe: use call_from_thread since logs may come from workers
            # Use stored app reference to avoid NoActiveAppError from worker threads
            self._app.call_from_thread(
                self.console.write_log, message, record.levelname
            )
        except Exception:
            # Silently ignore errors - don't call handleError as it prints to stderr
            pass


class DebugConsole(Static):
    """Debug console widget with log display."""

    def compose(self) -> ComposeResult:
        """Compose the debug console."""
        yield RichLog(id="debug-log", highlight=True, markup=True)

    def on_mount(self) -> None:
        """Set up the console when mounted."""
        log = self.query_one("#debug-log", RichLog)
        log.can_focus = False  # Don't steal focus from main UI

    @property
    def is_visible(self) -> bool:
        """Check if the debug console is currently visible."""
        return self.has_class("visible")

    def write_log(self, message: str, level: str) -> None:
        """Write a log message to the console.

        Args:
            message: Formatted log message
            level: Log level (DEBUG, INFO, WARNING, ERROR, CRITICAL)
        """
        log = self.query_one("#debug-log", RichLog)

        # Color-code by level
        if level in ("ERROR", "CRITICAL"):
            styled_message = f"[red]{message}[/red]"
        elif level == "WARNING":
            styled_message = f"[yellow]{message}[/yellow]"
        elif level == "DEBUG":
            styled_message = f"[dim]{message}[/dim]"
        else:  # INFO
            styled_message = message

        log.write(styled_message)

    def clear(self) -> None:
        """Clear the console."""
        log = self.query_one("#debug-log", RichLog)
        log.clear()
