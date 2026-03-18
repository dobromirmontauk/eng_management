"""
Visualization: Engineering Onsite Candidate Pipeline Analysis
Reads from onsite_candidates_latest.json and produces a multi-panel chart.
"""

import json
import math
from pathlib import Path
from datetime import datetime, timezone, timedelta
from collections import defaultdict

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import matplotlib.patches as mpatches
import matplotlib.lines as mlines
from matplotlib.gridspec import GridSpec
import numpy as np

# ── Load data ──────────────────────────────────────────────────────────────────
DATA_FILE = Path("/sessions/lucid-happy-edison/mnt/lever/onsite_candidates_latest.json")
data = json.loads(DATA_FILE.read_text())

stages_map = data["stages"]  # id -> name
candidates_raw = data["candidates"]

# ── Stage ordering (pipeline order) ────────────────────────────────────────────
STAGE_ORDER = [
    "lead-new",
    "lead-reached-out",
    "lead-responded",
    "applicant-new",
    "12a60d91-1ce3-46d9-9a5d-fa403ee12aa5",  # Recruiter Screen
    "ec9dea12-d029-420b-836b-0ad5c633c4a1",  # Phone screen
    "5c476846-962c-4bcc-b299-89a7a8f909be",  # Hiring Manager Screen
    "eed7c7e4-eda1-4ea4-8ae9-7d3d2f21e7f5",  # Assignment
    "ba3541af-b2ac-4dd2-8433-660582e2924e",  # On-site interview
    "e35ea840-3488-402f-9f86-e062ec0a5632",  # Abhinai Stage
    "65e31017-f862-489f-9c74-7e6f5d95d757",  # Reference check
    "offer",
]
STAGE_NAMES_SHORT = {
    "lead-new": "Lead",
    "lead-reached-out": "Reached Out",
    "lead-responded": "Responded",
    "applicant-new": "Applied",
    "12a60d91-1ce3-46d9-9a5d-fa403ee12aa5": "Recruiter\nScreen",
    "ec9dea12-d029-420b-836b-0ad5c633c4a1": "Phone\nScreen",
    "5c476846-962c-4bcc-b299-89a7a8f909be": "HM\nScreen",
    "eed7c7e4-eda1-4ea4-8ae9-7d3d2f21e7f5": "Assignment",
    "ba3541af-b2ac-4dd2-8433-660582e2924e": "On-Site\nInterview",
    "e35ea840-3488-402f-9f86-e062ec0a5632": "Abhinai\nStage",
    "65e31017-f862-489f-9c74-7e6f5d95d757": "Reference\nCheck",
    "offer": "Offer",
}

# Colors for each stage segment (gradient from light to rich)
STAGE_COLORS = {
    "lead-new":             "#d4e6f1",
    "lead-reached-out":     "#a9cce3",
    "lead-responded":       "#7fb3d3",
    "applicant-new":        "#d5e8d4",
    "12a60d91-1ce3-46d9-9a5d-fa403ee12aa5": "#82b366",  # Recruiter Screen
    "ec9dea12-d029-420b-836b-0ad5c633c4a1": "#f0a500",  # Phone Screen
    "5c476846-962c-4bcc-b299-89a7a8f909be": "#e07b00",  # HM Screen
    "eed7c7e4-eda1-4ea4-8ae9-7d3d2f21e7f5": "#c55a00",  # Assignment
    "ba3541af-b2ac-4dd2-8433-660582e2924e": "#cc0000",  # Onsite
    "e35ea840-3488-402f-9f86-e062ec0a5632": "#8b0000",  # Abhinai
    "65e31017-f862-489f-9c74-7e6f5d95d757": "#4a0072",  # Ref Check
    "offer":                "#006400",
}

# ── Parse candidate data ────────────────────────────────────────────────────────
def ts_to_dt(ms):
    return datetime.fromtimestamp(ms / 1000)

NOW = datetime.now()

