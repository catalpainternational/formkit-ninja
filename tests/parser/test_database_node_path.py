"""
Tests for DatabaseNodePath.

Tests database-driven configuration for code generation,
including priority cascade and settings fallback.
"""

import pytest

from formkit_ninja.code_generation_config import CodeGenerationConfig
from formkit_ninja.formkit_schema import DatePickerNode, TextNode
from formkit_ninja.parser.database_node_path import DatabaseNodePath


@pytest.mark.django_db
class TestDatabaseNodePath:
    """Tests for DatabaseNodePath configuration lookup."""

    def test_db_config_overrides_pydantic_type(self):
        """Database config should override default Pydantic type."""
        # Create config for datepicker
        CodeGenerationConfig.objects.create(
            formkit_type="datepicker",
            pydantic_type="datetime",  # Override default 'date'
            is_active=True,
        )

        node = DatePickerNode(name="test_date")
        nodepath = DatabaseNodePath(node)

        assert nodepath.to_pydantic_type() == "datetime"

    def test_db_config_node_name_priority(self):
        """Node name match should have higher priority than formkit_type."""
        # Create type-level config
        CodeGenerationConfig.objects.create(
            formkit_type="text",
            django_type="TextField",
            is_active=True,
        )

        # Create node-specific config (higher priority)
        CodeGenerationConfig.objects.create(
            formkit_type="text",
            node_name="district",
            django_type="ForeignKey",
            is_active=True,
        )

        # Node with matching name
        node1 = TextNode(name="district")
        nodepath1 = DatabaseNodePath(node1)
        assert nodepath1.to_django_type() == "ForeignKey"

        # Node without matching name
        node2 = TextNode(name="other_field")
        nodepath2 = DatabaseNodePath(node2)
        assert nodepath2.to_django_type() == "TextField"

    def test_db_config_combined_formkit_and_options_match(self):
        """Config with both formkit_type and options_pattern should match when both criteria met."""
        # Create config for select fields with IDA options
        CodeGenerationConfig.objects.create(
            formkit_type="select",
            options_pattern="$ida(",
            pydantic_type="int",
            priority=10,  # Higher priority
            is_active=True,
        )

        # Also create a general select config
        CodeGenerationConfig.objects.create(
            formkit_type="select",
            pydantic_type="str",
            priority=0,
            is_active=True,
        )

        # Node matching both formkit and options
        from formkit_ninja.formkit_schema import SelectNode

        node1 = SelectNode(name="status", options="$ida(yesno)")
        nodepath1 = DatabaseNodePath(node1)
        # Should match the combined config due to options pattern
        assert nodepath1.to_pydantic_type() == "int"

        # Node with formkit but not matching options
        node2 = SelectNode(name="other_field", options="regular_options")
        nodepath2 = DatabaseNodePath(node2)
        # Should match general select config
        assert nodepath2.to_pydantic_type() == "str"

    def test_inactive_configs_ignored(self):
        """Inactive configs should be ignored."""
        CodeGenerationConfig.objects.create(
            formkit_type="text",
            node_name="test",
            django_type="ForeignKey",
            is_active=False,  # Inactive
        )

        node = TextNode(name="test")
        nodepath = DatabaseNodePath(node)

        # Should fall back to default
        assert nodepath.to_django_type() == "TextField"

    def test_priority_ordering(self):
        """Higher priority configs should be checked first."""
        # Create low priority config
        CodeGenerationConfig.objects.create(
            formkit_type="text",
            node_name="field1",
            django_type="TextField",
            priority=0,
            is_active=True,
        )

        # Create high priority config
        CodeGenerationConfig.objects.create(
            formkit_type="text",
            node_name="field1",
            django_type="ForeignKey",
            priority=10,
            is_active=True,
        )

        node = TextNode(name="field1")
        nodepath = DatabaseNodePath(node)

        # Should use high priority config
        assert nodepath.to_django_type() == "ForeignKey"

    def test_django_args_from_db(self):
        """Django args should be loaded from database config."""
        CodeGenerationConfig.objects.create(
            formkit_type="text",
            node_name="district",
            django_type="ForeignKey",
            django_args={
                "to": "pnds_data.zDistrict",
                "on_delete": "models.CASCADE",
                "null": True,
            },
            is_active=True,
        )

        node = TextNode(name="district")
        nodepath = DatabaseNodePath(node)

        args = nodepath.to_django_args()
        assert "pnds_data.zDistrict" in args
        assert "on_delete=models.CASCADE" in args
        assert "null=True" in args

    def test_validators_from_db(self):
        """Validators should be loaded from database config."""
        CodeGenerationConfig.objects.create(
            formkit_type="text",
            node_name="email",
            validators=["@field_validator('email')", "def validate_email(cls, v): ..."],
            is_active=True,
        )

        node = TextNode(name="email")
        nodepath = DatabaseNodePath(node)

        validators = nodepath.get_validators()
        assert len(validators) == 2
        assert "@field_validator('email')" in validators

    def test_extra_imports_from_db(self):
        """Extra imports should be loaded from database config."""
        CodeGenerationConfig.objects.create(
            formkit_type="text",
            node_name="currency",
            extra_imports=["from decimal import Decimal"],
            is_active=True,
        )

        node = TextNode(name="currency")
        nodepath = DatabaseNodePath(node)

        imports = nodepath.get_extra_imports()
        assert "from decimal import Decimal" in imports

    def test_config_caching(self):
        """Config lookups should be cached."""
        CodeGenerationConfig.objects.create(
            formkit_type="text",
            node_name="field1",
            django_type="ForeignKey",
            is_active=True,
        )

        node = TextNode(name="field1")
        nodepath = DatabaseNodePath(node)

        # First lookup (cache miss)
        type1 = nodepath.to_django_type()

        # Second lookup (cache hit)
        type2 = nodepath.to_django_type()

        assert type1 == type2 == "ForeignKey"

    def test_default_fallback_when_no_config(self):
        """Should use default converters when no config found."""
        node = TextNode(name="unconfigured_field")
        nodepath = DatabaseNodePath(node)

        # Should use default converter
        assert nodepath.to_pydantic_type() == "str"
        assert nodepath.to_django_type() == "TextField"


