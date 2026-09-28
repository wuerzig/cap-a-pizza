#!/usr/bin/env bash
# ============================================================================
#  Replica Set bootstrap script (run once by the `mongo-init` container)
# ============================================================================
#  1. Wait until mongo-primary is reachable.
#  2. If the replica set is NOT already initialized, run rs.initiate().
#  3. Wait until a PRIMARY has actually been elected, then exit 0.
#
#  Being idempotent matters: if you `docker compose up` a second time on an
#  existing volume, we must NOT try to re-initiate an already-formed set.
# ============================================================================
set -euo pipefail

echo "[mongo-init] Waiting for mongo-primary to accept connections..."
until mongosh --host mongo-primary:27017 --quiet --eval "db.adminCommand('ping')" >/dev/null 2>&1; do
  sleep 1
done
echo "[mongo-init] mongo-primary is up."

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
