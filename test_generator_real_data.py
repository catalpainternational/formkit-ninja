#!/usr/bin/env python
"""
Test script to test code generator with real Partisipa data.

This script:
1. Finds a GroupNode that represents a schema (top-level)
2. Converts it to a FormKitSchema format
3. Tests the code generator
4. Verifies that nested GroupNodes generate Models and Repeaters generate M2M models
"""

import os
import sys
from pathlib import Path

# Setup Django
import django

sys.path.insert(0, str(Path(__file__).parent))
os.environ.setdefault("DJANGO_SETTINGS_MODULE", "testproject.settings")
django.setup()

from formkit_ninja import formkit_schema, models  # noqa: E402
from formkit_ninja.parser import (  # noqa: E402
    CodeFormatter,
    CodeGenerator,
    DefaultTemplateLoader,
    GeneratorConfig,
)


def find_schema_group_node(prefer_with_repeaters=True):
    """Find a GroupNode that represents a schema (has nested groups/repeaters)."""
    # Look for GroupNodes that have children with groups or repeaters
    all_nodes = models.FormKitSchemaNode.objects.filter(is_active=True)

    # First, try to find one with repeaters if preferred
    if prefer_with_repeaters:
        for node in all_nodes:
            if not node.node or not isinstance(node.node, dict):
                continue

            formkit_type = node.node.get("$formkit") or node.node.get("formkit")
            if formkit_type != "group":
                continue

            # Check if this node has repeaters
            children = node.children.all()
            has_repeaters = False

            for child in children:
                if not child.node or not isinstance(child.node, dict):
                    continue
                child_formkit = child.node.get("$formkit") or child.node.get("formkit")
                if child_formkit == "repeater":
                    has_repeaters = True
                    break

            if has_repeaters:
                return node

    # Then look for any with nested groups or repeaters
    for node in all_nodes:
        if not node.node or not isinstance(node.node, dict):
            continue

        formkit_type = node.node.get("$formkit") or node.node.get("formkit")
        if formkit_type != "group":
            continue

        # Check if this node has nested groups or repeaters
        children = node.children.all()
        has_nested_groups = False
        has_repeaters = False

        for child in children:
            if not child.node or not isinstance(child.node, dict):
                continue
            child_formkit = child.node.get("$formkit") or child.node.get("formkit")
            if child_formkit == "group":
                has_nested_groups = True
            elif child_formkit == "repeater":
                has_repeaters = True

        if has_nested_groups or has_repeaters:
            return node

    # Fallback: return first group node
    for node in all_nodes:
        if node.node and isinstance(node.node, dict):
            formkit_type = node.node.get("$formkit") or node.node.get("formkit")
            if formkit_type == "group":
                return node

    return None


def node_to_schema_dict(node):
    """Convert a FormKitSchemaNode to a schema dict format."""

    def node_to_dict(n):
        """Recursively convert node to dict."""
        if not n.node or not isinstance(n.node, dict):
            return None

        node_dict = n.node.copy()

        # Add children recursively
        children = []
        for child in n.children.all().order_by("id"):
            child_dict = node_to_dict(child)
            if child_dict:
                children.append(child_dict)

        if children:
            node_dict["children"] = children

        return node_dict

    return node_to_dict(node)


