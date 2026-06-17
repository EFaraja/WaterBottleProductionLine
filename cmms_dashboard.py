import customtkinter as ctk
import tkinter as tk
import random
from datetime import datetime, timedelta

# ── InfluxDB integration ───────────────────────────────────────────────────────
try:
    from database.influx_client import InfluxReader, InfluxLogger
    _reader = InfluxReader()
    _writer = InfluxLogger()
    INFLUX_AVAILABLE = _reader.available
except Exception:
    _reader = None
    _writer = None
    INFLUX_AVAILABLE = False

# ── Fallback local production line (used when InfluxDB is offline) ─────────────
try:
    from production_line import ProductionLine
    line = ProductionLine()
    SIMULATION_MODE = False
except ImportError:
    SIMULATION_MODE = True

    class _FakeCMMS:
        def __init__(self):
            self.equipment_health = 95.0
            self.maintenance_status = "NORMAL"
            self.last_maintenance_date = datetime.now() - timedelta(days=5)
            self.next_maintenance_date = datetime.now() + timedelta(days=25)
            self.work_orders = []
            self.fault_history = []
            self.maintenance_history = []
            self.defective_bottles = 0
            self.total_maintenance_actions = 0
            self._alerts = []

        def get_alerts(self):
            return list(self._alerts)

        def perform_maintenance(self):
            self.equipment_health = 100.0
            self.maintenance_status = "NORMAL"
            self.last_maintenance_date = datetime.now()
            self.next_maintenance_date = datetime.now() + timedelta(days=30)
            self.total_maintenance_actions += 1
            self._alerts.clear()
            self.maintenance_history.append({
                "date": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                "action": "Preventive Maintenance"
            })

        def record_defect(self):
            self.defective_bottles += 1
            self.equipment_health = max(0, self.equipment_health - 0.5)
            if self.equipment_health < 60 and "Health critical" not in self._alerts:
                self._alerts.append("Health critical — schedule maintenance")
            if self.equipment_health < 80:
                self.maintenance_status = "WARNING"

        def report_fault(self, msg):
            self.fault_history.append({
                "date": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                "fault": msg
            })
            wo = {
                "id": len(self.work_orders) + 1,
                "issue": msg,
                "status": "OPEN",
                "date": datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            }
            self.work_orders.append(wo)
            if msg not in self._alerts:
                self._alerts.append(f"FAULT: {msg}")

    class _FakeLine:
        STAGES = ["Bottle Supply", "Water Filling", "Capping", "Branding", "Quality Control"]

        def __init__(self):
            self.machine_state = "STOPPED"
            self.current_stage = "IDLE"
            self._idx = 0
            self.total_bottles = 0
            self.good_bottles = 0
            self.defective_bottles = 0
            self.last_error = "NONE"
            self.cmms = _FakeCMMS()
            self.water_level = 85.0

        def start(self):
            self.machine_state = "RUNNING"
            self.current_stage = self.STAGES[0]

        def stop(self):
            self.machine_state = "STOPPED"
            self.current_stage = "IDLE"

        def reset(self):
            self.__init__()

        def process_bottle(self):
            if self.machine_state != "RUNNING":
                return None
            self._idx = (self._idx + 1) % len(self.STAGES)
            self.current_stage = self.STAGES[self._idx]
            self.cmms.equipment_health = max(20, self.cmms.equipment_health - random.uniform(0.05, 0.2))
            self.water_level = max(5, min(100, self.water_level - random.uniform(0.1, 0.5)))

            defective = random.random() < 0.08
            if self._idx == len(self.STAGES) - 1:
                self.total_bottles += 1
                if defective:
                    self.defective_bottles += 1
                    reason = random.choice(["Cap misalign", "Underfill", "Label error", "Seal breach"])
                    self.last_error = reason
                    self.cmms.record_defect()
                    if self.defective_bottles % 5 == 0:
                        self.cmms.report_fault("Excessive Defects Detected")
                    return type("B", (), {"id": self.total_bottles, "defective": True, "defect_reason": reason})()
                else:
                    self.good_bottles += 1
                    return type("B", (), {"id": self.total_bottles, "defective": False, "defect_reason": None})()
            return None

    line = _FakeLine()

# ── Theme ──────────────────────────────────────────────────────────────────────
BG_DEEP   = "#060D1A"
BG_MID    = "#0B1628"
BG_PANEL  = "#0F1E33"
BG_CARD   = "#132340"

CYAN      = "#00D9FF"
CYAN_DIM  = "#0090AA"
GREEN     = "#00E676"
AMBER     = "#FFB300"
RED       = "#FF1744"
WHITE     = "#E8F4FF"
GRAY      = "#8AAABB"
GRAY_DIM  = "#3D5566"

ctk.set_appearance_mode("dark")
ctk.set_default_color_theme("blue")

# ── Station tracking ───────────────────────────────────────────────────────────
STATIONS = [
    {"name": "Bottle Supply",   "key": "supply"},
    {"name": "Water Filling",   "key": "filling"},
    {"name": "Capping",         "key": "capping"},
    {"name": "Branding",        "key": "branding"},
    {"name": "Quality Control", "key": "qc"},
]

station_data = {
    s["key"]: {
        "wear":        random.uniform(1.0, 6.0),
        "defect_rate": random.uniform(2.0, 8.0),
        "status":      "OK",
    }
    for s in STATIONS
}

