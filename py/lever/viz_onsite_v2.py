"""
Visualization v2: Last 50 engineering onsite candidates.
Multi-panel chart: Gantt timeline + stage durations + outcomes + funnel + days-to-onsite.
"""

import json
from pathlib import Path
from datetime import datetime, timedelta
from collections import defaultdict, Counter

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import matplotlib.patches as mpatches
import matplotlib.lines as mlines
import matplotlib.dates as mdates
from matplotlib.gridspec import GridSpec
import numpy as np

# ── Load data ──────────────────────────────────────────────────────────────────
DATA_FILE = Path("/sessions/lucid-happy-edison/mnt/lever/onsite_candidates_latest.json")
data = json.loads(DATA_FILE.read_text())

stages_map = data["stages"]
archive_reasons = data.get("archive_reasons", {})
candidates_raw = data["candidates"]

# ── Stage ordering / colors ────────────────────────────────────────────────────
ONSITE_STAGE_ID = "ba3541af-b2ac-4dd2-8433-660582e2924e"

STAGE_ORDER = [
    "lead-new", "lead-reached-out", "lead-responded", "applicant-new",
    "12a60d91-1ce3-46d9-9a5d-fa403ee12aa5",  # Recruiter Screen
    "ec9dea12-d029-420b-836b-0ad5c633c4a1",  # Phone screen
    "5c476846-962c-4bcc-b299-89a7a8f909be",  # HM Screen
    "eed7c7e4-eda1-4ea4-8ae9-7d3d2f21e7f5",  # Assignment
    "ba3541af-b2ac-4dd2-8433-660582e2924e",  # On-site
    "e35ea840-3488-402f-9f86-e062ec0a5632",  # Abhinai Stage
    "65e31017-f862-489f-9c74-7e6f5d95d757",  # Reference check
    "offer",
]
STAGE_LABELS = {
    "lead-new": "Lead",
    "lead-reached-out": "Reached Out",
    "lead-responded": "Responded",
    "applicant-new": "Applied",
    "12a60d91-1ce3-46d9-9a5d-fa403ee12aa5": "Recruiter Screen",
    "ec9dea12-d029-420b-836b-0ad5c633c4a1": "Phone Screen",
    "5c476846-962c-4bcc-b299-89a7a8f909be": "HM Screen",
    "eed7c7e4-eda1-4ea4-8ae9-7d3d2f21e7f5": "Assignment",
    "ba3541af-b2ac-4dd2-8433-660582e2924e": "Onsite",
    "e35ea840-3488-402f-9f86-e062ec0a5632": "Abhinai",
    "65e31017-f862-489f-9c74-7e6f5d95d757": "Ref Check",
    "offer": "Offer",
}
STAGE_COLORS = {
    "lead-new": "#aed6f1",
    "lead-reached-out": "#7fb3d3",
    "lead-responded": "#5499c7",
    "applicant-new": "#a9dfbf",
    "12a60d91-1ce3-46d9-9a5d-fa403ee12aa5": "#52be80",
    "ec9dea12-d029-420b-836b-0ad5c633c4a1": "#f5b041",
    "5c476846-962c-4bcc-b299-89a7a8f909be": "#e67e22",
    "eed7c7e4-eda1-4ea4-8ae9-7d3d2f21e7f5": "#ca6f1e",
    "ba3541af-b2ac-4dd2-8433-660582e2924e": "#c0392b",
    "e35ea840-3488-402f-9f86-e062ec0a5632": "#922b21",
    "65e31017-f862-489f-9c74-7e6f5d95d757": "#7d3c98",
    "offer": "#1e8449",
}
OUTCOME_COLORS = {
    "Hired":                  "#1e8449",
    "Offer Declined":         "#27ae60",
    "Active in Another Pipeline": "#52be80",
    "Still Active":           "#2980b9",
    "Position Closed":        "#95a5a6",
    "Timing":                 "#f39c12",
    "Withdrew":               "#e67e22",
    "Unresponsive":           "#e74c3c",
    "Unqualified":            "#c0392b",
    "Role Not a Match":       "#922b21",
}

