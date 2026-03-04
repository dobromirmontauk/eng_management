"""
Lever Resume Review Tool

Fetches candidates from a Lever pipeline stage, downloads their resume PDFs,
grades them using Claude in parallel, and prints a summary.

Usage:
    export LEVER_API_KEY="your-lever-api-key"
    export ANTHROPIC_API_KEY="your-anthropic-api-key"
    python resume_review.py --prompt-file prompts/resume-review.md --limit 5
"""

import asyncio
import os
import sys
import argparse
from typing import Optional

import anthropic

from lever_client import LeverClient
from grader import grade_resume, CRITERIA_KEYS
from results import ResultWriter


async def process_candidate(
    i: int, total: int, opp: dict, semaphore: asyncio.Semaphore,
    lever: LeverClient, claude: anthropic.AsyncAnthropic,
    grading_prompt: str, job_description: Optional[str],
    model: str, pass_threshold: float,
    target_stage_id: Optional[str], advance_stage_name: Optional[str],
    archive_below: Optional[float], archive_reason_id: Optional[str],
    archive_reason_text: Optional[str], archive_bad_resume: bool,
    writer: ResultWriter, verbose: bool,
):
    """Process a single candidate: download, grade, act, record."""
    async with semaphore:
        name = opp.get("name", "Unknown")
        opp_id = opp["id"]
        print(f"[{i}/{total}] {name}")

        # Download resume
        print(f"  [{name}] Downloading resume...")
        pdf_bytes = await lever.download_resume_pdf(opp_id)

        if pdf_bytes is None:
            action = "skipped"
            if archive_reason_id and archive_bad_resume:
                print(f"  [{name}] No resume found. Archiving.")
                await lever.add_note(opp_id, "[AI Resume Review] No resume attached — archived automatically.")
                await lever.archive_opportunity(opp_id, archive_reason_id)
                action = "archived"
            else:
                print(f"  [{name}] No resume found. Skipping.")
            writer.write_skip(name, opp_id, action, "no resume")
            return

        # Grade with Claude (retry on rate limit)
        print(f"  [{name}] Grading with Claude...")
        grade_result = None
        last_error = None
        for attempt in range(3):
            try:
                grade_result = await grade_resume(claude, pdf_bytes, grading_prompt, name, job_description, model=model)
                break
            except anthropic.RateLimitError as e:
                last_error = e
                wait = 2 ** attempt * 5
                print(f"  [{name}] Rate limited, retrying in {wait}s...")
                await asyncio.sleep(wait)
            except anthropic.BadRequestError:
                action = "skipped"
                if archive_reason_id and archive_bad_resume:
                    print(f"  [{name}] Invalid PDF. Archiving.")
                    await lever.add_note(opp_id, "[AI Resume Review] Invalid/corrupt resume PDF — archived automatically.")
                    await lever.archive_opportunity(opp_id, archive_reason_id)
                    action = "archived"
                else:
                    print(f"  [{name}] Invalid PDF, skipping.")
                writer.write_skip(name, opp_id, action, "invalid PDF")
                return

        if grade_result is None:
            if last_error:
                print(f"  [{name}] Rate limit retries exhausted: {last_error}")
            print(f"  [{name}] Failed to grade. Crashing to avoid bad data.")
            sys.exit(1)

        passed = grade_result.score >= pass_threshold
        status = "PASS" if passed else "FAIL"
        print(f"  [{name}] {status} (Score: {grade_result.score}, threshold: {pass_threshold}) — ${grade_result.total_cost:.4f}")
        print(f"  [{name}] {grade_result.reasoning}")
        if verbose:
            print(f"  [{name}] Full response: {grade_result.raw_response}")

        # Take action
        action = "graded"
        score_parts = " + ".join(str(grade_result.scores.get(k, 0)) for k in CRITERIA_KEYS)
        note_text = f"[AI Resume Review] {score_parts} = {grade_result.score} — {grade_result.reasoning}"
        if passed and target_stage_id:
            print(f"  [{name}] Advancing to '{advance_stage_name}'...")
            await lever.add_note(opp_id, note_text)
            await lever.advance_opportunity(opp_id, target_stage_id)
            action = "advanced"
        elif archive_below is not None and grade_result.score <= archive_below and archive_reason_id:
            print(f"  [{name}] Archiving as '{archive_reason_text}' (score {grade_result.score} <= {archive_below})...")
            await lever.add_note(opp_id, note_text)
            await lever.archive_opportunity(opp_id, archive_reason_id)
            action = "archived"

        writer.write_grade(name, opp_id, grade_result, passed, status, action)


