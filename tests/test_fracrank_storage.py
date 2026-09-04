"""The C-collation guard for ``SeparatedSubmission.repeater_rank`` (#74).

Fractional index keys are compared as **bytes**. Postgres' default en_US.UTF-8
collation is not byte order — it is roughly case-insensitive and ignores some
characters — so a rank column declared without ``COLLATE "C"`` orders rows
differently in SQL than the algorithm that minted the keys does in Python.

Nothing about that failure is loud. The rows come back in a plausible-looking
order that is simply not the one the user chose, and only for keys that happen
to differ in case. These two tests are the only thing standing between us and a
later migration quietly dropping the collation.
"""

import uuid

import pytest
from django.db import connection

from formkit_ninja.form_submission.models import SeparatedSubmission, Submission


@pytest.mark.django_db
def test_rank_column_is_declared_c_collation():
    """Asked of the database, not of the model: a model that says ``db_collation``
    and a column that was never altered to match is exactly the state this guards."""
    with connection.cursor() as cursor:
        cursor.execute(
            """
            SELECT collation_name
            FROM information_schema.columns
            WHERE table_name = %s AND column_name = %s
            """,
            [SeparatedSubmission._meta.db_table, "repeater_rank"],
        )
        row = cursor.fetchone()

    assert row is not None, "repeater_rank column is missing"
    assert row[0] == "C", f'repeater_rank must be COLLATE "C", got {row[0]!r}'


@pytest.mark.django_db
def test_sql_order_matches_python_order_for_case_differing_keys():
    """The divergence made concrete.

    ``"a0V"`` and ``"a0v"`` differ only in case. Under COLLATE "C" they sort by
    byte, so uppercase precedes lowercase and SQL agrees with Python. Under a
    linguistic collation the comparison is case-insensitive at the primary level
    and the two come back the other way round.

    Shown to fail without the collation. Re-declaring the column as
    ``COLLATE "en-US-x-icu"`` and re-running this test::

        SQL ORDER UNDER en-US-x-icu: ['a0g', 'a0G', 'a0v', 'a0V']
        PYTHON BYTE ORDER          : ['a0G', 'a0V', 'a0g', 'a0v']

    Every pair is transposed, and nothing raises.
    """
    sub = Submission.objects.create(form_type="TestForm", fields={})
    root = SeparatedSubmission.objects.get(pk=sub.pk)

    # Deliberately inserted in an order that is neither the byte order nor the
    # reverse of it, so a database that ignores the ORDER BY cannot pass by luck.
    keys = ["a0v", "a0V", "a0G", "a0g"]
    for key in keys:
        SeparatedSubmission.objects.create(
            id=uuid.uuid4(),
            submission=sub,
            fields={},
            form_type="TestFormRepeater",
            repeater_parent=root,
            repeater_key="repeater",
            repeater_rank=key,
        )

    from_sql = list(SeparatedSubmission.objects.filter(repeater_parent=root).order_by("repeater_rank").values_list("repeater_rank", flat=True))

    assert from_sql == sorted(keys)
    # Spelled out, because `sorted` on a list of str is itself byte order and the
    # assertion above would hold vacuously if both sides were wrong the same way.
    assert from_sql == ["a0G", "a0V", "a0g", "a0v"]
