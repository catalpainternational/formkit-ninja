"""
Don't make changes to this code directly
Instead, make changes to the template and re-generate this file
"""

from pydantic import BaseModel


class ParentItems(BaseModel):
    item_name: str | None = None
    item_count: int | None = None


class ParentChild(BaseModel):
    child_field: str | None = None


class Parent(BaseModel):
    child: ParentChild | None = None
    items: list[ParentItems] | None = None


class ParentChild(BaseModel):
    child_field: str | None = None


class ParentItems(BaseModel):
    item_name: str | None = None
    item_count: int | None = None