@pytest.mark.django_db
class TestDatabaseNodePathSettings:
    """Tests for Django settings integration."""

    def test_settings_fallback_type_mappings(self, settings):
        """Settings TYPE_MAPPINGS should be used when no DB config."""
        settings.FORMKIT_NINJA = {
            "TYPE_MAPPINGS": {
                "datepicker": {
                    "pydantic_type": "datetime",
                    "django_type": "DateTimeField",
                }
            }
        }

        node = DatePickerNode(name="test_date")
        nodepath = DatabaseNodePath(node)

        assert nodepath.to_pydantic_type() == "datetime"
        assert nodepath.to_django_type() == "DateTimeField"

    def test_settings_name_mappings_priority(self, settings):
        """NAME_MAPPINGS should have higher priority than TYPE_MAPPINGS."""
        settings.FORMKIT_NINJA = {
            "TYPE_MAPPINGS": {"text": {"django_type": "TextField"}},
            "NAME_MAPPINGS": {"district": {"django_type": "ForeignKey"}},
        }

        # Node with matching name
        node1 = TextNode(name="district")
        nodepath1 = DatabaseNodePath(node1)
        assert nodepath1.to_django_type() == "ForeignKey"

        # Node without matching name
        node2 = TextNode(name="other")
        nodepath2 = DatabaseNodePath(node2)
        assert nodepath2.to_django_type() == "TextField"

    def test_settings_django_args_dict(self, settings):
        """Django args as dict in settings should be converted to string."""
        settings.FORMKIT_NINJA = {
            "NAME_MAPPINGS": {
                "district": {
                    "django_args": {
                        "to": "pnds_data.zDistrict",
                        "on_delete": "models.CASCADE",
                        "null": True,
                    }
                }
            }
        }

        node = TextNode(name="district")
        nodepath = DatabaseNodePath(node)

        args = nodepath.to_django_args()
        assert "pnds_data.zDistrict" in args
        assert "on_delete=models.CASCADE" in args
        assert "null=True" in args

    def test_db_config_overrides_settings(self, settings):
        """Database config should override settings."""
        settings.FORMKIT_NINJA = {"TYPE_MAPPINGS": {"text": {"django_type": "TextField"}}}

        CodeGenerationConfig.objects.create(
            formkit_type="text",
            node_name="field1",
            django_type="ForeignKey",
            is_active=True,
        )

        node = TextNode(name="field1")
        nodepath = DatabaseNodePath(node)

        # DB config should override settings
        assert nodepath.to_django_type() == "ForeignKey"
