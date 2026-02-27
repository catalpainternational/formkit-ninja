"""
App-wide utility functions.
"""

from uuid import UUID


def short_uuid(value: UUID | str | None) -> str:
    """
    Return the first 8 characters of a UUID in consistent uppercase for display.

    Use for list displays, __str__, and any frontend display of a raw UUID
    to keep formatting consistent and readable.

    Args:
        value: A UUID instance, UUID string, or None.

    Returns:
        First 8 characters in uppercase, or empty string if value is None.
    """
    if value is None:
        return ""
    s = str(value).replace("-", "")[:8]
    return s.upper()
