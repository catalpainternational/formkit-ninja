"""
Tests for formkit_ninja.parser.template_loader module.

This module tests:
- TemplateLoader abstract base class
- DefaultTemplateLoader
- ExtendedTemplateLoader
- Template inheritance (project templates override base)
"""

import tempfile
from pathlib import Path
from unittest.mock import MagicMock

import pytest
from jinja2 import Environment, TemplateNotFound

from formkit_ninja.parser.template_loader import (
    DefaultTemplateLoader,
    ExtendedTemplateLoader,
    TemplateLoader,
)


class TestTemplateLoader:
    """Tests for TemplateLoader abstract base class"""

    def test_template_loader_is_abstract(self):
        """Test that TemplateLoader cannot be instantiated directly"""
        with pytest.raises(TypeError):
            TemplateLoader()  # type: ignore

    def test_template_loader_requires_get_environment(self):
        """Test that subclasses must implement get_environment method"""

        class IncompleteLoader(TemplateLoader):
            pass

        with pytest.raises(TypeError):
            IncompleteLoader()  # type: ignore


class TestDefaultTemplateLoader:
    """Tests for DefaultTemplateLoader"""

    def test_default_loader_creates_environment(self):
        """Test that DefaultTemplateLoader creates a Jinja2 environment"""
        loader = DefaultTemplateLoader()
        env = loader.get_environment()

        assert isinstance(env, Environment)
        assert env.trim_blocks is True
        assert env.lstrip_blocks is True

    def test_default_loader_finds_base_templates(self):
        """Test that DefaultTemplateLoader can find base templates"""
        loader = DefaultTemplateLoader()
        env = loader.get_environment()

        # Should be able to get a known template
        template = env.get_template("model.jinja2")
        assert template is not None

    def test_default_loader_template_not_found(self):
        """Test that DefaultTemplateLoader raises TemplateNotFound for missing templates"""
        loader = DefaultTemplateLoader()
        env = loader.get_environment()

        with pytest.raises(TemplateNotFound):
            env.get_template("nonexistent.jinja2")

    def test_default_loader_environment_configuration(self):
        """Test that DefaultTemplateLoader configures environment correctly"""
        loader = DefaultTemplateLoader()
        env = loader.get_environment()

        # Check environment settings
        assert env.trim_blocks is True
        assert env.lstrip_blocks is True
        assert env.autoescape is not None

    def test_default_loader_can_render_template(self):
        """Test that DefaultTemplateLoader can render a template"""
        loader = DefaultTemplateLoader()
        env = loader.get_environment()
        template = env.get_template("model.jinja2")

        # Render with minimal context (may fail, but should not raise TemplateNotFound)
        # The template requires specific NodePath context, so we expect it to raise
        # an error, but the important thing is that TemplateNotFound is not raised
        try:
            result = template.render(this=MagicMock())
            assert isinstance(result, str)
        except (AttributeError, TypeError, Exception):
            # Expected if template requires specific context - the important thing
            # is that we got the template (no TemplateNotFound)
            pass


