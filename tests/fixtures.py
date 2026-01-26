import pytest

from formkit_ninja import models
from formkit_ninja.schemas import Schemas
from tests.factories import (
    AutocompleteNodeFactory,
    ConditionalNodeFactory,
    DatepickerNodeFactory,
    DropdownNodeFactory,
    ElementNodeFactory,
    FormKitSchemaFactory,
    GroupNodeFactory,
    NumberNodeFactory,
    OptionFactory,
    OptionGroupFactory,
    RadioNodeFactory,
    RepeaterNodeFactory,
    SelectNodeFactory,
    TextNodeFactory,
)

"""
These are the forms used in Partisipa
To recreate, from the Partisipa project
(note we will deprecate 'ts' type form schemas soon)

from formkit_python_sync.get_schemas import _run_tsx
import tempfile
import json
for form_name, form_defn in _run_tsx().items():
     import tempfile
     with tempfile.NamedTemporaryFile(prefix=form_name, delete=False, mode='w') as o:
         o.write(json.dumps(form_defn))
         print(o.name)


"""

schemas = Schemas()


@pytest.fixture
def CFM_12_FF_12():
    return schemas.as_json("CFM_12_FF_12")


@pytest.fixture
def CFM_2_FF_4():
    return schemas.as_json("CFM_2_FF_4")


@pytest.fixture
def FF_14():
    return schemas.as_json("FF_14")


@pytest.fixture
def POM_1():
    return schemas.as_json("POM_1")


@pytest.fixture
def SF_1_1():
    return schemas.as_json("SF_1_1")


@pytest.fixture
def SF_1_2():
    return schemas.as_json("SF_1_2")


@pytest.fixture
def SF_1_3():
    return schemas.as_json("SF_1_3")


@pytest.fixture
def SF_2_3():
    return schemas.as_json("SF_2_3")


@pytest.fixture
def SF_4_1():
    return schemas.as_json("SF_4_1")


@pytest.fixture
def SF_4_2():
    return schemas.as_json("SF_4_2")


@pytest.fixture
def SF_6_2():
    return schemas.as_json("SF_6_2")


@pytest.fixture
def TF_13_2_1():
    return schemas.as_json("TF_13_2_1")


@pytest.fixture
def TF_6_1_1():
    """Load TF_6_1_1 schema from database."""
    return schemas.as_json("TF_6_1_1")


