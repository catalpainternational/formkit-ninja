"""
Don't make changes to this code directly
Instead, make changes to the template and re-generate this file
"""

from __future__ import annotations

from ninja import Schema


class MainFormSchema(Schema):
    title: str | None = None
    description: str | None = None
    line_items: list[MainFormLineItemsSchema] | None = None


class MainFormLineItemsSchema(Schema):
    item_name: str | None = None
    quantity: int | None = None
    price: int | None = None
    ordinality: int


MainFormSchema.update_forward_refs()
MainFormLineItemsSchema.update_forward_refs()
