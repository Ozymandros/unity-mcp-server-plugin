"""
Subprocess lifecycle manager for the unity-mcp process.

Single Responsibility: start, monitor, and stop the ``unity-mcp`` executable.
No MCP protocol logic lives here.
"""

from __future__ import annotations

import asyncio
import logging
from datetime import datetime, timezone
from typing import Optional

from .exceptions import ProcessException
from .models import ProcessInfo, ProcessState, UnityMcpOptions

logger = logging.getLogger(__name__)


class ProcessManager:
    """
    Manages the ``unity-mcp`` subprocess lifecycle.

    Implements ``IProcessManager`` (structural subtyping via duck-typing).

    Usage::

        mgr = ProcessManager(options)
        info = await mgr.ensure_process_running()
        # write to mgr.stdin / read from mgr.stdout
        await mgr.stop_process()
    """

    def __init__(self, options: UnityMcpOptions) -> None:
        self._options = options
        self._process: Optional[asyncio.subprocess.Process] = None
        self._state = ProcessState.NOT_STARTED
        self._started_at: datetime = datetime.min.replace(tzinfo=timezone.utc)
        self._lock = asyncio.Lock()

    # ------------------------------------------------------------------
    # IProcessManager
    # ------------------------------------------------------------------

    @property
    def state(self) -> ProcessState:
        return self._state

    @property
    def stdin(self) -> asyncio.StreamWriter:
        if self._process is None or self._process.stdin is None:
            raise ProcessException("Process not started or stdin unavailable")
        return self._process.stdin

    @property
    def stdout(self) -> asyncio.StreamReader:
        if self._process is None or self._process.stdout is None:
            raise ProcessException("Process not started or stdout unavailable")
        return self._process.stdout

    async def ensure_process_running(self) -> ProcessInfo:
        """
        Start the subprocess if it is not already running.

        Returns ``ProcessInfo`` for the running process.
        Raises ``ProcessException`` on failure.
        """
        async with self._lock:
            if self._state == ProcessState.RUNNING and self._process is not None:
                if self._process.returncode is None:
                    return ProcessInfo(
                        process_id=self._process.pid,
                        executable_path=self._options.executable_path,
                        started_at=self._started_at,
                    )
                # Process exited unexpectedly — restart
                logger.warning("unity-mcp process exited unexpectedly (rc=%s), restarting", self._process.returncode)

            return await self._start_process()

    async def stop_process(self) -> None:
        """Gracefully terminate the subprocess."""
        async with self._lock:
            if self._process is None or self._state == ProcessState.NOT_STARTED:
                return
            try:
                if self._process.returncode is None:
                    self._process.terminate()
                    try:
                        await asyncio.wait_for(self._process.wait(), timeout=5.0)
                    except asyncio.TimeoutError:
                        self._process.kill()
                        await self._process.wait()
                self._state = ProcessState.STOPPED
                logger.debug("unity-mcp process stopped")
            except Exception as exc:
                logger.warning("Error stopping process: %s", exc)
                self._state = ProcessState.STOPPED
            finally:
                self._process = None

    async def close(self) -> None:
        """Alias for ``stop_process`` — satisfies async context manager pattern."""
        await self.stop_process()

    # ------------------------------------------------------------------
    # Private
    # ------------------------------------------------------------------

    async def _start_process(self) -> ProcessInfo:
        try:
            self._process = await asyncio.create_subprocess_exec(
                self._options.executable_path,
                stdin=asyncio.subprocess.PIPE,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
            self._started_at = datetime.now(timezone.utc)
            self._state = ProcessState.RUNNING
            logger.info("Started unity-mcp process (pid=%d)", self._process.pid)
            return ProcessInfo(
                process_id=self._process.pid,
                executable_path=self._options.executable_path,
                started_at=self._started_at,
            )
        except FileNotFoundError as exc:
            self._state = ProcessState.FAULTED
            raise ProcessException(
                f"Failed to start unity-mcp process: executable '{self._options.executable_path}' not found. "
                "Install with: dotnet tool install -g unity-mcp",
                cause=exc,
            ) from exc
        except Exception as exc:
            self._state = ProcessState.FAULTED
            raise ProcessException(f"Failed to start unity-mcp process: {exc}", cause=exc) from exc
