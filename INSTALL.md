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

## Step 0 — Sanity check what you already have

```bash
docker --version          # e.g. "Docker version 24.x" (installed via docker.io)
python3 --version         # Ubuntu Desktop ships Python 3
lsb_release -d            # confirm your Ubuntu version
```

If `docker --version` prints a version, the engine is installed. It probably
still needs `sudo` at this point — we fix that in Step 2.

---

## Step 1 — Install the missing pieces

The `docker.io` package installs the **engine** but **not** the Compose plugin,
and a fresh desktop may be missing `pip`/`venv` and `git`. Install them all:

```bash
sudo apt update
sudo apt install -y docker-compose-v2 python3-pip python3-venv git
```

Verify Compose is now available:

```bash
docker compose version    # should print "Docker Compose version v2.x"
```

> **If `docker-compose-v2` isn't found** (older Ubuntu, e.g. 22.04 without
> updates), install the classic standalone instead:
> ```bash
> sudo apt install -y docker-compose
> ```
> Then use the **hyphenated** command `docker-compose` everywhere this guide
> says `docker compose`. (They behave the same for our purposes.)

---

## Step 2 — Run Docker without `sudo` (recommended)

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

```bash
# Option B — apply it to just the current shell without logging out:
newgrp docker
```

Confirm it worked (no `sudo`, no permission error):

```bash
docker run --rm hello-world
```

Also make sure the daemon starts on every boot:

```bash
sudo systemctl enable --now docker
```

> Don't want to bother with the group? You can instead prefix every `docker`
> command in this guide and the README with `sudo`. The group approach is
> less error-prone.

---

## Step 3 — Get the project into the VM

Pick whichever is convenient:

**A. Clone with git** (if the repo is hosted somewhere):

```bash
cd ~
git clone <your-repo-url> distributed-pizzeria
cd distributed-pizzeria
```

**B. VirtualBox Shared Folder** (Guest Additions are installed, so this works).
On the **host**: VM → *Settings → Shared Folders* → add the folder containing
the project, tick **Auto-mount** and **Make Permanent**. Inside the VM the
share appears under `/media/sf_<name>`; your user must be in the `vboxsf`
group to read it:

```bash
sudo usermod -aG vboxsf $USER   # then log out/in (like Step 2)
cp -r /media/sf_<name>/distributed-pizzeria ~/distributed-pizzeria
cd ~/distributed-pizzeria
```

**C. Drag-and-drop / shared clipboard.** If you enabled Drag-and-Drop in the
VM settings, just drop the `distributed-pizzeria` folder onto the desktop, then
`cd ~/Desktop/distributed-pizzeria`.

Whatever you choose, confirm you're in the right place:

```bash
ls
# expected: docker-compose.yml  README.md  load_tester.py  dashboard.html  services/  mongo-init/ ...
```

---

## Step 4 — Prepare the OrderService config

The stack ships with a ready-to-run `.env`, but confirm it exists (if it was
lost via a shared folder / .gitignore, recreate it from the template):

```bash
ls services/order-service/.env || \
  cp services/order-service/.env.example services/order-service/.env

# Peek at the CAP lever (should say MONGO_WRITE_CONCERN=1 by default):
grep MONGO_WRITE_CONCERN services/order-service/.env
```

---

## Step 5 — Start the environment

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

> **VM sizing tip:** give the VM at least **4 GB RAM** and **2 CPUs** in
> VirtualBox settings. Three MongoDB nodes + RabbitMQ + three Python services
> is snug in 2 GB.

---

## Step 6 — Run the load generator + open the dashboard

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
firefox dashboard.html
```

(or just double-click `dashboard.html` in the Files app). The counters should
climb. Because VirtualBox uses NAT networking by default, `localhost:8000`
resolves correctly **inside** the VM — no extra network config needed.

Quick API check from the terminal:

```bash
curl http://localhost:8000/orders
```

---

## Step 7 — Try the CAP experiment

With the load tester running, simulate a network partition:

```bash
docker pause mongo-sec-1 mongo-sec-2      # isolate the primary
# ...observe the load tester / dashboard...
docker unpause mongo-sec-1 mongo-sec-2    # heal the partition
```

The full Phase 1 (AP) / Phase 2 (CP) walkthrough — including editing
`MONGO_WRITE_CONCERN` and running `docker compose restart order-service` — is
in **[README.md](README.md#-the-cap-theorem-experiment-session-1)**.

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

*That's it — you now have a distributed system running inside a single VM.
Head to [README.md](README.md) for the lab sessions.* 🍕
