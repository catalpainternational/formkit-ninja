"""
Template loader abstraction for code generation.

This module provides:
- TemplateLoader: Abstract base class for template loading
- DefaultTemplateLoader: Loads templates from formkit_ninja.parser.templates
- ExtendedTemplateLoader: Supports multiple package sources with template inheritance
"""

from abc import ABC, abstractmethod
from typing import List

from jinja2 import ChoiceLoader, Environment, PackageLoader, select_autoescape


class TemplateLoader(ABC):
    """
    Abstract base class for template loaders.

    Subclasses must implement get_environment() to return a configured Jinja2 Environment.
    """

    @abstractmethod
    def get_environment(self) -> Environment:
        """
        Get a configured Jinja2 Environment.

        Returns:
            Environment: A Jinja2 Environment instance configured with appropriate
                         template loaders and settings.
        """
        pass


class DefaultTemplateLoader(TemplateLoader):
    """
    Default template loader that loads templates from formkit_ninja.parser.templates.

    This loader provides access to the base templates included with formkit-ninja.
    """

    def get_environment(self) -> Environment:
        """
        Get a Jinja2 Environment configured to load from formkit_ninja.parser.templates.

        Returns:
            Environment: A Jinja2 Environment with PackageLoader for base templates.
        """
        return Environment(
            loader=PackageLoader("formkit_ninja.parser", "templates"),
            autoescape=select_autoescape(),
            trim_blocks=True,
            lstrip_blocks=True,
        )


class ExtendedTemplateLoader(TemplateLoader):
    """
    Extended template loader that supports multiple package sources.

    Templates are loaded from packages in order, with earlier packages taking precedence.
    This allows projects to override base templates with custom versions.

    The loader looks for a "templates" subdirectory within each package.

    Args:
        template_packages: List of package names (e.g., ["myapp", "formkit_ninja.parser"]).
                          Templates are expected to be in a "templates" subdirectory of each package.
    """

    def __init__(self, template_packages: List[str]) -> None:
        """
        Initialize ExtendedTemplateLoader.

        Args:
            template_packages: List of package names where templates can be found.
                              Templates are expected in a "templates" subdirectory.
                              Packages are checked in order, first match wins.
        """
        self.template_packages = template_packages

    def get_environment(self) -> Environment:
        """
        Get a Jinja2 Environment configured to load from multiple package sources.

        Returns:
            Environment: A Jinja2 Environment with ChoiceLoader for multiple sources.
        """
        loaders = [PackageLoader(package, "templates") for package in self.template_packages]

        return Environment(
            loader=ChoiceLoader(loaders),
            autoescape=select_autoescape(),
            trim_blocks=True,
            lstrip_blocks=True,
        )
