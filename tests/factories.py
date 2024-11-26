from factory import Faker
from factory.django import DjangoModelFactory

from formkit_ninja import models


class FormKitSchemaNodeFactory(DjangoModelFactory):
    class Meta:
        model = models.FormKitSchemaNode

    # Assuming FormKitSchemaNode has these fields
    node = Faker("pydict")
    label = Faker("sentence")
    node_type = Faker("word")
