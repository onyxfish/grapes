"""Cluster loading screen widget for Grapes."""

import logging

from textual.app import ComposeResult
from textual.reactive import reactive
from textual.widgets import Static

logger = logging.getLogger(__name__)


class LoadingScreen(Static):
    """Loading screen shown during initial data fetch."""

    status_message: reactive[str] = reactive("Initializing...")

    def compose(self) -> ComposeResult:
        """Compose the loading screen."""
        yield Static(id="loading-message")

    def on_mount(self) -> None:
        """Initialize the loading screen."""
        self._update_display()

    def watch_status_message(self, message: str) -> None:
        """Update when status message changes."""
        self._update_display()

    def _update_display(self) -> None:
        """Update the loading screen display."""
        try:
            message = self.query_one("#loading-message", Static)
            message.update(
                f"[bold]Grapes[/bold]\n\n"
                f"Loading cluster data...\n\n"
                f"[cyan]{self.status_message}[/cyan]"
            )
        except Exception as e:
            logger.debug(f"Loading screen not mounted yet: {e}")

    def update_status(self, message: str) -> None:
        """Update the loading status message."""
        self.status_message = message
