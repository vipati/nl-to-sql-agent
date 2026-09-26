import atexit
import shutil
import tempfile
import threading
import time
from datetime import date, datetime, timedelta
from datetime import time as dt_time
from decimal import Decimal
from functools import cache
from pathlib import Path
from typing import Any

import duckdb
from pydantic import BaseModel

from nl_to_sql_agent.schema import DatabaseSchema, introspect_schema

SEED_SQL_PATH = Path(__file__).resolve().parents[2] / "data" / "sample_ecommerce.sql"


class QueryResult(BaseModel):
    columns: list[str]
    rows: list[list[Any]]
    row_count: int
    truncated: bool = False
    elapsed_ms: float = 0.0


class QueryTimeoutError(RuntimeError):
    """The query ran longer than the configured timeout and was interrupted."""


class Database:
    """Read-only access to a DuckDB file.

    Every query gets its own connection that is opened read-only, with file and network
    access disabled and the configuration locked, so SQL cannot turn the protections back
    off. This is the second safety layer: it holds even if the SQL guard has a gap.
    """

    def __init__(
        self,
        path: str | Path,
        max_rows: int = 1000,
        timeout_seconds: float = 5.0,
    ) -> None:
        self.path = Path(path)
        if not self.path.exists():
            raise FileNotFoundError(f"DuckDB database not found: {self.path}")
        self.max_rows = max_rows
        self.timeout_seconds = timeout_seconds
        self._schema: DatabaseSchema | None = None

    @classmethod
    def sample(cls, max_rows: int = 1000, timeout_seconds: float = 5.0) -> "Database":
        """The bundled ecommerce sample, built once per process from data/sample_ecommerce.sql."""
        return cls(sample_database_path(), max_rows=max_rows, timeout_seconds=timeout_seconds)

    def connect(self) -> duckdb.DuckDBPyConnection:
        return duckdb.connect(
            str(self.path),
            read_only=True,
            config={"enable_external_access": False, "lock_configuration": True},
        )

    @property
    def schema(self) -> DatabaseSchema:
        if self._schema is None:
            connection = self.connect()
            try:
                self._schema = introspect_schema(connection)
            finally:
                connection.close()
        return self._schema

    def execute(self, sql: str) -> QueryResult:
        """Run one query with a timeout, returning at most max_rows rows."""
        connection = self.connect()
        timer = threading.Timer(self.timeout_seconds, connection.interrupt)
        started = time.perf_counter()
        timer.start()
        try:
            cursor = connection.execute(sql)
            columns = [column[0] for column in cursor.description or []]
            fetched = cursor.fetchmany(self.max_rows + 1)
        except duckdb.InterruptException as error:
            raise QueryTimeoutError(
                f"Query exceeded the {self.timeout_seconds:g}s timeout and was cancelled."
            ) from error
        finally:
            timer.cancel()
            connection.close()

        truncated = len(fetched) > self.max_rows
        rows = [[_to_json_value(value) for value in row] for row in fetched[: self.max_rows]]
        return QueryResult(
            columns=columns,
            rows=rows,
            row_count=len(rows),
            truncated=truncated,
            elapsed_ms=(time.perf_counter() - started) * 1000,
        )


@cache
def sample_database_path(seed_sql_path: Path = SEED_SQL_PATH) -> Path:
    directory = Path(tempfile.mkdtemp(prefix="nl2sql-"))
    atexit.register(shutil.rmtree, directory, ignore_errors=True)
    path = directory / "sample.duckdb"
    connection = duckdb.connect(str(path))
    try:
        connection.execute(seed_sql_path.read_text(encoding="utf-8"))
    finally:
        connection.close()
    return path


def _to_json_value(value: Any) -> Any:
    if isinstance(value, Decimal):
        return float(value)
    if isinstance(value, datetime | date | dt_time):
        return value.isoformat()
    if isinstance(value, timedelta):
        return str(value)
    if isinstance(value, bytes):
        return value.hex()
    if value is None or isinstance(value, bool | int | float | str | list | dict):
        return value
    return str(value)
