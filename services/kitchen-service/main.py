# ============================================================================
#  KitchenService  --  bakes pizzas (slowly, on purpose)
# ============================================================================
#  A deliberately dumb little web server. Its only job is to be SLOW, so that
#  students feel the pain of synchronous coupling: while this sleeps for two
#  seconds, the OrderService (and the customer) can do nothing but wait.
# ============================================================================

import time

from fastapi import FastAPI
from pydantic import BaseModel

app = FastAPI(title="Pizzeria KitchenService")

# How long a pizza takes to bake. Two seconds is long enough to be annoying
# under load -- which is exactly what motivates the move to events in Lab 2.
BAKE_SECONDS = 2


class BakeRequest(BaseModel):
    # Accept whatever the OrderService sends; we only care that a pizza exists.
    pizza: str = "margherita"


@app.get("/health")
def health():
    return {"status": "ok"}


@app.post("/bake")
def bake(req: BakeRequest):
    """Bake a pizza. Simulates real oven time by sleeping for 2 seconds.

    TODO (Lab 2): Convert this REST endpoint into a RabbitMQ message listener.
    Instead of the OrderService calling us and blocking, we should subscribe
    to OrderPlacedEvent, bake on our own schedule, and then publish a
    PizzaBakedEvent when we're done.
    """
    print(f"[kitchen] Baking a {req.pizza}... ({BAKE_SECONDS}s)")
    time.sleep(BAKE_SECONDS)
    print(f"[kitchen] {req.pizza} is ready!")
    return {"status": "BAKED", "pizza": req.pizza}
