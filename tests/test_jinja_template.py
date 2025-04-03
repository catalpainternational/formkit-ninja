import ast
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
    tree = ast.parse(text)

    class_def: ast.ClassDef = tree.body[0]
    body: ast.Assign = class_def.body[0]
    
    field_def: ast.Name = body.targets[0]
    field_call: ast.Call = body.value

    assert class_def.name == "Foo"
    attribute: ast.Attribute = class_def.bases[0]
    assert attribute.attr == "Model"
    attribute_value: ast.Name = attribute.value
    assert attribute_value.id == "models"
    
    assert field_def.id == 'foonum'

    assert field_call.keywords[0].arg == "null"
    assert field_call.func.attr == "IntegerField"


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


def test_checkbox_node_field(pydantic_class_template: Template, checkbox_node: NodePath):
    text = pydantic_class_template.render(this=checkbox_node)
    expect = "    is_active: bool\n"
    assert text.strip() == dedent(expect).strip()


def test_currency_node_field(pydantic_class_template: Template, currency_node: NodePath):
    text = pydantic_class_template.render(this=currency_node)
    expect = "    amount: Decimal\n"
    assert text.strip() == dedent(expect).strip()


def test_uuid_node_field(pydantic_class_template: Template, uuid_node: NodePath):
    text = pydantic_class_template.render(this=uuid_node)
    expect = "    id: UUID\n"
    assert text.strip() == dedent(expect).strip()


def test_date_node_field(pydantic_class_template: Template, date_node: NodePath):
    text = pydantic_class_template.render(this=date_node)
    expect = "    birth_date: date\n"
    assert text.strip() == dedent(expect).strip()


def test_datepicker_node_field(pydantic_class_template: Template, datepicker_node: NodePath):
    text = pydantic_class_template.render(this=datepicker_node)
    expect = "    meeting_time: datetime\n"
    assert text.strip() == dedent(expect).strip()


def test_tel_node_field(pydantic_class_template: Template, tel_node: NodePath):
    text = pydantic_class_template.render(this=tel_node)
    expect = "    phone: int\n"
    assert text.strip() == dedent(expect).strip()


def test_select_node_field(pydantic_class_template: Template, select_node: NodePath):
    text = pydantic_class_template.render(this=select_node)
    expect = "    country: str\n"
    assert text.strip() == dedent(expect).strip()


def test_hidden_node_field(pydantic_class_template: Template, hidden_node: NodePath):
    text = pydantic_class_template.render(this=hidden_node)
    expect = "    token: str\n"
    assert text.strip() == dedent(expect).strip()


def test_checkbox_node_django_field(django_class_template: Template, checkbox_node: NodePath):
    text = "{node.django_attrib_name} = models.{node.django_type}({node.django_args})".format(node =checkbox_node)
    expect = "is_active = models.BooleanField(null=True, blank=True)\n"
    assert text.strip() == dedent(expect).strip()


def test_currency_node_django_field(django_class_template: Template, currency_node: NodePath):
    text = "{node.django_attrib_name} = models.{node.django_type}({node.django_args})".format(node =currency_node)
    expect = "amount = models.DecimalField(max_digits=20, decimal_places=2, null=True, blank=True)\n"
    assert text.strip() == dedent(expect).strip()


def test_uuid_node_django_field(django_class_template: Template, uuid_node: NodePath):
    text = "{node.django_attrib_name} = models.{node.django_type}({node.django_args})".format(node =uuid_node)
    expect = "id = models.UUIDField(editable=False, null=True, blank=True)\n"
    assert text.strip() == dedent(expect).strip()


def test_date_node_django_field(django_class_template: Template, date_node: NodePath):
    text = "{node.django_attrib_name} = models.{node.django_type}({node.django_args})".format(node =date_node)
    expect = "birth_date = models.DateField(null=True, blank=True)\n"
    assert text.strip() == dedent(expect).strip()


def test_datepicker_node_django_field(django_class_template: Template, datepicker_node: NodePath):
    text = "{node.django_attrib_name} = models.{node.django_type}({node.django_args})".format(node =datepicker_node)
    expect = "meeting_time = models.DateTimeField(null=True, blank=True)\n"
    assert text.strip() == dedent(expect).strip()


def test_tel_node_django_field(django_class_template: Template, tel_node: NodePath):
    text = "{node.django_attrib_name} = models.{node.django_type}({node.django_args})".format(node =tel_node)
    expect = "phone = models.IntegerField(null=True, blank=True)\n"
    assert text.strip() == dedent(expect).strip()


