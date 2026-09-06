#!/bin/sh
set -eu
exec flyway -url="jdbc:postgresql://${PGHOST}:${PGPORT}/${PGDATABASE}" -user="${PGUSER}" -password="${PGPASSWORD}" -locations=filesystem:/flyway/sql -connectRetries=20 migrate
