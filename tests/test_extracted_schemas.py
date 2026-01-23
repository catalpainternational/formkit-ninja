import pytest

from formkit_ninja.formkit_schema import FormKitNode
from formkit_ninja.schemas import Schemas


def test_load_all_schemas():
    """
    Verify that all extracted schemas can be loaded and parsed as FormKitNodes
    """
    schemas = Schemas()
    schema_names = schemas.list_schemas()
    assert len(schema_names) > 0, "No schemas found"

    print(f"Testing {len(schema_names)} schemas")

    failures = []

    for name in schema_names:
        try:
            data = schemas.as_json(name)
            # Verify it parses to FormKitNode
            # Note: FormKitNode.parse_obj handles dict or list
            FormKitNode.parse_obj(data)
        except Exception as e:
            failures.append(f"{name}: {e}")

    if failures:
        pytest.fail(f"Failed to parse {len(failures)} schemas:\n" + "\n".join(failures))