_fault_log_seen   = set()
_hmi_state        = "IDLE"   # updated each cycle from InfluxDB; drives station wear simulation

# Shared state updated by update_ui() — used by alert and work-order refresh functions
_last_health       = 100.0
_last_maint_status = "NORMAL"
_last_work_orders  = 0
_last_fault_events: list = []   # recent fault events from InfluxDB

# Manually created work orders (CMMS operator-generated)
_manual_work_orders: list = []

# ── Root window ────────────────────────────────────────────────────────────────
root = ctk.CTk()
root.title("Water Bottle Production Line  —  CMMS")
root.geometry("1440x900")
root.minsize(1100, 750)
root.configure(fg_color=BG_DEEP)

# ══════════════════════════════════════════════════════════════════════════════
# NAV BAR
# ══════════════════════════════════════════════════════════════════════════════
nav_bar = ctk.CTkFrame(root, fg_color=BG_MID, corner_radius=0, height=62)
nav_bar.pack(fill="x", side="top")
nav_bar.pack_propagate(False)

ctk.CTkLabel(
    nav_bar,
    text="⬡  WATER BOTTLE  CMMS",
    font=("Segoe UI", 15, "bold"),
    text_color=CYAN,
).pack(side="left", padx=22, pady=14)

ctk.CTkLabel(
    nav_bar,
    text="Maintenance Management System  •  Live Production Monitoring",
    font=("Segoe UI", 9),
    text_color=GRAY,
).pack(side="left", padx=(0, 30))

status_pill = ctk.CTkLabel(
    nav_bar,
    text="  ● IDLE  ",
    font=("Segoe UI", 10, "bold"),
    text_color=BG_DEEP,
    fg_color=AMBER,
    corner_radius=8,
    width=100,
    height=28,
)
status_pill.pack(side="right", padx=22, pady=16)

clock_lbl = ctk.CTkLabel(nav_bar, text="", font=("Consolas", 11), text_color=GRAY)
clock_lbl.pack(side="right", padx=10)

# ── Tab nav buttons ────────────────────────────────────────────────────────────
nav_btn_frame = ctk.CTkFrame(nav_bar, fg_color="transparent")
nav_btn_frame.pack(side="left")

content_area = ctk.CTkFrame(root, fg_color="transparent")
content_area.pack(fill="both", expand=True)

_pages: dict = {}
_nav_btns: dict = {}


def _switch_page(name: str):
    for t, page in _pages.items():
        if t == name:
            page.pack(fill="both", expand=True)
            _nav_btns[t].configure(fg_color=CYAN, text_color=BG_DEEP)
        else:
            page.pack_forget()
            _nav_btns[t].configure(fg_color="transparent", text_color=GRAY)

    # Immediately refresh the newly shown page — functions are resolved at
    # call-time so forward references to _refresh_* are safe here.
    if name == "Work Orders":
        _refresh_wo()
    elif name == "Maintenance":
        _refresh_maint()
    elif name == "Alerts":
        _refresh_alerts()


def _make_nav_btn(text: str):
    first = not _nav_btns
    btn = ctk.CTkButton(
        nav_btn_frame,
        text=text,
        font=("Segoe UI", 11, "bold"),
        fg_color=CYAN if first else "transparent",
        text_color=BG_DEEP if first else GRAY,
        hover_color=CYAN_DIM,
        corner_radius=6,
        height=32,
        width=120,
        command=lambda t=text: _switch_page(t),
    )
    btn.pack(side="left", padx=4, pady=14)
    _nav_btns[text] = btn


# Create scrollable pages
for _tab in ["Dashboard", "Work Orders", "Maintenance", "Alerts"]:
    _p = ctk.CTkScrollableFrame(
        content_area,
        fg_color="transparent",
        scrollbar_button_color=GRAY_DIM,
        scrollbar_button_hover_color=CYAN_DIM,
    )
    _pages[_tab] = _p
    _make_nav_btn(_tab)

_pages["Dashboard"].pack(fill="both", expand=True)

# ══════════════════════════════════════════════════════════════════════════════
# HELPERS
# ══════════════════════════════════════════════════════════════════════════════

def _card(parent, **kw):
    defaults = dict(fg_color=BG_PANEL, corner_radius=10)
    defaults.update(kw)
    return ctk.CTkFrame(parent, **defaults)


def _srow(parent, label_text):
    f = ctk.CTkFrame(parent, fg_color=BG_MID, corner_radius=6)
    f.pack(fill="x", pady=3)
    ctk.CTkLabel(f, text=label_text, font=("Segoe UI", 9), text_color=GRAY, anchor="w").pack(
        side="left", padx=10, pady=6
    )
    val = ctk.CTkLabel(f, text="—", font=("Segoe UI", 9, "bold"), text_color=WHITE, anchor="e")
    val.pack(side="right", padx=10)
    return val


def _status_color(status: str) -> str:
    return {"OK": GREEN, "WATCH": AMBER, "FAULT": RED}.get(status, GRAY)


# ══════════════════════════════════════════════════════════════════════════════
# DASHBOARD PAGE
# ══════════════════════════════════════════════════════════════════════════════
dash = _pages["Dashboard"]

