# Tests always use PostgreSQL due to pgtrigger dependency

# Pytest best practice: fixtures in conftest.py are automatically discovered
# For fixtures in tests/fixtures.py, import them explicitly in test files where needed
# This avoids using 'import *' which is discouraged

import os

import pytest
from django.db.models.signals import post_save

# Import fixtures from tests.fixtures so they're available to all tests
pytest_plugins = ["tests.fixtures"]

# Ensure signal handlers are connected for all tests
from formkit_ninja.form_submission import import_monitoring  # noqa: F401, E402
from formkit_ninja.form_submission.models import SeparatedSubmission, Submission  # noqa: E402


def _split_on_post_save(sender, instance, **kwargs):
    SeparatedSubmission.objects.from_submission(instance)


@pytest.fixture(autouse=True)
def split_submissions_on_save(request):
    """
    Split every saved ``Submission`` into its ``SeparatedSubmission`` rows.

    ``Submission.save()`` deliberately does *not* do this (issue #57) — the
    consumer owns the split. Partisipa wires it from a ``post_save`` receiver,
    and this fixture mirrors that, so the suite exercises the same arrangement a
    real consumer produces rather than a behaviour the library no longer has.

    A test that needs the bare library behaviour — no split at all — opts out
    with ``@pytest.mark.no_split_on_save``.

    Gated on ``django_db`` so it stays off for the parser/Playwright tests that
    never touch the ORM: connecting a receiver there would be inert, but it
    would also be a claim about scope that isn't true.
    """
    if request.node.get_closest_marker("no_split_on_save") or "django_db" not in request.keywords:
        yield
        return
    post_save.connect(_split_on_post_save, sender=Submission, dispatch_uid="tests-split-on-save")
    try:
        yield
    finally:
        post_save.disconnect(sender=Submission, dispatch_uid="tests-split-on-save")


@pytest.fixture(scope="session")
def browser_context_args(browser_context_args):
    """
    Enable video recording when PLAYWRIGHT_VIDEO=1 is set.
    Videos are saved to test-videos/ directory.
    """
    if os.environ.get("PLAYWRIGHT_VIDEO"):
        return {
            **browser_context_args,
            "record_video_dir": "test-videos/",
        }
    return browser_context_args
