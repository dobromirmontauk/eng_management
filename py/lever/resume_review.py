"""
Lever Resume Review Tool

Fetches candidates from a Lever pipeline stage, downloads their resume PDFs,
grades them using Claude, and prints a summary.

Usage:
    export LEVER_API_KEY="your-lever-api-key"
    export ANTHROPIC_API_KEY="your-anthropic-api-key"
    python resume_review.py --prompt-file prompts/example_grading.txt --limit 5
"""

import os
import sys
import json
import time
import base64
import argparse
from dataclasses import dataclass
from typing import Optional

import requests
from requests.auth import HTTPBasicAuth
import anthropic

LEVER_BASE_URL = "https://api.lever.co/v1"


# --- Lever API helpers ---

def get_lever_auth() -> HTTPBasicAuth:
    api_key = os.environ.get("LEVER_API_KEY")
    if not api_key:
        print("Error: LEVER_API_KEY environment variable is required.")
        sys.exit(1)
    return HTTPBasicAuth(username=api_key, password="")


def lever_get(endpoint: str, params: dict = None) -> dict:
    url = f"{LEVER_BASE_URL}{endpoint}"
    response = requests.get(url, auth=get_lever_auth(), params=params)
    if response.status_code == 429:
        retry_after = int(response.headers.get("Retry-After", 10))
        print(f"  Rate limited. Waiting {retry_after}s...")
        time.sleep(retry_after)
        response = requests.get(url, auth=get_lever_auth(), params=params)
    response.raise_for_status()
    return response.json()


def lever_put(endpoint: str, json_body: dict) -> dict:
    url = f"{LEVER_BASE_URL}{endpoint}"
    response = requests.put(url, auth=get_lever_auth(), json=json_body)
    if response.status_code == 429:
        retry_after = int(response.headers.get("Retry-After", 10))
        print(f"  Rate limited. Waiting {retry_after}s...")
        time.sleep(retry_after)
        response = requests.put(url, auth=get_lever_auth(), json=json_body)
    response.raise_for_status()
    return response.json()


def lever_post(endpoint: str, json_body: dict) -> dict:
    url = f"{LEVER_BASE_URL}{endpoint}"
    response = requests.post(url, auth=get_lever_auth(), json=json_body)
    if response.status_code == 429:
        retry_after = int(response.headers.get("Retry-After", 10))
        print(f"  Rate limited. Waiting {retry_after}s...")
        time.sleep(retry_after)
        response = requests.post(url, auth=get_lever_auth(), json=json_body)
    response.raise_for_status()
    return response.json()


def lever_get_binary(endpoint: str) -> bytes:
    url = f"{LEVER_BASE_URL}{endpoint}"
    response = requests.get(url, auth=get_lever_auth())
    if response.status_code == 429:
        retry_after = int(response.headers.get("Retry-After", 10))
        print(f"  Rate limited. Waiting {retry_after}s...")
        time.sleep(retry_after)
        response = requests.get(url, auth=get_lever_auth())
    response.raise_for_status()
    return response.content


# --- Lever domain functions ---

def find_stage_id(stage_name: str) -> str:
    data = lever_get("/stages")
    for stage in data["data"]:
        if stage["text"].lower() == stage_name.lower():
            return stage["id"]
    available = [s["text"] for s in data["data"]]
    print(f"Error: Stage '{stage_name}' not found. Available stages: {available}")
    sys.exit(1)


def find_archive_reason_id(reason_text: str) -> str:
    data = lever_get("/archive_reasons")
    for reason in data["data"]:
        if reason["text"].lower() == reason_text.lower():
            return reason["id"]
    available = [r["text"] for r in data["data"]]
    print(f"Error: Archive reason '{reason_text}' not found. Available: {available}")
    sys.exit(1)


def get_opportunities(stage_id: str, posting_ids: Optional[list] = None,
                       limit: Optional[int] = None) -> list:
    opportunities = []
    offset = None
    while True:
        params = {"stage_id": stage_id, "archived": "false"}
        if posting_ids:
            params["posting_id"] = posting_ids
        if offset:
            params["offset"] = offset
        data = lever_get("/opportunities", params=params)
        opportunities.extend(data["data"])
        if limit and len(opportunities) >= limit:
            return opportunities[:limit]
        if data.get("hasNext"):
            offset = data.get("next")
        else:
            break
    return opportunities


def advance_opportunity(opportunity_id: str, target_stage_id: str):
    lever_put(f"/opportunities/{opportunity_id}/stage", {"stage": target_stage_id})


def archive_opportunity(opportunity_id: str, reason_id: str):
    lever_put(f"/opportunities/{opportunity_id}/archived", {"reason": reason_id})


def add_note(opportunity_id: str, text: str):
    lever_post(f"/opportunities/{opportunity_id}/notes", {"value": text})


def download_resume_pdf(opportunity_id: str) -> Optional[bytes]:
    data = lever_get(f"/opportunities/{opportunity_id}/resumes")
    resumes = data.get("data", [])
    if not resumes:
        return None
    resume_id = resumes[0]["id"]
    return lever_get_binary(
        f"/opportunities/{opportunity_id}/resumes/{resume_id}/download"
    )


