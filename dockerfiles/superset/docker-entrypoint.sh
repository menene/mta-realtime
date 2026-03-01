#!/bin/bash
set -e

echo ">>> Waiting for PostgreSQL to be ready..."
until python -c "
import psycopg2, sys
try:
    psycopg2.connect(host='${DATA_DB_HOST:-postgres}', port=${DATA_DB_PORT:-5432}, dbname='superset', user='${DATA_DB_USER:-admin}', password='${DATA_DB_PASS:-admin123}')
    sys.exit(0)
except Exception as e:
    print(e); sys.exit(1)
"; do
  echo "    Retrying in 3s..."
  sleep 3
done
echo ">>> PostgreSQL is ready."

echo ">>> Upgrading Superset metadata database..."
superset db upgrade

echo ">>> Creating admin user..."
superset fab create-admin \
  --username "${SUPERSET_ADMIN_USERNAME:-admin}" \
  --firstname "Admin" \
  --lastname "User" \
  --email "${SUPERSET_ADMIN_EMAIL:-admin@example.com}" \
  --password "${SUPERSET_ADMIN_PASSWORD:-admin123}" 2>/dev/null || true

echo ">>> Initializing roles and permissions..."
superset init

echo ">>> Registering PostgreSQL data source..."
superset set-database-uri \
  -d "DataPlatform PostgreSQL" \
  -u "postgresql+psycopg2://${DATA_DB_USER:-admin}:${DATA_DB_PASS:-admin123}@${DATA_DB_HOST:-postgres}:${DATA_DB_PORT:-5432}/${DATA_DB_NAME:-mta}" 2>/dev/null || true

echo ">>> Starting Superset..."
exec gunicorn \
  --bind "0.0.0.0:8088" \
  --workers 2 \
  --worker-class gthread \
  --threads 20 \
  --timeout 120 \
  "superset.app:create_app()"
