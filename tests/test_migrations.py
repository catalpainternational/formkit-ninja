"""
Tests for data migration backward compatibility.

Verifies that existing data with properties in additional_props
is correctly promoted to dedicated model fields during migrations.
"""

import importlib

import pytest
from django.apps import apps

from formkit_ninja import models


@pytest.mark.django_db
def test_migrate_icon_title_from_additional_props():
    """
    Test migration 0028: icon and title promotion from additional_props.
    """
    # Import the migration module directly
    migration_0028 = importlib.import_module("formkit_ninja.migrations.0028_migrate_additional_props")

    # Create node with old format (properties in additional_props)
    node = models.FormKitSchemaNode.objects.create(
        node_type="$formkit",
        node={"$formkit": "text", "name": "test"},
        additional_props={"icon": "star", "title": "Test Title", "customProp": "keep me"},
    )

    # Run migration
    migration_0028.forward(apps, None)

    # Verify fields promoted
    node.refresh_from_db()
    assert node.icon == "star"
    assert node.title == "Test Title"

    # Verify promoted fields removed from additional_props
    assert "icon" not in node.additional_props
    assert "title" not in node.additional_props

    # Verify other props preserved
    assert node.additional_props["customProp"] == "keep me"


@pytest.mark.django_db
def test_migrate_readonly_sections_min_from_additional_props():
    """
    Test migration 0030: readonly, sectionsSchema, min promotion from additional_props.
    Tests bool string handling.
    """
    # Import the migration module directly
    migration_0030 = importlib.import_module("formkit_ninja.migrations.0030_migrate_more_props")

    # Create nodes with data ONLY in additional_props (simulating old data)
    # We bypass the model's save() auto-promotion by using update()
    node1 = models.FormKitSchemaNode.objects.create(
        node_type="$formkit",
        node={"$formkit": "text"},
    )
    models.FormKitSchemaNode.objects.filter(id=node1.id).update(
        additional_props={
            "readonly": "true",  # String format in DB
            "min": 5,
            "sectionsSchema": {"section1": "value1"},
        }
    )

    node2 = models.FormKitSchemaNode.objects.create(
        node_type="$formkit",
        node={"$formkit": "text"},
    )
    models.FormKitSchemaNode.objects.filter(id=node2.id).update(
        additional_props={
            "readonly": True,  # Bool format in DB
            "min": "10",
        }
    )

    # Run migration
    migration_0030.forward(apps, None)

    # Verify node1
    node1.refresh_from_db()
    assert node1.readonly is True  # String "true" → bool True
    assert node1.min == "5"  # Converted to string
    assert node1.sections_schema == {"section1": "value1"}
    assert "readonly" not in node1.additional_props
    assert "min" not in node1.additional_props
    assert "sectionsSchema" not in node1.additional_props

    # Verify node2
    node2.refresh_from_db()
    assert node2.readonly is True  # Bool True stays True
    assert node2.min == "10"


@pytest.mark.django_db
def test_migrate_repeater_props_from_additional_props():
    """
    Test migration 0032: repeater properties promotion from additional_props.
    Tests mixed bool formats.
    """
    # Import the migration module directly
    migration_0032 = importlib.import_module("formkit_ninja.migrations.0032_migrate_repeater_props")

    # Create repeater with data ONLY in additional_props (simulating old data)
    node = models.FormKitSchemaNode.objects.create(
        node_type="$formkit",
        node={"$formkit": "repeater", "name": "testRepeater"},
    )
    models.FormKitSchemaNode.objects.filter(id=node.id).update(
        additional_props={
            "addLabel": "Add Item",
            "upControl": "true",  # String true in DB
            "downControl": False,  # Bool false in DB
            "step": 1,
            "itemClass": "custom-class",  # Should stay in additional_props
        }
    )

    # Run migration
    migration_0032.forward(apps, None)

    # Verify promoted fields
    node.refresh_from_db()
    assert node.add_label == "Add Item"
    assert node.up_control is True  # String "true" → bool True
    assert node.down_control is False  # Bool False stays False
    assert node.step == "1"  # Converted to string

    # Verify promoted fields removed from additional_props
    assert "addLabel" not in node.additional_props
    assert "upControl" not in node.additional_props
    assert "downControl" not in node.additional_props
    assert "step" not in node.additional_props

    # Verify non-promoted props preserved
    assert node.additional_props["itemClass"] == "custom-class"


@pytest.mark.django_db
def test_migration_edge_case_bool_strings():
    """
    Test that migration handles various bool string representations.
    """
    # Import the migration module directly
    migration_0032 = importlib.import_module("formkit_ninja.migrations.0032_migrate_repeater_props")

    # Create with string "false" in additional_props
    node1 = models.FormKitSchemaNode.objects.create(
        node_type="$formkit",
        node={"$formkit": "repeater"},
    )
    models.FormKitSchemaNode.objects.filter(id=node1.id).update(
        additional_props={"upControl": "false", "downControl": "false"}
    )

    migration_0032.forward(apps, None)
    node1.refresh_from_db()
    assert node1.up_control is False
    assert node1.down_control is False


@pytest.mark.django_db
def test_migration_preserves_non_dict_additional_props():
    """
    Test that migration safely handles nodes with non-dict additional_props.
    """
    # Import the migration module directly
    migration_0028 = importlib.import_module("formkit_ninja.migrations.0028_migrate_additional_props")

    # Create node with None additional_props
    node1 = models.FormKitSchemaNode.objects.create(
        node_type="$formkit", node={"$formkit": "text"}, additional_props=None
    )

    # Create node with empty additional_props
    node2 = models.FormKitSchemaNode.objects.create(
        node_type="$formkit", node={"$formkit": "text"}, additional_props={}
    )

    # Run migration - should not crash
    migration_0028.forward(apps, None)

    # Verify nodes unchanged
    node1.refresh_from_db()
    node2.refresh_from_db()
    assert node1.additional_props is None
    assert node2.additional_props == {}


@pytest.mark.django_db
def test_migration_handles_missing_fields():
    """
    Test that migration handles nodes that only have some of the promoted fields.
    """
    # Import the migration module directly
    migration_0032 = importlib.import_module("formkit_ninja.migrations.0032_migrate_repeater_props")

    # Create node with only some repeater props in additional_props
    node = models.FormKitSchemaNode.objects.create(
        node_type="$formkit",
        node={"$formkit": "repeater"},
    )
    models.FormKitSchemaNode.objects.filter(id=node.id).update(
        additional_props={"addLabel": "Add", "customField": "value"}
        # Missing upControl, downControl, step
    )

    migration_0032.forward(apps, None)

    # Verify only present field promoted
    node.refresh_from_db()
    assert node.add_label == "Add"
    # up_control and down_control have defaults of True, not None
    assert node.up_control is True  # Model default
    assert node.down_control is True  # Model default
    assert "addLabel" not in node.additional_props
    assert node.additional_props["customField"] == "value"
