# Tests always use PostgreSQL due to pgtrigger dependency

# Pytest best practice: fixtures in conftest.py are automatically discovered
# For fixtures in tests/fixtures.py, import them explicitly in test files where needed
# This avoids using 'import *' which is discouraged
