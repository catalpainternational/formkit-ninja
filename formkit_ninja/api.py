import datetime
import warnings
from typing import List
from uuid import UUID

from django.db.models import F, Q
from django.http import HttpRequest, HttpResponse
from django.shortcuts import get_object_or_404
from ninja import ModelSchema, Router, Schema

from formkit_ninja import formkit_schema, models

router = Router(tags=["FormKit"])


class FormKitSchemaIn(ModelSchema):
    class Config:
        model = models.FormKitSchema
        model_fields = "__all__"


class SchemaLabel(ModelSchema):
    class Config:
        model = models.SchemaLabel
        model_fields = ("lang", "label")


class SchemaDescription(ModelSchema):
    class Config:
        model = models.SchemaLabel
        model_fields = ("lang", "label")


class FormKitSchemaListOut(ModelSchema):
    schemalabel_set: list[SchemaLabel]
    schemadescription_set: list[SchemaDescription]

    class Config:
        model = models.FormKitSchema
        model_fields = ("id", "label")


class FormComponentsOut(ModelSchema):
    node_id: UUID
    schema_id: UUID

    class Config:
        model = models.FormComponents
        model_fields = ("label",)


class NodeChildrenOut(ModelSchema):
    class Config:
        model = models.NodeChildren
        model_fields = ("parent", "child", "order")


class OptionLabel(Schema):
    lang: str
    label: str


class Option(Schema):
    group: str  # This is annotation of the model `content_type_model`
    label_set: list[OptionLabel]
    value: str


@router.get("list-schemas", response=list[FormKitSchemaListOut])
def get_list_schemas(request):
    return models.FormKitSchema.objects.all()


@router.get("list-nodes", response=dict[str, formkit_schema.Node], exclude_defaults=True, exclude_none=True)
def get_formkit_nodes(request):
    """
    Get all of the FormKit nodes in the database
    """
    response: dict[str, formkit_schema.Node] = {}
    for node in models.FormKitSchemaNode.objects.all():
        try:
            response[f"{node.pk}"] = node.get_node()
        except:  # noqa: E722
            warnings.warn(f"An unparseable FormKit node was hit at {node.pk}")
    return response


@router.get("list-related-nodes", response=list[NodeChildrenOut], exclude_defaults=True, exclude_none=True)
def get_related_nodes(request):
    """
    Get all of the FormKit nodes in the database
    """
    return models.NodeChildren.objects.all()


@router.get(
    "list-components", response=List[FormComponentsOut], exclude_defaults=True, exclude_none=True, by_alias=True
)
def get_components(request):
    values = models.FormComponents.objects.all()
    return values


@router.get(
    "schema/{schema_id}",
    response=formkit_schema.FormKitSchema,
    exclude_none=True,
    by_alias=True,
)
def get_schemas(request, schema_id: UUID):
    schema: models.FormKitSchema = get_object_or_404(models.FormKitSchema.objects, id=schema_id)
    model = schema.to_pydantic()
    return model


@router.get(
    "schema/by-label/{label}",
    response=formkit_schema.FormKitSchema,
    exclude_none=True,
    by_alias=True,
)
def get_schema_by_label(request, label: str):
    schema: models.FormKitSchema = get_object_or_404(models.FormKitSchema.objects, label=label)
    model = schema.to_pydantic()
    return model


@router.get(
    "node/{node_id}",
    response=formkit_schema.FormKitNode,
    exclude_none=True,
    by_alias=True,
)
def get_node(request, node_id: UUID):
    node: models.FormKitSchemaNode = get_object_or_404(models.FormKitSchemaNode.objects, id=node_id)
    instance = node.get_node()
    return instance


@router.get("/options", response=list[Option], exclude_none=True)
def list_options(request: HttpRequest, response: HttpResponse):
    """
    List all available options from the zTables
    and the associated Translations
    This may include both "native" FormKit ninja labels and links
    to any model with a compatible table structure.
    """

    def options_from_formkit():
        qs = models.Option.objects.annotate(group_name=F("group__group")).prefetch_related("optionlabel_set")
        for option in qs:
            yield Option(
                group=option.group_name,
                label_set=[dict(lang=_.lang, label=_.label) for _ in option.optionlabel_set.all()],
                value=option.value,
            )

    def options_from_apps():
        choice_models = (
            m.content_type.model_class() for m in models.OptionGroup.objects.filter(content_type__isnull=False)
        )
        for model in choice_models:
            qs = model.objects.all().prefetch_related("label_set")
            for instance in qs:
                yield Option(
                    group=model._meta.verbose_name.capitalize(),
                    label_set=[dict(lang=_.lang, label=_.label) for _ in instance.label_set.all()],
                    value=instance.value,
                )

    return list(options_from_formkit()) + list(options_from_apps())
