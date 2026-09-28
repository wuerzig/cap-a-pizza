# ============================================================================
#  OrderService  --  The core of the Distributed Pizzeria
# ============================================================================
#  Tech:  FastAPI + PyMongo (synchronous, on purpose -- it reads top-to-bottom)
#
#  This is the "brain" students interact with. In the starter code it does
#  everything the slow, coupled, synchronous way. Over the three lab sessions
#  you will gradually pull it apart into a proper event-driven system.
#
#  Look for the `TODO (Lab N)` comments -- those mark exactly where each
#  session's exercise happens.
# ============================================================================

import os
import uuid
import datetime

import requests
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from pymongo import MongoClient
from pymongo.write_concern import WriteConcern

# ---------------------------------------------------------------------------
# Configuration -- ALL of it comes from environment variables.
# ---------------------------------------------------------------------------
# This is deliberate and is the heart of the Session 1 CAP experiment:
# students flip MONGO_WRITE_CONCERN between "1" and "majority" in the .env
# file and observe how the system behaves under a network partition.
# NOTHING about consistency is hard-coded here.
# ---------------------------------------------------------------------------
MONGO_URI = os.getenv("MONGO_URI", "mongodb://mongo-primary:27017/?replicaSet=rs0")
MONGO_DB = os.getenv("MONGO_DB", "pizzeria")
RAW_WRITE_CONCERN = os.getenv("MONGO_WRITE_CONCERN", "1")

# Where the other two services live (synchronous calls, for now).
KITCHEN_URL = os.getenv("KITCHEN_URL", "http://kitchen-service:8001")
PAYMENT_URL = os.getenv("PAYMENT_URL", "http://payment-service:8002")


def parse_write_concern(raw):
    """Turn the .env value into a value PyMongo understands.

    Accepts friendly variants so students don't get tripped up by syntax:
        "1"          -> 1          (wait for the primary only)   [AP-leaning]
        "majority"   -> "majority" (wait for a majority of nodes) [CP-leaning]
        "w:1" / "w=1"/ "w:majority" are also tolerated.
    """
    value = raw.strip()
    # Strip an optional "w:" or "w=" prefix if a student copied it verbatim.
    for prefix in ("w:", "w="):
        if value.lower().startswith(prefix):
            value = value[len(prefix):]
    value = value.strip()
    return int(value) if value.isdigit() else value


WRITE_CONCERN_VALUE = parse_write_concern(RAW_WRITE_CONCERN)

# ---------------------------------------------------------------------------
# Database handle
# ---------------------------------------------------------------------------
# We attach the WriteConcern to the *collection* so that every insert/update
# on it respects the concern the student chose. `serverSelectionTimeoutMS`
# is kept modest so that when the primary loses its majority (CP mode), the
# load tester visibly *freezes then errors* instead of hanging forever.
client = MongoClient(MONGO_URI, serverSelectionTimeoutMS=5000)
db = client[MONGO_DB]
orders = db.get_collection(
    "orders",
    write_concern=WriteConcern(w=WRITE_CONCERN_VALUE),
)

# ---------------------------------------------------------------------------
# FastAPI app
# ---------------------------------------------------------------------------
app = FastAPI(title="Pizzeria OrderService")

# Wide-open CORS so students can just double-click dashboard.html (file://)
# and have it work. They should be learning about distributed systems, not
# fighting CORS preflight errors.
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)


class OrderRequest(BaseModel):
    """What a customer sends us to order a pizza."""
    customer: str = "anonymous"
    pizza: str = "margherita"


@app.get("/")
def root():
    """Tiny landing page so `curl localhost:8000` shows something useful."""
    return {
        "service": "OrderService",
        "write_concern": WRITE_CONCERN_VALUE,
        "mongo_uri": MONGO_URI,
    }


@app.get("/health")
def health():
    return {"status": "ok"}


@app.post("/orders")
def create_order(req: OrderRequest):
    """Create a new pizza order.

    Starter flow (fully synchronous and tightly coupled):
        1. Write the order to Mongo as PENDING.
        2. Call the KitchenService and wait 2s for the pizza to bake.
        3. Call the PaymentService and wait for it to (maybe) succeed.
        4. Update the final state.

    This is intentionally the "bad" design -- the whole point of Session 2 is
    to feel the pain of synchronous coupling before replacing it with events.
    """
    order = {
        "_id": str(uuid.uuid4()),
        "customer": req.customer,
        "pizza": req.pizza,
        "state": "PENDING",
        "created_at": datetime.datetime.utcnow().isoformat(),
    }

    # Step 1: persist the order. This insert is what the CAP experiment
    # observes -- under w:majority with a lost majority, THIS line blocks
    # and then raises a timeout.
    orders.insert_one(order)

    # ------------------------------------------------------------------
    # TODO (Lab 2): Remove this synchronous call and publish an
    # OrderPlacedEvent to RabbitMQ instead. The KitchenService and
    # PaymentService should react to that event on their own time, so
    # that a slow kitchen never blocks the customer's order.
    # ------------------------------------------------------------------
    try:
        # --- Synchronous call #1: bake the pizza (blocks for ~2 seconds) ---
        bake_resp = requests.post(f"{KITCHEN_URL}/bake", json=order, timeout=10)
        if bake_resp.status_code == 200:
            orders.update_one({"_id": order["_id"]}, {"$set": {"state": "BAKING"}})
            order["state"] = "BAKING"

        # --- Synchronous call #2: take payment (fails ~30% of the time) ---
        pay_resp = requests.post(f"{PAYMENT_URL}/pay", json=order, timeout=10)
        if pay_resp.status_code == 200:
            orders.update_one({"_id": order["_id"]}, {"$set": {"state": "PAID"}})
            order["state"] = "PAID"
        else:
            # Payment was declined. In a synchronous world we just mark it.
            # TODO (Lab 3): There is no local ROLLBACK across services once
            # this is event-driven -- this failure is what the Saga (a
            # compensating transaction) will have to clean up.
            orders.update_one({"_id": order["_id"]}, {"$set": {"state": "FAILED"}})
            order["state"] = "FAILED"

    except requests.RequestException as exc:
        # A downstream service was slow or unreachable. The order still
        # exists in Mongo as PENDING -- another symptom of tight coupling.
        order["error"] = str(exc)

    return order


@app.get("/orders")
def list_orders():
    """Return every order, plus handy per-state counts for the dashboard.

    TODO (Lab 2): Implement CQRS. This endpoint should read from a fast
    Redis cache (a "read model" updated by events) instead of querying the
    heavy write-side MongoDB replica set on every dashboard poll.
    """
    all_orders = list(orders.find({}, {"created_at": 0}))

    counts = {"PENDING": 0, "BAKING": 0, "PAID": 0, "FAILED": 0}
    for o in all_orders:
        counts[o.get("state", "PENDING")] = counts.get(o.get("state", "PENDING"), 0) + 1

    return {
        "total": len(all_orders),
        "counts": counts,
        "orders": all_orders,
    }
