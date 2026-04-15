import os
from dotenv import load_dotenv

load_dotenv()


class Config:
    ANTHROPIC_API_KEY = os.getenv("ANTHROPIC_API_KEY")
    DATABASE_URL = os.getenv("DATABASE_URL")
    FLASK_ENV = os.getenv("FLASK_ENV", "development")
    FLASK_PORT = os.getenv("FLASK_PORT", "5000")
    GUEST_CREDIT_LIMIT = int(os.getenv("GUEST_CREDIT_LIMIT", "5"))
    USER_CREDIT_LIMIT = int(os.getenv("USER_CREDIT_LIMIT", "15"))

    # Enrichment v3 (hibrido Gemini 2.5 Flash Lite + 3.1 Flash Lite Preview)
    ENRICHMENT_MODE = os.getenv("ENRICHMENT_MODE", "gemini_hybrid_v3")
    ENRICHMENT_V3_PROMPT_PATH = os.getenv(
        "ENRICHMENT_V3_PROMPT_PATH",
        "backend/prompts/enrichment_v3_prompt.txt",
    )
    ENRICHMENT_GEMINI_25_MODEL = os.getenv(
        "ENRICHMENT_GEMINI_25_MODEL", "gemini-2.5-flash-lite"
    )
    ENRICHMENT_GEMINI_31_MODEL = os.getenv(
        "ENRICHMENT_GEMINI_31_MODEL", "gemini-3.1-flash-lite-preview"
    )
    ENRICHMENT_V3_ENABLE_AUTO_CREATE = (
        os.getenv("ENRICHMENT_V3_ENABLE_AUTO_CREATE", "true").lower() == "true"
    )
    ENRICHMENT_V3_CONTROLLED_ONLY = (
        os.getenv("ENRICHMENT_V3_CONTROLLED_ONLY", "true").lower() == "true"
    )
    # Fallback do enrichment v3: se o hibrido (2.5 + 3.1) falhar,
    # cai para Gemini 2.5 Flash Lite puro (sem escalacao).
    # ThinkingLeakError NAO e capturada pelo fallback.
    ENRICHMENT_V3_FALLBACK_ENABLED = (
        os.getenv("ENRICHMENT_V3_FALLBACK_ENABLED", "true").lower() == "true"
    )
    ENRICHMENT_V3_FALLBACK_MODEL = os.getenv(
        "ENRICHMENT_V3_FALLBACK_MODEL", "gemini-2.5-flash-lite"
    )
