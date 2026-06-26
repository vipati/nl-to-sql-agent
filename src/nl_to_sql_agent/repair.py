import re

from pydantic import BaseModel

from nl_to_sql_agent.database import QueryExecutionResult, execute_sql
from nl_to_sql_agent.validator import validate_sql


class RepairAttempt(BaseModel):
    original_sql: str
    repaired_sql: str
    changed: bool
    valid: bool
    executed: bool
    error: str | None = None
    execution: QueryExecutionResult | None = None


REPAIR_RULES = {
    "customer_name": "name",
    "amount": "total_amount",
    "order_status": "status",
}

TABLE_REPAIR_RULES = {
    r"\bcustomer\b": "customers",
}


def repair_sql(sql: str) -> str:
    repaired = sql
    for old, new in REPAIR_RULES.items():
        repaired = repaired.replace(old, new)
    for pattern, replacement in TABLE_REPAIR_RULES.items():
        repaired = re.sub(pattern, replacement, repaired)
    return repaired


def execute_with_repair(sql: str) -> RepairAttempt:
    validation = validate_sql(sql)
    if validation.valid:
        try:
            execution = execute_sql(sql)
            return RepairAttempt(
                original_sql=sql,
                repaired_sql=sql,
                changed=False,
                valid=True,
                executed=True,
                execution=execution,
            )
        except Exception as exc:
            original_error = str(exc)
    else:
        original_error = validation.error

    repaired_sql = repair_sql(sql)
    repaired_validation = validate_sql(repaired_sql)
    if not repaired_validation.valid:
        return RepairAttempt(
            original_sql=sql,
            repaired_sql=repaired_sql,
            changed=repaired_sql != sql,
            valid=False,
            executed=False,
            error=repaired_validation.error or original_error,
        )

    try:
        execution = execute_sql(repaired_sql)
    except Exception as exc:
        return RepairAttempt(
            original_sql=sql,
            repaired_sql=repaired_sql,
            changed=repaired_sql != sql,
            valid=True,
            executed=False,
            error=str(exc),
        )

    return RepairAttempt(
        original_sql=sql,
        repaired_sql=repaired_sql,
        changed=repaired_sql != sql,
        valid=True,
        executed=True,
        execution=execution,
    )
