import importlib
import re
from functools import cached_property
from http import HTTPStatus
from importlib.util import find_spec
from types import ModuleType
from typing import Sequence
from uuid import UUID, uuid4

from django.db import transaction
from django.db.models import F
from django.db.models.aggregates import Max
from django.http import HttpRequest, HttpResponse
from django.shortcuts import get_object_or_404
from django.utils.cache import add_never_cache_headers
from ninja import Field, ModelSchema, Router, Schema
from pydantic import BaseModel, ConfigDict

from formkit_ninja import formkit_schema, models

if find_spec("sentry_sdk"):
    sentry_sdk: ModuleType | None = importlib.import_module("sentry_sdk")
else:
    sentry_sdk = None


def sentry_message(message: str):
    if sentry_sdk and hasattr(sentry_sdk, "capture_message"):
        sentry_sdk.capture_message(f"{message}")


router = Router(tags=["FormKit"])


class FormKitSchemaIn(ModelSchema):
    class Meta:
        model = models.FormKitSchema
        fields = "__all__"


class SchemaLabel(ModelSchema):
    class Meta:
        model = models.SchemaLabel
        fields = ["lang", "label"]


class SchemaDescription(ModelSchema):
    class Meta:
        model = models.SchemaDescription
        fields = ["lang", "label"]


class FormKitSchemaListOut(ModelSchema):
    schemalabel_set: list[SchemaLabel]
    schemadescription_set: list[SchemaDescription]

    class Meta:
        model = models.FormKitSchema
        fields = ["id", "label"]


class FormComponentsOut(ModelSchema):
    node_id: UUID
    schema_id: UUID

    class Meta:
        model = models.FormComponents
        fields = ["label"]


class NodeChildrenOut(ModelSchema):
    children: list[UUID] = []
    latest_change: int | None = None

    class Meta:
        model = models.NodeChildren
        fields = ["parent"]


class NodeReturnType(BaseModel):
    key: UUID
    last_updated: int
    node: formkit_schema.FormKitNode
    protected: bool


class NodeInactiveType(BaseModel):
    key: UUID
    last_updated: int
    is_active: bool = False
    protected: bool


class NodeStringType(NodeReturnType):
    """
    str | formkit_schema.FormKitNode causes openapi generator to fail
    """

    node: str


NodeQSResponse = Sequence[NodeStringType | NodeReturnType | NodeInactiveType]


def node_queryset_response(qs: models.NodeQS) -> NodeQSResponse:
    responses = []
    n: NodeStringType | NodeInactiveType | NodeReturnType
    for key, last_updated, node, protected in qs.to_response(ignore_errors=False):
        if isinstance(node, str):
            n = NodeStringType(
                key=key, last_updated=last_updated, protected=protected, node=node
            )
        elif node is None:
            n = NodeInactiveType(
                key=key, last_updated=last_updated, protected=protected, is_active=False
            )
        else:
            n = NodeReturnType(
                key=key, last_updated=last_updated, protected=protected, node=node
            )
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

    class Meta:
        model = models.Option
        fields = ["value"]


@router.get("list-schemas", response=list[FormKitSchemaListOut])
def get_list_schemas(request):
    return models.FormKitSchema.objects.all()


@router.get("list-nodes", response=NodeQSResponse, by_alias=True, exclude_none=True)
def get_formkit_nodes(
    request: HttpRequest, response: HttpResponse, latest_change: int | None = -1
):
    """
    Get all of the FormKit nodes in the database
    """
    objects: models.NodeQS = models.FormKitSchemaNode.objects
    nodes = objects.from_change(latest_change)
    response["latest_change"] = (
        nodes.aggregate(_=Max("track_change"))["_"] or latest_change
    )
    add_never_cache_headers(response)
    return node_queryset_response(nodes)


