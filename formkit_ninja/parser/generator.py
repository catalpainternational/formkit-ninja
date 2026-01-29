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
        root_classname: str | None = None,
    ) -> str:
        """
        Generate a single file from a template.

        Args:
            template_name: Name of the Jinja2 template
            output_filename: Name of the output file (for reference)
            nodepaths: List of NodePath instances to render
            root_classname: Optional root node classname for imports

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
            root_classname=root_classname,
        )

        return code

    def _generate_per_schema_file(
        self,
        template_name: str,
        filename: str,
        subdirectory: str,
        nodepaths: List[NodePath],
        root_classname: str | None = None,
    ) -> None:
        """
        Generate a per-schema file in a subdirectory.

        Args:
            template_name: Name of the Jinja2 template to use
            filename: Name of the output file
            subdirectory: Subdirectory within output_dir (e.g., "schemas", "admin")
            nodepaths: List of NodePath instances to generate code from
            root_classname: Optional root node classname for imports
        """
        # Generate code from template
        code = self._generate_file(template_name, filename, nodepaths, root_classname=root_classname)

        # Format code (may raise FormattingError)
        try:
            formatted_code = self.formatter.format(code)
        except FormattingError:
            # If formatting fails, use unformatted code
            formatted_code = code

        # Validate code syntax
        self._validate_code(formatted_code, filename)

        # Write to file in subdirectory
        self._write_file(filename, formatted_code, subdirectory=subdirectory)

    def _extract_classes_from_code(self, code: str, file_type: str) -> List[str]:
        """
        Extract class/function names from generated code based on file type.

        Args:
            code: Generated Python code as string
            file_type: Type of file ("models", "schemas", "schemas_in", "admin", "api")

        Returns:
            List of class/function/variable names to import
        """
        try:
            tree = ast.parse(code)
        except SyntaxError:
            return []

        extracted = []

        for node in tree.body:
            if file_type == "models":
                # Extract concrete (non-abstract) classes
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
                        extracted.append(node.name)
            elif file_type == "schemas":
                # Extract classes ending with "Schema" that inherit from Schema
                if isinstance(node, ast.ClassDef) and node.name.endswith("Schema"):
                    # Check if class inherits from Schema
                    for base in node.bases:
                        if isinstance(base, ast.Name) and base.id == "Schema":
                            extracted.append(node.name)
                            break
                        elif isinstance(base, ast.Attribute):
                            # Handle cases like "schema_out.Schema"
                            if isinstance(base.value, ast.Name) and base.attr == "Schema":
                                extracted.append(node.name)
                                break
            elif file_type == "schemas_in":
                # Extract all classes (BaseModel subclasses)
                if isinstance(node, ast.ClassDef):
                    extracted.append(node.name)
            elif file_type == "admin":
                # Extract classes ending with "Admin" or "Inline" (exclude ReadOnlyInline)
                if isinstance(node, ast.ClassDef):
                    if (node.name.endswith("Admin") or node.name.endswith("Inline")) and node.name != "ReadOnlyInline":
                        extracted.append(node.name)
            elif file_type == "api":
                # Extract functions and router variable
                if isinstance(node, ast.FunctionDef):
                    extracted.append(node.name)
                elif isinstance(node, ast.Assign):
                    # Check if assigning to "router"
                    for target in node.targets:
                        if isinstance(target, ast.Name) and target.id == "router":
                            extracted.append("router")

        return extracted

    def _generate_init_file(
        self,
        subdirectory: str,
        module_name: str,
        file_type: str,
        generated_file_content: str,
        existing_init_content: str | None = None,
    ) -> str:
        """
        Generate or update __init__.py file for a subdirectory.

        Args:
            subdirectory: Subdirectory name (e.g., "schemas", "admin")
            module_name: Name of the module file (without .py extension)
            file_type: Type of file ("models", "schemas", "schemas_in", "admin", "api")
            generated_file_content: Content of the generated per-schema file
            existing_init_content: Existing __init__.py content if updating

        Returns:
            Generated __init__.py content as string
        """
        # Extract classes/functions from generated file
        extracted_items = self._extract_classes_from_code(generated_file_content, file_type)

        if not extracted_items:
            # No items to import, return existing content or empty
            return existing_init_content or ""

        # Parse existing __init__.py to preserve imports
        existing_import_lines = []
        existing_all = []
        if existing_init_content:
            # Extract existing import statements and __all__
            try:
                tree = ast.parse(existing_init_content)
                for node in tree.body:
                    if isinstance(node, ast.ImportFrom) and node.module:
                        # Check if it's a relative import (level > 0 means relative)
                        is_relative = node.level > 0
                        if is_relative:
                            # Relative import - preserve the original line
                            imported_names = [alias.name for alias in node.names]
                            names_str = ", ".join(imported_names)
                            # Reconstruct the line with proper relative import syntax
                            # node.module doesn't include the dot, so we add it
                            module_path = "." * node.level + (node.module or "")
                            # Only add if not from current module
                            if not module_path.endswith(f".{module_name}") and module_path != f".{module_name}":
                                line = f"from {module_path} import {names_str}  # noqa: F401"
                                existing_import_lines.append(line)
                    elif isinstance(node, ast.Assign):
                        # Check for __all__ assignment
                        for target in node.targets:
                            if isinstance(target, ast.Name) and target.id == "__all__":
                                if isinstance(node.value, (ast.List, ast.Tuple)):
                                    existing_all = [
                                        (
                                            elt.value
                                            if isinstance(elt, ast.Constant)
                                            else (elt.s if isinstance(elt, ast.Str) else str(elt))
                                        )
                                        for elt in node.value.elts
                                        if isinstance(elt, (ast.Constant, ast.Str))
                                    ]
            except SyntaxError:
                # If parsing fails, try to extract imports manually
                for line in existing_init_content.split("\n"):
                    stripped = line.strip()
                    if stripped.startswith("from .") and "import" in stripped:
                        # Check if it's not from current module
                        if f".{module_name}" not in stripped:
                            existing_import_lines.append(stripped)
                    elif stripped.startswith("__all__"):
                        # Extract __all__ values manually - simple regex-like extraction
                        import re

                        match = re.search(r"\[(.*?)\]", stripped)
                        if match:
                            all_content = match.group(1)
                            # Extract quoted strings
                            all_items = re.findall(r'"([^"]+)"', all_content)
                            existing_all.extend(all_items)

        # Build new __init__.py content
        init_lines = []

        # Add docstring if this is a new file
        if not existing_init_content:
            init_lines.append(f'"""{subdirectory.capitalize()} for all schemas."""')
            init_lines.append("")

        # Special handling for API router merging
        if file_type == "api":
            # Collect all module names that have routers
            schema_modules = set()
            all_functions = []

            # Parse existing imports to get module names
            import re

            for import_line in existing_import_lines:
                # Extract module name from "from .module import router, ..."
                match = re.search(r"from \.(\w+) import", import_line)
                if match and "router" in import_line:
                    schema_modules.add(match.group(1))
                # Extract function names from imports
                if "router" not in import_line:
                    # This is a function import, preserve it
                    all_functions.append(import_line)

            # Add current module
            if extracted_items:
                has_router = "router" in extracted_items
                function_items = [item for item in extracted_items if item != "router"]

                if has_router:
                    schema_modules.add(module_name)

                # Add function imports for current module
                if function_items:
                    items_str = ", ".join(function_items)
                    all_functions.append(f"from .{module_name} import {items_str}  # noqa: F401")

            # Import all functions
            for func_import in all_functions:
                init_lines.append(func_import)

            # Create combined router
            init_lines.append("")
            init_lines.append("from ninja import Router")
            init_lines.append("")
            init_lines.append('router = Router(tags=["forms"])')

            # Add router merging for all schema routers
            for schema_module in sorted(schema_modules):
                init_lines.append(f"from .{schema_module} import router as {schema_module}_router")
                init_lines.append(f'router.add_router("", {schema_module}_router)')

            # Build __all__ list (include router and all functions)
            all_items = existing_all.copy()
            all_items.extend(extracted_items)
            # Remove duplicates while preserving order
            seen = set()
            unique_all = []
            for item in all_items:
                if item not in seen:
                    seen.add(item)
                    unique_all.append(item)

            if unique_all:
                init_lines.append("")
                all_str = ", ".join(f'"{item}"' for item in unique_all)
                init_lines.append(f"__all__ = [{all_str}]")
        else:
            # Standard handling for other file types
            # Add existing imports (excluding the current module)
            for import_line in existing_import_lines:
                if f".{module_name}" not in import_line:
                    init_lines.append(import_line)

            # Add import for current module
            if extracted_items:
                items_str = ", ".join(extracted_items)
                init_lines.append(f"from .{module_name} import {items_str}  # noqa: F401")

            # Build __all__ list
            all_items = existing_all.copy()
            all_items.extend(extracted_items)
            # Remove duplicates while preserving order
            seen = set()
            unique_all = []
            for item in all_items:
                if item not in seen:
                    seen.add(item)
                    unique_all.append(item)

            if unique_all:
                init_lines.append("")
                all_str = ", ".join(f'"{item}"' for item in unique_all)
                init_lines.append(f"__all__ = [{all_str}]")

        return "\n".join(init_lines)

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

            # Deduplicate nodepaths by classname to prevent duplicate class generation
            seen_classnames = set()
            unique_nodepaths = []
            for np in nodepaths:
                if np.classname not in seen_classnames:
                    seen_classnames.add(np.classname)
                    unique_nodepaths.append(np)
            nodepaths = unique_nodepaths

            # Derive filename from root node classname
            models_filename = f"{schema_name_to_filename(root_classname)}.py"
            models_subdirectory = "models"

            # Generate models file
            models_code = self._generate_file(
                "models.py.jinja2", models_filename, nodepaths, root_classname=root_classname
            )
            try:
                formatted_models_code = self.formatter.format(models_code)
            except FormattingError:
                formatted_models_code = models_code
            self._validate_code(formatted_models_code, models_filename)
            self._write_file(models_filename, formatted_models_code, subdirectory=models_subdirectory)

            # Generate __init__.py for models folder using the new method
            module_name = schema_name_to_filename(root_classname)

            # Read existing __init__.py if it exists
            init_file_path = self.config.output_dir / models_subdirectory / "__init__.py"
            existing_init_content = None
            if init_file_path.exists():
                existing_init_content = init_file_path.read_text()

            # Generate or update __init__.py
            init_content = self._generate_init_file(
                subdirectory=models_subdirectory,
                module_name=module_name,
                file_type="models",
                generated_file_content=formatted_models_code,
                existing_init_content=existing_init_content,
            )

            # Format and write __init__.py
            try:
                formatted_init_code = self.formatter.format(init_content)
            except FormattingError:
                formatted_init_code = init_content
            self._validate_code(formatted_init_code, "__init__.py")
            self._write_file("__init__.py", formatted_init_code, subdirectory=models_subdirectory)
        else:
            # No root node found - fallback to original behavior
            nodepaths = all_groups_and_repeaters
            # Deduplicate nodepaths by classname to prevent duplicate class generation
            seen_classnames = set()
            unique_nodepaths = []
            for np in nodepaths:
                if np.classname not in seen_classnames:
                    seen_classnames.add(np.classname)
                    unique_nodepaths.append(np)
            nodepaths = unique_nodepaths
            models_code = self._generate_file("models.py.jinja2", "models.py", nodepaths, root_classname=None)
            try:
                formatted_models_code = self.formatter.format(models_code)
            except FormattingError:
                formatted_models_code = models_code
            self._validate_code(formatted_models_code, "models.py")
            self._write_file("models.py", formatted_models_code)

        # Define file mappings: (template_name, subdirectory, file_type)
        file_mappings = [
            ("schemas.py.jinja2", "schemas", "schemas"),
            ("schemas_in.py.jinja2", "schemas_in", "schemas_in"),
            ("admin.py.jinja2", "admin", "admin"),
            ("api.py.jinja2", "api", "api"),
        ]

        # Generate each file in its subdirectory
        for template_name, subdirectory, file_type in file_mappings:
            if root_nodepath:
                # Generate per-schema file in subdirectory
                schema_filename = f"{schema_name_to_filename(root_classname)}.py"
                self._generate_per_schema_file(
                    template_name=template_name,
                    filename=schema_filename,
                    subdirectory=subdirectory,
                    nodepaths=nodepaths,
                    root_classname=root_classname,
                )

                # Read the generated file content
                generated_file_path = self.config.output_dir / subdirectory / schema_filename
                generated_file_content = generated_file_path.read_text()

                # Read existing __init__.py if it exists
                init_file_path = self.config.output_dir / subdirectory / "__init__.py"
                existing_init_content = None
                if init_file_path.exists():
                    existing_init_content = init_file_path.read_text()

                # Generate or update __init__.py
                init_content = self._generate_init_file(
                    subdirectory=subdirectory,
                    module_name=schema_name_to_filename(root_classname),
                    file_type=file_type,
                    generated_file_content=generated_file_content,
                    existing_init_content=existing_init_content,
                )

                # Write __init__.py
                try:
                    formatted_init = self.formatter.format(init_content)
                except FormattingError:
                    formatted_init = init_content
                self._validate_code(formatted_init, "__init__.py")
                self._write_file("__init__.py", formatted_init, subdirectory=subdirectory)
            else:
                # Fallback: no root node - use original behavior (write to root)
                output_filename = f"{subdirectory}.py"
                code = self._generate_file(template_name, output_filename, nodepaths, root_classname=None)
                try:
                    formatted_code = self.formatter.format(code)
                except FormattingError:
                    formatted_code = code
                self._validate_code(formatted_code, output_filename)
                self._write_file(output_filename, formatted_code)