class Candidate:
    def __init__(self, raw):
        opp = raw["opportunity"]
        self.id = opp["id"]
        self.name = opp["name"].strip()
        self.archived = opp.get("archived")
        self.stage_changes = []  # list of (stage_id, datetime)
        for sc in opp.get("stageChanges", []):
            self.stage_changes.append((sc["toStageId"], ts_to_dt(sc["updatedAt"])))
        self.stage_changes.sort(key=lambda x: x[1])

        self.interviews = []  # list of (datetime, subject, canceled)
        for iv in raw.get("interviews", []):
            if iv.get("date"):
                self.interviews.append({
                    "dt": ts_to_dt(iv["date"]),
                    "subject": iv.get("subject", ""),
                    "canceled": bool(iv.get("canceledAt")),
                    "stage": iv.get("stage", ""),
                    "duration": iv.get("duration", 30),
                })

        self.feedback = []
        for fb in raw.get("feedback", []):
            completed = fb.get("completedAt")
            if completed:
                self.feedback.append({
                    "dt": ts_to_dt(completed),
                    "text": fb.get("text", ""),
                })

        self.first_dt = self.stage_changes[0][1] if self.stage_changes else None
        self.last_dt = self.stage_changes[-1][1] if self.stage_changes else None
        self.current_stage = self.stage_changes[-1][0] if self.stage_changes else None

        # Compute time-to-onsite
        onsite_dt = None
        for sid, dt in self.stage_changes:
            if sid == "ba3541af-b2ac-4dd2-8433-660582e2924e":
                onsite_dt = dt
                break
        self.onsite_dt = onsite_dt
        self.days_to_onsite = (onsite_dt - self.first_dt).days if (onsite_dt and self.first_dt) else None


candidates = [Candidate(r) for r in candidates_raw]
# Sort by first contact date
candidates.sort(key=lambda c: c.first_dt or NOW)

# ── Figure layout ───────────────────────────────────────────────────────────────
fig = plt.figure(figsize=(20, 22), facecolor="#f8f9fa")
fig.suptitle(
    "Engineering Candidates — Onsite Pipeline Analysis",
    fontsize=18, fontweight="bold", y=0.98, color="#1a1a2e"
)

gs = GridSpec(3, 2, figure=fig,
              left=0.08, right=0.97, top=0.94, bottom=0.04,
              hspace=0.38, wspace=0.35,
              height_ratios=[2.2, 1.0, 1.0])

ax_timeline = fig.add_subplot(gs[0, :])   # Full-width timeline (Gantt)
ax_stages   = fig.add_subplot(gs[1, 0])   # Stage transition time (days)
ax_counts   = fig.add_subplot(gs[1, 1])   # Interview / feedback counts
ax_funnel   = fig.add_subplot(gs[2, 0])   # Stage funnel
ax_days     = fig.add_subplot(gs[2, 1])   # Days-to-onsite per candidate

# ── Panel 1: Gantt-style timeline ──────────────────────────────────────────────
ax = ax_timeline
ax.set_facecolor("#ffffff")

# Find global date range
all_dts = []
for c in candidates:
    for _, dt in c.stage_changes:
        all_dts.append(dt)
    for iv in c.interviews:
        all_dts.append(iv["dt"])
t_min = min(all_dts) - timedelta(days=2)
t_max = max(all_dts) + timedelta(days=4)

n = len(candidates)
bar_h = 0.55
gap = 1.0

