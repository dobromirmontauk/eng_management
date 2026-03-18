"""
Visualization v2: Last 50 engineering onsite candidates.
Gantt shows actual interviews as bars (not stage durations).
Bottom panels: outcomes, days-to-onsite, interview type breakdown.
"""

import json, re
from pathlib import Path
from datetime import datetime, timedelta
from collections import Counter

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

archive_reasons = data.get("archive_reasons", {})
candidates_raw  = data["candidates"]

ONSITE_STAGE_ID = "ba3541af-b2ac-4dd2-8433-660582e2924e"

# ── Interview type classifier ──────────────────────────────────────────────────
# Based purely on the interview subject line / stage tag
IV_TYPES = [
    ("Onsite",           "#c0392b", ["on-site", "onsite"]),
    ("HM Screen",        "#e67e22", ["hiring manager", "hm screen", "hm interview"]),
    ("Phone Screen",     "#f5b041", ["phone screen", "phone interview", "behavioral phone"]),
    ("Recruiter Screen", "#52be80", ["recruiter", "pre-screen", "pre screen", "sourcer"]),
    ("Technical",        "#8e44ad", ["technical", "coding", "system design", "take-home", "takehome"]),
    ("Reference",        "#7d3c98", ["reference"]),
    ("Other",            "#95a5a6", []),
]

# Stage ID → interview type (authoritative — beats keyword matching)
STAGE_TYPE_MAP = {
    "ba3541af-b2ac-4dd2-8433-660582e2924e": "Onsite",           # On-site interview
    "e35ea840-3488-402f-9f86-e062ec0a5632": "HM Screen",        # Abhinai Stage (behavioral)
    "5c476846-962c-4bcc-b299-89a7a8f909be": "HM Screen",        # Hiring Manager Screen
    "ec9dea12-d029-420b-836b-0ad5c633c4a1": "Phone Screen",     # Phone screen
    "12a60d91-1ce3-46d9-9a5d-fa403ee12aa5": "Recruiter Screen", # Recruiter Screen
    "eed7c7e4-eda1-4ea4-8ae9-7d3d2f21e7f5": "Technical",        # Assignment
    "65e31017-f862-489f-9c74-7e6f5d95d757": "Reference",        # Reference check
}

def classify_interview(iv):
    subject = iv.get("subject", "").lower()
    stage   = iv.get("stage", "")
    # Stage ID is authoritative
    if stage in STAGE_TYPE_MAP:
        return STAGE_TYPE_MAP[stage]
    # Fall back to subject keywords
    for name, color, keywords in IV_TYPES:
        if any(kw in subject for kw in keywords):
            return name
    return "Other"

IV_COLOR = {name: color for name, color, _ in IV_TYPES}

# ── Outcome colors ─────────────────────────────────────────────────────────────
OUTCOME_COLORS = {
    "Hired":                      "#1e8449",   # dark green — success
    "Offer Declined":             "#e67e22",   # orange — so close, but no
    "Active in Another Pipeline": "#2980b9",   # blue
    "Still Active":               "#5dade2",   # light blue
    "Position Closed":            "#95a5a6",   # grey
    "Timing":                     "#f5b041",   # yellow
    "Candidate Not Interested":   "#d35400",   # darker orange
    "Withdrew":                   "#c0392b",   # red
    "Unresponsive":               "#922b21",   # dark red
    "Unqualified":                "#7b241c",   # darker red
    "Role Not a Match":           "#6c3483",   # purple
    "Do Not Recruit":             "#1a1a2e",   # near-black
}

def ts(ms): return datetime.fromtimestamp(ms / 1000)

NOW = datetime.now()

# ── Parse candidates ───────────────────────────────────────────────────────────
class Candidate:
    def __init__(self, raw):
        opp = raw["opportunity"]
        self.id   = opp["id"]
        self.name = opp["name"].strip()
        self.tags = opp.get("tags", [])
        self.current_stage_id = opp.get("stage", "")
        self.created_dt = ts(opp["createdAt"]) if opp.get("createdAt") else None
        self.last_advanced_dt = ts(opp["lastAdvancedAt"]) if opp.get("lastAdvancedAt") else None

        # Outcome
        arch = opp.get("archived")
        if arch:
            reason_id = arch.get("reason", "")
            self.outcome = archive_reasons.get(reason_id, "Archived")
        else:
            self.outcome = "Still Active"

        self.contact_id = opp.get("contact", self.id)
        self.origin = opp.get("origin", "applied")  # "applied" | "sourced" | "referred"

        # Interviews (non-canceled only, past AND future)
        self.interviews = []
        for iv in raw.get("interviews", []):
            if iv.get("canceledAt") or not iv.get("date"):
                continue
            self.interviews.append({
                "dt":       ts(iv["date"]),
                "future":   ts(iv["date"]) > NOW,
                "duration": iv.get("duration", 30),   # minutes
                "subject":  iv.get("subject", ""),
                "stage":    iv.get("stage", ""),
                "type":     classify_interview(iv),
            })
        self.interviews.sort(key=lambda x: x["dt"])

        # Feedback completions
        self.feedback = [
            ts(fb["completedAt"])
            for fb in raw.get("feedback", []) if fb.get("completedAt")
        ]
        self.feedback.sort()

        # First and last interview dates
        self.first_iv_dt = self.interviews[0]["dt"]  if self.interviews else None
        self.last_iv_dt  = self.interviews[-1]["dt"] if self.interviews else None

        # Days from created → first onsite interview
        onsite_ivs = [iv for iv in self.interviews if iv["type"] == "Onsite"]
        self.first_onsite_dt = onsite_ivs[0]["dt"] if onsite_ivs else None
        self.days_to_onsite = (
            (self.first_onsite_dt - self.created_dt).days
            if (self.first_onsite_dt and self.created_dt) else None
        )


