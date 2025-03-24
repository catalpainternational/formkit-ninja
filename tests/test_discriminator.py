from typing import Any

import pytest
from pydantic import RootModel, TypeAdapter

from formkit_ninja import models
from formkit_ninja.formkit_schema import (DiscriminatedNodeType, FormKitNode,
                                          FormKitSchemaFormKit, GroupNode,
                                          RepeaterNode, TextAreaNode, TextNode)
from tests.test_python_models import schema_are_same


class Node(RootModel):
    root: FormKitSchemaFormKit


type_adapter = TypeAdapter(FormKitSchemaFormKit)


def test_text():
    n = Node({"$formkit": "text"})
    n.model_dump(by_alias=True, exclude_none=True)


def test_group():
    n = Node({"$formkit": "group", "children": [{"$formkit": "text"}]})
    n.root.model_dump(by_alias=True, exclude_none=True)


def test_nested_group():
    n = Node.model_validate(
        {
            "$formkit": "group",
            "randomprop": "random",
            "children": [
                {
                    "$formkit": "group",
                    "children": [{"$formkit": "group", "randomprop": "random"}],
                }
            ],
        }
    )
    n.root.model_dump(by_alias=True, exclude_none=True)


def test_nested_group_adapter():
    n = GroupNode.model_validate({"$formkit": "group", "randomprop": "random"})
    print(n)


def test_node_type():
    assert isinstance(
        DiscriminatedNodeType.model_validate({"$formkit": "text"}).root, TextNode
    )
    assert isinstance(
        DiscriminatedNodeType.model_validate({"$formkit": "textarea"}).root,
        TextAreaNode,
    )


def test_group_disc():
    schema_in = {
        "$formkit": "group",
        "children": [{"$formkit": "text", "class": "red"}],
    }
    group = DiscriminatedNodeType.model_validate(schema_in)
    assert isinstance(group.root, GroupNode)
    assert isinstance(group.root.children[0], TextNode)
    assert group.root.children[0].additional_props == {"class": "red"}

    # When we do `group.model_dump` we get an error!
    schema_out = group.root.model_dump(by_alias=True, exclude_none=True)
    assert schema_in == schema_out


def test_group_disc_again():
    g = GroupNode()
    d = DiscriminatedNodeType(root=g)
    d.model_dump(by_alias=True, exclude_none=True)

    t = TextNode()
    g = GroupNode(children=[t])
    d = DiscriminatedNodeType(root=g)
    d.model_dump(by_alias=True, exclude_none=True)

    t = TextNode(additional_props={"class": "red"})
    g = GroupNode(children=[t])
    d = DiscriminatedNodeType(root=g)
    assert isinstance(d.root, GroupNode)
    assert isinstance(d.root.children[0], TextNode)
    assert d.root.children[0].additional_props == {"class": "red"}
    d.model_dump(by_alias=True, exclude_none=True)


def test_element():
    schema_in = {
        "$el": "button",
        "attrs": {
            "class": "disabled:hidden cursor-pointer flex items-center justify-center flex-row-reverse h-[50px] rounded-2.5xl px-4 w-full bg-white border-2 border-solid border-emerald-600 text-zinc-900 hover:bg-emerald-600 hover:text-white font-bold text-base",
            "data-index": "$index",
            "data-repeaterid": "$id",
            "onClick": "$attrs.removeAction",
        },
        "children": ["$attrs.removeLabel"],
        "if": "$value.length > 1",
    }

    group = DiscriminatedNodeType.model_validate(schema_in)
    assert group.model_dump(by_alias=True, exclude_none=True) == schema_in


def test_conditional():
    """
    Part of CFM 4
    """
    datepicker = {
        "$formkit": "datepicker",
        "_currentDate": "$getCurrentDate",
        "calendarIcon": "calendar",
        "format": "DD/MM/YYYY",
        "id": "date",
        "key": "date",
        "label": '$gettext("Date")',
        "name": "date",
        "nextIcon": "angleRight",
        "prevIcon": "angleLeft",
        "sectionsSchema": {
            "day": {
                "children": [
                    "$day.getDate()",
                    {
                        "children": [
                            {
                                "children": [
                                    {
                                        "$el": "div",
                                        "attrs": {"class": "formkit-day-highlight"},
                                        "if": "$attrs._currentDate().year === $day.getFullYear()",
                                    }
                                ],
                                "if": "$attrs._currentDate().month === $day.getMonth()",
                            }
                        ],
                        "if": "$attrs._currentDate().day === $day.getDate()",
                    },
                ]
            }
        },
    }

    group = DiscriminatedNodeType.model_validate(datepicker)
    assert group.model_dump(by_alias=True, exclude_none=True) == datepicker


simple_group = {
    "$formkit": "group",
    "children": [
        {
            "$formkit": "text",
            "key": "name",
            "label": "Name",
            "placeholder": "Enter your name",
        },
        {
            "$formkit": "text",
            "key": "email",
            "label": "Email",
            "placeholder": "Enter your email",
        },
    ],
}

