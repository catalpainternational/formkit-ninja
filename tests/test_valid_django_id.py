import pytest

from formkit_ninja.models import check_valid_django_id


def test_valid_id():
    assert check_valid_django_id("valid_id") is None


def test_invalid_id_starting_with_digit():
    with pytest.raises(TypeError):
        check_valid_django_id("1invalid")


def test_invalid_id_ending_with_underscore():
    with pytest.raises(TypeError):
        check_valid_django_id("invalid_")


def test_invalid_id_with_keyword():
    with pytest.raises(TypeError):
        check_valid_django_id("for")


def test_invalid_id_with_softkeyword():
    with pytest.raises(TypeError):
        check_valid_django_id("async")