@pytest.fixture
def TF_6_1_1_from_factory(db):
    """
    Create TF_6_1_1 schema structure using factoryboy.

    This fixture recreates the TF_6_1_1 form structure with:
    - Root group (TF_6_1_1)
    - Nested groups (meetinginformation, projecttimeframe, projectdetails,
      projectbeneficiaries, projectoutput)
    - Various field types (select, number, datepicker, uuid)
    - Repeater with nested children
    - Conditional logic examples
    """
    from formkit_ninja import models

    # Root group
    root = GroupNodeFactory(
        label="TF_6_1_1",
        node={"$formkit": "group", "name": "TF_6_1_1"},
    )

    # meetinginformation group
    meeting_info = GroupNodeFactory(
        label="meetinginformation",
        icon="las la-map-marked-alt",
        title="Location",
        node={
            "$formkit": "group",
            "id": "meetinginformation",
            "name": "meetinginformation",
            "icon": "las la-map-marked-alt",
            "title": "Location",
        },
    )
    models.NodeChildren.objects.create(parent=root, child=meeting_info, order=0)

    # Select fields in meetinginformation
    district = SelectNodeFactory(
        label="$gettext(Municipality)",
        option_group=None,
        node={
            "$formkit": "select",
            "id": "district",
            "key": "district",
            "name": "district",
            "label": "$gettext(Municipality)",
            "options": "$getLocations()",
        },
    )
    admin_post = SelectNodeFactory(
        label='$gettext("Administrative Post")',
        option_group=None,
        node={
            "$formkit": "select",
            "name": "administrative_post",
            "label": '$gettext("Administrative Post")',
            "options": "$getLocations()",
        },
    )
    suco = SelectNodeFactory(
        label="$gettext(Suco)",
        option_group=None,
        node={
            "$formkit": "select",
            "name": "suco",
            "label": "$gettext(Suco)",
            "options": "$getLocations()",
        },
    )
    aldeia = SelectNodeFactory(
        label="$gettext(Aldeia)",
        option_group=None,
        node={
            "$formkit": "select",
            "name": "aldeia",
            "label": "$gettext(Aldeia)",
            "options": "$getLocations()",
        },
    )
    models.NodeChildren.objects.create(parent=meeting_info, child=district, order=0)
    models.NodeChildren.objects.create(parent=meeting_info, child=admin_post, order=1)
    models.NodeChildren.objects.create(parent=meeting_info, child=suco, order=2)
    models.NodeChildren.objects.create(parent=meeting_info, child=aldeia, order=3)

    # projecttimeframe group
    project_timeframe = GroupNodeFactory(
        label="projecttimeframe",
        node={"$formkit": "group", "name": "projecttimeframe", "label": "projecttimeframe"},
    )
    models.NodeChildren.objects.create(parent=root, child=project_timeframe, order=1)

    # Datepicker fields
    date_start = DatepickerNodeFactory(
        label='$gettext("Date start estimated")',
        node={
            "$formkit": "datepicker",
            "name": "date_start_estimated",
            "label": '$gettext("Date start estimated")',
            "format": "DD/MM/YY",
        },
    )
    date_finish = DatepickerNodeFactory(
        label='$gettext("Date finish estimated")',
        node={
            "$formkit": "datepicker",
            "name": "date_finish_estimated",
            "label": '$gettext("Date finish estimated")',
            "format": "DD/MM/YY",
        },
    )
    models.NodeChildren.objects.create(parent=project_timeframe, child=date_start, order=0)
    models.NodeChildren.objects.create(parent=project_timeframe, child=date_finish, order=1)

    # projectdetails group
    project_details = GroupNodeFactory(
        label="projectdetails",
        node={"$formkit": "group", "name": "projectdetails", "label": "projectdetails"},
    )
    models.NodeChildren.objects.create(parent=root, child=project_details, order=2)

    # Fields in projectdetails
    project_status = SelectNodeFactory(
        label="project_status",
        option_group=None,
        node={"$formkit": "select", "name": "project_status", "label": "project_status"},
    )
    project_sector = SelectNodeFactory(
        label='$gettext("Project Sector")',
        option_group=None,
        node={
            "$formkit": "select",
            "name": "project_sector",
            "label": '$gettext("Project Sector")',
            "options": "$ida(activity)",
        },
    )
    project_subsector = SelectNodeFactory(
        label='$gettext("Project Sub-Sector")',
        option_group=None,
        node={
            "$formkit": "select",
            "name": "project_subsector",
            "label": '$gettext("Project Sub-Sector")',
            "if": "$get(project_sector).value",
            "options": "$ida(subsector)",
        },
    )
    project_name = SelectNodeFactory(
        label='$gettext("Project name")',
        option_group=None,
        node={
            "$formkit": "select",
            "name": "project_name",
            "label": '$gettext("Project name")',
        },
    )
    objective = SelectNodeFactory(
        label='$gettext("Objective")',
        option_group=None,
        node={
            "$formkit": "select",
            "name": "objective",
            "label": '$gettext("Objective")',
        },
    )
    gps_lat = NumberNodeFactory(
        label='$gettext("GPS Coordinate - LATITUDE")',
        node={
            "$formkit": "number",
            "name": "gps_latitude",
            "label": '$gettext("GPS Coordinate - LATITUDE")',
        },
    )
    gps_lon = NumberNodeFactory(
        label='$gettext("GPS Coordinate - LONGITUDE")',
        node={
            "$formkit": "number",
            "name": "gps_longitude",
            "label": '$gettext("GPS Coordinate - LONGITUDE")',
        },
    )
    women_priority = SelectNodeFactory(
        label='$gettext("Is a women priority?")',
        option_group=None,
        node={
            "$formkit": "select",
            "name": "is_women_priority",
            "label": '$gettext("Is a women priority?")',
        },
    )
    models.NodeChildren.objects.create(parent=project_details, child=project_status, order=0)
    models.NodeChildren.objects.create(parent=project_details, child=project_sector, order=1)
    models.NodeChildren.objects.create(parent=project_details, child=project_subsector, order=2)
    models.NodeChildren.objects.create(parent=project_details, child=project_name, order=3)
    models.NodeChildren.objects.create(parent=project_details, child=objective, order=4)
    models.NodeChildren.objects.create(parent=project_details, child=gps_lat, order=5)
    models.NodeChildren.objects.create(parent=project_details, child=gps_lon, order=6)
    models.NodeChildren.objects.create(parent=project_details, child=women_priority, order=7)

    # projectbeneficiaries group
    project_beneficiaries = GroupNodeFactory(
        label="projectbeneficiaries",
        node={
            "$formkit": "group",
            "name": "projectbeneficiaries",
            "label": "projectbeneficiaries",
        },
    )
    models.NodeChildren.objects.create(parent=root, child=project_beneficiaries, order=3)

    # Number fields in projectbeneficiaries
    num_households = NumberNodeFactory(
        label='$gettext("Number of households")',
        node={
            "$formkit": "number",
            "name": "number_of_households",
            "label": '$gettext("Number of households")',
        },
    )
    num_women = NumberNodeFactory(
        label='$gettext("No. of women")',
        node={"$formkit": "number", "name": "no_of_women", "label": '$gettext("No. of women")'},
    )
    num_men = NumberNodeFactory(
        label='$gettext("No. of men")',
        node={"$formkit": "number", "name": "no_of_men", "label": '$gettext("No. of men")'},
    )
    disability_male = NumberNodeFactory(
        label='$gettext("No. of people with disability - male")',
        node={
            "$formkit": "number",
            "name": "disability_male",
            "label": '$gettext("No. of people with disability - male")',
        },
    )
    disability_female = NumberNodeFactory(
        label='$gettext("No. of people with disability - female")',
        node={
            "$formkit": "number",
            "name": "disability_female",
            "label": '$gettext("No. of people with disability - female")',
        },
    )
    models.NodeChildren.objects.create(parent=project_beneficiaries, child=num_households, order=0)
    models.NodeChildren.objects.create(parent=project_beneficiaries, child=num_women, order=1)
    models.NodeChildren.objects.create(parent=project_beneficiaries, child=num_men, order=2)
    models.NodeChildren.objects.create(parent=project_beneficiaries, child=disability_male, order=3)
    models.NodeChildren.objects.create(parent=project_beneficiaries, child=disability_female, order=4)

    # projectoutput group
    project_output = GroupNodeFactory(
        label="projectoutput",
        node={"$formkit": "group", "name": "projectoutput", "label": "projectoutput"},
    )
    models.NodeChildren.objects.create(parent=root, child=project_output, order=4)

    # Repeater in projectoutput
    repeater = RepeaterNodeFactory(
        label="repeaterProjectOutput",
        node={
            "$formkit": "repeater",
            "name": "repeaterProjectOutput",
            "label": "repeaterProjectOutput",
        },
    )
    models.NodeChildren.objects.create(parent=project_output, child=repeater, order=0)

    # UUID field in repeater
    from tests.factories import FormKitSchemaNodeFactory

    uuid_field = FormKitSchemaNodeFactory(
        node_type="$formkit",
        label="uuid",
        node={"$formkit": "uuid", "name": "uuid", "label": "uuid"},
    )
    models.NodeChildren.objects.create(parent=repeater, child=uuid_field, order=0)

    # Element node in repeater
    element_node = ElementNodeFactory(
        node_type="$el",
        text_content="Output ",
        node={"$el": "div", "children": "Output "},
    )
    models.NodeChildren.objects.create(parent=repeater, child=element_node, order=1)

    return root


