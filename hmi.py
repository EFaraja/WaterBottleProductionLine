import customtkinter as ctk
import tkinter as tk
from tkinter import Canvas
import matplotlib
matplotlib.use("TkAgg")
from matplotlib.figure import Figure
from matplotlib.backends.backend_tkagg import FigureCanvasTkAgg
import matplotlib.pyplot as plt
import matplotlib.patches as mpatches
from datetime import datetime, timedelta
import random
import math

# ──────────────────────────────────────────────
# ATTEMPT TO IMPORT PRODUCTION LINE
# Falls back to a built-in simulator if not found
# ──────────────────────────────────────────────
try:
    from production_line import ProductionLine
    line = ProductionLine()
    SIMULATION_MODE = False
except ImportError:
    SIMULATION_MODE = True

    class FakeCMMS:
        def __init__(self):
            self.equipment_health = 95
            self.maintenance_status = "NORMAL"
            self.last_maintenance_date = datetime.now() - timedelta(days=5)
            self.next_maintenance_date = datetime.now() + timedelta(days=25)
            self.work_orders = []
            self._alerts = []

        def get_alerts(self):
            return self._alerts

        def perform_maintenance(self):
            self.equipment_health = 100
            self.maintenance_status = "NORMAL"
            self.last_maintenance_date = datetime.now()
            self.next_maintenance_date = datetime.now() + timedelta(days=30)
            self._alerts = []

    class FakeBottle:
        _id_counter = 0

        def __init__(self):
            FakeBottle._id_counter += 1
            self.id = FakeBottle._id_counter
            self.defective = random.random() < 0.08
            self.defect_reason = random.choice([
                "Cap misalign", "Underfill", "Label error", "Seal breach"
            ]) if self.defective else None

    class FakeProductionLine:
        STAGES = ["Bottle Supply", "Water Filling", "Capping", "Branding", "Quality Control"]

        def __init__(self):
            self.machine_state = "STOPPED"
            self.current_stage = "IDLE"
            self._stage_idx = 0
            self.total_bottles = 0
            self.good_bottles = 0
            self.defective_bottles = 0
            self.last_error = "NONE"
            self.cmms = FakeCMMS()
            self.water_level = 85.0

        def start(self):
            self.machine_state = "RUNNING"
            self.current_stage = self.STAGES[0]

        def stop(self):
            self.machine_state = "STOPPED"
            self.current_stage = "IDLE"

        def reset(self):
            self.machine_state = "STOPPED"
            self.current_stage = "IDLE"
            self.total_bottles = 0
            self.good_bottles = 0
            self.defective_bottles = 0
            self.last_error = "NONE"
            FakeBottle._id_counter = 0

        def process_bottle(self):
            if self.machine_state != "RUNNING":
                return None
            self._stage_idx = (self._stage_idx + 1) % len(self.STAGES)
            self.current_stage = self.STAGES[self._stage_idx]

            # Degrade health slowly
            self.cmms.equipment_health = max(
                20, self.cmms.equipment_health - random.uniform(0.1, 0.4)
            )
            if self.cmms.equipment_health < 60:
                self.cmms.maintenance_status = "DUE"
                if "Health critical" not in self.cmms._alerts:
                    self.cmms._alerts.append("Health critical")
            elif self.cmms.equipment_health < 80:
                self.cmms.maintenance_status = "WARNING"

            # Water level fluctuates
            self.water_level = max(
                5, min(100, self.water_level - random.uniform(0.2, 0.8))
            )

            bottle = FakeBottle()
            self.total_bottles += 1
            if bottle.defective:
                self.defective_bottles += 1
                self.last_error = bottle.defect_reason
            else:
                self.good_bottles += 1
            return bottle

    line = FakeProductionLine()

# ──────────────────────────────────────────────
# THEME TOKENS
# ──────────────────────────────────────────────
BG_DEEP      = "#060D1A"
BG_MID       = "#0B1628"
BG_PANEL     = "#0F1E33"
BG_CARD      = "#132340"
BG_CARD2     = "#172944"