uuid_schema = {"$formkit": "uuid", "name": "uuid", "readonly": True}


tel = {
    "$formkit": "tel",
    "label": '$gettext("Phone number")',
    "maxLength": 8,
    "name": "phone_number",
    "validation": "number|length:8,8",
}

sf_repeater = {
    "$formkit": "repeater",
    "addLabel": '$gettext("Add another member")',
    "children": [
        {
            "$el": "div",
            "attrs": {
                "class": "rounded-full px-5 py-2 bg-zinc-400 text-lg font-bold mb-5"
            },
            "children": [
                {"$el": "span", "children": ["$: ($index + 1)"]},
                " Suku facilitator",
            ],
        },
        {"$formkit": "uuid", "name": "uuid", "readonly": True},
        #   {
        #    "$formkit": "select",
        #    "label": "$gettext(\"Round\")",
        #    "name": "round",
        #    "options":  "$ida(electionround)",
        #    "placeholder": "$gettext(\"Please select\")"
        #   },
        #   {
        #    "$formkit": "select",
        #    "label": "$gettext(\"Position\")",
        #    "name": "position",
        #    "options": "$ida(teamposition, \"group_id=2\")",
        #    "placeholder": "$gettext(\"Please select\")"
        #   },
        #   {
        #    "$formkit": "text",
        #    "label": "$gettext(\"Name\")",
        #    "name": "name",
        #    "placeholder": "$gettext(\"Please enter\")"
        #   },
        #   {
        #    "$formkit": "select",
        #    "label": "$gettext(\"Gender\")",
        #    "name": "gender",
        #    "options": "$ida(gender)",
        #    "placeholder": "$gettext(\"Please select\")"
        #   },
        #   {
        #    "$formkit": "select",
        #    "label": "$gettext(\"Person with a disability\")",
        #    "name": "person_with_disability",
        #    "options": "$ida(yesno)",
        #    "placeholder": "$gettext(\"Please select\")"
        #   },
        #   {
        #    "$formkit": "tel",
        #    "label": "$gettext(\"Phone number\")",
        #    "maxLength": 8,
        #    "name": "phone_number",
        #    "validation": "number|length:8,8"
        #   },
        #   {
        #    "$formkit": "date",
        #    "label": "$gettext(\"Date of exit from the committee\")",
        #    "name": "date_exit_committee"
        #   },
        #   {
        #    "$formkit": "text",
        #    "label": "$gettext(\"Reason for exit\")",
        #    "name": "exit_details"
        #   },
        #   {
        #    "$formkit": "select",
        #    "label": "$gettext(\"Is active?\")",
        #    "name": "active_status",
        #    "options": "$ida(yesno)",
        #    "value": "1"
        #   }
    ],
    "downControl": False,
    "id": "repeaterSukus",
    "itemClass": "repeater-children-index",
    "itemsClass": "repeater",
    "max": 2,
    "min": 1,
    "name": "repeaterSukus",
    "removeAction": "$repeaterRemoveAction",
    "removeLabel": '$gettext("Remove")',
    "sectionsSchema": {
        "remove": {
            "children": [
                {
                    "$el": "button",
                    "attrs": {
                        "class": "disabled:hidden cursor-pointer flex items-center justify-center flex-row-reverse h-[50px] rounded-2.5xl px-4 w-full bg-white border-2 border-solid border-emerald-600 text-zinc-900 hover:bg-emerald-600 hover:text-white font-bold text-base",
                        "data-index": "$index",
                        "data-repeaterid": "$id",
                        "onClick": "$attrs.removeAction",
                    },
                    "children": ["$attrs.removeLabel"],
                    "if": "$value.length > 1",
                }
            ]
        }
    },
    "upControl": False,
    "validationRules": "validateSukuFacilitators",
}


sf_41_datpicker = {
    "$formkit": "datepicker",
    "_currentDate": "$getCurrentDate",
    "calendarIcon": "calendar",
    "format": "DD/MM/YYYY",
    "id": "date",
    "key": "date",
    "label": '$gettext("Date")',
    "name": "date",
    "nextIcon": "angleRight",
    "prevIcon": "angleLeft",
    "sectionsSchema": {
        "day": {
            "children": [
                "$day.getDate()",
                {
                    "children": [
                        {
                            "children": [
                                {
                                    "$el": "div",
                                    "attrs": {"class": "formkit-day-highlight"},
                                    "if": "$attrs._currentDate().year === $day.getFullYear()",
                                }
                            ],
                            "if": "$attrs._currentDate().month === $day.getMonth()",
                        }
                    ],
                    "if": "$attrs._currentDate().day === $day.getDate()",
                },
            ]
        }
    },
}

