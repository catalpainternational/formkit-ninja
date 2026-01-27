"""
Code generator for FormKit schemas.

This module provides the CodeGenerator class which generates Django models,
Pydantic schemas, admin classes, and API endpoints from FormKit schemas.
"""

import ast
from typing import List, Union

from formkit_ninja.formkit_schema import FormKitSchema
from formkit_ninja.parser.formatter import CodeFormatter, FormattingError
from formkit_ninja.parser.generator_config import GeneratorConfig, schema_name_to_filename
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
        abstract_base_info: dict[str, bool] = {}  # Use classname as key
        root_child_abstract_bases: dict[str, list[str]] = {}  # Use classname as key

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

            # Set config and abstract info on all NodePath instances
            node_path._config = self.config
            node_path._abstract_base_info = abstract_base_info

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

        # After collecting all nodepaths, identify abstract bases if merging is enabled
        if self.config.merge_top_level_groups:
            # Only process group nodes
            group_nodepaths = [np for np in nodepaths if np.is_group]
            for node_path in group_nodepaths:
                # Root-level groups (depth=1, not a child)
                if not node_path.is_child:
                    # This is a root group - find its immediate child groups
                    child_abstract_bases = []
                    for child_path in group_nodepaths:
                        if (
                            child_path.is_child
                            and len(child_path.nodes) == 2  # depth=2 (root + child)
                            and child_path.nodes[0] == node_path.node  # parent is this root
                        ):
                            # This is an immediate child group of the root
                            abstract_base_info[child_path.classname] = True
                            child_abstract_bases.append(child_path.abstract_class_name)
                    root_child_abstract_bases[node_path.classname] = child_abstract_bases

        # Set child_abstract_bases for all root nodes and update abstract_base_info
        for node_path in nodepaths:
            # Update abstract_base_info dict reference so all NodePaths share the same dict
            node_path._abstract_base_info = abstract_base_info
            # Only set child_abstract_bases for group nodes (they have classnames)
            if node_path.is_group:
                try:
                    node_path._child_abstract_bases = root_child_abstract_bases.get(node_path.classname, [])
                except AttributeError:
                    # Skip nodes without names (e.g., element nodes)
                    node_path._child_abstract_bases = []

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

    def _write_file(self, filename: str, content: str, subdirectory: str | None = None) -> None:
        """
        Write content to a file, creating directory if needed.

        Args:
            filename: Name of the file (relative to output_dir or subdirectory)
            content: Content to write
            subdirectory: Optional subdirectory within output_dir (e.g., "models")
        """
        # Ensure output directory exists
        self.config.output_dir.mkdir(parents=True, exist_ok=True)

        if subdirectory:
            file_path = self.config.output_dir / subdirectory / filename
            file_path.parent.mkdir(parents=True, exist_ok=True)
        else:
            file_path = self.config.output_dir / filename

        file_path.write_text(content, encoding="utf-8")

    def generate(self, schema: Union[List[dict], FormKitSchema]) -> None:
        """
        Generate all code files from a FormKit schema.

        Generates:
        - models/<schema_name>.py: Django models (if schema_name is provided)
        - models/__init__.py: Imports from the generated model file
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
        all_groups_and_repeaters = [np for np in all_nodepaths if np.is_group or np.is_repeater]

        # Find root node (first non-child group)
        root_nodepath = next((np for np in all_groups_and_repeaters if not np.is_child and np.is_group), None)

        if not root_nodepath:
            # Fallback: use first group or repeater as root
            root_nodepath = next((np for np in all_groups_and_repeaters if np.is_group), None)
            if not root_nodepath:
                root_nodepath = all_groups_and_repeaters[0] if all_groups_and_repeaters else None

        if root_nodepath:
            # Filter to only include root and its descendants (repeaters and groups)
            root_classname = root_nodepath.classname
            nodepaths = [root_nodepath]  # Start with root

            # Add all descendants (children of root)
            # A descendant is any nodepath that starts with the root node
            for np in all_groups_and_repeaters:
                if np != root_nodepath:
                    # Check if this nodepath is a descendant of root
                    # A descendant has root as its first node in the path
                    if len(np.nodes) > len(root_nodepath.nodes):
                        # Check if the first nodes match the root's nodes
                        is_descendant = all(
                            np.nodes[i] == root_nodepath.nodes[i] for i in range(len(root_nodepath.nodes))
                        )
                        if is_descendant:
                            nodepaths.append(np)

            # Sort nodepaths so abstract bases come before classes that inherit from them
            # This ensures proper class definition order in models.py
            if self.config.merge_top_level_groups:
                # Separate abstract bases and concrete classes
                abstract_bases = [np for np in nodepaths if np.is_abstract_base]
                concrete_classes = [np for np in nodepaths if not np.is_abstract_base]
                # Put abstract bases first, then concrete classes
                nodepaths = abstract_bases + concrete_classes

            # Derive filename from root node classname
            models_filename = f"{schema_name_to_filename(root_classname)}.py"
            models_subdirectory = "models"

            # Generate models file
            models_code = self._generate_file("models.py.jinja2", models_filename, nodepaths)
            try:
                formatted_models_code = self.formatter.format(models_code)
            except FormattingError:
                formatted_models_code = models_code
            self._validate_code(formatted_models_code, models_filename)
            self._write_file(models_filename, formatted_models_code, subdirectory=models_subdirectory)

            # Generate __init__.py for models folder
            # Parse the generated models file to find all class definitions
            module_name = schema_name_to_filename(root_classname)
            init_code = f'"""Models for {root_classname} schema."""\n\n'

            try:
                tree = ast.parse(formatted_models_code)
                concrete_class_names = []
                # Only get top-level class definitions (not nested classes like Meta)
                # Iterate over tree.body to get only module-level classes
                for node in tree.body:
                    if isinstance(node, ast.ClassDef):
                        # Check if this class is abstract by looking for Meta class with abstract = True
                        is_abstract = False
                        for child in node.body:
                            if isinstance(child, ast.ClassDef) and child.name == "Meta":
                                # Check if Meta class has abstract = True
                                for meta_attr in child.body:
                                    if (
                                        isinstance(meta_attr, ast.Assign)
                                        and len(meta_attr.targets) == 1
                                        and isinstance(meta_attr.targets[0], ast.Name)
                                        and meta_attr.targets[0].id == "abstract"
                                    ):
                                        # Check if the value is True
                                        if isinstance(meta_attr.value, ast.Constant) and meta_attr.value.value is True:
                                            is_abstract = True
                                            break
                                if is_abstract:
                                    break

                        # Only include concrete (non-abstract) classes
                        if not is_abstract:
                            concrete_class_names.append(node.name)

                # Import only concrete classes from the generated file
                if concrete_class_names:
                    # Use a single import statement with all concrete classes
                    classes_str = ", ".join(concrete_class_names)
                    init_code += f"from .{module_name} import {classes_str}  # noqa: F401\n\n"
                    # Add __all__ to explicitly list exported classes
                    all_str = ", ".join(f'"{name}"' for name in concrete_class_names)
                    init_code += f"__all__ = [{all_str}]\n"
                else:
                    # Fallback: import everything (shouldn't happen in practice)
                    init_code += f"from .{module_name} import *  # noqa: F403, F405\n"
            except SyntaxError:
                # If parsing fails, import everything
                init_code += f"from .{module_name} import *  # noqa: F403, F405\n"

            try:
                formatted_init_code = self.formatter.format(init_code)
            except FormattingError:
                formatted_init_code = init_code
            self._validate_code(formatted_init_code, "__init__.py")
            self._write_file("__init__.py", formatted_init_code, subdirectory=models_subdirectory)
        else:
            # No root node found - fallback to original behavior
            nodepaths = all_groups_and_repeaters
            models_code = self._generate_file("models.py.jinja2", "models.py", nodepaths)
            try:
                formatted_models_code = self.formatter.format(models_code)
            except FormattingError:
                formatted_models_code = models_code
            self._validate_code(formatted_models_code, "models.py")
            self._write_file("models.py", formatted_models_code)

        # Define other files to generate: (template_name, output_filename)
        other_files_to_generate = [
            ("schemas.py.jinja2", "schemas.py"),
            ("schemas_in.py.jinja2", "schemas_in.py"),
            ("admin.py.jinja2", "admin.py"),
            ("api.py.jinja2", "api.py"),
        ]

        # Generate each file
        for template_name, output_filename in other_files_to_generate:
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
