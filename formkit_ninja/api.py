from typing import List, Literal
from uuid import UUID

from django.db import transaction
from django.db.models import F
from django.db.models.aggregates import Max
from django.http import HttpRequest, HttpResponse
from django.shortcuts import get_object_or_404
from ninja import ModelSchema, Router, Schema
from pydantic import BaseModel

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

    children: list[UUID] = []
    latest_change: int | None = None

    class Config:
        model = models.NodeChildren
        model_fields = ("parent",)


class NodeReturnType(BaseModel):
    key: UUID
    last_updated: int
    node: formkit_schema.FormKitNode


class NodeInactiveType(BaseModel):
    key: UUID
    last_updated: int
    is_active: bool = False


class NodeStringType(NodeReturnType):
    """
    str | formkit_schema.FormKitNode causes openapi generator to fail
    """

    node: str


NodeQSResponse = list[NodeStringType | NodeReturnType | NodeInactiveType]


def node_queryset_response(qs: models.NodeQS) -> NodeQSResponse:
    responses = []
    for key, last_updated, node in qs.to_response(ignore_errors=False):
        if isinstance(node, str):
            n = NodeStringType(key=key, last_updated=last_updated, node=node)
        elif node is None:
            n = NodeInactiveType(key=key, last_updated=last_updated, is_active=False)
        else:
            n = NodeReturnType(key=key, last_updated=last_updated, node=node)
        responses.append(n)
    return responses


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


@router.get("list-nodes", response=NodeQSResponse, by_alias=True, exclude_none=True)
def get_formkit_nodes(request: HttpRequest, response: HttpResponse, latest_change: int | None = -1):
    """
    Get all of the FormKit nodes in the database
    """
    objects: models.NodeQS = models.FormKitSchemaNode.objects
    nodes = objects.from_change(latest_change)
    response["latest_change"] = nodes.aggregate(_=Max("track_change"))["_"] or latest_change
    response["Cache-Control"] = "no-store,max-age=0"
    return node_queryset_response(nodes)


@router.get("list-related-nodes", response=list[NodeChildrenOut], exclude_defaults=True, exclude_none=True)
def get_related_nodes(request, latest_change: int | None = -1):
    """
    Get all of the FormKit nodes in the database
    """
    objects: models.NodeChildrenManager = models.NodeChildren.objects
    return objects.aggregate_changes_table(latest_change=latest_change)


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


# Create a new Group within a Form
class GroupIn(BaseModel):
    parent_id: UUID
    id: str = "newsection"
    icon: str = "info-circle"
    title: str = "New Section"


@router.post(
    "create_group",
    response=list[NodeStringType | NodeReturnType | NodeInactiveType],
    exclude_none=True,
    by_alias=True,
)
def create_group(request, response: HttpResponse, payload: GroupIn):
    """
    Adds a new 'Group' node to a form
    This is a collapsible section with an icon and title
    """
    with transaction.atomic():
        parent = get_object_or_404(models.FormKitSchemaNode.objects, id=payload.parent_id)
        if parent.node_type != "$formkit":
            raise ValueError("Parent node must be a FormKit node")
        if not isinstance(parent.node, dict):
            raise ValueError("Parent node must be a FormKit node")
        if payload.id in models.NodeChildren.objects.filter(parent=parent).values_list("child__node__id", flat=True):
            raise KeyError("A node with this ID already exists")
        child = models.FormKitSchemaNode.objects.create(
            label=payload.title,
            node_type="$formkit",
            additional_props=dict(
                icon=payload.icon,
                title=payload.title,
            ),
            node=dict(
                id=payload.id,
                formkit="group",
            ),
        )
        models.NodeChildren.objects.create(parent=parent, child=child)
        objects: models.NodeQS = models.FormKitSchemaNode.objects
        nodes = objects.filter(pk__in=[parent.pk, child.pk])
        return node_queryset_response(nodes)


@router.delete("delete", response=NodeInactiveType, exclude_none=True, by_alias=True)
def delete_node(request, node_id: UUID):
    """
    Delete a node based on its UUID
    """
    with transaction.atomic():
        node: models.FormKitSchemaNode = get_object_or_404(models.FormKitSchemaNode.objects, id=node_id)
        node.delete()
        # node.refresh_from_db()
        objects: models.NodeQS = models.FormKitSchemaNode.objects
        return node_queryset_response(objects.filter(pk=node_id))[0]


class FormKitNodeIn(Schema):
    """
    Creates a new FormKit text or number node
    """

    formkit: Literal["text", "number"]
    label: str
    key: str
    node_label: str
    parent_id: UUID | None
    id: str | None = None


class FormKitNodeCreate(FormKitNodeIn):
    parent_id: UUID


class FormKitNodeUpdate(Schema):
    formkit: Literal["text", "number"] | None = None
    label: str | None = None
    key: str | None = None
    node_label: str | None = None
    id: str | None = None
    node_id: UUID | None = None
    placeholder: str | None = None


@router.post(
    "add_node",
    response=list[NodeReturnType],
    exclude_none=True,
    by_alias=True,
)
def add_node(request, response: HttpResponse, payload: FormKitNodeCreate):
    """
    Adds a new child node to an element
    """
    with transaction.atomic():
        parent = get_object_or_404(models.FormKitSchemaNode.objects, id=payload.parent_id)
        if parent.node_type != "$formkit":
            raise ValueError("Parent node must be a FormKit node")
        if not isinstance(parent.node, dict):
            raise ValueError("Parent node must be a FormKit node")
        if payload.id is not None and payload.id in models.NodeChildren.objects.filter(parent=parent).values_list(
            "child__node__id", flat=True
        ):
            raise KeyError("A node with this ID already exists")

        node = dict(formkit=payload.formkit)
        if payload.id:
            node["id"] = payload.id
        node["label"] = payload.node_label
        child = models.FormKitSchemaNode.objects.create(label=payload.label, node_type="$formkit", node=node)
        models.NodeChildren.objects.create(parent=parent, child=child)
        objects: models.NodeQS = models.FormKitSchemaNode.objects
        nodes = objects.filter(pk__in=[parent.pk, child.pk])
        return node_queryset_response(nodes)


@router.put(
    "update_node",
    response=list[NodeReturnType],
    exclude_none=True,
    by_alias=True,
)
def update_node(request, response: HttpResponse, payload: FormKitNodeUpdate):
    """
    Updates a given FormKit node
    """
    with transaction.atomic():
        node = dict(formkit=payload.formkit)
        if payload.id:
            node["id"] = payload.id
        node["label"] = payload.node_label
        if payload.placeholder:
            node["placeholder"] = payload.placeholder

        child, created = models.FormKitSchemaNode.objects.update_or_create(
            id=payload.node_id, defaults=dict(label=payload.label, node_type="$formkit", node=node)
        )
        objects: models.NodeQS = models.FormKitSchemaNode.objects
        nodes = objects.filter(pk__in=[child.pk])
        return node_queryset_response(nodes)
