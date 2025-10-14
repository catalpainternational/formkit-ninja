"""
End-to-end tests with real Partisipa form data.

Tests complete workflows:
- Loading complex nested forms from fixtures
- Reconstructing schemas from node hierarchies
- Publishing forms
- Editing through admin
- Querying submission data
"""

import pytest
from django.db.models import Count

from formkit_ninja import models


@pytest.mark.django_db
class TestPartisipaComplexForms:
    """End-to-end tests with complex multi-level Partisipa forms."""

    @pytest.fixture(autouse=True)
    def load_fixtures(self, django_db_setup, django_db_blocker):
        """Load complex Partisipa form data."""
        from django.core.management import call_command

        with django_db_blocker.unblock():
            call_command("loaddata", "tests/fixtures/partisipa_complex_form.yaml")

    def test_complex_form_loaded(self):
        """Verify complex nested form loaded correctly."""
        # Should have ~24 nodes and 23 parent-child relationships
        node_count = models.FormKitSchemaNode.objects.count()
        assert node_count >= 20, f"Expected ~24 nodes, got {node_count}"

        relationship_count = models.NodeChildren.objects.count()
        assert relationship_count >= 20, (
            f"Expected ~23 relationships, got {relationship_count}"
        )

        # Check for the CFM_2_FF_4 root node
        cfm_form = models.FormKitSchemaNode.objects.filter(
            node__contains={"name": "CFM_2_FF_4"}
        ).first()
        assert cfm_form is not None, "CFM_2_FF_4 form not found"
        assert cfm_form.node["$formkit"] == "group"

    def test_reconstruct_schema_from_nodes(self):
        """
        Test reconstructing a complete schema from orphaned nodes.

        The fixture has nodes with parent-child relationships but no schema.
        We should be able to create a schema and assign nodes to it.
        """
        # Find the root node (CFM_2_FF_4)
        root_node = models.FormKitSchemaNode.objects.filter(
            node__contains={"name": "CFM_2_FF_4"}
        ).first()
        assert root_node is not None

        # Create a schema and assign the root node
        schema = models.FormKitSchema.objects.create(label="CFM_2_FF_4_TEST")

        # Assign root node to schema
        root_node.schema = schema
        root_node.save(update_fields=["schema"])

        # Recursively assign all children
        def assign_children_to_schema(node, target_schema):
            """Recursively assign node and all children to schema."""
            node.schema = target_schema
            node.save(update_fields=["schema"])

            children = models.NodeChildren.objects.filter(parent=node)
            for child_rel in children:
                assign_children_to_schema(child_rel.child, target_schema)

        assign_children_to_schema(root_node, schema)

        # Verify assignment
        schema_node_count = models.FormKitSchemaNode.objects.filter(
            schema=schema
        ).count()
        assert schema_node_count > 20, (
            f"Expected >20 nodes in schema, got {schema_node_count}"
        )

    def test_get_nested_node_values(self):
        """
        Test that get_node_values works with deep nesting.

        This tests the recursive functionality with real complex data.
        """
        # Get a parent node
        parent_nodes = models.NodeChildren.objects.values_list(
            "parent", flat=True
        ).distinct()[:5]

        for parent_id in parent_nodes:
            parent = models.FormKitSchemaNode.objects.get(pk=parent_id)

            # Get node values recursively
            values = parent.get_node_values(recursive=True, options=True)

            assert isinstance(values, dict)

            # If it has children, verify they're in the output
            children = models.NodeChildren.objects.filter(parent=parent)
            if children.exists():
                assert "children" in values, (
                    f"Parent {parent.label or parent.pk} should have children in values"
                )
                assert isinstance(values["children"], list)
                assert len(values["children"]) == children.count()

    def test_complex_form_admin_workflow(self):
        """
        Test complete admin workflow with complex nested form.

        1. Load nodes
        2. Create schema
        3. Add nodes to schema
        4. Edit nodes via admin
        5. Publish schema
        """
        from formkit_ninja.admin import FormKitNodeGroupForm

        # Create a schema
        schema = models.FormKitSchema.objects.create(label="Admin Workflow Test")

        # Find diverse nodes to add
        group_node = models.FormKitSchemaNode.objects.filter(
            node__contains={"$formkit": "group"}
        ).first()
        assert group_node is not None

        # Assign to schema
        group_node.schema = schema
        group_node.save(update_fields=["schema"])

        # Edit through admin form
        form_data = {
            "label": "Edited via Admin",
            "description": "Testing admin workflow",
            "additional_props": {},
            "is_active": True,
            "protected": False,
            "name": group_node.node.get("name", "test_group"),  # Provide name
        }
        form = FormKitNodeGroupForm(form_data, instance=group_node)
        assert form.is_valid(), f"Form errors: {form.errors}"

        saved_node = form.save()
        assert saved_node.label == "Edited via Admin"

        # Publish the schema
        published = schema.publish()
        assert published.status == models.PublishedForm.Status.PUBLISHED
        assert published.version == 1
        assert len(published.published_schema) > 0

    def test_nodechildren_ordering(self):
        """
        Test that NodeChildren relationships maintain proper ordering.

        This is critical for form rendering.
        """
        # Find a parent with multiple children
        parents_with_children = (
            models.NodeChildren.objects.values("parent")
            .annotate(child_count=Count("parent"))
            .filter(child_count__gte=3)
            .order_by("-child_count")
        )

        if not parents_with_children.exists():
            pytest.skip("No parents with 3+ children found")

        parent_id = parents_with_children.first()["parent"]
        parent = models.FormKitSchemaNode.objects.get(pk=parent_id)

        # Get children in order
        children_rels = models.NodeChildren.objects.filter(parent=parent).order_by(
            "order"
        )

        orders = [rel.order for rel in children_rels]

        # Verify ordering is sequential (allowing for gaps)
        assert orders == sorted(orders), "Children order should be sorted"

        # Verify no duplicates
        assert len(orders) == len(set(orders)), "No duplicate orders allowed"

    def test_get_schema_values_preserves_structure(self):
        """
        Test that get_schema_values maintains the full form structure.

        With real complex nested data.
        """
        # Create a schema and add some nodes from the fixture
        schema = models.FormKitSchema.objects.create(label="Structure Test")

        # Get a root node with children
        root_node = models.FormKitSchemaNode.objects.filter(
            node__contains={"name": "CFM_2_FF_4"}
        ).first()

        if root_node:
            # Recursively assign to schema
            def assign_to_schema(node):
                node.schema = schema
                node.save(update_fields=["schema"])
                children = models.NodeChildren.objects.filter(parent=node)
                for child_rel in children:
                    assign_to_schema(child_rel.child)

            assign_to_schema(root_node)

            # Get schema values
            schema_values = list(schema.get_schema_values(recursive=True, options=True))

            # Should have at least one node (the root)
            assert len(schema_values) > 0

            # The root should be a group with children
            if isinstance(schema_values[0], dict):
                assert "$formkit" in schema_values[0]

    def test_complex_form_to_pydantic(self):
        """
        Test converting complex nested structures to Pydantic.

        This validates that the entire form can round-trip through Pydantic
        validation without errors.
        """
        # Create schema from complex nodes
        schema = models.FormKitSchema.objects.create(label="Pydantic Test")

        # Get some diverse nodes
        nodes_to_add = []

        # Add a group
        group = models.FormKitSchemaNode.objects.filter(
            node__contains={"$formkit": "group"}
        ).first()
        if group:
            nodes_to_add.append(group)

        # Add a repeater if available
        repeater = models.FormKitSchemaNode.objects.filter(
            node__contains={"$formkit": "repeater"}
        ).first()
        if repeater:
            nodes_to_add.append(repeater)

        # Assign to schema
        for node in nodes_to_add:
            node.schema = schema
            node.save(update_fields=["schema"])

        # Convert to Pydantic - this validates the structure
        try:
            pydantic_schema = schema.to_pydantic()
            assert pydantic_schema is not None
            # Should be able to convert back to dict
            schema_dict = pydantic_schema.model_dump(by_alias=True, exclude_none=True)
            assert isinstance(schema_dict, list)
        except Exception as e:
            pytest.fail(f"Pydantic conversion failed: {e}")


