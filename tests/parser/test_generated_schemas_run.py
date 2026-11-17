"""
The generated schema modules must import and validate data under Pydantic 2.

These tests load the generated modules the way a consumer would and push a
submission through them.
"""

import importlib.util
import sys
from datetime import date
from decimal import Decimal
from pathlib import Path
from types import ModuleType, SimpleNamespace
from typing import Any

import pytest

from formkit_ninja.formkit_schema import FormKitSchema
from formkit_ninja.parser.formatter import CodeFormatter
from formkit_ninja.parser.generator import CodeGenerator
from formkit_ninja.parser.generator_config import GeneratorConfig
from formkit_ninja.parser.template_loader import DefaultTemplateLoader
from formkit_ninja.parser.type_convert import NodePath

FORM = [
    {
        "$formkit": "group",
        "name": "visit",
        "children": [
            # A field named after the type it holds: Partisipa forms have these.
            {"$formkit": "datepicker", "name": "date"},
            {"$formkit": "datepicker", "name": "follow_up"},
            {"$formkit": "text", "name": "name"},
            {"$formkit": "number", "name": "count"},
            {"$formkit": "currency", "name": "amount"},
            {"$formkit": "uuid", "name": "ref"},
            {"$formkit": "checkbox", "name": "ok"},
            {"$formkit": "group", "name": "place", "children": [{"$formkit": "text", "name": "village"}]},
            {
                "$formkit": "repeater",
                "name": "people",
                "children": [
                    {"$formkit": "text", "name": "who"},
                    {"$formkit": "repeater", "name": "visits", "children": [{"$formkit": "datepicker", "name": "date"}]},
                ],
            },
        ],
    }
]


