import os
from dotenv import load_dotenv

load_dotenv()


class Config:
    ANTHROPIC_API_KEY = os.getenv("ANTHROPIC_API_KEY")
    DASHSCOPE_API_KEY = os.getenv("DASHSCOPE_API_KEY")
    DASHSCOPE_BASE_URL = os.getenv(
        "DASHSCOPE_BASE_URL",
        "https://dashscope-intl.aliyuncs.com/compatible-mode/v1",
    )
    BACO_PROVIDER = os.getenv("BACO_PROVIDER", "qwen").lower()
    BACO_MODEL = os.getenv("BACO_MODEL", "qwen3.6-plus")
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
    # Modelo escalado: 3.1 Flash Lite Preview.
    # Ativado para escalacao pois o 2.5 puro provou insuficiente (output explode em loop).
    # SEGURANCA: `ThinkingLeakError` em `backend/tools/media.py` aborta se
    # thoughts_token_count > 0 — nunca paga thinking silenciosamente.
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

    BULK_INGEST_TOKEN = os.getenv("BULK_INGEST_TOKEN", "")
    BULK_INGEST_BATCH_SIZE = int(os.getenv("BULK_INGEST_BATCH_SIZE", "10000"))
    BULK_INGEST_MAX_ITEMS = int(os.getenv("BULK_INGEST_MAX_ITEMS", "50000"))
    # DQ V3 Escopo 4: cut-off defensivo para BLOCKED_QUEUE_EXPLOSION.
    # Se um run gerar mais de INGEST_QUEUE_ABS_CAP reviews, OU se o ratio
    # reviews / valid exceder INGEST_QUEUE_PCT_CAP, o apply eh abortado
    # sem nenhum write.
    INGEST_QUEUE_ABS_CAP = int(os.getenv("INGEST_QUEUE_ABS_CAP", "20000"))
    INGEST_QUEUE_PCT_CAP = float(os.getenv("INGEST_QUEUE_PCT_CAP", "0.05"))

    # ========================================================================
    # Winegod Data Ops / Control Plane (Fase 1)
    # Schema `ops.*` - observabilidade pura. Nada toca dados de negocio.
    # Ver WINEGOD_PLATAFORMA_CENTRAL_SCRAPERS_DESIGN_FREEZE.md
    # ========================================================================
    # Tokens (SEM valor real no repo - preencher em .env local / Render)
    OPS_TOKEN = os.getenv("OPS_TOKEN", "")
    OPS_DASHBOARD_TOKEN = os.getenv("OPS_DASHBOARD_TOKEN", "")

    # Feature flags - defaults por fase
    OPS_API_ENABLED = os.getenv("OPS_API_ENABLED", "true").lower() == "true"
    OPS_WRITE_ENABLED = os.getenv("OPS_WRITE_ENABLED", "true").lower() == "true"
    OPS_DASHBOARD_ENABLED = (
        os.getenv("OPS_DASHBOARD_ENABLED", "false").lower() == "true"
    )
    OPS_ALERTS_ENABLED = (
        os.getenv("OPS_ALERTS_ENABLED", "false").lower() == "true"
    )
    OPS_CANARY_ENABLED = (
        os.getenv("OPS_CANARY_ENABLED", "true").lower() == "true"
    )
    OPS_DEBUG_KEEP_SAMPLE = (
        os.getenv("OPS_DEBUG_KEEP_SAMPLE", "false").lower() == "true"
    )

    # Retencao em batches de 10k (REGRA 5 do CLAUDE.md)
    OPS_RETENTION_BATCH_SIZE = int(os.getenv("OPS_RETENTION_BATCH_SIZE", "10000"))

    # Flask session secret para o dashboard /ops (Fase 3).
    # Em producao, setar via env. Local usa fallback.
    OPS_SESSION_SECRET = os.getenv("OPS_SESSION_SECRET", "")
