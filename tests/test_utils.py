"""Tests for formkit_ninja.utils."""

from uuid import UUID, uuid4

from formkit_ninja.utils import short_uuid


def test_short_uuid_from_uuid():
    """short_uuid returns first 8 chars of UUID in uppercase."""
    u = uuid4()
    result = short_uuid(u)
    assert len(result) == 8
    # `str.isupper()` is False when the string has no cased characters, so an
    # all-digit hex prefix (~2% of random uuids) would flake. Check that the
    # value is already uppercased instead — robust for digit-only prefixes.
    assert result == result.upper()
    assert result == str(u).replace("-", "")[:8].upper()


def test_short_uuid_from_string():
    """short_uuid accepts string UUID and returns 8 chars uppercase."""
    s = "550e8400-e29b-41d4-a716-446655440000"
    result = short_uuid(s)
    assert result == "550E8400"


def test_short_uuid_none():
    """short_uuid(None) returns empty string."""
    assert short_uuid(None) == ""


def test_short_uuid_consistent():
    """Same UUID gives same short form regardless of input type."""
    u = uuid4()
    assert short_uuid(u) == short_uuid(str(u))


def test_short_uuid_accepts_uuid_object():
    """short_uuid accepts uuid.UUID and returns 8-char uppercase hex."""
    u = UUID("550e8400-e29b-41d4-a716-446655440000")
    assert short_uuid(u) == "550E8400"