for row_i, cand in enumerate(candidates):
    y = row_i * gap
    changes = cand.stage_changes

    # Draw stage segments
    for seg_i, (sid, seg_start) in enumerate(changes):
        if seg_i + 1 < len(changes):
            seg_end = changes[seg_i + 1][1]
        else:
            # Last stage: extend to NOW or 3 days for visual clarity
            seg_end = min(NOW, seg_start + timedelta(days=3))
            if seg_end <= seg_start:
                seg_end = seg_start + timedelta(hours=12)

        duration_days = (seg_end - seg_start).total_seconds() / 86400
        color = STAGE_COLORS.get(sid, "#cccccc")

        rect = mpatches.FancyBboxPatch(
            (matplotlib.dates.date2num(seg_start), y - bar_h / 2),
            matplotlib.dates.date2num(seg_end) - matplotlib.dates.date2num(seg_start),
            bar_h,
            boxstyle="round,pad=0.01",
            facecolor=color, edgecolor="white", linewidth=0.5,
            zorder=2,
        )
        ax.add_patch(rect)

        # Label stage name inside the bar if wide enough
        if duration_days > 1.5:
            mid = seg_start + (seg_end - seg_start) / 2
            label = STAGE_NAMES_SHORT.get(sid, stages_map.get(sid, "?")).replace("\n", " ")
            ax.text(
                matplotlib.dates.date2num(mid), y,
                label, ha="center", va="center",
                fontsize=6.5, color="white" if STAGE_COLORS.get(sid, "#fff") < "#888888" else "#333",
                fontweight="bold", zorder=3,
            )

    # Draw interview markers
    for iv in cand.interviews:
        if iv["canceled"]:
            continue
        marker_color = "#cc0000" if "on-site" in iv["subject"].lower() or iv["stage"] == "ba3541af-b2ac-4dd2-8433-660582e2924e" else "#1a6b9a"
        ax.plot(
            matplotlib.dates.date2num(iv["dt"]), y + bar_h / 2 + 0.08,
            marker="v", markersize=7,
            color=marker_color, zorder=4, alpha=0.9,
        )

    # Draw feedback markers
    for fb in cand.feedback:
        ax.plot(
            matplotlib.dates.date2num(fb["dt"]), y - bar_h / 2 - 0.08,
            marker="^", markersize=5,
            color="#2ca02c", zorder=4, alpha=0.7,
        )

    # Candidate name label on left
    ax.text(
        matplotlib.dates.date2num(t_min) - 0.2, y,
        cand.name, ha="right", va="center",
        fontsize=8.5, color="#1a1a2e", fontweight="medium",
    )

    # Show final status
    if cand.archived:
        status_label = f"✕ {cand.archived.get('reason', 'Archived')}"
        status_color = "#cc0000"
    else:
        status_label = f"● {STAGE_NAMES_SHORT.get(cand.current_stage,'Active').replace(chr(10),' ')}"
        status_color = "#006400"
    ax.text(
        matplotlib.dates.date2num(t_max) + 0.1, y,
        status_label, ha="left", va="center",
        fontsize=7, color=status_color, style="italic",
    )

# Gridlines for weeks
ax.xaxis_date()
ax.xaxis.set_major_formatter(matplotlib.dates.DateFormatter("%b %d"))
ax.xaxis.set_major_locator(matplotlib.dates.WeekdayLocator(byweekday=0))
ax.xaxis.set_minor_locator(matplotlib.dates.DayLocator())
ax.set_xlim(matplotlib.dates.date2num(t_min) - 2, matplotlib.dates.date2num(t_max) + 4)
ax.set_ylim(-gap, n * gap)
ax.set_yticks([])
ax.set_xlabel("Date", fontsize=9, color="#555")
ax.set_title("Candidate Timelines — Stages, Interviews (▼) & Feedback Submissions (▲)",
             fontsize=11, fontweight="bold", pad=6, color="#1a1a2e")
ax.grid(axis="x", color="#e0e0e0", linewidth=0.5, zorder=0)
ax.spines[["top", "right", "left"]].set_visible(False)

# Legend for timeline
legend_elements = [
    mpatches.Patch(facecolor=STAGE_COLORS["lead-new"], label="Lead / Outreach"),
    mpatches.Patch(facecolor=STAGE_COLORS["applicant-new"], label="Applied"),
    mpatches.Patch(facecolor=STAGE_COLORS["12a60d91-1ce3-46d9-9a5d-fa403ee12aa5"], label="Recruiter Screen"),
    mpatches.Patch(facecolor=STAGE_COLORS["ec9dea12-d029-420b-836b-0ad5c633c4a1"], label="Phone Screen"),
    mpatches.Patch(facecolor=STAGE_COLORS["5c476846-962c-4bcc-b299-89a7a8f909be"], label="HM Screen"),
    mpatches.Patch(facecolor=STAGE_COLORS["ba3541af-b2ac-4dd2-8433-660582e2924e"], label="On-Site"),
    mpatches.Patch(facecolor=STAGE_COLORS["e35ea840-3488-402f-9f86-e062ec0a5632"], label="Abhinai Stage"),
    mlines.Line2D([0], [0], marker="v", color="w", markerfacecolor="#1a6b9a", markersize=8, label="Interview (non-onsite)"),
    mlines.Line2D([0], [0], marker="v", color="w", markerfacecolor="#cc0000", markersize=8, label="On-Site Interview"),
    mlines.Line2D([0], [0], marker="^", color="w", markerfacecolor="#2ca02c", markersize=7, label="Feedback Submitted"),
]
ax.legend(handles=legend_elements, loc="upper left", fontsize=7,
          ncol=5, framealpha=0.85, edgecolor="#ccc")


