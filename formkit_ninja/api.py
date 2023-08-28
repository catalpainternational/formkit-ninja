import datetime
import warnings
from typing import List
from uuid import UUID

from django.db.models import F, Q
from django.http import HttpRequest, HttpResponse
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


class OptionLabel(ModelSchema):
    class Config:
        model = models.OptionLabel
        model_fields = ("lang", "label")


class Option(ModelSchema):
    group_name: str  # This is annotation of the model `content_type_model`
    optionlabel_set: list[OptionLabel]

    class Config:
        model = models.Option
        model_fields = ("id", "object_id")


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


@router.get("/options", response=list[Option], exclude_none=True)
def list_options(request: HttpRequest, response: HttpResponse, since: str = None):
    """
    List all available options from the zTables
    and the associated Translations
    """

    model = Option.Config.model
    qs = model.objects.all()

    if since is not None and since != "":
        # Python 3.10 does not support a trailing 'Z'
        if since.endswith("Z"):
            since = since[:-1] + "+00:00"
        try:
            ts = datetime.datetime.fromisoformat(since)
            qs = qs.filter(Q(last_updated__gt=ts))
        except Exception as E:
            warnings.warn(f"{E}")
    try:
        response["X-lastupdated"] = qs.latest("last_updated").last_updated.isoformat()
    except model.DoesNotExist:
        # if there are no changes, use the same header as was sent
        if since:
            response["X-lastupdated"] = since
    return qs.annotate(group_name=F("group__group")).prefetch_related("optionlabel_set")
