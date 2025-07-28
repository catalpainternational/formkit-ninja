import marimo

__generated_with = "0.14.13"
app = marimo.App()

with app.setup:
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
    mo.md(r"""# Importing from HTML""")
    return


@app.cell
def _():
    html_form = """
    <FormKit type="form" @submit="submit">
      <h2>Change password</h2>
      <FormKit
        type="password"
        name="password"
        label="Password"
        validation="required|?length:10"
        :validation-messages="{
          length: 'Try to make your password longer!',
        }"
      />
      <FormKit
        type="password"
        label="Confirm password"
        name="password_confirm"
        validation="required|confirm"
      />
    </FormKit>
    """
    return (html_form,)


@app.cell
def _(FormKitTagParser, html_form):
    form_as_pydantic = FormKitTagParser(html_form).tags[0]
    form_as_pydantic.model_dump(by_alias=True, exclude_none=True)
    return (form_as_pydantic,)


@app.cell
def _(form_as_pydantic):
    import json5
    print(json5.dumps(
        form_as_pydantic.model_dump(by_alias=True, exclude_none=True),
        indent=2
    ))
    return


@app.cell
def _(schema_thing):
    from formkit_ninja.formkit_schema import RadioNode
    rn = RadioNode(**schema_thing)
    return (rn,)


@app.cell
def _(rn):
    rn.model_dump(by_alias=True, exclude_none=True)
    return


@app.cell
def _():
    import marimo as mo
    return (mo,)


if __name__ == "__main__":
    app.run()
