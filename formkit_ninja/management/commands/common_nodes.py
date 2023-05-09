from formkit_ninja import models


def create_location_nodes():
    """
    Yield the nodes used by location schemas
    """

    district, c = models.FormKitSchemaNode.objects.update_or_create(
        label="municipality",
        defaults=dict(
            node_type="$formkit",
            translation_context="municipality",
            node=dict(
                label="Municipality",
                html_id="municipality",
                name="municipality",
                key="municipality",
                formkit="select",
                options="$getLocations()",
            ),
        ),
    )
    yield district, c

    admin_post, c = models.FormKitSchemaNode.objects.get_or_create(
        label="admin_post",
        defaults=dict(
            node_type="$formkit",
            translation_context="admin_post",
            node=dict(
                label="Administrative Post",
                html_id="admin_post",
                name="admin_post",
                key="admin_post",
                formkit="select",
                if_condition='$getLocations($get("municipality").value)',
                options='$getLocations($get("municipality").value)',
            ),
        ),
    )
    yield admin_post, c

    suco, c = models.FormKitSchemaNode.objects.get_or_create(
        label="suco",
        defaults=dict(
            node_type="$formkit",
            translation_context="suco",
            node=dict(
                label="Suco",
                html_id="suco",
                name="suco",
                key="suco",
                formkit="select",
                if_condition='$getLocations($get("admin_post").value)',
                options='$getLocations($get("municipality").value, $get("admin_post").value)',
            ),
        ),
    )
    yield suco, c

    aldeia, c = models.FormKitSchemaNode.objects.get_or_create(
        label="aldeia",
        defaults=dict(
            node_type="$formkit",
            translation_context="aldeia",
            node=dict(
                label="Aldeia",
                html_id="aldeia",
                name="aldeia",
                key="aldeia",
                formkit="select",
                if_condition='$getLocations($get("suco").value)',
                options='$getLocations($get("municipality").value, $get("admin_post").value, $get("suco").value)',
            ),
        ),
    )
    yield aldeia, c


def add_location_schema():
    """
    This is a "general" location picker without the special SF 1.1 logic
    """

    # The SF11 schema is represented by these parts
    locations, created = models.FormKitSchema.objects.get_or_create(key="Locations except SF 1.1")

    yield locations, created

    # Locations has: suco, aldeia, postu_admin, district nodes
    # From the admin, you'll set the "admin key" and the "node type"

    municipality, admin_post, suco, aldeia = (node for (node, _) in create_location_nodes())

    yield models.FormComponents.objects.update_or_create(
        defaults=dict(
            schema=locations,
            node=municipality,
        ),
        key="Municipalities for the Location Select schema",
    )

    yield models.FormComponents.objects.update_or_create(
        key="Administrative Posts for the Location Select schema",
        defaults=dict(
            schema=locations,
            node=admin_post,
        ),
    )

    yield models.FormComponents.objects.update_or_create(
        defaults=dict(
            schema=locations,
            node=suco,
        ),
        key="Suco for the Location Select schema",
    )

    yield models.FormComponents.objects.update_or_create(
        key="Aldeias for the Location Select schema",
        defaults=dict(
            schema=locations,
            node=aldeia,
        ),
    )