# --- Claude grading ---

CRITERIA_KEYS = ["school", "pedigree", "startup", "shipped", "career", "published"]
CRITERIA_HEADERS = ["Schl", "Pdgr", "Strt", "Ship", "Crer", "Publ"]


@dataclass
class GradeResult:
    score: float
    scores: dict  # per-criterion scores keyed by CRITERIA_KEYS
    reasoning: str
    raw_response: str


def grade_resume(pdf_bytes: bytes, grading_prompt: str, candidate_name: str,
                  job_description: Optional[str] = None,
                  model: str = "claude-sonnet-4-6") -> Optional[GradeResult]:
    client = anthropic.Anthropic()

    pdf_b64 = base64.standard_b64encode(pdf_bytes).decode("utf-8")

    system_prompt = """You are a resume reviewer. You will be given a resume PDF, grading criteria, and optionally a job description.
Evaluate the resume against the criteria and respond with ONLY a JSON object in this exact format:
{
    "scores": {
        "school": <number>,
        "pedigree": <number>,
        "startup": <number>,
        "shipped": <number>,
        "career": <number>,
        "published": <number>
    },
    "reasoning": "2-3 sentence explanation of your assessment"
}
Each score should match the points defined in the grading criteria. The total is the sum of all scores.
Do not include any other text before or after the JSON."""

    user_text = f"Candidate name: {candidate_name}\n\n"
    if job_description:
        user_text += f"Job description:\n{job_description}\n\n"
    user_text += f"Grading criteria:\n{grading_prompt}"

    message = client.messages.create(
        model=model,
        max_tokens=1024,
        system=system_prompt,
        messages=[
            {
                "role": "user",
                "content": [
                    {
                        "type": "document",
                        "source": {
                            "type": "base64",
                            "media_type": "application/pdf",
                            "data": pdf_b64,
                        },
                    },
                    {
                        "type": "text",
                        "text": user_text,
                    },
                ],
            }
        ],
    )

    raw_text = message.content[0].text
    # Strip markdown code fences if present
    cleaned = raw_text.strip()
    if cleaned.startswith("```"):
        cleaned = cleaned.split("\n", 1)[1] if "\n" in cleaned else cleaned[3:]
        if cleaned.endswith("```"):
            cleaned = cleaned[:-3]
        cleaned = cleaned.strip()
    try:
        result = json.loads(cleaned)
        scores = result["scores"]
        total = sum(scores.get(k, 0) for k in CRITERIA_KEYS)
        return GradeResult(
            score=total,
            scores=scores,
            reasoning=result["reasoning"],
            raw_response=raw_text,
        )
    except (json.JSONDecodeError, KeyError) as e:
        print(f"  Warning: Could not parse Claude response: {e}")
        print(f"  Raw response: {raw_text[:200]}")
        return None


# --- Main ---