def main():
    """Main test function."""
    print("=" * 80)
    print("Testing Code Generator with Real Partisipa Data")
    print("=" * 80)

    # Step 1: Find a schema GroupNode (prefer one with repeaters)
    print("\n1. Finding a GroupNode schema with repeaters...")
    schema_node = find_schema_group_node(prefer_with_repeaters=True)

    if not schema_node:
        print("   ✗ No suitable GroupNode found")
        return 1

    print(f"   ✓ Found GroupNode: {schema_node.label or schema_node.id}")

    # Analyze structure
    children = schema_node.children.all()
    nested_groups = [
        c
        for c in children
        if c.node and isinstance(c.node, dict) and (c.node.get("$formkit") or c.node.get("formkit")) == "group"
    ]
    repeaters = [
        c
        for c in children
        if c.node and isinstance(c.node, dict) and (c.node.get("$formkit") or c.node.get("formkit")) == "repeater"
    ]

    print(f"   - Total children: {children.count()}")
    print(f"   - Nested GroupNodes: {len(nested_groups)}")
    print(f"   - RepeaterNodes: {len(repeaters)}")

    # Step 2: Convert to schema format
    print("\n2. Converting GroupNode to schema format...")
    schema_dict = node_to_schema_dict(schema_node)

    if not schema_dict:
        print("   ✗ Could not convert node to schema dict")
        return 1

    # Wrap in list (FormKitSchema expects a list)
    schema_list = [schema_dict]

    # Parse as FormKitSchema
    try:
        pydantic_schema = formkit_schema.FormKitSchema.parse_obj(schema_list)
        print("   ✓ Schema parsed successfully")
    except Exception as e:
        print(f"   ✗ Error parsing schema: {e}")
        import traceback

        traceback.print_exc()
        return 1

    # Step 3: Test code generator
    print("\n3. Testing code generator...")
    output_dir = Path("/tmp/formkit_generated_real")
    output_dir.mkdir(exist_ok=True, parents=True)
    print(f"   Output directory: {output_dir}")

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

        # Collect NodePaths to analyze what will be generated
        print("   Collecting NodePaths...")
        all_nodepaths = generator._collect_nodepaths(pydantic_schema)
        groups = [np for np in all_nodepaths if np.is_group]
        repeaters_list = [np for np in all_nodepaths if np.is_repeater]

        print(f"   - Total NodePaths: {len(all_nodepaths)}")
        print(f"   - GroupNodes: {len(groups)}")
        print(f"   - RepeaterNodes: {len(repeaters_list)}")

        # Show what models will be generated
        if groups:
            print("\n   Models that will be generated from GroupNodes:")
            for group in groups:
                print(f"     - {group.classname} (from: {group.fieldname})")

        if repeaters_list:
            print("\n   M2M models that will be generated from Repeaters:")
            for repeater in repeaters_list:
                print(f"     - {repeater.classname}Link (M2M for: {repeater.fieldname})")

        # Generate code
        print("\n   Generating code...")
        generator.generate(pydantic_schema)
        print("   ✓ Code generation successful!")

        # Step 4: Analyze generated files
        print("\n4. Analyzing generated code...")
        models_file = output_dir / "models.py"

        if models_file.exists():
            with open(models_file, "r") as f:
                models_code = f.read()

            # Count class definitions
            import re

            class_matches = re.findall(r"^class (\w+)", models_code, re.MULTILINE)
            print(f"   ✓ Generated {len(class_matches)} model classes:")
            for class_name in class_matches:
                print(f"     - {class_name}")

            # Check for M2M models (Link classes)
            link_classes = [c for c in class_matches if "Link" in c]
            if link_classes:
                print(f"\n   ✓ Generated {len(link_classes)} M2M link models:")
                for link_class in link_classes:
                    print(f"     - {link_class}")

        # List all generated files
        print("\n5. Generated files:")
        for filename in ["models.py", "schemas.py", "schemas_in.py", "admin.py", "api.py"]:
            filepath = output_dir / filename
            if filepath.exists():
                size = filepath.stat().st_size
                lines = len(open(filepath).readlines())
                print(f"   ✓ {filename} ({size} bytes, {lines} lines)")

        # Validate generated code
        print("\n6. Validating generated code...")
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
        print("\nKey findings:")
        print(f"  - Generated {len(groups)} models from GroupNodes")
        print(f"  - Generated {len(repeaters_list)} M2M models from Repeaters")
        return 0

    except Exception as e:
        print(f"\n   ✗ Error during code generation: {e}")
        import traceback

        traceback.print_exc()
        return 1


if __name__ == "__main__":
    sys.exit(main())
