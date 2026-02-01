"""
Tests for CodeGenerationConfig admin interface.

Tests the custom admin interface including:
- Custom widgets and form validation
- List display and filtering
- Search functionality
- Fieldsets organization
"""

import json

import pytest
from django.contrib.admin import site
from django.contrib.auth.models import User
from django.test import RequestFactory

from formkit_ninja.admin_code_generation import (
    CodeGenerationConfigAdmin,
    CodeGenerationConfigAdminForm,
    PrettyJSONWidget,
)
from formkit_ninja.code_generation_config import CodeGenerationConfig


class TestPrettyJSONWidget:
    """Tests for the PrettyJSONWidget."""

    def test_widget_formats_dict_nicely(self):
        """Widget should format dict as indented JSON."""
        widget = PrettyJSONWidget()
        value = {"key": "value", "nested": {"a": 1, "b": 2}}

        formatted = widget.format_value(value)

        # Should be pretty-printed JSON
        assert '"key": "value"' in formatted
        assert '"nested":' in formatted
        # Should have indentation
        assert "  " in formatted or "\t" in formatted

    def test_widget_formats_json_string_nicely(self):
        """Widget should parse and re-format JSON strings."""
        widget = PrettyJSONWidget()
        value = '{"key":"value","nested":{"a":1}}'

        formatted = widget.format_value(value)

        # Should be pretty-printed
        assert '"key": "value"' in formatted
        assert "  " in formatted or "\t" in formatted

    def test_widget_handles_empty_value(self):
        """Widget should handle empty/None values gracefully."""
        widget = PrettyJSONWidget()

        assert widget.format_value(None) == ""
        assert widget.format_value("") == ""

    def test_widget_handles_invalid_json(self):
        """Widget should return invalid JSON as-is."""
        widget = PrettyJSONWidget()
        value = "not valid json"

        formatted = widget.format_value(value)
        assert formatted == value


@pytest.mark.django_db
class TestCodeGenerationConfigAdminForm:
    """Tests for the admin form."""

    def test_form_requires_formkit_type(self):
        """Form should require formkit_type."""
        form = CodeGenerationConfigAdminForm(
            data={
                "formkit_type": "",
                "pydantic_type": "int",
            }
        )

        assert not form.is_valid()
        assert "formkit_type" in str(form.errors)

    def test_form_requires_at_least_one_override(self):
        """Form should require at least one override field."""
        form = CodeGenerationConfigAdminForm(
            data={
                "formkit_type": "text",
                # No overrides provided
            }
        )

        assert not form.is_valid()
        assert "override" in str(form.errors).lower()

    def test_form_accepts_valid_config(self):
        """Form should accept valid configuration."""
        form = CodeGenerationConfigAdminForm(
            data={
                "formkit_type": "text",
                "node_name": "district",
                "django_type": "ForeignKey",
                "django_args": json.dumps({"to": "app.District", "on_delete": "models.CASCADE"}),
                "priority": 10,
                "is_active": True,
            }
        )

        assert form.is_valid(), form.errors

    def test_form_uses_pretty_json_widget(self):
        """Form should use PrettyJSONWidget for django_args."""
        form = CodeGenerationConfigAdminForm()

        assert isinstance(form.fields["django_args"].widget, PrettyJSONWidget)


@pytest.mark.django_db
class TestCodeGenerationConfigAdmin:
    """Tests for the admin interface."""

    @pytest.fixture
    def admin_user(self):
        """Create an admin user."""
        return User.objects.create_superuser(
            username="admin",
            email="admin@test.com",
            password="password123",
        )

    @pytest.fixture
    def admin_site(self):
        """Get the admin instance."""
        return CodeGenerationConfigAdmin(CodeGenerationConfig, site)

    @pytest.fixture
    def request_factory(self):
        """Create a request factory."""
        return RequestFactory()

    def test_admin_registered(self):
        """CodeGenerationConfig should be registered in admin."""
        assert CodeGenerationConfig in site._registry
        assert isinstance(site._registry[CodeGenerationConfig], CodeGenerationConfigAdmin)

    def test_list_display_shows_key_fields(self, admin_site):
        """List display should show important fields."""
        list_display = admin_site.list_display

        assert "formkit_type" in list_display
        assert "node_name" in list_display
        assert "priority" in list_display
        assert "is_active" in list_display

    def test_list_filter_available(self, admin_site):
        """Admin should provide useful filters."""
        list_filter = admin_site.list_filter

        assert "is_active" in list_filter
        assert "formkit_type" in list_filter

    def test_search_fields_configured(self, admin_site):
        """Admin should allow searching key fields."""
        search_fields = admin_site.search_fields

        assert "formkit_type" in search_fields
        assert "node_name" in search_fields
        assert "pydantic_type" in search_fields

    def test_fieldsets_organized(self, admin_site, request_factory, admin_user):
        """Admin should organize fields into logical sections."""
        request = request_factory.get("/admin/")
        request.user = admin_user

        fieldsets = admin_site.get_fieldsets(request)

        # Should have multiple fieldsets
        assert len(fieldsets) > 1

        # Check for key sections
        fieldset_names = [fs[0] for fs in fieldsets]
        assert "Matching Criteria" in fieldset_names
        assert "Type Overrides" in fieldset_names

    def test_summary_display_shows_formkit_type(self, admin_site):
        """Summary should show formkit_type."""
        config = CodeGenerationConfig(formkit_type="text")

        summary = admin_site.summary(config)

        assert "text" in summary

    def test_summary_display_shows_node_name(self, admin_site):
        """Summary should show node_name when present."""
        config = CodeGenerationConfig(formkit_type="text", node_name="district")

        summary = admin_site.summary(config)

        assert "text" in summary
        assert "district" in summary

    def test_summary_display_shows_options_pattern(self, admin_site):
        """Summary should show options_pattern when present."""
        config = CodeGenerationConfig(
            formkit_type="select",
            options_pattern="$ida(",
        )

        summary = admin_site.summary(config)

        assert "select" in summary
        assert "$ida(" in summary

    def test_has_pydantic_override_indicator(self, admin_site):
        """Admin should show if Pydantic type is overridden."""
        config_with = CodeGenerationConfig(formkit_type="text", pydantic_type="int")
        config_without = CodeGenerationConfig(formkit_type="text")

        assert admin_site.has_pydantic_override(config_with) is True
        assert admin_site.has_pydantic_override(config_without) is False

    def test_has_django_override_indicator(self, admin_site):
        """Admin should show if Django config is overridden."""
        config_type = CodeGenerationConfig(formkit_type="text", django_type="ForeignKey")
        config_args = CodeGenerationConfig(formkit_type="text", django_args={"null": True})
        config_none = CodeGenerationConfig(formkit_type="text")

        assert admin_site.has_django_override(config_type) is True
        assert admin_site.has_django_override(config_args) is True
        assert admin_site.has_django_override(config_none) is False

    def test_ordering_by_priority(self, admin_site):
        """Admin should order by priority descending."""
        ordering = admin_site.ordering

        assert "-priority" in ordering or ordering[0] == "-priority"
