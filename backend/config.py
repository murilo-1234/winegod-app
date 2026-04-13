import os
from dotenv import load_dotenv

load_dotenv()


class Config:
    ANTHROPIC_API_KEY = os.getenv("ANTHROPIC_API_KEY")
    DATABASE_URL = os.getenv("DATABASE_URL")
    FLASK_ENV = os.getenv("FLASK_ENV", "development")
    FLASK_PORT = os.getenv("FLASK_PORT", "5000")
    GUEST_CREDIT_LIMIT = 5
    USER_CREDIT_LIMIT = 15
