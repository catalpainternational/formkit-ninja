"""
Rewritten PartisipaNodePath using enhanced FormKit generator features.

This demonstrates how the new features (enhanced registry, helper methods,
extension points) can simplify PartisipaNodePath customization.
"""

import warnings

from formkit_ninja.parser.converters import TypeConverterRegistry
from formkit_ninja.parser.converters_examples import (
    FieldNameConverter,
    OptionsPatternConverter,
)
from formkit_ninja.parser.type_convert import NodePath


def create_partisipa_registry() -> TypeConverterRegistry:
    """
    Create a custom TypeConverterRegistry for Partisipa with converters
    that match by options patterns and field names.
    """
    registry = TypeConverterRegistry()

    # Register IDA options converter (matches $ida(...) patterns)
    registry.register(
        OptionsPatternConverter(pattern="$ida(", pydantic_type="int"),
        priority=20,
    )

    # Register getoptions converter (deprecated, but still supported)
    registry.register(
        OptionsPatternConverter(pattern="$getoptions", pydantic_type="bool"),
        priority=15,
    )

    # Register field name converters for specific field types
    registry.register(
        FieldNameConverter(
            names={
                "activity_type",
                "activity_subtype",
                "project_sector",
                "project_sub_sector",
                "district",
                "administrative_post",
                "suco",
                "aldeia",
                "sector",
                "unit",
                "month",
                "year",
                "round",
                "output",
            },
            pydantic_type="int",
        ),
        priority=10,
    )

    # Register latitude/longitude as Decimal
    registry.register(
        FieldNameConverter(names={"latitude", "longitude"}, pydantic_type="Decimal"),
        priority=10,
    )

    # Register date_exit_committee as date_
    registry.register(
        FieldNameConverter(names={"date_exit_committee"}, pydantic_type="date_"),
        priority=10,
    )

    return registry