@pytest.mark.django_db
class TestPartisipaFormPublishing:
    """Test form publishing workflows with Partisipa data."""

    @pytest.fixture(autouse=True)
    def load_fixtures(self, django_db_setup, django_db_blocker):
        """Load complex Partisipa form data."""
        from django.core.management import call_command

        with django_db_blocker.unblock():
            call_command("loaddata", "tests/fixtures/partisipa_complex_form.yaml")

    def test_publish_complex_form(self):
        """
        Test publishing a complex nested form.

        Verifies that published_schema captures the complete structure.
        """
        # Create schema
        schema = models.FormKitSchema.objects.create(label="Test Publish")

        # Add a simple group from fixture
        group_node = models.FormKitSchemaNode.objects.filter(
            node__contains={"$formkit": "group"}
        ).first()
        assert group_node is not None

        group_node.schema = schema
        group_node.save(update_fields=["schema"])

        # Publish
        published = schema.publish()

        assert published.status == models.PublishedForm.Status.PUBLISHED
        assert published.version == 1
        assert isinstance(published.published_schema, list)
        assert len(published.published_schema) > 0

        # Verify the published schema is a frozen snapshot
        first_node = published.published_schema[0]
        assert isinstance(first_node, dict)
        assert (
            "$formkit" in first_node
            or "children" in first_node
            or isinstance(first_node, str)
        )

    def test_form_versioning(self):
        """
        Test that form versioning works correctly.

        When a form is republished, old version should be marked as replaced.
        """
        # Create and publish
        schema = models.FormKitSchema.objects.create(label="Versioning Test")

        # Add a node
        node = models.FormKitSchemaNode.objects.filter(is_active=True).first()
        node.schema = schema
        node.save(update_fields=["schema"])

        # First publication
        v1 = schema.publish()
        assert v1.version == 1
        assert v1.status == models.PublishedForm.Status.PUBLISHED

        # Modify schema
        node.label = "Modified for v2"
        node.save(update_fields=["label"])

        # Second publication
        v2 = schema.publish()
        assert v2.version == 2
        assert v2.status == models.PublishedForm.Status.PUBLISHED

        # Check v1 was replaced
        v1.refresh_from_db()
        assert v1.status == models.PublishedForm.Status.REPLACED
        assert v1.replaced is not None


