"""
Download last 50 software engineering candidates who went through On-site interviews.
Approach: query by the explicit posting IDs from review_eng.sh (active + archived),
keep only those who reached the onsite stage or beyond, sort by lastAdvancedAt, enrich.
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

# Software engineering posting IDs — sourced directly from review_eng.sh
SW_ENG_POSTING_IDS = [
    "a28b2c47-17dd-4e34-88a3-a31e0bc40902",
    "d7a3d123-e0ff-4563-bf4c-b336124ca0ee",
    "19a14c15-5e89-4fb2-be7a-5c1be01ba952",
    "f3176417-e303-4bff-a17c-59715534bd26",
    "da733114-d2b5-4abf-92e3-c034ce970a86",
    "f7f9e38b-c319-4c85-aac3-50e08d888ebd",
    "e1c61f69-a670-46cc-ac1c-1840dac4bc53",
    "65f070bd-9864-4053-b46c-f512e9b513bb",
    "254cf2cb-4013-44e4-b13e-cf0707f49ee3",
    "3621bdb7-757a-4402-8657-7e8c9237235b",
    "61092a1a-3e1b-4b70-8384-7abf807774e8",
    "f82e7b37-9e91-416e-97b6-64449ab28f48",
    "8063b092-4081-46db-8eee-df07f647b467",
    "48b78db5-49c6-4e2b-9cf2-e2282da615ae",
    "a2cd54bf-7a30-4ecb-ba62-755094100b27",
]

ONSITE_STAGE_IDS = {
    "ba3541af-b2ac-4dd2-8433-660582e2924e",  # On-site interview
    "e35ea840-3488-402f-9f86-e062ec0a5632",  # Abhinai Stage (post-onsite)
    "65e31017-f862-489f-9c74-7e6f5d95d757",  # Reference check
    "offer",
}

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


def reached_onsite(opp):
    """Return True if the candidate's current stage is onsite or beyond."""
    return opp.get("stage", "") in ONSITE_STAGE_IDS


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

    # Step 1: Posting names for display
    print("\n[1/5] Loading posting metadata...")
    all_postings = []
    for state in ["published", "closed", "internal", "draft"]:
        all_postings.extend(get_all_pages("/postings", params={"state": state}))
    posting_names = {p["id"]: p.get("text", p["id"]) for p in all_postings}
    sw_eng_names = {pid: posting_names.get(pid, pid[:8]) for pid in SW_ENG_POSTING_IDS}
    print(f"  SW eng postings ({len(SW_ENG_POSTING_IDS)}):")
    for pid, name in sw_eng_names.items():
        print(f"    {name}")

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

    SW_ENG_POSTING_SET = set(SW_ENG_POSTING_IDS)

    # Step 3: Fetch all onsite+ candidates (active + archived) with applications expanded
    # posting_id filter silently drops archived candidates, so we query by stage_id instead
    # and use expand=applications to get the posting ID inline for filtering.
    print("\n[3/5] Fetching all onsite+ candidates (active + archived) with posting info...")
    ONSITE_AND_BEYOND = {
        "ba3541af-b2ac-4dd2-8433-660582e2924e": "On-site interview",
        "e35ea840-3488-402f-9f86-e062ec0a5632": "Abhinai Stage",
        "65e31017-f862-489f-9c74-7e6f5d95d757": "Reference check",
        "offer": "Offer",
    }
    all_opps = {}
    for stage_id, stage_name in ONSITE_AND_BEYOND.items():
        for archived_val in ["false", "true"]:
            opps = get_all_pages("/opportunities", params={
                "limit": 100,
                "stage_id": stage_id,
                "archived": archived_val,
                "expand": "applications",
            })
            for opp in opps:
                all_opps[opp["id"]] = opp
            label = "active" if archived_val == "false" else "archived"
            print(f"  {stage_name} ({label}): {len(opps)}")

    print(f"  Total unique onsite+ candidates: {len(all_opps)}")

    # Step 4: Filter to SW eng postings using the expanded applications.posting field
    print("\n[4/5] Filtering to SW eng postings...")
    def is_sw_eng(opp):
        for app in opp.get("applications", []):
            if isinstance(app, dict) and app.get("posting") in SW_ENG_POSTING_SET:
                return True
        return False

    eng_opps = [opp for opp in all_opps.values() if is_sw_eng(opp)]
    print(f"  SW eng candidates who reached onsite+: {len(eng_opps)}")

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
        "version": "v3",
        "sw_eng_posting_ids": SW_ENG_POSTING_IDS,
        "onsite_stage_ids": list(ONSITE_STAGE_IDS),
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