def ts_to_dt(ms):
    return datetime.fromtimestamp(ms / 1000)

NOW = datetime.now()

# ── Parse candidates ───────────────────────────────────────────────────────────
class Candidate:
    def __init__(self, raw):
        opp = raw["opportunity"]
        self.id = opp["id"]
        self.name = opp["name"].strip()
        self.archived = opp.get("archived")
        self.tags = opp.get("tags", [])
        self.job_title = self.tags[0] if self.tags else "Unknown"
        self.current_stage_id = opp.get("stage", "")

        self.stage_changes = sorted(
            [(sc["toStageId"], ts_to_dt(sc["updatedAt"])) for sc in opp.get("stageChanges", [])],
            key=lambda x: x[1]
        )

        self.interviews = []
        for iv in raw.get("interviews", []):
            if iv.get("date"):
                self.interviews.append({
                    "dt": ts_to_dt(iv["date"]),
                    "subject": iv.get("subject", ""),
                    "canceled": bool(iv.get("canceledAt")),
                    "stage": iv.get("stage", ""),
                })

        self.feedback = [
            {"dt": ts_to_dt(fb["completedAt"]), "text": fb.get("text", "")}
            for fb in raw.get("feedback", []) if fb.get("completedAt")
        ]

        self.first_dt = self.stage_changes[0][1] if self.stage_changes else (
            ts_to_dt(opp["createdAt"]) if opp.get("createdAt") else None
        )
        self.last_dt = self.stage_changes[-1][1] if self.stage_changes else None
        self.last_advanced_dt = ts_to_dt(opp["lastAdvancedAt"]) if opp.get("lastAdvancedAt") else self.last_dt

        # Outcome label
        if self.archived:
            reason_id = self.archived.get("reason", "")
            self.outcome = archive_reasons.get(reason_id, reason_id[:12] if reason_id else "Archived")
        else:
            self.outcome = "Still Active"

        # Days from first contact to reaching onsite
        onsite_dt = next((dt for sid, dt in self.stage_changes if sid == ONSITE_STAGE_ID), None)
        if not onsite_dt and self.current_stage_id == ONSITE_STAGE_ID and self.last_advanced_dt:
            onsite_dt = self.last_advanced_dt
        self.onsite_dt = onsite_dt
        self.days_to_onsite = (onsite_dt - self.first_dt).days if (onsite_dt and self.first_dt) else None

candidates = [Candidate(r) for r in candidates_raw]
candidates.sort(key=lambda c: -(c.last_advanced_dt.timestamp() if c.last_advanced_dt else 0))

# ── Figure setup ───────────────────────────────────────────────────────────────
N = len(candidates)  # 50
BAR_H = 0.6
ROW_GAP = 1.0

fig = plt.figure(figsize=(24, N * 0.38 + 16), facecolor="#f8f9fa")
fig.suptitle(
    "Engineering Candidates — Last 50 Through On-Site Interviews",
    fontsize=20, fontweight="bold", y=0.995, color="#1a1a2e"
)

# Layout: tall Gantt on top, 2x3 analytics panels below
gs = GridSpec(2, 3, figure=fig,
              left=0.07, right=0.97, top=0.985, bottom=0.02,
              hspace=0.07, wspace=0.30,
              height_ratios=[N * 0.38, 9])

ax_gantt   = fig.add_subplot(gs[0, :])          # Full-width Gantt
ax_outcome = fig.add_subplot(gs[1, 0])          # Outcome distribution
ax_funnel  = fig.add_subplot(gs[1, 1])          # Stage funnel
ax_days    = fig.add_subplot(gs[1, 2])          # Days to onsite

