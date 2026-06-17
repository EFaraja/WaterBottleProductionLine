from influxdb_client import InfluxDBClient, Point, WritePrecision
from influxdb_client.client.write_api import SYNCHRONOUS
import time

_URL   = "http://localhost:8086"
_TOKEN = "my-super-token"
_ORG   = "SRH"
_BUCKET = "production"


class InfluxLogger:

    def __init__(self):
        self.client = InfluxDBClient(url=_URL, token=_TOKEN, org=_ORG)
        self.write_api = self.client.write_api(write_options=SYNCHRONOUS)
        self.bucket = _BUCKET
        self.org = _ORG

    def _write(self, point):
        try:
            self.write_api.write(bucket=self.bucket, org=self.org, record=point)
        except Exception as e:
            print(f"[InfluxDB] write error: {e}")

    # ── Production metrics ─────────────────────────────────────────────────────
    def write_production(self, bottles, good, defects, state, efficiency):
        point = (
            Point("production_line")
            .tag("machine_state", state)
            .field("bottles_produced",  int(bottles))
            .field("good_bottles",       int(good))
            .field("defective_bottles",  int(defects))
            .field("efficiency_pct",     float(efficiency))
            .time(time.time_ns(), WritePrecision.NS)
        )
        self._write(point)
        print(f"[InfluxDB] production: {bottles} total, {defects} defects, {efficiency:.1f}% eff")

    # ── CMMS health snapshot ───────────────────────────────────────────────────
    def write_cmms_health(self, equipment_health, maintenance_status,
                          work_orders_open, total_maintenance_actions,
                          defective_count):
        status_code = {"NORMAL": 0, "WARNING": 1, "DUE": 2, "FAULT": 3}.get(
            maintenance_status, 0
        )
        point = (
            Point("cmms_health")
            .tag("maintenance_status", maintenance_status)
            .field("equipment_health",          float(equipment_health))
            .field("maintenance_status_code",   int(status_code))
            .field("work_orders_open",          int(work_orders_open))
            .field("total_maintenance_actions", int(total_maintenance_actions))
            .field("total_defects",             int(defective_count))
            .time(time.time_ns(), WritePrecision.NS)
        )
        self._write(point)

    # ── Discrete events (faults, maintenance actions) ──────────────────────────
    def write_cmms_event(self, event_type, message):
        """
        event_type: "fault" | "maintenance" | "alarm"
        """
        point = (
            Point("cmms_events")
            .tag("event_type", event_type)
            .field("message", str(message))
            .field("count", 1)
            .time(time.time_ns(), WritePrecision.NS)
        )
        self._write(point)
        print(f"[InfluxDB] cmms_event {event_type}: {message}")

    # ── Per-station wear / defect rate ─────────────────────────────────────────
    def write_station_metrics(self, station_name, wear_pct, defect_rate, status):
        point = (
            Point("station_metrics")
            .tag("station", station_name)
            .tag("status",  status)
            .field("wear_pct",        float(wear_pct))
            .field("defect_rate_pct", float(defect_rate))
            .time(time.time_ns(), WritePrecision.NS)
        )
        self._write(point)

    # ── Backward-compatibility shim ────────────────────────────────────────────
    def write_data(self, bottles, defects, state):
        good = max(0, int(bottles) - int(defects))
        eff  = good / bottles * 100 if bottles > 0 else 0.0
        self.write_production(bottles, good, defects, state, eff)


# ══════════════════════════════════════════════════════════════════════════════
# InfluxReader  —  used by the CMMS dashboard to pull live data
# ══════════════════════════════════════════════════════════════════════════════

class InfluxReader:

    def __init__(self):
        self.client    = InfluxDBClient(url=_URL, token=_TOKEN, org=_ORG)
        self.query_api = self.client.query_api()
        self.bucket    = _BUCKET
        self.org       = _ORG
        self.available = self._ping()

    def _ping(self) -> bool:
        try:
            h = self.client.health()
            return h.status == "pass"
        except Exception:
            return False

    def _query(self, flux: str) -> list:
        try:
            result = self.query_api.query(flux, org=self.org)
            self.available = True
            return result
        except Exception as e:
            self.available = False
            print(f"[InfluxDB] read error: {e}")
            return []

    # ── Latest production snapshot ─────────────────────────────────────────────
    def get_latest_production(self) -> dict:
        """Returns dict with keys: bottles_produced, good_bottles,
           defective_bottles, efficiency_pct, machine_state"""
        # group(columns:["_field"]) merges all tag-series for each field so that
        # last() picks the single most-recent record per field regardless of which
        # machine_state tag was active (avoids stale STOPPED data shadowing newer
        # RUNNING data after a machine reset).
        tables = self._query(f"""
            from(bucket: "{self.bucket}")
              |> range(start: -1h)
              |> filter(fn: (r) => r._measurement == "production_line")
              |> group(columns: ["_field"])
              |> last()
        """)
        data = {}
        latest_time = None
        for table in tables:
            for rec in table.records:
                data[rec.get_field()] = rec.get_value()
                rec_time = rec.get_time()
                if latest_time is None or rec_time > latest_time:
                    latest_time = rec_time
                    data["machine_state"] = rec.values.get("machine_state", "UNKNOWN")
        return data

    # ── Latest CMMS health snapshot ────────────────────────────────────────────
    def get_latest_cmms_health(self) -> dict:
        """Returns dict with keys: equipment_health, maintenance_status_code,
           work_orders_open, total_maintenance_actions, total_defects"""
        tables = self._query(f"""
            from(bucket: "{self.bucket}")
              |> range(start: -1h)
              |> filter(fn: (r) => r._measurement == "cmms_health")
              |> group(columns: ["_field"])
              |> last()
        """)
        data = {}
        for table in tables:
            for rec in table.records:
                data[rec.get_field()] = rec.get_value()
        return data

    # ── Recent fault / maintenance events ──────────────────────────────────────
    def get_recent_events(self, limit: int = 40) -> list:
        """Returns list of dicts: {time, event_type, message}"""
        tables = self._query(f"""
            from(bucket: "{self.bucket}")
              |> range(start: -24h)
              |> filter(fn: (r) => r._measurement == "cmms_events"
                        and r._field == "message")
              |> sort(columns: ["_time"], desc: true)
              |> limit(n: {limit})
        """)
        events = []
        for table in tables:
            for rec in table.records:
                events.append({
                    "time":       rec.get_time().strftime("%Y-%m-%d %H:%M:%S"),
                    "event_type": rec.values.get("event_type", "info"),
                    "message":    rec.get_value() or "",
                })
        return events

    # ── Per-station metrics ────────────────────────────────────────────────────
    def get_station_metrics(self) -> dict:
        """Returns dict keyed by station name:
           {wear_pct, defect_rate_pct, status}"""
        tables = self._query(f"""
            from(bucket: "{self.bucket}")
              |> range(start: -30m)
              |> filter(fn: (r) => r._measurement == "station_metrics")
              |> last()
        """)
        stations: dict = {}
        for table in tables:
            for rec in table.records:
                name = rec.values.get("station", "unknown")
                if name not in stations:
                    stations[name] = {"status": rec.values.get("status", "OK")}
                stations[name][rec.get_field()] = rec.get_value()
        return stations

#change commit