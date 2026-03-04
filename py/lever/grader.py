"""Async Claude resume grading."""

import base64
import json
from dataclasses import dataclass
from typing import Optional

import anthropic


CRITERIA_KEYS = ["school", "pedigree", "startup", "shipped", "career", "published", "urm"]
CRITERIA_HEADERS = ["Schl", "Pdgr", "Strt", "Ship", "Crer", "Publ", "URM"]

# Cost per million tokens (input, output) by model
MODEL_COSTS = {
    "claude-opus-4-6": (15.0, 75.0),
    "claude-sonnet-4-6": (3.0, 15.0),
    "claude-haiku-4-5-20251001": (0.80, 4.0),
}

SYSTEM_PROMPT = """You are a resume reviewer. You will be given a resume PDF, grading criteria, and optionally a job description.
Evaluate the resume against the criteria and respond with ONLY a JSON object in this exact format:
{
    "scores": {
        "school": <number>,
        "pedigree": <number>,
        "startup": <number>,
        "shipped": <number>,
        "career": <number>,
        "published": <number>,
        "urm": <number>
    },
    "reasoning": "2-3 sentence explanation of your assessment"
}
Each score should match the points defined in the grading criteria. The total is the sum of all scores.
Do not include any other text before or after the JSON."""


@dataclass
class GradeResult:
    score: float
    scores: dict  # per-criterion scores keyed by CRITERIA_KEYS
    reasoning: str
    raw_response: str
    input_tokens: int
    output_tokens: int
    input_cost: float   # USD
    output_cost: float  # USD
    total_cost: float   # USD


async def grade_resume(client: anthropic.AsyncAnthropic, pdf_bytes: bytes,
                       grading_prompt: str, candidate_name: str,
                       job_description: Optional[str] = None,
                       model: str = "claude-sonnet-4-6") -> Optional[GradeResult]:
    pdf_b64 = base64.standard_b64encode(pdf_bytes).decode("utf-8")

    user_text = f"Candidate name: {candidate_name}\n\n"
    if job_description:
        user_text += f"Job description:\n{job_description}\n\n"
    user_text += f"Grading criteria:\n{grading_prompt}"

    message = await client.messages.create(
        model=model,
        max_tokens=1024,
        system=SYSTEM_PROMPT,
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

    # Calculate cost
    usage = message.usage
    input_rate, output_rate = MODEL_COSTS.get(model, (3.0, 15.0))
    input_cost = usage.input_tokens * input_rate / 1_000_000
    output_cost = usage.output_tokens * output_rate / 1_000_000

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
            input_tokens=usage.input_tokens,
            output_tokens=usage.output_tokens,
            input_cost=input_cost,
            output_cost=output_cost,
            total_cost=input_cost + output_cost,
        )
    except (json.JSONDecodeError, KeyError) as e:
        print(f"  Parse error: {e}")
        print(f"  Raw response:\n{raw_text}")
        return None
