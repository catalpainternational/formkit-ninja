from factory import Faker, LazyAttribute, SubFactory, post_generation
from factory.django import DjangoModelFactory

from formkit_ninja import models


class OptionGroupFactory(DjangoModelFactory):
    class Meta:
        model = models.OptionGroup
        django_get_or_create = ("group",)

    group = Faker("word")


class OptionLabelFactory(DjangoModelFactory):
    class Meta:
        model = models.OptionLabel

    option = SubFactory("tests.factories.OptionFactory")
    label = Faker("word")
    lang = "en"


class OptionFactory(DjangoModelFactory):
    class Meta:
        model = models.Option
        skip_postgeneration_save = True

    group = SubFactory(OptionGroupFactory)
    value = Faker("word")
    object_id = None
    order = None

    @post_generation
    def create_label(self, create, extracted, **kwargs):
        if not create:
            return
        if extracted is not None:
            OptionLabelFactory(option=self, label=extracted, lang="en")
        else:
            OptionLabelFactory(option=self, label=self.value, lang="en")
        self.save()  # Save after creating label


class FormKitSchemaNodeFactory(DjangoModelFactory):
    class Meta:
        model = models.FormKitSchemaNode

    node_type = "$formkit"
    label = Faker("sentence", nb_words=3)
    node = LazyAttribute(lambda obj: {"$formkit": "text", "name": obj.label.lower().replace(" ", "_")})
    is_active = True
    protected = False
    option_group = None


class TextNodeFactory(FormKitSchemaNodeFactory):
    node_type = "$formkit"
    label = Faker("sentence", nb_words=2)
    node = LazyAttribute(
        lambda obj: {
            "$formkit": "text",
            "name": obj.label.lower().replace(" ", "_") if obj.label else "text_field",
            "label": obj.label,
        }
    )


class NumberNodeFactory(FormKitSchemaNodeFactory):
    node_type = "$formkit"
    label = Faker("sentence", nb_words=2)
    node = LazyAttribute(
        lambda obj: {
            "$formkit": "number",
            "name": obj.label.lower().replace(" ", "_") if obj.label else "number_field",
            "label": obj.label,
            "min": 0,
            "max": 100,
        }
    )


class RepeaterNodeFactory(FormKitSchemaNodeFactory):
    node_type = "$formkit"
    label = Faker("sentence", nb_words=2)
    add_label = "Add another"
    up_control = True
    down_control = True
    min = None
    node = LazyAttribute(
        lambda obj: {
            "$formkit": "repeater",
            "name": obj.label.lower().replace(" ", "_") if obj.label else "repeater_field",
            "label": obj.label,
            "addLabel": obj.add_label,
            "upControl": obj.up_control,
            "downControl": obj.down_control,
            **({"min": int(obj.min)} if obj.min else {}),
        }
    )


class GroupNodeFactory(FormKitSchemaNodeFactory):
    node_type = "$formkit"
    label = Faker("sentence", nb_words=2)
    icon = None
    title = None
    node = LazyAttribute(
        lambda obj: {
            "$formkit": "group",
            "name": obj.label.lower().replace(" ", "_") if obj.label else "group_field",
            "label": obj.label,
            **({"icon": obj.icon} if obj.icon else {}),
            **({"title": obj.title} if obj.title else {}),
        }
    )


class DatepickerNodeFactory(FormKitSchemaNodeFactory):
    node_type = "$formkit"
    label = Faker("sentence", nb_words=2)
    node = LazyAttribute(
        lambda obj: {
            "$formkit": "datepicker",
            "name": obj.label.lower().replace(" ", "_") if obj.label else "datepicker_field",
            "label": obj.label,
            "format": "DD/MM/YY",
            "calendarIcon": "calendar",
        }
    )
    additional_props = None


class DropdownNodeFactory(FormKitSchemaNodeFactory):
    node_type = "$formkit"
    label = Faker("sentence", nb_words=2)
    option_group = SubFactory(OptionGroupFactory)
    node = LazyAttribute(
        lambda obj: {
            "$formkit": "dropdown",
            "name": obj.label.lower().replace(" ", "_") if obj.label else "dropdown_field",
            "label": obj.label,
            "placeholder": "Please select",
            "selectIcon": "angleDown",
        }
    )


class AutocompleteNodeFactory(FormKitSchemaNodeFactory):
    node_type = "$formkit"
    label = Faker("sentence", nb_words=2)
    option_group = SubFactory(OptionGroupFactory)
    node = LazyAttribute(
        lambda obj: {
            "$formkit": "autocomplete",
            "name": obj.label.lower().replace(" ", "_") if obj.label else "autocomplete_field",
            "label": obj.label,
        }
    )


class SelectNodeFactory(FormKitSchemaNodeFactory):
    node_type = "$formkit"
    label = Faker("sentence", nb_words=2)
    option_group = SubFactory(OptionGroupFactory)
    node = LazyAttribute(
        lambda obj: {
            "$formkit": "select",
            "name": obj.label.lower().replace(" ", "_") if obj.label else "select_field",
            "label": obj.label,
        }
    )


class RadioNodeFactory(FormKitSchemaNodeFactory):
    node_type = "$formkit"
    label = Faker("sentence", nb_words=2)
    option_group = SubFactory(OptionGroupFactory)
    node = LazyAttribute(
        lambda obj: {
            "$formkit": "radio",
            "name": obj.label.lower().replace(" ", "_") if obj.label else "radio_field",
            "label": obj.label,
        }
    )


class ElementNodeFactory(FormKitSchemaNodeFactory):
    node_type = "$el"
    label = None
    text_content = None
    node = LazyAttribute(
        lambda obj: {
            "$el": "span",
            "attrs": {"class": "test-class"},
            "children": obj.text_content or "Test content",
        }
    )


class ConditionalNodeFactory(FormKitSchemaNodeFactory):
    """Factory for nodes with conditional logic (if conditions)"""

    node_type = "$formkit"
    label = Faker("sentence", nb_words=2)
    node = LazyAttribute(
        lambda obj: {
            "$formkit": "text",
            "name": obj.label.lower().replace(" ", "_") if obj.label else "conditional_field",
            "label": obj.label,
            "if": "$get(parent_field).value",
        }
    )


class FormKitSchemaFactory(DjangoModelFactory):
    class Meta:
        model = models.FormKitSchema

    label = Faker("sentence", nb_words=3)

    @post_generation
    def add_nodes(self, create, extracted, **kwargs):
        if not create:
            return
        if extracted:
            for idx, node in enumerate(extracted):
                models.FormComponents.objects.create(schema=self, node=node, order=idx, label=str(node))


class NodeChildrenFactory(DjangoModelFactory):
    class Meta:
        model = models.NodeChildren

    parent = SubFactory(FormKitSchemaNodeFactory)
    child = SubFactory(FormKitSchemaNodeFactory)
    order = 0
