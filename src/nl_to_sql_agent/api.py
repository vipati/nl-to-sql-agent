from fastapi import FastAPI
from pydantic import BaseModel, Field

from nl_to_sql_agent.database import QueryExecutionResult, execute_sql
from nl_to_sql_agent.generator import generate_sql
from nl_to_sql_agent.schema import ecommerce_schema
from nl_to_sql_agent.validator import validate_sql

app = FastAPI(title="NL-to-SQL Agent", version="0.1.0")


class QueryRequest(BaseModel):
    question: str = Field(min_length=3, examples=["show total revenue by customer"])


class QueryResponse(BaseModel):
    question: str
    sql: str
    valid: bool
    execution: QueryExecutionResult | None = None
    error: str | None = None


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok"}


@app.post("/query", response_model=QueryResponse)
def query(request: QueryRequest) -> QueryResponse:
    sql = generate_sql(request.question, ecommerce_schema())
    validation = validate_sql(sql)
    execution = execute_sql(sql) if validation.valid else None
    return QueryResponse(
        question=request.question,
        sql=sql,
        valid=validation.valid,
        execution=execution,
        error=validation.error,
    )
