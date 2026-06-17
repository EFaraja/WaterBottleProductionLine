# Water Bottle Production Line

A simulated water bottle production line built for the Advanced Programming 2026 course at SRH. It has two separate windows — an HMI for controlling the line and a CMMS dashboard for monitoring machine health — connected through InfluxDB so they can run as independent processes.

---

## What it does

The HMI simulates a production line that takes a bottle through five stages: supply, filling, capping, branding, and quality control. Each stage has a small random chance of failure, so some bottles come out defective. If too many defects pile up, the machine stops itself and raises a fault.

The CMMS dashboard sits on the other side of InfluxDB. It doesn't control anything — it just reads the data the HMI writes and shows you equipment health, open work orders, alerts, and a log of faults and maintenance events. You can also create work orders manually from the dashboard.

Grafana connects to the same InfluxDB instance if you want to build analytics dashboards on top of the data.

---

## Requirements

- Python 3.10 or higher
- Docker Desktop (for InfluxDB and Grafana)

Install the Python dependencies:

```bash
pip install customtkinter influxdb-client
```

---

## Getting started

First, start InfluxDB and Grafana with Docker:

```bash
docker compose up -d
```

Then launch both windows at once:

```bash
python launcher.py
```

That's it. The HMI and CMMS dashboard open as separate windows. You can also run them individually if you only need one:

```bash
python hmi.py
python cmms_dashboard.py
```

If InfluxDB isn't running, both apps fall back to a local simulator automatically. The CMMS will show "SIMULATOR (InfluxDB offline)" in the top bar so you know.

---

## Using the HMI

Press **START** to begin production. The line runs continuously, cycling through bottles one at a time. You can **STOP** it at any point and **RESET** to clear all counters and start fresh.

The **Perform Maintenance** button resets equipment health back to 100% and logs a maintenance event to InfluxDB, which shows up in the CMMS maintenance history.

The machine will stop itself automatically if it detects 10 or more defective bottles — this is the excessive defect fault. When that happens, press RESET and then START to resume.

---

## Using the CMMS dashboard

The dashboard has four tabs. The main **Dashboard** tab shows equipment health, bottle counts, and per-station wear. The **Work Orders** tab lets you view and create work orders — faults generate them automatically, but you can also add one manually with a description and priority. **Maintenance** shows past maintenance actions pulled from InfluxDB. **Alerts** flags anything that needs attention based on health levels and fault history.

---

## InfluxDB and Grafana

InfluxDB runs on `http://localhost:8086`. Login is `admin` / `admin12345`. The org is `SRH`, the bucket is `production`, and the token is `my-super-token`.

Grafana runs on `http://localhost:3000`. Default login is `admin` / `admin`. To connect it to InfluxDB, add a Flux data source pointing at `http://influxdb:8086` with the org, token, and bucket above.

The HMI writes to three measurements: `production_line` for bottle counts and efficiency, `cmms_health` for equipment status, and `cmms_events` for discrete fault and maintenance events. The CMMS dashboard writes station wear data to `station_metrics`.

---

## Project files

- `launcher.py` — opens both apps as separate processes
- `hmi.py` — the operator control window
- `cmms_dashboard.py` — the maintenance monitoring window
- `production_line.py` — the core simulation logic
- `cmms.py` — the CMMS model (work orders, fault history, health tracking)
- `bottle.py` — the bottle object
- `quality_control.py` — inspects each bottle at the end of the line
- `database/influx_client.py` — handles all InfluxDB reads and writes
- `docker-compose.yml` — spins up InfluxDB 2.7 and Grafana
