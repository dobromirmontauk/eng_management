"""
Download last 50 engineering candidates who went through On-site interviews.
Approach: query by stage_id (current stage) across all post-onsite stages,
filter to engineering roles, sort by lastAdvancedAt, take top 50, enrich.
"""

import json
import os
import sys
import time
from datetime import datetime
from pathlib import Path

import httpx

API_KEY = os.environ.get("LEVER_API_KEY")
if not API_KEY:
    env_file = Path(__file__).parent / "mnt/lever/.env"
    if env_file.exists():
        for line in env_file.read_text().splitlines():
            if line.startswith("LEVER_API_KEY="):
                API_KEY = line.split("=", 1)[1].strip()
if not API_KEY:
    print("ERROR: LEVER_API_KEY not found"); sys.exit(1)

BASE_URL = "https://api.lever.co/v1"
ONSITE_STAGE_ID = "ba3541af-b2ac-4dd2-8433-660582e2924e"
OUTPUT_DIR = Path("/sessions/lucid-happy-edison/mnt/lever")

# All stages at/after onsite — candidates at these stages have been through onsite
ONSITE_AND_BEYOND = {
    "ba3541af-b2ac-4dd2-8433-660582e2924e": "On-site interview",
    "e35ea840-3488-402f-9f86-e062ec0a5632": "Abhinai Stage",
    "65e31017-f862-489f-9c74-7e6f5d95d757": "Reference check",
    "offer": "Offer",
}

ENG_KEYWORDS = [
    "engineer", "developer", "software", "hardware", "backend", "frontend",
    "fullstack", "full-stack", "full stack", "infrastructure", "devops",
    "machine learning", "computer vision", "deep learning", "technical lead",
    "architect", "firmware", "electrical", "mechanical", "platform", "embedded",
    "data engineer", "ai developer", "builder"
]

client = httpx.Client(base_url=BASE_URL, auth=(API_KEY, ""), timeout=60.0)


def rate_limited_get(endpoint, params=None, retries=3):
    for attempt in range(retries):
        r = client.get(endpoint, params=params)
        if r.status_code == 429:
            wait = int(r.headers.get("Retry-After", 10))
            print(f"  Rate limited, waiting {wait}s...")
            time.sleep(wait)
            continue
        r.raise_for_status()
        return r.json()
    raise Exception(f"Failed after {retries} retries: {endpoint}")


def get_all_pages(endpoint, params=None):
    params = params or {}
    items = []
    offset = None
    while True:
        p = dict(params)
        if offset:
            p["offset"] = offset
        data = rate_limited_get(endpoint, params=p)
        items.extend(data.get("data", []))
        if data.get("hasNext"):
            offset = data.get("next")
        else:
            break
    return items


def is_engineering_candidate(opp, eng_posting_ids=None):
    """Check if candidate is for an engineering role, using tags (job title is first tag)."""
    tag_str = " ".join(t.lower() for t in opp.get("tags", []))
    return any(kw in tag_str for kw in ENG_KEYWORDS)


def fetch_interviews(opp_id):
    try:
        return get_all_pages(f"/opportunities/{opp_id}/interviews")
    except Exception as e:
        print(f"    Warning: interviews for {opp_id}: {e}")
        return []


def fetch_feedback(opp_id):
    try:
        return get_all_pages(f"/opportunities/{opp_id}/feedback")
    except Exception as e:
        print(f"    Warning: feedback for {opp_id}: {e}")
        return []