CYAN         = "#00D9FF"
CYAN_DIM     = "#0090AA"
CYAN_GLOW    = "#00AACC"
BLUE_ACCENT  = "#1565C0"
BLUE_BRIGHT  = "#2196F3"

GREEN        = "#00E676"
GREEN_DIM    = "#009B50"
AMBER        = "#FFB300"
RED          = "#FF1744"
RED_DIM      = "#B71C1C"

WHITE        = "#E8F4FF"
GRAY_LIGHT   = "#8AAABB"
GRAY_MID     = "#3D5566"

FONT_DISPLAY = ("Segoe UI", 32, "bold")
FONT_HEAD    = ("Segoe UI", 13, "bold")
FONT_BODY    = ("Segoe UI", 11)
FONT_SMALL   = ("Segoe UI", 10)
FONT_MONO    = ("Consolas", 11)
FONT_KPI_BIG = ("Segoe UI", 28, "bold")
FONT_KPI_SUB = ("Segoe UI", 10)

# CTk appearance
ctk.set_appearance_mode("dark")
ctk.set_default_color_theme("blue")

# ──────────────────────────────────────────────
# STATE
# ──────────────────────────────────────────────
auto_running = False
production_history = []   # list of (time_str, total, good, defective)
alarm_log = []            # list of (timestamp, message, level)
_anim_stage_idx = -1

# ──────────────────────────────────────────────
# ROOT WINDOW
# ──────────────────────────────────────────────
root = ctk.CTk()
root.title("Water Bottle Production Line  |  SCADA HMI  v2.0")
root.geometry("1520x960")
root.minsize(1200, 800)
root.configure(fg_color=BG_DEEP)

# ══════════════════════════════════════════════
# HELPER WIDGETS
# ══════════════════════════════════════════════

def make_card(parent, **kwargs):
    """Flat card with panel background."""
    defaults = dict(fg_color=BG_CARD, corner_radius=10)
    defaults.update(kwargs)
    return ctk.CTkFrame(parent, **defaults)


def label(parent, text, font=FONT_BODY, color=WHITE, **kwargs):
    return ctk.CTkLabel(parent, text=text, font=font, text_color=color, **kwargs)


def section_title(parent, text):
    f = ctk.CTkFrame(parent, fg_color="transparent")
    f.pack(fill="x", padx=14, pady=(10, 4))
    ctk.CTkLabel(
        f, text="◆  " + text,
        font=("Segoe UI", 11, "bold"),
        text_color=CYAN
    ).pack(side="left")
    ctk.CTkFrame(f, height=1, fg_color=CYAN_DIM).pack(
        side="left", fill="x", expand=True, padx=(8, 0), pady=6
    )
    return f

# ══════════════════════════════════════════════
# TITLE BAR
# ══════════════════════════════════════════════
title_bar = ctk.CTkFrame(root, fg_color=BG_MID, corner_radius=0, height=58)
title_bar.pack(fill="x", side="top")
title_bar.pack_propagate(False)

ctk.CTkLabel(
    title_bar,
    text="⬡  WATER BOTTLE PRODUCTION LINE  — HMI",
    font=("Segoe UI", 16, "bold"),
    text_color=CYAN
).pack(side="left", padx=22, pady=12)

clock_label = ctk.CTkLabel(
    title_bar, text="", font=FONT_MONO, text_color=GRAY_LIGHT
)
clock_label.pack(side="right", padx=22)

status_pill = ctk.CTkLabel(
    title_bar,
    text="  ● IDLE  ",
    font=("Segoe UI", 11, "bold"),
    text_color=BG_DEEP,
    fg_color=AMBER,
    corner_radius=8,
    width=90, height=26
)
status_pill.pack(side="right", padx=10, pady=14)

# ══════════════════════════════════════════════
# MAIN LAYOUT  (left column | center column | right column)
# ══════════════════════════════════════════════
main = ctk.CTkFrame(root, fg_color="transparent")
main.pack(fill="both", expand=True, padx=10, pady=8)
main.columnconfigure(0, weight=0, minsize=220)
main.columnconfigure(1, weight=1)
main.columnconfigure(2, weight=0, minsize=280)
main.rowconfigure(0, weight=1)

