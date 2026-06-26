from pydantic import BaseModel
from sqlglot import parse_one


class ValidationResult(BaseModel):
    valid: bool
    error: str | None = None


def validate_sql(sql: str, dialect: str = "duckdb") -> ValidationResult:
    try:
        parse_one(sql, read=dialect)
    except Exception as exc:
        return ValidationResult(valid=False, error=str(exc))

    return ValidationResult(valid=True)