def parse_args():
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
    parser.add_argument("--no-archive-bad-resume", action="store_true", default=False,
                        help="Don't archive candidates with missing or invalid resumes (default: archive them)")
    parser.add_argument("--posting-ids", nargs="+", default=None,
                        help="Only process candidates for these posting IDs (space-separated)")
    parser.add_argument("--limit", type=int, default=None,
                        help="Maximum number of candidates to process")
    parser.add_argument("--concurrency", type=int, default=2,
                        help="Number of candidates to process in parallel (default: 2)")
    parser.add_argument("--verbose", action="store_true",
                        help="Print full Claude responses")
    return parser.parse_args()


async def async_main():
    args = parse_args()

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

    lever = LeverClient()
    claude = anthropic.AsyncAnthropic()

    try:
        # Resolve stage and action targets
        print(f"Finding stage '{args.stage_name}'...")
        source_stage_id = await lever.find_stage_id(args.stage_name)

        target_stage_id = None
        if args.advance_qualified:
            print(f"Finding advance target stage '{args.advance_stage_name}'...")
            target_stage_id = await lever.find_stage_id(args.advance_stage_name)

        archive_reason_id = None
        needs_archive_reason = args.archive_below is not None or not args.no_archive_bad_resume
        if needs_archive_reason:
            print(f"Finding archive reason '{args.archive_reason_text}'...")
            archive_reason_id = await lever.find_archive_reason_id(args.archive_reason_text)

        # Fetch candidates
        if args.posting_ids:
            print(f"Fetching candidates in stage '{args.stage_name}' for {len(args.posting_ids)} posting(s)...")
        else:
            print(f"Fetching candidates in stage '{args.stage_name}' (all postings)...")
        opportunities = await lever.get_opportunities(source_stage_id, posting_ids=args.posting_ids, limit=args.limit)
        print(f"Found {len(opportunities)} candidate(s).\n")

        if not opportunities:
            print("No candidates to review.")
            return

        writer = ResultWriter()
        print(f"Writing results to {writer.csv_path}\n")

        semaphore = asyncio.Semaphore(args.concurrency)
        tasks = [
            process_candidate(
                i=i, total=len(opportunities), opp=opp, semaphore=semaphore,
                lever=lever, claude=claude,
                grading_prompt=grading_prompt, job_description=job_description,
                model=args.model, pass_threshold=args.pass_threshold,
                target_stage_id=target_stage_id, advance_stage_name=args.advance_stage_name,
                archive_below=args.archive_below, archive_reason_id=archive_reason_id,
                archive_reason_text=args.archive_reason_text,
                archive_bad_resume=not args.no_archive_bad_resume,
                writer=writer, verbose=args.verbose,
            )
            for i, opp in enumerate(opportunities, 1)
        ]

        try:
            await asyncio.gather(*tasks)
        except KeyboardInterrupt:
            print("\n\nInterrupted! Printing results so far...\n")
        finally:
            writer.print_summary()
    finally:
        await lever.close()


def main():
    try:
        asyncio.run(async_main())
    except KeyboardInterrupt:
        pass  # summary already printed by the inner handler


if __name__ == "__main__":
    main()