# ─────────────────────────────────────
# LEFT COLUMN
# ─────────────────────────────────────
left_col = ctk.CTkFrame(main, fg_color="transparent")
left_col.grid(row=0, column=0, sticky="nsew", padx=(0, 8))

# ── Control Panel ──
ctrl_card = make_card(left_col)
ctrl_card.pack(fill="x", pady=(0, 8))
section_title(ctrl_card, "MACHINE CONTROL")

def _btn(parent, text, color, cmd):
    return ctk.CTkButton(
        parent, text=text, fg_color=color, hover_color=color,
        text_color=BG_DEEP, font=("Segoe UI", 12, "bold"),
        corner_radius=6, height=38, command=cmd
    )

btn_frame = ctk.CTkFrame(ctrl_card, fg_color="transparent")
btn_frame.pack(fill="x", padx=14, pady=(4, 10))

start_btn = _btn(btn_frame, "▶  START",    GREEN,  lambda: start_machine())
stop_btn  = _btn(btn_frame, "■  STOP",     RED,    lambda: stop_machine())
reset_btn = _btn(btn_frame, "↺  RESET",    AMBER,  lambda: reset_machine())
maint_btn = _btn(btn_frame, "⚙  MAINT.",   CYAN,   lambda: do_maintenance())

for b in [start_btn, stop_btn, reset_btn, maint_btn]:
    b.pack(fill="x", pady=3)

# ── Machine Info ──
minfo_card = make_card(left_col)
minfo_card.pack(fill="x", pady=(0, 8))
section_title(minfo_card, "MACHINE INFO")

rows_info = ctk.CTkFrame(minfo_card, fg_color="transparent")
rows_info.pack(fill="x", padx=14, pady=(0, 10))

def info_row(parent, key):
    f = ctk.CTkFrame(parent, fg_color="transparent")
    f.pack(fill="x", pady=2)
    ctk.CTkLabel(f, text=key, font=FONT_SMALL, text_color=GRAY_LIGHT, anchor="w").pack(side="left")
    val = ctk.CTkLabel(f, text="—", font=FONT_SMALL, text_color=WHITE, anchor="e")
    val.pack(side="right")
    return val

v_state  = info_row(rows_info, "State")
v_stage  = info_row(rows_info, "Stage")
v_err    = info_row(rows_info, "Last Error")

# ── Water Tank Gauge ──
tank_card = make_card(left_col)
tank_card.pack(fill="x", pady=(0, 8))
section_title(tank_card, "WATER TANK")

tank_canvas = Canvas(
    tank_card, width=180, height=170,
    bg=BG_CARD, highlightthickness=0
)
tank_canvas.pack(pady=6)

def draw_tank(level_pct):
    tank_canvas.delete("all")
    W, H = 180, 170
    tx, ty, tw, th = 55, 20, 70, 120

    # Outer shell
    tank_canvas.create_rectangle(tx, ty, tx+tw, ty+th,
        outline=CYAN_DIM, width=2, fill=BG_MID)

    # Water fill
    fill_h = int(th * level_pct / 100)
    fill_y = ty + th - fill_h
    if level_pct < 20:
        water_col = RED_DIM
    elif level_pct < 50:
        water_col = AMBER
    else:
        water_col = "#0D47A1"
    tank_canvas.create_rectangle(tx+2, fill_y, tx+tw-2, ty+th-2,
        fill=water_col, outline="")

    # Shimmer lines
    for i in range(3):
        yy = fill_y + 8 + i * 14
        if yy < ty + th - 4:
            tank_canvas.create_line(tx+8, yy, tx+tw-8, yy,
                fill="#1565C0", width=1, dash=(4, 3))

    # Border again (over fill)
    tank_canvas.create_rectangle(tx, ty, tx+tw, ty+th,
        outline=CYAN_DIM, width=2, fill="")

    # Percentage text
    tank_canvas.create_text(
        tx + tw//2, ty + th//2,
        text=f"{level_pct:.0f}%",
        fill=WHITE, font=("Segoe UI", 14, "bold")
    )

    # Label
    tank_canvas.create_text(W//2, ty + th + 16,
        text="Fill Level", fill=GRAY_LIGHT, font=("Segoe UI", 10))

    # Danger zone line at 20%
    dz_y = ty + th - int(th * 0.20)
    tank_canvas.create_line(tx, dz_y, tx+tw, dz_y,
        fill=RED, width=1, dash=(3, 3))