# ── Hero card ─────────────────────────────────────────────────────────────────
hero_card = _card(dash, corner_radius=12)
hero_card.pack(fill="x", padx=20, pady=(18, 0))

hero_inner = ctk.CTkFrame(hero_card, fg_color="transparent")
hero_inner.pack(fill="x", padx=22, pady=18)

hero_text = ctk.CTkFrame(hero_inner, fg_color="transparent")
hero_text.pack(side="left", fill="x", expand=True)
ctk.CTkLabel(
    hero_text, text="Maintenance Dashboard",
    font=("Segoe UI", 20, "bold"), text_color=WHITE
).pack(anchor="w")
ctk.CTkLabel(
    hero_text,
    text="Live CMMS overview for the Water Bottle Production Line",
    font=("Segoe UI", 10),
    text_color=GRAY,
).pack(anchor="w", pady=(2, 0))

hero_right = ctk.CTkFrame(hero_inner, fg_color="transparent")
hero_right.pack(side="right", anchor="e")

hero_status = ctk.CTkLabel(
    hero_right, text="  ● IDLE  ",
    font=("Segoe UI", 10, "bold"),
    text_color=BG_DEEP, fg_color=AMBER,
    corner_radius=8, width=110, height=30,
)
hero_status.pack(anchor="e")

conn_lbl = ctk.CTkLabel(
    hero_right,
    text="⬡  SIMULATOR",
    font=("Segoe UI", 9),
    text_color=AMBER,
)
conn_lbl.pack(anchor="e", pady=(4, 0))

# ── Quick controls ─────────────────────────────────────────────────────────────
ctrl_row = ctk.CTkFrame(dash, fg_color="transparent")
ctrl_row.pack(fill="x", padx=20, pady=(12, 0))


def _qbtn(parent, text, color, cmd):
    return ctk.CTkButton(
        parent, text=text,
        font=("Segoe UI", 11, "bold"),
        fg_color=color, text_color=BG_DEEP, hover_color=color,
        corner_radius=6, height=34, command=cmd,
    )


def start_line():
    global auto_running
    line.start()
    auto_running = True
    _auto_produce()


def stop_line():
    global auto_running
    auto_running = False
    line.stop()


def reset_line():
    global auto_running
    auto_running = False
    line.reset()
    _fault_log_seen.clear()
    fault_box.configure(state="normal")
    fault_box.delete("0.0", "end")
    fault_box.configure(state="disabled")
    for s in STATIONS:
        station_data[s["key"]]["wear"]        = random.uniform(1.0, 6.0)
        station_data[s["key"]]["defect_rate"] = random.uniform(2.0, 8.0)
        station_data[s["key"]]["status"]      = "OK"


def do_maintenance():
    line.cmms.perform_maintenance()
    for s in STATIONS:
        station_data[s["key"]]["wear"]        = max(0.0, station_data[s["key"]]["wear"] - 4.0)
        station_data[s["key"]]["defect_rate"] = max(0.0, station_data[s["key"]]["defect_rate"] - 2.0)
    ts = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    _append_fault(ts, "Maintenance performed — health restored", ok=True)
    if INFLUX_AVAILABLE and _writer:
        try:
            _writer.write_cmms_event("maintenance", "Preventive Maintenance performed via CMMS dashboard")
        except Exception:
            pass


_qbtn(ctrl_row, "▶  START", GREEN, start_line).pack(side="left", padx=(0, 6))
_qbtn(ctrl_row, "■  STOP",  RED,   stop_line).pack(side="left", padx=(0, 6))
_qbtn(ctrl_row, "↺  RESET", AMBER, reset_line).pack(side="left", padx=(0, 6))

# ── KPI row ────────────────────────────────────────────────────────────────────
kpi_frame = ctk.CTkFrame(dash, fg_color="transparent")
kpi_frame.pack(fill="x", padx=20, pady=(14, 0))
for _i in range(5):
    kpi_frame.columnconfigure(_i, weight=1, uniform="kpi")

KPI_DEFS = [
    ("eq_health",    "EQUIPMENT HEALTH",   CYAN,      "%"),
    ("total",        "BOTTLES PRODUCED",   "#4FC3F7", "total components"),
    ("defective",    "REJECTED BOTTLES",   RED,       "rejected by QC"),
    ("work_orders",  "WORK ORDERS",        AMBER,     "open tickets"),
    ("maint_events", "MAINTENANCE EVENTS", GREEN,     "automatic CMMS events"),
]

kpi_vals: dict = {}

for _col, (_key, _title, _color, _sub) in enumerate(KPI_DEFS):
    _c = _card(kpi_frame)
    _c.grid(row=0, column=_col, sticky="ew", padx=4, pady=4)
    ctk.CTkFrame(_c, height=3, fg_color=_color, corner_radius=0).pack(fill="x")
    _inn = ctk.CTkFrame(_c, fg_color="transparent")
    _inn.pack(padx=16, pady=12, fill="x")
    ctk.CTkLabel(_inn, text=_title, font=("Segoe UI", 8, "bold"), text_color=GRAY).pack(anchor="w")
    _v = ctk.CTkLabel(_inn, text="—", font=("Segoe UI", 30, "bold"), text_color=_color)
    _v.pack(anchor="w", pady=(4, 0))
    ctk.CTkLabel(_inn, text=_sub, font=("Segoe UI", 9), text_color=GRAY).pack(anchor="w")
    kpi_vals[_key] = _v

