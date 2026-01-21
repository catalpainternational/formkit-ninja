# Tests always use PostgreSQL due to pgtrigger dependency

# Pytest best practice: fixtures in conftest.py are automatically discovered
# For fixtures in tests/fixtures.py, import them explicitly in test files where needed
# This avoids using 'import *' which is discouraged

import os

import pytest


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
