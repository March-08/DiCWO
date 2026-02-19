"""Background thread wrapper for running experiments without blocking Streamlit."""

from __future__ import annotations

import queue
import threading
import traceback
from typing import Any


class ExperimentThread:
    """Runs an ExperimentRunner in a background daemon thread.

    Progress events are pushed to a thread-safe queue that
    the Streamlit main loop polls via drain_events().
    """

    def __init__(self) -> None:
        self.queue: queue.Queue[tuple[str, dict[str, Any]]] = queue.Queue()
        self._thread: threading.Thread | None = None
        self.result: dict[str, Any] | None = None
        self.error: str | None = None
        self.done = threading.Event()

    # ------------------------------------------------------------------
    # Callback wired into ExperimentRunner / LLMClient
    # ------------------------------------------------------------------

    def _progress_callback(self, event_type: str, data: dict[str, Any]) -> None:
        self.queue.put((event_type, data))

    # ------------------------------------------------------------------
    # Run API
    # ------------------------------------------------------------------

    def start(self, runner_factory: Any, repeat: int = 1) -> None:
        """Start the experiment in a background thread.

        Args:
            runner_factory: callable() -> ExperimentRunner (created with progress_callback)
            repeat: number of repetitions (1 = single run)
        """
        self.done.clear()
        self.result = None
        self.error = None

        def _target() -> None:
            try:
                runner = runner_factory(self._progress_callback)
                if repeat > 1:
                    self.result = runner.run_repeated(repeat)
                else:
                    self.result = runner.run()
            except Exception:
                self.error = traceback.format_exc()
                self.queue.put(("error", {"traceback": self.error}))
            finally:
                self.done.set()
                self.queue.put(("finished", {}))

        self._thread = threading.Thread(target=_target, daemon=True)
        self._thread.start()

    @property
    def is_running(self) -> bool:
        return self._thread is not None and self._thread.is_alive()

    def drain_events(self) -> list[tuple[str, dict[str, Any]]]:
        """Non-blocking drain of all queued events."""
        events = []
        while True:
            try:
                events.append(self.queue.get_nowait())
            except queue.Empty:
                break
        return events
