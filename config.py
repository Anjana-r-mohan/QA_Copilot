import os
from dotenv import load_dotenv

load_dotenv()

class Config:
    # LLM Configuration
    OPENAI_API_KEY = os.getenv("OPENAI_API_KEY", "")
    GEMINI_API_KEY = os.getenv("GEMINI_API_KEY", "") or os.getenv("GOOGLE_API_KEY", "")
    
    # Database
    DATABASE_URL = os.getenv("DATABASE_URL", "postgresql://localhost:5432/qa_copilot")
    
    # Zoho Integration
    ZOHO_API_KEY = os.getenv("ZOHO_API_KEY", "")
    ZOHO_ORG_ID = os.getenv("ZOHO_ORG_ID", "")
    
    # Application
    APP_HOST = os.getenv("APP_HOST", "0.0.0.0")
    APP_PORT = int(os.getenv("APP_PORT", "8000"))
    
    # Paths
    KMM_SHARED_PATH = os.getenv("KMM_SHARED_PATH", "./sample_projects/kmm_shared")
    ANDROID_PATH = os.getenv("ANDROID_PATH", "./sample_projects/android")
    IOS_PATH = os.getenv("IOS_PATH", "./sample_projects/ios")
    AUTOMATION_PATH = os.getenv("AUTOMATION_PATH", "./sample_projects/automation")

config = Config()