draw_tank(85)

# ── Equipment Health Gauge ──
health_card = make_card(left_col)
health_card.pack(fill="x", pady=(0, 8))
section_title(health_card, "EQUIPMENT HEALTH")

health_canvas = Canvas(
    health_card, width=180, height=130,
    bg=BG_CARD, highlightthickness=0
)
health_canvas.pack(pady=4)

def draw_arc_gauge(canvas, value, max_val=100):
    canvas.delete("all")
    W, H = 180, 130
    cx, cy, r = W // 2, H - 20, 80
    start_a, end_a = 210, -30   # degrees (tkinter: counter-clockwise)
    span = 240

    pct = value / max_val
    if pct > 0.7:
        needle_col = GREEN
    elif pct > 0.4:
        needle_col = AMBER
    else:
        needle_col = RED

    # Track arc (background)
    canvas.create_arc(
        cx-r, cy-r, cx+r, cy+r,
        start=start_a, extent=-span,
        style="arc", outline=GRAY_MID, width=14
    )
    # Fill arc
    fill_extent = span * pct
    canvas.create_arc(
        cx-r, cy-r, cx+r, cy+r,
        start=start_a, extent=-fill_extent,
        style="arc", outline=needle_col, width=14
    )

    # Ticks
    for i in range(6):
        angle = math.radians(start_a - i * (span / 5))
        x1 = cx + (r - 20) * math.cos(angle)
        y1 = cy - (r - 20) * math.sin(angle)
        x2 = cx + (r - 8)  * math.cos(angle)
        y2 = cy - (r - 8)  * math.sin(angle)
        canvas.create_line(x1, y1, x2, y2, fill=GRAY_MID, width=1)

    # Value text
    canvas.create_text(
        cx, cy - 20,
        text=f"{value:.0f}%",
        fill=needle_col, font=("Segoe UI", 18, "bold")
    )
    canvas.create_text(
        cx, cy - 2,
        text="Health",
        fill=GRAY_LIGHT, font=("Segoe UI", 9)
    )

draw_arc_gauge(health_canvas, 95)

# ─────────────────────────────────────
# CENTER COLUMN
# ─────────────────────────────────────
center_col = ctk.CTkFrame(main, fg_color="transparent")
center_col.grid(row=0, column=1, sticky="nsew", padx=(0, 8))
center_col.columnconfigure(0, weight=1)
center_col.rowconfigure(2, weight=1)

# ── KPI ROW ──
kpi_row = ctk.CTkFrame(center_col, fg_color="transparent")
kpi_row.grid(row=0, column=0, sticky="ew", pady=(0, 8))
for i in range(4):
    kpi_row.columnconfigure(i, weight=1, uniform="kpi")

KPI_DEFS = [
    ("total_bottles",  "TOTAL BOTTLES",       CYAN,  "⬡"),
    ("good_bottles",   "GOOD BOTTLES",         GREEN, "✔"),
    ("defective_bottles", "DEFECTIVE",         RED,   "✘"),
    ("efficiency",     "EFFICIENCY",           AMBER, "%"),
]

kpi_value_labels = {}

for col, (key, title, color, icon) in enumerate(KPI_DEFS):
    card = ctk.CTkFrame(kpi_row, fg_color=BG_CARD, corner_radius=10)
    card.grid(row=0, column=col, sticky="ew", padx=4)

    # Top accent strip
    ctk.CTkFrame(card, height=3, fg_color=color, corner_radius=0).pack(fill="x")

    inner = ctk.CTkFrame(card, fg_color="transparent")
    inner.pack(fill="both", padx=14, pady=10)

    ctk.CTkLabel(inner, text=f"{icon}  {title}",
        font=("Segoe UI", 9, "bold"), text_color=GRAY_LIGHT).pack(anchor="w")

    val_lbl = ctk.CTkLabel(inner, text="0",
        font=("Segoe UI", 30, "bold"), text_color=color)
    val_lbl.pack(anchor="w", pady=(2, 0))

    sub_lbl = ctk.CTkLabel(inner, text="units", font=FONT_KPI_SUB, text_color=GRAY_LIGHT)
    sub_lbl.pack(anchor="w")

    kpi_value_labels[key] = (val_lbl, sub_lbl, color)

