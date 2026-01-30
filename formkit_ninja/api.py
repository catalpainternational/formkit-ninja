import json
import re
from functools import cached_property
from http import HTTPStatus
from typing import Sequence, cast
from uuid import UUID, uuid4

from django.contrib.auth import get_user
from django.db import transaction
from django.db.models import F
from django.db.models.aggregates import Max
from django.http import HttpRequest, HttpResponse
from django.shortcuts import get_object_or_404
from django.utils.cache import add_never_cache_headers
from ninja import Field, ModelSchema, Router, Schema
from pydantic import BaseModel, validator

from formkit_ninja import formkit_schema, models
from formkit_ninja.notifications import get_default_notifier

notifier = get_default_notifier()


def sentry_message(message: str) -> None:
    notifier.notify(message)


router = Router(tags=["FormKit"])


def formkit_auth(request: HttpRequest):
    """
    Custom authentication function that checks if user is authenticated.
    Permissions are checked in the endpoint itself to return proper 403 status.
    """
    user = get_user(request)
    if not user or not user.is_authenticated:
        return None
    return user


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
    node: formkit_schema.Node
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

    node: str  # type: ignore[assignment]


NodeQSResponse = Sequence[NodeStringType | NodeReturnType | NodeInactiveType]


def node_queryset_response(qs: models.NodeQS) -> NodeQSResponse:
    responses = []
    n: NodeStringType | NodeInactiveType | NodeReturnType
    for key, last_updated, node_val, protected in qs.to_response(ignore_errors=False):
        if last_updated is None:
            last_updated = -1
        if isinstance(node_val, str):
            n = NodeStringType(key=key, last_updated=last_updated, protected=protected, node=node_val)
        elif node_val is None:
            n = NodeInactiveType(key=key, last_updated=last_updated, protected=protected, is_active=False)
        else:
            n = NodeReturnType(key=key, last_updated=last_updated, protected=protected, node=node_val)  # type: ignore[arg-type]
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
    objects: models.NodeQS = cast(models.NodeQS, models.FormKitSchemaNode.objects)
    nodes = objects.from_change(latest_change or -1)
    lc = nodes.aggregate(_=Max("track_change"))["_"]
    response["latest_change"] = lc if lc is not None else (latest_change or -1)
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


class FormKitErrors(BaseModel):
    errors: list[str] = []
    field_errors: dict[str, str] = {}


@router.delete(
    "delete/{node_id}",
    response={
        HTTPStatus.OK: NodeInactiveType,
        HTTPStatus.FORBIDDEN: FormKitErrors,
        HTTPStatus.NOT_FOUND: FormKitErrors,
    },
    exclude_none=True,
    by_alias=True,
    auth=formkit_auth,
)
def delete_node(request, node_id: UUID):
    """
    Delete a node based on its UUID
    """
    # Authentication is checked by formkit_auth
    # Check permissions here to return proper 403 status
    if not request.user.has_perm("formkit_ninja.change_formkitschemanode"):
        error_response = FormKitErrors()
        error_response.errors.append("You do not have permission to delete FormKit schema nodes.")
        return HTTPStatus.FORBIDDEN, error_response
    try:
        with transaction.atomic():
            node: models.FormKitSchemaNode = get_object_or_404(models.FormKitSchemaNode.objects, id=node_id)
            node.delete()
            # node.refresh_from_db()
            objects: models.NodeQS = cast(models.NodeQS, models.FormKitSchemaNode.objects)
            return node_queryset_response(objects.filter(pk=node_id))[0]
    except Exception as e:
        # Handle protected node deletion or other database errors
        error_response = FormKitErrors()
        error_msg = str(e)
        if "protected" in error_msg.lower() or "cannot delete" in error_msg.lower():
            error_response.errors.append("This node is protected and cannot be deleted.")
            return HTTPStatus.FORBIDDEN, error_response
        # Re-raise other exceptions
        raise


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
    value: str | None = None  # Default value for fields (especially hidden fields)

    # Fields from "number"
    max: int | str | None = None
    min: int | str | None = None
    step: str | None = None

    # Field from dropdown/select/autocomplete/radio/checkbox
    options: str | None = None

    # Repeater-specific properties
    addLabel: str | None = None
    itemClass: str | None = None
    itemsClass: str | None = None
    upControl: bool | None = None
    downControl: bool | None = None

    # Conditional logic
    if_condition: str | None = Field(default=None, alias="if")

    # Validation
    validationRules: str | None = None
    validation: str | list[str] | None = None

    # Field Constraints
    maxLength: int | None = None
    _minDateSource: str | None = None
    _maxDateSource: str | None = None
    disabledDays: str | None = None

    # Used for Creates
    parent_id: UUID | None = None

    # Used for Updates - optional for creates, required for updates
    uuid: UUID | None = None

    # Used for "Add Group"
    # This should include an `icon`, `title` and `id` for the second level group
    additional_props: dict[str, str | int] | None = None

    @validator("formkit")
    def validate_formkit_type(cls, v):
        """Validate that the formkit type is a valid FormKit type"""
        from typing import get_args

        valid_types = get_args(formkit_schema.FORMKIT_TYPE)
        if v not in valid_types:
            raise ValueError(f"Invalid FormKit type: {v}. Valid types are: {', '.join(valid_types)}")
        return v

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
            return set(parent.children.exclude(pk=self.child.pk).values_list("node__name", flat=True))
        elif self.parent[0]:
            return set(parent.children.values_list("node__name", flat=True))
        else:
            return set()

    @cached_property
    def child(self):
        # The uuid may belong to a node or may be a new value
        if self.uuid is None:
            # Create mode - generate new UUID
            return models.FormKitSchemaNode(pk=uuid4(), node={})
        try:
            # Update mode - fetch existing node
            return models.FormKitSchemaNode.objects.get(pk=self.uuid)
        except models.FormKitSchemaNode.DoesNotExist:
            # UUID provided but node doesn't exist - this is an error for updates
            return None

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

    class Config:
        allow_population_by_field_name = True
        keep_untouched = (cached_property,)