@pytest.fixture
def el_priority():
    """
    This represents a more complicated "el" element type
    """
    return {
        "$el": "div",
        "children": ["Priority ", {"$el": "span", "attrs": {"class": "ml-1"}, "children": ["$: ($index + 1)"]}],
        "attrs": {"class": "rounded-full px-5 py-2 bg-zinc-400 text-lg font-bold mb-5"},
    }


@pytest.fixture
def simple_text_node():
    return {"$el": "span", "children": "Priority"}


@pytest.fixture
def formkit_text_node():
    return {
        "key": "activity_type",
        "id": "activity_type",
        "name": "activity_type",
        "label": "$pgettext('activity_type', 'Meeting or Training')",
        "$formkit": "select",
        "placeholder": '$gettext("Please select")',
        "class": "red",
        "options": [{"value": "1", "label": "Training"}, {"value": "2", "label": "Meeting"}],
    }


# Factory-based fixtures for complex node types


@pytest.fixture
def simple_repeater_node(db):
    """Simple repeater node with basic properties"""
    return RepeaterNodeFactory(
        label="priorities",
        add_label="Add another priority",
        up_control=False,
        down_control=False,
        node={
            "$formkit": "repeater",
            "name": "priorities",
            "label": "priorities",
            "addLabel": "Add another priority",
            "upControl": False,
            "downControl": False,
        },
    )


