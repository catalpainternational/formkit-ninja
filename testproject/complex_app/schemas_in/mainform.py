"""
Don't make changes to this code directly
Instead, make changes to the template and re-generate this file
"""

from __future__ import annotations

from pydantic import BaseModel


class MainFormSchema(BaseModel):
    title: str | None = None
    description: str | None = None
    line_items: list[MainFormLineItemsSchema] | None = None


class MainFormLineItemsSchema(BaseModel):
    item_name: str | None = None
    quantity: int | None = None
    price: int | None = None


MainFormSchema.update_forward_refs()
MainFormLineItemsSchema.update_forward_refs()
