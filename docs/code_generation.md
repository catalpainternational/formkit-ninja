# Code Generation Guide

formkit-ninja provides a powerful code generation system that automatically creates Django models, Pydantic schemas, admin classes, and API endpoints from your FormKit schemas.

## Table of Contents

- [Basic Usage](#basic-usage)
- [Programmatic Usage](#programmatic-usage)
- [Extensibility](#extensibility)
  - [Custom Type Converters](#custom-type-converters)
  - [Custom NodePath](#custom-nodepath)
  - [Plugin System](#plugin-system)
  - [Custom Templates](#custom-templates)

## Basic Usage

### Management Command

The simplest way to generate code is using the Django management command:

```bash
./manage.py generate_code --app-name myapp --output-dir ./myapp/generated
```

**Arguments:**

- `--app-name` (required): Name of the Django app
- `--output-dir` (required): Directory where generated code will be written
- `--schema-label` (optional): Generate code for a specific schema label. If omitted, generates for all schemas

**Example:**

```bash
# Generate code for all schemas
./manage.py generate_code --app-name forms --output-dir ./forms/generated

# Generate code for a specific schema
./manage.py generate_code --app-name forms --output-dir ./forms/generated --schema-label "Contact Form"
```

### Generated Files

The code generator creates the following files in the output directory:

1. **models.py** - Django models for groups and repeaters
2. **schemas.py** - Django Ninja output schemas
3. **schemas_in.py** - Django Ninja input schemas (Pydantic BaseModel)
4. **admin.py** - Django admin classes
5. **api.py** - Django Ninja API endpoints

## Programmatic Usage

You can also use the code generator programmatically:

```python
from pathlib import Path
from formkit_ninja.parser import (
    CodeGenerator,
    GeneratorConfig,
    DefaultTemplateLoader,
    CodeFormatter,
)

# Create configuration
config = GeneratorConfig(
    app_name="myapp",
    output_dir=Path("./myapp/generated"),
)

# Initialize components
template_loader = DefaultTemplateLoader()
formatter = CodeFormatter()
generator = CodeGenerator(
    config=config,
    template_loader=template_loader,
    formatter=formatter,
)

# Generate code from a schema (list of dicts or FormKitSchema object)
schema = [...]  # Your FormKit schema
generator.generate(schema)
```

## Extensibility

formkit-ninja provides multiple extension points for customizing code generation to fit your project's needs.

### Custom Type Converters

Type converters determine how FormKit nodes are converted to Pydantic types. You can create custom converters for new node types or override existing behavior.

**Example: Custom Converter for a "currency" Node**

```python
from formkit_ninja.parser import TypeConverter, TypeConverterRegistry
from formkit_ninja.formkit_schema import FormKitType

class CurrencyConverter:
    """Converter for currency FormKit nodes."""
    
    def can_convert(self, node: FormKitType) -> bool:
        """Check if this converter can handle the node."""
        return hasattr(node, "formkit") and node.formkit == "currency"
    
    def to_pydantic_type(self, node: FormKitType) -> str:
        """Convert the node to a Pydantic type string."""
        return "Decimal"

# Register the converter
registry = TypeConverterRegistry()
registry.register(CurrencyConverter(), priority=10)  # Higher priority = checked first
```

**Using a Custom Registry:**

```python
from formkit_ninja.parser import NodePath, TypeConverterRegistry

# Create registry with custom converters
registry = TypeConverterRegistry()
registry.register(CurrencyConverter(), priority=10)

# Use with NodePath
nodepath = NodePath(node, type_converter_registry=registry)
pydantic_type = nodepath.to_pydantic_type()
```

### Custom NodePath

You can subclass `NodePath` to add project-specific logic, validators, imports, or filter clauses.

**Example: Custom NodePath with Validators**

```python
from formkit_ninja.parser import NodePath
from formkit_ninja.formkit_schema import FormKitType

class CustomNodePath(NodePath):
    """Custom NodePath with project-specific extensions."""
    
    def get_validators(self) -> list[str]:
        """Return custom validators for this node."""
        validators = []
        
        # Add currency validator for currency fields
        if hasattr(self.node, "formkit") and self.node.formkit == "currency":
            validators.append("@field_validator('currency_field')")
            validators.append("def validate_currency(cls, v):")
            validators.append("    if v < 0:")
            validators.append("        raise ValueError('Currency must be positive')")
            validators.append("    return v")
        
        return validators
    
    def get_extra_imports(self) -> list[str]:
        """Return extra imports for schema files."""
        imports = []
        
        if hasattr(self.node, "formkit") and self.node.formkit == "currency":
            imports.append("from decimal import Decimal")
            imports.append("from pydantic import field_validator")
        
        return imports
    
    def get_custom_imports(self) -> list[str]:
        """Return custom imports for models.py."""
        imports = []
        
        if hasattr(self.node, "formkit") and self.node.formkit == "currency":
            imports.append("from django.db.models import DecimalField")
        
        return imports
    
    @property
    def filter_clause(self) -> str:
        """Return custom filter clause class name."""
        # Override default "SubStatusFilter" with your custom filter
        return "CustomStatusFilter"
```

**Using Custom NodePath:**

```python
from formkit_ninja.parser import GeneratorConfig

# Configure generator to use custom NodePath
config = GeneratorConfig(
    app_name="myapp",
    output_dir=Path("./myapp/generated"),
    node_path_class=CustomNodePath,  # Use custom class
)
```

### Plugin System

The plugin system allows you to bundle multiple extensions (converters, templates, NodePath) together in a single plugin class.

**Example: Complete Plugin**

```python
from formkit_ninja.parser import (
    GeneratorPlugin,
    TypeConverterRegistry,
    NodePath,
    register_plugin,
)
from typing import Type

class MyProjectPlugin(GeneratorPlugin):
    """Plugin for my project's custom extensions."""
    
    def register_converters(self, registry: TypeConverterRegistry) -> None:
        """Register custom type converters."""
        registry.register(CurrencyConverter(), priority=10)
        registry.register(CustomDateConverter(), priority=5)
    
    def get_template_packages(self) -> list[str]:
        """Return template packages (checked in order)."""
        return [
            "myapp.templates",  # Project templates (highest priority)
            "formkit_ninja.parser",  # Base templates (fallback)
        ]
    
    def extend_node_path(self) -> Type[NodePath] | None:
        """Return custom NodePath subclass."""
        return CustomNodePath

# Register the plugin (automatically registered when imported)
@register_plugin
class MyProjectPlugin(GeneratorPlugin):
    # ... implementation ...
```

**Using Plugins Programmatically:**

```python
from formkit_ninja.parser import (
    PluginRegistry,
    GeneratorConfig,
    ExtendedTemplateLoader,
    CodeGenerator,
    CodeFormatter,
)

# Create plugin registry
registry = PluginRegistry()
registry.register(MyProjectPlugin())

# Get NodePath class from plugins
node_path_class = registry.get_node_path_class() or NodePath

# Collect template packages
template_packages = registry.collect_template_packages()

# Create configuration
config = GeneratorConfig(
    app_name="myapp",
    output_dir=Path("./myapp/generated"),
    node_path_class=node_path_class,
    template_packages=template_packages,
)

# Create template loader with plugin packages
template_loader = ExtendedTemplateLoader(template_packages)

# Create generator
generator = CodeGenerator(
    config=config,
    template_loader=template_loader,
    formatter=CodeFormatter(),
)

# Apply plugin converters to registry
converter_registry = TypeConverterRegistry()
registry.apply_converters(converter_registry)
```

### Custom Templates

You can override the default Jinja2 templates by providing your own template packages.

**Template Structure:**

```
myapp/
  templates/
    models.py.jinja2
    schemas.py.jinja2
    schemas_in.py.jinja2
    admin.py.jinja2
    api.py.jinja2
```

**Using Custom Templates:**

```python
from formkit_ninja.parser import ExtendedTemplateLoader

# Templates are checked in order (first match wins)
template_loader = ExtendedTemplateLoader([
    "myapp.templates",  # Your custom templates
    "formkit_ninja.parser",  # Base templates (fallback)
])
```

**Template Variables:**

Templates receive the following variables:

- `nodepaths`: List of NodePath instances (groups and repeaters)
- `app_name`: Django app name
- `config`: GeneratorConfig instance

**Example: Custom Template Override**

```jinja2
{# myapp/templates/models.py.jinja2 #}
from django.db import models
{% for nodepath in nodepaths %}
class {{ nodepath.classname }}(models.Model):
    # Your custom model definition
    pass
{% endfor %}
```

## Default Type Converters

formkit-ninja includes the following default type converters:

- **TextConverter**: Handles `text`, `textarea`, `email`, `password`, `hidden`, `select`, `dropdown`, `radio`, `autocomplete` → `str`
- **NumberConverter**: Handles `number`, `tel` → `int` or `float` (based on `step` attribute)
- **DateConverter**: Handles `datepicker` → `datetime`, `date` → `date`
- **BooleanConverter**: Handles `checkbox` → `bool`
- **UuidConverter**: Handles `uuid` → `UUID`
- **CurrencyConverter**: Handles `currency` → `Decimal`

These are automatically registered in the default registry and checked in registration order.

## NodePath Extension Points

The `NodePath` class provides several extension points that can be overridden in subclasses:

- **`get_validators()`**: Return list of validator strings for Pydantic schemas
- **`get_extra_imports()`**: Return extra imports for schema files (`schemas.py`, `schemas_in.py`)
- **`get_custom_imports()`**: Return custom imports for `models.py`
- **`filter_clause`**: Property returning filter clause class name for admin/API (default: `"SubStatusFilter"`)
- **`extra_attribs`**: Property returning list of extra field definitions for models.py
- **`to_django_type()`**: Method returning Django field type string
- **`to_django_args()`**: Method returning Django field arguments string

## Extension Points Reference

### `extra_attribs` Property

Add extra fields to generated models. This is useful for adding relationships, custom fields, or project-specific fields.

**Example: Adding Submission Relationship**

```python
class PartisipaNodePath(NodePath):
    @property
    def extra_attribs(self):
        """Add submission relationship to all models."""
        attribs = []
        if self.is_group or self.is_repeater:
            if self.is_group and not self.is_child:
                # Parent model: use as primary key
                attribs.append(
                    'submission = models.OneToOneField('
                    '"form_submission.SeparatedSubmission", '
                    'on_delete=models.CASCADE, primary_key=True)'
                )
            else:
                # Repeater model: nullable
                attribs.append(
                    'submission = models.OneToOneField('
                    '"form_submission.SeparatedSubmission", '
                    'on_delete=models.CASCADE, null=True)'
                )
        return attribs
```

### `to_django_type()` Method

Override the Django field type for specific nodes. Useful for converting TextFields to ForeignKeys based on business logic.

**Example: ForeignKey Detection for Option Models**

```python
class PartisipaNodePath(NodePath):
    def to_django_type(self) -> str:
        """Convert option-based fields to ForeignKeys."""
        # Check if this node references an option model
        if hasattr(self.node, 'option_group') and self.node.option_group:
            # Map option group to Partisipa model
            model_name = self._map_option_group_to_model(self.node.option_group)
            if model_name:
                return f"ForeignKey({model_name}, ...)"
        return super().to_django_type()
    
    def _map_option_group_to_model(self, option_group):
        """Map option group to Django model name."""
        # Partisipa-specific mapping logic
        mappings = {
            'cycle': 'ida_options.Cycle',
            'project': 'ida_options.Project',
            'output': 'ida_options.Output',
            'munisipiu': 'ida_options.Munisipiu',
            # ... more mappings
        }
        return mappings.get(option_group.lower())
```

### `to_django_args()` Method

Override Django field arguments. Useful for adding constraints, custom on_delete behavior, or other field options.

**Example: UUID Unique Constraint**

```python
class PartisipaNodePath(NodePath):
    def to_django_args(self) -> str:
        """Add unique=True to UUID fields."""
        if self.to_pydantic_type() == "UUID":
            return "editable=False, unique=True, null=True, blank=True"
        return super().to_django_args()
```

## Partisipa-Specific Extensions Example

Here's a complete example of a Partisipa-specific NodePath that implements all the customizations:

```python
from formkit_ninja.parser import NodePath
from formkit_ninja.formkit_schema import FormKitType

class PartisipaNodePath(NodePath):
    """
    Partisipa-specific NodePath extensions.
    
    Adds:
    - Submission relationship to all models
    - ForeignKey detection for option models
    - UUID unique constraint
    - Primary key customization
    """
    
    @property
    def extra_attribs(self):
        """Add submission relationship to all models."""
        attribs = []
        if self.is_group or self.is_repeater:
            if self.is_group and not self.is_child:
                # Parent model: use submission as primary key
                attribs.append(
                    'submission = models.OneToOneField('
                    '"form_submission.SeparatedSubmission", '
                    'on_delete=models.CASCADE, primary_key=True)'
                )
            else:
                # Repeater model: nullable submission
                attribs.append(
                    'submission = models.OneToOneField('
                    '"form_submission.SeparatedSubmission", '
                    'on_delete=models.CASCADE, null=True)'
                )
        return attribs
    
    def to_django_type(self) -> str:
        """Convert option-based fields to ForeignKeys."""
        # Check if this node references an option model
        if hasattr(self.node, 'option_group') and self.node.option_group:
            model_name = self._map_option_group_to_model(self.node.option_group)
            if model_name:
                return f"ForeignKey({model_name}, ...)"
        return super().to_django_type()
    
    def to_django_args(self) -> str:
        """Add unique=True to UUID fields."""
        if self.to_pydantic_type() == "UUID":
            return "editable=False, unique=True, null=True, blank=True"
        return super().to_django_args()
    
    def _map_option_group_to_model(self, option_group):
        """Map option group to Partisipa Django model."""
        # Partisipa-specific mapping
        mappings = {
            'cycle': 'ida_options.Cycle',
            'project': 'ida_options.Project',
            'output': 'ida_options.Output',
            'munisipiu': 'ida_options.Munisipiu',
            'postu_administrativu': 'ida_options.PostuAdministrativu',
            'suku': 'ida_options.Suku',
        }
        return mappings.get(option_group.lower())
```

**Using PartisipaNodePath:**

```python
from formkit_ninja.parser import GeneratorConfig

config = GeneratorConfig(
    app_name="partisipa",
    output_dir=Path("./partisipa/generated"),
    node_path_class=PartisipaNodePath,  # Use Partisipa extensions
)
```

## Best Practices

1. **Use Plugins for Multiple Extensions**: If you need custom converters, templates, and NodePath extensions, bundle them in a plugin.

2. **Priority Order**: When registering converters, use higher priorities for more specific converters. Converters are checked in priority order (higher first).

3. **Template Inheritance**: Use `ExtendedTemplateLoader` with your project templates first, then base templates, to allow selective overrides.

4. **Type Hints**: Always use type hints in your custom code for better IDE support and type checking.

5. **Testing**: Test your custom converters and NodePath extensions with the same test patterns used in formkit-ninja's test suite.

## Examples

See the test files in `tests/parser/` for more examples:

- `test_converters.py` - Type converter examples
- `test_plugins.py` - Plugin system examples
- `test_generator.py` - Code generation examples
- `test_template_loader.py` - Template loading examples
