from socket import gethostname

from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    DATABASE_URL: str
    REDIS_URL: str = "redis://localhost:6379/0"
    REDIS_QUEUE: str = "pm_webhook_events"

    WEBHOOK_SIGNATURE_SECRET: str = ""
    WEBHOOK_SIGNATURE_HEADER: str = "X-Op-Signature"
    WEBHOOK_REQUIRE_SIGNATURE: bool = False

    WORKER_ID: str = gethostname()
    WORKER_LEASE_SECONDS: int = 300
    WORKER_MAX_EVENT_ATTEMPTS: int = 5
    WORKER_RETRY_BASE_SECONDS: int = 30
    WORKER_RETRY_MAX_SECONDS: int = 600
    PLANNING_AGENT_CORE_URL: str = "http://planning-agent-core:8000"
    PLANNING_AGENT_CORE_TIMEOUT_SECONDS: float = 30.0


settings = Settings()