@pytest.fixture
def repeater_with_children(db):
    """Repeater with nested element child"""
    repeater = RepeaterNodeFactory(
        label="priorities",
        add_label="Add another priority",
        up_control=False,
        down_control=False,
    )
    child_element = ElementNodeFactory(
        node_type="$el",
        text_content="Priority 1",
        node={
            "$el": "div",
            "attrs": {
                "class": (
                    "mb-5 bg-zinc-400 text-base text-zinc-900 h-[50px] px-5 flex items-center rounded-full font-bold"
                )
            },
            "children": "Priority 1",
        },
    )
    models.NodeChildren.objects.create(parent=repeater, child=child_element, order=0)
    return repeater


@pytest.fixture
def repeater_with_all_properties(db):
    """Repeater with all properties set"""
    return RepeaterNodeFactory(
        label="test_repeater",
        add_label="Add Item",
        up_control=True,
        down_control=False,
        min="1",
        node={
            "$formkit": "repeater",
            "name": "test_repeater",
            "label": "test_repeater",
            "addLabel": "Add Item",
            "upControl": True,
            "downControl": False,
            "min": 1,
        },
        additional_props={"itemClass": "my-item-class", "itemsClass": "my-items-class"},
    )


@pytest.fixture
def simple_group_node(db):
    """Simple group node"""
    return GroupNodeFactory(
        label="newgroup",
        node={"$formkit": "group", "name": "newgroup", "label": "newgroup"},
    )


@pytest.fixture
def group_with_icon_title(db):
    """Group with icon and title"""
    return GroupNodeFactory(
        label="meetingInformation",
        icon="las la-map-marked-alt",
        title="Radio Buttons",
        node={
            "$formkit": "group",
            "name": "meetingInformation",
            "label": "meetingInformation",
            "icon": "las la-map-marked-alt",
            "title": "Radio Buttons",
        },
    )


@pytest.fixture
def group_with_children(db):
    """Group with nested children nodes"""
    group = GroupNodeFactory(
        label="meetingInformation",
        icon="las la-map-marked-alt",
        title="Radio Buttons",
    )
    # Create child radio nodes
    sector = RadioNodeFactory(
        label="Sector",
        node={
            "$formkit": "radio",
            "key": "sector",
            "id": "sector_id",
            "name": "sector",
            "label": "$gettext(Sector)",
            "options": "$ida(sector)",
        },
    )
    subsector = ConditionalNodeFactory(
        label="Subsector",
        node={
            "$formkit": "radio",
            "key": "subsector",
            "if": "$get(sector_id).value",
            "id": "subsector_id",
            "name": "subsector",
            "label": "$gettext(Subsector)",
            "options": '$ida(subsector, "sector_id="+$get(sector_id).value)',
        },
    )
    models.NodeChildren.objects.create(parent=group, child=sector, order=0)
    models.NodeChildren.objects.create(parent=group, child=subsector, order=1)
    return group


@pytest.fixture
def conditional_node(db):
    """Node with conditional logic (if condition)"""
    return ConditionalNodeFactory(
        label="subsector",
        node={
            "$formkit": "text",
            "name": "subsector",
            "label": "subsector",
            "if": "$get(sector_id).value",
        },
    )


