import os
from dotenv import load_dotenv

load_dotenv()

def env_bool(name: str, default: bool = False) -> bool:
    value = os.getenv(name)
    return default if value is None else value.strip().lower() in {"1", "true", "yes", "on"}

def env_float(name: str, default: float) -> float:
    try:
        return float(os.getenv(name, default))
    except (TypeError, ValueError):
        return default

def env_int(name: str, default: int) -> int:
    try:
        return int(os.getenv(name, default))
    except (TypeError, ValueError):
        return default

DATABASE_PATH = os.getenv("DATABASE_PATH", "smartroute.db")
GROQ_API_KEY = os.getenv("GROQ_API_KEY", "")
OPENROUTER_API_KEY = os.getenv("OPENROUTER_API_KEY", "")
GROQ_BASE_URL = os.getenv("GROQ_BASE_URL", "https://api.groq.com/openai/v1").rstrip("/")
OPENROUTER_BASE_URL = os.getenv("OPENROUTER_BASE_URL", "https://openrouter.ai/api/v1").rstrip("/")
PRIMARY_PROVIDER = os.getenv("PRIMARY_PROVIDER", "groq").lower()
FALLBACK_PROVIDER = os.getenv("FALLBACK_PROVIDER", "openrouter").lower()

MODELS = {
    "easy": os.getenv("EASY_MODEL", "llama-3.1-8b-instant"),
    "medium": os.getenv("MEDIUM_MODEL", "llama-3.3-70b-versatile"),
    "hard": os.getenv("HARD_MODEL", "llama-3.3-70b-versatile"),
    "router": os.getenv("ROUTER_MODEL", "llama-3.1-8b-instant"),
    "judge": os.getenv("JUDGE_MODEL", "llama-3.3-70b-versatile"),
}

PRICES = {
    "easy": (env_float("EASY_INPUT_PRICE_PER_1M", 0.05), env_float("EASY_OUTPUT_PRICE_PER_1M", 0.08)),
    "medium": (env_float("MEDIUM_INPUT_PRICE_PER_1M", 0.59), env_float("MEDIUM_OUTPUT_PRICE_PER_1M", 0.79)),
    "hard": (env_float("HARD_INPUT_PRICE_PER_1M", 0.59), env_float("HARD_OUTPUT_PRICE_PER_1M", 0.79)),
}
CACHE_TTL_SECONDS = env_int("CACHE_TTL_SECONDS", 3600)
EXACT_CACHE_ENABLED = env_bool("EXACT_CACHE_ENABLED", True)
SEMANTIC_CACHE_ENABLED = env_bool("SEMANTIC_CACHE_ENABLED", False)
SEMANTIC_CACHE_THRESHOLD = env_float("SEMANTIC_CACHE_THRESHOLD", 0.93)
SEMANTIC_MODEL = os.getenv("SEMANTIC_MODEL", "sentence-transformers/all-MiniLM-L6-v2")
MAX_RETRIES = env_int("MAX_RETRIES", 2)
RETRY_BASE_SECONDS = env_float("RETRY_BASE_SECONDS", 1.0)
CIRCUIT_FAILURE_THRESHOLD = env_int("CIRCUIT_FAILURE_THRESHOLD", 3)
CIRCUIT_RESET_SECONDS = env_int("CIRCUIT_RESET_SECONDS", 30)
API_KEY = os.getenv("API_KEY", "")
RATE_LIMIT_PER_MINUTE = env_int("RATE_LIMIT_PER_MINUTE", 60)