# ── Machine Condition header ───────────────────────────────────────────────────
mc_hdr = ctk.CTkFrame(dash, fg_color="transparent")
mc_hdr.pack(fill="x", padx=20, pady=(22, 6))

ctk.CTkLabel(mc_hdr, text="Machine Condition",
    font=("Segoe UI", 14, "bold"), text_color=WHITE).pack(side="left")
ctk.CTkLabel(mc_hdr,
    text="  Station wear, defect rate, and live maintenance condition",
    font=("Segoe UI", 10), text_color=GRAY).pack(side="left")
ctk.CTkLabel(mc_hdr, text="View alerts →",
    font=("Segoe UI", 10), text_color=CYAN,
    cursor="hand2").pack(side="right")

# ── Station cards grid ─────────────────────────────────────────────────────────
mc_grid = ctk.CTkFrame(dash, fg_color="transparent")
mc_grid.pack(fill="x", padx=20)
for _i in range(5):
    mc_grid.columnconfigure(_i, weight=1, uniform="mc")

station_widgets: dict = {}

for _col, _st in enumerate(STATIONS):
    _key = _st["key"]
    _sc = ctk.CTkFrame(
        mc_grid, fg_color=BG_PANEL, corner_radius=10,
        border_width=1, border_color=GRAY_DIM,
    )
    _sc.grid(row=0, column=_col, sticky="nsew", padx=4, pady=4)

    _hrow = ctk.CTkFrame(_sc, fg_color="transparent")
    _hrow.pack(fill="x", padx=12, pady=(12, 4))
    ctk.CTkLabel(_hrow, text=_st["name"],
        font=("Segoe UI", 10, "bold"), text_color=WHITE).pack(side="left")
    _badge = ctk.CTkLabel(
        _hrow, text=" OK ",
        font=("Segoe UI", 8, "bold"), text_color=BG_DEEP,
        fg_color=GREEN, corner_radius=4, width=48,
    )
    _badge.pack(side="right")

    # Wear
    _wr = ctk.CTkFrame(_sc, fg_color="transparent")
    _wr.pack(fill="x", padx=12, pady=(8, 0))
    ctk.CTkLabel(_wr, text="Tool wear", font=("Segoe UI", 9), text_color=GRAY).pack(side="left")
    _wv = ctk.CTkLabel(_wr, text="—", font=("Segoe UI", 9, "bold"), text_color=WHITE)
    _wv.pack(side="right")
    _wb = ctk.CTkProgressBar(_sc, height=6, corner_radius=3, fg_color=GRAY_DIM, progress_color=GREEN)
    _wb.set(0)
    _wb.pack(fill="x", padx=12, pady=(3, 6))

    # Defect rate
    _dr = ctk.CTkFrame(_sc, fg_color="transparent")
    _dr.pack(fill="x", padx=12, pady=(2, 0))
    ctk.CTkLabel(_dr, text="Defect rate", font=("Segoe UI", 9), text_color=GRAY).pack(side="left")
    _dv = ctk.CTkLabel(_dr, text="—", font=("Segoe UI", 9, "bold"), text_color=WHITE)
    _dv.pack(side="right")
    _db = ctk.CTkProgressBar(_sc, height=6, corner_radius=3, fg_color=GRAY_DIM, progress_color=GREEN)
    _db.set(0)
    _db.pack(fill="x", padx=12, pady=(3, 12))

    station_widgets[_key] = {
        "card": _sc, "badge": _badge,
        "wear_val": _wv, "wear_bar": _wb,
        "def_val":  _dv, "def_bar":  _db,
    }

# ── Bottom row: schedule + fault log ──────────────────────────────────────────
bot = ctk.CTkFrame(dash, fg_color="transparent")
bot.pack(fill="x", padx=20, pady=(18, 20))
bot.columnconfigure(0, weight=1)
bot.columnconfigure(1, weight=1)

# Schedule card
sched_card = _card(bot)
sched_card.grid(row=0, column=0, sticky="nsew", padx=(0, 8))
ctk.CTkLabel(sched_card, text="Maintenance Schedule",
    font=("Segoe UI", 12, "bold"), text_color=WHITE).pack(anchor="w", padx=16, pady=(14, 6))

sched_body = ctk.CTkFrame(sched_card, fg_color="transparent")
sched_body.pack(fill="x", padx=16, pady=(0, 10))

sv_status  = _srow(sched_body, "Status")
sv_last    = _srow(sched_body, "Last Maintenance")
sv_next    = _srow(sched_body, "Next Scheduled")
sv_actions = _srow(sched_body, "Total Maintenance Actions")
sv_defects = _srow(sched_body, "Total Defects Recorded")

ctk.CTkButton(
    sched_card,
    text="⚙  Perform Maintenance",
    font=("Segoe UI", 11, "bold"),
    fg_color=CYAN, text_color=BG_DEEP, hover_color=CYAN_DIM,
    corner_radius=6, height=36,
    command=do_maintenance,
).pack(fill="x", padx=16, pady=(0, 14))

# Fault log card
fault_card = _card(bot)
fault_card.grid(row=0, column=1, sticky="nsew", padx=(8, 0))
ctk.CTkLabel(fault_card, text="Recent Faults & Events",
    font=("Segoe UI", 12, "bold"), text_color=WHITE).pack(anchor="w", padx=16, pady=(14, 6))

