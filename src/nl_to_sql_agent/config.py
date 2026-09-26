import os
from dataclasses import dataclass


def _env(name: str, default: str) -> str:
    return os.environ.get(f"NL2SQL_{name}", default)


@dataclass(frozen=True)
class Settings:
    """Runtime configuration, read from NL2SQL_* environment variables."""

    provider: str = "rules"
    base_url: str = "http://localhost:11434/v1"
    api_key: str = ""
    model: str = "llama3.1:8b"
    llm_timeout_seconds: float = 60.0
    database: str = ""
    max_rows: int = 1000
    query_timeout_seconds: float = 5.0
    max_repair_attempts: int = 2

    @classmethod
    def from_env(cls) -> "Settings":
        return cls(
            provider=_env("PROVIDER", cls.provider),
            base_url=_env("BASE_URL", cls.base_url),
            api_key=_env("API_KEY", cls.api_key),
            model=_env("MODEL", cls.model),
            llm_timeout_seconds=float(_env("LLM_TIMEOUT_SECONDS", str(cls.llm_timeout_seconds))),
            database=_env("DATABASE", cls.database),
            max_rows=int(_env("MAX_ROWS", str(cls.max_rows))),
            query_timeout_seconds=float(
                _env("QUERY_TIMEOUT_SECONDS", str(cls.query_timeout_seconds))
            ),
            max_repair_attempts=int(_env("MAX_REPAIR_ATTEMPTS", str(cls.max_repair_attempts))),
        )