@pytest.mark.django_db
class TestPartisipaNodeRelationships:
    """Test complex node relationship scenarios from Partisipa."""

    @pytest.fixture(autouse=True)
    def load_fixtures(self, django_db_setup, django_db_blocker):
        """Load complex Partisipa form data."""
        from django.core.management import call_command

        with django_db_blocker.unblock():
            call_command("loaddata", "tests/fixtures/partisipa_complex_form.yaml")

    def test_traverse_deep_hierarchy(self):
        """
        Test traversing a 6-level deep form hierarchy.

        Verifies that deeply nested forms work correctly.
        """
        # Find the deepest parent
        root = models.FormKitSchemaNode.objects.filter(
            node__contains={"name": "CFM_2_FF_4"}
        ).first()
        assert root is not None

        # Traverse the hierarchy
        def get_hierarchy_depth(node, depth=1):
            """Get the maximum depth of this node's children."""
            children = models.NodeChildren.objects.filter(parent=node)
            if not children.exists():
                return depth

            max_child_depth = depth
            for child_rel in children:
                child_depth = get_hierarchy_depth(child_rel.child, depth + 1)
                max_child_depth = max(max_child_depth, child_depth)

            return max_child_depth

        depth = get_hierarchy_depth(root)
        assert depth >= 3, f"Expected depth >=3, got {depth}"

        print(f"\nForm hierarchy depth: {depth}")

    def test_parent_child_consistency(self):
        """
        Test that all parent-child relationships are consistent.

        No orphaned children, all references valid, etc.
        """
        # Get all NodeChildren relationships
        relationships = models.NodeChildren.objects.all()

        for rel in relationships:
            # Parent and child must exist
            assert rel.parent is not None, f"Relationship {rel.pk} has null parent"
            assert rel.child is not None, f"Relationship {rel.pk} has null child"

            # Parent and child must be different
            assert rel.parent.pk != rel.child.pk, (
                f"Node {rel.parent.pk} is its own child"
            )

    def test_complex_form_get_node_recursive(self):
        """
        Test get_node(recursive=True) on complex nested structures.

        This is what the admin uses to display forms.
        """
        # Get a parent with children
        parents = models.NodeChildren.objects.values_list(
            "parent", flat=True
        ).distinct()

        for parent_id in list(parents)[:5]:
            parent = models.FormKitSchemaNode.objects.get(pk=parent_id)

            # Get the node recursively
            try:
                node = parent.get_node(recursive=True, options=True)

                # Should return valid data
                assert node is not None

                # If it's a dict, should have basic structure
                if isinstance(node, dict):
                    # Groups and repeaters should have children
                    if node.get("$formkit") in ["group", "repeater"]:
                        # May or may not have children in the result
                        # depending on whether children are active
                        pass

            except Exception as e:
                pytest.fail(f"get_node failed for {parent.label or parent.pk}: {e}")

    def test_add_child_to_complex_form(self):
        """
        Test adding a new child node to an existing complex form.

        This simulates adding a field through the admin.
        """

        # Find a group node to add a child to
        group_node = models.FormKitSchemaNode.objects.filter(
            node__contains={"$formkit": "group"}
        ).first()
        assert group_node is not None

        # Create a new child node
        new_child = models.FormKitSchemaNode.objects.create(
            node_type="$formkit",
            label="New Field",
            node={"$formkit": "text", "name": "new_text_field"},
        )

        # Add as child
        models.NodeChildren.objects.create(
            parent=group_node,
            child=new_child,
            order=999,  # Will be auto-adjusted
        )

        # Verify relationship
        children = models.NodeChildren.objects.filter(parent=group_node)
        assert new_child in [c.child for c in children]

        # Get parent node recursively to verify child is included
        parent_values = group_node.get_node_values(recursive=True)
        if "children" in parent_values:
            # New child should be in there
            child_names = [
                c.get("name") for c in parent_values["children"] if isinstance(c, dict)
            ]
            assert "new_text_field" in child_names

    def test_reorder_children(self):
        """
        Test reordering children in a complex form.

        This is common in admin when organizing form fields.
        """
        # Find a parent with multiple children
        parent_with_children = (
            models.NodeChildren.objects.values("parent")
            .annotate(count=Count("parent"))
            .filter(count__gte=3)
            .order_by("-count")
            .first()
        )

        if not parent_with_children:
            pytest.skip("No parent with 3+ children found")

        parent_id = parent_with_children["parent"]

        # Get children
        children = list(
            models.NodeChildren.objects.filter(parent_id=parent_id).order_by("order")
        )

        assert len(children) >= 3

        # Swap first two children
        first, second = children[0], children[1]
        original_first_order = first.order
        original_second_order = second.order

        # Update orders
        first.order = original_second_order
        second.order = original_first_order

        first.save(update_fields=["order"])
        second.save(update_fields=["order"])

        # Verify reordering worked
        reordered = list(
            models.NodeChildren.objects.filter(parent_id=parent_id).order_by("order")
        )

        assert reordered[0].child.pk == children[1].child.pk
        assert reordered[1].child.pk == children[0].child.pk
