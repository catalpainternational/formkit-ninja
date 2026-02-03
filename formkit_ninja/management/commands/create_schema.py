"""
Django management command to create a FormKit schema interactively.

This command guides users through creating a FormKit schema with groups,
repeaters, and input fields.
"""

import json
import uuid
from django.core.management.base import BaseCommand, CommandError
from formkit_ninja import models


class Command(BaseCommand):
    """Create a FormKit schema interactively."""

    help = "Create a FormKit schema interactively with groups, repeaters, and fields"

    def add_arguments(self, parser):
        """Add command-line arguments."""
        parser.add_argument(
            "--label",
            type=str,
            required=True,
            help="Label for the schema (required)",
        )
        parser.add_argument(
            "--from-json",
            type=str,
            default=None,
            help="Path to JSON file containing schema definition (optional)",
        )

    def handle(self, *args, **options):
        """Execute the command."""
        label = options["label"]
        json_file = options.get("from_json")

        # Check if schema already exists
        if models.FormKitSchema.objects.filter(label=label).exists():
            raise CommandError(f"Schema with label '{label}' already exists")

        if json_file:
            # Load from JSON file
            self.stdout.write(f"Loading schema from: {json_file}")
            schema = self._create_from_json(label, json_file)
        else:
            # Interactive creation
            self.stdout.write(self.style.SUCCESS(f"Creating schema: {label}"))
            schema = self._create_interactively(label)

        self.stdout.write("\n" + "=" * 70)
        self.stdout.write(self.style.SUCCESS("✓ Schema created successfully!"))
        self.stdout.write("=" * 70)
        self.stdout.write(f"\nSchema label: {schema.label}")
        self.stdout.write(f"Schema ID: {schema.id}")
        self.stdout.write(f"\nYou can now use this schema with:")
        self.stdout.write(f"  ./manage.py bootstrap_app --schema-label \"{label}\" --app-name your_app_name\n")

    def _create_from_json(self, label: str, json_file: str) -> models.FormKitSchema:
        """Create schema from JSON file."""
        try:
            with open(json_file, 'r') as f:
                schema_data = json.load(f)
        except FileNotFoundError:
            raise CommandError(f"File not found: {json_file}")
        except json.JSONDecodeError as e:
            raise CommandError(f"Invalid JSON in file: {e}")

        # Create schema
        schema = models.FormKitSchema.objects.create(label=label)
        
        # Process nodes recursively
        self._process_nodes(schema, schema_data, parent=None)
        
        return schema

    def _process_nodes(self, schema: models.FormKitSchema, nodes: list, parent=None):
        """Process nodes recursively."""
        for order, node_data in enumerate(nodes):
            formkit_type = node_data.get("$formkit", "text")
            name = node_data.get("name", f"field_{uuid.uuid4().hex[:8]}")
            label = node_data.get("label", name)
            
            # Create node
            node = models.FormKitSchemaNode.objects.create(
                node={"$formkit": formkit_type, "name": name},
                label=label,
                additional_props=node_data,
            )
            
            # Add to schema ONLY if this is a root node (no parent)
            if parent is None:
                models.FormComponents.objects.create(
                    schema=schema,
                    node=node,
                    label=label,
                    order=order,
                )
            
            # Add parent relationship if needed
            if parent:
                models.NodeChildren.objects.create(
                    parent=parent,
                    child=node,
                    order=order,
                )
            
            # Process children if this is a group or repeater
            if formkit_type in ["group", "repeater"] and "children" in node_data:
                self._process_nodes(schema, node_data["children"], parent=node)

    def _create_interactively(self, label: str) -> models.FormKitSchema:
        """Create schema interactively."""
        self.stdout.write("\nThis wizard will guide you through creating a FormKit schema.")
        self.stdout.write("You can create groups, repeaters, and input fields.\n")

        # Create schema
        schema = models.FormKitSchema.objects.create(label=label)
        self.stdout.write(self.style.SUCCESS(f"✓ Created schema: {label}\n"))

        # Create root group
        self.stdout.write("Creating root group node...")
        root_name = self._prompt("Root group name", default=label.lower().replace(" ", "_"))
        root_label = self._prompt("Root group label", default=label)
        
        root_node = models.FormKitSchemaNode.objects.create(
            node={"$formkit": "group", "name": root_name},
            label=root_label,
        )
        
        models.FormComponents.objects.create(
            schema=schema,
            node=root_node,
            label=root_label,
            order=0,
        )
        
        self.stdout.write(self.style.SUCCESS(f"✓ Created root group: {root_name}\n"))

        # Add child nodes
        self._add_children_interactively(root_node)

        return schema

    def _add_children_interactively(self, parent_node: models.FormKitSchemaNode):
        """Add child nodes interactively."""
        order = 0
        
        while True:
            parent_name = parent_node.node.get("name", "node") if parent_node.node else "node"
            self.stdout.write(f"\nAdding child to: {parent_name}")
            
            # Ask what type of node to add
            node_type = self._prompt_choice(
                "Node type",
                choices=["text", "number", "email", "textarea", "select", "checkbox", "date", "group", "repeater", "done"],
                default="done"
            )
            
            if node_type == "done":
                break
            
            # Get node details
            name = self._prompt("Field name (e.g., 'email', 'age')")
            label = self._prompt("Field label (human-readable)", default=name.replace("_", " ").title())
            
            # Create node
            node = models.FormKitSchemaNode.objects.create(
                node={"$formkit": node_type, "name": name},
                label=label,
            )
            
            # Add as child
            models.NodeChildren.objects.create(
                parent=parent_node,
                child=node,
                order=order,
            )
            
            order += 1
            
            self.stdout.write(self.style.SUCCESS(f"✓ Added {node_type} field: {name}"))
            
            # If group or repeater, recursively add children
            if node_type in ["group", "repeater"]:
                add_children = self._prompt_yes_no(f"Add children to {name}?", default=True)
                if add_children:
                    self._add_children_interactively(node)

    def _prompt(self, message: str, default: str = None) -> str:
        """Prompt user for input."""
        if default:
            prompt = f"{message} [{default}]: "
        else:
            prompt = f"{message}: "
        
        value = input(prompt).strip()
        return value if value else default

    def _prompt_choice(self, message: str, choices: list, default: str = None) -> str:
        """Prompt user to choose from a list."""
        self.stdout.write(f"\n{message}:")
        for i, choice in enumerate(choices, 1):
            marker = " (default)" if choice == default else ""
            self.stdout.write(f"  {i}. {choice}{marker}")
        
        while True:
            value = input(f"\nEnter choice [1-{len(choices)}] or name: ").strip()
            
            # Check if it's a number
            if value.isdigit():
                idx = int(value) - 1
                if 0 <= idx < len(choices):
                    return choices[idx]
            
            # Check if it's a choice name
            if value in choices:
                return value
            
            # Use default if empty
            if not value and default:
                return default
            
            self.stdout.write(self.style.ERROR("Invalid choice. Try again."))

    def _prompt_yes_no(self, message: str, default: bool = True) -> bool:
        """Prompt user for yes/no."""
        default_str = "Y/n" if default else "y/N"
        value = input(f"{message} [{default_str}]: ").strip().lower()
        
        if not value:
            return default
        
        return value in ["y", "yes", "true", "1"]
