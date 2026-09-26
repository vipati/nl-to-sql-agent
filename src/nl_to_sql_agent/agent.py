import time
from typing import Literal

import duckdb
from pydantic import BaseModel

from nl_to_sql_agent.config import Settings
from nl_to_sql_agent.database import Database, QueryResult, QueryTimeoutError
from nl_to_sql_agent.guard import check_sql
from nl_to_sql_agent.providers import (
    ProviderError,
    SQLProvider,
    UnanswerableError,
    build_request,
    provider_from_settings,
)
from nl_to_sql_agent.repair import autofix_identifiers

Status = Literal[
    "ok", "unanswerable", "blocked", "invalid", "execution_error", "timeout", "provider_error"
]
Stage = Literal["generate", "autofix", "llm_repair", "user"]
ErrorKind = Literal["syntax", "unsafe", "schema", "execution", "timeout"]


class Attempt(BaseModel):
    stage: Stage
    sql: str
    ok: bool
    error_kind: ErrorKind | None = None
    error: str | None = None


class AgentResult(BaseModel):
    question: str | None
    status: Status
    sql: str | None = None
    attempts: list[Attempt] = []
    result: QueryResult | None = None
    error: str | None = None
    provider_calls: int = 0
    prompt_tokens: int = 0
    completion_tokens: int = 0
    latency_ms: float = 0.0


_FINAL_STATUS: dict[ErrorKind, Status] = {
    "syntax": "invalid",
    "schema": "invalid",
    "unsafe": "blocked",
    "execution": "execution_error",
    "timeout": "timeout",
}


class Agent:
    """Question -> SQL -> guard -> execute, with bounded self-correction.

    On a syntax, schema, or execution error, the agent first tries a deterministic
    identifier fix (no model call), then asks the provider to repair its query using
    the error message. Unsafe SQL fails closed and is never retried, and timeouts are
    not retried either. Each question uses at most 1 + max_repair_attempts attempts.
    """

    def __init__(
        self,
        provider: SQLProvider,
        database: Database,
        max_repair_attempts: int = 2,
    ) -> None:
        self.provider = provider
        self.database = database
        self.max_repair_attempts = max_repair_attempts

    @classmethod
    def from_settings(cls, settings: Settings | None = None) -> "Agent":
        settings = settings or Settings.from_env()
        if settings.database:
            database = Database(
                settings.database,
                max_rows=settings.max_rows,
                timeout_seconds=settings.query_timeout_seconds,
            )
        else:
            database = Database.sample(
                max_rows=settings.max_rows, timeout_seconds=settings.query_timeout_seconds
            )
        return cls(provider_from_settings(settings), database, settings.max_repair_attempts)

    def ask(self, question: str) -> AgentResult:
        started = time.perf_counter()
        schema = self.database.schema
        result = AgentResult(question=question, status="unanswerable")

        stage: Stage = "generate"
        request = build_request(question, schema)
        repairs = 0
        while True:
            try:
                generation = self.provider.generate(request)
            except UnanswerableError as error:
                if not result.attempts:
                    result.error = str(error)
                break
            except ProviderError as error:
                result.status, result.error = "provider_error", str(error)
                break
            finally:
                result.provider_calls += 1
            result.prompt_tokens += generation.prompt_tokens or 0
            result.completion_tokens += generation.completion_tokens or 0

            sql = generation.sql
            while True:
                attempt, query_result = self._run(sql, stage)
                result.attempts.append(attempt)
                if attempt.ok:
                    result.status, result.sql, result.result = "ok", attempt.sql, query_result
                    result.error = None
                    return _finish(result, started)
                result.status, result.error = _FINAL_STATUS[attempt.error_kind], attempt.error
                if (
                    attempt.error_kind in ("unsafe", "timeout")
                    or repairs >= self.max_repair_attempts
                ):
                    return _finish(result, started)
                repairs += 1
                fixed = autofix_identifiers(sql, schema) if attempt.error_kind == "schema" else None
                if not fixed:
                    break
                sql, stage = fixed, "autofix"

            stage = "llm_repair"
            request = build_request(question, schema, previous_sql=sql, error=attempt.error)
        return _finish(result, started)

    def run_sql(self, sql: str) -> AgentResult:
        """Guard and execute SQL written by a user, with no generation or repair."""
        started = time.perf_counter()
        attempt, query_result = self._run(sql, "user")
        result = AgentResult(question=None, status="ok", attempts=[attempt])
        if attempt.ok:
            result.sql, result.result = attempt.sql, query_result
        else:
            result.status, result.error = _FINAL_STATUS[attempt.error_kind], attempt.error
        return _finish(result, started)

    def _run(self, sql: str, stage: Stage) -> tuple[Attempt, QueryResult | None]:
        # One extra row lets the database report that results were truncated.
        guard = check_sql(sql, self.database.schema, row_limit=self.database.max_rows + 1)
        if not guard.ok:
            return Attempt(
                stage=stage, sql=sql, ok=False, error_kind=guard.error_kind, error=guard.error
            ), None
        try:
            query_result = self.database.execute(guard.sql)
        except QueryTimeoutError as error:
            return Attempt(
                stage=stage, sql=guard.sql, ok=False, error_kind="timeout", error=str(error)
            ), None
        except duckdb.Error as error:
            message = str(error).strip().splitlines()[0]
            return Attempt(
                stage=stage, sql=guard.sql, ok=False, error_kind="execution", error=message
            ), None
        return Attempt(stage=stage, sql=guard.sql, ok=True), query_result


def _finish(result: AgentResult, started: float) -> AgentResult:
    result.latency_ms = (time.perf_counter() - started) * 1000
    return result