# ── PRODUCTION FLOW ──
flow_card = make_card(center_col)
flow_card.grid(row=1, column=0, sticky="ew", pady=(0, 8))

section_title(flow_card, "LIVE PRODUCTION FLOW")

flow_inner = ctk.CTkFrame(flow_card, fg_color="transparent")
flow_inner.pack(fill="x", padx=14, pady=(0, 14))
for i in range(9):
    flow_inner.columnconfigure(i, weight=1 if i % 2 == 0 else 0)

STAGE_NAMES  = ["FEED", "FILL", "CAP", "LABEL", "QC", "PACK"]
STAGE_ICONS  = ["⬡",    "💧",   "🔩",  "🏷",   "🔍", "📦"]
STAGE_LABELS = [
    "Bottle Supply", "Water Filling", "Capping",
    "Branding", "Quality Control", "Packing"
]

stage_boxes = {}

for i, (sname, sicon, slabel) in enumerate(zip(STAGE_NAMES, STAGE_ICONS, STAGE_LABELS)):
    box = ctk.CTkFrame(
        flow_inner, fg_color="#0F1E33",
        corner_radius=8, border_width=1, border_color=CYAN_DIM
    )
    box.grid(row=0, column=i * 2, sticky="ew", padx=2, pady=6)

    ctk.CTkLabel(box, text=sicon, font=("Segoe UI", 16), text_color=WHITE).pack(pady=(8, 0))
    ctk.CTkLabel(box, text=sname, font=("Segoe UI", 9, "bold"), text_color=CYAN).pack()
    ctk.CTkLabel(box, text=slabel, font=("Segoe UI", 8), text_color=GRAY_LIGHT).pack(pady=(0, 8))

    stage_boxes[slabel] = box

    # Arrow connector
    if i < len(STAGE_NAMES) - 1:
        ctk.CTkLabel(flow_inner, text="→", font=("Segoe UI", 18, "bold"),
            text_color=CYAN_DIM).grid(row=0, column=i * 2 + 1, padx=2)

# ── LIVE CHART ──
chart_card = make_card(center_col)
chart_card.grid(row=2, column=0, sticky="nsew", pady=(0, 8))
section_title(chart_card, "PRODUCTION TREND  (last 30 cycles)")

fig = Figure(figsize=(6, 2.6), dpi=90, facecolor=BG_CARD)
ax = fig.add_subplot(111)
ax.set_facecolor(BG_MID)
ax.tick_params(colors=GRAY_LIGHT, labelsize=8)
for spine in ax.spines.values():
    spine.set_edgecolor(GRAY_MID)
ax.set_xlabel("Cycle", color=GRAY_LIGHT, fontsize=8)
ax.set_ylabel("Bottles", color=GRAY_LIGHT, fontsize=8)
fig.tight_layout(pad=1.2)

chart_canvas = FigureCanvasTkAgg(fig, master=chart_card)
chart_canvas.get_tk_widget().pack(fill="both", expand=True, padx=10, pady=(0, 8))

def refresh_chart():
    ax.clear()
    ax.set_facecolor(BG_MID)
    ax.tick_params(colors=GRAY_LIGHT, labelsize=8)
    for spine in ax.spines.values():
        spine.set_edgecolor(GRAY_MID)

    if len(production_history) > 1:
        xs = list(range(len(production_history)))
        goods = [h[2] for h in production_history]
        bads  = [h[3] for h in production_history]

        ax.fill_between(xs, goods, alpha=0.25, color=GREEN)
        ax.plot(xs, goods, color=GREEN,   linewidth=1.5, label="Good")
        ax.fill_between(xs, bads,  alpha=0.20, color=RED)
        ax.plot(xs, bads,  color=RED,    linewidth=1.2, label="Defective")
        ax.legend(facecolor=BG_MID, labelcolor=WHITE, fontsize=8, framealpha=0.6)

    ax.set_xlabel("Cycle", color=GRAY_LIGHT, fontsize=8)
    ax.set_ylabel("Bottles", color=GRAY_LIGHT, fontsize=8)
    fig.tight_layout(pad=1.2)
    chart_canvas.draw()

