from django.shortcuts import get_object_or_404
from ninja import ModelSchema, Router
from pydantic import UUID4

from formkit_ninja import formkit_schema, models

router = Router(tags=["FormKit"])


class FormKitSchemaIn(ModelSchema):
    class Config:
        model = models.FormKitSchema
        model_fields = "__all__"


class FormKitSchemaListOut(ModelSchema):
    class Config:
        model = models.FormKitSchema
        model_fields = ("id", "name")


@router.get("list-schemas", response=list[FormKitSchemaListOut])
def get_list_schemas(request):
    return models.FormKitSchema.objects.all()


@router.post(
    "schema/create",
    response=formkit_schema.FormKitSchema,
    by_alias=True,
    exclude_none=True,
)
def post_schema(request, payload: list[dict]):
    schema: models.FormKitSchema = models.FormKitSchema.from_json(payload)
    return schema.to_pydantic()


@router.get(
    "schema/{schema_id}",
    response=formkit_schema.FormKitSchema,
    exclude_none=True,
    by_alias=True,
)
def get_schemas(request, schema_id: int):
    schema: models.FormKitSchema = get_object_or_404(models.FormKitSchema.objects, id=schema_id)
    model = schema.to_pydantic()
    return model


@router.get(
    "node/{node_id}",
    response=formkit_schema.FormKitNode,
    exclude_none=True,
    by_alias=True,
)
def get_node(request, node_id: UUID4):
    node: models.FormKitSchemaNode = get_object_or_404(models.FormKitSchemaNode.objects, id=node_id)
    instance = node.get_node()
    return instance
