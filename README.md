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
   5 orders/sec     │                     │   polls /orders 1x/sec
                    └───────┬─────────────┘
                            │ (synchronous REST calls — for now)
              ┌─────────────┴──────────────┐
              ▼                             ▼
    ┌───────────────────┐        ┌────────────────────┐
    │  KitchenService   │        │  PaymentService    │
    │  (FastAPI, :8001) │        │  (FastAPI, :8002)  │
    │  /bake sleeps 2s  │        │  /pay fails ~30%   │
    └───────────────────┘        └────────────────────┘

    Persistence:  3-node MongoDB replica set  (mongo-primary + 2 secondaries)
    Broker:       RabbitMQ (:5672, UI :15672) — pre-wired, used from Session 2
```

---

## Project structure

```
distributed-pizzeria/
├── docker-compose.yml            # Boots the whole environment
├── .gitignore
├── README.md                     # You are here
├── load_tester.py                # Fires 5 POST /orders per second, forever
├── dashboard.html                # Vanilla HTML/JS live dashboard
├── requirements-loadtest.txt     # Deps for running load_tester.py on the host
│
├── mongo-init/
│   ├── init-replica.js           # rs.initiate() — the 3-node replica set config
│   └── run-init.sh               # Waits for mongod, then applies it (idempotent)
│
└── services/
    ├── order-service/            # THE CORE
    │   ├── main.py               #   FastAPI app (POST/GET /orders)
    │   ├── requirements.txt
    │   ├── Dockerfile
    │   ├── .env.example          #   Template — copy to .env
    │   └── .env                  #   ACTIVE config (the CAP lever lives here)
    │
    ├── kitchen-service/          # Bakes pizzas (sleeps 2s)
    │   ├── main.py
    │   ├── requirements.txt
    │   └── Dockerfile
    │
    └── payment-service/          # Takes payment (fails ~30%)
        ├── main.py
        ├── requirements.txt
        └── Dockerfile
```

---

## Service reference

| Service | Port | Key endpoints | Notes |
|---|---|---|---|
| OrderService   | 8000 | `POST /orders`, `GET /orders` | Reads Mongo URI + WriteConcern from `.env` |
| KitchenService | 8001 | `POST /bake` | Sleeps ~2s to simulate baking |
| PaymentService | 8002 | `POST /pay`  | Declines ~30% of payments |
| RabbitMQ       | 5672 / 15672 | — | Management UI at http://localhost:15672 (guest/guest) |
| MongoDB        | 27017 | — | 3-node replica set `rs0` |

The `MONGO_WRITE_CONCERN` value in `services/order-service/.env` is the dial for
the CAP experiment (`1` = availability-leaning, `majority` = consistency-leaning).
*Buon appetito, and happy partitioning.*