def main():
    print("=" * 60)
    print("Lever: Last 50 Engineering Onsite Candidates (v2)")
    print("=" * 60)

    # Step 1: Engineering posting IDs
    print("\n[1/5] Loading engineering postings...")
    all_postings = []
    for state in ["published", "closed", "internal", "draft"]:
        all_postings.extend(get_all_pages("/postings", params={"state": state}))
    eng_posting_ids = {
        p["id"] for p in all_postings
        if any(kw in p.get("text", "").lower() for kw in ENG_KEYWORDS)
    }
    posting_names = {p["id"]: p.get("text", p["id"]) for p in all_postings}
    print(f"  Total postings: {len(all_postings)}, Engineering: {len(eng_posting_ids)}")

    # Step 2: Stage metadata + archive reasons
    print("\n[2/5] Loading metadata...")
    stages_data = rate_limited_get("/stages")
    stages = {s["id"]: s["text"] for s in stages_data.get("data", [])}
    stages.update({
        "lead-new": "New lead", "lead-reached-out": "Reached out",
        "lead-responded": "Responded", "applicant-new": "New applicant",
        "offer": "Offer",
    })
    archive_data = rate_limited_get("/archive_reasons")
    archive_reasons = {r["id"]: r["text"] for r in archive_data.get("data", [])}

    # Step 3: Fetch all candidates at onsite-or-beyond stages
    print("\n[3/5] Fetching all candidates at onsite+ stages...")
    all_opps = {}
    for stage_id, stage_name in ONSITE_AND_BEYOND.items():
        for archived_val in ["false", "true"]:
            opps = get_all_pages("/opportunities", params={
                "limit": 100,
                "stage_id": stage_id,
                "archived": archived_val,
            })
            for opp in opps:
                all_opps[opp["id"]] = opp
            label = "active" if archived_val == "false" else "archived"
            print(f"  {stage_name} ({label}): {len(opps)}")

    print(f"  Total unique candidates: {len(all_opps)}")

    # Step 4: Filter to engineering + sort by lastAdvancedAt
    print("\n[4/5] Filtering to engineering roles...")
    eng_opps = [
        opp for opp in all_opps.values()
        if is_engineering_candidate(opp)
    ]
    print(f"  Engineering candidates at onsite+: {len(eng_opps)}")

    # Sort by lastAdvancedAt descending (most recently active first)
    eng_opps.sort(key=lambda x: -(x.get("lastAdvancedAt") or 0))

    # Take top 50
    top_50 = eng_opps[:50]
    print(f"  Taking top 50 most recent (lastAdvancedAt)")

    # Print summary of who we're including
    for i, opp in enumerate(top_50):
        last_adv = datetime.fromtimestamp(opp["lastAdvancedAt"]/1000).strftime("%Y-%m-%d") if opp.get("lastAdvancedAt") else "N/A"
        archived = opp.get("archived")
        reason = archive_reasons.get(archived.get("reason",""), archived.get("reason","")) if archived else "Active"
        apps = opp.get("applications", [])
        posting = posting_names.get(
            apps[0].get("posting","") if apps and isinstance(apps[0],dict) else "",
            "Unknown posting"
        )
        print(f"  [{i+1:2d}] {opp['name'][:32]:32} | {last_adv} | {reason[:25]} | {posting[:30]}")

    # Step 5: Enrich with interviews and feedback
    print(f"\n[5/5] Fetching interviews & feedback for {len(top_50)} candidates...")
    enriched = []
    for i, opp in enumerate(top_50):
        name = opp.get("name", "Unknown").strip()
        opp_id = opp["id"]
        print(f"  [{i+1}/{len(top_50)}] {name} ({opp_id[:8]}...)")
        interviews = fetch_interviews(opp_id)
        feedback = fetch_feedback(opp_id)
        enriched.append({
            "opportunity": opp,
            "interviews": interviews,
            "feedback": feedback,
        })

    # Save
    print("\n--- Saving ---")
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    output = {
        "downloaded_at": datetime.now().isoformat(),
        "version": "v2",
        "onsite_stage_id": ONSITE_STAGE_ID,
        "stages": stages,
        "archive_reasons": archive_reasons,
        "posting_names": posting_names,
        "total_eng_onsite_candidates": len(eng_opps),
        "candidates": enriched,
    }
    out_path = OUTPUT_DIR / f"onsite_candidates_top50_{timestamp}.json"
    latest_path = OUTPUT_DIR / "onsite_candidates_latest.json"
    out_path.write_text(json.dumps(output, indent=2))
    latest_path.write_text(json.dumps(output, indent=2))

    print(f"\n✓ Saved {len(enriched)} candidates to:")
    print(f"  {out_path}")
    print(f"  {latest_path}  (latest)")

    # Summary stats
    active = sum(1 for c in enriched if not c["opportunity"].get("archived"))
    archived_count = len(enriched) - active
    final_stages = {}
    for c in enriched:
        s = c["opportunity"].get("stage", "?")
        final_stages[stages.get(s, s)] = final_stages.get(stages.get(s, s), 0) + 1
    outcomes = {}
    for c in enriched:
        arch = c["opportunity"].get("archived")
        reason = archive_reasons.get(arch.get("reason",""), arch.get("reason","unknown")) if arch else "Still Active"
        outcomes[reason] = outcomes.get(reason, 0) + 1

    print(f"\n=== Summary ===")
    print(f"  Total eng candidates who reached onsite: {len(eng_opps)}")
    print(f"  Showing most recent 50:  {len(enriched)}")
    print(f"  Still active: {active} | Archived: {archived_count}")
    print(f"  Final stages:  {final_stages}")
    print(f"  Outcomes:")
    for reason, count in sorted(outcomes.items(), key=lambda x: -x[1]):
        print(f"    {reason}: {count}")


if __name__ == "__main__":
    main()
