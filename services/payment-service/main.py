# ============================================================================
#  PaymentService  --  takes payment (and fails 30% of the time, on purpose)
# ============================================================================
#  This service is unreliable BY DESIGN. Roughly 3 out of every 10 payments
#  are declined with "Insufficient Funds". That unpredictability is what makes
#  Session 3 (Sagas / compensating transactions) necessary and interesting.
# ============================================================================

import random

from fastapi import FastAPI
from fastapi.responses import JSONResponse
from pydantic import BaseModel

app = FastAPI(title="Pizzeria PaymentService")

# Probability that a given payment is declined. Tweak this to make the
# Session 3 failures more or less frequent while students debug their Saga.
FAILURE_RATE = 0.30


class PayRequest(BaseModel):
    customer: str = "anonymous"
    pizza: str = "margherita"


@app.get("/health")
def health():
    return {"status": "ok"}


@app.post("/pay")
def pay(req: PayRequest):
    """Charge the customer. Randomly fails ~30% of the time.

    TODO (Lab 3): Listen to events and trigger Compensating Transactions
    (Sagas) on failure. When a payment fails here, the orchestrator must
    publish a PaymentFailedEvent so the order can be cancelled and any
    reserved ingredients freed -- there is no cross-service ROLLBACK.
    """
    if random.random() < FAILURE_RATE:
        print(f"[payment] DECLINED payment for {req.customer} (insufficient funds)")
        return JSONResponse(
            status_code=400,
            content={"status": "DECLINED", "reason": "Insufficient Funds"},
        )

    print(f"[payment] APPROVED payment for {req.customer}")
    return {"status": "PAID", "customer": req.customer}