@router.get(
    "list-related-nodes",
    response=list[NodeChildrenOut],
    exclude_defaults=True,
    exclude_none=True,
)
def get_related_nodes(request, response: HttpResponse, latest_change: int | None = -1):
    """
    Get all of the FormKit node relationships in the database
    """
    add_never_cache_headers(response)
    objects: models.NodeChildrenManager = models.NodeChildren.objects
    return objects.aggregate_changes_table(latest_change=latest_change)


@router.get(
    "list-components",
    response=list[FormComponentsOut],
    exclude_defaults=True,
    exclude_none=True,
    by_alias=True,
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
    schema: models.FormKitSchema = get_object_or_404(
        models.FormKitSchema.objects, id=schema_id
    )
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
    schema: models.FormKitSchema = get_object_or_404(
        models.FormKitSchema.objects, label=label
    )
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
    node: models.FormKitSchemaNode = get_object_or_404(
        models.FormKitSchemaNode.objects, id=node_id
    )
    instance = node.get_node()
    return instance


@router.get("/options", response=list[Option], exclude_none=True)
def list_options(request: HttpRequest, response: HttpResponse):
    """
    List all available "native" FormKit ninja labels and links
    """
    return models.Option.objects.annotate(group_name=F("group__group"))


class FormKitErrors(BaseModel):
    errors: list[str] = []
    field_errors: dict[str, str] = {}


@router.delete("delete", response=NodeInactiveType, exclude_none=True, by_alias=True)
def delete_node(request, node_id: UUID):
    """
    Delete a node based on its UUID
    """
    with transaction.atomic():
        node: models.FormKitSchemaNode = get_object_or_404(
            models.FormKitSchemaNode.objects, id=node_id
        )
        node.delete()
        # node.refresh_from_db()
        objects: models.NodeQS = models.FormKitSchemaNode.objects
        return node_queryset_response(objects.filter(pk=node_id))[0]


class FormKitNodeIn(Schema):
    """
    Creates a new FormKit text or number node
    We'd like to use `formkit_schema.FormKitSchemaFormKit`
    here but that `discriminated node` stuff makes it hard
    """

    formkit: str = Field(default="text", alias="$formkit")
    label: str | None = None
    key: str | None = None
    name: str | None = None
    placeholder: str | None = None
    help: str | None = None

    # Fields from "number"
    max: int | None = None
    min: int | None = None
    step: str | None = None

    # Field from dropdown/select/autocomplete/radio/checkbox
    options: str | None = None

    # Used for Creates
    parent_id: UUID | None = None

    # Used for Updates
    uuid: UUID = Field(default_factory=uuid4)

    # Used for "Add Group"
    # This should include an `icon`, `title` and `id` for the second level group
    additional_props: dict[str, str | int] | None = None

    @cached_property
    def parent(self):
        if self.parent_id is None:
            return None, None
        try:
            parent = models.FormKitSchemaNode.objects.get(pk=self.parent_id)
        except models.FormKitSchemaNode.DoesNotExist:
            return None, ["The parent node given does not exist"]
        if parent.node.get("$formkit") not in {"group", "repeater"}:
            return None, ["The parent node given is not a group or repeater"]
        if parent is None:
            return None, ["The parent node given does not exist"]
        return parent, None

    @cached_property
    def parent_names(self) -> set[str]:
        """
        Return the names of parent nodes' child nodes.
        The saved child node must not use any of these names.
        """
        parent, parent_errors = self.parent
        if self.parent[0] and self.child:
            # Ensures that names are not "overwritten"
            return set(
                parent.children.exclude(pk=self.child.pk).values_list(
                    "node__name", flat=True
                )
            )
        elif self.parent[0]:
            return set(parent.children.values_list("node__name", flat=True))
        else:
            return set()

    @cached_property
    def child(self):
        # The uuid may belong to a node or may be a new value
        try:
            return models.FormKitSchemaNode.objects.get(pk=self.uuid)
        except models.FormKitSchemaNode.DoesNotExist:
            return models.FormKitSchemaNode(pk=self.uuid, node={})

    @cached_property
    def preferred_name(self):
        """
        Fetch a suitable name for the database to use.
        This name must be unique to the 'parent' group, a valid Python id, valid Django id,
        preferably lowercase.
        """
        # If "name" is not provided use the "label" field
        if self.name is not None:
            return disambiguate_name(make_name_valid_id(self.name), self.parent_names)
        elif self.label is not None:
            return disambiguate_name(make_name_valid_id(self.label), self.parent_names)
        return make_name_valid_id(f"{uuid4().hex[:8]}_unnamed")

    model_config = ConfigDict(populate_by_name=True, ignored_types=(cached_property,))


def create_or_update_child_node(payload: FormKitNodeIn):
    parent, parent_errors = payload.parent
    child = payload.child

    if parent_errors:
        return None, parent_errors
    if child.is_active is False:
        return None, ["This node has already been deleted and cannot be edited"]

    values = payload.dict(
        by_alias=True,
        exclude_none=True,
        exclude={"parent_id", "uuid"}
        | {"parent", "child", "preferred_name", "parent_names"},
    )
    # Ensure the name is unique and suitable
    # Do not replace existing names though
    existing_name = (
        child.node.get("name", None) if isinstance(child.node, dict) else None
    )
    if existing_name is None:
        values["name"] = payload.preferred_name
    child.node.update(values)
    if payload.additional_props is not None:
        child.node.update(payload.additional_props)

    child.label = payload.label

    if isinstance(payload.additional_props, dict):
        if label := payload.additional_props.get("label"):
            # groups require a label
            child.label = label

    child.node_type = "formkit"

    with transaction.atomic():
        child.save()
        if parent:
            models.NodeChildren.objects.create(parent=parent, child=child)

    return child, []


def make_name_valid_id(in_: str):
    """
    Take a string. Replace any python-invalid characters with '_'
    """
    subbed = re.sub(r"\W|^(?=\d)", "_", in_)
    while subbed[-1] == "_":
        subbed = subbed[:-1]
    return subbed.lower()


def disambiguate_name(name_in: str, used_names: Sequence[str]):
    suffix = 1
    if name_in not in used_names:
        return name_in
    while f"{name_in}_{suffix}" in used_names:
        suffix = suffix + 1
    return f"{name_in}_{suffix}"


@router.post(
    "create_or_update_node",
    response={
        HTTPStatus.OK: NodeReturnType,
        HTTPStatus.INTERNAL_SERVER_ERROR: FormKitErrors,
    },
    exclude_none=True,
    by_alias=True,
)
def create_or_update_node(request, response: HttpResponse, payload: FormKitNodeIn):
    """
    Creates or updates a node in the FormKitSchemaNode model.

    This function takes payload of type FormKitNodeIn.
    It fetches the parent node if it exists and checks if it is a group or repeater.
    If the parent node is not valid or is not a group or repeater, it returns an error response.
    Otherwise, it proceeds to create or update the node.

    Args:
        request: The request object.
        response (HttpResponse): The HttpResponse object.
        payload (FormKitNodeIn): The payload containing the data for the node to be created or updated.

    Returns:
        HTTPStatus: The status of the HTTP response.
        FormKitErrors: The errors encountered during the process, if any.
    """

    error_response = FormKitErrors()
    # Update the payload "name"
    # When label is provided, use the label to generate the name
    # Fetch parent node, if it exists, and check that it is a group or repeater

    try:
        child, errors = create_or_update_child_node(payload)
        if errors:
            error_response.errors.append(errors)
    except Exception as E:
        error_response.errors.append(f"{E}")

    if error_response.errors or error_response.field_errors:
        return HTTPStatus.INTERNAL_SERVER_ERROR, error_response

    return node_queryset_response(
        models.FormKitSchemaNode.objects.filter(pk__in=[child.pk])
    )[0]