class PartisipaNodePathRewritten(NodePath):
    """
    Rewritten PartisipaNodePath using enhanced FormKit generator features.

    This version uses:
    - Custom TypeConverterRegistry for type conversion (instead of overriding to_pydantic_type)
    - Helper methods (has_option, matches_name) for cleaner attribute checks
    - get_django_args_extra() extension point (instead of full to_django_args override)
    """

    def __init__(self, *args, **kwargs):
        """Initialize with custom registry if not provided."""
        if "type_converter_registry" not in kwargs:
            kwargs["type_converter_registry"] = create_partisipa_registry()
        super().__init__(*args, **kwargs)

    @property
    def filter_clause(self):
        """
        Returns a "filter" clause for the Django ORM.
        This adds classes based on the "form name" for certain special cases
        and adds more general "status" filters for all other forms.
        """
        # Non repeaters will have at least a status on 'Submission Status'
        # The Financial forms (FF4, FF12, POM) filter based on Suco and Year
        if self.classname in {"Cfm_2_ff_4", "Cfm_12_ff_12", "Pom_1"}:
            return "SubstatusYearSucoFilter"
        elif self.classname in {
            "Sf_2_3Priorities",
            "Sf_1_3Repeaterprojectteam",
            "Sf_1_3Repeaterplanning",
            "Sf_1_3Repeatersukus",
        }:
            return "PriorityFilter"
        elif self.classname == "Sf_2_3":
            return "SubStatusSucoFilter"
        # The default case is only to filter on status
        # or parent status, if it's a repeater
        return "RepeaterSubStatusFilter" if self.is_repeater else "SubStatusFilter"

    @property
    def extra_attribs(self) -> list[str]:
        """
        If this node has a depth of 1 (root level), it has a ForeignKey to Submission.
        """
        if self.depth == 1:
            return [
                'submission = models.OneToOneField("form_submission.Submission", '
                "on_delete=models.CASCADE, primary_key=True)"
            ]
        return super().extra_attribs

    @property
    def extra_attribs_schema(self) -> list[str]:
        """
        If this node has a depth of 1, it has a ForeignKey to Submission.
        """
        if self.depth == 1:
            return ["submission_id: UUID"]
        return super().extra_attribs_schema

    @property
    def extra_attribs_basemodel(self) -> list[str]:
        """
        If this node has a depth of 1, it has a ForeignKey to Submission.
        """
        if self.depth == 1:
            return ["id: UUID", f'form_type: Literal["{self.fieldname}"]']
        return super().extra_attribs_basemodel

    @property
    def _ida_model(self) -> str | None:
        """
        Returns the related model for this node, if it's an IDA option.
        This fetches a model name from an options starting with an `$ida(`
        This skips special cases: 'month' and 'year' which we want to treat as integers,
        not as foreign keys.
        """
        # Use helper method instead of direct attribute access
        if not self.has_option("$ida("):
            # Also check for deprecated getoptions pattern
            if self.has_option("$getoptions.tf1321.outputs"):
                warnings.warn(
                    "There is a reference to `getoptions` which should be altered to an `ida`",
                    DeprecationWarning,
                )
                warnings.warn("Faking this as an ida Output not a zOutput")
                return "ida_options.Output"
            return None

        # Get options value using helper method
        opts = self.get_option_value()
        if not opts:
            return None

        # Formkit does not have access to "Option" class and subclasses
        # So we need to fake it. In the real Partisipa codebase, Option.str_to_model()
        # returns a Django model instance, but here we need to extract the model name
        # from the options string directly.
        # Format: "$ida(ModelName)" -> "ida_options.ModelName"
        if opts.startswith("$ida(") and opts.endswith(")"):
            model_name = opts[5:-1]  # Extract "ModelName" from "$ida(ModelName)"
            ida_option_candidate = f"ida_options.{model_name}"
            if ida_option_candidate in {"ida_options.Year", "ida_options.Month"}:
                return None
            return ida_option_candidate
        return None

    def to_django_type(self) -> str:
        """Convert option-based fields to ForeignKeys to ida_options models."""
        if self._ida_model:
            return "ForeignKey"

        # Use helper method for cleaner code
        if self.matches_name({"district", "administrative_post", "suco", "aldeia", "sector", "unit"}):
            return "ForeignKey"

        if self.matches_name({"latitude", "longitude"}):
            return "DecimalField"

        if self.to_pydantic_type() == "date_":
            return "DateField"

        return super().to_django_type()

    def get_django_args_extra(self) -> list[str]:
        """
        Add custom Django field arguments using the extension point.
        This is cleaner than overriding the entire to_django_args() method.
        """
        extra_args = []

        # Custom decimal places for latitude/longitude
        if self.pydantic_type == "Decimal":
            if self.matches_name({"latitude", "longitude"}):
                extra_args = ["max_digits=20", "decimal_places=12"]
            else:
                extra_args = ["max_digits=20", "decimal_places=2"]
            return extra_args

        # UUID fields get unique=True
        if self.pydantic_type == "UUID":
            extra_args = ["editable=False", "unique=True"]
            return extra_args

        # IDA model references
        if self._ida_model:
            extra_args.append(f'"{self._ida_model}"')
            extra_args.append("on_delete=models.DO_NOTHING")
            if self._ida_model == "ida_options.YesNo":
                extra_args.append('related_name="+"')
            return extra_args

        # zTable references (non-IDA ForeignKeys)
        # Check if this would be a ForeignKey by checking the same conditions as to_django_type()
        if self.matches_name({"district", "administrative_post", "suco", "aldeia", "sector", "unit"}):
            warnings.warn("This model uses a zTable not an IDA options", DeprecationWarning)
            # Use helper method for cleaner code
            if self.matches_name({"district"}):
                extra_args.append('"pnds_data.zDistrict"')
            elif self.matches_name({"administrative_post"}):
                extra_args.append('"pnds_data.zSubdistrict"')
            elif self.matches_name({"suco"}):
                extra_args.append('"pnds_data.zSuco"')
            elif self.matches_name({"aldeia"}):
                extra_args.append('"pnds_data.zAldeia"')
            elif self.matches_name({"sector"}):
                extra_args.append('"pnds_data.zSector"')
            elif self.matches_name({"unit"}):
                extra_args.append('"pnds_data.zUnits"')

            extra_args.append("on_delete=models.CASCADE")

        return extra_args

    @property
    def validators(self):
        """
        Return "extra" validation field for schemas.py.
        """
        validators_list = list(super().validators)

        if self.to_pydantic_type() == "date_":
            validate_fn = "v_date"
            validators_list.append(f'_normalize_{self.fieldname} = {validate_fn}("{self.fieldname}")')

        if self.matches_name({"latitude", "longitude"}):
            validate_fn = "v_decimal"
            validators_list.append(f'_normalize_{self.fieldname} = {validate_fn}("{self.fieldname}")')

        return validators_list