sf_41_district = {
    "$formkit": "select",
    "id": "district",
    "key": "district",
    "label": "$gettext(Municipality)",
    "name": "district",
    "options": "$getLocations()",
}

sf_41_locations = {
    "$formkit": "select",
    "id": "administrative_post",
    "if": "$get(district).value",
    "key": "administrative_post",
    "label": '$gettext("Administrative Post")',
    "name": "administrative_post",
    "options": "$getLocations($get(district).value)",
}

af_41_sucu = {
    "$formkit": "select",
    "id": "suco",
    "if": "$get(administrative_post).value",
    "key": "suco",
    "label": "$gettext(Suco)",
    "name": "suco",
    "options": "$getLocations($get(district).value, $get(administrative_post).value)",
}
sf_41_activityname = {
    "$formkit": "select",
    "id": "activity",
    "key": "activity",
    "label": '$gettext("Activity name")',
    "name": "activity",
    "options": "$ida(cycle)",
    "placeholder": '$gettext("Please select")',
}
sf_41_meeting = {
    "$formkit": "dropdown",
    "key": "meeting_objective",
    "label": '$gettext("Meeting objective")',
    "name": "meeting_objective",
    "options": ["First accountability meeting", "Final accountability meeting2"],
    "selectIcon": "angleDown",
}

repeater = {
    "$formkit": "repeater",
    "addLabel": '$gettext("Add project")',
}

repeater_2 = {
    "$formkit": "repeater",
    "children": [
        {
            "$formkit": "repeater",
        },
        {
            "$formkit": "repeater",
            "children": [{"$formkit": "repeater", "children": [{"$formkit": "text"}]}],
        },
    ],
}

div_el = {
    "$el": "div",
    "attrs": {"class": "rounded-full px-5 py-2 bg-zinc-400 text-lg font-bold mb-5"},
    "children": ["Output ", {"$el": "span", "children": ["$: ($index + 1)"]}],
}


@pytest.mark.parametrize(
    "schema",
    [
        simple_group,
        uuid_schema,
        tel,
        sf_repeater,
        sf_41_activityname,
        sf_41_datpicker,
        sf_41_district,
        sf_41_locations,
        af_41_sucu,
        sf_41_meeting,
        repeater,
        repeater_2,
        div_el,
    ],
)
def test_param_schemas(schema: dict[str, Any] | dict[str, str]):
    model_validated = DiscriminatedNodeType.model_validate(schema)

    # We get strange things happening
    schema_out = model_validated.root.model_dump(by_alias=True, exclude_none=True)
    assert schema_out == schema


def test_el():
    div_el = {
        "$el": "div",
        "attrs": {"class": "rounded-full px-5 py-2 bg-zinc-400 text-lg font-bold mb-5"},
        "children": ["Output ", {"$el": "span", "children": ["$: ($index + 1)"]}],
    }

    model_validated = DiscriminatedNodeType.model_validate(div_el)
    # We get strange things happening
    schema_out = model_validated.model_dump(by_alias=True, exclude_none=True)
    schema_are_same(schema_out, div_el)


@pytest.mark.django_db
@pytest.mark.parametrize(
    "schema",
    [
        simple_group,
        uuid_schema,
        tel,
        sf_repeater,
        sf_41_activityname,
        sf_41_datpicker,
        sf_41_district,
        sf_41_locations,
        af_41_sucu,
        sf_41_meeting,
        repeater,
        repeater_2,
        div_el,
    ],
)
def test_roundtrip_on_database(schema: dict):
    m = DiscriminatedNodeType.model_validate(schema)
    node_in_the_db = list(models.FormKitSchemaNode.from_pydantic(m.root))[0]
    schema_from_db: FormKitNode = node_in_the_db.to_pydantic(
        recursive=True, options=True
    )

    schema_out = schema_from_db.model_dump(by_alias=True, exclude_none=True)

    DiscriminatedNodeType.model_validate(node_in_the_db.get_node_values())

    schema_are_same(schema_out, schema)


def test_formkit_value_on_children():
    """
    This is an error case where "$formkit" is not correctly set on "child" nodes
    """
    t = TextNode()
    g = GroupNode(children=[t])
    f = FormKitNode(root=g)
    value = f.model_dump(by_alias=True, exclude_none=True, exclude_defaults=False)

    assert t.formkit == "text"
    assert t.node_type == "formkit"
    assert f.root.children[0].model_dump(by_alias=True, exclude_none=True) == {
        "$formkit": "text"
    }
    assert f.root.children[0].formkit == "text"
    assert "$formkit" in value["children"][0]
    assert value["children"][0]["$formkit"] == "text"


def test_repeater():
    r = RepeaterNode()
    t = TextNode()
    r.children = [t]
    assert r.model_dump(by_alias=True, exclude_none=True)


def test_repeater_prop():
    r = RepeaterNode(upControl=False)
    assert r.model_dump(by_alias=True, exclude_none=True)