_all_candidates = [Candidate(r) for r in candidates_raw]

# Merge opportunities for the same person (same contact ID) into one row
from collections import OrderedDict
_by_contact = OrderedDict()
for c in _all_candidates:
    if c.contact_id not in _by_contact:
        _by_contact[c.contact_id] = c
    else:
        # Merge: add interviews and feedback, keep most-recent outcome/last_advanced
        existing = _by_contact[c.contact_id]
        existing.interviews = sorted(existing.interviews + c.interviews, key=lambda x: x["dt"])
        existing.feedback   = sorted(existing.feedback + c.feedback)
        if (c.last_advanced_dt or NOW) > (existing.last_advanced_dt or NOW):
            existing.last_advanced_dt = c.last_advanced_dt
            existing.outcome = c.outcome

candidates = list(_by_contact.values())
# Sort newest last-activity first (newest at top of chart)
candidates.sort(key=lambda c: -(c.last_advanced_dt.timestamp() if c.last_advanced_dt else 0))

# ── Figure layout ──────────────────────────────────────────────────────────────
N   = len(candidates)
ROW = 0.42          # inches per row in the Gantt
BAR = 0.55          # bar height (in data units)

fig = plt.figure(figsize=(24, N * ROW + 14), facecolor="#f8f9fa")
fig.suptitle(
    "Engineering Candidates — Last 50 Through On-Site Interviews",
    fontsize=20, fontweight="bold", y=0.998, color="#1a1a2e",
)

gs = GridSpec(2, 3, figure=fig,
              left=0.07, right=0.97, top=0.993, bottom=0.015,
              hspace=0.08, wspace=0.30,
              height_ratios=[N * ROW, 9])

ax_gantt   = fig.add_subplot(gs[0, :])
ax_outcome = fig.add_subplot(gs[1, 0])
ax_ivtype  = fig.add_subplot(gs[1, 1])
ax_days    = fig.add_subplot(gs[1, 2])

# ── Panel 1: Interview-driven Gantt ───────────────────────────────────────────
ax = ax_gantt
ax.set_facecolor("#ffffff")

# Date range: cover all interview dates including future ones
all_iv_dts = [iv["dt"] for c in candidates for iv in c.interviews]
if all_iv_dts:
    t_min = min(all_iv_dts) - timedelta(days=10)
    t_max = max(all_iv_dts) + timedelta(days=10)
else:
    t_min = NOW - timedelta(days=180)
    t_max = NOW + timedelta(days=30)

# One day in matplotlib date units
ONE_DAY = mdates.date2num(NOW + timedelta(days=1)) - mdates.date2num(NOW)

