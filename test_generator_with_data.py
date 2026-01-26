#!/usr/bin/env python
"""
Test script to load dumpdata and test the code generator.

This script:
1. Loads the dumpdata from /tmp/formkit.yaml
2. Disables necessary triggers
3. Loads the data
4. Re-enables triggers
5. Tests the code generator with the loaded data
"""

import os
import sys
from pathlib import Path

# Setup Django
import django
from django.core.management import call_command

# Add project to path
sys.path.insert(0, str(Path(__file__).parent))

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "testproject.settings")
django.setup()

from formkit_ninja import models  # noqa: E402
from formkit_ninja.parser import (  # noqa: E402
    CodeFormatter,
    CodeGenerator,
    DefaultTemplateLoader,
    GeneratorConfig,
)


def main():
    """Main test function."""
    print("=" * 80)
    print("Testing Code Generator with Real Data")
    print("=" * 80)

    # Step 1: Check current state
    print("\n1. Checking current database state...")
    schema_count = models.FormKitSchema.objects.count()
    node_count = models.FormKitSchemaNode.objects.count()
    print(f"   Schemas: {schema_count}")
    print(f"   Nodes: {node_count}")

    # Step 2: Disable triggers (if needed)
    print("\n2. Disabling triggers...")
    try:
        call_command("pgtrigger", "disable", "formkit_ninja.FormKitSchemaNode:protect_node_deletes_and_updates")
        call_command("pgtrigger", "disable", "formkit_ninja.FormKitSchemaNode:protect_node_updates")
        print("   ✓ Triggers disabled")
    except Exception as e:
        print(f"   ⚠ Could not disable triggers: {e}")

    # Step 3: Load dumpdata
    print("\n3. Loading dumpdata from /tmp/formkit.yaml...")
    try:
        call_command("loaddata", "/tmp/formkit.yaml", verbosity=1)
        print("   ✓ Data loaded successfully")
    except Exception as e:
        print(f"   ✗ Error loading data: {e}")
        return 1

    # Step 4: Re-enable triggers
    print("\n4. Re-enabling triggers...")
    try:
        call_command("pgtrigger", "enable", "formkit_ninja.FormKitSchemaNode:protect_node_deletes_and_updates")
        call_command("pgtrigger", "enable", "formkit_ninja.FormKitSchemaNode:protect_node_updates")
        print("   ✓ Triggers re-enabled")
    except Exception as e:
        print(f"   ⚠ Could not re-enable triggers: {e}")

    # Step 5: Check new state
    print("\n5. Checking database state after load...")
    schema_count_after = models.FormKitSchema.objects.count()
    node_count_after = models.FormKitSchemaNode.objects.count()
    print(f"   Schemas: {schema_count_after} (was {schema_count})")
    print(f"   Nodes: {node_count_after} (was {node_count})")

    # Step 6: Test code generator
    print("\n6. Testing code generator...")

    if schema_count_after == 0:
        print("   ⚠ No schemas found in database. Creating a test schema from nodes...")
        # Try to find root nodes (nodes with no parent) and create a schema
        from formkit_ninja.models import FormComponents

        # Find nodes that are not children of other nodes
        # This is a simplified approach - in reality, we'd need to find the actual root nodes
        all_nodes = models.FormKitSchemaNode.objects.filter(is_active=True)
        root_nodes = [n for n in all_nodes if n.children.count() == 0 or n.node_type == "$formkit"]

        if not root_nodes:
            # Try a different approach - get nodes that might be roots
            root_nodes = list(all_nodes[:5])  # Get first 5 nodes as a test

        if root_nodes:
            # Create a test schema
            test_schema = models.FormKitSchema.objects.create(label="Test Schema from Nodes")
            for idx, node in enumerate(root_nodes[:3]):  # Use first 3 nodes
                FormComponents.objects.create(
                    schema=test_schema, node=node, order=idx, label=f"Test {node.label or node.id}"
                )
            print(f"   ✓ Created test schema with {len(root_nodes[:3])} nodes")
            schema_count_after = 1
        else:
            print("   ✗ No suitable nodes found to create a schema.")
            return 1

    # Create output directory
    output_dir = Path("/tmp/formkit_generated")
    output_dir.mkdir(exist_ok=True, parents=True)
    print(f"   Output directory: {output_dir}")

    # Get first schema for testing
    first_schema = models.FormKitSchema.objects.first()
    print(f"   Testing with schema: {first_schema.label or first_schema.id}")

    try:
        # Initialize generator
        config = GeneratorConfig(
            app_name="testapp",
            output_dir=output_dir,
        )
        template_loader = DefaultTemplateLoader()
        formatter = CodeFormatter()
        generator = CodeGenerator(
            config=config,
            template_loader=template_loader,
            formatter=formatter,
        )

        # Get schema values
        values = list(first_schema.get_schema_values(recursive=True))
        from formkit_ninja import formkit_schema

        pydantic_schema = formkit_schema.FormKitSchema.parse_obj(values)

        # Generate code
        print("   Generating code...")
        generator.generate(pydantic_schema)
        print("   ✓ Code generation successful!")

        # List generated files
        print("\n7. Generated files:")
        for filename in ["models.py", "schemas.py", "schemas_in.py", "admin.py", "api.py"]:
            filepath = output_dir / filename
            if filepath.exists():
                size = filepath.stat().st_size
                print(f"   ✓ {filename} ({size} bytes)")
            else:
                print(f"   ✗ {filename} (missing)")

        # Validate generated code
        print("\n8. Validating generated code...")
        import ast

        errors = []
        for filename in ["models.py", "schemas.py", "schemas_in.py", "admin.py", "api.py"]:
            filepath = output_dir / filename
            if filepath.exists():
                try:
                    with open(filepath, "r") as f:
                        code = f.read()
                    ast.parse(code)
                    print(f"   ✓ {filename} - valid Python syntax")
                except SyntaxError as e:
                    errors.append(f"{filename}: {e}")
                    print(f"   ✗ {filename} - syntax error: {e}")

        if errors:
            print("\n   ✗ Validation failed with errors:")
            for error in errors:
                print(f"     - {error}")
            return 1

        print("\n" + "=" * 80)
        print("✓ All tests passed!")
        print("=" * 80)
        print(f"\nGenerated code is available in: {output_dir}")
        return 0

    except Exception as e:
        print(f"\n   ✗ Error during code generation: {e}")
        import traceback

        traceback.print_exc()
        return 1


if __name__ == "__main__":
    sys.exit(main())
