#!/usr/bin/env bash
set -euo pipefail

PYTHON="${PYTHON:-python3}"
PGBIN="$($PYTHON -c 'import pathlib, pgserver; print(pathlib.Path(pgserver.__file__).parent / "pginstall" / "bin")')"
WORKDIR="$(mktemp -d)"
PORT="${TEST_PG_PORT:-54329}"
PASSWORD="test-admin-password"

printf '%s' "$PASSWORD" > "$WORKDIR/pw"
"$PGBIN/initdb" -D "$WORKDIR/data" -U postgres --auth=scram-sha-256 --pwfile="$WORKDIR/pw" > /dev/null
"$PGBIN/pg_ctl" -D "$WORKDIR/data" -o "-p $PORT -c listen_addresses=127.0.0.1 -c unix_socket_directories=$WORKDIR" -l "$WORKDIR/log" -w start > /dev/null
trap '"$PGBIN/pg_ctl" -D "$WORKDIR/data" -m immediate stop > /dev/null; rm -rf "$WORKDIR"' EXIT

export TEST_PG_HOST=127.0.0.1 TEST_PG_PORT="$PORT" TEST_PG_USER=postgres TEST_PG_PASSWORD="$PASSWORD"
"$PYTHON" -m pytest tests/test_postgres_integration.py -q -p no:cacheprovider "$@"