# ── PROGRESS BAR ──
prog_card = make_card(center_col)
prog_card.grid(row=3, column=0, sticky="ew")

prog_inner = ctk.CTkFrame(prog_card, fg_color="transparent")
prog_inner.pack(fill="x", padx=14, pady=8)

prog_stage_lbl = ctk.CTkLabel(
    prog_inner, text="Stage: IDLE",
    font=("Segoe UI", 10, "bold"), text_color=CYAN
)
prog_stage_lbl.pack(anchor="w")

progress_bar = ctk.CTkProgressBar(
    prog_inner, height=16, corner_radius=4,
    fg_color=BG_MID, progress_color=CYAN
)
progress_bar.set(0)
progress_bar.pack(fill="x", pady=4)

# ─────────────────────────────────────
# RIGHT COLUMN
# ─────────────────────────────────────
right_col = ctk.CTkFrame(main, fg_color="transparent")
right_col.grid(row=0, column=2, sticky="nsew")
right_col.rowconfigure(0, weight=1)

# ── ALARM / EVENT LOG ──
alarm_card = make_card(right_col)
alarm_card.pack(fill="both", expand=True)
section_title(alarm_card, "ALARM & EVENT LOG")

log_box = ctk.CTkTextbox(
    alarm_card,
    fg_color=BG_MID,
    text_color=WHITE,
    font=FONT_MONO,
    corner_radius=6,
    wrap="word",
    state="disabled"
)
log_box.pack(fill="both", expand=True, padx=14, pady=(0, 10))

# Colour tags (applied via tk Text tag mechanism)
log_box._textbox.tag_config("alarm", foreground=RED)
log_box._textbox.tag_config("warn",  foreground=AMBER)
log_box._textbox.tag_config("info",  foreground=CYAN)
log_box._textbox.tag_config("ok",    foreground=GREEN)
log_box._textbox.tag_config("ts",    foreground=GRAY_LIGHT)

def log(message, level="info"):
    """Insert a timestamped line into the alarm/event log."""
    ts = datetime.now().strftime("%H:%M:%S")
    log_box.configure(state="normal")
    log_box._textbox.insert("end", f"[{ts}] ", "ts")
    tag = {"alarm": "alarm", "warn": "warn", "ok": "ok"}.get(level, "info")
    log_box._textbox.insert("end", message + "\n", tag)
    log_box.configure(state="disabled")
    log_box._textbox.see("end")
    alarm_log.append((ts, message, level))

# ══════════════════════════════════════════════
# STAGE ANIMATION HELPERS
# ══════════════════════════════════════════════
STAGE_MAP = {
    "Bottle Supply":  "Bottle Supply",
    "Water Filling":  "Water Filling",
    "Capping":        "Capping",
    "Branding":       "Branding",
    "Quality Control":"Quality Control",
}

_prev_active_stage = None

def highlight_stage(stage_label_key):
    global _prev_active_stage
    # Reset all boxes
    for box in stage_boxes.values():
        box.configure(fg_color="#0F1E33", border_color=CYAN_DIM)

    if stage_label_key and stage_label_key in stage_boxes:
        stage_boxes[stage_label_key].configure(
            fg_color=BG_CARD2, border_color=GREEN
        )
        _prev_active_stage = stage_label_key

# Pulsing animation for the active stage (subtle brightness toggle)
_pulse_bright = True

def pulse_active():
    global _pulse_bright
    if _prev_active_stage and _prev_active_stage in stage_boxes:
        box = stage_boxes[_prev_active_stage]
        box.configure(fg_color=BG_CARD2 if _pulse_bright else "#1E3A5F")
        _pulse_bright = not _pulse_bright
    root.after(600, pulse_active)

