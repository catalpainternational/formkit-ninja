import json
import os
import warnings
from collections import defaultdict
from contextlib import AbstractContextManager
from importlib import resources
from io import StringIO
from keyword import iskeyword
from pathlib import Path
from string import Template
from textwrap import dedent, indent
from typing import Iterable, Literal, Optional

import black
import sqlparse
from django.db import connection
from rich.console import Console
from rich.markup import escape

from formkit_ninja.formkit_schema import (
    FormKitNode,
    FormKitSchemaDOMNode,
    FormKitSchemaFormKit,
    GroupNode,
    RepeaterNode,
)

from . import type_convert

strings = tuple[str, ...]

console = Console()
log = console.log


class FormKitInput(GroupNode):
    """
    This ported from typescript class of the same name
    """

    id: str
    title: str
    children: list[FormKitSchemaFormKit | FormKitSchemaDOMNode]
    icon: Optional[str] = None
    sectionTitle: Optional[str] = None


class chdir(AbstractContextManager):
    """This is a backport of contextlib.chdir."""

    def __init__(self, path):
        self.path = path
        self._old_cwd = []

    def __enter__(self):
        self._old_cwd.append(os.getcwd())
        os.chdir(self.path)

    def __exit__(self, *excinfo):
        os.chdir(self._old_cwd.pop())


def safe_name(name: str) -> str:
    if not name.isidentifier() or iskeyword(name):
        raise KeyError(f"The name:  '''{name}''' is not a valid identifier")
    return name


def nodename(node: FormKitSchemaFormKit):
    """
    Returns a node "name", possibly altered to fit Python semantics
    ie no leading digits
    """
    return safe_name(node.name)


def process_node(innode: dict | str) -> FormKitSchemaDOMNode | FormKitSchemaFormKit | None:
    """
    Handle the definition of a "node"
    as returned via the typescript fetch
    """

    if isinstance(innode, str):
        return innode
    if child_inputs := innode.get("children", None):
        children = list(map(process_node, child_inputs))
    else:
        children = None

    try:
        if element := innode.get("$el", None):
            props = {**innode, "node_type": "element", "element": element}
        elif formkit := innode.get("$formkit", None):
            props = {**innode, "children": children, "node_type": "formkit", "formkit": formkit}
        else:
            warnings.warn("unhandled node type", RuntimeWarning)
            return None
        return FormKitNode(__root__=props).__root__
    except Exception as E:
        warnings.warn(f"{E}", RuntimeWarning)
    return None


JSONB_TYPE_RETURN = Literal["object", "array", "string", "number", "boolean", "null"]


