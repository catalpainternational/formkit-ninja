from typing import Any

from pydantic import (BaseModel, RootModel, ValidatorFunctionWrapHandler,
                      field_validator)


class MyModel(BaseModel):
    value: str

    @field_validator("value", mode="wrap")
    @classmethod
    def translate(cls, value: Any, handler: ValidatorFunctionWrapHandler) -> str:
        return handler(value)[::-1]


def test_mymodel():
    model = MyModel.model_validate({"value": "This is a message"})
    assert model.value == "egassem a si sihT"


class SomeRootModel(RootModel):
    root: MyModel


def test_rootmodel():
    model = SomeRootModel.model_validate({"value": "This is a message"})
    assert model.root.value == "egassem a si sihT"