@pytest.fixture
def cascading_conditional_nodes(db):
    """Multiple nodes with cascading conditional logic"""
    sector = RadioNodeFactory(
        label="Sector",
        node={"$formkit": "radio", "name": "sector", "id": "sector_id", "label": "Sector"},
    )
    subsector = ConditionalNodeFactory(
        label="Subsector",
        node={
            "$formkit": "text",
            "name": "subsector",
            "id": "subsector_id",
            "label": "Subsector",
            "if": "$get(sector_id).value",
        },
    )
    output = ConditionalNodeFactory(
        label="Output",
        node={
            "$formkit": "text",
            "name": "output",
            "id": "output_id",
            "label": "Output",
            "if": "$get(subsector_id).value",
        },
    )
    return [sector, subsector, output]


@pytest.fixture
def dropdown_with_options(db):
    """Dropdown node with options"""
    option_group = OptionGroupFactory(group="units")
    OptionFactory(group=option_group, value="Km", order=0)
    OptionFactory(group=option_group, value="m3", order=1)
    OptionFactory(group=option_group, value="m2", order=2)
    OptionFactory(group=option_group, value="package", order=3)
    return DropdownNodeFactory(
        label="Unit",
        option_group=option_group,
        node={
            "$formkit": "dropdown",
            "name": "unit",
            "label": "Unit",
            "placeholder": "Please select",
            "selectIcon": "angleDown",
        },
    )


@pytest.fixture
def autocomplete_with_options(db):
    """Autocomplete node with options"""
    option_group = OptionGroupFactory(group="autocomplete_options")
    OptionFactory(group=option_group, value="option1", order=0)
    OptionFactory(group=option_group, value="option2", order=1)
    return AutocompleteNodeFactory(
        label="Autocomplete Field",
        option_group=option_group,
        node={
            "$formkit": "autocomplete",
            "name": "autocomplete_field",
            "label": "Autocomplete Field",
        },
    )


@pytest.fixture
def select_with_ida_options(db):
    """Select node with $ida() function call for options"""
    return SelectNodeFactory(
        label="Sector",
        option_group=None,
        node={
            "$formkit": "select",
            "key": "sector",
            "id": "sector_id",
            "name": "sector",
            "label": "$gettext(Sector)",
            "options": "$ida(sector)",
        },
    )


@pytest.fixture
def datepicker_node(db):
    """Datepicker node with basic properties"""
    return DatepickerNodeFactory(
        label="Date Field",
        node={
            "$formkit": "datepicker",
            "name": "date_field",
            "label": "Date Field",
            "format": "DD/MM/YY",
            "calendarIcon": "calendar",
        },
    )


@pytest.fixture
def datepicker_with_constraints(db):
    """Datepicker with min/max date sources and disabled days"""
    return DatepickerNodeFactory(
        label="Date Field",
        node={
            "$formkit": "datepicker",
            "name": "date_field",
            "label": "Date Field",
            "format": "DD/MM/YY",
            "calendarIcon": "calendar",
        },
        additional_props={
            "_minDateSource": "start_date",
            "_maxDateSource": "end_date",
            "disabledDays": "return true",
        },
    )


@pytest.fixture
def nested_group_repeater(db):
    """Group containing a repeater (complex nested structure)"""
    group = GroupNodeFactory(
        label="Infrastructure Fund",
        icon="fa fa-building",
        title="Infrastructure",
    )
    repeater = RepeaterNodeFactory(
        label="repeaterInfrastructureFund",
        add_label="Add Item",
        node={
            "$formkit": "repeater",
            "id": "repeaterInfrastructureFund",
            "name": "repeaterInfrastructureFund",
            "label": "repeaterInfrastructureFund",
            "addLabel": "Add Item",
        },
    )
    # Add text field as child of repeater
    text_field = TextNodeFactory(
        label="Item Name",
        node={"$formkit": "text", "name": "item_name", "label": "Item Name"},
    )
    models.NodeChildren.objects.create(parent=group, child=repeater, order=0)
    models.NodeChildren.objects.create(parent=repeater, child=text_field, order=0)
    return group


