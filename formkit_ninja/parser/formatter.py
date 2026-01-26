"""
Code formatter using ruff.

This module provides a CodeFormatter class that uses ruff format
to format Python code strings.
"""

import subprocess
from typing import Optional


class FormattingError(Exception):
    """Exception raised when code formatting fails."""

    def __init__(self, message: str, original_error: Optional[Exception] = None) -> None:
        """Initialize FormattingError with a message and optional original error.

        Args:
            message: Error message describing what went wrong
            original_error: The original exception that caused the formatting error
        """
        super().__init__(message)
        self.message = message
        self.original_error = original_error


class CodeFormatter:
    """Formatter for Python code using ruff format."""

    def format(self, code: str) -> str:
        """Format Python code using ruff format.

        Args:
            code: The Python code string to format

        Returns:
            The formatted Python code string

        Raises:
            FormattingError: If formatting fails (invalid syntax, ruff not found, etc.)
        """
        if not code.strip():
            # Handle empty or whitespace-only strings
            return code

        try:
            # Use ruff format via subprocess
            # --stdin-filename ensures ruff treats input as Python code
            result = subprocess.run(
                ["ruff", "format", "--stdin-filename", "code.py"],
                input=code.encode("utf-8"),
                capture_output=True,
                check=True,
                text=False,  # We handle encoding manually
            )

            # Decode the formatted output
            formatted = result.stdout.decode("utf-8")

            return formatted

        except FileNotFoundError as e:
            raise FormattingError(
                "ruff command not found. Please ensure ruff is installed and in your PATH.",
                original_error=e,
            ) from e

        except subprocess.CalledProcessError as e:
            # Ruff returned non-zero exit code (usually syntax errors)
            error_message = "Code formatting failed"
            if e.stderr:
                try:
                    stderr_text = e.stderr.decode("utf-8")
                    error_message = f"Code formatting failed: {stderr_text}"
                except (UnicodeDecodeError, AttributeError):
                    error_message = f"Code formatting failed (exit code {e.returncode})"

            raise FormattingError(error_message, original_error=e) from e

        except subprocess.SubprocessError as e:
            raise FormattingError(
                f"Subprocess error during formatting: {str(e)}",
                original_error=e,
            ) from e

        except Exception as e:
            raise FormattingError(
                f"Unexpected error during formatting: {str(e)}",
                original_error=e,
            ) from e
