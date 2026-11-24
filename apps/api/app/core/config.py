from functools import lru_cache
from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict

REPO_ROOT = Path(__file__).resolve().parents[4]


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=(REPO_ROOT / ".env", ".env"), extra="ignore"
    )

    database_url: str = "postgresql+asyncpg://zhkh24:zhkh24_dev@localhost:5432/zhkh24"
    qdrant_url: str = "http://localhost:6333"
    qdrant_path: Path | None = None  # встроенный режим Qdrant для разработки без Docker

    embed_model: str = "BAAI/bge-m3"
    rerank_model: str = "BAAI/bge-reranker-v2-m3"
    ml_device: str = "auto"  # auto | cpu | mps | cuda
    ml_dtype: str = "auto"  # auto (fp16 на mps/cuda, fp32 на cpu) | float16 | float32 — fp16 вдвое меньше памяти
    rerank_enabled: bool = True
    rerank_pool: int = 20  # сколько лучших кандидатов RRF переоценивает реранкер
    rerank_max_length: int = 384  # токенов на пару (запрос, фрагмент); пункты закона обычно короче
    # акты специального жилищного законодательства: их лучшие кандидаты всегда попадают в реранкинг
    core_acts: str = "ZHO,RULES_MGMT,RULES_DECISIONS,METHOD_BUDGET,COMM_SERVICES"
    core_rerank_extra: int = 4
    redis_url: str = "redis://localhost:6379/0"
    s3_endpoint: str = "http://localhost:9000"

    # anthropic — Claude API по ключу; gemini — Vertex AI (ключ ментора); claude_code — локальный `claude -p` по подписке
    # (только разработка на своём компьютере); none — без LLM (демо-режим)
    llm_provider: str = "anthropic"
    claude_bin: str = ""  # путь к claude; пусто — поиск в PATH и стандартных местах
    claude_model: str = ""  # пусто — модель по умолчанию в Claude Code
    claude_timeout: float = 240.0
    claude_max_parallel: int = 2
    anthropic_api_key: str = ""
    llm_model: str = "claude-opus-5-5"
    llm_fallbacks: str = "default"  # server-side fallback при отказе модели; "off" — выключить

    # gemini — Vertex AI по ключу ментора (проект eknot-zhkh-lawyer-balaiym). Ключ только в .env сервера.
    gemini_api_key: str = ""
    gemini_model: str = ""  # ID модели из Model Garden; для разработки — Flash
    gemini_project: str = ""  # ID проекта Google Cloud; без него Vertex отвечает 403 «project None»
    gemini_location: str = "global"
    gemini_max_output_tokens: int = 8192
    gemini_timeout_sec: int = 120  # один запрос к Vertex AI
    gemini_thinking_budget: int = 2048  # ограничиваем мышление: лимит проекта $95 в месяц

    # Многошаговая консультация (app/services/lawyer/analysis.py)
    decompose_enabled: bool = True  # делить сообщение на подвопросы, искать и разбирать каждый отдельно
    max_sub_questions: int = 4
    branch_top_k: int = 6  # норм на подвопрос (плюс связанные по графу)
    branch_max_output_tokens: int = 3000
    branch_followup_rounds: int = 1  # сколько раз ветка может дозапросить нормы (итеративный поиск)
    factcheck_enabled: bool = True  # второй проход: проверка ответа по нормам и одна переработка
    factcheck_max_output_tokens: int = 3000
    factcheck_rounds: int = 2  # сколько раз можно исправить ответ по замечаниям (после каждого — новая проверка)
    graph_limit: int = 5  # сколько связанных по графу закона пунктов добавлять к выдаче

    jwt_secret: str = "change-me-in-production"
    cors_origins: str = "http://localhost:3000"

    adilet_cache_dir: Path = REPO_ROOT / "data" / "adilet_cache"
    adilet_request_delay_sec: float = 3.0

    @property
    def cors_origin_list(self) -> list[str]:
        return [o.strip() for o in self.cors_origins.split(",") if o.strip()]


@lru_cache
def get_settings() -> Settings:
    return Settings()
