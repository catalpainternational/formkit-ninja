# Recipes for working on formkit-ninja. `just` with no arguments lists them.

default:
    @just --list

# Extra arguments go to pytest: `just test-full -x -k events`.
# The whole suite against a throwaway Postgres 16, one run at a time on this machine.
test-full *args:
    #!/usr/bin/env bash
    set -euo pipefail
    # One full run at a time across every checkout on the machine. Where the lock's directory
    # does not exist (CI, a laptop) there is nothing to queue behind, so the suite just runs.
    lock="${FULL_TEST_RUN_LOCK:-$HOME/sessions/full-test-run.lock}"
    if [ -z "${TEST_FULL_HAS_LOCK:-}" ] && [ -d "$(dirname "$lock")" ]; then
        echo "waiting for $lock" >&2
        TEST_FULL_HAS_LOCK=1 exec flock "$lock" just test-full {{ args }}
    fi
    name="formkit-ninja-test-$$"
    trap 'podman rm -f "$name" >/dev/null 2>&1 || true' EXIT
    # Podman picks a free port, so two checkouts never collide on one.
    podman run -d --rm --name "$name" -e POSTGRES_PASSWORD=postgres -p 127.0.0.1::5432 docker.io/library/postgres:16 >/dev/null
    until podman exec "$name" pg_isready -U postgres -q; do sleep 1; done
    port="$(podman port "$name" 5432/tcp | head -1 | sed 's/.*://')"
    POSTGRES_HOST=localhost POSTGRES_PORT="$port" POSTGRES_DB=postgres POSTGRES_USER=postgres POSTGRES_PASSWORD=postgres \
        uv run pytest --create-db -p no:cacheprovider {{ args }}
