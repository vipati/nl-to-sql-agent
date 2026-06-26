from fastapi import FastAPI
from pydantic import BaseModel, Field

from nl_to_sql_agent.generator import generate_sql
from nl_to_sql_agent.repair import RepairAttempt, execute_with_repair
from nl_to_sql_agent.schema import ecommerce_schema

app = FastAPI(title="NL-to-SQL Agent", version="0.1.0")


class QueryRequest(BaseModel):
    question: str = Field(min_length=3, examples=["show total revenue by customer"])


class QueryResponse(BaseModel):
    question: str
    sql: str
    valid: bool
    repaired_sql: str | None = None
    repaired: bool = False
    execution: RepairAttempt | None = None
    error: str | None = None


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok"}


@app.post("/query", response_model=QueryResponse)
def query(request: QueryRequest) -> QueryResponse:
    sql = generate_sql(request.question, ecommerce_schema())
    execution = execute_with_repair(sql)
    return QueryResponse(
        question=request.question,
        sql=sql,
        valid=execution.valid,
        repaired_sql=execution.repaired_sql if execution.changed else None,
        repaired=execution.changed,
        execution=execution,
        error=execution.error,
    )
