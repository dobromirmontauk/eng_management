"""
Download all engineering candidates who reached the onsite stage from Lever.
Saves raw data locally as JSON for later analysis/visualization.
"""

import asyncio
import json
import os
import sys
import time
from datetime import datetime
from pathlib import Path

import httpx

API_KEY = os.environ.get("LEVER_API_KEY")
if not API_KEY:
    # Try loading from .env file
    env_file = Path(__file__).parent / "mnt/lever/.env"
    if env_file.exists():
        for line in env_file.read_text().splitlines():
            if line.startswith("LEVER_API_KEY="):
                API_KEY = line.split("=", 1)[1].strip()
                break

if not API_KEY:
    print("ERROR: LEVER_API_KEY not found")
    sys.exit(1)

BASE_URL = "https://api.lever.co/v1"
ONSITE_STAGE_ID = "ba3541af-b2ac-4dd2-8433-660582e2924e"
OUTPUT_DIR = Path("/sessions/lucid-happy-edison/mnt/lever")

# Engineering keywords to identify engineering job postings
ENG_KEYWORDS = [
    "engineer", "developer", "software", "hardware", "backend", "frontend",
    "fullstack", "full-stack", "full stack", "infrastructure", "devops",
    "machine learning", "computer vision", "deep learning", "technical lead",
    "architect", "firmware", "electrical", "mechanical", "platform", "embedded",
    "data engineer", "ai developer"
]

client = httpx.Client(base_url=BASE_URL, auth=(API_KEY, ""), timeout=60.0)


def rate_limited_get(endpoint, params=None, retries=3):
    """GET with rate-limit retry logic."""
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
    """Fetch all pages from a paginated Lever endpoint."""
    params = params or {}
    items = []
    offset = None
    page = 1
    while True:
        p = dict(params)
        if offset:
            p["offset"] = offset
        data = rate_limited_get(endpoint, params=p)
        items.extend(data.get("data", []))
        if data.get("hasNext"):
            offset = data.get("next")
            page += 1
        else:
            break
    return items


def get_engineering_posting_ids(all_postings):
    """Filter postings to only engineering roles."""
    eng_ids = []
    for p in all_postings:
        title = p.get("text", "").lower()
        if any(kw in title for kw in ENG_KEYWORDS):
            eng_ids.append(p["id"])
    return eng_ids


def is_onsite_candidate(opportunity):
    """Check if this candidate ever reached the onsite stage."""
    for change in opportunity.get("stageChanges", []):
        if change.get("toStageId") == ONSITE_STAGE_ID:
            return True
    return False


def fetch_interviews(opp_id):
    """Fetch all interviews for an opportunity."""
    try:
        return get_all_pages(f"/opportunities/{opp_id}/interviews")
    except Exception as e:
        print(f"    Warning: could not fetch interviews for {opp_id}: {e}")
        return []


def fetch_feedback(opp_id):
    """Fetch all feedback forms for an opportunity."""
    try:
        return get_all_pages(f"/opportunities/{opp_id}/feedback")
    except Exception as e:
        print(f"    Warning: could not fetch feedback for {opp_id}: {e}")
        return []


def fetch_notes(opp_id):
    """Fetch notes for an opportunity."""
    try:
        return get_all_pages(f"/opportunities/{opp_id}/notes")
    except Exception as e:
        print(f"    Warning: could not fetch notes for {opp_id}: {e}")
        return []


