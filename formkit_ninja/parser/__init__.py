"""
Parser module for FormKit schema conversion.

This module provides:
- NodePath: Path-like wrapper for FormKit node traversal
- TypeConverter system: Extensible type conversion from FormKit nodes to Pydantic types
- CodeFormatter: Code formatting using ruff
- CodeGenerator: Code generation from FormKit schemas
"""

from formkit_ninja.parser.converters import (
    BooleanConverter,
    CurrencyConverter,
    DateConverter,
    NumberConverter,
    TextConverter,
    TypeConverter,
    TypeConverterRegistry,
    UuidConverter,
    default_registry,
)
from formkit_ninja.parser.formatter import CodeFormatter, FormattingError
from formkit_ninja.parser.generator import CodeGenerator
from formkit_ninja.parser.generator_config import GeneratorConfig
from formkit_ninja.parser.plugins import (
    GeneratorPlugin,
    PluginRegistry,
    get_default_registry,
    register_plugin,
)
from formkit_ninja.parser.template_loader import (
    DefaultTemplateLoader,
    ExtendedTemplateLoader,
    TemplateLoader,
)
from formkit_ninja.parser.type_convert import NodePath, make_valid_identifier

__all__ = [
    "NodePath",
    "make_valid_identifier",
    "TypeConverter",
    "TypeConverterRegistry",
    "TextConverter",
    "NumberConverter",
    "DateConverter",
    "BooleanConverter",
    "UuidConverter",
    "CurrencyConverter",
    "default_registry",
    "TemplateLoader",
    "DefaultTemplateLoader",
    "ExtendedTemplateLoader",
    "CodeFormatter",
    "FormattingError",
    "CodeGenerator",
    "GeneratorConfig",
    "GeneratorPlugin",
    "PluginRegistry",
    "register_plugin",
    "get_default_registry",
]