fault_box = ctk.CTkTextbox(
    fault_card, fg_color=BG_MID, text_color=WHITE,
    font=("Consolas", 10), corner_radius=6, wrap="word",
    state="disabled", height=200,
)
fault_box.pack(fill="both", expand=True, padx=16, pady=(0, 14))
fault_box._textbox.tag_config("fault", foreground=RED)
fault_box._textbox.tag_config("ts",    foreground=GRAY)
fault_box._textbox.tag_config("ok",    foreground=GREEN)
fault_box._textbox.tag_config("warn",  foreground=AMBER)


def _append_fault(ts: str, msg: str, ok: bool = False, warn: bool = False):
    fault_box.configure(state="normal")
    fault_box._textbox.insert("end", f"[{ts}]  ", "ts")
    tag = "ok" if ok else ("warn" if warn else "fault")
    fault_box._textbox.insert("end", msg + "\n", tag)
    fault_box.configure(state="disabled")
    fault_box._textbox.see("end")


# ══════════════════════════════════════════════════════════════════════════════
# WORK ORDERS PAGE
# ══════════════════════════════════════════════════════════════════════════════
wo_page = _pages["Work Orders"]

# ── Header ────────────────────────────────────────────────────────────────────
wo_hdr = ctk.CTkFrame(wo_page, fg_color="transparent")
wo_hdr.pack(fill="x", padx=20, pady=(20, 2))
ctk.CTkLabel(wo_hdr, text="Work Orders",
    font=("Segoe UI", 18, "bold"), text_color=WHITE).pack(side="left")
wo_count_lbl = ctk.CTkLabel(wo_hdr, text="",
    font=("Segoe UI", 10), text_color=GRAY)
wo_count_lbl.pack(side="left", padx=10)

ctk.CTkLabel(wo_page,
    text="System-generated and manually created maintenance work orders",
    font=("Segoe UI", 10), text_color=GRAY).pack(anchor="w", padx=20, pady=(0, 12))

# ── Create Work Order form ────────────────────────────────────────────────────
wo_form = _card(wo_page, corner_radius=10)
wo_form.pack(fill="x", padx=20, pady=(0, 12))

ctk.CTkLabel(wo_form, text="Create New Work Order",
    font=("Segoe UI", 11, "bold"), text_color=WHITE).pack(anchor="w", padx=16, pady=(12, 6))

wo_form_inner = ctk.CTkFrame(wo_form, fg_color="transparent")
wo_form_inner.pack(fill="x", padx=16, pady=(0, 12))
wo_form_inner.columnconfigure(0, weight=1)
wo_form_inner.columnconfigure(1, weight=0)
wo_form_inner.columnconfigure(2, weight=0)

wo_entry = ctk.CTkEntry(
    wo_form_inner,
    placeholder_text="Describe the issue...",
    font=("Segoe UI", 11),
    fg_color=BG_MID, text_color=WHITE,
    border_color=GRAY_DIM, corner_radius=6, height=36,
)
wo_entry.grid(row=0, column=0, sticky="ew", padx=(0, 8))

wo_priority = ctk.CTkOptionMenu(
    wo_form_inner,
    values=["Low", "Medium", "High", "Critical"],
    font=("Segoe UI", 10),
    fg_color=BG_MID, button_color=GRAY_DIM,
    text_color=WHITE, corner_radius=6, height=36, width=110,
)
wo_priority.set("Medium")
wo_priority.grid(row=0, column=1, padx=(0, 8))

wo_submit_btn = ctk.CTkButton(
    wo_form_inner, text="+ Create",
    font=("Segoe UI", 10, "bold"),
    fg_color=CYAN, text_color=BG_DEEP, hover_color=CYAN_DIM,
    corner_radius=6, height=36, width=90,
)
wo_submit_btn.grid(row=0, column=2)

# ── Work order list ───────────────────────────────────────────────────────────
wo_list = ctk.CTkFrame(wo_page, fg_color="transparent")
wo_list.pack(fill="x", padx=20)


def _create_work_order():
    issue = wo_entry.get().strip()
    if not issue:
        wo_entry.configure(border_color=RED)
        root.after(1500, lambda: wo_entry.configure(border_color=GRAY_DIM))
        return

    priority = wo_priority.get()
    ts = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    wo_id = len(_manual_work_orders) + 1

    wo = {
        "id":       f"M-{wo_id:03d}",
        "issue":    f"[{priority}] {issue}",
        "status":   "OPEN",
        "date":     ts,
        "source":   "manual",
        "priority": priority,
    }
    _manual_work_orders.append(wo)

    if INFLUX_AVAILABLE and _writer:
        try:
            _writer.write_cmms_event(
                "work_order", f"[{priority}] {issue}"
            )
        except Exception:
            pass

    wo_entry.delete(0, "end")
    _append_fault(ts, f"Work order created: [{priority}] {issue}", warn=True)
    _refresh_wo()


wo_submit_btn.configure(command=_create_work_order)


