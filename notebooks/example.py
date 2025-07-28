import marimo

__generated_with = "0.14.13"
app = marimo.App()

with app.setup:
    # Initialization code 
    import os
    import django
    from pathlib import Path
    import sys

    sys.path.insert(0, str(Path(__file__).parent.parent))
    os.environ["DJANGO_ALLOW_ASYNC_UNSAFE"] = "true"
    os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'testproject.settings')
    django.setup()


@app.cell(hide_code=True)
def _(mo):
    mo.md(r""" """)
    return


@app.cell(hide_code=True)
def _(mo):
    mo.md(
        r"""
    # Formkit-Ninja

    What is Formkit-Ninja?
    It's a Django application to store and convert FormKit schemas between JSON, Pydantic models, and database backend. It supports most of the FormKit syntax as well as some of the "extra" goodies.
    """
    )
    return


@app.cell
def _():
    # Here we're defining some functions to help us display data in a nice way 

    from typing import Any
    from rich.table import Table
    from rich.jupyter import print
    from pydantic import BaseModel

    def kvtable(inputelement: dict[str, Any], title: str | None = None):
        table = Table(title=title)
        table.add_column("Key", style="cyan", no_wrap=True)
        table.add_column("Value", style="magenta")
        for key, value in sorted(inputelement.items()):
            table.add_row(str(key), str(value))
        print(table)

    def modeltable(inputmodel: BaseModel):
        kvtable(inputmodel.model_dump(exclude_none=True, by_alias=True), title=inputmodel.__class__.__name__)

    def manytable(inputelements: list[dict[str, Any]], title: str | None = None):
        table = Table(title=title)
        table.add_column("Index", style="cyan", no_wrap=True)
        # Set of all keys
        keys = set()
        for element in inputelements:
            keys.update(element.keys())
        # These are the "rows"
        rows = sorted(keys)
        # These are the "columns"
        range(len(inputelements))
        # Add the columns
        for index, i in enumerate(inputelements):
            table.add_column(str(index), style="magenta")
        # Add the rows
        for row in rows:
            content = []
            for index, i in enumerate(inputelements):
                content.append(str(i.get(row, "")))
            table.add_row(row, *content)
        print(table)

    def manynodetable(inputelements: list[BaseModel], title: str | None = None):
        manytable([i.model_dump(exclude_none=True, by_alias=True) for i in inputelements], title=title)
    return kvtable, manynodetable, manytable, modeltable, print


@app.cell
def _(kvtable):
    # Add a "Telephone" input

    # This is a simple input with validation and a label
    # Note that the label is translated using the gettext function (client side)
    tel = {
        "$formkit": "tel",
        "label": '$gettext("Phone number")',
        "maxLength": 8,
        "name": "phone_number",
        "validation": "number|length:8,8",
    }
    kvtable(tel)
    return (tel,)


@app.cell
def _(modeltable, tel):
    # This is in Python / Pydantic a "TelNode"
    # We can create this node from the dictionary above

    from formkit_ninja.formkit_schema import TelNode

    node = TelNode(**tel)

    modeltable(node)
    return


@app.cell
def _(modeltable, tel):
    from formkit_ninja.formkit_schema import DiscriminatedNodeType
    node_1 = DiscriminatedNodeType(**tel)
    modeltable(node_1)
    return DiscriminatedNodeType, node_1


@app.cell
def _(node_1):
    node_1
    return


@app.cell
def _(node_1):
    from formkit_ninja.models import FormKitSchemaNode
    nodes = list(FormKitSchemaNode.from_pydantic(node_1))
    return FormKitSchemaNode, nodes


@app.cell
def _(nodes):
    nodes
    return


@app.cell
def _(kvtable, modeltable, nodes):
    for _n in nodes:
        kvtable(_n.get_node_values())
        modeltable(_n.get_node())
    return


@app.cell(hide_code=True)
def _(mo):
    mo.md(
        r"""
    ## A More Complex Example

    The following example is a "datepicker"
    """
    )
    return


