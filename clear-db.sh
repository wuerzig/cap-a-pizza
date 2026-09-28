#!/usr/bin/env bash
# ============================================================================
#  clear-db.sh  --  wipe all pizza orders from MongoDB
# ============================================================================
#  Handy for resetting between demo runs or between the AP / CP phases of the
#  CAP experiment, without tearing the whole stack down with `down -v`.
#
#  Usage (from anywhere; the stack must be running):
#      ./clear-db.sh
#
#  It talks to the running `mongo-primary` container, so no local mongosh or
#  Python is needed.
# ============================================================================
set -euo pipefail

# Run from the repo root so `docker compose` finds docker-compose.yml.
cd "$(dirname "$0")"

echo "Clearing all orders from the 'pizzeria' database..."

docker compose exec -T mongo-primary mongosh --quiet pizzeria --eval '
  const before = db.orders.countDocuments();
  const res = db.orders.deleteMany({});
  print(`Deleted ${res.deletedCount} order(s) (collection had ${before}).`);
'

echo "Done. Refresh dashboard.html — the counters should reset to 0."
