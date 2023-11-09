from formkit_ninja.api import make_name_valid_id, disambiguate_name


def test_disambiguate_name():
    assert disambiguate_name("test", set()) == "test"
    assert disambiguate_name("test", {"test"}) == "test_1"
    assert disambiguate_name("test", {"test_1"}) == "test"
    assert disambiguate_name("test", {"test", "test_1", "test_2"}) == "test_3"


def test_make_name_valid_id():
    assert make_name_valid_id("1Foo_") == "_1foo"
    assert make_name_valid_id("Foo_") == "foo"
    assert make_name_valid_id("Foo1") == "foo1"