def _render_wo_card(parent, wo, border=GRAY_DIM):
    c = ctk.CTkFrame(parent, fg_color=BG_PANEL, corner_radius=8,
        border_width=1, border_color=border)
    c.pack(fill="x", pady=4)
    top = ctk.CTkFrame(c, fg_color="transparent")
    top.pack(fill="x", padx=14, pady=(10, 4))
    ctk.CTkLabel(top, text=str(wo["id"]),
        font=("Segoe UI", 10, "bold"), text_color=CYAN).pack(side="left")
    sc = GREEN if wo["status"] == "CLOSED" else AMBER
    ctk.CTkLabel(top, text=f" {wo['status']} ",
        font=("Segoe UI", 8, "bold"), text_color=BG_DEEP,
        fg_color=sc, corner_radius=4).pack(side="right")
    src_col = CYAN if wo.get("source") == "auto" else GRAY
    ctk.CTkLabel(top, text=wo.get("source", "manual").upper(),
        font=("Segoe UI", 8), text_color=src_col).pack(side="right", padx=(0, 8))
    ctk.CTkLabel(c, text=wo["issue"],
        font=("Segoe UI", 10), text_color=WHITE, anchor="w").pack(anchor="w", padx=14, pady=(0, 2))
    ctk.CTkLabel(c, text=wo["date"],
        font=("Segoe UI", 9), text_color=GRAY, anchor="w").pack(anchor="w", padx=14, pady=(0, 8))


def _refresh_wo():
    for w in wo_list.winfo_children():
        w.destroy()

    # Auto-generated work orders from InfluxDB fault events
    auto_orders = []
    if INFLUX_AVAILABLE and _reader:
        for ev in _last_fault_events:
            if ev.get("event_type") == "fault":
                auto_orders.append({
                    "id":     "AUTO",
                    "issue":  ev["message"],
                    "status": "OPEN",
                    "date":   ev["time"],
                    "source": "auto",
                })

    all_orders = list(reversed(_manual_work_orders)) + auto_orders

    wo_count_lbl.configure(text=f"({len(all_orders)} total)")

    if not all_orders:
        ctk.CTkLabel(wo_list, text="No work orders yet. Create one above or run production to generate faults.",
            font=("Segoe UI", 11), text_color=GRAY, wraplength=700).pack(pady=30)
        return

    for wo in all_orders:
        border = RED if wo.get("source") == "auto" else GRAY_DIM
        _render_wo_card(wo_list, wo, border=border)


# ══════════════════════════════════════════════════════════════════════════════
# MAINTENANCE PAGE
# ══════════════════════════════════════════════════════════════════════════════
maint_page = _pages["Maintenance"]
ctk.CTkLabel(maint_page, text="Maintenance History",
    font=("Segoe UI", 18, "bold"), text_color=WHITE).pack(anchor="w", padx=20, pady=(20, 2))
ctk.CTkLabel(maint_page,
    text="Complete record of all preventive and corrective maintenance events",
    font=("Segoe UI", 10), text_color=GRAY).pack(anchor="w", padx=20, pady=(0, 12))

mh_list = ctk.CTkFrame(maint_page, fg_color="transparent")
mh_list.pack(fill="x", padx=20)


def _refresh_maint():
    for w in mh_list.winfo_children():
        w.destroy()

    # Build unified history: InfluxDB events + local cmms history
    records = []

    if INFLUX_AVAILABLE:
        for ev in _last_fault_events:
            if ev.get("event_type") == "maintenance":
                records.append({
                    "date":   ev["time"],
                    "action": ev["message"],
                    "source": "HMI / CMMS",
                })
    else:
        for rec in line.cmms.maintenance_history:
            records.append({
                "date":   rec["date"],
                "action": rec["action"],
                "source": "local",
            })

    if not records:
        src = "InfluxDB" if INFLUX_AVAILABLE else "simulator"
        ctk.CTkLabel(mh_list,
            text=f"No maintenance records yet  [{src}]",
            font=("Segoe UI", 11), text_color=GRAY).pack(pady=30)
        return

    for rec in records:
        c = _card(mh_list, corner_radius=8)
        c.pack(fill="x", pady=4)
        row = ctk.CTkFrame(c, fg_color="transparent")
        row.pack(fill="x", padx=14, pady=10)
        ctk.CTkLabel(row, text=rec["action"],
            font=("Segoe UI", 10, "bold"), text_color=CYAN).pack(side="left")
        right = ctk.CTkFrame(row, fg_color="transparent")
        right.pack(side="right")
        ctk.CTkLabel(right, text=rec["date"],
            font=("Segoe UI", 9), text_color=GRAY).pack(anchor="e")
        ctk.CTkLabel(right, text=rec["source"],
            font=("Segoe UI", 8), text_color=GRAY_DIM).pack(anchor="e")


# ══════════════════════════════════════════════════════════════════════════════
# ALERTS PAGE
# ══════════════════════════════════════════════════════════════════════════════
al_page = _pages["Alerts"]
ctk.CTkLabel(al_page, text="Active Alerts",
    font=("Segoe UI", 18, "bold"), text_color=WHITE).pack(anchor="w", padx=20, pady=(20, 2))
ctk.CTkLabel(al_page,
    text="Live alerts and warnings from all monitored stations",
    font=("Segoe UI", 10), text_color=GRAY).pack(anchor="w", padx=20, pady=(0, 12))

al_list = ctk.CTkFrame(al_page, fg_color="transparent")
al_list.pack(fill="x", padx=20)


