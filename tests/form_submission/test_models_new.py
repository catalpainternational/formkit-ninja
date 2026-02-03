import pytest

from formkit_ninja.form_submission.models import SeparatedSubmissionImport, SubmissionFile


@pytest.mark.django_db
def test_submission_file_fields():
    fields = {f.name for f in SubmissionFile._meta.fields}
    assert {"submission", "file", "user", "comment", "deleted"}.issubset(fields)


@pytest.mark.django_db
def test_separated_submission_import_fields():
    fields = {f.name for f in SeparatedSubmissionImport._meta.fields}
    assert {"submission", "created", "success", "message"}.issubset(fields)
