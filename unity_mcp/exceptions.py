"""
Domain exceptions for the Unity MCP plugin.

Hierarchy::

    UnityMcpException
    ├── NetworkException
    ├── TimeoutException
    ├── ProtocolException
    ├── McpServerException
    ├── ProcessException
    ├── ConfigurationException
    └── TypeConversionException
"""

from __future__ import annotations

from datetime import timedelta
from typing import Optional


class UnityMcpException(Exception):
    """Base exception for all Unity MCP errors."""


class NetworkException(UnityMcpException):
    """Raised when communication with the unity-mcp process fails."""

    def __init__(self, message: str, endpoint: str = "stdio://unity-mcp", cause: Optional[Exception] = None) -> None:
        super().__init__(message)
        self.endpoint = endpoint
        self.__cause__ = cause


class TimeoutException(UnityMcpException):
    """Raised when an operation exceeds its configured timeout."""

    def __init__(self, message: str, timeout: timedelta, operation: str = "") -> None:
        super().__init__(message)
        self.timeout = timeout
        self.operation = operation


class ProtocolException(UnityMcpException):
    """Raised when MCP messages are malformed or the protocol is violated."""

    def __init__(self, message: str, malformed_data: Optional[str] = None, cause: Optional[Exception] = None) -> None:
        super().__init__(message)
        self.malformed_data = malformed_data
        self.__cause__ = cause


class McpServerException(UnityMcpException):
    """Raised when the Unity MCP server returns a JSON-RPC error response."""

    def __init__(self, message: str, error_code: int = -1, error_data: Optional[str] = None) -> None:
        super().__init__(message)
        self.error_code = error_code
        self.error_data = error_data


class ProcessException(UnityMcpException):
    """Raised when the unity-mcp subprocess cannot be started or managed."""

    def __init__(self, message: str, process_id: Optional[int] = None, cause: Optional[Exception] = None) -> None:
        super().__init__(message)
        self.process_id = process_id
        self.__cause__ = cause


class ConfigurationException(UnityMcpException):
    """Raised when the plugin is misconfigured."""

    def __init__(self, message: str, parameter_name: str = "") -> None:
        super().__init__(message)
        self.parameter_name = parameter_name


class TypeConversionException(UnityMcpException):
    """Raised when a parameter or result cannot be converted to the expected type."""

    def __init__(self, message: str, source_type: str = "", target_type: str = "") -> None:
        super().__init__(message)
        self.source_type = source_type
        self.target_type = target_type
