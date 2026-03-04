"""Async Lever API client."""

import asyncio
import os
import sys
from typing import Optional

import httpx


LEVER_BASE_URL = "https://api.lever.co/v1"


class LeverClient:
    """Async client for the Lever API with rate-limit handling."""

    def __init__(self, api_key: Optional[str] = None):
        self.api_key = api_key or os.environ.get("LEVER_API_KEY")
        if not self.api_key:
            print("Error: LEVER_API_KEY environment variable is required.")
            sys.exit(1)
        self._client = httpx.AsyncClient(
            base_url=LEVER_BASE_URL,
            auth=(self.api_key, ""),
            timeout=30.0,
        )

    async def close(self):
        await self._client.aclose()

    async def _request(self, method: str, endpoint: str, **kwargs) -> httpx.Response:
        response = await self._client.request(method, endpoint, **kwargs)
        if response.status_code == 429:
            retry_after = int(response.headers.get("Retry-After", 10))
            print(f"  Rate limited. Waiting {retry_after}s...")
            await asyncio.sleep(retry_after)
            response = await self._client.request(method, endpoint, **kwargs)
        response.raise_for_status()
        return response

    async def get(self, endpoint: str, params: dict = None) -> dict:
        response = await self._request("GET", endpoint, params=params)
        return response.json()

    async def put(self, endpoint: str, json_body: dict) -> dict:
        response = await self._request("PUT", endpoint, json=json_body)
        return response.json()

    async def post(self, endpoint: str, json_body: dict) -> dict:
        response = await self._request("POST", endpoint, json=json_body)
        return response.json()

    async def get_binary(self, endpoint: str) -> bytes:
        response = await self._request("GET", endpoint)
        return response.content

    # --- Domain methods ---

    async def find_stage_id(self, stage_name: str) -> str:
        data = await self.get("/stages")
        for stage in data["data"]:
            if stage["text"].lower() == stage_name.lower():
                return stage["id"]
        available = [s["text"] for s in data["data"]]
        print(f"Error: Stage '{stage_name}' not found. Available stages: {available}")
        sys.exit(1)

    async def find_archive_reason_id(self, reason_text: str) -> str:
        data = await self.get("/archive_reasons")
        for reason in data["data"]:
            if reason["text"].lower() == reason_text.lower():
                return reason["id"]
        available = [r["text"] for r in data["data"]]
        print(f"Error: Archive reason '{reason_text}' not found. Available: {available}")
        sys.exit(1)

    async def get_opportunities(self, stage_id: str, posting_ids: Optional[list] = None,
                                limit: Optional[int] = None,
                                created_at_start: Optional[int] = None) -> list:
        opportunities = []
        offset = None
        while True:
            params = {"stage_id": stage_id, "archived": "false", "expand": "applications"}
            if posting_ids:
                params["posting_id"] = posting_ids
            if created_at_start:
                params["created_at_start"] = created_at_start
            if offset:
                params["offset"] = offset
            data = await self.get("/opportunities", params=params)
            opportunities.extend(data["data"])
            if limit and len(opportunities) >= limit:
                return opportunities[:limit]
            if data.get("hasNext"):
                offset = data.get("next")
            else:
                break
        return opportunities

    async def advance_opportunity(self, opportunity_id: str, target_stage_id: str):
        await self.put(f"/opportunities/{opportunity_id}/stage", {"stage": target_stage_id})

    async def archive_opportunity(self, opportunity_id: str, reason_id: str):
        await self.put(f"/opportunities/{opportunity_id}/archived", {"reason": reason_id})

    async def add_note(self, opportunity_id: str, text: str):
        await self.post(f"/opportunities/{opportunity_id}/notes", {"value": text})

    async def has_note_with_prefix(self, opportunity_id: str, prefix: str) -> bool:
        """Check if an opportunity already has a note starting with the given prefix."""
        data = await self.get(f"/opportunities/{opportunity_id}/notes")
        for note in data.get("data", []):
            for field in note.get("fields", []):
                if field.get("value", "").startswith(prefix):
                    return True
        return False

    async def get_posting_name(self, posting_id: str) -> str:
        """Fetch the human-readable name for a posting ID."""
        try:
            data = await self.get(f"/postings/{posting_id}")
            return data["data"]["text"]
        except Exception:
            return posting_id[:12]

    async def download_resume_pdf(self, opportunity_id: str) -> Optional[bytes]:
        data = await self.get(f"/opportunities/{opportunity_id}/resumes")
        resumes = data.get("data", [])
        if not resumes:
            return None
        resume_id = resumes[0]["id"]
        return await self.get_binary(
            f"/opportunities/{opportunity_id}/resumes/{resume_id}/download"
        )
