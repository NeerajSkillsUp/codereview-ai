from fastapi import APIRouter, Request, status, Body, BackgroundTasks
from app.services.github import GitHubService
from app.services.gemini_service import GeminiService
from app.database import SessionLocal, CodeReviewHistory

router = APIRouter(
    prefix="/webhooks",
    tags=["Webhooks"]
)

github_service = GitHubService()
gemini_service = GeminiService()

async def run_ai_review_workflow(repo_name: str, pr_number: int, action: str):
    """
    Handles the long-running API tasks independently so the main 
    webhook response can return instantly to GitHub.
    """
    
    # ─── INCORPORATING SAFETY BREAKPOINTS TO STOP HOLLOW REVIEWS ───
    try:
        # Capture structured dictionary data from our hardened Gemini Service loop
        review_data = await gemini_service.analyze_code_diff(
            repo_name=repo_name, 
            pr_number=pr_number
        )
    except Exception as e:
        # ⚠️ SHORT-CIRCUIT: If Gemini completely failed all 3 retries, freeze execution immediately!
        print(f"🚨 [WORKFLOW] Short-circuit triggered. Aborting analysis loop for {repo_name} PR #{pr_number} to prevent empty updates.")
        return  # Kills the background thread cleanly without running GitHub or DB tasks below

    summary_text = review_data.get("summary", "Review complete.")
    inline_comments_list = review_data.get("comments", [])
    
    # 2. Deploy a complete contextual PR review object to GitHub
    await github_service.post_pr_review(
        repo_full_name=repo_name, 
        pr_number=pr_number, 
        summary=summary_text,
        inline_comments=inline_comments_list
    )
    
    print(f"💾 [DATABASE] Saving review logs for {repo_name} PR #{pr_number}...")
    db = SessionLocal()
    try:
        # Save the global summary string in your database record history
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
async def github_webhook(request: Request, background_tasks: BackgroundTasks, payload: dict = Body(...)):
    action = payload.get("action")
    pr_number = payload.get("number")
    
    repo_name = "Unknown Repo"
    if "repository" in payload and payload["repository"]:
        repo_name = payload["repository"].get("full_name", "Unknown Repo")
    
    print(f"\n📥 [WEBHOOK RECEIVED] Repo: {repo_name} | PR #{pr_number} | Action: {action}")
    
    if action in ["opened", "synchronize", "reopened"]:
        print(f"⏳ [WEBHOOK] Handing off heavy analysis to FastAPI background thread...")
        
        # Schedule the job to run immediately after we respond to GitHub
        background_tasks.add_task(run_ai_review_workflow, repo_name, pr_number, action)
        
        return {
            "status": "accepted",
            "message": "AI analysis offloaded to worker thread successfully."
        }
    
    return {
        "status": "ignored",
        "message": "Action skipped."
    }