def _refresh_alerts():
    for w in al_list.winfo_children():
        w.destroy()

    alerts = []

    if INFLUX_AVAILABLE:
        # Derive alerts from the latest InfluxDB snapshot
        if _last_health < 50:
            alerts.append(("CRITICAL: Equipment health critically low"
                           f" ({_last_health:.0f}%)", RED))
        elif _last_health < 70:
            alerts.append((f"WARNING: Equipment health low ({_last_health:.0f}%)", AMBER))

        if _last_maint_status == "FAULT":
            alerts.append(("FAULT: Machine fault detected — maintenance required", RED))
        elif _last_maint_status == "DUE":
            alerts.append(("Maintenance overdue — schedule service immediately", AMBER))
        elif _last_maint_status == "WARNING":
            alerts.append(("Maintenance approaching — plan service soon", AMBER))

        # Recent faults from InfluxDB as active alerts
        for ev in _last_fault_events[:5]:
            if ev.get("event_type") == "fault":
                alerts.append((f"FAULT at {ev['time']}: {ev['message']}", RED))
    else:
        # Fallback: local simulator alerts
        for a in line.cmms.get_alerts():
            alerts.append((a, AMBER))

    if not alerts:
        c = _card(al_list, corner_radius=8)
        c.pack(fill="x", pady=4)
        src = "InfluxDB" if INFLUX_AVAILABLE else "simulator"
        ctk.CTkLabel(c,
            text=f"No active alerts — all systems nominal  [{src}]",
            font=("Segoe UI", 11), text_color=GREEN).pack(pady=18)
        return

    for text, color in alerts:
        bg = "#140508" if color == RED else "#1A1200"
        border = color
        c = ctk.CTkFrame(al_list, fg_color=bg,
            corner_radius=8, border_width=1, border_color=border)
        c.pack(fill="x", pady=4)
        row = ctk.CTkFrame(c, fg_color="transparent")
        row.pack(fill="x", padx=14, pady=12)
        ctk.CTkLabel(row, text="  " + text,
            font=("Segoe UI", 10, "bold"), text_color=color).pack(side="left")
        ctk.CTkLabel(row, text=datetime.now().strftime("%H:%M:%S"),
            font=("Segoe UI", 9), text_color=GRAY).pack(side="right")


# ══════════════════════════════════════════════════════════════════════════════
# AUTO PRODUCE
# ══════════════════════════════════════════════════════════════════════════════

def _auto_produce():
    if auto_running and line.machine_state == "RUNNING":
        line.process_bottle()
        root.after(950, _auto_produce)


# ══════════════════════════════════════════════════════════════════════════════
# UPDATE STATION WEAR
# ══════════════════════════════════════════════════════════════════════════════

def _update_station_wear():
    if line.machine_state != "RUNNING":
        return
    for s in STATIONS:
        d = station_data[s["key"]]
        d["wear"]        = min(100.0, d["wear"]        + random.uniform(0.0, 0.07))
        d["defect_rate"] = min(100.0, max(0.0, d["defect_rate"] + random.uniform(-0.08, 0.13)))
        if d["wear"] > 15 or d["defect_rate"] > 15:
            d["status"] = "FAULT"
        elif d["wear"] > 8 or d["defect_rate"] > 10:
            d["status"] = "WATCH"
        else:
            d["status"] = "OK"


# ══════════════════════════════════════════════════════════════════════════════
# MAIN UPDATE LOOP
# ══════════════════════════════════════════════════════════════════════════════

_STATUS_CODE_MAP = {0: "NORMAL", 1: "WARNING", 2: "DUE", 3: "FAULT"}


def update_ui():
    global INFLUX_AVAILABLE, _hmi_state
    global _last_health, _last_maint_status, _last_work_orders, _last_fault_events
    try:
        _update_loop_body()
    except Exception as e:
        print(f"[CMMS] update_ui error: {e}")
    finally:
        root.after(2000, update_ui)


