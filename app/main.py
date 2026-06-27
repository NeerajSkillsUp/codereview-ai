from fastapi import FastAPI
from app.config import settings 
from app.webhooks import router as webhooks_router
# 1. Import our database initialization function
from app.database import init_db

# 2. Trigger table creation automatically on startup
print("🗄️ [DATABASE] Initializing memory storage schemas...")
init_db()

app = FastAPI(
    title=settings.APP_NAME,
    description="An AI-powered GitHub PR Reviewer"
)

app.include_router(webhooks_router)

@app.get("/")
async def root():
    return {
        "status": "online",
        "message": "CodeReview AI Bot engine and memory storage are fully linked!"
    }

@app.get("/health")
async def health_check():
    return {"status": "healthy"}