def main():
    print("=" * 60)
    print("Lever Engineering Onsite Candidate Data Downloader")
    print("=" * 60)

    # Step 1: Get all postings (published + closed + internal)
    print("\n[1/5] Fetching all job postings...")
    all_postings = []
    for state in ["published", "closed", "internal", "draft"]:
        p = get_all_pages("/postings", params={"state": state})
        all_postings.extend(p)
    print(f"  Total postings: {len(all_postings)}")

    eng_posting_ids = get_engineering_posting_ids(all_postings)
    print(f"  Engineering postings: {len(eng_posting_ids)}")

    # Build posting name lookup
    posting_names = {p["id"]: p.get("text", p["id"]) for p in all_postings}

    # Step 2: Get all stages metadata
    print("\n[2/5] Fetching stage metadata...")
    stages_data = rate_limited_get("/stages")
    stages = {s["id"]: s["text"] for s in stages_data.get("data", [])}
    # Add built-in stages
    stages.update({
        "lead-new": "New lead",
        "lead-reached-out": "Reached out",
        "lead-responded": "Responded",
        "applicant-new": "New applicant",
        "offer": "Offer",
    })
    print(f"  Stages: {list(stages.values())}")

    # Step 3: Fetch ALL opportunities for engineering postings
    # Must include both active AND archived since most onsite candidates are archived
    print("\n[3/5] Fetching opportunities for engineering postings...")
    print(f"  (Fetching both active and archived, across {len(eng_posting_ids)} postings)")

    all_opps = []
    # Lever allows filtering by posting_id in batches
    # We'll fetch in chunks of 10 posting IDs to avoid too-long URLs
    CHUNK = 10
    total_fetched = 0
    for i in range(0, len(eng_posting_ids), CHUNK):
        chunk_ids = eng_posting_ids[i:i + CHUNK]
        # Fetch active
        params_active = {"posting_id[]": chunk_ids, "limit": 100}
        chunk_active = get_all_pages("/opportunities", params=params_active)
        # Fetch archived
        params_archived = {"posting_id[]": chunk_ids, "limit": 100, "archived": "true"}
        chunk_archived = get_all_pages("/opportunities", params=params_archived)

        all_opps.extend(chunk_active)
        all_opps.extend(chunk_archived)
        total_fetched += len(chunk_active) + len(chunk_archived)
        print(f"  Chunk {i//CHUNK + 1}/{(len(eng_posting_ids)+CHUNK-1)//CHUNK}: "
              f"+{len(chunk_active)} active, +{len(chunk_archived)} archived "
              f"(total so far: {total_fetched})")

    # Deduplicate by ID (a candidate can be in multiple postings)
    seen_ids = set()
    unique_opps = []
    for opp in all_opps:
        if opp["id"] not in seen_ids:
            seen_ids.add(opp["id"])
            unique_opps.append(opp)
    print(f"  Unique opportunities: {len(unique_opps)}")

    # Step 4: Filter for onsite candidates
    print("\n[4/5] Filtering for candidates who reached onsite...")
    onsite_candidates = [opp for opp in unique_opps if is_onsite_candidate(opp)]
    print(f"  Onsite candidates: {len(onsite_candidates)}")

    # Step 5: Fetch interviews + feedback for each onsite candidate
    print(f"\n[5/5] Fetching interviews & feedback for {len(onsite_candidates)} candidates...")
    enriched = []
    for i, opp in enumerate(onsite_candidates):
        name = opp.get("name", "Unknown")
        opp_id = opp["id"]
        print(f"  [{i+1}/{len(onsite_candidates)}] {name} ({opp_id[:8]}...)")

        interviews = fetch_interviews(opp_id)
        feedback = fetch_feedback(opp_id)

        enriched.append({
            "opportunity": opp,
            "interviews": interviews,
            "feedback": feedback,
        })

    # Save everything
    print("\n--- Saving data ---")
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    output = {
        "downloaded_at": datetime.now().isoformat(),
        "onsite_stage_id": ONSITE_STAGE_ID,
        "stages": stages,
        "posting_names": posting_names,
        "candidates": enriched,
    }

    out_path = OUTPUT_DIR / f"onsite_candidates_{timestamp}.json"
    out_path.write_text(json.dumps(output, indent=2))
    # Also write a "latest" symlink-style file for easy access
    latest_path = OUTPUT_DIR / "onsite_candidates_latest.json"
    latest_path.write_text(json.dumps(output, indent=2))

    print(f"\n✓ Saved {len(enriched)} candidates to:")
    print(f"  {out_path}")
    print(f"  {latest_path}  (also written as 'latest')")

    # Quick summary stats
    print(f"\n=== Summary ===")
    print(f"  Total engineering postings:  {len(eng_posting_ids)}")
    print(f"  Total opportunities fetched: {len(unique_opps)}")
    print(f"  Reached onsite stage:        {len(onsite_candidates)}")
    archived_onsite = sum(1 for c in onsite_candidates if c["opportunity"].get("archived"))
    print(f"  Archived (no longer active): {archived_onsite}")
    print(f"  Still active in pipeline:    {len(onsite_candidates) - archived_onsite}")


if __name__ == "__main__":
    main()
