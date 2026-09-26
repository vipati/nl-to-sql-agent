import threading
from collections import Counter, deque
from typing import Any

from fastapi import FastAPI, HTTPException
from pydantic import BaseModel, Field

from nl_to_sql_agent import __version__
from nl_to_sql_agent.agent import Agent, AgentResult
from nl_to_sql_agent.schema import DatabaseSchema, format_schema_context


class QueryRequest(BaseModel):
    question: str = Field(min_length=3, max_length=1000, examples=["top 5 customers by spend"])


class SQLRequest(BaseModel):
    sql: str = Field(min_length=1, max_length=10_000, examples=["SELECT COUNT(*) FROM orders"])


class SchemaResponse(BaseModel):
    schema_: DatabaseSchema = Field(alias="schema")
    prompt_context: str


class Metrics:
    """Request counters and a bounded latency window, safe across FastAPI's worker threads."""

    def __init__(self, window: int = 1000) -> None:
        self._lock = threading.Lock()
        self._statuses: Counter[str] = Counter()
        self._repaired = 0
        self._latencies: deque[float] = deque(maxlen=window)

    def record(self, result: AgentResult) -> None:
        with self._lock:
            self._statuses[result.status] += 1
            self._repaired += int(len(result.attempts) > 1)
            self._latencies.append(result.latency_ms)

    def snapshot(self) -> dict[str, Any]:
        with self._lock:
            latencies = sorted(self._latencies)
            statuses = dict(self._statuses)
            repaired = self._repaired

        def percentile(fraction: float) -> float | None:
            if not latencies:
                return None
            return latencies[min(len(latencies) - 1, int(fraction * len(latencies)))]

        return {
            "requests": sum(statuses.values()),
            "by_status": statuses,
            "repaired": repaired,
            "latency_ms_p50": percentile(0.5),
            "latency_ms_p95": percentile(0.95),
        }


def create_app(agent: Agent | None = None) -> FastAPI:
    agent = agent or Agent.from_settings()
    metrics = Metrics()
    app = FastAPI(
        title="NL-to-SQL Agent",
        version=__version__,
        description="Natural-language questions to guarded, read-only SQL.",
    )

    @app.get("/health")
    def health() -> dict[str, str]:
        return {
            "status": "ok",
            "provider": agent.provider.name,
            "database": agent.database.path.name,
        }

    @app.get("/schema", response_model=SchemaResponse, response_model_by_alias=True)
    def schema() -> SchemaResponse:
        db_schema = agent.database.schema
        return SchemaResponse(schema=db_schema, prompt_context=format_schema_context(db_schema))

    @app.post("/query", response_model=AgentResult)
    def query(request: QueryRequest) -> AgentResult:
        """Answer a question. Agent outcomes (blocked, invalid, ...) are reported in `status`."""
        result = agent.ask(request.question)
        metrics.record(result)
        if result.status == "provider_error":
            raise HTTPException(status_code=502, detail=result.error)
        return result

    @app.post("/sql", response_model=AgentResult)
    def run_sql(request: SQLRequest) -> AgentResult:
        """Run caller-supplied SQL through the same guard and read-only executor."""
        result = agent.run_sql(request.sql)
        metrics.record(result)
        if result.status in ("blocked", "invalid"):
            raise HTTPException(
                status_code=400,
                detail={"status": result.status, "error": result.error},
            )
        return result

    @app.get("/metrics")
    def get_metrics() -> dict[str, Any]:
        return metrics.snapshot()

    return app


app = create_app()
