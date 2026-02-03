import os
from textwrap import dedent

import pytest
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


@pytest.fixture()
def number_node():
    return NodePath.from_obj(
        {
            "$formkit": "number",
            "name": "foonum",
        }
    )


@pytest.fixture()
def group_node():
    return NodePath.from_obj(
        {
            "$formkit": "group",
            "name": "foo",
            "children": [
                {
                    "$formkit": "number",
                    "name": "foonum",
                }
            ],
        }
    )


@pytest.fixture()
def nested_group_node():
    return NodePath.from_obj(
        {
            "$formkit": "group",
            "name": "bar",
            "children": [
                {
                    "$formkit": "group",
                    "name": "foo",
                    "children": [
                        {
                            "$formkit": "number",
                            "name": "foonum",
                        }
                    ],
                }
            ],
        }
    )


@pytest.fixture()
def nested_repeater_node():
    return NodePath.from_obj(
        {
            "$formkit": "group",
            "name": "bar",
            "children": [
                {
                    "$formkit": "repeater",
                    "name": "foo",
                    "children": [
                        {
                            "$formkit": "number",
                            "name": "foonum",
                        }
                    ],
                }
            ],
        }
    )


@pytest.fixture()
def django_class_template():
    env = get_env()
    template = env.get_template("model.jinja2")
    return template


@pytest.fixture()
def admin_template():
    env = get_env()
    template = env.get_template("admin.jinja2")
    return template


@pytest.fixture()
def admin_py_template():
    """Test the entire admin file including import header"""
    env = get_env()
    template = env.get_template("admin.py.jinja2")
    return template


@pytest.fixture()
def api_template():
    env = get_env()
    template = env.get_template("api.jinja2")
    return template


@pytest.fixture()
def schema_out_template():
    env = get_env()
    template = env.get_template("schema.jinja2")
    return template


@pytest.fixture()
def pydantic_class_template():
    env = get_env()
    template = env.get_template("basemodel.jinja2")
    return template


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
    expect = "    foonum: int | None = None\n"
    assert text.strip() == dedent(expect).strip()


def test_pd_group_node_field(pydantic_class_template: Template, group_node: NodePath):
    text = pydantic_class_template.render(this=group_node)
    expect = "class FooSchema(BaseModel):\n    foonum: int | None = None\n"
    assert text.strip() == dedent(expect).strip()


def test_pd_nested_group_node_field(pydantic_class_template: Template, nested_group_node: NodePath):
    text = pydantic_class_template.render(this=nested_group_node)
    expect = """
        class BarSchema(BaseModel):
            foo: BarFooSchema | None = None
        """
    assert text.strip() == dedent(expect).strip()


def test_group_node_field(django_class_template: Template, group_node: NodePath):
    text = django_class_template.render(this=group_node)
    expect = """class Foo(models.Model):
    \"\"\"
    Generated from FormKit Group node: foo
    \"\"\"
    submission = models.OneToOneField("formkit_ninja.SeparatedSubmission", on_delete=models.CASCADE, primary_key=True, related_name="+")  # Added via extra_attribs hook
    foonum = models.IntegerField(null=True, blank=True)  # From: foo > foonum
"""
    assert text.strip() == dedent(expect).strip()


def test_nested_group_node_field(django_class_template: Template, nested_group_node: NodePath):
    text = django_class_template.render(this=nested_group_node)
    expect = """
        class Bar(models.Model):
            \"\"\"
            Generated from FormKit Group node: bar
            \"\"\"
            submission = models.OneToOneField("formkit_ninja.SeparatedSubmission", on_delete=models.CASCADE, primary_key=True, related_name="+")  # Added via extra_attribs hook
            foo = models.OneToOneField(BarFoo, on_delete=models.CASCADE)  # From: bar > foo
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
from .. import models

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


def test_admin_nested_group_node_field(admin_template: Template, nested_group_node: NodePath):
    text = admin_template.render(this=nested_group_node)
    expect = """
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


def test_api_nested_group_node_field(api_template: Template, nested_group_node: NodePath):
    text = api_template.render(this=nested_group_node)
    expect = """
        @router.get("bar", response=list[schema_out.BarSchema], exclude_none=True)
        def bar(request):
            # Schema includes fields: foo 
            queryset = models.Bar.objects.all()
            queryset = queryset.select_related(
                "foo",
            )
            return queryset


        @router.post("bar", response=schema_out.BarSchema)
        def create_bar(request, payload: schema_in.BarSchema):
            data = payload.dict(exclude_unset=True)
            
            # Create a Submission entry
            submission = Submission.objects.create(
                fields=data,
                form_type="Bar",
            )
            
            # The signal handlers should have run synchronously.
            # We need to find the specific model instance that was created.
            # 1. Find the parent SeparatedSubmission
            try:
                # For the root object, repeater_parent is None and form_type matches
                sep_sub = SeparatedSubmission.objects.get(
                    submission=submission,
                    form_type="Bar",
                    repeater_parent__isnull=True
                )
                
                # 2. Get the model instance linked to it
                instance = models.Bar.objects.get(submission=sep_sub)
                return instance
                
            except (SeparatedSubmission.DoesNotExist, models.Bar.DoesNotExist):
                # Fallback or error handling
                # If signal failed or async, we might return something else or 202 Accepted
                # But here we expect synchronous success
                raise Exception("Submission processing failed or model not created.")
        """
    expected_clean = "\n".join([line.rstrip() for line in dedent(expect).strip().splitlines()])
    actual_clean = "\n".join([line.rstrip() for line in text.strip().splitlines()])
    assert actual_clean == expected_clean


def test_api_nested_repeater_node_field(api_template: Template, nested_repeater_node: NodePath):
    text = api_template.render(this=nested_repeater_node)
    expect = """
        @router.get("bar", response=list[schema_out.BarSchema], exclude_none=True)
        def bar(request):
            # Schema includes fields: 
            queryset = models.Bar.objects.all()
            queryset = queryset.prefetch_related(
                "foo",
            )
            return queryset


        @router.post("bar", response=schema_out.BarSchema)
        def create_bar(request, payload: schema_in.BarSchema):
            data = payload.dict(exclude_unset=True)
            
            # Create a Submission entry
            submission = Submission.objects.create(
                fields=data,
                form_type="Bar",
            )
            
            # The signal handlers should have run synchronously.
            # We need to find the specific model instance that was created.
            # 1. Find the parent SeparatedSubmission
            try:
                # For the root object, repeater_parent is None and form_type matches
                sep_sub = SeparatedSubmission.objects.get(
                    submission=submission,
                    form_type="Bar",
                    repeater_parent__isnull=True
                )
                
                # 2. Get the model instance linked to it
                instance = models.Bar.objects.get(submission=sep_sub)
                return instance
                
            except (SeparatedSubmission.DoesNotExist, models.Bar.DoesNotExist):
                # Fallback or error handling
                # If signal failed or async, we might return something else or 202 Accepted
                # But here we expect synchronous success
                raise Exception("Submission processing failed or model not created.")
        """
    expected_clean = "\n".join([line.rstrip() for line in dedent(expect).strip().splitlines()])
    actual_clean = "\n".join([line.rstrip() for line in text.strip().splitlines()])
    assert actual_clean == expected_clean


def test_schema_out_nested_group_node_field(schema_out_template: Template, nested_group_node: NodePath):
    text = schema_out_template.render(this=nested_group_node)
    expect = """
        class BarSchema(Schema):
            foo: BarFooSchema | None = None
    """
    assert text.strip() == dedent(expect).strip()
