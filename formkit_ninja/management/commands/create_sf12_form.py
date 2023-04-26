from django.core.management.base import BaseCommand

from formkit_ninja import models
from formkit_ninja.management.commands.common_nodes import create_location_nodes


def create():
    municipality, admin_post, suco, aldeia = (node for (node, _) in create_location_nodes())
    locations, created = models.FormKitSchema.objects.get_or_create(key="SF 1.2 Location and Date")
    count, created = models.FormKitSchema.objects.get_or_create(key="SF 1.2 Community contribution")

    yield locations, created
    yield models.FormComponents.objects.update_or_create(
        defaults=dict(
            schema=locations,
            node=municipality,
        ),
        label="Municipalities for the SF 1.2 Location and Date schema",
    )

    yield models.FormComponents.objects.update_or_create(
        label="Administrative Posts for the SF 1.2 Location and Date schema",
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
        label="Suco for the SF 1.2 Location and Date schema",
    )

    yield models.FormComponents.objects.update_or_create(
        label="Aldeias for the SF 1.2 Location and Date schema",
        defaults=dict(
            schema=locations,
            node=aldeia,
        ),
    )

    date_component, created = models.FormKitSchemaNode.objects.update_or_create(
        label="SF 1.2 Date",
        defaults=dict(
            node_type="$formkit", node=dict(name="date", label="""$gettext("Date")""", calendarIcon="calendar")
        ),
    )

    yield date_component, created

    yield models.FormComponents.objects.update_or_create(
        label="Date picker for the SF 1.2 Location and Date schema",
        defaults=dict(
            schema=locations,
            node=date_component,
        ),
    )

    cc, cc_created = models.FormKitSchemaNode.objects.update_or_create(
        label="SF 1.2 Community Contribution",
        defaults=dict(
            node_type="$formkit",
            node=dict(
                label="Cost estimation",
                placeholder="Please enter",
                name="cost_estimation",
                min=0,
            ),
            additional_props={"icon": "las la-address-book"},
        ),
    )

    yield cc, cc_created

    yield models.FormComponents.objects.update_or_create(
        label="Community Contributions for SF 1.2",
        defaults=dict(
            schema=count,
            node=cc,
        ),
    )


class Command(BaseCommand):
    help = """
        Create the Partisipa 'SF12' form
        as a set of Django models / FormKit integration
    """

    def handle(self, *args, **options):
        for instance, created in create_location_nodes():
            if options["verbosity"] > 1:
                self.stdout.write(self.style.SUCCESS(f"{'Created' if created else 'Updated'} {instance}"))
        for instance, created in create():
            if options["verbosity"] > 1:
                self.stdout.write(self.style.SUCCESS(f"{'Created' if created else 'Updated'} {instance}"))
