import os
import httpx
from app.config import settings

class GitHubService:
    def __init__(self):
        print("⚙️ [GITHUB SERVICE] Service initialized. Token will be fetched dynamically at runtime.")

    def _get_token(self) -> str:
        """
        Dynamically fetches and cleans the GitHub token at runtime 
        to ensure environment variables are fully loaded.
        """
        token = getattr(settings, "GITHUB_ACCESS_TOKEN", None) or os.getenv("GITHUB_ACCESS_TOKEN")
        if token:
            return token.strip().strip('"').strip("'")
        return ""

    async def post_pr_comment(self, repo_full_name: str, pr_number: int, comment_body: str):
        """
        Legacy method: Posts a single catch-all comment to the PR main timeline.
        """
        token = self._get_token()
        url = f"https://api.github.com/repos/{repo_full_name}/issues/{pr_number}/comments"
        headers = {
            "Authorization": f"token {token}",
            "Accept": "application/vnd.github+json",
            "User-Agent": "FastAPI-CodeReview-Bot"
        }
        async with httpx.AsyncClient() as client:
            response = await client.post(url, json={"body": comment_body}, headers=headers)
            return response.status_code

    async def post_pr_review(self, repo_full_name: str, pr_number: int, summary: str, inline_comments: list):
        """
        New Method: Posts a unified multi-file, multi-line inline PR review block.
        """
        url = f"https://api.github.com/repos/{repo_full_name}/pulls/{pr_number}/reviews"
        
        token = self._get_token()
        if not token:
            print("❌ [GITHUB SERVICE] Aborting PR review post: GITHUB_TOKEN is completely blank or None at runtime!")
            return False

        headers = {
            "Authorization": f"token {token}",
            "Accept": "application/vnd.github+json",
            "User-Agent": "FastAPI-CodeReview-Bot"
        }
        
        # Format the comment array exactly how GitHub's Review API demands it
        formatted_comments = []
        for c in inline_comments:
            formatted_comments.append({
                "path": c.get("path"),
                "line": int(c.get("line")),
                "body": c.get("body")
            })

        payload = {
            "body": summary,
            "event": "COMMENT", 
            "comments": formatted_comments
        }

        print(f"🤖 [GITHUB SERVICE] Transmitting inline review batch ({len(formatted_comments)} line comments) to PR #{pr_number}...")
        print(f"🔑 [GITHUB SERVICE] Verifying outbound Auth Header... Prefix: 'token' | Character Count: {len(token)}")
        
        async with httpx.AsyncClient() as client:
            response = await client.post(url, json=payload, headers=headers)
            if response.status_code in [200, 201]:
                print("Base URL connection OK. ✅ [GITHUB SERVICE] Multi-line inline review posted flawlessly!")
                return True
            else:
                print(f"❌ [GITHUB SERVICE] Failed to post review. Code: {response.status_code}")
                print(f"📄 [GITHUB SERVICE] Response Context: {response.text}")
                return False