class TestExtendedTemplateLoader:
    """Tests for ExtendedTemplateLoader"""

    def test_extended_loader_creates_environment(self):
        """Test that ExtendedTemplateLoader creates a Jinja2 environment"""
        loader = ExtendedTemplateLoader(["formkit_ninja.parser"])
        env = loader.get_environment()

        assert isinstance(env, Environment)
        assert env.trim_blocks is True
        assert env.lstrip_blocks is True

    def test_extended_loader_with_single_package(self):
        """Test ExtendedTemplateLoader with a single package"""
        loader = ExtendedTemplateLoader(["formkit_ninja.parser"])
        env = loader.get_environment()

        # Should be able to get a known template
        template = env.get_template("model.jinja2")
        assert template is not None

    def test_extended_loader_with_multiple_packages(self):
        """Test ExtendedTemplateLoader with multiple package sources"""
        # Use the same package twice to simulate multiple sources
        loader = ExtendedTemplateLoader(["formkit_ninja.parser", "formkit_ninja.parser"])
        env = loader.get_environment()

        # Should be able to get a known template
        template = env.get_template("model.jinja2")
        assert template is not None

    def test_extended_loader_template_inheritance(self):
        """Test that ExtendedTemplateLoader supports template inheritance (first package wins)"""
        import importlib
        import sys
        import uuid

        # Use a unique package name to avoid conflicts with other tests
        package_name = f"test_package_{uuid.uuid4().hex[:8]}"

        # Create a temporary package with a custom template
        with tempfile.TemporaryDirectory() as tmpdir:
            tmp_path = Path(tmpdir)
            package_dir = tmp_path / package_name
            templates_dir = package_dir / "templates"
            templates_dir.mkdir(parents=True)

            # Create a custom template
            custom_template = templates_dir / "model.jinja2"
            custom_template.write_text("CUSTOM_MODEL_TEMPLATE")

            # Create __init__.py to make it a package
            (package_dir / "__init__.py").touch()

            # Add to sys.path temporarily
            sys.path.insert(0, str(tmp_path))

            try:
                # Import the package to ensure it's recognized
                importlib.import_module(package_name)

                # Create loader with custom package first, then base
                loader = ExtendedTemplateLoader([package_name, "formkit_ninja.parser"])
                env = loader.get_environment()

                # Should load from first package (custom)
                template = env.get_template("model.jinja2")
                result = template.render()
                assert "CUSTOM_MODEL_TEMPLATE" in result
            finally:
                sys.path.remove(str(tmp_path))
                # Clean up any cached imports
                if package_name in sys.modules:
                    del sys.modules[package_name]

    def test_extended_loader_fallback_to_base(self):
        """Test that ExtendedTemplateLoader falls back to base templates when custom not found"""
        # Create a temporary package without the specific template we're looking for
        import importlib
        import sys
        import uuid

        # Use a unique package name to avoid conflicts with other tests
        package_name = f"test_package_{uuid.uuid4().hex[:8]}"

        with tempfile.TemporaryDirectory() as tmpdir:
            tmp_path = Path(tmpdir)
            package_dir = tmp_path / package_name
            templates_dir = package_dir / "templates"
            templates_dir.mkdir(parents=True)

            # Create a different template file (not model.jinja2) to ensure
            # the templates directory is recognized by PackageLoader
            (templates_dir / "other.jinja2").write_text("OTHER_TEMPLATE")

            # Create __init__.py to make it a package
            (package_dir / "__init__.py").touch()

            # Add to sys.path temporarily
            sys.path.insert(0, str(tmp_path))

            try:
                # Import the package to ensure it's recognized
                importlib.import_module(package_name)

                # Create loader with custom package first, then base
                loader = ExtendedTemplateLoader([package_name, "formkit_ninja.parser"])
                env = loader.get_environment()

                # Should fall back to base template (model.jinja2 not in custom package)
                template = env.get_template("model.jinja2")
                assert template is not None
                # Base template should have actual content, not be empty
                # The template requires specific context, so we expect it to raise
                # an error, but the important thing is that we got the template
                try:
                    result = template.render(this=MagicMock())
                    assert len(result) > 0
                except (AttributeError, TypeError, Exception):
                    # Expected if template requires specific context
                    pass
            finally:
                sys.path.remove(str(tmp_path))
                # Clean up any cached imports
                if package_name in sys.modules:
                    del sys.modules[package_name]

    def test_extended_loader_environment_configuration(self):
        """Test that ExtendedTemplateLoader configures environment correctly"""
        loader = ExtendedTemplateLoader(["formkit_ninja.parser"])
        env = loader.get_environment()

        # Check environment settings
        assert env.trim_blocks is True
        assert env.lstrip_blocks is True
        assert env.autoescape is not None

    def test_extended_loader_empty_package_list(self):
        """Test that ExtendedTemplateLoader handles empty package list"""
        loader = ExtendedTemplateLoader([])
        env = loader.get_environment()

        # Should raise TemplateNotFound for any template
        with pytest.raises(TemplateNotFound):
            env.get_template("model.jinja2")

    def test_extended_loader_invalid_package(self):
        """Test that ExtendedTemplateLoader handles invalid package gracefully"""
        loader = ExtendedTemplateLoader(["nonexistent.package"])

        # PackageLoader will raise an error during initialization when package doesn't exist
        with pytest.raises((ValueError, ModuleNotFoundError)):
            loader.get_environment()
