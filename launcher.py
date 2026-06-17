"""
launcher.py  —  Water Bottle Production Line
============================================
Starts both the HMI and CMMS dashboard as separate windows.

    python launcher.py

Architecture
------------
HMI (hmi.py)
  • Controls the production line (START / STOP / RESET)
  • Writes every cycle to InfluxDB:
      - Measurement: production_line  → bottles, defects, efficiency
      - Measurement: cmms_health      → equipment health, maintenance status
      - Measurement: cmms_events      → fault and maintenance events

CMMS Dashboard (cmms_dashboard.py)
  • Reads live data FROM InfluxDB (no direct link to HMI process)
  • Falls back to its own simulator when InfluxDB is offline
  • Pushes per-station wear/defect metrics → station_metrics

Grafana
  • Connects to InfluxDB (localhost:8086, org=SRH, bucket=production)
  • Queries all four measurements for live dashboards

InfluxDB must be running for the two apps to share data.
Without InfluxDB each app runs its own independent simulator.
"""

import subprocess
import sys
import os

BASE = os.path.dirname(os.path.abspath(__file__))


def main():
    print("=" * 60)
    print("  Water Bottle Production Line  —  Launcher")
    print("=" * 60)
    print("  Starting HMI …")
    hmi_proc = subprocess.Popen(
        [sys.executable, os.path.join(BASE, "hmi.py")],
        cwd=BASE,
    )

    print("  Starting CMMS Dashboard …")
    cmms_proc = subprocess.Popen(
        [sys.executable, os.path.join(BASE, "cmms_dashboard.py")],
        cwd=BASE,
    )

    print()
    print("  Both windows are open.")
    print("  Data link: HMI → InfluxDB (localhost:8086) → CMMS / Grafana")
    print("  Close either window or press Ctrl+C here to stop both.")
    print("=" * 60)

    try:
        hmi_proc.wait()
    except KeyboardInterrupt:
        pass
    finally:
        for proc in (hmi_proc, cmms_proc):
            if proc.poll() is None:
                proc.terminate()
        print("\n  Both processes stopped.")


if __name__ == "__main__":
    main()

#change commit