# ── Panel 1: Gantt timeline ────────────────────────────────────────────────────
ax = ax_gantt
ax.set_facecolor("#ffffff")

all_dts = []
for c in candidates:
    for _, dt in c.stage_changes: all_dts.append(dt)
    for iv in c.interviews: all_dts.append(iv["dt"])
    if c.last_advanced_dt: all_dts.append(c.last_advanced_dt)
t_min = min(all_dts) - timedelta(days=3)
t_max = max(all_dts) + timedelta(days=5)

for row_i, cand in enumerate(candidates):
    y = (N - 1 - row_i) * ROW_GAP  # newest at top
    changes = cand.stage_changes

    # If no stage changes, draw a thin line from createdAt to lastAdvancedAt
    if not changes and cand.first_dt and cand.last_advanced_dt:
        ax.barh(y, (cand.last_advanced_dt - cand.first_dt).days,
                left=mdates.date2num(cand.first_dt), height=BAR_H * 0.3,
                color="#cccccc", zorder=2)
    else:
        for seg_i, (sid, seg_start) in enumerate(changes):
            if seg_i + 1 < len(changes):
                seg_end = changes[seg_i + 1][1]
            else:
                seg_end = min(cand.last_advanced_dt or NOW, seg_start + timedelta(days=2))
                if seg_end <= seg_start:
                    seg_end = seg_start + timedelta(hours=6)

            color = STAGE_COLORS.get(sid, "#bbbbbb")
            width = mdates.date2num(seg_end) - mdates.date2num(seg_start)
            ax.barh(y, width, left=mdates.date2num(seg_start),
                    height=BAR_H, color=color, edgecolor="white", linewidth=0.4, zorder=2)

            days = (seg_end - seg_start).days
            if days >= 3:
                mid = seg_start + (seg_end - seg_start) / 2
                lbl = STAGE_LABELS.get(sid, "").replace(" ", "\n")
                txt_color = "white" if STAGE_COLORS.get(sid, "#fff") < "#999999" else "#333"
                ax.text(mdates.date2num(mid), y, lbl,
                        ha="center", va="center", fontsize=5.5,
                        color="white", fontweight="bold", zorder=3)

    # Interview markers
    for iv in cand.interviews:
        if iv["canceled"]: continue
        is_os = (iv["stage"] == ONSITE_STAGE_ID or "on-site" in iv["subject"].lower() or "onsite" in iv["subject"].lower())
        ax.plot(mdates.date2num(iv["dt"]), y + BAR_H / 2 + 0.07,
                marker="v", markersize=6,
                color="#c0392b" if is_os else "#2471a3",
                alpha=0.9, zorder=4)

    # Feedback markers
    for fb in cand.feedback:
        ax.plot(mdates.date2num(fb["dt"]), y - BAR_H / 2 - 0.07,
                marker="^", markersize=4.5,
                color="#1e8449", alpha=0.75, zorder=4)

    # Candidate label
    short_name = cand.name.split()[0] + " " + cand.name.split()[-1] if len(cand.name.split()) > 1 else cand.name
    ax.text(mdates.date2num(t_min) - 0.4, y,
            short_name, ha="right", va="center", fontsize=7, color="#1a1a2e")

    # Outcome badge on the right
    oc = cand.outcome
    oc_color = OUTCOME_COLORS.get(oc, "#888888")
    ax.text(mdates.date2num(t_max) + 0.2, y,
            oc, ha="left", va="center", fontsize=6.5,
            color=oc_color, style="italic", fontweight="bold")

