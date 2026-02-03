#!/usr/bin/env python
"""
Demonstration script showing the complete formkit-ninja workflow.

This script demonstrates:
1. Creating a FormKit schema programmatically
2. Bootstrapping a Django app from the schema
3. Submitting data and watching it flow through the system
4. Adding a new field and regenerating code
"""

import json
import os
import sys
from pathlib import Path

# Add the project to the path
sys.path.insert(0, str(Path(__file__).parent))

# Setup Django
os.environ.setdefault("DJANGO_SETTINGS_MODULE", "testproject.settings")

import django
django.setup()

from django.contrib.auth import get_user_model
from formkit_ninja import models as fk_models
from formkit_ninja.form_submission.models import Submission


def print_section(title):
    """Print a section header."""
    print("\n" + "=" * 70)
    print(f"  {title}")
    print("=" * 70 + "\n")


def create_demo_schema():
    """Create a demo FormKit schema."""
    print_section("Step 1: Creating FormKit Schema")
    
    # Delete existing schema if it exists
    fk_models.FormKitSchema.objects.filter(label="Demo Data Collection").delete()
    
    # Create schema
    schema = fk_models.FormKitSchema.objects.create(label="Demo Data Collection")
    print(f"✓ Created schema: {schema.label}")
    
    # Create root group
    root_group = fk_models.FormKitSchemaNode.objects.create(
        node={"$formkit": "group", "name": "data_collection"},
        label="Data Collection Form",
    )
    
    fk_models.FormComponents.objects.create(
        schema=schema,
        node=root_group,
        label="Data Collection Form",
        order=0,
    )
    print(f"✓ Created root group: {root_group.node.get('name', 'data_collection')}")
    
    # Add fields to root group
    fields = [
        {"formkit": "text", "name": "collector_name", "label": "Collector Name"},
        {"formkit": "email", "name": "collector_email", "label": "Collector Email"},
        {"formkit": "date", "name": "collection_date", "label": "Collection Date"},
    ]
    
    for order, field_data in enumerate(fields):
        field_node = fk_models.FormKitSchemaNode.objects.create(
            node={"$formkit": field_data["formkit"], "name": field_data["name"]},
            label=field_data["label"],
        )
        
        fk_models.NodeChildren.objects.create(
            parent=root_group,
            child=field_node,
            order=order,
        )
        print(f"✓ Added field: {field_data['name']} ({field_data['formkit']})")
    
    # Add a nested group
    location_group = fk_models.FormKitSchemaNode.objects.create(
        node={"$formkit": "group", "name": "location"},
        label="Location Information",
    )
    
    fk_models.NodeChildren.objects.create(
        parent=root_group,
        child=location_group,
        order=len(fields),
    )
    print(f"✓ Added nested group: {location_group.node.get('name', 'location')}")
    
    # Add fields to location group
    location_fields = [
        {"formkit": "text", "name": "district", "label": "District"},
        {"formkit": "text", "name": "village", "label": "Village"},
    ]
    
    for order, field_data in enumerate(location_fields):
        field_node = fk_models.FormKitSchemaNode.objects.create(
            node={"$formkit": field_data["formkit"], "name": field_data["name"]},
            label=field_data["label"],
        )
        
        fk_models.NodeChildren.objects.create(
            parent=location_group,
            child=field_node,
            order=order,
        )
        print(f"  ✓ Added to location: {field_data['name']}")
    
    # Add a repeater
    observations_repeater = fk_models.FormKitSchemaNode.objects.create(
        node={"$formkit": "repeater", "name": "observations"},
        label="Observations",
    )
    
    fk_models.NodeChildren.objects.create(
        parent=root_group,
        child=observations_repeater,
        order=len(fields) + 1,
    )
    print(f"✓ Added repeater: {observations_repeater.node.get('name', 'observations')}")
    
    # Add fields to repeater
    repeater_fields = [
        {"formkit": "text", "name": "observation_type", "label": "Type"},
        {"formkit": "textarea", "name": "notes", "label": "Notes"},
        {"formkit": "number", "name": "count", "label": "Count"},
    ]
    
    for order, field_data in enumerate(repeater_fields):
        field_node = fk_models.FormKitSchemaNode.objects.create(
            node={"$formkit": field_data["formkit"], "name": field_data["name"]},
            label=field_data["label"],
        )
        
        fk_models.NodeChildren.objects.create(
            parent=observations_repeater,
            child=field_node,
            order=order,
        )
        print(f"  ✓ Added to observations: {field_data['name']}")
    
    print(f"\n✓ Schema created with {fk_models.FormKitSchemaNode.objects.count()} nodes")
    return schema


def show_schema_structure(schema):
    """Display the schema structure."""
    print_section("Schema Structure")
    
    def print_node(node, indent=0):
        prefix = "  " * indent
        # Access name and formkit from the node JSON field
        node_data = node.node or {}
        name = node_data.get("name", "unnamed")
        formkit = node_data.get("$formkit", "unknown")
        print(f"{prefix}- {name} ({formkit})")
        
        # Get children
        children = fk_models.NodeChildren.objects.filter(parent=node).order_by("order")
        for child_rel in children:
            print_node(child_rel.child, indent + 1)
    
    # Get root node
    root_component = fk_models.FormComponents.objects.filter(schema=schema).first()
    if root_component and root_component.node:
        print_node(root_component.node)


