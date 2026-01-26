"""
Don't make changes to this code directly
Instead, make changes to the template and re-generate this file
"""

from pydantic import BaseModel


class Testgroup(BaseModel):
    field1: str | None = None