# X axis
ax.xaxis_date()
ax.xaxis.set_major_formatter(mdates.DateFormatter("%b %d"))
ax.xaxis.set_major_locator(mdates.WeekdayLocator(byweekday=0))
ax.xaxis.set_minor_locator(mdates.DayLocator())
ax.set_xlim(mdates.date2num(t_min) - 3, mdates.date2num(t_max) + 6)
ax.set_ylim(-ROW_GAP, N * ROW_GAP)
ax.set_yticks([])
ax.grid(axis="x", color="#e5e5e5", linewidth=0.5, zorder=0)
ax.spines[["top", "right", "left"]].set_visible(False)
ax.set_title(
    "Candidate Pipeline Timelines  (newest → oldest)   ▼ = Interview   ▲ = Feedback submitted",
    fontsize=11, fontweight="bold", pad=5, color="#1a1a2e"
)

# Legend
legend_items = [
    mpatches.Patch(facecolor=STAGE_COLORS["lead-new"], label="Lead/Outreach"),
    mpatches.Patch(facecolor=STAGE_COLORS["applicant-new"], label="Applied"),
    mpatches.Patch(facecolor=STAGE_COLORS["12a60d91-1ce3-46d9-9a5d-fa403ee12aa5"], label="Recruiter Screen"),
    mpatches.Patch(facecolor=STAGE_COLORS["ec9dea12-d029-420b-836b-0ad5c633c4a1"], label="Phone Screen"),
    mpatches.Patch(facecolor=STAGE_COLORS["5c476846-962c-4bcc-b299-89a7a8f909be"], label="HM Screen"),
    mpatches.Patch(facecolor=STAGE_COLORS["ba3541af-b2ac-4dd2-8433-660582e2924e"], label="Onsite"),
    mpatches.Patch(facecolor=STAGE_COLORS["e35ea840-3488-402f-9f86-e062ec0a5632"], label="Abhinai Stage"),
    mpatches.Patch(facecolor=STAGE_COLORS["offer"], label="Offer"),
    mlines.Line2D([], [], marker="v", color="w", markerfacecolor="#2471a3", markersize=7, label="Interview"),
    mlines.Line2D([], [], marker="v", color="w", markerfacecolor="#c0392b", markersize=7, label="Onsite Interview"),
    mlines.Line2D([], [], marker="^", color="w", markerfacecolor="#1e8449", markersize=6, label="Feedback"),
]
ax.legend(handles=legend_items, loc="upper left", fontsize=7.5, ncol=6,
          framealpha=0.9, edgecolor="#ccc")

# ── Panel 2: Outcome distribution (horizontal bar) ────────────────────────────
ax = ax_outcome
ax.set_facecolor("#ffffff")

outcome_counts = Counter(c.outcome for c in candidates)
outcomes_sorted = sorted(outcome_counts.items(), key=lambda x: x[1])
labels, vals = zip(*outcomes_sorted)
colors = [OUTCOME_COLORS.get(l, "#888") for l in labels]

bars = ax.barh(range(len(labels)), vals, color=colors, edgecolor="white", height=0.65)
ax.set_yticks(range(len(labels)))
ax.set_yticklabels(labels, fontsize=9)
ax.set_xlabel("# candidates", fontsize=9)
ax.set_title(f"Outcomes\n(n={N} most recent onsite candidates)", fontsize=10, fontweight="bold", pad=4)
ax.spines[["top", "right"]].set_visible(False)
ax.grid(axis="x", color="#eeeeee")
for bar, val in zip(bars, vals):
    ax.text(val + 0.1, bar.get_y() + bar.get_height() / 2,
            str(val), va="center", fontsize=9, fontweight="bold")

# ── Panel 3: Stage funnel ──────────────────────────────────────────────────────
ax = ax_funnel
ax.set_facecolor("#ffffff")

FUNNEL_STAGES = [
    "lead-new", "applicant-new",
    "12a60d91-1ce3-46d9-9a5d-fa403ee12aa5",
    "ec9dea12-d029-420b-836b-0ad5c633c4a1",
    "5c476846-962c-4bcc-b299-89a7a8f909be",
    "ba3541af-b2ac-4dd2-8433-660582e2924e",
    "e35ea840-3488-402f-9f86-e062ec0a5632",
    "65e31017-f862-489f-9c74-7e6f5d95d757",
    "offer",
]
funnel = {}
for sid in FUNNEL_STAGES:
    count = sum(1 for c in candidates
                for sc_id, _ in c.stage_changes if sc_id == sid)
    # Also count by final stage
    count += sum(1 for c in candidates
                 if c.current_stage_id == sid and not any(sc_id == sid for sc_id, _ in c.stage_changes))
    if count > 0:
        funnel[sid] = count