@pytest.fixture
def repeater_with_group(db):
    """Repeater containing a group (reverse nesting)"""
    repeater = RepeaterNodeFactory(
        label="Repeater with Groups",
        add_label="Add Group",
    )
    group = GroupNodeFactory(
        label="Nested Group",
        icon="fa fa-users",
        title="Group Title",
    )
    text_field = TextNodeFactory(
        label="Field in Group",
        node={"$formkit": "text", "name": "field_in_group", "label": "Field in Group"},
    )
    models.NodeChildren.objects.create(parent=repeater, child=group, order=0)
    models.NodeChildren.objects.create(parent=group, child=text_field, order=0)
    return repeater


@pytest.fixture
def multi_level_nested_with_conditionals(db):
    """Multi-level nesting with conditional logic"""
    # Top level group
    top_group = GroupNodeFactory(
        label="Top Level",
        icon="fa fa-home",
        title="Top Level Group",
    )
    # Conditional field at top level
    conditional_field = ConditionalNodeFactory(
        label="Conditional Field",
        node={
            "$formkit": "text",
            "name": "conditional_field",
            "label": "Conditional Field",
            "if": "$get(trigger_field).value",
        },
    )
    # Nested group
    nested_group = GroupNodeFactory(
        label="Nested Group",
        title="Nested",
    )
    # Repeater in nested group
    repeater = RepeaterNodeFactory(
        label="Nested Repeater",
    )
    # Field in repeater
    repeater_field = TextNodeFactory(
        label="Repeater Field",
        node={"$formkit": "text", "name": "repeater_field", "label": "Repeater Field"},
    )
    # Build hierarchy
    models.NodeChildren.objects.create(parent=top_group, child=conditional_field, order=0)
    models.NodeChildren.objects.create(parent=top_group, child=nested_group, order=1)
    models.NodeChildren.objects.create(parent=nested_group, child=repeater, order=0)
    models.NodeChildren.objects.create(parent=repeater, child=repeater_field, order=0)
    return top_group


@pytest.fixture
def example_schema_factory(db):
    """Factory fixture that creates a schema similar to EXAMPLE.json"""
    schema = FormKitSchemaFactory(label="EXAMPLE")
    # Create first group with radio buttons
    group1 = GroupNodeFactory(
        label="meetingInformation",
        icon="las la-map-marked-alt",
        title="Radio Buttons",
    )
    # Create radio nodes with conditional logic
    sector = RadioNodeFactory(
        label="Sector",
        node={
            "$formkit": "radio",
            "key": "sector",
            "id": "sector_id",
            "name": "sector",
            "label": "$gettext(Sector)",
            "options": "$ida(sector)",
        },
    )
    subsector = ConditionalNodeFactory(
        label="Subsector",
        node={
            "$formkit": "radio",
            "key": "subsector",
            "if": "$get(sector_id).value",
            "id": "subsector_id",
            "name": "subsector",
            "label": "$gettext(Subsector)",
            "options": '$ida(subsector, "sector_id="+$get(sector_id).value)',
        },
    )
    output = ConditionalNodeFactory(
        label="Output",
        node={
            "$formkit": "radio",
            "key": "output",
            "if": "$get(subsector_id).value",
            "id": "output_id",
            "name": "output",
            "label": "$gettext(output)",
            "options": '$ida(output, "subsector_id="+$get(subsector_id).value)',
        },
    )
    # Add children to group1
    models.NodeChildren.objects.create(parent=group1, child=sector, order=0)
    models.NodeChildren.objects.create(parent=group1, child=subsector, order=1)
    models.NodeChildren.objects.create(parent=group1, child=output, order=2)
    # Create second group with selects
    group2 = GroupNodeFactory(
        label="meetingInformation2",
        icon="las la-map-marked-alt",
        title="Dropdowns",
    )
    sector_select = SelectNodeFactory(
        label="Sector",
        node={
            "$formkit": "select",
            "key": "sector",
            "id": "sector_id_dropdown",
            "name": "sector",
            "label": "$gettext(Sector)",
            "options": "$ida(sector)",
        },
    )
    # Add to schema
    models.FormComponents.objects.create(schema=schema, node=group1, order=0, label="Group 1")
    models.FormComponents.objects.create(schema=schema, node=group2, order=1, label="Group 2")
    models.FormComponents.objects.create(schema=schema, node=sector_select, order=2, label="Sector Select")
    return schema
