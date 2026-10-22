"""Error type and process exit codes shared by every devctl command."""

from __future__ import annotations

EXIT_OK = 0
EXIT_GATE = 1
EXIT_PRECONDITION = 2
EXIT_EXECUTION = 3
EXIT_REQUIRED_FEATURE = 4


class DevctlError(Exception):
    """A failure that maps directly onto a documented devctl exit code."""

    def __init__(self, code: int, message: str, detail: str | None = None) -> None:
        super().__init__(message)
        self.code = code
        self.message = message
        self.detail = detail
