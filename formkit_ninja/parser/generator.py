"""
Code generator for FormKit schemas.

This module provides the CodeGenerator class which generates Django models,
Pydantic schemas, admin classes, and API endpoints from FormKit schemas.
"""

import ast
from typing import List, Union

from formkit_ninja.formkit_schema import FormKitSchema
from formkit_ninja.parser.formatter import CodeFormatter, FormattingError
from formkit_ninja.parser.generator_config import GeneratorConfig
from formkit_ninja.parser.template_loader import TemplateLoader
from formkit_ninja.parser.type_convert import NodePath


class CodeGenerator:
    """
    Code generator for FormKit schemas.

    Generates Django models, Pydantic schemas, admin classes, and API endpoints
    from FormKit schema definitions.

    Args:
        config: Generator configuration (app name, output dir, etc.)
        template_loader: Template loader for Jinja2 templates
        formatter: Code formatter (uses ruff)
    """

    def __init__(
        self,
        config: GeneratorConfig,
        template_loader: TemplateLoader,
        formatter: CodeFormatter,
    ) -> None:
        """Initialize CodeGenerator with configuration and dependencies."""
        self.config = config
        self.template_loader = template_loader
        self.formatter = formatter

    def _collect_nodepaths(self, schema: Union[List[dict], FormKitSchema]) -> List[NodePath]:
        """
        Collect all NodePath instances from a FormKit schema recursively.

        Traverses the schema structure and collects all nodes (groups, repeaters,
        and form fields) as NodePath instances.

        Args:
            schema: FormKit schema (list of dicts or FormKitSchema object)

        Returns:
            List of NodePath instances representing all nodes in the schema
        """
        nodepaths: List[NodePath] = []

        # Convert to list of dicts if FormKitSchema object
        if isinstance(schema, FormKitSchema):
            # Convert FormKitSchema nodes to dicts
            schema_dicts = []
            for node in schema.__root__:
                # Handle string nodes (skip them)
                if isinstance(node, str):
                    continue
                # Convert Pydantic model to dict
                schema_dicts.append(node.dict(exclude_none=True))
        else:
            schema_dicts = schema

        def traverse_node(node_dict: dict, parent_path: NodePath | None = None) -> None:
            """Recursively traverse a node and its children."""
            # Create NodePath from node dict to get the node object
            temp_path = self.config.node_path_class.from_obj(node_dict)
            node = temp_path.node

            # Build the full path
            if parent_path is not None:
                # Append to parent path
                node_path = parent_path / node
            else:
                # Root level node - create new path
                node_path = self.config.node_path_class(node)

            # Add to collection
            nodepaths.append(node_path)

            # Recursively process children
            children = node_dict.get("children", [])
            if children:
                for child_dict in children:
                    # Skip string children (text nodes)
                    if isinstance(child_dict, str):
                        continue
                    traverse_node(child_dict, node_path)

        # Process all root-level nodes
        for node_dict in schema_dicts:
            traverse_node(node_dict)

        return nodepaths

    def _generate_file(
        self,
        template_name: str,
        output_filename: str,
        nodepaths: List[NodePath],
    ) -> str:
        """
        Generate a single file from a template.

        Args:
            template_name: Name of the Jinja2 template
            output_filename: Name of the output file (for reference)
            nodepaths: List of NodePath instances to render

        Returns:
            Generated code as string (before formatting)
        """
        env = self.template_loader.get_environment()
        template = env.get_template(template_name)

        # Render template with nodepaths
        code = template.render(
            nodepaths=nodepaths,
            app_name=self.config.app_name,
            include_ordinality=self.config.include_ordinality,
        )

        return code

    def _validate_code(self, code: str, filename: str) -> None:
        """
        Validate that generated code is valid Python.

        Args:
            code: Python code string to validate
            filename: Name of file (for error messages)

        Raises:
            SyntaxError: If code is not valid Python
        """
        try:
            ast.parse(code)
        except SyntaxError as e:
            raise SyntaxError(
                f"Generated {filename} has syntax errors: {e.msg} at line {e.lineno}",
            ) from e

    def _write_file(self, filename: str, content: str) -> None:
        """
        Write content to a file, creating directory if needed.

        Args:
            filename: Name of the file (relative to output_dir)
            content: Content to write
        """
        # Ensure output directory exists
        self.config.output_dir.mkdir(parents=True, exist_ok=True)

        file_path = self.config.output_dir / filename
        file_path.write_text(content, encoding="utf-8")

    def generate(self, schema: Union[List[dict], FormKitSchema]) -> None:
        """
        Generate all code files from a FormKit schema.

        Generates:
        - models.py: Django models
        - schemas.py: Django Ninja output schemas
        - schemas_in.py: Django Ninja input schemas (Pydantic BaseModel)
        - admin.py: Django admin classes
        - api.py: Django Ninja API endpoints

        Args:
            schema: FormKit schema (list of dicts or FormKitSchema object)

        Raises:
            SyntaxError: If generated code is not valid Python
            FormattingError: If code formatting fails
        """
        # Collect all NodePath instances
        all_nodepaths = self._collect_nodepaths(schema)

        # Filter to only groups and repeaters (templates handle form fields through parent)
        nodepaths = [np for np in all_nodepaths if np.is_group or np.is_repeater]

        # Define files to generate: (template_name, output_filename)
        files_to_generate = [
            ("models.py.jinja2", "models.py"),
            ("schemas.py.jinja2", "schemas.py"),
            ("schemas_in.py.jinja2", "schemas_in.py"),
            ("admin.py.jinja2", "admin.py"),
            ("api.py.jinja2", "api.py"),
        ]

        # Generate each file
        for template_name, output_filename in files_to_generate:
            # Generate code from template
            code = self._generate_file(template_name, output_filename, nodepaths)

            # Format code (may raise FormattingError)
            try:
                formatted_code = self.formatter.format(code)
            except FormattingError:
                # If formatting fails, use unformatted code
                # This allows generation to continue even if ruff is not available
                formatted_code = code

            # Validate code syntax
            self._validate_code(formatted_code, output_filename)

            # Write to file
            self._write_file(output_filename, formatted_code)
