#!/bin/bash
set -e

export COUCHDB_USER="${COUCHDB_USER:-admin}"
export COUCHDB_PASSWORD="${COUCHDB_PASSWORD:-admin}"

export COUCHDB_URL="http://${COUCHDB_USER}:${COUCHDB_PASSWORD}@127.0.0.1:5984"

/usr/local/bin/docker-entrypoint.sh /opt/couchdb/bin/couchdb &

echo "Aguardando CouchDB iniciar..."

until curl -fsS -u "${COUCHDB_USER}:${COUCHDB_PASSWORD}" http://127.0.0.1:5984/ > /dev/null
do
    sleep 2
done

echo "CouchDB iniciado."

curl -fsS -u "${COUCHDB_USER}:${COUCHDB_PASSWORD}" -X PUT http://127.0.0.1:5984/_users || true
curl -fsS -u "${COUCHDB_USER}:${COUCHDB_PASSWORD}" -X PUT http://127.0.0.1:5984/_replicator || true
curl -fsS -u "${COUCHDB_USER}:${COUCHDB_PASSWORD}" -X PUT http://127.0.0.1:5984/_global_changes || true

flask --app app init-db

echo "Banco inicializado."

exec gunicorn app:app \
    --bind 0.0.0.0:${PORT:-10000} \
    --workers 1 \
    --threads 2