def process_forms_to_postgres(forms: Iterable[tuple[str, FormKitInput]]):
    """
    Returns a query
    """

    def exception_notice(text, message: str = "This query raised an error"):
        """
        Execute the text. If the query fails yield a notice
        """
        try:
            with connection.cursor() as c:
                c.execute(text)
                # pprint(dedent(text))
                # pprint(c.fetchall())
        except Exception as E:
            yield f"\n-- {message}\n"
            yield f"/* {E} */\n"
        yield text
        yield ";\n"

    def pg_typedef(fkinputs: Iterable[FormKitSchemaFormKit]):
        """
        Returns a list of postgres json "field names" and "types
        """
        return [
            f'"{nf.name}" {type_convert.to_postgres(form_name, (part["id"],), nf, log)}'
            for nf in non_grouped(fkinputs)
        ]

    def format_pgtypedef(definition, indent=8):
        """
        Indent a return from the `pg_typedef` function
        """
        return " " * indent + (",\n" + " " * indent).join(definition)

    def repeater_handler(form_name: str, part, node: RepeaterNode):
        """
        Returns a query for a 'Repeater Node' or a "Group Node"
        These differ in that a "Group Node" is a single level of nesting and
        a "Repeater Node" is a nested array
        """
        nested_fields_breakdown = Template(
            dedent(
                """
                with selection as (
                    select key, form_type, repeater, pos
                        from form_submission_submission
                        cross join lateral
                        jsonb_array_elements(${field} -> '${repeater_name}') with ordinality as t(repeater, pos)
                        where form_type = '${form_name}'
                )
                select
                    key,
                    selection.pos,
                    selection.form_type,
                    temp_type.*
                    from
                selection,
                jsonb_to_record(repeater)
                as temp_type(
                ${temp_definition}
                );
                        """
            )
        )

        text = nested_fields_breakdown.substitute(
            repeater_name=n.name,
            form_name=form_name,
            temp_definition=format_pgtypedef(pg_typedef(node.children)),
            field="fields -> '{node.name}'",
        )
        yield f'-- json generated for {form_name} {part["title"]}\n'
        yield from exception_notice(text)

    def group_handler(form_name: str, part, node: GroupNode):
        template = Template(
            dedent(
                """
        select
            fss.key,
            fss.form_type,
            temp_type.*
        from
            form_submission_submission fss,
            jsonb_to_record(${field}) as temp_type(
                ${temp_definition}
            )
        where form_type = '${form_name}'
        """
            )
        )
        text = template.substitute(
            form_name=form_name,
            temp_definition=format_pgtypedef(pg_typedef(node.children)),
            field=f"fields -> '{node.name}'",
        )
        yield f'-- json generated for {form_name} {part["title"]}\n'
        yield from exception_notice(text)

    def nodes_handler(form_name: str, part, nodes: Iterable[FormKitNode]):
        """
        Returns a query for a form with no repeaters
        """
        definition = pg_typedef(nodes)
        if len(definition) == 0:
            yield f"--  No fields associated for {form_name} {part['title']}\n"
            return

        # Most simple forms will have only one level
        top_level_breakdown = Template(
            dedent(
                """
                select form_type, key, temp_type.* from form_submission_submission fss
                cross join lateral
                    jsonb_to_record(${field})
                    as temp_type(
                ${temp_definition}
                    )
                    where form_type = '${form_name}'
                    """
            )
        )

        text = top_level_breakdown.substitute(
            form_name=form_name, temp_definition=format_pgtypedef(definition), field="fields"
        )

        yield f"-- json generated for {form_name} {part['title']}\n"
        yield from exception_notice(text)

    for form_name, part in forms:
        nodes = [process_node(n) for n in part["children"]]

        yield from nodes_handler(form_name, part, nodes)

        for n in groups(nodes):
            yield from group_handler(form_name, part, n)

        for n in repeaters(nodes):
            yield from repeater_handler(form_name, part, n)


def repeaters(nodes: Iterable[FormKitSchemaFormKit | FormKitSchemaDOMNode]):
    yield from (n for n in nodes if isinstance(n, RepeaterNode))


def groups(nodes: Iterable[FormKitSchemaFormKit | FormKitSchemaDOMNode]):
    yield from (n for n in nodes if isinstance(n, GroupNode))


def non_grouped(nodes: Iterable[FormKitSchemaFormKit | FormKitSchemaDOMNode]):
    yield from (n for n in nodes if not isinstance(n, (GroupNode, RepeaterNode, FormKitSchemaDOMNode)))


def get_django_fields(
    form_name: str,
    form_path: strings,
    nodes: Iterable[FormKitSchemaFormKit | FormKitSchemaDOMNode],
    abstract=True,
    ordinality_column=False,
):
    """
    Returns Python code describing a sequence of FormKit fields
    as a Django model
    """

    rows: list[tuple[str, str | None, str, strings]] = []

    if ordinality_column:
        rows.append(("order", None, "IntegerField", ()))

    for node in (n for n in nodes if not isinstance(n, FormKitSchemaDOMNode)):
        field_type, field_args = type_convert.to_django(form_name, form_path, node, log)
        rows.append((node.name, node.formkit, field_type, field_args))

    # If I have a "group" or "repeater" it becomes a separate model and a ForeignKey in the current model
    # Repeaters and Groups
    for repeater in repeaters(nodes):
        yield from get_django_fields(
            form_name, (*form_path, str(repeater.name)), repeater.children, abstract=False, ordinality_column=True
        )

    for group in groups(nodes):
        yield from get_django_fields(form_name, (*form_path, str(group.name)), group.children, abstract=False)

    # This yield comes after "repeater" and "group" as these will be foreign keys to the main model
    yield (form_path, rows, abstract)


