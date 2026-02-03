import pytest
from django.contrib.admin.sites import AdminSite

from formkit_ninja.admin_code_generation import CodeGenerationConfigAdmin
from formkit_ninja.code_generation_config import CodeGenerationConfig


@pytest.mark.django_db
def test_admin_code_preview():
    """Verify that admin preview methods return expected HTML."""
    config = CodeGenerationConfig.objects.create(formkit_type="datepicker", django_type="DateField", django_args={"null": True}, pydantic_type="date")

    admin = CodeGenerationConfigAdmin(CodeGenerationConfig, AdminSite())

    # Test Django preview
    django_html = admin.django_code_preview(config)
    assert "models.DateField" in django_html
    assert "null=True" in django_html

    # Test Pydantic preview
    pydantic_html = admin.pydantic_code_preview(config)
    assert ": date | None = None" in pydantic_html


@pytest.mark.django_db
def test_admin_code_preview_error():
    """Verify that admin preview handles errors gracefully."""
    # Invalid django_args (invalid identifier as key)
    config = CodeGenerationConfig.objects.create(
        formkit_type="text",
        django_args={"invalid identifier": "value"},  # This will produce "invalid identifier='value'" which is invalid syntax
    )

    admin = CodeGenerationConfigAdmin(CodeGenerationConfig, AdminSite())
    html = admin.django_code_preview(config)
    assert "Error generating preview" in html