for row_i, cand in enumerate(candidates):
    y = (N - 1 - row_i)   # newest at top

    # Alternating row background shading
    if row_i % 2 == 0:
        ax.axhspan(y - 0.5, y + 0.5, facecolor="#f0f2f5", alpha=0.6, zorder=0)

    ivs = cand.interviews

    # "Entered system" bar — from createdAt to first interview, colored by origin
    ORIGIN_COLOR = {"applied": "#2471a3", "sourced": "#117a65", "referred": "#884ea0"}
    if cand.created_dt:
        x_applied = mdates.date2num(cand.created_dt)
        if ivs:
            x_first_iv = mdates.date2num(ivs[0]["dt"])
        else:
            x_first_iv = x_applied + ONE_DAY * 2
        origin_color = ORIGIN_COLOR.get(cand.origin, "#888888")
        ax.barh(y, x_first_iv - x_applied, left=x_applied,
                height=BAR, color=origin_color, alpha=0.45, zorder=2,
                edgecolor="white", linewidth=0.3)

    # Colored bars spanning interview-to-interview gaps
    # Each bar goes from interview[i] → interview[i+1], colored by interview[i]'s type
    for i in range(len(ivs)):
        x_start = mdates.date2num(ivs[i]["dt"])
        x_end   = mdates.date2num(ivs[i + 1]["dt"]) if i + 1 < len(ivs) else x_start + ONE_DAY * 2
        color   = IV_COLOR.get(ivs[i]["type"], "#95a5a6")
        ax.barh(y, x_end - x_start, left=x_start,
                height=BAR, color=color, edgecolor="white",
                linewidth=0.3, alpha=0.55, zorder=2)

    # Solid interview marker bars on top (short, full-opacity, show actual duration)
    for iv in ivs:
        dur_days = max(iv["duration"] / (60 * 24), 0.35)
        x_left   = mdates.date2num(iv["dt"])
        color    = IV_COLOR.get(iv["type"], "#95a5a6")
        ax.barh(y, dur_days * ONE_DAY, left=x_left,
                height=BAR, color=color, edgecolor="white",
                linewidth=0.5, zorder=3)

    # Feedback dots (below the bar)
    for fb_dt in cand.feedback:
        ax.plot(mdates.date2num(fb_dt), y - BAR / 2 - 0.1,
                marker="^", markersize=4, color="#1e8449", alpha=0.8, zorder=4)

    # Candidate name label
    short = (cand.name.split()[0] + " " + cand.name.split()[-1]
             if len(cand.name.split()) > 1 else cand.name)
    ax.text(mdates.date2num(t_min) - 0.5, y, short,
            ha="right", va="center", fontsize=7, color="#1a1a2e")

    # Outcome label: just after the last interview bar
    if ivs:
        last_iv = ivs[-1]
        dur_days = max(last_iv["duration"] / (60 * 24), 0.35)
        x_after = mdates.date2num(last_iv["dt"]) + dur_days * ONE_DAY + ONE_DAY * 0.4
    elif cand.last_advanced_dt:
        x_after = mdates.date2num(cand.last_advanced_dt) + ONE_DAY * 0.4
    else:
        x_after = mdates.date2num(t_min) + ONE_DAY
    oc_color = OUTCOME_COLORS.get(cand.outcome, "#888888")
    ax.text(x_after, y, cand.outcome,
            ha="left", va="center", fontsize=6.5,
            color=oc_color, style="italic", fontweight="bold")

# "Today" divider
ax.axvline(mdates.date2num(NOW), color="#333333", linewidth=1.2,
           linestyle="--", zorder=5, alpha=0.5)
ax.text(mdates.date2num(NOW), N - 0.2, " today",
        fontsize=7.5, color="#333333", va="top", alpha=0.7)

# Axes formatting — monthly ticks across the 2-year span
ax.xaxis_date()
ax.xaxis.set_major_locator(mdates.MonthLocator())
ax.xaxis.set_major_formatter(mdates.DateFormatter("%b '%y"))
ax.xaxis.set_minor_locator(mdates.WeekdayLocator(byweekday=0))
ax.tick_params(axis="x", which="major", labelsize=8.5, rotation=45)
ax.set_xlim(mdates.date2num(t_min), mdates.date2num(t_max))
ax.set_ylim(-1, N)
ax.set_yticks([])
ax.grid(axis="x", which="major", color="#d8d8d8", linewidth=0.8, zorder=0)
ax.grid(axis="x", which="minor", color="#efefef", linewidth=0.4, zorder=0)
ax.spines[["top", "right", "left"]].set_visible(False)
ax.set_title(
    "Interview timelines — faded bars = gap to next interview   solid bars = interview duration   ▲ = feedback submitted",
    fontsize=11, fontweight="bold", pad=6, color="#1a1a2e",
)

# Legend
legend_items = [
    mpatches.Patch(facecolor=IV_COLOR[t], label=t)
    for t, _, _ in IV_TYPES
] + [
    mlines.Line2D([], [], marker="^", color="w", markerfacecolor="#1e8449",
                  markersize=7, label="Feedback submitted"),
    mpatches.Patch(facecolor="#2471a3", alpha=0.45, label="Applied → first IV"),
    mpatches.Patch(facecolor="#117a65", alpha=0.45, label="Sourced → first IV"),
    mpatches.Patch(facecolor="#884ea0", alpha=0.45, label="Referred → first IV"),
]
ax.legend(handles=legend_items, loc="upper left", fontsize=8,
          ncol=len(legend_items), framealpha=0.9, edgecolor="#ccc")

# ── Panel 2: Outcome distribution ─────────────────────────────────────────────
ax = ax_outcome
ax.set_facecolor("#ffffff")

outcome_counts = Counter(c.outcome for c in candidates)
items = sorted(outcome_counts.items(), key=lambda x: x[1])
labels, vals = zip(*items)
colors = [OUTCOME_COLORS.get(l, "#888") for l in labels]

