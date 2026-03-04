# Lever Resume Review Tool — Design Doc

## Problem

Reviewing resumes manually in Lever's UI is slow. Each candidate requires opening a PDF, reading it, mentally scoring it against criteria, then clicking through Lever's interface to advance or archive. At scale (100+ applicants per role), this takes hours.

## Solution

A CLI tool that automates the entire pipeline: fetch candidates from Lever, download their resume PDFs, grade them with Claude AI against configurable criteria, and take action (advance/archive) — all in parallel.

## Architecture

```
resume_review.py          CLI entry point + async orchestration
    ├── lever_client.py    Async Lever API client (httpx)
    ├── grader.py          Async Claude grading (anthropic SDK)
    └── results.py         CSV writer + terminal summary
```

### `lever_client.py`

Async HTTP client wrapping Lever's V1 REST API (`https://api.lever.co/v1`). Uses `httpx.AsyncClient` for connection pooling across concurrent requests. Auth is HTTP Basic (API key as username, empty password).

All methods are async. Rate-limit handling (HTTP 429) is built into the base `_request()` method — it sleeps for `Retry-After` seconds and retries once.

Key endpoints used:
- `GET /stages` — resolve stage names to IDs
- `GET /opportunities?stage_id=X&archived=false` — list candidates (paginated)
- `GET /opportunities/:id/resumes/:rid/download` — download resume PDF bytes
- `PUT /opportunities/:id/stage` — advance candidate
- `PUT /opportunities/:id/archived` — archive candidate
- `POST /opportunities/:id/notes` — add explanatory note

### `grader.py`

Sends resume PDFs to Claude for evaluation. The PDF is base64-encoded and sent as a `document` content block — no PDF parsing library needed, Claude reads the PDF natively.

Claude returns structured JSON with per-criterion scores. The system prompt is hardcoded to match the 6 criteria keys: `school`, `pedigree`, `startup`, `shipped`, `career`, `published`. If these criteria change in the prompt file, the system prompt and `CRITERIA_KEYS` must be updated to match.

Response parsing strips markdown code fences (Claude sometimes wraps JSON in triple backticks) before `json.loads()`. On parse failure, returns `None` — the caller crashes to avoid acting on bad data.

Cost tracking uses token counts from the API response multiplied by per-model rates (hardcoded in `MODEL_COSTS`).

### `results.py`

`ResultWriter` wraps a CSV `DictWriter`, flushing after every row so data survives interrupted runs. Also holds an in-memory results list for the summary table. The summary prints a columnar table with per-criterion scores and a totals line including cost.

### `resume_review.py`

Async orchestration using `asyncio.gather()` with a `Semaphore(concurrency)` to limit parallel API calls. Each candidate is processed independently:

1. Download resume PDF (async HTTP)
2. Grade with Claude (async API call, retries on 429)
3. Take action: advance if passing, archive if below threshold
4. Write CSV row + print result

Ctrl+C prints the summary of whatever completed so far and closes the CSV cleanly.

## Key Design Decisions

**No PDF library.** Claude accepts raw PDF bytes via the Messages API as a base64-encoded `document` content block. This eliminated the need for `pdfplumber`, `PyPDF2`, or similar — fewer dependencies, no parsing bugs, and Claude sees the actual visual layout.

**Async with semaphore, not thread pool.** The bottleneck is I/O (Claude API calls take 3-5s each). `asyncio` is simpler than threading for this workload. The semaphore (default 2) prevents hitting Anthropic's concurrent connection limit.

**Crash on parse failure.** If Claude's response can't be parsed as JSON, we `sys.exit(1)` rather than skipping. Early on, a parse bug caused all candidates to get score 0 and be incorrectly archived. Crashing is safer than acting on bad data.

**Flush CSV after every row.** The tool may process 100+ candidates over 10+ minutes. If it's interrupted, we don't want to lose all results. Each row is flushed immediately.

**Archive bad resumes by default.** Candidates with missing or corrupt PDFs are archived automatically (with a note explaining why). Disable with `--no-archive-bad-resume`.

**Notes before actions.** Before advancing or archiving, the tool posts a note to Lever with the score breakdown and reasoning. This way recruiters can see why a candidate was moved/archived.

**`archived=false` filter.** Without this, the Lever API returns previously-archived candidates in the results, causing duplicate processing across runs.

## Configuration

### Environment Variables

```
LEVER_API_KEY=...       # Lever API key (HTTP Basic auth)
ANTHROPIC_API_KEY=...   # Claude API key
```

Stored in `.env` (gitignored), loaded by `run.sh`.

### CLI Flags

| Flag | Default | Description |
|---|---|---|
| `--prompt-file` | (required) | Grading criteria prompt |
| `--job-file` | None | Job description for context |
| `--stage-name` | "New applicant" | Pipeline stage to pull from |
| `--posting-ids` | None (all) | Filter by specific job postings |
| `--pass-threshold` | 4 | Score needed to pass |
| `--advance-qualified` | false | Advance passing candidates |
| `--advance-stage-name` | "Recruiter Screen" | Target stage for advancement |
| `--archive-below` | None | Archive at or below this score |
| `--archive-reason-text` | "Unqualified" | Lever archive reason |
| `--no-archive-bad-resume` | false | Skip instead of archive bad PDFs |
| `--model` | claude-sonnet-4-6 | Claude model |
| `--concurrency` | 2 | Parallel candidates |
| `--limit` | None | Max candidates to process |
| `--verbose` | false | Print full Claude responses |

### Wrapper Scripts (gitignored)

- `run.sh` — Creates venv, loads `.env`, runs `resume_review.py`
- `review_eng.sh` — Pre-configured for engineering roles with specific posting IDs

## Grading Criteria

The prompt file (`prompts/resume-review.md`) defines 6 criteria, each worth up to 1 point (school can be 1.5). The criteria are tightly coupled to `CRITERIA_KEYS` in `grader.py` and the system prompt's JSON schema. To add/remove criteria:

1. Update the prompt file
2. Update `CRITERIA_KEYS` and `CRITERIA_HEADERS` in `grader.py`
3. Update the JSON schema in `SYSTEM_PROMPT` in `grader.py`

## Cost

At ~5K input tokens per resume (PDF + prompt) and ~200 output tokens:
- **Sonnet 4.6**: ~$0.02/candidate → $2 per 100 candidates
- **Haiku 4.5**: ~$0.005/candidate → $0.50 per 100 candidates
- **Opus 4.6**: ~$0.09/candidate → $9 per 100 candidates

Actual cost is logged per-candidate and in the CSV.

## Failure Modes

| Failure | Behavior |
|---|---|
| Invalid PDF | Archive with note (or skip with `--no-archive-bad-resume`) |
| No resume attached | Archive with note (or skip) |
| Claude parse error | Crash (`sys.exit(1)`) |
| Lever rate limit (429) | Sleep + retry (built into client) |
| Claude rate limit (429) | Exponential backoff, 3 attempts |
| Ctrl+C | Print summary of completed work, close CSV |
