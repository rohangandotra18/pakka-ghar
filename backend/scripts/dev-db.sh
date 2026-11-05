#!/bin/bash
# Start (or create, then start) the local Postgres 16 used in development and tests.
#   scripts/dev-db.sh          start it
#   scripts/dev-db.sh stop     stop it
set -euo pipefail
cd "$(dirname "$0")/.."
BIN=$(.venv/bin/python -c "import pgserver, os; print(os.path.dirname(pgserver.__file__))")/pginstall/bin
if [ "${1:-}" = "stop" ]; then "$BIN/pg_ctl" -D .pgdata stop; exit; fi
if [ ! -d .pgdata ]; then
  "$BIN/initdb" -D .pgdata -U postgres --auth=trust -E UTF8 --locale=C >/dev/null
  printf "listen_addresses='localhost'\nport=5432\nunix_socket_directories='%s'\ntimezone='Asia/Kolkata'\n" "$PWD/.pgdata" >> .pgdata/postgresql.conf
  "$BIN/pg_ctl" -D .pgdata -l .pgdata/server.log start -w
  "$BIN/psql" -h localhost -U postgres -d postgres -v ON_ERROR_STOP=1 -f scripts/bootstrap_db.sql
else
  "$BIN/pg_isready" -h localhost -q || "$BIN/pg_ctl" -D .pgdata -l .pgdata/server.log start -w
fi