def create_or_update_child_node(payload: FormKitNodeIn, raw_payload_dict: dict | None = None):
    """
    Create or update a child node from API payload.

    Args:
        payload: Validated FormKitNodeIn payload (only recognized fields)
        raw_payload_dict: Optional raw payload dict with all fields including unrecognized ones
    """
    parent, parent_errors = payload.parent
    child = payload.child

    if parent_errors:
        return None, parent_errors

    # If uuid was provided but node doesn't exist, return error
    if payload.uuid is not None and child is None:
        return None, ["Node with the provided UUID does not exist"]

    # If child is None (shouldn't happen after above check, but safety first)
    if child is None:
        return None, ["Failed to create or retrieve node"]

    if child.is_active is False:
        return None, ["This node has already been deleted and cannot be edited"]

    values = payload.dict(
        by_alias=True,
        exclude_none=True,
        exclude={"parent_id", "uuid"} | {"parent", "child", "preferred_name", "parent_names"},
    )
    # Ensure the name is unique and suitable
    # Do not replace existing names though
    # Initialize node dict if it doesn't exist
    if child.node is None:
        child.node = {}
    existing_name = child.node.get("name", None) if isinstance(child.node, dict) else None
    if existing_name is None:
        values["name"] = payload.preferred_name
    child.node.update(values)
    if payload.additional_props is not None:
        child.node.update(payload.additional_props)
        # Also store additional_props in the model field
        if child.additional_props is None:
            child.additional_props = {}
        child.additional_props.update(payload.additional_props)

    # Extract and preserve unrecognized fields from raw payload
    if raw_payload_dict is not None:
        # Get set of recognized fields from FormKitNodeIn schema
        recognized_fields = set(FormKitNodeIn.__fields__.keys())
        # Also include alias names
        for field_name, field_info in FormKitNodeIn.__fields__.items():
            if hasattr(field_info, "alias") and field_info.alias:
                recognized_fields.add(field_info.alias)

        # Fields that are API-specific and should not go to additional_props
        api_only_fields = {"parent_id", "uuid"}

        # Extract unrecognized fields (not in schema, not API-only)
        unrecognized_fields = {
            k: v
            for k, v in raw_payload_dict.items()
            if k not in recognized_fields | api_only_fields and v is not None  # Exclude None values
        }

        # Store unrecognized fields in additional_props
        if unrecognized_fields:
            if child.additional_props is None:
                child.additional_props = {}
            # Merge with existing additional_props (don't overwrite if already set)
            for key, value in unrecognized_fields.items():
                if key not in child.additional_props:
                    child.additional_props[key] = value

    child.label = payload.label

    if isinstance(payload.additional_props, dict):
        if label := payload.additional_props.get("label"):
            # groups require a label
            child.label = label

    child.node_type = "formkit"

    with transaction.atomic():
        child.save()
        if parent:
            # Use get_or_create to avoid duplicate relationships
            models.NodeChildren.objects.get_or_create(
                parent=parent,
                child=child,
                defaults={"order": None},  # Order can be set later if needed
            )

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
        HTTPStatus.NOT_FOUND: FormKitErrors,
        HTTPStatus.BAD_REQUEST: FormKitErrors,
        HTTPStatus.FORBIDDEN: FormKitErrors,
        HTTPStatus.INTERNAL_SERVER_ERROR: FormKitErrors,
    },
    exclude_none=True,
    by_alias=True,
    auth=formkit_auth,
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
    # Authentication is checked by formkit_auth
    # Check permissions here to return proper 403 status
    if not request.user.has_perm("formkit_ninja.change_formkitschemanode"):
        error_response = FormKitErrors()
        error_response.errors.append("You do not have permission to create or update FormKit schema nodes.")
        return HTTPStatus.FORBIDDEN, error_response

    error_response = FormKitErrors()
    # Update the payload "name"
    # When label is provided, use the label to generate the name
    # Fetch parent node, if it exists, and check that it is a group or repeater

    # Extract unrecognized fields from raw request body
    raw_payload_dict = None
    try:
        if hasattr(request, "body") and request.body:
            raw_payload_dict = json.loads(request.body)
    except (json.JSONDecodeError, AttributeError):
        # If we can't parse the body, continue without extracting unrecognized fields
        pass

    try:
        child, errors = create_or_update_child_node(payload, raw_payload_dict)
        if errors:
            # Flatten errors if it's a list
            if isinstance(errors, list):
                error_response.errors.extend(errors)
            else:
                error_response.errors.append(errors)

            # Determine appropriate status code based on error type
            error_text = " ".join(error_response.errors) if error_response.errors else ""
            if "does not exist" in error_text or "UUID" in error_text:
                return HTTPStatus.NOT_FOUND, error_response
            elif "deleted" in error_text or "cannot be edited" in error_text:
                return HTTPStatus.BAD_REQUEST, error_response
            else:
                return HTTPStatus.BAD_REQUEST, error_response
    except Exception as E:
        error_response.errors.append(f"{E}")
        return HTTPStatus.INTERNAL_SERVER_ERROR, error_response

    if error_response.errors or error_response.field_errors:
        return HTTPStatus.INTERNAL_SERVER_ERROR, error_response

    return node_queryset_response(models.FormKitSchemaNode.objects.filter(pk__in=[child.pk]))[0]
