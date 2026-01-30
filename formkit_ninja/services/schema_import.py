"""
Schema import services to keep model methods thin.
"""

from __future__ import annotations

from typing import Iterable, cast

from formkit_ninja import formkit_schema, models


class SchemaImportService:
    """Service for importing schemas and options into the database."""

    @staticmethod
    def import_options(
        options: list[str] | list[models.OptionDict],
        group: models.OptionGroup | None = None,
    ) -> Iterable[models.Option]:
        for option in options:
            if isinstance(option, str):
                opt = models.Option(value=option, group=group)
                opt.save()
                opt.refresh_from_db()
                models.OptionLabel.objects.create(option=opt, lang="en", label=option)
            elif isinstance(option, dict) and option.keys() == {"value", "label"}:
                opt = models.Option(value=option["value"], group=group)
                models.OptionLabel.objects.create(option=opt, lang="en", label=option["label"])
            else:
                models.console.log(f"[red]Could not format the given object {option}")
                continue
            yield opt

    @staticmethod
    def import_schema(
        input_model: formkit_schema.FormKitSchema,
        label: str | None = None,
    ) -> models.FormKitSchema:
        instance = models.FormKitSchema.objects.create(label=label)
        nodes: Iterable[models.FormKitSchemaNode] = models.FormKitSchemaNode.from_pydantic(
            cast(Iterable[formkit_schema.FormKitSchemaProps], input_model.__root__)
        )
        for node in nodes:
            models.log(f"[yellow]Saving {node}")
            node.save()
            models.FormComponents.objects.create(
                schema=instance,
                node=node,
                label=str(f"{str(instance)} {str(node)}"),
            )
        models.logger.info("Schema load from JSON done")
        return instance
