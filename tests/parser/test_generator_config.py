"""
Tests for formkit_ninja.parser.generator_config module.

This module tests:
- GeneratorConfig dataclass
- Field validation
- Required vs optional fields
- Path object support for output_dir
"""

from pathlib import Path

import pytest
from pydantic import ValidationError

from formkit_ninja.parser.generator_config import GeneratorConfig
from formkit_ninja.parser.type_convert import NodePath


class TestGeneratorConfig:
    """Tests for GeneratorConfig class"""

    def test_config_creation_with_valid_data(self):
        """Test that GeneratorConfig can be created with valid data"""
        output_dir = Path("/tmp/test_output")
        config = GeneratorConfig(
            app_name="test_app",
            output_dir=output_dir,
        )

        assert config.app_name == "test_app"
        assert config.output_dir == output_dir
        assert config.node_path_class == NodePath
        assert config.template_packages == []
        assert config.custom_imports == []

    def test_config_creation_with_string_output_dir(self):
        """Test that GeneratorConfig accepts string for output_dir"""
        config = GeneratorConfig(
            app_name="test_app",
            output_dir="/tmp/test_output",
        )

        assert isinstance(config.output_dir, Path)
        assert config.output_dir == Path("/tmp/test_output")

    def test_config_creation_with_path_output_dir(self):
        """Test that GeneratorConfig accepts Path object for output_dir"""
        output_dir = Path("/tmp/test_output")
        config = GeneratorConfig(
            app_name="test_app",
            output_dir=output_dir,
        )

        assert isinstance(config.output_dir, Path)
        assert config.output_dir == output_dir

    def test_config_creation_with_custom_node_path_class(self):
        """Test that GeneratorConfig accepts custom NodePath class"""

        class CustomNodePath(NodePath):
            pass

        config = GeneratorConfig(
            app_name="test_app",
            output_dir="/tmp/test_output",
            node_path_class=CustomNodePath,
        )

        assert config.node_path_class == CustomNodePath
        assert issubclass(config.node_path_class, NodePath)

    def test_config_creation_with_template_packages(self):
        """Test that GeneratorConfig accepts template_packages"""
        template_packages = ["myapp.templates", "other.templates"]
        config = GeneratorConfig(
            app_name="test_app",
            output_dir="/tmp/test_output",
            template_packages=template_packages,
        )

        assert config.template_packages == template_packages

    def test_config_creation_with_custom_imports(self):
        """Test that GeneratorConfig accepts custom_imports"""
        custom_imports = ["from myapp.models import BaseModel", "import os"]
        config = GeneratorConfig(
            app_name="test_app",
            output_dir="/tmp/test_output",
            custom_imports=custom_imports,
        )

        assert config.custom_imports == custom_imports

    def test_config_creation_with_all_fields(self):
        """Test that GeneratorConfig can be created with all fields"""

        class CustomNodePath(NodePath):
            pass

        output_dir = Path("/tmp/test_output")
        template_packages = ["myapp.templates"]
        custom_imports = ["from myapp.models import BaseModel"]

        config = GeneratorConfig(
            app_name="test_app",
            output_dir=output_dir,
            node_path_class=CustomNodePath,
            template_packages=template_packages,
            custom_imports=custom_imports,
        )

        assert config.app_name == "test_app"
        assert config.output_dir == output_dir
        assert config.node_path_class == CustomNodePath
        assert config.template_packages == template_packages
        assert config.custom_imports == custom_imports

    def test_config_validation_rejects_empty_app_name(self):
        """Test that GeneratorConfig validation rejects empty app_name"""
        with pytest.raises(ValueError, match="app_name cannot be empty"):
            GeneratorConfig(
                app_name="",
                output_dir="/tmp/test_output",
            )

    def test_config_validation_rejects_whitespace_only_app_name(self):
        """Test that GeneratorConfig validation rejects whitespace-only app_name"""
        with pytest.raises(ValueError, match="app_name cannot be empty"):
            GeneratorConfig(
                app_name="   ",
                output_dir="/tmp/test_output",
            )

    def test_config_validation_rejects_none_app_name(self):
        """Test that GeneratorConfig validation rejects None app_name"""
        with pytest.raises(ValidationError):
            GeneratorConfig(
                app_name=None,  # type: ignore
                output_dir="/tmp/test_output",
            )

    def test_config_validation_rejects_invalid_node_path_class(self):
        """Test that GeneratorConfig validation rejects non-NodePath class"""
        with pytest.raises(ValidationError) as exc_info:
            GeneratorConfig(
                app_name="test_app",
                output_dir="/tmp/test_output",
                node_path_class=str,  # type: ignore
            )
        assert "node_path_class" in str(exc_info.value)

    def test_config_validation_rejects_none_node_path_class(self):
        """Test that GeneratorConfig validation rejects None node_path_class"""
        with pytest.raises(ValidationError) as exc_info:
            GeneratorConfig(
                app_name="test_app",
                output_dir="/tmp/test_output",
                node_path_class=None,  # type: ignore
            )
        assert "node_path_class" in str(exc_info.value)

    def test_config_validation_rejects_invalid_template_packages_type(self):
        """Test that GeneratorConfig validation rejects non-list template_packages"""
        with pytest.raises(ValidationError) as exc_info:
            GeneratorConfig(
                app_name="test_app",
                output_dir="/tmp/test_output",
                template_packages="not_a_list",  # type: ignore
            )
        assert "template_packages" in str(exc_info.value)

    def test_config_validation_rejects_invalid_custom_imports_type(self):
        """Test that GeneratorConfig validation rejects non-list custom_imports"""
        with pytest.raises(ValidationError) as exc_info:
            GeneratorConfig(
                app_name="test_app",
                output_dir="/tmp/test_output",
                custom_imports="not_a_list",  # type: ignore
            )
        assert "custom_imports" in str(exc_info.value)

    def test_config_validation_rejects_non_string_in_template_packages(self):
        """Test that GeneratorConfig validation rejects non-string items in template_packages"""
        with pytest.raises(ValidationError) as exc_info:
            GeneratorConfig(
                app_name="test_app",
                output_dir="/tmp/test_output",
                template_packages=["valid", 123],  # type: ignore
            )
        assert "template_packages" in str(exc_info.value)

    def test_config_validation_rejects_non_string_in_custom_imports(self):
        """Test that GeneratorConfig validation rejects non-string items in custom_imports"""
        with pytest.raises(ValidationError) as exc_info:
            GeneratorConfig(
                app_name="test_app",
                output_dir="/tmp/test_output",
                custom_imports=["valid", 123],  # type: ignore
            )
        assert "custom_imports" in str(exc_info.value)

    def test_config_default_values(self):
        """Test that GeneratorConfig has correct default values"""
        config = GeneratorConfig(
            app_name="test_app",
            output_dir="/tmp/test_output",
        )

        assert config.node_path_class == NodePath
        assert config.template_packages == []
        assert config.custom_imports == []

    def test_config_empty_template_packages(self):
        """Test that GeneratorConfig accepts empty template_packages list"""
        config = GeneratorConfig(
            app_name="test_app",
            output_dir="/tmp/test_output",
            template_packages=[],
        )

        assert config.template_packages == []

    def test_config_empty_custom_imports(self):
        """Test that GeneratorConfig accepts empty custom_imports list"""
        config = GeneratorConfig(
            app_name="test_app",
            output_dir="/tmp/test_output",
            custom_imports=[],
        )

        assert config.custom_imports == []

    def test_config_accepts_merge_top_level_groups(self):
        """Test that GeneratorConfig accepts merge_top_level_groups parameter"""
        config = GeneratorConfig(
            app_name="testapp",
            output_dir=Path("/tmp"),
            merge_top_level_groups=True,
        )
        assert config.merge_top_level_groups is True

        config_default = GeneratorConfig(
            app_name="testapp",
            output_dir=Path("/tmp"),
        )
        assert config_default.merge_top_level_groups is False
