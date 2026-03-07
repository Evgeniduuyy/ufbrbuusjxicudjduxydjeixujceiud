import os
from dotenv import load_dotenv

load_dotenv()

class Config:
    BOT_TOKEN = os.getenv("BOT_TOKEN")
    DATABASE_URL = os.getenv("DATABASE_URL", "postgresql+asyncpg://user:pass@localhost/cdzmonstr")
    REDIS_URL = os.getenv("REDIS_URL", "redis://localhost:6379/0")
    ENCRYPTION_KEY = os.getenv("ENCRYPTION_KEY")
    
    AI_PROVIDER = os.getenv("AI_PROVIDER", "openai")
    OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")
    YANDEX_GPT_API_KEY = os.getenv("YANDEX_GPT_API_KEY")
    YANDEX_GPT_FOLDER_ID = os.getenv("YANDEX_GPT_FOLDER_ID")
    OPENROUTER_API_KEY = os.getenv("OPENROUTER_API_KEY")
    
    MAX_FREE_SOLVES = int(os.getenv("MAX_FREE_SOLVES", 3))
    MAX_FREE_AUTOS = int(os.getenv("MAX_FREE_AUTOS", 1))
    
    OCR_ENGINE = os.getenv("OCR_ENGINE", "paddle")
    
    CELERY_BROKER_URL = os.getenv("CELERY_BROKER_URL", "redis://localhost:6379/1")
    CELERY_RESULT_BACKEND = os.getenv("CELERY_RESULT_BACKEND", "redis://localhost:6379/1")
    
    HEADLESS = os.getenv("HEADLESS", "True").lower() == "true"
    ADMIN_IDS = list(map(int, os.getenv("ADMIN_IDS", "").split(","))) if os.getenv("ADMIN_IDS") else []
