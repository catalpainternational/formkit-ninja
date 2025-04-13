import pytest
from django.db import IntegrityError

from formkit_ninja.models import FormKitSchema, FormKitSchemaNode


@pytest.mark.django_db
class TestOrderManagement:
    @pytest.fixture
    def schema(self):
        return FormKitSchema.objects.create(label="Test Schema")

    @pytest.fixture
    def node_factory(self, schema):
        def create_node(**kwargs):
            n = FormKitSchemaNode.objects.create(
                schema=schema,
                node_type="$formkit",
                node={"$formkit": "text"},
                **kwargs
            )
            n.refresh_from_db()  # Otherwise we miss `order` updates
            return n
        return create_node

    def test_auto_order_assignment(self, node_factory):
        """Test that nodes without order get assigned the next available order"""
        # Create first node without order
        node1 = node_factory()
        assert node1.order == 1

        # Create second node without order
        node2 = node_factory()
        assert node2.order == 2

        # Create third node without order
        node3 = node_factory()
        assert node3.order == 3

    def test_explicit_order_assignment(self, node_factory):
        """Test that nodes with explicit order cause reordering"""
        # Create initial nodes
        node1 = node_factory(order=1)
        node2 = node_factory(order=2)
        node3 = node_factory(order=3)

        # Insert a node in the middle
        node4 = node_factory(order=2)
        
        # Verify orders were adjusted
        node1.refresh_from_db()
        node2.refresh_from_db()
        node3.refresh_from_db()
        node4.refresh_from_db()
        
        assert node1.order == 1
        assert node4.order == 2
        assert node2.order == 3
        assert node3.order == 4

    def test_deactivation_order_management(self, node_factory):
        """Test that deactivating a node adjusts remaining orders"""
        # Create initial nodes
        node1 = node_factory(order=1)
        node2 = node_factory(order=2)
        node3 = node_factory(order=3)

        # Deactivate middle node
        node2.delete()

        # Verify orders were adjusted
        node1.refresh_from_db()
        # node2.refresh_from_db()
        node3.refresh_from_db()
        
        assert node1.order == 1
        # assert node2.order is None
        assert node3.order == 2


    def test_order_null_on_deletion(self, node_factory):
        """Test that deleting a node adjusts remaining orders"""
        # Create initial nodes
        node1 = node_factory(order=1)
        node2 = node_factory(order=2)
        node3 = node_factory(order=3)

        # Delete middle node
        node2.delete()

        # Verify orders were adjusted
        node1.refresh_from_db()
        node3.refresh_from_db()
        
        assert node1.order == 1
        assert node3.order == 2

    def test_schema_isolation(self, schema, node_factory):
        """Test that order management is isolated to each schema"""
        # Create nodes in first schema
        node1 = node_factory(order=1)
        node2 = node_factory(order=2)

        # Create second schema and nodes
        schema2 = FormKitSchema.objects.create(label="Test Schema 2")
        node3 = FormKitSchemaNode.objects.create(
            schema=schema2,
            node_type="$formkit",
            node={"$formkit": "text"},
            order=1
        )
        node4 = FormKitSchemaNode.objects.create(
            schema=schema2,
            node_type="$formkit",
            node={"$formkit": "text"},
            order=2
        )

        # Verify orders are independent between schemas
        assert node1.order == 1
        assert node2.order == 2
        assert node3.order == 1
        assert node4.order == 2 