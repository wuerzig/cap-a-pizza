# ============================================================================
#  OrderService  --  The core of the Distributed Pizzeria
# ============================================================================
#  Tech:  FastAPI + PyMongo (synchronous, on purpose -- it reads top-to-bottom)
#
#  Everything is slow, coupled, synchronous way. Over the three lab sessions
#  you will gradually pull it apart into a proper event-driven system.
#
#  Look for the `TODO` comments -- those mark exactly where each
#  session's exercise happens.
# ============================================================================

import os
import uuid
import datetime

import requests
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from pymongo import MongoClient
from pymongo.errors import PyMongoError, WriteConcernError
from pymongo.write_concern import WriteConcern

# ---------------------------------------------------------------------------
# Configuration -- ALL of it comes from environment variables.
# ---------------------------------------------------------------------------
# This is deliberate and is the heart of the Session 1 CAP experiment:
# students flip MONGO_WRITE_CONCERN between "1" (wait for the primary only)
# and "3" (wait for ALL three nodes), pause ONE secondary, and observe how the
# system behaves. NOTHING about consistency is hard-coded here.
# ---------------------------------------------------------------------------
MONGO_URI = os.getenv("MONGO_URI", "mongodb://mongo-primary:27017/?replicaSet=rs0")
MONGO_DB = os.getenv("MONGO_DB", "pizzeria")
RAW_WRITE_CONCERN = os.getenv("MONGO_WRITE_CONCERN", "1")

# Where the other two services live (synchronous calls, for now).
KITCHEN_URL = os.getenv("KITCHEN_URL", "http://kitchen-service:8001")
PAYMENT_URL = os.getenv("PAYMENT_URL", "http://payment-service:8002")