# ── Panel 2: Days in each stage (scatter with median line) ─────────────────────
ax = ax_stages
ax.set_facecolor("#ffffff")

# Calculate days spent in each stage for each candidate
stage_durations = defaultdict(list)  # stage_id -> list of days
RELEVANT_STAGES = [
    "lead-new", "lead-reached-out", "lead-responded", "applicant-new",
    "12a60d91-1ce3-46d9-9a5d-fa403ee12aa5",
    "ec9dea12-d029-420b-836b-0ad5c633c4a1",
    "5c476846-962c-4bcc-b299-89a7a8f909be",
    "ba3541af-b2ac-4dd2-8433-660582e2924e",
]

for cand in candidates:
    changes = cand.stage_changes
    for seg_i, (sid, seg_start) in enumerate(changes):
        if sid not in RELEVANT_STAGES:
            continue
        if seg_i + 1 < len(changes):
            seg_end = changes[seg_i + 1][1]
            days = (seg_end - seg_start).total_seconds() / 86400
            stage_durations[sid].append(days)

# Only show stages that have data
active_stages = [s for s in RELEVANT_STAGES if stage_durations[s]]
x_pos = list(range(len(active_stages)))
x_labels = [STAGE_NAMES_SHORT[s].replace("\n", "\n") for s in active_stages]

for xi, sid in enumerate(active_stages):
    vals = stage_durations[sid]
    # Jitter
    jitter = np.random.normal(0, 0.05, len(vals))
    ax.scatter([xi + j for j in jitter], vals,
               color=STAGE_COLORS.get(sid, "#888"), s=60, zorder=3, alpha=0.8, edgecolors="white")
    # Median line
    med = np.median(vals)
    ax.hlines(med, xi - 0.3, xi + 0.3, colors=STAGE_COLORS.get(sid, "#888"),
              linewidth=2.5, zorder=4)
    ax.text(xi, med + max(vals) * 0.06, f"{med:.1f}d",
            ha="center", fontsize=8, color=STAGE_COLORS.get(sid, "#333"), fontweight="bold")

ax.set_xticks(x_pos)
ax.set_xticklabels(x_labels, fontsize=8)
ax.set_ylabel("Days in stage", fontsize=9)
ax.set_title("Days Spent per Stage\n(dots = candidates, bar = median)", fontsize=10, fontweight="bold", pad=4)
ax.spines[["top", "right"]].set_visible(False)
ax.grid(axis="y", color="#eeeeee", linewidth=0.7)
ax.set_ylim(bottom=0)


# ── Panel 3: Interview & feedback counts per candidate ─────────────────────────
ax = ax_counts
ax.set_facecolor("#ffffff")

names_short = [c.name.split()[0] for c in candidates]
iv_counts = [sum(1 for iv in c.interviews if not iv["canceled"]) for c in candidates]
fb_counts = [len(c.feedback) for c in candidates]

x = np.arange(len(candidates))
w = 0.35
bars1 = ax.bar(x - w/2, iv_counts, w, label="Interviews (not canceled)", color="#1a6b9a", alpha=0.85)
bars2 = ax.bar(x + w/2, fb_counts, w, label="Feedback forms completed", color="#2ca02c", alpha=0.75)

ax.set_xticks(x)
ax.set_xticklabels(names_short, rotation=35, ha="right", fontsize=8)
ax.set_ylabel("Count", fontsize=9)
ax.set_title("Interviews & Feedback per Candidate", fontsize=10, fontweight="bold", pad=4)
ax.legend(fontsize=8, loc="upper left")
ax.spines[["top", "right"]].set_visible(False)
ax.grid(axis="y", color="#eeeeee", linewidth=0.7)

# Add value labels on bars
for bar in list(bars1) + list(bars2):
    h = bar.get_height()
    if h > 0:
        ax.text(bar.get_x() + bar.get_width() / 2, h + 0.1, str(int(h)),
                ha="center", va="bottom", fontsize=7.5, color="#333")


# ── Panel 4: Stage funnel (how many candidates passed through each stage) ───────
ax = ax_funnel
ax.set_facecolor("#ffffff")