def _update_loop_body():
    global INFLUX_AVAILABLE, _hmi_state
    global _last_health, _last_maint_status, _last_work_orders, _last_fault_events

    _update_station_wear()

    # ── Pull data: InfluxDB first, simulator fallback ──────────────────────────
    if _reader is not None:
        prod_data   = _reader.get_latest_production()
        health_data = _reader.get_latest_cmms_health()
        INFLUX_AVAILABLE = _reader.available
    else:
        prod_data = health_data = {}
        INFLUX_AVAILABLE = False

    cmms = line.cmms  # local simulator always available for dates

    if INFLUX_AVAILABLE and prod_data:
        health       = float(health_data.get("equipment_health",          cmms.equipment_health) or 100.0)
        total        = int(prod_data.get(  "bottles_produced",            line.total_bottles)   or 0)
        defv         = int(prod_data.get(  "defective_bottles",           line.defective_bottles) or 0)
        work_orders  = int(health_data.get("work_orders_open",            len(cmms.work_orders)) or 0)
        maint_events = int(health_data.get("total_maintenance_actions",   cmms.total_maintenance_actions) or 0)
        maint_status = _STATUS_CODE_MAP.get(
            int(health_data.get("maintenance_status_code", 0) or 0),
            cmms.maintenance_status
        )
        _hmi_state   = prod_data.get("machine_state", "IDLE")
        conn_text    = "LIVE  |  InfluxDB"
        conn_color   = GREEN
        # Pull events for alerts and maintenance history
        _last_fault_events = _reader.get_recent_events(limit=40)
    else:
        health       = cmms.equipment_health
        total        = line.total_bottles
        defv         = line.defective_bottles
        work_orders  = len(cmms.work_orders)
        maint_events = cmms.total_maintenance_actions
        maint_status = cmms.maintenance_status
        _hmi_state   = "IDLE"
        conn_text    = "SIMULATOR  (InfluxDB offline)"
        conn_color   = AMBER
        _last_fault_events = []

    # Update shared state for alerts / work orders / maintenance pages
    _last_health       = health
    _last_maint_status = maint_status
    _last_work_orders  = work_orders

    # ── Connection indicator ───────────────────────────────────────────────────
    conn_lbl.configure(text=conn_text, text_color=conn_color)

    # ── Status pills — use InfluxDB state when available ──────────────────────
    state = _hmi_state  # populated from InfluxDB; "IDLE" when offline
    sc = GREEN if state == "RUNNING" else (RED if state == "STOPPED" else AMBER)
    status_pill.configure(text=f"  ● {state}  ", fg_color=sc)
    hero_status.configure(text=f"  ● {state}  ", fg_color=sc)

    # ── KPI cards ─────────────────────────────────────────────────────────────
    kpi_vals["eq_health"].configure(text=f"{health:.0f}")
    kpi_vals["total"].configure(text=str(total))
    kpi_vals["defective"].configure(text=str(defv))
    kpi_vals["work_orders"].configure(text=str(work_orders))
    kpi_vals["maint_events"].configure(text=str(maint_events))

    # ── Schedule card (dates always from local cmms) ───────────────────────────
    sc_col = GREEN if maint_status == "NORMAL" else (AMBER if maint_status == "WARNING" else RED)
    sv_status.configure(text=maint_status, text_color=sc_col)
    sv_last.configure(text=cmms.last_maintenance_date.strftime("%Y-%m-%d  %H:%M"))
    sv_next.configure(text=cmms.next_maintenance_date.strftime("%Y-%m-%d"))
    sv_actions.configure(text=str(maint_events))
    sv_defects.configure(text=str(defv))

    # ── Station cards + push metrics to InfluxDB for Grafana ──────────────────
    for s in STATIONS:
        k = s["key"]
        d = station_data[k]
        w = station_widgets[k]
        status = d["status"]

        if INFLUX_AVAILABLE and _writer and state == "RUNNING":
            try:
                _writer.write_station_metrics(
                    s["name"], d["wear"], d["defect_rate"], status
                )
            except Exception:
                pass

        badge_col = _status_color(status)
        w["badge"].configure(text=f" {status} ", fg_color=badge_col)

        wear_col = GREEN if d["wear"] < 8 else (AMBER if d["wear"] < 15 else RED)
        w["wear_val"].configure(text=f'{d["wear"]:.2f}%')
        w["wear_bar"].configure(progress_color=wear_col)
        w["wear_bar"].set(min(1.0, d["wear"] / 100))

        def_col = GREEN if d["defect_rate"] < 8 else (AMBER if d["defect_rate"] < 15 else RED)
        w["def_val"].configure(text=f'{d["defect_rate"]:.1f}%')
        w["def_bar"].configure(progress_color=def_col)
        w["def_bar"].set(min(1.0, d["defect_rate"] / 100))

        if status == "FAULT":
            w["card"].configure(border_color=RED, border_width=2)
        elif status == "WATCH":
            w["card"].configure(border_color=AMBER, border_width=2)
        else:
            w["card"].configure(border_color=GRAY_DIM, border_width=1)

    # ── Fault / event log — reuse events already fetched above ───────────────
    if INFLUX_AVAILABLE and _last_fault_events:
        for ev in reversed(_last_fault_events):
            key = (ev["time"], ev["message"])
            if key not in _fault_log_seen:
                _fault_log_seen.add(key)
                _append_fault(
                    ev["time"], ev["message"],
                    ok=(ev["event_type"] == "maintenance"),
                    warn=(ev["event_type"] == "alarm"),
                )
    else:
        for fault in cmms.fault_history:
            key = (fault["date"], fault["fault"])
            if key not in _fault_log_seen:
                _fault_log_seen.add(key)
                _append_fault(fault["date"], fault["fault"])

    # ── Sub-page lists — only refresh the currently visible tab ───────────────
    # winfo_ismapped() returns True only when the frame is packed and shown.
    # This stops the destroy+recreate cycle on hidden tabs, eliminating flashing.
    if _pages["Work Orders"].winfo_ismapped():
        _refresh_wo()
    if _pages["Maintenance"].winfo_ismapped():
        _refresh_maint()
    if _pages["Alerts"].winfo_ismapped():
        _refresh_alerts()


# ══════════════════════════════════════════════════════════════════════════════
# CLOCK
# ══════════════════════════════════════════════════════════════════════════════

def _tick():
    clock_lbl.configure(text=datetime.now().strftime("%a %Y-%m-%d  %H:%M:%S"))
    root.after(1000, _tick)


_tick()

# ── Boot ──────────────────────────────────────────────────────────────────────
if SIMULATION_MODE:
    _append_fault(
        datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "production_line.py not found — running built-in simulator",
        warn=True,
    )

update_ui()
root.mainloop()

#change commit