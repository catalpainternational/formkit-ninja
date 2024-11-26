from django.core.management.base import BaseCommand

from formkit_ninja.models import FormKitSchemaNode, check_valid_django_id


class Command(BaseCommand):
    help = "Check node 'name' fields to be valid python identifiers"

    def handle(self, *args, **options):
        for node in FormKitSchemaNode.objects.all():
            if node.node and "name" in node.node:
                name = node.node["name"]
                try:
                    check_valid_django_id(name)
                    # self.stdout.write(self.style.SUCCESS(name))
                except TypeError:
                    self.stdout.write(self.style.WARNING(f"{node.pk}: {name}"))
