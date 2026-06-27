import os
import httpx
import json
import asyncio
import random
from google import genai
from google.genai import types
from pydantic import BaseModel, Field
from typing import List, Dict, Any
from app.config import settings

class LineCommentSchema(BaseModel):
    path: str = Field(description="The exact relative file path where the issue resides, matching the diff headers precisely (e.g., 'auth.py').")
    line: int = Field(description="The precise line number in the NEW file (right side of the diff) where the issue or note occurs.")
    body: str = Field(description="Constructive, professional feedback tailored to this specific line. Use Markdown syntax and short emojis.")

class FullReviewSchema(BaseModel):
    summary: str = Field(description="A comprehensive global summary comment reviewing the architectural impacts of the PR.")
    comments: List[LineCommentSchema] = Field(description="Array of targeted inline single-line or multi-line observations.")

class GeminiService:
    def __init__(self):
        print("🧠 [AI SERVICE] Service initialized. Keys will be fetched dynamically at runtime.")

    def _get_api_key(self) -> str:
        key = getattr(settings, "GEMINI_API_KEY", None) or os.getenv("GEMINI_API_KEY")
        if key:
            return key.strip().strip('"').strip("'")
        return ""

    def _get_github_token(self) -> str:
        token = getattr(settings, "GITHUB_TOKEN", None) or os.getenv("GITHUB_TOKEN")
        if token:
            return token.strip().strip('"').strip("'")
        return ""

    async def _fetch_live_diff(self, repo_name: str, pr_number: int) -> str:
        url = f"https://api.github.com/repos/{repo_name}/pulls/{pr_number}"
        headers = {
            "Accept": "application/vnd.github.v3.diff",
            "User-Agent": "FastAPI-CodeReview-Bot"
        }
        token = self._get_github_token()
        if token:
            headers["Authorization"] = f"token {token}"

        try:
            async with httpx.AsyncClient(follow_redirects=True) as client:
                response = await client.get(url, headers=headers)
                if response.status_code == 200:
                    return response.text
                return ""
        except Exception:
            return ""

    async def analyze_code_diff(self, repo_name: str, pr_number: int) -> Dict[str, Any]:
        print(f"🧠 [AI SERVICE] Initiating structured inline analysis for {repo_name} PR #{pr_number}...")
        diff_text = await self._fetch_live_diff(repo_name, pr_number)

        if not diff_text or diff_text.strip() == "":
            return {
                "summary": "### ⚠️ System Warning\nUnable to reach live PR diff changes dynamically.",
                "comments": []
            }

        api_key = self._get_api_key()
        if not api_key or "your_gemini" in api_key.lower():
            print("⚠️ [AI SERVICE] Mock fallback triggered.")
            return {
                "summary": "### 🤖 Mock Code Review Summary\nCodebase stability checks passed.",
                "comments": [
                    {"path": "auth.py", "line": 11, "body": "💡 Avoid hardcoding credential values."}
                ]
            }

        system_prompt = (
            "You are an elite Senior Staff Software Engineer reviewing an incoming GitHub Pull Request diff.\n"
            "Your objective is to identify critical bugs, security vulnerabilities, architectural improvements, "
            "and formatting issues.\n\n"
            "CRITICAL REQUIREMENT FOR INLINE COMMENTS:\n"
            "1. Only create inline comments for files and lines that are explicitly added or modified in the diff (marked with '+').\n"
            "2. Make sure the 'path' variable perfectly matches the true file names from the diff.\n"
            "3. Deduce the exact target line number in the final modified file context accurately. Do not comment on negative line frames."
        )

        user_prompt = f"Repository: {repo_name}\nPull Request: #{pr_number}\n\nReview this raw git diff snapshot:\n```diff\n{diff_text}\n```"

        # ─── EXTRACTION RESILIENCY WITH EXPONENTIAL BACKOFF RETRIES ───
        max_retries = 3
        base_delay = 2.0  # Wait 2 seconds, then 4 seconds...

        for attempt in range(max_retries):
            try:
                client = genai.Client(api_key=api_key)
                
                response = await client.aio.models.generate_content(
                    model="gemini-2.5-flash",
                    contents=user_prompt,
                    config=types.GenerateContentConfig(
                        system_instruction=system_prompt,
                        temperature=0.1,
                        response_mime_type="application/json",
                        response_schema=FullReviewSchema,
                    )
                )
                
                print("✅ [AI SERVICE] Gemini successfully returned structured inline review data!")
                return json.loads(response.text)

            except Exception as e:
                error_msg = str(e).lower()
                
                # Check explicitly for 503 errors or Google system unavailability states
                if "503" in error_msg or "unavailable" in error_msg:
                    if attempt < max_retries - 1:
                        # Exponential progression formula tracking base delay + uniform randomized jitter
                        delay = (base_delay ** attempt) + random.uniform(0.1, 1.0)
                        print(f"⏳ [AI SERVICE] Gemini overloaded (503/UNAVAILABLE). Retrying in {delay:.2f}s... (Attempt {attempt + 1}/{max_retries})")
                        await asyncio.sleep(delay)
                        continue  # Return to the top of the loop and try again
                
                # If we run out of retries, or encounter a separate fatal problem (like an invalid key), throw it up!
                print(f"❌ [AI SERVICE] Structured Gemini processing failed critically after retries: {e}")
                raise e