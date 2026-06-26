from pathlib import Path
from typing import Any

import duckdb
from pydantic import BaseModel

SEED_SQL_PATH = Path(__file__).resolve().parents[2] / "data" / "sample_ecommerce.sql"


class QueryExecutionResult(BaseModel):
    columns: list[str]
    rows: list[dict[str, Any]]
    row_count: int


def execute_sql(sql: str, seed_sql_path: Path = SEED_SQL_PATH) -> QueryExecutionResult:
    """Execute SQL against a fresh in-memory DuckDB seeded with sample ecommerce data."""
    connection = duckdb.connect(database=":memory:")
    try:
        connection.execute(seed_sql_path.read_text(encoding="utf-8"))
        result = connection.execute(sql)
        columns = [column[0] for column in result.description or []]
        tuples = result.fetchall()
    finally:
        connection.close()

    rows = [dict(zip(columns, row, strict=True)) for row in tuples]
    return QueryExecutionResult(columns=columns, rows=rows, row_count=len(rows))

