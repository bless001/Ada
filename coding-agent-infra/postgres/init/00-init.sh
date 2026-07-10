#!/usr/bin/env sh
set -e

echo "Creating OpenProject database if needed..."
psql -v ON_ERROR_STOP=1 --username "$POSTGRES_USER" --dbname "$POSTGRES_DB" <<-EOSQL
SELECT 'CREATE DATABASE ${POSTGRES_OPENPROJECT_DB}'
WHERE NOT EXISTS (SELECT FROM pg_database WHERE datname = '${POSTGRES_OPENPROJECT_DB}')\gexec

GRANT ALL PRIVILEGES ON DATABASE ${POSTGRES_OPENPROJECT_DB} TO ${POSTGRES_USER};
EOSQL

echo "Creating coding-agent application schema..."
psql -v ON_ERROR_STOP=1 --username "$POSTGRES_USER" --dbname "$POSTGRES_DB" -f /docker-entrypoint-initdb.d/01-agent-schema.sql
