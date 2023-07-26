from typing import Callable, Literal

from formkit_ninja.formkit_schema import FormKitSchemaFormKit, GroupNode, RepeaterNode


def suggest_model_name(form_path: tuple[str, ...]):
    """
    Single reference for table name and foreign key references
    """
    model_name = "".join((c.capitalize() for c in form_path))
    return model_name


def to_pydantic(
    form_name: str, form_path: tuple[str, ...], node: FormKitSchemaFormKit, log: Callable[[str], None]
) -> Literal["str", "int", "bool", "Decimal", "float", "date"]:
    if getattr(node, "options", None) == "$getoptions.translatedOptions('Yes', 'No')":
        return "bool"

    if node.formkit == "number":
        if node.step is not None:
            # We don't actually **know** this but it's a good assumption
            return "float"
        return "int"

    # Select, Dropdown or Radio can be any value
    # We need to differentiate between "lookup string" and "lookup integer" here
    # if node.formkit in {"select", "dropdown", "radio"}:
    match (node.formkit, node.name):
        case [_, ("sector" | "unit" | "activity_type" | "year" | "month" | "round" | "unit")]:
            return "int"

        case [("select" | "dropdown" | "radio"), ("project_sector" | "project_sub_sector" | "output")]:
            return "int"

        case [("select" | "dropdown" | "radio"), ("suco" | "district" | "administrative_post" | "suco" | "aldeia")]:
            return "int"

        case [("select" | "dropdown" | "radio"), _]:
            log(f"Underspecified field {node.formkit} field {node.name}. Defaulting to text.")
            return "str"

    match node.formkit:
        case "text":
            return "str"
        case "number":
            log(
                f"Underspecified field {node.formkit} field {node.name}. Could be int, float, or decimal. Defaulting to float."
            )
            return "float"
        case "select" | "dropdown" | "radio":
            log(f"Underspecified {node.formkit} field {node.name}. Defaulting to string.")
            return "str"
        case "datepicker":
            return "datetime"
        case "currency":
            return "Decimal"
        case "tel":
            return "int"

    log(f"Unknown field {node.formkit} field {node.name}. Defaulting to string.")
    return "str"


postgres_type = Literal["int", "text", "boolean", "NUMERIC(15,2)"]
django_type = Literal["ForeignKey", "DateField", "DateTimeField", "DecimalField", "ForeignKey", "OneToOneField"]


def to_postgres(
    form_name: str, form_path: tuple[str, ...], node: FormKitSchemaFormKit, log: Callable[[str], None]
) -> postgres_type:
    """
    Returns a suitable Postgres field type for data coerced from JSON
    """

    match to_pydantic(form_name, form_path, node, log):
        case "bool":
            return "boolean"
        case "str":
            return "text"
        case "Decimal":
            return "NUMERIC(15,2)"
        case "int":
            return "int"
        case "float":
            return "float"

    return "text"


def to_django(
    form_name: str, form_path: tuple[str, ...], node: FormKitSchemaFormKit, log: Callable[[str], None]
) -> tuple[django_type, tuple[str, ...]]:
    """
    Returns a string suitable for a Django models file `field` parameter
    """

    if isinstance(node, RepeaterNode):
        return "ForeignKey", (suggest_model_name((form_name, *form_path, node.name)), "on_delete=models.CASCADE")

    if isinstance(node, GroupNode):
        return "OneToOneField", (suggest_model_name((form_name, *form_path, node.name)), "on_delete=models.CASCADE")

    # Some well named fields are easy to describe
    match node.name:
        case "district":
            return "ForeignKey", ("pnds_data.zDistrict", "on_delete=models.CASCADE")
        case "administrative_post":
            return "ForeignKey", ("pnds_data.zSubdistrict", "on_delete=models.CASCADE")
        case "suco":
            return "ForeignKey", ("pnds_data.zSuco", "on_delete=models.CASCADE")
        case "aldeia":
            return "ForeignKey", ("pnds_data.zAldeia", "on_delete=models.CASCADE")
        case "sector":
            return "ForeignKey", ("pnds_data.zSector", "on_delete=models.CASCADE")
        case "unit":
            return "ForeignKey", ("pnds_data.zUnits", "on_delete=models.CASCADE")
        case "sector":
            return "ForeignKey", ("pnds_data.zSector", "on_delete=models.CASCADE")
        case "unit":
            return "ForeignKey", ("pnds_data.zUnits", "on_delete=models.CASCADE")

    match to_pydantic(form_name, form_path, node, log):
        case "bool":
            return "BooleanField", ()
        case "str":
            return "TextField", ()
        case "Decimal":
            return "DecimalField", ("max_digits=20", "decimal_places=2")
        case "int":
            return "IntegerField", ()
        case "float":
            return "FloatField", ()
        case "datetime":
            return "DateTimeField", ()
        case "date":
            return "DateField", ()