def parse_write_concern(raw):
    """Turn the .env value into a value PyMongo understands.

    Accepts friendly variants:
        "1"          -> 1          (wait for the primary only)   [AP-leaning]
        "3"          -> 3          (wait for ALL three nodes)     [CP-leaning]
        "majority"   -> "majority" (wait for a majority of nodes)
        "w:1" / "w=1"/ "w:3" are also tolerated.
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
# on it respects the concern the student chose.
#   - serverSelectionTimeoutMS: if there's no reachable primary (e.g. two nodes
#     paused), fail after 5s instead of hanging forever.
#   - WTIMEOUT_MS: in CP mode (w=3) with one node paused, the requested
#     acknowledgment can never arrive. Rather than block a server thread
#     forever, give up waiting after WTIMEOUT_MS. The DATA is still committed to
#     the primary -- we just learn that the durability we asked for wasn't met,
#     and flag the order accordingly (see create_order). (Ignored when w=1.)
WTIMEOUT_MS = 1500
client = MongoClient(MONGO_URI, serverSelectionTimeoutMS=5000)
db = client[MONGO_DB]
orders = db.get_collection(
    "orders",
    write_concern=WriteConcern(w=WRITE_CONCERN_VALUE, wtimeout=WTIMEOUT_MS),
)

# A second handle on the SAME collection, but always w=1. We use it for the
# internal state transitions (PENDING -> BAKING -> PAID/FAILED), which are just
# bookkeeping. Only the customer-facing "accept the order" insert uses the
# student-configured write concern -- that is the one CAP decision we want to
# study. Using w=1 here keeps status flips fast and stops every single update
# from also stalling for WTIMEOUT_MS when a replica is paused.
orders_local = orders.with_options(write_concern=WriteConcern(w=1))

# ---------------------------------------------------------------------------
# FastAPI app
# ---------------------------------------------------------------------------
app = FastAPI(title="Pizzeria OrderService")

# Wide-open CORS so we can just double-click dashboard.html (file://)
# and have it work. NEVER user this in a production system.
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

    This is intentionally the "bad" design -- the whole point of the Lab is
    to feel the pain of synchronous coupling before replacing it with events.
    """
    order = {
        "_id": str(uuid.uuid4()),
        "customer": req.customer,
        "pizza": req.pizza,
        "state": "PENDING",
        "created_at": datetime.datetime.utcnow().isoformat(),
        # The durability we ASKED for (the student's MONGO_WRITE_CONCERN)...
        "write_concern": str(WRITE_CONCERN_VALUE),
        # ...and whether we actually GOT it. Updated below if the write concern
        # times out. Surfaced on the dashboard so the CAP trade-off is visible.
        "replicated": True,
    }

    # Step 1: accept + persist the order using the student-configured write
    # concern. THIS is the CAP decision point. With ONE secondary paused the
    # primary stays up, so the write concern alone decides what happens:
    #   - w=1: the primary acknowledges by itself -> fully replicated, all good.
    #   - w=3: the write waits for the paused node too. The data still commits
    #          on the primary, but the requested ack never arrives, so after
    #          WTIMEOUT_MS pymongo raises WriteConcernError. We do NOT abort --
    #          the order is usable -- we just mark it replicated=False so the
    #          consistency cost is visible. (Availability kept; durability
    #          guarantee degraded = the trade-off, made concrete.)
    try:
        orders.insert_one(order)
    except WriteConcernError:
        # Committed locally, but not acknowledged to the requested level.
        order["replicated"] = False
        orders_local.update_one({"_id": order["_id"]}, {"$set": {"replicated": False}})
    except PyMongoError as exc:
        # No reachable primary at all (e.g. TWO nodes paused -> the primary lost
        # its majority and stepped down). Nothing was written; the system is
        # genuinely unavailable. This is MongoDB being fundamentally CP.
        raise HTTPException(
            status_code=503,
            detail=(
                "Order rejected -- no reachable primary. With a majority of "
                "nodes down MongoDB refuses all writes (it is a CP system). "
                f"({type(exc).__name__})"
            ),
        )

    # ------------------------------------------------------------------
    # TODO (Lab): Remove this synchronous call and publish an
    # OrderPlacedEvent to RabbitMQ instead. The KitchenService and
    # PaymentService should react to that event on their own time, so
    # that a slow kitchen never blocks the customer's order.
    # ------------------------------------------------------------------
    try:
        # --- Synchronous call #1: bake the pizza (blocks for ~10 seconds) ---
        # Mark it BAKING *before* the call so the order actually spends the
        # ~10s bake time in the BAKING state (and shows up on the dashboard).
        # (These status flips use orders_local = w=1: they're bookkeeping, not
        # the CAP decision, so they stay fast even while a replica is paused.)
        orders_local.update_one({"_id": order["_id"]}, {"$set": {"state": "BAKING"}})
        order["state"] = "BAKING"
        requests.post(f"{KITCHEN_URL}/bake", json=order, timeout=10)

        # --- Synchronous call #2: take payment (fails ~30% of the time) ---
        pay_resp = requests.post(f"{PAYMENT_URL}/pay", json=order, timeout=10)
        if pay_resp.status_code == 200:
            orders_local.update_one({"_id": order["_id"]}, {"$set": {"state": "PAID"}})
            order["state"] = "PAID"
        else:
            # Payment was declined. In a synchronous world we just mark it.
            # TODO (Lab 3): There is no local ROLLBACK across services once
            # this is event-driven -- this failure is what the Saga (a
            # compensating transaction) will have to clean up.
            orders_local.update_one({"_id": order["_id"]}, {"$set": {"state": "FAILED"}})
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
    # Sorted newest-first so the dashboard's "last 20" list is meaningful.
    # Reads default to the primary, so in CP mode after a stepdown this also
    # fails -- return a clean 503 so the dashboard shows its red "unavailable"
    # banner instead of a 500. (The secondaries are paused too, so there is
    # genuinely nothing left to read from: total unavailability = the CP tax.)
    try:
        all_orders = list(orders.find({}).sort("created_at", -1))
    except PyMongoError as exc:
        raise HTTPException(
            status_code=503,
            detail=f"Dashboard unavailable -- database has no reachable primary. ({type(exc).__name__})",
        )

    counts = {"PENDING": 0, "BAKING": 0, "PAID": 0, "FAILED": 0}
    unreplicated = 0
    for o in all_orders:
        counts[o.get("state", "PENDING")] = counts.get(o.get("state", "PENDING"), 0) + 1
        # replicated defaults to True for orders written before this field existed.
        if not o.get("replicated", True):
            unreplicated += 1

    return {
        "total": len(all_orders),
        "counts": counts,
        # How many accepted orders did NOT meet the requested write concern
        # (i.e. were not fully replicated). 0 in w=1 mode; climbs in w=3 mode
        # while a replica is paused -- the visible cost of the CAP trade-off.
        "unreplicated": unreplicated,
        "orders": all_orders,
    }
