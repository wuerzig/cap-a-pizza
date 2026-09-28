#!/usr/bin/env python3
# ============================================================================
#  load_tester.py  --  the "customers keep ordering" firehose
# ============================================================================
#  Fires POST /orders at a steady 5 requests/second, FOREVER, and prints a
#  live once-per-second status line. This is what students watch during the
#  Session 1 CAP experiment.
#
#  Usage:
#      python load_tester.py                 # targets http://localhost:8000
#      ORDER_URL=http://localhost:8000 python load_tester.py
#
#  Requires:  pip install requests
#
#  WHY IS THIS CONCURRENT?
#  -----------------------
#  The starter OrderService is fully synchronous: a single POST /orders blocks
#  for ~10s while the kitchen bakes. A naive serial loop (fire, wait, fire)
#  therefore can NOT sustain 5 req/s -- it manages ~1 request per response --
#  and every request looks "dropped" because the client gives up before the
#  slow bake finishes, even though the order actually succeeds server-side.
#
#  So we submit each request to a thread pool and TRACK it:
#    - in-flight = requests submitted but not yet returned ("unconfirmed").
#    - latency   = how long a completed order actually took.
#  Under the synchronous starter you'll see in-flight climb to ~50-60 and
#  latency sit around ~10s -- a vivid picture of synchronous-coupling backlog.
#  After you move to Event-Driven Architecture (Session 2), in-flight should
#  collapse toward ~0 and latency should drop sharply. That contrast is the
#  whole point.
#
#  WHAT TO WATCH DURING THE CAP EXPERIMENT  (pause exactly ONE secondary)
#  ---------------------------------------------------------------------
#    - w=1 + one paused secondary -> orders succeed, fully replicated.
#    - w=3 + one paused secondary -> orders STILL succeed (available!) but the
#      "unreplicated" tally climbs -- the write concern couldn't be met.
#    - pause TWO nodes (any setting) -> the "unavailable" tally climbs (HTTP
#      503): the primary steps down and MongoDB refuses all writes.
# ============================================================================

import os
import time
import threading
import datetime
from concurrent.futures import ThreadPoolExecutor

import requests

ORDER_URL = os.getenv("ORDER_URL", "http://localhost:8000")
REQUESTS_PER_SECOND = 0.5
DELAY = 1.0 / REQUESTS_PER_SECOND  # 0.2s between submissions

# Generous timeout: a *successful* order legitimately takes >10s in the
# synchronous starter (the kitchen bakes for ~10s). We must wait well past the
# bake time, otherwise we'd mislabel slow-but-fine orders as failures -- which
# is exactly the confusion this rewrite removes.
TIMEOUT = 30

# Cap concurrency so a wedged server can't make us spawn threads without bound.
# ~60 are needed in steady state (10s latency x 5/s); 128 leaves headroom.
MAX_WORKERS = 128

# A little variety so the orders look believable in the dashboard.
CUSTOMERS = ["alice", "bob", "carol", "dave", "erin"]
PIZZAS = ["margherita", "pepperoni", "hawaiian", "veggie", "quattro-formaggi",
          "speziale", "mushroom"]

# ---------------------------------------------------------------------------
# Shared stats, guarded by a single lock. A plain dict keeps it readable.
# ---------------------------------------------------------------------------
_lock = threading.Lock()
S = {
    "sent": 0,          # total requests submitted
    "inflight": 0,      # submitted but not yet returned  (== "unconfirmed")
    "done": 0,          # returned 200 OK
    "unreplicated": 0,  # 200 OK but write concern not met (w=3, replica paused)
    "unavailable": 0,   # returned 503 (no primary -> CP hard wall)
    "errors": 0,        # timeouts / connection errors
    "lat_sum": 0.0,     # sum of completed-order latencies (for the average)
    "max_inflight": 0,  # high-water mark, printed in the final summary
    "last_latency": 0.0,
}


def send_one(n):
    """Fire a single POST /orders and record the outcome in S."""
    payload = {"customer": CUSTOMERS[n % len(CUSTOMERS)],
               "pizza": PIZZAS[n % len(PIZZAS)]}
    t0 = time.monotonic()
    try:
        resp = requests.post(f"{ORDER_URL}/orders", json=payload, timeout=TIMEOUT)
        dt = time.monotonic() - t0
        with _lock:
            S["inflight"] -= 1
            S["last_latency"] = dt
            if resp.status_code == 200:
                S["done"] += 1
                S["lat_sum"] += dt
                if not resp.json().get("replicated", True):
                    S["unreplicated"] += 1
            elif resp.status_code == 503:
                S["unavailable"] += 1
            else:
                S["errors"] += 1
    except requests.RequestException:
        with _lock:
            S["inflight"] -= 1
            S["errors"] += 1


def reporter(stop_event):
    """Print one status line per second until told to stop."""
    prev_sent = 0
    while not stop_event.wait(1.0):
        with _lock:
            s = dict(S)  # snapshot under the lock, then release
        rate = s["sent"] - prev_sent
        prev_sent = s["sent"]
        avg = (s["lat_sum"] / s["done"]) if s["done"] else 0.0
        stamp = datetime.datetime.now().strftime("%H:%M:%S")
        print(
            f"[{stamp}] rate={rate}/s  in-flight={s['inflight']:<3}  "
            f"done={s['done']:<5}  unreplicated={s['unreplicated']:<4}  "
            f"unavailable={s['unavailable']:<4}  errors={s['errors']:<4}  "
            f"| latency avg={avg:5.1f}s last={s['last_latency']:5.1f}s"
        )


def main():
    print(f"Firing {REQUESTS_PER_SECOND} orders/sec at {ORDER_URL}/orders")
    print("Columns: in-flight = submitted but not yet answered (unconfirmed).")
    print("Press Ctrl+C to stop.\n")

    stop_event = threading.Event()
    reporter_thread = threading.Thread(target=reporter, args=(stop_event,), daemon=True)
    reporter_thread.start()

    pool = ThreadPoolExecutor(max_workers=MAX_WORKERS)
    n = 0
    try:
        while True:
            tick = time.monotonic()
            n += 1
            with _lock:
                S["sent"] += 1
                S["inflight"] += 1
                S["max_inflight"] = max(S["max_inflight"], S["inflight"])
            pool.submit(send_one, n)

            # Pace submissions to the target rate (independent of response time,
            # because responses happen on the pool's threads, not here).
            elapsed = time.monotonic() - tick
            if elapsed < DELAY:
                time.sleep(DELAY - elapsed)
    except KeyboardInterrupt:
        pass
    finally:
        stop_event.set()
        # Don't wait for slow in-flight bakes to finish on the way out.
        pool.shutdown(wait=False, cancel_futures=True)
        with _lock:
            s = dict(S)
        print(
            f"\nStopped. sent={s['sent']} done={s['done']} "
            f"unreplicated={s['unreplicated']} unavailable={s['unavailable']} "
            f"errors={s['errors']} peak in-flight={s['max_inflight']}"
        )


if __name__ == "__main__":
    main()
