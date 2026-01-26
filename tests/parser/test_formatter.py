"""
Tests for formkit_ninja.parser.formatter module.

This module tests:
- CodeFormatter class
- Formatting valid Python code
- Handling formatting errors
- Edge cases (empty strings, only comments, invalid code)
"""

import subprocess
from unittest.mock import MagicMock, patch

import pytest

from formkit_ninja.parser.formatter import CodeFormatter, FormattingError


class TestCodeFormatter:
    """Tests for CodeFormatter class"""

    def test_formatter_can_be_instantiated(self):
        """Test that CodeFormatter can be instantiated"""
        formatter = CodeFormatter()
        assert formatter is not None

    def test_format_valid_python_code(self):
        """Test that valid Python code is formatted correctly"""
        formatter = CodeFormatter()
        unformatted = "def hello():\n    x=1+2\n    return x"
        formatted = formatter.format(unformatted)

        # Should be formatted (ruff will normalize spacing)
        assert isinstance(formatted, str)
        assert "def hello():" in formatted
        assert "return x" in formatted

    def test_format_preserves_code_meaning(self):
        """Test that formatting preserves code meaning"""
        formatter = CodeFormatter()
        code = "x=1+2+3"
        formatted = formatter.format(code)

        # Should still contain the same logic
        assert "x" in formatted
        assert "1" in formatted
        assert "2" in formatted
        assert "3" in formatted

    def test_format_empty_string(self):
        """Test that formatter handles empty strings"""
        formatter = CodeFormatter()
        result = formatter.format("")

        # Empty string should return empty string or be handled gracefully
        assert isinstance(result, str)

    def test_format_only_comments(self):
        """Test that formatter handles code with only comments"""
        formatter = CodeFormatter()
        code = "# This is a comment\n# Another comment"
        formatted = formatter.format(code)

        # Should handle comments gracefully
        assert isinstance(formatted, str)
        assert "#" in formatted

    def test_format_whitespace_only(self):
        """Test that formatter handles whitespace-only strings"""
        formatter = CodeFormatter()
        code = "   \n\t  \n  "
        formatted = formatter.format(code)

        # Should handle whitespace gracefully
        assert isinstance(formatted, str)

    def test_format_invalid_syntax_raises_error(self):
        """Test that invalid Python syntax raises FormattingError"""
        formatter = CodeFormatter()
        invalid_code = "def hello(\n    return x  # Missing closing paren and invalid syntax"

        with pytest.raises(FormattingError):
            formatter.format(invalid_code)

    def test_format_incomplete_code_raises_error(self):
        """Test that incomplete code raises FormattingError"""
        formatter = CodeFormatter()
        incomplete_code = "def hello("  # Missing closing paren

        with pytest.raises(FormattingError):
            formatter.format(incomplete_code)

    def test_format_error_includes_message(self):
        """Test that FormattingError includes a helpful message"""
        formatter = CodeFormatter()
        invalid_code = "def hello(\n    return x"

        with pytest.raises(FormattingError) as exc_info:
            formatter.format(invalid_code)

        assert len(str(exc_info.value)) > 0
        assert isinstance(exc_info.value.message, str)

    @patch("subprocess.run")
    def test_format_uses_ruff_subprocess(self, mock_run):
        """Test that formatter uses ruff format via subprocess"""
        # Mock successful ruff format
        mock_process = MagicMock()
        mock_process.returncode = 0
        mock_process.stdout = b"formatted_code = 1\n"
        mock_run.return_value = mock_process

        formatter = CodeFormatter()
        formatter.format("code=1")

        # Verify subprocess.run was called with ruff format
        mock_run.assert_called_once()
        call_args = mock_run.call_args
        assert "ruff" in call_args[0][0] or "ruff" in str(call_args)

    @patch("subprocess.run")
    def test_format_handles_ruff_not_found(self, mock_run):
        """Test that formatter handles ruff not being found gracefully"""
        # Mock FileNotFoundError (ruff not in PATH)
        mock_run.side_effect = FileNotFoundError("ruff: command not found")

        formatter = CodeFormatter()
        with pytest.raises(FormattingError) as exc_info:
            formatter.format("x = 1")

        assert "ruff" in str(exc_info.value).lower() or "not found" in str(exc_info.value).lower()

    @patch("subprocess.run")
    def test_format_handles_ruff_nonzero_exit(self, mock_run):
        """Test that formatter handles ruff returning non-zero exit code"""
        # Mock ruff format failure - CalledProcessError is raised when check=True and returncode != 0
        mock_process = MagicMock()
        mock_process.returncode = 1
        mock_process.stderr = b"Error: invalid syntax"
        mock_run.side_effect = subprocess.CalledProcessError(
            returncode=1,
            cmd=["ruff", "format", "--stdin-filename", "code.py"],
            stderr=b"Error: invalid syntax",
        )

        formatter = CodeFormatter()
        with pytest.raises(FormattingError):
            formatter.format("invalid syntax here")

    @patch("subprocess.run")
    def test_format_handles_subprocess_error(self, mock_run):
        """Test that formatter handles subprocess errors gracefully"""
        # Mock subprocess error
        mock_run.side_effect = subprocess.SubprocessError("Subprocess failed")

        formatter = CodeFormatter()
        with pytest.raises(FormattingError):
            formatter.format("x = 1")

    @patch("subprocess.run")
    def test_format_handles_stderr_decode_error(self, mock_run):
        """Test that formatter handles stderr that fails to decode"""
        # Create a mock object with stderr that raises UnicodeDecodeError when decode is called
        mock_stderr = MagicMock()
        mock_stderr.decode.side_effect = UnicodeDecodeError("utf-8", b"", 0, 1, "invalid start byte")

        # Mock CalledProcessError with custom stderr
        mock_error = subprocess.CalledProcessError(
            returncode=1,
            cmd=["ruff", "format", "--stdin-filename", "code.py"],
        )
        mock_error.stderr = mock_stderr
        mock_run.side_effect = mock_error

        formatter = CodeFormatter()
        with pytest.raises(FormattingError) as exc_info:
            formatter.format("invalid code")

        # Should still raise FormattingError with fallback message
        assert "Code formatting failed" in str(exc_info.value)

    @patch("subprocess.run")
    def test_format_handles_generic_exception(self, mock_run):
        """Test that formatter handles unexpected exceptions gracefully"""
        # Mock an unexpected exception
        mock_run.side_effect = ValueError("Unexpected error")

        formatter = CodeFormatter()
        with pytest.raises(FormattingError) as exc_info:
            formatter.format("x = 1")

        assert "Unexpected error" in str(exc_info.value)

    def test_format_complex_code(self):
        """Test that formatter handles complex Python code"""
        formatter = CodeFormatter()
        complex_code = """
class MyClass:
    def __init__(self, x):
        self.x = x
    
    def method(self):
        return self.x * 2
"""
        formatted = formatter.format(complex_code)

        assert "class MyClass:" in formatted
        assert "def __init__" in formatted
        assert "def method" in formatted

    def test_format_with_imports(self):
        """Test that formatter handles code with imports"""
        formatter = CodeFormatter()
        code = "from typing import List, Dict\nimport os\nx:List[int]=[1,2,3]"
        formatted = formatter.format(code)

        assert "from typing import" in formatted or "from typing" in formatted
        assert "import os" in formatted

    def test_format_multiline_string(self):
        """Test that formatter handles multiline strings"""
        formatter = CodeFormatter()
        code = 'x="""\nmultiline\nstring\n"""'
        formatted = formatter.format(code)

        assert isinstance(formatted, str)
        assert "multiline" in formatted or "string" in formatted
