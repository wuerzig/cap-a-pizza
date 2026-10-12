# The Distributed Pizzeria

A hands-on lab environment for learning the **CAP Theorem**, **Event-Driven
Architecture (EDA)**, **CQRS**, and **Sagas** — by running a tiny pizza-ordering
system made of three microservices. This was originally developed at DHSN - Duale 
Hochschule Sachsen, Dresden by Prof. Dr. Thomas Nindel, 2026.

See LICENSE.md for licensing details.

## The system

```
                    ┌─────────────────────┐
   load_tester.py   │    OrderService     │   dashboard.html
   ───────────────► │   (FastAPI, :8000)  │ ◄───────────────
   steady orders    │                     │   polls /orders 1x/sec
                    └───────┬─────────────┘
                            │ (synchronous REST calls — for now)
              ┌─────────────┴──────────────┐
              ▼                             ▼
    ┌───────────────────┐        ┌────────────────────┐
    │  KitchenService   │        │  PaymentService    │
    │  (FastAPI, :8001) │        │  (FastAPI, :8002)  │
    │  /bake sleeps 10s │        │  /pay fails ~30%   │
    └───────────────────┘        └────────────────────┘

    Persistence:  3-node MongoDB replica set  (mongo-primary + 2 secondaries)
    Broker:       RabbitMQ (:5672, UI :15672) — pre-wired, used from Session 2
```

---

## Quickstart

Prerequisites: Docker + Docker Compose, and Python 3 (only for the load tester).

```bash
# 1. Boot everything (MongoDB replica set, RabbitMQ, the three services)
docker compose up --build

# 2. In a second terminal, generate traffic
pip install -r requirements-loadtest.txt
python load_tester.py

# 3. Open the live dashboard
#    open dashboard.html in your browser

# Reset between runs:  ./clear-db.sh
# Tear everything down: docker compose down -v
```

## Key files to look at

| File | What it's for |
|---|---|
| `services/order-service/main.py` | The core: `POST`/`GET /orders`, the write-concern logic you'll study |
| `services/kitchen-service/main.py` | Bakes pizzas (deliberately slow) |
| `services/payment-service/main.py` | Takes payment (fails ~30% on purpose) |
| `services/order-service/.env` | **The CAP lever** — `MONGO_WRITE_CONCERN` (`1` = availability-leaning, `3`/all = consistency-leaning) |
| `docker-compose.yml` | MongoDB replica-set nodes & images, ports, broker |
| `mongo-init/init-replica.js` | The 3-node replica-set definition (`rs.initiate`) |
| `load_tester.py` / `dashboard.html` | Traffic generator and live view |

## Lab instructions

Step-by-step exercises for all three sessions are in **`LAB_CAP-a-Pizza.pdf`**.

*Buon appetito, and happy partitioning.*
