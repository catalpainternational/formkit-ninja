from formkit_ninja.html_parser import FormKitTagParser


def test_basic_example():
    html_content = """
    <formkit type="text" />
    """
    parser = FormKitTagParser(html_content)
    assert parser.tags[0].model_dump(exclude_none=True, by_alias=True) == {
        "$formkit": "text"
    }