def main():
    parser = argparse.ArgumentParser(
        description="Review resumes from Lever using Claude AI"
    )
    parser.add_argument("--prompt-file", required=True,
                        help="Path to the grading criteria prompt file")
    parser.add_argument("--job-file", default=None,
                        help="Path to a job description file (provides role context for grading)")
    parser.add_argument("--stage-name", default="New applicant",
                        help="Pipeline stage to pull candidates from (default: 'New applicant')")
    parser.add_argument("--pass-threshold", type=float, default=4,
                        help="Minimum score to pass (default: 4)")
    parser.add_argument("--advance-qualified", action="store_true", default=False,
                        help="Advance passing candidates to the next stage")
    parser.add_argument("--advance-stage-name", default="Recruiter Screen",
                        help="Stage to advance qualified candidates to (default: 'Recruiter Screen')")
    parser.add_argument("--archive-below", type=float, default=None,
                        help="Archive candidates scoring at or below this threshold (e.g. --archive-below 2)")
    parser.add_argument("--archive-reason-text", default="Unqualified",
                        help="Archive reason for archived candidates (default: 'Unqualified')")
    parser.add_argument("--model", default="claude-sonnet-4-6",
                        help="Claude model for grading. Options: "
                             "claude-opus-4-6 ($5/$25 per MTok, most capable), "
                             "claude-sonnet-4-6 ($3/$15, best speed/quality balance, default), "
                             "claude-haiku-4-5-20251001 ($1/$5, fastest/cheapest)")
    parser.add_argument("--posting-ids", nargs="+", default=None,
                        help="Only process candidates for these posting IDs (space-separated)")
    parser.add_argument("--limit", type=int, default=None,
                        help="Maximum number of candidates to process")
    parser.add_argument("--verbose", action="store_true",
                        help="Print full Claude responses")
    args = parser.parse_args()

    # Load grading prompt
    try:
        with open(args.prompt_file, "r") as f:
            grading_prompt = f.read()
    except FileNotFoundError:
        print(f"Error: Prompt file not found: {args.prompt_file}")
        sys.exit(1)

    # Load job description
    job_description = None
    if args.job_file:
        try:
            with open(args.job_file, "r") as f:
                job_description = f.read()
        except FileNotFoundError:
            print(f"Error: Job description file not found: {args.job_file}")
            sys.exit(1)

    # Validate env vars
    if not os.environ.get("LEVER_API_KEY"):
        print("Error: LEVER_API_KEY environment variable is required.")
        sys.exit(1)
    if not os.environ.get("ANTHROPIC_API_KEY"):
        print("Error: ANTHROPIC_API_KEY environment variable is required.")
        sys.exit(1)

    # Resolve stage and action targets
    print(f"Finding stage '{args.stage_name}'...")
    source_stage_id = find_stage_id(args.stage_name)

    target_stage_id = None
    if args.advance_qualified:
        print(f"Finding advance target stage '{args.advance_stage_name}'...")
        target_stage_id = find_stage_id(args.advance_stage_name)

    archive_reason_id = None
    if args.archive_below is not None:
        print(f"Finding archive reason '{args.archive_reason_text}'...")
        archive_reason_id = find_archive_reason_id(args.archive_reason_text)

    # Fetch candidates
    if args.posting_ids:
        print(f"Fetching candidates in stage '{args.stage_name}' for {len(args.posting_ids)} posting(s)...")
    else:
        print(f"Fetching candidates in stage '{args.stage_name}' (all postings)...")
    opportunities = get_opportunities(source_stage_id, posting_ids=args.posting_ids, limit=args.limit)
    print(f"Found {len(opportunities)} candidate(s).\n")

    if not opportunities:
        print("No candidates to review.")
        return

    # Process each candidate
    results = []
    for i, opp in enumerate(opportunities, 1):
        name = opp.get("name", "Unknown")
        opp_id = opp["id"]
        print(f"[{i}/{len(opportunities)}] {name}")

        # Download resume
        print("  Downloading resume...")
        pdf_bytes = download_resume_pdf(opp_id)

        if pdf_bytes is None:
            print("  No resume found. Skipping.")
            results.append({"name": name, "score": 0, "scores": {}, "passed": None, "action": "skipped", "reasoning": "no resume"})
            continue

        # Grade with Claude
        print("  Grading with Claude...")
        try:
            grade_result = grade_resume(pdf_bytes, grading_prompt, name, job_description, model=args.model)
        except anthropic.BadRequestError as e:
            print(f"  Invalid PDF, skipping: {e}")
            results.append({"name": name, "score": 0, "scores": {}, "passed": None, "action": "skipped", "reasoning": "invalid PDF"})
            continue

        if grade_result is None:
            print("  Could not parse grade. Crashing to avoid bad data.")
            sys.exit(1)

        passed = grade_result.score >= args.pass_threshold
        status = "PASS" if passed else "FAIL"
        print(f"  Result: {status} (Score: {grade_result.score}, threshold: {args.pass_threshold})")
        print(f"  Reasoning: {grade_result.reasoning}")
        if args.verbose:
            print(f"  Full response: {grade_result.raw_response}")

        # Take action
        action = "graded"
        score_parts = " + ".join(str(grade_result.scores.get(k, 0)) for k in CRITERIA_KEYS)
        note_text = f"[AI Resume Review] {score_parts} = {grade_result.score} — {grade_result.reasoning}"
        if passed and target_stage_id:
            print(f"  Advancing to '{args.advance_stage_name}'...")
            add_note(opp_id, note_text)
            advance_opportunity(opp_id, target_stage_id)
            action = "advanced"
        elif args.archive_below is not None and grade_result.score <= args.archive_below and archive_reason_id:
            print(f"  Archiving as '{args.archive_reason_text}' (score {grade_result.score} <= {args.archive_below})...")
            add_note(opp_id, note_text)
            archive_opportunity(opp_id, archive_reason_id)
            action = "archived"

        results.append({"name": name, "score": grade_result.score, "scores": grade_result.scores,
                         "passed": passed, "action": action, "reasoning": grade_result.reasoning})
        print()

    # Print summary
    criteria_hdr = " ".join(f"{h:<5}" for h in CRITERIA_HEADERS)
    print("=" * 100)
    print("SUMMARY")
    print("=" * 100)
    print(f"{'Name':<25} {criteria_hdr} {'Total':<6} {'Result':<6} {'Action':<10}")
    print("-" * 100)
    for r in results:
        display_name = r["name"][:23] + ".." if len(r["name"]) > 25 else r["name"]
        if r["scores"]:
            scores_str = " ".join(f"{r['scores'].get(k, 0):<5}" for k in CRITERIA_KEYS)
        else:
            scores_str = " ".join(f"{'—':<5}" for _ in CRITERIA_KEYS)
        status = "PASS" if r["passed"] else ("FAIL" if r["passed"] is not None else "N/A")
        print(f"{display_name:<25} {scores_str} {r['score']:<6} {status:<6} {r['action']:<10}")

    passed_count = sum(1 for r in results if r["passed"] is True)
    failed_count = sum(1 for r in results if r["passed"] is False)
    skipped_count = sum(1 for r in results if r["passed"] is None)
    print(f"\nTotal: {len(results)} | Passed: {passed_count} | Failed: {failed_count} | Skipped: {skipped_count}")


if __name__ == "__main__":
    main()