@app.cell
def _():
    sf_41_datpicker = {
        "$formkit": "datepicker",
        "_currentDate": "$getCurrentDate",
        "calendarIcon": "calendar",
        "format": "DD/MM/YYYY",
        "id": "date",
        "key": "date",
        "label": '$gettext("Date")',
        "name": "date",
        "nextIcon": "angleRight",
        "prevIcon": "angleLeft",
        "sectionsSchema": {
            "day": {
                "children": [
                    "$day.getDate()",
                    {
                        "children": [
                            {
                                "children": [
                                    {
                                        "$el": "div",
                                        "attrs": {"class": "formkit-day-highlight"},
                                        "if": "$attrs._currentDate().year === $day.getFullYear()",
                                    }
                                ],
                                "if": "$attrs._currentDate().month === $day.getMonth()",
                            }
                        ],
                        "if": "$attrs._currentDate().day === $day.getDate()",
                    },
                ]
            }
        },
    }
    return (sf_41_datpicker,)


@app.cell
def _(DiscriminatedNodeType, sf_41_datpicker):
    # When we run this we should get a valid node
    sf_41_node = DiscriminatedNodeType(**sf_41_datpicker)
    return (sf_41_node,)


@app.cell
def _(kvtable, modeltable, sf_41_datpicker, sf_41_node):
    kvtable(sf_41_datpicker)
    modeltable(sf_41_node)
    return


@app.cell
def _(FormKitSchemaNode, sf_41_node):
    nodes_1 = list(FormKitSchemaNode.from_pydantic(sf_41_node))
    return (nodes_1,)


@app.cell
def _(kvtable, modeltable, nodes_1):
    for _n in nodes_1:
        kvtable(_n.get_node_values())
        modeltable(_n.get_node())
    return


@app.cell
def _():
    # Schemas
    # Usually one input is not enough, we need a schema to hold multiple inputs
    # This is a JSON object not real javascript
    schema = '''
    [
      {
        $el: 'h1',
        children: 'Register',
        attrs: {
          class: 'text-2xl font-bold mb-4',
        },
      },
      {
        $formkit: 'text',
        name: 'email',
        label: 'Email',
        help: 'This will be used for your account.',
        validation: 'required|email',
      },
      {
        $formkit: 'password',
        name: 'password',
        label: 'Password',
        help: 'Enter your new password.',
        validation: 'required|length:5,16',
      },
      {
        $formkit: 'password',
        name: 'password_confirm',
        label: 'Confirm password',
        help: 'Enter your new password again to confirm it.',
        validation: 'required|confirm',
        validationLabel: 'password confirmation',
      },
      {
        $cmp: 'FormKit',
        props: {
          name: 'eu_citizen',
          type: 'checkbox',
          id: 'eu',
          label: 'Are you a european citizen?',
        },
      },
      {
        $formkit: 'select',
        if: '$get(eu).value', // 👀 Oooo, conditionals!
        name: 'cookie_notice',
        label: 'Cookie notice frequency',
        options: {
          refresh: 'Every page load',
          hourly: 'Ever hour',
          daily: 'Every day',
        },
        help: 'How often should we display a cookie notice?',
      },
    ]
    '''

    import json5
    schema_as_js = json5.loads(schema)
    return schema, schema_as_js


@app.cell
def _(kvtable, schema_as_js):
    for _n in schema_as_js:
        kvtable(_n)
    return


@app.cell
def _(print, schema_as_js):
    from formkit_ninja.formkit_schema import DiscriminatedNodeTypeSchema
    from formkit_ninja.models import FormKitSchema
    schema_as_pydantic = DiscriminatedNodeTypeSchema(schema_as_js)
    nodes_2 = FormKitSchema.from_pydantic(schema_as_pydantic)
    print(nodes_2)
    return (nodes_2,)


@app.cell
def _(nodes_2):
    nodes_2.publish()
    return


@app.cell
def _(nodes_2):
    nodes_2
    return


@app.cell
def _(manynodetable, manytable, nodes_2, schema_as_js):
    manytable(schema_as_js)
    manytable([_n.get_node_values() for _n in nodes_2])
    manynodetable([_n.get_node() for _n in nodes_2])
    return


@app.cell
def _(schema_as_js):
    # nodes[3].get_node_values()
    schema_as_js[3]

    from formkit_ninja.formkit_schema import PasswordNode
    PasswordNode(**schema_as_js[3])

    schema_as_js[3]["validation-label"] = schema_as_js[3].pop("validationLabel")
    PasswordNode(**schema_as_js[3])
    return


@app.cell
def _(sf_41_node):
    sf_41_node
    return


@app.cell
def _(schema):
    schema
    return


@app.cell
def _():
    import marimo as mo
    return (mo,)


if __name__ == "__main__":
    app.run()
