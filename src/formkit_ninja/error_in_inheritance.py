from typing import Literal

from pydantic import BaseModel, Field


class TestNodeType(BaseModel): ...


class TestTextNode(TestNodeType):
    node_type: Literal["formkit"] = Field(default="formkit", exclude=True)
    formkit: Literal["text"] = Field(default="text", alias="$formkit")


class TestGroupNode(BaseModel):
    children: list[TestTextNode]