fsids = [s for s in FUNNEL_STAGES if s in funnel]
fvals = [funnel[s] for s in fsids]
flabels = [STAGE_LABELS[s] for s in fsids]
fcolors = [STAGE_COLORS.get(s, "#888") for s in fsids]

bars = ax.barh(range(len(fsids)), fvals, color=fcolors, edgecolor="white", height=0.65)
ax.set_yticks(range(len(fsids)))
ax.set_yticklabels(flabels, fontsize=9)
ax.invert_yaxis()
ax.set_xlabel("# candidates who passed through stage", fontsize=9)
ax.set_title("Stage Funnel\n(all 50 onsite candidates)", fontsize=10, fontweight="bold", pad=4)
ax.spines[["top", "right"]].set_visible(False)
ax.grid(axis="x", color="#eeeeee")
ax.set_xlim(0, max(fvals) + 3)
for bar, val in zip(bars, fvals):
    ax.text(val + 0.1, bar.get_y() + bar.get_height() / 2,
            str(val), va="center", fontsize=9, fontweight="bold")

# ── Panel 4: Days from first contact to onsite ─────────────────────────────────
ax = ax_days
ax.set_facecolor("#ffffff")

days_data = [(c.name.split()[0], c.days_to_onsite, c.outcome)
             for c in candidates if c.days_to_onsite is not None]
days_data.sort(key=lambda x: -x[1])  # sorted longest to shortest

names_d = [d[0] for d in days_data]
vals_d = [d[1] for d in days_data]
colors_d = [OUTCOME_COLORS.get(d[2], "#888") for d in days_data]

# Horizontal bar chart
bars = ax.barh(range(len(names_d)), vals_d, color=colors_d, edgecolor="white", height=0.65)
ax.set_yticks(range(len(names_d)))
ax.set_yticklabels(names_d, fontsize=7.5)
ax.set_xlabel("Days from first contact → onsite", fontsize=9)
ax.set_title("Time to Onsite (days)\ncoloured by outcome", fontsize=10, fontweight="bold", pad=4)
ax.spines[["top", "right"]].set_visible(False)
ax.grid(axis="x", color="#eeeeee")

# Median line
if vals_d:
    med = float(np.median(vals_d))
    ax.axvline(med, color="#555", linestyle="--", linewidth=1.2)
    ax.text(med + 0.5, len(names_d) - 0.5, f"Median\n{med:.0f}d",
            va="top", fontsize=8, color="#555")

# Outcome color legend for this chart
legend_els = [mpatches.Patch(facecolor=v, label=k)
              for k, v in OUTCOME_COLORS.items() if k in outcome_counts]
ax.legend(handles=legend_els, loc="lower right", fontsize=7, ncol=1, framealpha=0.85)

# ── Footer ─────────────────────────────────────────────────────────────────────
fig.text(0.5, 0.002,
         f"Data from Lever  •  Downloaded {data['downloaded_at'][:10]}  "
         f"•  {data.get('total_eng_onsite_candidates', N)} total engineering onsite candidates  "
         f"•  Showing 50 most recent by last activity",
         ha="center", fontsize=8, color="#888", style="italic")

# ── Save ───────────────────────────────────────────────────────────────────────
OUT = Path("/sessions/lucid-happy-edison/mnt/lever/onsite_pipeline_analysis.png")
plt.savefig(OUT, dpi=140, bbox_inches="tight", facecolor=fig.get_facecolor())
print(f"Saved → {OUT}")