def get_django_models(
    form_name: str, form_path: strings, nodes: Iterable[FormKitSchemaFormKit | FormKitSchemaDOMNode]
):
    """
    Returns one or more `model.Models` code blocks defining Model instances from
    a formkit schema

    Each "section" is an abstract model
    Each "form name" and "repeater" and "group" defines a concrete model
    """
    text_content = []
    abstract_model_names = []
    for model_path, field_definitions, abstract in get_django_fields(form_name, form_path, nodes):
        model_name = type_convert.suggest_model_name((form_name, *model_path))
        # A single form is defined as multiple 'abstract' forms
        text_content.append(f"class {model_name}(models.Model):\n")
        text_content.append(indent(f'"""\n{form_name} form\nSection: {" ".join(model_path)}\n"""\n', " " * 4))
        if abstract:
            abstract_model_names.append(model_name)
            text_content.append("    class Meta:\n")
            text_content.append("        abstract=True\n")
        enumerated = 0
        for fieldname, formkit_type, field_type, args in field_definitions:
            enumerated += 1
            argslist = ", ".join(args) if args else ""
            text_content.append(f"    {safe_name(fieldname)} = models.{field_type}({argslist})\n")
        if enumerated == 0:
            text_content.append("    pass\n")

    return text_content, abstract_model_names


def models_dot_py(forms: Iterable[tuple[str, FormKitInput]]):
    abstracts = defaultdict(list)
    with StringIO() as i:
        # Add some common imports
        i.write("from django.db import models\n")
        i.write("from pnds_data import models as pnds_data\n")

        for form_name, part in forms:
            nodes: list[FormKitSchemaFormKit] = [process_node(n) for n in part["children"]]
            # Fetch the tables as Django models
            # These are all the models for a given schema
            model_definitions, model_names = get_django_models(form_name, (part["id"],), nodes)
            abstracts[form_name].extend(model_names)
            i.writelines(model_definitions)

        for model_id, abstract_model_names in abstracts.items():
            i.write(f'class {model_id.capitalize()}({", ".join(abstract_model_names)}):\n')
            i.write("    pass\n")
        i.seek(0)
        file_content = black.format_str(i.read(), mode=black.Mode())

    return file_content


def get_pydantic_fields(
    form_name: str,
    form_path: strings,
    nodes: list[FormKitSchemaFormKit | FormKitSchemaDOMNode],
    ordinality_column=False,
    optional=True,
):
    """
    Returns Python code describing a sequence of FormKit fields
    as a Pydantic model
    """

    rows: list[tuple[str, str | None, str, strings]] = []
    if ordinality_column:
        rows.append(("order", None, "int", ()))

    for node in (n for n in nodes if not isinstance(n, FormKitSchemaDOMNode)):
        field_type: str = ""

        if isinstance(node, GroupNode):
            field_type = type_convert.suggest_model_name((form_name, *form_path, node.name))

        elif isinstance(node, RepeaterNode):
            field_type = f"list[{type_convert.suggest_model_name((form_name, *form_path, node.name))}]"

        else:
            field_type = type_convert.to_pydantic(form_name, form_path, node, log)

        if optional:
            field_type = f"Optional[{field_type}]"
        rows.append((str(node.name), str(node.formkit), field_type, ()))

    # If I have a "group" or "repeater" it becomes a separate model and a ForeignKey in the current model
    # Repeaters and Groups
    for repeater in repeaters(nodes):
        yield from get_pydantic_fields(form_name, (*form_path, str(repeater.name)), repeater.children)

    for group in groups(nodes):
        yield from get_pydantic_fields(form_name, (*form_path, str(group.name)), group.children)

    # This yield comes after "repeater" and "group" as these will be foreign keys to the main model
    yield (form_path, rows)


def pydantic_base_models(form_name: str, form_path: tuple[str], nodes) -> tuple[list[str], list[str]]:
    text_content = []
    abstract_model_names = []

    # Keep track of "currency" fields for coercion to "decimal"
    for model_path, field_definitions in get_pydantic_fields(form_name, form_path, nodes):
        currency_fields = []

        model_name = type_convert.suggest_model_name((form_name, *model_path))
        # A single form is defined as multiple 'abstract' forms
        log(": ".join((form_name, *model_path)))
        text_content.append(f"class {model_name}(BaseModel):\n")
        text_content.append(indent(f'"""\n{form_name} form\nSection: {" ".join(model_path)}\n"""\n', " " * 4))
        abstract_model_names.append(model_name)
        enumerated = 0
        for fieldname, formkit_type, field_type, args in field_definitions:
            enumerated += 1
            # argslist = ", ".join(args) if args else ""
            text_content.append(f"    {safe_name(fieldname)}: {field_type}\n")
            log(f"  {fieldname} {formkit_type} {escape(field_type)} {args}")

            if formkit_type == "currency":
                currency_fields.append(safe_name(fieldname))

        if enumerated == 0:
            text_content.append("    pass\n")

        for cf in currency_fields:
            text_content.append(f'    _normalize_{cf} = v_currency("{cf}")\n')

    return text_content, abstract_model_names