def test_select_node_django_field(django_class_template: Template, select_node: NodePath):
    text = "{node.django_attrib_name} = models.{node.django_type}({node.django_args})".format(node =select_node)
    expect = "country = models.TextField(null=True, blank=True)\n"
    assert text.strip() == dedent(expect).strip()


def test_hidden_node_django_field(django_class_template: Template, hidden_node: NodePath):
    text = "{node.django_attrib_name} = models.{node.django_type}({node.django_args})".format(node =hidden_node)
    expect = "token = models.TextField(null=True, blank=True)\n"
    assert text.strip() == dedent(expect).strip()


def test_select_node_json_table_query(select_node: NodePath):
    query = select_node.to_json_table_query("form_data", "json_content")
    expect = """
    SELECT jt.country
    FROM form_data,
    jsonb_array_elements(json_content) AS jt
    WHERE jt->>'$formkit' = 'select'
    AND jt->>'name' = 'country'
    """
    assert query.strip() == dedent(expect).strip()

def test_select_node_json_table_query_with_validation(select_node: NodePath):
    query = select_node.to_json_table_query_with_validation("form_data", "json_content")
    expect = """
    SELECT jt.country
    FROM form_data,
    jsonb_array_elements(json_content) AS jt
    WHERE jt->>'$formkit' = 'select'
    AND jt->>'name' = 'country'
    AND jt.country IS NOT NULL
    """
    assert query.strip() == dedent(expect).strip()

def test_number_node_json_table_query_with_validation(number_node: NodePath):
    query = number_node.to_json_table_query_with_validation("form_data", "json_content")
    expect = """
    SELECT jt.foonum
    FROM form_data,
    jsonb_array_elements(json_content) AS jt
    WHERE jt->>'$formkit' = 'number'
    AND jt->>'name' = 'foonum'
    AND jt.foonum ~ '^[0-9]+$'
    """
    assert query.strip() == dedent(expect).strip()

def test_date_node_json_table_query_with_validation(date_node: NodePath):
    query = date_node.to_json_table_query_with_validation("form_data", "json_content")
    expect = """
    SELECT jt.birth_date
    FROM form_data,
    jsonb_array_elements(json_content) AS jt
    WHERE jt->>'$formkit' = 'date'
    AND jt->>'name' = 'birth_date'
    AND jt.birth_date ~ '^\\d{4}-\\d{2}-\\d{2}'
    """
    assert query.strip() == dedent(expect).strip()

def test_uuid_node_json_table_query_with_validation(uuid_node: NodePath):
    query = uuid_node.to_json_table_query_with_validation("form_data", "json_content")
    expect = """
    SELECT jt.id
    FROM form_data,
    jsonb_array_elements(json_content) AS jt
    WHERE jt->>'$formkit' = 'uuid'
    AND jt->>'name' = 'id'
    AND jt.id ~ '^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$'
    """
    assert query.strip() == dedent(expect).strip()

def test_currency_node_json_table_query_with_validation(currency_node: NodePath):
    query = currency_node.to_json_table_query_with_validation("form_data", "json_content")
    expect = """
    SELECT jt.amount
    FROM form_data,
    jsonb_array_elements(json_content) AS jt
    WHERE jt->>'$formkit' = 'currency'
    AND jt->>'name' = 'amount'
    AND jt.amount ~ '^\\d+(\\.\\d{2})?$'
    """
    assert query.strip() == dedent(expect).strip()

def test_checkbox_node_json_table_query_with_validation(checkbox_node: NodePath):
    query = checkbox_node.to_json_table_query_with_validation("form_data", "json_content")
    expect = """
    SELECT jt.is_active
    FROM form_data,
    jsonb_array_elements(json_content) AS jt
    WHERE jt->>'$formkit' = 'checkbox'
    AND jt->>'name' = 'is_active'
    AND jt.is_active IN ('true', 'false')
    """
    assert query.strip() == dedent(expect).strip()

def test_complete_json_table_query(nested_group_node: NodePath):
    query = nested_group_node.to_complete_json_table_query("form_data", "json_content")
    expect = """
    SELECT jt.*
    FROM form_data,
    JSONTABLE(
        json_content,
        '$[*]' COLUMNS (
            foonum int PATH '$.foonum'
        )
    ) AS jt
    WHERE NOT EXISTS (
        SELECT 1 
        FROM form_data t2 
        WHERE t2.id = jt.id 
        AND t2.deleted_at IS NOT NULL
    )
    """
    assert query.strip() == dedent(expect).strip()
