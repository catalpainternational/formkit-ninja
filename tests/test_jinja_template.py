import os
from textwrap import dedent

from jinja2 import Environment, PackageLoader, Template, select_autoescape

from formkit_ninja.parser.type_convert import NodePath


def strip_empty_lines(text: str):
    return os.linesep.join([s for s in text.splitlines() if s])


def get_env():
    return Environment(
        loader=PackageLoader("formkit_ninja.parser"),
        autoescape=select_autoescape(),
        trim_blocks=True,
        lstrip_blocks=True,
    )


def test_nested_group_node(nested_group_node: NodePath):
    assert nested_group_node.is_repeater is False
    assert nested_group_node.classname == "Bar"
    assert nested_group_node.classname_schema == "BarSchema"
    assert nested_group_node.django_type == "OneToOneField"
    assert nested_group_node.is_group is True
    assert nested_group_node.is_child is False


def test_number_node_field(number_node: NodePath):
    assert number_node.is_repeater is False


def test_pd_number_node_field(pydantic_class_template: Template, number_node: NodePath):
    text = pydantic_class_template.render(this=number_node)
    expect = "    foonum: int\n"
    assert text.strip() == dedent(expect).strip()


def test_pd_group_node_field(pydantic_class_template: Template, group_node: NodePath):
    text = pydantic_class_template.render(this=group_node)
    expect = "class Foo(BaseModel):\n    foonum: int | None = None\n"
    assert text.strip() == dedent(expect).strip()


def test_pd_nested_group_node_field(
    pydantic_class_template: Template, nested_group_node: NodePath
):
    text = pydantic_class_template.render(this=nested_group_node)
    expect = """
        class BarFoo(BaseModel):
            foonum: int | None = None
        class Bar(BaseModel):
            foo: BarFoo | None = None
        """
    assert text.strip() == dedent(expect).strip()


def test_group_node_field(django_class_template: Template, group_node: NodePath):
    text = django_class_template.render(this=group_node)
    expect = "class Foo(models.Model):\n    foonum = models.IntegerField(null=True, blank=True)\n"
    assert text.strip() == dedent(expect).strip()


def test_nested_group_node_field(
    django_class_template: Template, nested_group_node: NodePath
):
    text = django_class_template.render(this=nested_group_node)
    expect = """
        class BarFoo(models.Model):
            foonum = models.IntegerField(null=True, blank=True)
        class Bar(models.Model):
            foo = models.OneToOneField(BarFoo, on_delete=models.CASCADE)
        """
    assert text.strip() == dedent(expect).strip()


def test_admin_group_node_field(admin_template: Template, group_node: NodePath):
    text = admin_template.render(this=group_node)
    expect = """
        @admin.register(models.Foo)
        class FooAdmin(admin.ModelAdmin):
            list_display = [
                "foonum",
            ]
            readonly_fields = [
                "foonum",
            ]
    """
    assert text.strip() == dedent(expect).strip()


def test_admin_py_group_node_field(admin_py_template: Template, group_node: NodePath):
    text = admin_py_template.render(nodepaths=[group_node])
    expect = '''
"""
Don't make changes to this code directly
Instead, make changes to the template and re-generate this file
"""

from django.contrib import admin
from . import models

class ReadOnlyInline(admin.TabularInline):
    def has_change_permission(self, request, obj=None):
        return False
    def has_add_permission(self, request, obj=None):
        return False
    def has_delete_permission(self, request, obj=None):
        return False

@admin.register(models.Foo)
class FooAdmin(admin.ModelAdmin):
    list_display = [
        "foonum",
    ]
    readonly_fields = [
        "foonum",
    ]
    '''
    assert text.strip() == dedent(expect).strip()


def test_admin_nested_group_node_field(
    admin_template: Template, nested_group_node: NodePath
):
    text = admin_template.render(this=nested_group_node)
    expect = """
        @admin.register(models.BarFoo)
        class BarFooAdmin(admin.ModelAdmin):
            list_display = [
                "foonum",
            ]
            readonly_fields = [
                "foonum",
            ]
        @admin.register(models.Bar)
        class BarAdmin(admin.ModelAdmin):
            list_display = [
                "foo",
            ]
            readonly_fields = [
                "foo",
            ]
        """
    assert text.strip() == dedent(expect).strip()


def test_api_nested_group_node_field(
    api_template: Template, nested_group_node: NodePath
):
    text = api_template.render(this=nested_group_node)
    expect = """
        @router.get("barfoo", response=list[schema_out.BarFooSchema], exclude_none=True)
        def barfoo(request):
            queryset = models.BarFoo.objects.all()
            return queryset
        @router.get("bar", response=list[schema_out.BarSchema], exclude_none=True)
        def bar(request):
            queryset = models.Bar.objects.all()
            queryset = queryset.select_related(
                "foo",
            )
            return queryset
        """
    assert text.strip() == dedent(expect).strip()


def test_api_nested_repeater_node_field(
    api_template: Template, nested_repeater_node: NodePath
):
    text = api_template.render(this=nested_repeater_node)
    expect = """
        @router.get("barfoo", response=list[schema_out.BarFooSchema], exclude_none=True)
        def barfoo(request):
            queryset = models.BarFoo.objects.all()
            return queryset
        @router.get("bar", response=list[schema_out.BarSchema], exclude_none=True)
        def bar(request):
            queryset = models.Bar.objects.all()
            queryset = queryset.prefetch_related(
                "foo",
            )
            return queryset
        """
    assert text.strip() == dedent(expect).strip()


def test_schema_out_nested_group_node_field(
    schema_out_template: Template, nested_group_node: NodePath
):
    text = schema_out_template.render(this=nested_group_node)
    expect = """
        class BarFooSchema(Schema):
            foonum: int | None = None
        class BarSchema(Schema):
            foo: BarFoo | None = None
    """
    assert text.strip() == dedent(expect).strip()
