# Centralized Security Vault Office for permission management and secret storage.
import os
from dotenv import load_dotenv
load_dotenv()  # Look for the .env file and load its variables into memory
class Settings:
    """This class acts as our application's vault. 
    Instead of reading directly from the system everywhere, 
    we read from this settings object."""
    
    APP_NAME: str = "CodeReview AI Bot"
    APP_ENV: str = os.getenv("APP_ENV", "development")
    
    # Secrets
    GITHUB_WEBHOOK_SECRET: str = os.getenv("GITHUB_WEBHOOK_SECRET", "")
    GITHUB_ACCESS_TOKEN: str = os.getenv("GITHUB_ACCESS_TOKEN", "")
    GEMINI_API_KEY: str = os.getenv("GEMINI_API_KEY", "")
    DATABASE_URL: str = os.getenv("DATABASE_URL", "")

settings = Settings()   # Instantiate the settings object so other files can import it directly