# Count how many candidates ever entered each stage
FUNNEL_STAGES = [
    "lead-new", "lead-reached-out", "lead-responded", "applicant-new",
    "12a60d91-1ce3-46d9-9a5d-fa403ee12aa5",
    "ec9dea12-d029-420b-836b-0ad5c633c4a1",
    "5c476846-962c-4bcc-b299-89a7a8f909be",
    "ba3541af-b2ac-4dd2-8433-660582e2924e",
    "e35ea840-3488-402f-9f86-e062ec0a5632",
]
stage_counts = {}
for sid in FUNNEL_STAGES:
    count = sum(1 for c in candidates
                for sc_id, _ in c.stage_changes if sc_id == sid)
    if count > 0:
        stage_counts[sid] = count

funnel_sids = [s for s in FUNNEL_STAGES if s in stage_counts]
funnel_vals = [stage_counts[s] for s in funnel_sids]
funnel_labels = [STAGE_NAMES_SHORT[s].replace("\n", " ") for s in funnel_sids]
colors = [STAGE_COLORS.get(s, "#888") for s in funnel_sids]

bars = ax.barh(range(len(funnel_sids)), funnel_vals, color=colors, edgecolor="white", height=0.65)
ax.set_yticks(range(len(funnel_sids)))
ax.set_yticklabels(funnel_labels, fontsize=8.5)
ax.invert_yaxis()
ax.set_xlabel("# candidates who reached stage", fontsize=9)
ax.set_title("Stage Funnel\n(all onsite candidates)", fontsize=10, fontweight="bold", pad=4)
ax.spines[["top", "right"]].set_visible(False)
ax.grid(axis="x", color="#eeeeee", linewidth=0.7)
ax.set_xlim(0, max(funnel_vals) + 1)
for bar, val in zip(bars, funnel_vals):
    ax.text(val + 0.05, bar.get_y() + bar.get_height() / 2,
            str(val), va="center", fontsize=9, fontweight="bold", color="#333")


# ── Panel 5: Days from first contact to onsite ─────────────────────────────────
ax = ax_days
ax.set_facecolor("#ffffff")

valid = [(c.name.split()[0], c.days_to_onsite) for c in candidates if c.days_to_onsite is not None]
names_d, days_d = zip(*valid) if valid else ([], [])
colors_d = ["#cc0000" if d < 14 else "#f0a500" if d < 28 else "#1a6b9a" for d in days_d]

bars = ax.bar(range(len(names_d)), days_d, color=colors_d, edgecolor="white", width=0.6)
ax.set_xticks(range(len(names_d)))
ax.set_xticklabels(names_d, rotation=35, ha="right", fontsize=8)
ax.set_ylabel("Days", fontsize=9)
ax.set_title("Days from First Contact → Onsite\n(red <14d, amber 14–28d, blue >28d)",
             fontsize=10, fontweight="bold", pad=4)
ax.spines[["top", "right"]].set_visible(False)
ax.grid(axis="y", color="#eeeeee", linewidth=0.7)
for bar, d in zip(bars, days_d):
    ax.text(bar.get_x() + bar.get_width() / 2, d + 0.5, f"{int(d)}d",
            ha="center", va="bottom", fontsize=8.5, fontweight="bold")

# Median line
if days_d:
    med = float(np.median(days_d))
    ax.axhline(med, color="#555", linestyle="--", linewidth=1.2, zorder=5)
    ax.text(len(names_d) - 0.5, med + 1, f"Median: {med:.0f}d",
            ha="right", fontsize=8, color="#555")

# ── Footer ─────────────────────────────────────────────────────────────────────
fig.text(0.5, 0.01,
         f"Data downloaded from Lever on {data['downloaded_at'][:10]}  •  "
         f"{len(candidates)} candidates reached On-Site interview stage  •  Engineering roles only",
         ha="center", fontsize=8, color="#888", style="italic")

# ── Save ───────────────────────────────────────────────────────────────────────
OUT = Path("/sessions/lucid-happy-edison/mnt/lever/onsite_pipeline_analysis.png")
plt.savefig(OUT, dpi=160, bbox_inches="tight", facecolor=fig.get_facecolor())
print(f"Saved to {OUT}")
