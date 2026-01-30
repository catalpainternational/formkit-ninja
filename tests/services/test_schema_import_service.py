import pytest

from formkit_ninja import formkit_schema, models
from formkit_ninja.services.schema_import import SchemaImportService


@pytest.mark.django_db
def test_import_options_creates_options_and_labels() -> None:
    group = models.OptionGroup.objects.create(group="test-group")
    options = ["Option A", {"value": "option-b", "label": "Option B"}]

    created = list(SchemaImportService.import_options(options, group=group))

    assert len(created) == 2
    assert models.Option.objects.filter(group=group).count() == 2
    assert models.OptionLabel.objects.filter(option=created[0], label="Option A", lang="en").exists()
    assert models.OptionLabel.objects.filter(option=created[1], label="Option B", lang="en").exists()


@pytest.mark.django_db
def test_import_schema_creates_schema_and_components() -> None:
    schema = formkit_schema.FormKitSchema.parse_obj([{"$formkit": "text", "name": "field1"}])

    created = SchemaImportService.import_schema(schema, label="Test Schema")

    assert created.label == "Test Schema"
    assert models.FormKitSchema.objects.filter(id=created.id).exists()
    assert models.FormComponents.objects.filter(schema=created).count() == 1