bars = ax.barh(range(len(labels)), vals, color=colors, edgecolor="white", height=0.65)
ax.set_yticks(range(len(labels)))
ax.set_yticklabels(labels, fontsize=9)
ax.set_xlabel("# candidates", fontsize=9)
ax.set_title(f"Outcomes  (n={N})", fontsize=10, fontweight="bold", pad=4)
ax.spines[["top", "right"]].set_visible(False)
ax.grid(axis="x", color="#eeeeee")
for bar, val in zip(bars, vals):
    ax.text(val + 0.1, bar.get_y() + bar.get_height() / 2,
            str(val), va="center", fontsize=9, fontweight="bold")

# ── Panel 3: Interview type counts per candidate (stacked) ────────────────────
ax = ax_ivtype
ax.set_facecolor("#ffffff")

iv_type_names = [t for t, _, _ in IV_TYPES if t != "Other"]
iv_type_names.append("Other")

# Count per type for all candidates combined.
# For "Onsite": count distinct onsite DAYS per candidate (not individual slots),
# since a single onsite day contains many back-to-back interview events.
type_totals = Counter()
for c in candidates:
    onsite_days_seen = set()
    for iv in c.interviews:
        if iv["type"] == "Onsite":
            day_key = iv["dt"].date()
            if day_key not in onsite_days_seen:
                onsite_days_seen.add(day_key)
                type_totals["Onsite"] += 1
        else:
            type_totals[iv["type"]] += 1

type_order = sorted(type_totals.items(), key=lambda x: -x[1])
t_labels = [t for t, _ in type_order]
t_vals   = [v for _, v in type_order]
t_colors = [IV_COLOR.get(t, "#888") for t in t_labels]

bars = ax.barh(range(len(t_labels)), t_vals, color=t_colors, edgecolor="white", height=0.65)
ax.set_yticks(range(len(t_labels)))
ax.set_yticklabels(t_labels, fontsize=9)
ax.invert_yaxis()
ax.set_xlabel("Total interviews conducted", fontsize=9)
ax.set_title("Interview Volume by Type\n(Onsite = days; all others = individual events)", fontsize=10, fontweight="bold", pad=4)
ax.spines[["top", "right"]].set_visible(False)
ax.grid(axis="x", color="#eeeeee")
ax.set_xlim(0, max(t_vals) + 5)
for bar, val in zip(bars, t_vals):
    ax.text(val + 0.3, bar.get_y() + bar.get_height() / 2,
            str(val), va="center", fontsize=9, fontweight="bold")

# ── Panel 4: Days from created → first onsite interview ───────────────────────
ax = ax_days
ax.set_facecolor("#ffffff")

days_data = [(c.name.split()[0], c.days_to_onsite, c.outcome)
             for c in candidates if c.days_to_onsite is not None]
days_data.sort(key=lambda x: -x[1])  # sorted longest to shortest

names_d = [d[0] for d in days_data]
vals_d  = [d[1] for d in days_data]
colors_d = [OUTCOME_COLORS.get(d[2], "#888") for d in days_data]

bars = ax.barh(range(len(names_d)), vals_d, color=colors_d, edgecolor="white", height=0.65)
ax.set_yticks(range(len(names_d)))
ax.set_yticklabels(names_d, fontsize=7.5)
ax.set_xlabel("Days from first contact → onsite", fontsize=9)
ax.set_title("Time to Onsite (days)\ncoloured by outcome", fontsize=10, fontweight="bold", pad=4)
ax.spines[["top", "right"]].set_visible(False)
ax.grid(axis="x", color="#eeeeee")

if vals_d:
    med = float(np.median(vals_d))
    ax.axvline(med, color="#555", linestyle="--", linewidth=1.2)
    ax.text(med + 0.5, len(names_d) - 0.5, f"Median\n{med:.0f}d",
            va="top", fontsize=8, color="#555")

legend_els = [mpatches.Patch(facecolor=v, label=k)
              for k, v in OUTCOME_COLORS.items() if k in outcome_counts]
ax.legend(handles=legend_els, loc="lower right", fontsize=7, framealpha=0.85)

# ── Footer ─────────────────────────────────────────────────────────────────────
fig.text(
    0.5, 0.001,
    f"Data from Lever  •  Downloaded {data['downloaded_at'][:10]}  "
    f"•  {data.get('total_eng_onsite_candidates', N)} total engineering onsite candidates  "
    f"•  Showing 50 most recent by last activity",
    ha="center", fontsize=8, color="#888", style="italic",
)

# ── Save ───────────────────────────────────────────────────────────────────────
OUT = Path("/sessions/lucid-happy-edison/mnt/lever/onsite_pipeline_analysis.png")
plt.savefig(OUT, dpi=140, bbox_inches="tight", facecolor=fig.get_facecolor())
print(f"Saved → {OUT}")