# ══════════════════════════════════════════════
# UPDATE UI
# ══════════════════════════════════════════════
STAGE_PROGRESS = {
    "IDLE": 0.0,
    "Bottle Supply": 0.16,
    "Water Filling": 0.33,
    "Capping": 0.50,
    "Branding": 0.66,
    "Quality Control": 0.83,
    "Packing": 1.0,
}

def update_ui():
    # KPI
    total = line.total_bottles
    good  = line.good_bottles
    defv  = line.defective_bottles
    eff   = (good / total * 100) if total > 0 else 0.0

    kpi_value_labels["total_bottles"][0].configure(text=str(total))
    kpi_value_labels["good_bottles"][0].configure(text=str(good))
    kpi_value_labels["defective_bottles"][0].configure(text=str(defv))
    kpi_value_labels["efficiency"][0].configure(text=f"{eff:.1f}%")
    kpi_value_labels["efficiency"][1].configure(text="efficiency")

    # Machine info
    v_state.configure(text=line.machine_state,
        text_color=GREEN if line.machine_state == "RUNNING" else
                   (RED if line.machine_state == "STOPPED" else AMBER))
    v_stage.configure(text=line.current_stage)
    v_err.configure(text=line.last_error,
        text_color=RED if line.last_error != "NONE" else GRAY_LIGHT)

    # Progress
    pval = STAGE_PROGRESS.get(line.current_stage, 0.0)
    progress_bar.set(pval)
    prog_stage_lbl.configure(text=f"Stage: {line.current_stage}")

    # Stage flow highlight
    highlight_stage(STAGE_MAP.get(line.current_stage))

    # Water tank & health gauges
    water_lvl = getattr(line, "water_level", 85)
    health = line.cmms.equipment_health
    draw_tank(water_lvl)
    draw_arc_gauge(health_canvas, health)

    # Chart data
    production_history.append((
        datetime.now().strftime("%H:%M:%S"),
        total, good, defv
    ))
    if len(production_history) > 30:
        production_history.pop(0)
    refresh_chart()

# ══════════════════════════════════════════════
# CLOCK
# ══════════════════════════════════════════════
def tick_clock():
    clock_label.configure(text=datetime.now().strftime("%a %Y-%m-%d  %H:%M:%S"))
    root.after(1000, tick_clock)

tick_clock()

# ══════════════════════════════════════════════
# MACHINE CONTROL CALLBACKS
# ══════════════════════════════════════════════
def auto_produce():
    if auto_running and line.machine_state == "RUNNING":
        bottle = line.process_bottle()
        update_ui()
        if bottle:
            if bottle.defective:
                log(f"Bottle #{bottle.id}  REJECTED → {bottle.defect_reason}", "alarm")
            else:
                log(f"Bottle #{bottle.id}  APPROVED", "ok")
        root.after(1000, auto_produce)


def start_machine():
    global auto_running
    line.start()
    auto_running = True
    status_pill.configure(text="  ● RUNNING  ", fg_color=GREEN)
    update_ui()
    log("Machine started — production cycle initiated.", "info")
    auto_produce()


def stop_machine():
    global auto_running
    auto_running = False
    line.stop()
    status_pill.configure(text="  ● STOPPED  ", fg_color=RED)
    update_ui()
    log("Machine stopped by operator.", "warn")


def reset_machine():
    global auto_running
    auto_running = False
    line.reset()
    production_history.clear()
    status_pill.configure(text="  ● IDLE  ", fg_color=AMBER)
    update_ui()
    progress_bar.set(0)
    highlight_stage(None)
    log("System reset. All counters cleared.", "info")


def do_maintenance():
    line.cmms.perform_maintenance()
    if not SIMULATION_MODE:
        try:
            line.influx.write_cmms_event(
                "maintenance", "Preventive Maintenance performed by operator"
            )
        except Exception:
            pass
    update_ui()
    log("Maintenance performed. Equipment health restored.", "ok")


# ══════════════════════════════════════════════
# INIT
# ══════════════════════════════════════════════
update_ui()
pulse_active()

if SIMULATION_MODE:
    log("⚠  production_line.py not found — running built-in simulator.", "warn")
else:
    log("Production line module loaded successfully.", "info")

log("HMI v2.0 ready. Awaiting operator command.", "info")

root.mainloop()
#change commit