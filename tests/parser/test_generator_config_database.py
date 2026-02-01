"""
Tests for GeneratorConfig with DatabaseNodePath as default.

These tests verify that the GeneratorConfig correctly uses DatabaseNodePath
as the default node_path_class and allows custom overrides.
"""

from formkit_ninja.parser.database_node_path import DatabaseNodePath
from formkit_ninja.parser.generator_config import GeneratorConfig
from formkit_ninja.parser.type_convert import NodePath


class TestGeneratorConfigDatabaseNodePath:
    """Tests for GeneratorConfig default node_path_class."""

    def test_default_node_path_class_is_database_node_path(self, tmp_path):
        """GeneratorConfig should use DatabaseNodePath by default."""
        config = GeneratorConfig(
            app_name="test",
            output_dir=tmp_path,
        )

        assert config.node_path_class == DatabaseNodePath

    def test_custom_node_path_class_can_be_specified(self, tmp_path):
        """Users should be able to override with custom NodePath class."""

        class CustomNodePath(NodePath):
            """Custom NodePath for testing."""

            pass

        config = GeneratorConfig(
            app_name="test",
            output_dir=tmp_path,
            node_path_class=CustomNodePath,
        )

        assert config.node_path_class == CustomNodePath
        assert config.node_path_class != DatabaseNodePath

    def test_legacy_nodepath_still_works(self, tmp_path):
        """Base NodePath class should still be usable."""
        config = GeneratorConfig(
            app_name="test",
            output_dir=tmp_path,
            node_path_class=NodePath,
        )

        assert config.node_path_class == NodePath
