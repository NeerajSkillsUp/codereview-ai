import hmac
import hashlib
import json
from fastapi import APIRouter, Request, status, Header, HTTPException, BackgroundTasks
from app.services.github import GitHubService
from app.services.gemini_service import GeminiService
from app.database import SessionLocal, CodeReviewHistory
from app.config import settings
from fastapi import Depends
from sqlalchemy.orm import Session

router = APIRouter(
    prefix="/webhooks",
    tags=["Webhooks"]
)

github_service = GitHubService()
gemini_service = GeminiService()

def verify_signature(payload_body: bytes, signature: str) -> bool:
    """
    Cryptographically validates that the incoming payload payload 
    originated securely from GitHub using our vaulted secret passphrase.
    """
    # Fallback safety validation switch
    if not settings.GITHUB_WEBHOOK_SECRET:
        print("⚠️ [SECURITY] GITHUB_WEBHOOK_SECRET is empty. Bypassing validation.")
        return True
    
    if not signature:
        return False
        
    # GitHub payloads arrive with a 'sha256=' prefix string schema
    try:
        sha_type, sign_hash = signature.split("=")
        if sha_type != "sha256":
            return False
    except ValueError:
        return False
        
    # Generate the validation digest
    mac = hmac.new(
        settings.GITHUB_WEBHOOK_SECRET.encode(),
        msg=payload_body,
        digestmod=hashlib.sha256
    )
    return hmac.compare_digest(mac.hexdigest(), sign_hash)

async def run_ai_review_workflow(repo_name: str, pr_number: int, action: str):
    """
    Handles the long-running API tasks independently so the main 
    webhook response can return instantly to GitHub.
    """
    try:
        # Capture structured dictionary data from our hardened Gemini Service loop
        review_data = await gemini_service.analyze_code_diff(
            repo_name=repo_name, 
            pr_number=pr_number
        )
    except Exception as e:
        print(f"🚨 [WORKFLOW] Short-circuit triggered. Aborting analysis loop for {repo_name} PR #{pr_number}: {str(e)}")
        return

    summary_text = review_data.get("summary", "Review complete.")
    inline_comments_list = review_data.get("comments", [])
    
    # Deploy a complete contextual PR review object to GitHub
    await github_service.post_pr_review(
        repo_full_name=repo_name, 
        pr_number=pr_number, 
        summary=summary_text,
        inline_comments=inline_comments_list
    )
    
    print(f"💾 [DATABASE] Saving review logs for {repo_name} PR #{pr_number}...")
    db = SessionLocal()
    try:
        db_record = CodeReviewHistory(
            repo_name=repo_name,
            pr_number=pr_number,
            action=action,
            ai_feedback=summary_text
        )
        db.add(db_record)
        db.commit()
        print("✅ [DATABASE] Record successfully locked in!")
    except Exception as e:
        db.rollback()
        print(f"❌ [DATABASE] Failed to write memory log: {str(e)}")
    finally:
        db.close()

@router.post("/github", status_code=status.HTTP_200_OK)
async def github_webhook(
    request: Request, 
    background_tasks: BackgroundTasks,
    x_hub_signature_256: str = Header(None) # Automatically intercepts the GitHub security header
):
    # ─── STREAM RAW DATA BYTES FOR CRYPTOGRAPHIC VERIFICATION ───
    raw_body = await request.body()
    
    if not verify_signature(raw_body, x_hub_signature_256):
        print("❌ [SECURITY] Unauthorized payload attempt blocked. Invalid signature matching.")
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid webhook signature security verification failed."
        )
        
    # Parse the text bytes back into standard dictionary structures safely
    try:
        payload = json.loads(raw_body.decode("utf-8"))
    except Exception:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST, 
            detail="Invalid JSON layout formatting structure."
        )

    # ─── EXTRACTION WORKFLOW ───
    action = payload.get("action")
    
    # GitHub payloads nest the pull request number inside a dedicated context block
    pull_request = payload.get("pull_request", {})
    pr_number = pull_request.get("number") or payload.get("number")
    
    repo_name = "Unknown Repo"
    if "repository" in payload and payload["repository"]:
        repo_name = payload["repository"].get("full_name", "Unknown Repo")
    
    print(f"\n📥 [WEBHOOK VERIFIED] Repo: {repo_name} | PR #{pr_number} | Action: {action}")
    
    if action in ["opened", "synchronize", "reopened"]:
        print(f"⏳ [WEBHOOK] Handing off heavy analysis to FastAPI background thread...")
        background_tasks.add_task(run_ai_review_workflow, repo_name, pr_number, action)
        
        return {
            "status": "accepted",
            "message": "AI secure analysis offloaded to worker thread successfully."
        }
    
    return {
        "status": "ignored",
        "message": "Action skipped."
    }

# Helper dependency to handle database sessions cleanly
def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()

@router.get("/history", status_code=status.HTTP_200_OK)
def get_review_history(db: Session = Depends(get_db)):
    """
    Exposes a clean query channel to inspect all compiled code 
    reviews securely recorded in the application database layer.
    """
    try:
        # Fetch the last 50 code reviews, newest first
        records = db.query(CodeReviewHistory).order_by(CodeReviewHistory.id.desc()).limit(50).all()
        
        # Format the records into a clean, readable dictionary array
        history_log = []
        for r in records:
            history_log.append({
                "id": r.id,
                "repository": r.repo_name,
                "pr_number": r.pr_number,
                "action_event": r.action,
                "gemini_summary": r.ai_feedback,
                "created_at": getattr(r, "timestamp", "N/A") # handles timestamp if you added it
            })
            
        return {
            "status": "success",
            "total_records": len(history_log),
            "data": history_log
        }
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to query database logs: {str(e)}"
        )