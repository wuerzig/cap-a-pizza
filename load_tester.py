#!/usr/bin/env python3
# ============================================================================
#  load_tester.py  --  the "customers keep ordering" firehose
# ============================================================================
#  Sends POST /orders to the OrderService at a steady 5 requests/second,
#  forever, printing the outcome of each request. This is what students watch
#  during the Session 1 CAP experiment.
#
#  Usage:
#      python load_tester.py                 # targets http://localhost:8000
#      ORDER_URL=http://localhost:8000 python load_tester.py
#
#  Requires:  pip install requests
#
#  WHAT TO WATCH DURING THE CAP EXPERIMENT
#  ---------------------------------------
#    - w:1  + paused secondaries -> requests keep succeeding (Availability).
#    - w:majority + paused secondaries -> requests FREEZE then time out
#      (Consistency preserved, Availability sacrificed).
# ============================================================================

import os
import time
import datetime

import requests

ORDER_URL = os.getenv("ORDER_URL", "http://localhost:8000")
REQUESTS_PER_SECOND = 5
DELAY = 1.0 / REQUESTS_PER_SECOND  # 0.2s between requests

# A little variety so the orders look believable in the dashboard.
CUSTOMERS = ["alice", "bob", "carol", "dave", "erin"]
PIZZAS = ["margherita", "pepperoni", "hawaiian", "veggie", "quattro-formaggi"]


def main():
    print(f"Firing {REQUESTS_PER_SECOND} orders/sec at {ORDER_URL}/orders")
    print("Press Ctrl+C to stop.\n")

    sent = 0
    ok = 0
    failed = 0

    while True:
        started = time.monotonic()
        sent += 1
        customer = CUSTOMERS[sent % len(CUSTOMERS)]
        pizza = PIZZAS[sent % len(PIZZAS)]
        stamp = datetime.datetime.now().strftime("%H:%M:%S")

        try:
            # A tight timeout is important for the CAP demo: in CP mode the
            # write blocks, and we want to SEE it time out rather than hang.
            resp = requests.post(
                f"{ORDER_URL}/orders",
                json={"customer": customer, "pizza": pizza},
                timeout=6,
            )
            if resp.status_code == 200:
                ok += 1
                state = resp.json().get("state", "?")
                print(f"[{stamp}] #{sent:<5} OK      -> {state:<8} "
                      f"(ok={ok} failed={failed})")
            else:
                failed += 1
                print(f"[{stamp}] #{sent:<5} HTTP {resp.status_code} "
                      f"(ok={ok} failed={failed})")
        except requests.exceptions.RequestException as exc:
            # Timeouts and connection errors land here -- this is the
            # "system is unavailable" signal in the CP experiment.
            failed += 1
            reason = type(exc).__name__
            print(f"[{stamp}] #{sent:<5} DROPPED -> {reason:<20} "
                  f"(ok={ok} failed={failed})")

        # Keep a steady pace: subtract the time the request already took.
        elapsed = time.monotonic() - started
        if elapsed < DELAY:
            time.sleep(DELAY - elapsed)


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print("\nStopped. Buon appetito!")
