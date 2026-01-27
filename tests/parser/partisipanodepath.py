import warnings

from formkit_ninja.parser.type_convert import NodePath


class PartisipaNodePath(NodePath):
    """
    Partisipa nodes have an associated "form name"
    """

    @property
    def filter_clause(self):
        """
        Returns a "filter" clause for the Django ORM
        This adds classes based on the "form name" for
        certain special cases and adds more general "status" filters for all other
        forms
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
        If this node has a depth of zero, it has a ForeignKey to Submission
        """
        if self.depth == 1:
            return [
                """submission = models.OneToOneField(
                    "form_submission.Submission",
                    on_delete=models.CASCADE,
                    primary_key=True
                )"""
            ]
        return super().extra_attribs

    @property
    def extra_attribs_schema(self) -> list[str]:
        """
        If this node has a depth of zero, it has a ForeignKey to Submission
        """
        if self.depth == 1:
            return ["submission_id: UUID"]
        return super().extra_attribs_schema

    @property
    def extra_attribs_basemodel(self) -> list[str]:
        """
        If this node has a depth of zero, it has a ForeignKey to Submission
        """
        if self.depth == 1:
            return ["id: UUID", f'form_type: Literal["{self.fieldname}"]']
        return super().extra_attribs_schema

    def to_pydantic_type(self):
        if getattr(self.node, "options", "") == "$getoptions.translatedOptions('Yes', 'No')":
            return "bool"
        if getattr(self.node, "options", "") == "$getoptions.common.translatedOptions('Yes', 'No')":
            return "bool"
        if getattr(self.node, "options", "") == "$ida(yesno)":
            return "bool"
        if getattr(self.node, "formkit", "") == "currency":
            return "Decimal"
        if getattr(self.node, "formkit", "") == "uuid":
            return "UUID"
        if getattr(self.node, "formkit", "") == "datepicker":
            return "date_"  # Note that this is to avoid shadowing

        if self._ida_model:
            return "int"

        if self.node.name in (
            "activity_type",
            "activity_subtype",
            "project_sector",
            "project_sub_sector",
        ):
            return "int"
        if self.node.name in {
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
        }:
            return "int"
        if self.node.name == "date_exit_committee":
            return "date_"
        if self.node.name in {"latitude", "longitude"}:
            return "Decimal"
        return super().to_pydantic_type()

    @property
    def _ida_model(self) -> str | None:
        """
        Returns the related model for this node, if it's an IDA option
        This fetches a model name from an options starting with an `$ida(`
        This skips special cases: 'month' and 'year' which we want to treat as integers,
        not as foreign keys
        """
        opts = getattr(self.node, "options", None)

        # Formkit does not have access to "Option" class and subclasses
        # So we need to fake it
        class Option:
            @staticmethod
            def str_to_model(opts: str):
                return opts

        if isinstance(opts, str) and opts.startswith("$ida("):
            ida_option_candidate = Option.str_to_model(opts)._meta.label
            if ida_option_candidate in {"ida_options.Year", "ida_options.Month"}:
                return None
            return ida_option_candidate
        elif isinstance(opts, str) and opts.startswith("$getoptions.tf1321.outputs"):
            warnings.warn(
                "There is a reference to `getoptions` which should be altered to an `ida`", DeprecationWarning
            )
            warnings.warn("Faking this as an ida Output not a zOutput")
            return Option.str_to_model("$ida(output)")._meta.label
        else:
            return None

    def to_django_type(self) -> str:
        if self._ida_model:
            return "ForeignKey"

        if self.node.name in {
            "district",
            "administrative_post",
            "suco",
            "aldeia",
            "sector",
            "unit",
        }:
            return "ForeignKey"

        if self.node.name in {"latitude", "longitude"}:
            return "DecimalField"

        if self.to_pydantic_type() == "date_":
            return "DateField"

        return super().to_django_type()

    def to_django_args(self):
        # Everything is considered optional: "null" and "blank"
        default_opts = ("null=True", "blank=True")
        extra_opts: list[str] = []

        if self.pydantic_type == "Decimal":
            if self.node.name in {"latitude", "longitude"}:
                extra_opts = ["max_digits=20", "decimal_places=12"]
            else:
                extra_opts = ["max_digits=20", "decimal_places=2"]
        elif self.pydantic_type == "UUID":
            extra_opts = ["editable=False", "unique=True"]
        if self._ida_model:
            extra_opts.append(self._ida_model)
            extra_opts.append("on_delete=models.DO_NOTHING")
            if self._ida_model == "ida_options.YesNo":
                extra_opts.append('related_name="+"')

        else:
            if self.django_type == "ForeignKey":
                warnings.warn("This model uses a zTable not an IDA options", DeprecationWarning)
            match self.node.name:
                case "district":
                    extra_opts.append("pnds_data.zDistrict")
                case "administrative_post":
                    extra_opts.append("pnds_data.zSubdistrict")
                case "suco":
                    extra_opts.append("pnds_data.zSuco")
                case "aldeia":
                    extra_opts.append("pnds_data.zAldeia")
                case "sector":
                    extra_opts.append("pnds_data.zSector")
                case "unit":
                    extra_opts.append("pnds_data.zUnits")
                case "sector":
                    extra_opts.append("pnds_data.zSector")
                case "unit":
                    extra_opts.append("pnds_data.zUnits")

            if self.django_type == "ForeignKey":
                extra_opts.append("on_delete=models.CASCADE")
        return ", ".join((*extra_opts, *default_opts))

    @property
    def validators(self):
        """
        Return "extra" validation field for schemas.py
        """
        # if isinstance(self.node, CurrencyNode):
        #     validate_fn = "v_currency"
        #     return [f'_normalize_{self.fieldname} = {validate_fn}("{self.fieldname}")', *super().validators]

        if self.to_pydantic_type() == "date_":
            validate_fn = "v_date"
            return [f'_normalize_{self.fieldname} = {validate_fn}("{self.fieldname}")', *super().validators]

        if self.node.name in {"latitude", "longitude"}:
            validate_fn = "v_decimal"
            return [f'_normalize_{self.fieldname} = {validate_fn}("{self.fieldname}")', *super().validators]

        return super().validators
