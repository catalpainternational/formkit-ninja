from typing import Any, Callable, Iterable, NamedTuple

from formkit_schema import FormKitSchemaFormKit, FormKitSchemaDOMNode, RepeaterNode, GroupNode
from . import type_convert

from rich.console import Console
from .get_schemas import repeaters, groups, process_node


strings = tuple[str]

console = Console()
log = console.log


class TableRow(NamedTuple):
    node_name: str
    node_formkit: str
    field_type: str
    p_field_type: type_convert.postgres_type


table_row = tuple[str, str, str, type_convert.postgres_type]


def get_table(
    form_name: str, form_path: strings, nodes: Iterable[FormKitSchemaFormKit | FormKitSchemaDOMNode]
) -> Iterable[tuple[strings, list[TableRow]]]:
    rows: list[TableRow] = []

    for node in (n for n in nodes if not isinstance(n, (RepeaterNode, GroupNode, FormKitSchemaDOMNode))):
        field_type = type_convert.to_django(form_name, form_path, node, log)
        p_field_type = type_convert.to_postgres(form_name, form_path, node, log)
        rows.append(TableRow(node.name, node.formkit, str(field_type), p_field_type))

    # Repeaters and Groups
    for repeater in repeaters(nodes):
        yield from get_table(form_name, (*form_path, repeater.name), repeater.children)

    for group in groups(nodes):
        yield from get_table(form_name, (*form_path, group.name), group.children)

    # Yield the rows here after repeater + group
    yield (form_path, rows)


def tables(get_forms: Callable[[], Iterable[str, Any]]):
    for form_name, part in get_forms():
        nodes: list[FormKitSchemaFormKit] = [process_node(n) for n in part["children"]]
        yield from get_table(form_name, (part["title"],), nodes)