def load(path: Path) -> ModuleType:
    name = f"generated_{path.parent.name}_{path.stem}"
    spec = importlib.util.spec_from_file_location(name, path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    try:
        spec.loader.exec_module(module)
    finally:
        del sys.modules[name]
    return module


@pytest.fixture(scope="module")
def generated(tmp_path_factory: pytest.TempPathFactory) -> Path:
    out = tmp_path_factory.mktemp("generated")
    config = GeneratorConfig(app_name="visits", output_dir=out, node_path_class=NodePath)
    CodeGenerator(config=config, template_loader=DefaultTemplateLoader(), formatter=CodeFormatter()).generate(FORM)
    return out


def test_input_schemas_validate_a_submission(generated: Path) -> None:
    schemas_in = load(generated / "schemas_in" / "visit.py")

    visit = schemas_in.VisitSchema.model_validate(
        {
            "date": "2026-11-17",
            "follow_up": "2026-12-01",
            "count": "3",
            "amount": "12.50",
            "ref": "6f1c1d1e-0000-4000-8000-000000000001",
            "place": {"village": "Aileu"},
            "people": [{"who": "Ana", "visits": [{"date": "2026-10-01"}]}],
        }
    )

    assert visit.date == date(2026, 11, 17)
    assert visit.follow_up == date(2026, 12, 1)
    assert visit.count == 3
    assert visit.amount == Decimal("12.50")
    assert visit.place.village == "Aileu"
    assert visit.people[0].visits[0].date == date(2026, 10, 1)
    assert visit.model_dump(mode="json")["date"] == "2026-11-17"


def test_output_schemas_read_saved_rows(generated: Path) -> None:
    """The output schemas read attributes, as django-ninja does from a model instance."""
    schemas = load(generated / "schemas" / "visit.py")

    row = SimpleNamespace(
        date=date(2026, 11, 17),
        follow_up=None,
        name="Ana",
        count=3,
        amount=Decimal("12.50"),
        ref=None,
        ok=True,
        place=SimpleNamespace(village="Aileu"),
        people=[SimpleNamespace(who="Ana", ordinality=0, visits=[SimpleNamespace(date=date(2026, 10, 1), ordinality=0)])],
    )

    visit = schemas.VisitSchema.model_validate(row)

    assert visit.date == date(2026, 11, 17)
    assert visit.place.village == "Aileu"
    assert visit.people[0].visits[0].date == date(2026, 10, 1)
    assert visit.people[0].ordinality == 0


def generate(tmp_path: Path, form: list[dict] | FormKitSchema, node_path_class: type[NodePath] = NodePath, **config: Any) -> Path:
    config = GeneratorConfig(app_name="visits", output_dir=tmp_path, node_path_class=node_path_class, **config)
    CodeGenerator(config=config, template_loader=DefaultTemplateLoader(), formatter=CodeFormatter()).generate(form)
    return tmp_path


class DistrictIsAForeignKey(NodePath):
    """As in Partisipa, where an answer naming a district is stored as a link to the district."""

    def to_django_type(self) -> str:
        if self.fieldname == "district":
            return "ForeignKey"
        return super().to_django_type()


def test_a_linked_answer_is_read_from_its_own_key(tmp_path: Path) -> None:
    form = [{"$formkit": "group", "name": "visit", "children": [{"$formkit": "number", "name": "district"}]}]
    out = generate(tmp_path, form, DistrictIsAForeignKey)

    schemas_in = load(out / "schemas_in" / "visit.py")
    schemas = load(out / "schemas" / "visit.py")

    assert schemas_in.VisitSchema.model_validate({"district": 7}).district == 7
    # The output side reads the saved row, where Django names the column district_id.
    assert schemas.VisitSchema.model_validate(SimpleNamespace(district_id=7)).district_id == 7
    # The admin preview of the input model agrees with the generated file.
    assert "    district: int | None = None" in DistrictIsAForeignKey.from_obj(form[0]).pydantic_model_code


LAYOUT_FORM = [
    {
        "$formkit": "group",
        "name": "visit",
        "children": [
            {"$formkit": "text", "name": "name"},
            {
                "$el": "div",
                "children": [
                    {"$formkit": "currency", "name": "amount"},
                    {"$formkit": "group", "name": "place", "children": [{"$el": "div", "children": [{"$formkit": "text", "name": "village"}]}]},
                    {"$formkit": "repeater", "name": "people", "children": [{"$el": "div", "children": [{"$formkit": "text", "name": "who"}]}]},
                ],
            },
        ],
    }
]


@pytest.mark.parametrize("as_schema_object", [False, True], ids=["dicts", "schema object"])
def test_answers_inside_layout_elements_are_kept(tmp_path: Path, as_schema_object: bool) -> None:
    out = generate(tmp_path, FormKitSchema.parse_obj(LAYOUT_FORM) if as_schema_object else LAYOUT_FORM)
    schemas_in = load(out / "schemas_in" / "visit.py")

    visit = schemas_in.VisitSchema.model_validate({"name": "Ana", "amount": "1.50", "place": {"village": "Aileu"}, "people": [{"who": "Rui"}]})

    assert visit.amount == Decimal("1.50")
    assert visit.place.village == "Aileu"
    assert visit.people[0].who == "Rui"
    models = (out / "models" / "visit.py").read_text()
    assert "class VisitPeople(models.Model)" in models
    assert 'parent = models.ForeignKey("Visit"' in models


class CapitalisedNames(NodePath):
    """A node path that adds its own validator, which needs its own import."""

    def get_validators(self) -> list[str]:
        if self.fieldname == "name":
            return ['_capitalise_name = field_validator("name", mode="before")(capwords)']
        if self.fieldname == "count":
            return ['_negate_count = field_validator("count")(neg)']
        return super().get_validators()

    def get_extra_imports(self) -> list[str]:
        if self.fieldname == "name":
            return ["from string import capwords"]
        return super().get_extra_imports()


def test_validators_get_the_imports_they_need(tmp_path: Path) -> None:
    form = [{"$formkit": "group", "name": "visit", "children": [{"$formkit": "text", "name": "name"}, {"$formkit": "number", "name": "count"}]}]
    out = generate(tmp_path, form, CapitalisedNames, custom_imports=["from operator import neg"])

    visit = load(out / "schemas_in" / "visit.py").VisitSchema.model_validate({"name": "ana maria", "count": 3})

    assert visit.name == "Ana Maria"
    assert visit.count == -3


class RepeaterRowsKnowTheirSubmission(NodePath):
    """As in Partisipa, where each repeater row carries the id of the submission it was split into."""

    @property
    def pydantic_input_code(self) -> str:
        if self.fieldname == "uuid" and (self / "..").is_repeater:
            return 'uuid: UUID = Field(alias="submission")'
        return super().pydantic_input_code


def test_a_project_can_write_its_own_line_for_one_field(tmp_path: Path) -> None:
    form = [
        {
            "$formkit": "group",
            "name": "visit",
            "children": [{"$formkit": "repeater", "name": "people", "children": [{"$formkit": "uuid", "name": "uuid"}, {"$formkit": "text", "name": "who"}]}],
        }
    ]
    people = load(generate(tmp_path, form, RepeaterRowsKnowTheirSubmission) / "schemas_in" / "visit.py").VisitPeopleSchema

    row = people.model_validate({"submission": "6f1c1d1e-0000-4000-8000-000000000001", "who": "Ana"})

    assert str(row.uuid) == "6f1c1d1e-0000-4000-8000-000000000001"
    with pytest.raises(ValueError):
        people.model_validate({"who": "Ana"})
