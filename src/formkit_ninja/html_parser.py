from html.parser import HTMLParser

from formkit_ninja.formkit_schema import DiscriminatedNodeType


class FormKitTagParser(HTMLParser):
    """
    Reverse an HTML example to schema
    This is for lazy copy-pasting from the formkit website :)
    """

    def __init__(self, html_content: str, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.data: str | None = None

        self.current_tag: DiscriminatedNodeType | None = None
        self.tags: list[DiscriminatedNodeType] = []
        self.parents: list[DiscriminatedNodeType] = []
        self.feed(html_content)

    def handle_starttag(self, tag, attrs):
        """
        Read anything that's a "formtag" type
        """
        if tag != "formkit":
            return
        props = dict(attrs)
        props["$formkit"] = props.pop("type")

        tag = DiscriminatedNodeType(**props)
        if isinstance(tag, DiscriminatedNodeType):
            tag = tag.root
        self.current_tag = tag

        if self.parents:
            self.parents[-1].children.append(tag)
        else:
            self.tags.append(tag)
            self.parents.append(tag)

    def handle_endtag(self, tag: str) -> None:
        if tag != "formkit":
            return
        if self.parents:
            self.parents.pop()

    def handle_data(self, data):
        if self.current_tag and data.strip():
            if self.current_tag.children is None:
                self.current_tag.children = [data.strip()]
            else:
                self.current_tag.children.append(data.strip())
            # Ensure that children is included even when "exclude_unset" is True
            # since we populated this after the initial tag build
            self.current_tag.model_fields_set.add("children")
