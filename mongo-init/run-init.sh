#!/usr/bin/env bash
# ============================================================================
#  Replica Set bootstrap script (run once by the `mongo-init` container)
# ============================================================================
#  1. Wait until ALL THREE nodes are reachable.
#  2. If the replica set is NOT already initialized, run rs.initiate().
#  3. Wait until a PRIMARY has actually been elected, then exit 0.
#
#  We wait for all three here (not just the primary) because the node
#  containers have no healthcheck of their own -- the no-AVX image has no
#  mongosh to run one. This script IS the readiness gate for the whole set.
#
#  Being idempotent matters: if you `docker compose up` a second time on an
#  existing volume, we must NOT try to re-initiate an already-formed set.
# ============================================================================
set -euo pipefail

for HOST in mongo-primary mongo-sec-1 mongo-sec-2; do
  echo "[mongo-init] Waiting for ${HOST} to accept connections..."
  until mongosh --host "${HOST}:27017" --quiet --eval "db.adminCommand('ping')" >/dev/null 2>&1; do
    sleep 1
  done
  echo "[mongo-init] ${HOST} is up."
done

# Has the replica set already been configured on a previous run?
ALREADY_INIT=$(mongosh --host mongo-primary:27017 --quiet --eval \
  "try { rs.status().ok } catch (e) { 0 }")

if [ "$ALREADY_INIT" = "1" ]; then
  echo "[mongo-init] Replica set already initialized -- nothing to do."
  exit 0
fi

echo "[mongo-init] Initiating replica set rs0..."
mongosh --host mongo-primary:27017 --quiet /scripts/init-replica.js

echo "[mongo-init] Waiting for a PRIMARY to be elected..."
until [ "$(mongosh --host mongo-primary:27017 --quiet --eval \
  "try { db.hello().isWritablePrimary } catch (e) { false }")" = "true" ]; do
  sleep 1
done

echo "[mongo-init] Replica set rs0 is ready. PRIMARY elected. Done."
