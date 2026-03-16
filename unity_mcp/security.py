"""
Security utilities: log sanitization and input validation.

Mirrors ``LogSanitizer`` and ``InputValidator`` from the C# reference.
"""

from __future__ import annotations

import re
from typing import Any, Dict, Iterable, Optional

from .exceptions import UnityMcpException
from .models import McpToolDefinition

# ---------------------------------------------------------------------------
# Sensitive key patterns (case-insensitive)
# ---------------------------------------------------------------------------

_SENSITIVE_KEYS = re.compile(
    r"(password|passwd|api[_-]?key|apikey|token|secret|authorization|bearer|credential)",
    re.IGNORECASE,
)

# ---------------------------------------------------------------------------
# LogSanitizer
# ---------------------------------------------------------------------------


class LogSanitizer:
    """
    Redacts sensitive data from log messages and parameter dictionaries.

    All methods are static — no instantiation needed.
    """

    @staticmethod
    def sanitize_parameters(params: Dict[str, Any]) -> Dict[str, Any]:
        """
        Return a copy of *params* with sensitive values replaced by ``[REDACTED]``.

        Nested dicts are sanitized recursively.
        """
        result: Dict[str, Any] = {}
        for key, value in params.items():
            if _SENSITIVE_KEYS.search(key):
                result[key] = "[REDACTED]"
            elif isinstance(value, dict):
                result[key] = LogSanitizer.sanitize_parameters(value)
            else:
                result[key] = value
        return result

    @staticmethod
    def sanitize_string(text: Optional[str]) -> Optional[str]:
        """
        Redact sensitive patterns from a free-form string.

        Handles JWT tokens, Bearer tokens, email addresses, passwords in
        connection strings, and long API-key-like strings.
        """
        if text is None:
            return None
        if text == "":
            return ""

        # JWT tokens (three base64url segments)
        text = re.sub(
            r"eyJ[A-Za-z0-9_-]+\.[A-Za-z0-9_-]+\.[A-Za-z0-9_-]+",
            "[REDACTED]",
            text,
        )
        # Bearer tokens
        text = re.sub(r"Bearer\s+\S+", "Bearer [REDACTED]", text, flags=re.IGNORECASE)
        # Email addresses
        text = re.sub(r"[a-zA-Z0-9._%+\-]+@[a-zA-Z0-9.\-]+\.[a-zA-Z]{2,}", "[EMAIL_REDACTED]", text)
        # Passwords in connection strings
        text = re.sub(r"(?i)(Password|Passwd)=([^;]+)", r"\1=[REDACTED]", text)
        # Long alphanumeric strings (32+ chars) that look like API keys
        text = re.sub(r"\b[A-Za-z0-9]{32,}\b", "[REDACTED]", text)
        return text

    @staticmethod
    def sanitize_config_value(key: str, value: str) -> str:
        """Return ``[REDACTED]`` if *key* looks sensitive, otherwise *value*."""
        return "[REDACTED]" if _SENSITIVE_KEYS.search(key) else value


# ---------------------------------------------------------------------------
# InputValidator
# ---------------------------------------------------------------------------

_SAFE_NAME = re.compile(r"[^a-zA-Z0-9_\-\.]")
_SAFE_PARAM = re.compile(r"[^a-zA-Z0-9_\-]")

# Patterns for error message sanitization
_WIN_PATH = re.compile(r"[A-Za-z]:\\[^\s]+")
_UNIX_PATH = re.compile(r"(?<!://)(?<!\w)/(?:[^\s:/]+/)+[^\s]*")
_STACK_TRACE = re.compile(r"at\s+[\w\.<>]+\([^\)]*\)\s+in\s+[^\s]+")
_INTERNAL_TYPE = re.compile(r"unity_mcp\.\w+\.\w+", re.IGNORECASE)
_URL_CREDS = re.compile(r"://[^:]+:[^@]+@")


class InputValidator:
    """
    Validates tool names and parameters; sanitizes error messages.

    All methods are static.
    """

    @staticmethod
    def validate_tool_name(tool_name: str, registered_tools: Iterable[str]) -> None:
        """
        Raise ``UnityMcpException`` if *tool_name* is empty or not registered.
        """
        if not tool_name or not tool_name.strip():
            raise UnityMcpException("Tool name cannot be null or empty")
        if tool_name not in set(registered_tools):
            safe = InputValidator._sanitize_tool_name(tool_name)
            raise UnityMcpException(f"Tool '{safe}' is not registered")

    @staticmethod
    def validate_parameters(
        parameters: Dict[str, Any],
        tool_definition: McpToolDefinition,
    ) -> None:
        """
        Raise ``UnityMcpException`` on missing required params, null required
        values, unknown params, or type mismatches.
        """
        # Required params present and non-null
        for param_def in tool_definition.parameters.values():
            if not param_def.required:
                continue
            safe = InputValidator._sanitize_param_name(param_def.name)
            if param_def.name not in parameters:
                raise UnityMcpException(f"Required parameter '{safe}' is missing")
            if parameters[param_def.name] is None:
                raise UnityMcpException(f"Required parameter '{safe}' cannot be null")

        # No unknown params; type check known ones
        for name, value in parameters.items():
            if value is None:
                continue
            if name not in tool_definition.parameters:
                raise UnityMcpException(f"Unknown parameter '{InputValidator._sanitize_param_name(name)}'")
            InputValidator._validate_type(name, value, tool_definition.parameters[name].type)

    @staticmethod
    def sanitize_error_message(message: Optional[str]) -> str:
        """Return a sanitized version of *message* safe for external display."""
        if not message:
            return "An error occurred"

        s = _URL_CREDS.sub("://[credentials]@", message)
        s = _WIN_PATH.sub("[path]", s)
        s = _UNIX_PATH.sub("[path]", s)
        s = _STACK_TRACE.sub("[stack trace removed]", s)
        s = _INTERNAL_TYPE.sub("[internal type]", s)

        if len(s) > 200:
            s = s[:197] + "..."
        return s

    # ------------------------------------------------------------------
    # Private helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _validate_type(name: str, value: Any, expected: str) -> None:
        safe = InputValidator._sanitize_param_name(name)
        t = expected.lower()
        valid = {
            "string": lambda v: isinstance(v, str),
            "number": lambda v: isinstance(v, (int, float)) and not isinstance(v, bool),
            "integer": lambda v: isinstance(v, int) and not isinstance(v, bool),
            "boolean": lambda v: isinstance(v, bool),
            "object": lambda v: True,
            "array": lambda v: isinstance(v, (list, tuple)) and not isinstance(v, str),
        }.get(t, lambda v: True)

        if not valid(value):
            raise UnityMcpException(f"Parameter '{safe}' has invalid type. Expected: {expected}")

    @staticmethod
    def _sanitize_tool_name(name: str) -> str:
        s = _SAFE_NAME.sub("", name)[:50]
        return s or "[invalid]"

    @staticmethod
    def _sanitize_param_name(name: str) -> str:
        s = _SAFE_PARAM.sub("", name)[:50]
        return s or "[invalid]"