def demonstrate_code_generation(schema):
    """Demonstrate code generation."""
    print_section("Step 2: Code Generation Preview")
    
    from formkit_ninja.parser.formatter import CodeFormatter
    from formkit_ninja.parser.generator import CodeGenerator
    from formkit_ninja.parser.generator_config import GeneratorConfig
    from formkit_ninja.parser.template_loader import DefaultTemplateLoader
    from formkit_ninja import formkit_schema
    
    # Setup generator
    output_dir = Path("/tmp/demo_app")
    output_dir.mkdir(exist_ok=True)
    
    config = GeneratorConfig(
        app_name="demo_app",
        output_dir=output_dir,
        schema_name=schema.label,
    )
    
    template_loader = DefaultTemplateLoader()
    formatter = CodeFormatter()
    generator = CodeGenerator(
        config=config,
        template_loader=template_loader,
        formatter=formatter,
    )
    
    # Convert schema to Pydantic format
    values = list(schema.get_schema_values(recursive=True))
    pydantic_schema = formkit_schema.FormKitSchema.parse_obj(values)
    
    # Generate code
    print("Generating code...")
    generator.generate(pydantic_schema)
    
    print(f"\n✓ Code generated in: {output_dir}")
    print("\nGenerated files:")
    for file_path in sorted(output_dir.rglob("*.py")):
        rel_path = file_path.relative_to(output_dir)
        print(f"  - {rel_path}")


def demonstrate_data_flow(schema):
    """Demonstrate how data flows through the system."""
    print_section("Step 3: Data Flow Demonstration")
    
    # Create a submission
    User = get_user_model()
    user, _ = User.objects.get_or_create(username="demo_user", email="demo@example.com")
    
    submission_data = {
        "collector_name": "John Doe",
        "collector_email": "john@example.com",
        "collection_date": "2026-02-01",
        "location": {
            "district": "Dili",
            "village": "Comoro",
        },
        "observations": [
            {
                "uuid": "550e8400-e29b-41d4-a716-446655440001",
                "observation_type": "Wildlife",
                "notes": "Saw several birds",
                "count": 5,
            },
            {
                "uuid": "550e8400-e29b-41d4-a716-446655440002",
                "observation_type": "Plants",
                "notes": "Rare orchid species",
                "count": 2,
            },
        ],
    }
    
    print("Creating submission with data:")
    print(json.dumps(submission_data, indent=2))
    
    submission = Submission.objects.create(
        user=user,
        form_type="DataCollection",
        fields=submission_data,
    )
    
    print(f"\n✓ Created Submission: {submission.key}")
    
    # Show SeparatedSubmissions
    from formkit_ninja.form_submission.models import SeparatedSubmission
    
    separated = SeparatedSubmission.objects.filter(submission=submission)
    print(f"\n✓ Created {separated.count()} SeparatedSubmission instances:")
    
    for sep in separated:
        print(f"\n  - {sep.form_type} (ID: {sep.id})")
        print(f"    Fields: {list(sep.fields.keys())}")
        if sep.repeater_parent:
            print(f"    Parent: {sep.repeater_parent.form_type}")
        if sep.repeater_key:
            print(f"    Repeater: {sep.repeater_key} (order: {sep.repeater_order})")


def demonstrate_adding_field(schema):
    """Demonstrate adding a new field to the schema."""
    print_section("Step 4: Adding a New Field")
    
    # Find the root group
    root_component = fk_models.FormComponents.objects.filter(schema=schema).first()
    root_node = root_component.node
    
    print(f"Adding new field to: {root_node.node.get('name', 'root')}")
    
    # Create new field
    new_field = fk_models.FormKitSchemaNode.objects.create(
        node={"$formkit": "text", "name": "project_code"},
        label="Project Code",
    )
    
    # Get current max order
    max_order = fk_models.NodeChildren.objects.filter(parent=root_node).count()
    
    # Add as child
    fk_models.NodeChildren.objects.create(
        parent=root_node,
        child=new_field,
        order=max_order,
    )
    
    print(f"✓ Added field: {new_field.node.get('name', 'project_code')} ({new_field.node.get('$formkit', 'text')})")
    print("\nUpdated schema structure:")
    
    # Show updated structure
    def print_node(node, indent=0):
        prefix = "  " * indent
        node_data = node.node or {}
        name = node_data.get("name", "unnamed")
        formkit = node_data.get("$formkit", "unknown")
        marker = " [NEW]" if name == "project_code" else ""
        print(f"{prefix}- {name} ({formkit}){marker}")
        
        children = fk_models.NodeChildren.objects.filter(parent=node).order_by("order")
        for child_rel in children:
            print_node(child_rel.child, indent + 1)
    
    print_node(root_node)
    
    print("\n✓ Code would be regenerated with the new field included")


def main():
    """Run the demonstration."""
    print("\n" + "🚀 " * 35)
    print("  FormKit-Ninja: Complete Workflow Demonstration")
    print("🚀 " * 35)
    
    # Create schema
    schema = create_demo_schema()
    
    # Show structure
    show_schema_structure(schema)
    
    # Generate code
    demonstrate_code_generation(schema)
    
    # Show data flow
    demonstrate_data_flow(schema)
    
    # Add field
    demonstrate_adding_field(schema)
    
    # Summary
    print_section("Summary")
    print("This demonstration showed:")
    print("  ✓ Creating a FormKit schema with groups and repeaters")
    print("  ✓ Generating Django models, schemas, admin, and API code")
    print("  ✓ Submitting data and seeing it flow through the system")
    print("  ✓ Adding new fields and regenerating code")
    print("\nWith formkit-ninja, you can build complete data collection")
    print("applications with minimal coding required!")
    print("\nNext steps:")
    print("  1. Try the management commands:")
    print("     ./manage.py create_schema --label 'My Form'")
    print("     ./manage.py bootstrap_app --schema-label 'My Form' --app-name myapp")
    print("  2. Read the Quick Start Guide: docs/quick_start.md")
    print("  3. Explore the generated code in /tmp/demo_app/")
    print("\n" + "🎉 " * 35 + "\n")


if __name__ == "__main__":
    main()
