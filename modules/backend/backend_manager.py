"""Utilities for running the FastAPI backend in a dedicated thread."""

from __future__ import annotations

import threading
from typing import Optional

import uvicorn

from modules.backend.backend import backend_app


class BackendManager:
    """Launch and manage the FastAPI backend server."""

    def __init__(
        self,
        host: str = "0.0.0.0",
        port: int = 3191,
        reload: bool = False,
        log_level: str = "info",
    ) -> None:
        self.host = host
        self.port = port
        self.reload = reload
        self.log_level = log_level
        self._thread: Optional[threading.Thread] = None

    def start_backend(self) -> None:
        """Blocking call that runs the uvicorn server."""
        uvicorn.run(
            backend_app,
            host=self.host,
            port=self.port,
            reload=self.reload,
            log_level=self.log_level,
            access_log=False,
        )

    def start(self) -> None:
        """Start the backend server in a daemon thread if not already running."""
        if self._thread and self._thread.is_alive():
            return

        self._thread = threading.Thread(target=self.start_backend, daemon=True)
        self._thread.start()