def schema_dot_py(forms: Iterable[tuple[str, FormKitInput]]):
    abstracts: dict[str, Iterable[str]] = defaultdict(list)

    def imports(io_: StringIO):
        io_.writelines(
            [
                "from pydantic import BaseModel, validator\n",
                "from datetime import datetime\n",
                "from typing import Any, Optional\n",
                "from decimal import Decimal\n",
                "\n",
                "\n",
            ]
        )

    def validators(io_: StringIO):
        io_.writelines(
            [
                "def currency_to_decimal(currency: str | Decimal) -> Decimal:\n",
                "    if isinstance(currency, Decimal):\n",
                "        return currency\n",
                "    if isinstance(currency, str):\n",
                "        return Decimal(currency.replace(',', ''))\n",
                "\n",
                "\n",
                "def v_currency(field_name: str):\n",
                "    return validator(field_name, allow_reuse=True, pre=True)(currency_to_decimal)\n",
                "\n",
                "\n",
            ]
        )

    def factory(io_: StringIO):
        # Add a factory method
        io_.write("def get_submission_method(form_type: str) -> type[BaseModel]:\n")
        io_.write("    match form_type.upper():\n")
        for model_id, abstract_model_names in abstracts.items():
            io_.write(f'        case "{model_id.upper()}":\n')
            io_.write(f"            return {model_id.capitalize()}\n")
        io_.write("    raise KeyError\n")

        io_.write("def submission_factory(form_type: str, fields: dict[str, Any]) -> type[BaseModel]:\n")
        io_.write("    return get_submission_method(form_type).parse_obj(fields)")

    with StringIO() as i:
        # Add imports and a custom validator for 'Currency'
        imports(i)
        validators(i)
        for form_name, part in forms:
            log(f'{form_name}: {part["title"]}')
            nodes: list[FormKitSchemaFormKit] = [process_node(n) for n in part["children"]]
            # Fetch the tables as Pydantic models
            # These are all the models for a given schema
            model_definitions, model_names = pydantic_base_models(form_name, (part["id"],), nodes)
            abstracts[form_name].extend(model_names)
            i.writelines(model_definitions)

        for model_id, abstract_model_names in abstracts.items():
            i.write(f'class {model_id.capitalize()}({", ".join(abstract_model_names)}):\n')
            i.write("    pass\n")
        factory(i)
        i.seek(0)
        file_content = black.format_str(i.read(), mode=black.Mode())

    return file_content


if __name__ == "__main__":
    # def get_forms(workdir=Path(settings.BASE_DIR) / "src"):
    #     """
    #     This yields a form "idenfitier" and a FormKitInput
    #     A Formkit Input is a wrapper around formkit to add titles + ids
    #     for sections in a form
    #     """
    #     with chdir(workdir):
    #         duup = subprocess.run(["corepack", "yarn@3.5.0", "tsx", "get_schemas.ts"], capture_output=True)
    #     forms: dict[str, list[FormKitInput]] = json.loads(duup.stdout)
    #     for form, form_parts in forms.items():
    #         for part in form_parts:
    #             yield (form, part)

    def get_forms_from_file(package="tests", resource="schemas.json"):
        forms: dict[str, list[FormKitInput]] = json.loads(resources.read_text(package=package, resource=resource))
        for form, form_parts in forms.items():
            for part in form_parts:
                yield (form, part)

    output_dir = Path("generated_schemas")

    forms = list(get_forms_from_file())

    with chdir(output_dir), open("schema.py", "w") as outfile:
        outfile.write(schema_dot_py(forms))

    with chdir(output_dir), open("models.py", "w") as outfile:
        outfile.write(models_dot_py(forms))

    with chdir(output_dir), open("models.sql", "w") as outfile:
        outfile.write(sqlparse.format("".join(list(process_forms_to_postgres(forms)))))
