from django.apps import apps
from django.core.management.base import BaseCommand
from formkit_ninja.models import OptionGroup
from django.contrib.contenttypes.models import ContentType


class Command(BaseCommand):
    help = "Intended to create a link to 'Ida Choices' models as Option groups. Call from Partisipa manage.py"

    def handle(self, *args, **options):
        models = [
            n for n in apps.get_models() if hasattr(n, 'value')
            and hasattr(n, 'label_set')
        ]
        for model in models:
            group_name = model._meta.verbose_name.capitalize()
            content_type = ContentType.objects.get_for_model(model)
            OptionGroup.objects.get_or_create(group=group_name, defaults=dict(content_type = content_type))
