import warnings
from typing import List, Union
from uuid import UUID

from django.db.models import F
from django.http import HttpRequest, HttpResponse
from django.shortcuts import get_object_or_404
from ninja import ModelSchema, Router

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


class Option(ModelSchema):
    group_name: str  # This is annotation of the model `content_type_model`
    value: str
    # Note: For other projects you may want to extend this with additional languages
    label_tet: str | None
    label_en: str | None
    label_pt: str | None
    # This is an optional field used to indicate the last update
    # It's linked to a Django pg trigger instance in Partisipa
    change_id: int | None = None

    class Config:
        model = models.Option
        model_fields = ("value",)


@router.get("list-schemas", response=list[FormKitSchemaListOut])
def get_list_schemas(request):
    return models.FormKitSchema.objects.all()


@router.get("list-nodes", response=dict[str, Union[str, formkit_schema.FormKitNode]], by_alias=True, exclude_none=True)
def get_formkit_nodes(request):
    """
    Get all of the FormKit nodes in the database
    """
    response = {}
    for node in models.FormKitSchemaNode.objects.all():
        try:
            response[f"{str(node.id)[:8]}"] = node.get_node(recursive=False)
        except Exception as E:
            warnings.warn(f"An unparseable FormKit node was hit at {node.pk}")
            warnings.warn(f"{E}")
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
    "schema/by-uuid/{schema_id}",
    response=formkit_schema.FormKitSchema,
    exclude_none=True,
    by_alias=True,
)
def get_schemas(request, schema_id: UUID):
    """
    Get a schema based on its UUID
    """
    schema: models.FormKitSchema = get_object_or_404(models.FormKitSchema.objects, id=schema_id)
    model = schema.to_pydantic()
    return model


@router.get(
    "schema/all",
    response=list[formkit_schema.FormKitSchema],
    exclude_none=True,
    by_alias=True,
)
def get_all_schemas(request):
    """
    Get all schemas
    """
    schemas = models.FormKitSchema.objects.all()
    model = [s.to_pydantic() for s in schemas]
    return model


@router.get(
    "schema/by-label/{label}",
    response=formkit_schema.FormKitSchema,
    exclude_none=True,
    by_alias=True,
)
def get_schema_by_label(request, label: str):
    """
    Get a schema based on its label
    """
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
    """
    Gets a node based on its UUID
    """
    node: models.FormKitSchemaNode = get_object_or_404(models.FormKitSchemaNode.objects, id=node_id)
    instance = node.get_node()
    return instance


@router.get("/options", response=list[Option], exclude_none=True)
def list_options(request: HttpRequest, response: HttpResponse):
    """
    List all available "native" FormKit ninja labels and links
    """
    return models.Option.objects.annotate(group_name=F("group__group"))
