import warnings
from typing import List
from uuid import UUID

from django.shortcuts import get_object_or_404
from ninja import ModelSchema, Router

from formkit_ninja import formkit_schema, models

router = Router(tags=["FormKit"])


class FormKitSchemaIn(ModelSchema):
    class Config:
        model = models.FormKitSchema
        model_fields = "__all__"


class FormKitSchemaListOut(ModelSchema):
    class Config:
        model = models.FormKitSchema
        model_fields = ("id", "key")


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
    "node/{node_id}",
    response=formkit_schema.FormKitNode,
    exclude_none=True,
    by_alias=True,
)
def get_node(request, node_id: UUID):
    node: models.FormKitSchemaNode = get_object_or_404(models.FormKitSchemaNode.objects, id=node_id)
    instance = node.get_node()
    return instance
