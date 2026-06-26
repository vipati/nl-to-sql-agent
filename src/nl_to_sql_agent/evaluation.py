import json
from pathlib import Path
from typing import Any

from pydantic import BaseModel

from nl_to_sql_agent.database import execute_sql
from nl_to_sql_agent.generator import generate_sql
from nl_to_sql_agent.schema import ecommerce_schema
from nl_to_sql_agent.validator import validate_sql

EVAL_DATASET_PATH = Path(__file__).resolve().parents[2] / "data" / "eval" / "questions.jsonl"


class EvaluationCase(BaseModel):
    id: str
    question: str
    expected_columns: list[str]
    expected_rows: list[dict[str, Any]]
    difficulty: str


class EvaluationCaseResult(BaseModel):
    id: str
    question: str
    generated: bool
    valid_sql: bool
    executed: bool
    correct_result: bool
    error: str | None = None


class EvaluationReport(BaseModel):
    total: int
    generation_success_rate: float
    sql_validity_rate: float
    execution_success_rate: float
    result_accuracy_rate: float
    cases: list[EvaluationCaseResult]


def load_cases(dataset_path: Path = EVAL_DATASET_PATH) -> list[EvaluationCase]:
    cases: list[EvaluationCase] = []
    for line in dataset_path.read_text(encoding="utf-8").splitlines():
        if line.strip():
            cases.append(EvaluationCase.model_validate_json(line))
    return cases


def run_evaluation(cases: list[EvaluationCase] | None = None) -> EvaluationReport:
    eval_cases = cases or load_cases()
    results = [_run_case(case) for case in eval_cases]
    total = len(results)

    return EvaluationReport(
        total=total,
        generation_success_rate=_rate(results, "generated"),
        sql_validity_rate=_rate(results, "valid_sql"),
        execution_success_rate=_rate(results, "executed"),
        result_accuracy_rate=_rate(results, "correct_result"),
        cases=results,
    )


def _run_case(case: EvaluationCase) -> EvaluationCaseResult:
    try:
        sql = generate_sql(case.question, ecommerce_schema())
    except Exception as exc:
        return EvaluationCaseResult(
            id=case.id,
            question=case.question,
            generated=False,
            valid_sql=False,
            executed=False,
            correct_result=False,
            error=str(exc),
        )

    validation = validate_sql(sql)
    if not validation.valid:
        return EvaluationCaseResult(
            id=case.id,
            question=case.question,
            generated=True,
            valid_sql=False,
            executed=False,
            correct_result=False,
            error=validation.error,
        )

    try:
        execution = execute_sql(sql)
    except Exception as exc:
        return EvaluationCaseResult(
            id=case.id,
            question=case.question,
            generated=True,
            valid_sql=True,
            executed=False,
            correct_result=False,
            error=str(exc),
        )

    return EvaluationCaseResult(
        id=case.id,
        question=case.question,
        generated=True,
        valid_sql=True,
        executed=True,
        correct_result=(
            execution.columns == case.expected_columns
            and _normalize_rows(execution.rows) == _normalize_rows(case.expected_rows)
        ),
    )


def _normalize_rows(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return [json.loads(json.dumps(row, sort_keys=True)) for row in rows]


def _rate(results: list[EvaluationCaseResult], field_name: str) -> float:
    if not results:
        return 0.0
    passed = sum(1 for result in results if getattr(result, field_name))
    return passed / len(results)

