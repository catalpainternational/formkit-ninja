"""
Don't make changes to this code directly
Instead, make changes to the template and re-generate this file
"""

from ninja import Schema


class ParentItemsSchema(Schema):
    item_name: str | None = None
    item_count: int | None = None
    ordinality: int


class ParentChildSchema(Schema):
    child_field: str | None = None


class ParentSchema(Schema):
    child: ParentChild | None = None
    items: list[ParentItemsSchema] | None = None


class ParentChildSchema(Schema):
    child_field: str | None = None


class ParentItemsSchema(Schema):
    item_name: str | None = None
    item_count: int | None = None
    ordinality: int
