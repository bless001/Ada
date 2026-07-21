from pathlib import Path
from socket import gethostname

from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    DATABASE_URL: str
    REDIS_URL: str = "redis://localhost:6379/0"
    REDIS_QUEUE: str = "pm_webhook_events"

    WEBHOOK_SIGNATURE_SECRET: str = ""
    WEBHOOK_SIGNATURE_HEADER: str = "X-Op-Signature"
    WEBHOOK_REQUIRE_SIGNATURE: bool = False

    OPENPROJECT_BASE_URL: str = "http://openproject"
    OPENPROJECT_API_TOKEN: str = ""
    OPENPROJECT_API_TOKEN_FILE: str = ""
    OPENPROJECT_API_HOST_HEADER: str = ""

    AGENT_TRIGGER_STATUS_NAMES: str = "In Development,Agent Development"
    WORKER_ID: str = gethostname()
    WORKER_LEASE_SECONDS: int = 300
    WORKER_MAX_EVENT_ATTEMPTS: int = 5
    WORKER_RETRY_BASE_SECONDS: int = 30
    WORKER_RETRY_MAX_SECONDS: int = 600

    NEO4J_URI: str = "bolt://neo4j:7687"
    NEO4J_USER: str = "neo4j"
    NEO4J_PASSWORD: str = ""
    WEAVIATE_URL: str = "http://weaviate:8080"

    @property
    def openproject_api_token(self) -> str:
        if self.OPENPROJECT_API_TOKEN.strip():
            return self.OPENPROJECT_API_TOKEN.strip()

        if self.OPENPROJECT_API_TOKEN_FILE.strip():
            path = Path(self.OPENPROJECT_API_TOKEN_FILE)
            if path.exists():
                return path.read_text(encoding="utf-8").strip()

        return ""

    @property
    def agent_trigger_statuses(self) -> set[str]:
        return {
            item.strip().lower()
            for item in self.AGENT_TRIGGER_STATUS_NAMES.split(",")
            if item.strip()
        }


settings = Settings()
