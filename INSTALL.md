# 🛠️ INSTALL — Running the Distributed Pizzeria on a fresh Ubuntu VM

This guide takes you from a **freshly installed Ubuntu Desktop VM running in
VirtualBox** (with **Guest Additions** and the **`docker.io`** package already
installed) to a fully running lab environment.

> **Assumptions** (already done for you, per the task):
> - Ubuntu Desktop is installed and boots to a graphical session.
> - VirtualBox **Guest Additions** are installed (clipboard/shared folders work).
> - The **`docker.io`** package is installed (`docker --version` works with `sudo`).
>
> Everything else — Compose plugin, docker group, Python tooling, getting the
> code in, first run — is covered below. Total time: ~10 minutes (plus image
> downloads on first `up`).

Commands are meant to be run in a **Terminal** inside the VM
(`Ctrl`+`Alt`+`T`).

---

## Sanity Check

```bash
docker --version          # e.g. "Docker version 24.x" (installed via docker.io)
python3 --version         # Ubuntu Desktop ships Python 3
lsb_release -d            # confirm your Ubuntu version
```

---

## Compose, pip, venv

```bash
sudo apt update
sudo apt install -y docker-compose-v2 python3-pip python3-venv git
```

Verify Compose is now available:

```bash
docker compose version    # should print "Docker Compose version v2.x"
```

---

## Un-`sudo` Docker (recommended)

By default only root can talk to the Docker daemon. Add your user to the
`docker` group so the rest of this guide (and the README) works without `sudo`:

```bash
sudo usermod -aG docker $USER
```

**This only takes effect after a new login.** The cleanest way in a desktop VM:

```bash
# Option A — log out and back in (or reboot the VM):
reboot
```

Confirm with

```bash
docker run --rm hello-world
```

(no Errors thrown)

Also make sure the daemon starts on every boot:

```bash
sudo systemctl enable --now docker
```

---

## Clone project

```bash
cd ~
git clone https://github.com/wuerzig/cap-a-pizza
cd cap-a-pizza
```

Confirm with

```bash
ls
# expected: docker-compose.yml  README.md  load_tester.py  dashboard.html  services/  mongo-init/ ...
```

---

## Activate OrderService configuration-template

The stack ships with a ready-to-run `.env`, but confirm it exists (if it was
lost via a shared folder / .gitignore, recreate it from the template):

```bash
ls services/order-service/.env || \
  cp services/order-service/.env.example services/order-service/.env

# Peek at the CAP lever (should say MONGO_WRITE_CONCERN=1 by default):
grep MONGO_WRITE_CONCERN services/order-service/.env
```

---

## Start the environment

```bash
docker compose up --build
```

First run downloads the `mongo:7`, `rabbitmq:3-management`, and `python:3.12`
images plus builds the three services — **this can take several minutes** on a
fresh VM. Leave this terminal running; it streams all the logs.

You're ready when you see:
- `mongo-init` log the line **"Replica set rs0 is ready. PRIMARY elected. Done."**
  and then exit, and
- the order/kitchen/payment services logging that Uvicorn is running.

---

## Dashboard + Load-Generator

Open a **second terminal** (`Ctrl`+`Alt`+`T`), in the project folder:

```bash
cd ~/distributed-pizzeria        # or wherever you put it
python3 -m venv venv
source venv/bin/activate
pip install -r requirements-loadtest.txt
python3 load_tester.py
```

You should see a stream of `OK -> PAID / BAKING / FAILED` lines.

Now open the dashboard. In the VM's **Firefox**:

```bash
mimeopen dashboard.html
```

(or just double-click `dashboard.html` in the Files app). The counters should
climb. Because VirtualBox uses NAT networking by default, `localhost:8000`
resolves correctly **inside** the VM — no extra network config needed.

Quick API check from the terminal:

```bash
curl http://localhost:8000/orders
```

---

## Try the CAP experiment

With the load tester running, simulate a network partition:

```bash
docker pause mongo-sec-1 mongo-sec-2      # isolate the primary
# ...observe the load tester / dashboard...
docker unpause mongo-sec-1 mongo-sec-2    # heal the partition
```

Full LAB instructions are in the PDF-Documents (OPAL)

---

## Shutting down

```bash
# Stop the load tester:  Ctrl+C in its terminal, then `deactivate` the venv.

# Stop the stack (Ctrl+C in its terminal), then remove containers + data:
docker compose down -v
```

---

## Troubleshooting (VM-specific)

| Symptom | Cause / Fix |
|---|---|
| `permission denied ... /var/run/docker.sock` | You skipped Step 2, or didn't re-login. Run `newgrp docker` or reboot. |
| `docker compose: 'compose' is not a docker command` | Compose plugin missing. `sudo apt install -y docker-compose-v2`, or use `docker-compose` (Step 1 note). |
| `Cannot connect to the Docker daemon` | Daemon not running: `sudo systemctl enable --now docker`. |
| First `up` is extremely slow / stalls on downloads | Image pulls over the VM's NAT connection. Give it time; ensure the host has internet and the VM network adapter is enabled. |
| `python3: command not found` for pip/venv | `sudo apt install -y python3-pip python3-venv`. |
| Whole VM feels frozen during a run | Not enough RAM/CPU. Shut down, raise the VM to 4 GB / 2 CPUs in VirtualBox, restart. |
| Ports 8000/8001/8002/15672 already in use | Something else in the VM grabbed them. Stop it, or edit the port mappings in `docker-compose.yml`. |
| Shared-folder files unreadable (`/media/sf_*`) | Add your user to the `vboxsf` group (Step 3B) and log out/in. |
| Dashboard shows "Cannot reach OrderService" | The stack isn't up yet, or you opened `dashboard.html` on the **host** instead of inside the VM. Open it inside the VM. |

---
