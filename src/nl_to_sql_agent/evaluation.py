"""Evaluation: execution accuracy on gold questions, plus an adversarial safety suite.

A prediction is correct when running it returns the same result as running the gold
SQL, the execution-accuracy (EX) metric used by Spider and BIRD. Two variants are
reported:

- strict: same number of columns, same values.
- lenient: the prediction may return extra columns, as long as the gold columns are all
  present. This forgives "What is the most expensive product?" answered with the name
  and the price.

Column names and column order never matter. Row order matters only for cases marked
`"ordered": true`. Numbers are compared after rounding to 2 decimal places.
"""

import json
import statistics
from collections import Counter
from collections.abc import Callable
from pathlib import Path
from typing import Any, Literal

from pydantic import BaseModel

from nl_to_sql_agent.agent import Agent, Status
from nl_to_sql_agent.database import Database, QueryResult
from nl_to_sql_agent.guard import check_sql

DATA_DIR = Path(__file__).resolve().parents[2] / "data" / "eval"
QUESTIONS_PATH = DATA_DIR / "questions.jsonl"
SAFETY_PATH = DATA_DIR / "safety.jsonl"


class EvalCase(BaseModel):
    id: str
    question: str
    gold_sql: str
    difficulty: Literal["easy", "medium", "hard"]
    ordered: bool = False


class SafetyCase(BaseModel):
    id: str
    sql: str
    expect: Literal["blocked", "allowed"]
    category: str


class CaseResult(BaseModel):
    id: str
    question: str
    difficulty: str
    status: Status
    predicted_sql: str | None
    correct: bool
    correct_strict: bool
    attempts: int
    repaired: bool
    provider_calls: int
    latency_ms: float
    prompt_tokens: int
    completion_tokens: int
    error: str | None = None


class SafetyResult(BaseModel):
    id: str
    category: str
    expect: str
    guard_verdict: Literal["blocked", "allowed"]
    reason: str | None
    engine_blocks_alone: bool | None  # for unsafe SQL: would the engine refuse it with no guard?
    passed: bool


class SafetyReport(BaseModel):
    unsafe_total: int
    unsafe_blocked: int
    safe_total: int
    safe_allowed: int
    engine_alone_blocked: int
    cases: list[SafetyResult]

    @property
    def passed(self) -> bool:
        return self.unsafe_blocked == self.unsafe_total and self.safe_allowed == self.safe_total


class EvalReport(BaseModel):
    provider: str
    model: str | None
    total: int
    execution_accuracy: float
    execution_accuracy_strict: float
    first_attempt_accuracy: float
    valid_sql_rate: float
    answered_rate: float
    unsafe_generated: int
    repaired_correct: int
    accuracy_by_difficulty: dict[str, float]
    latency_p50_ms: float
    latency_p95_ms: float
    mean_provider_calls: float
    mean_prompt_tokens: float
    mean_completion_tokens: float
    cases: list[CaseResult]
    safety: SafetyReport


def load_cases(path: Path = QUESTIONS_PATH) -> list[EvalCase]:
    return [EvalCase.model_validate_json(line) for line in _lines(path)]


def load_safety_cases(path: Path = SAFETY_PATH) -> list[SafetyCase]:
    return [SafetyCase.model_validate_json(line) for line in _lines(path)]


def run_evaluation(
    agent: Agent,
    cases: list[EvalCase] | None = None,
    safety_cases: list[SafetyCase] | None = None,
    model: str | None = None,
    progress: Callable[[CaseResult], None] | None = None,
) -> EvalReport:
    cases = cases if cases is not None else load_cases()
    _ = agent.database.schema  # introspect up front so the first case's latency is not inflated
    results = []
    for case in cases:
        result = run_case(agent, case)
        results.append(result)
        if progress:
            progress(result)

    total = len(results) or 1
    latencies = sorted(result.latency_ms for result in results) or [0.0]
    by_difficulty: dict[str, list[CaseResult]] = {}
    for result in results:
        by_difficulty.setdefault(result.difficulty, []).append(result)

    return EvalReport(
        provider=agent.provider.name,
        model=model,
        total=len(results),
        execution_accuracy=sum(r.correct for r in results) / total,
        execution_accuracy_strict=sum(r.correct_strict for r in results) / total,
        first_attempt_accuracy=sum(r.correct and not r.repaired for r in results) / total,
        valid_sql_rate=sum(r.status == "ok" for r in results) / total,
        answered_rate=sum(r.status != "unanswerable" for r in results) / total,
        unsafe_generated=sum(r.status == "blocked" for r in results),
        repaired_correct=sum(r.correct and r.repaired for r in results),
        accuracy_by_difficulty={
            difficulty: sum(r.correct for r in group) / len(group)
            for difficulty, group in sorted(
                by_difficulty.items(), key=lambda item: ["easy", "medium", "hard"].index(item[0])
            )
        },
        latency_p50_ms=statistics.median(latencies),
        latency_p95_ms=_percentile(latencies, 0.95),
        mean_provider_calls=sum(r.provider_calls for r in results) / total,
        mean_prompt_tokens=sum(r.prompt_tokens for r in results) / total,
        mean_completion_tokens=sum(r.completion_tokens for r in results) / total,
        cases=results,
        safety=run_safety_suite(agent.database, safety_cases),
    )


def run_case(agent: Agent, case: EvalCase) -> CaseResult:
    gold = agent.database.execute(case.gold_sql)
    outcome = agent.ask(case.question)
    correct = correct_strict = False
    if outcome.status == "ok" and outcome.result is not None:
        correct = results_match(outcome.result, gold, ordered=case.ordered)
        correct_strict = correct and len(outcome.result.columns) == len(gold.columns)
    return CaseResult(
        id=case.id,
        question=case.question,
        difficulty=case.difficulty,
        status=outcome.status,
        predicted_sql=outcome.sql or (outcome.attempts[-1].sql if outcome.attempts else None),
        correct=correct,
        correct_strict=correct_strict,
        attempts=len(outcome.attempts),
        repaired=len(outcome.attempts) > 1,
        provider_calls=outcome.provider_calls,
        latency_ms=outcome.latency_ms,
        prompt_tokens=outcome.prompt_tokens,
        completion_tokens=outcome.completion_tokens,
        error=outcome.error,
    )


def run_safety_suite(database: Database, cases: list[SafetyCase] | None = None) -> SafetyReport:
    cases = cases if cases is not None else load_safety_cases()
    results = []
    for case in cases:
        guard = check_sql(case.sql, database.schema)
        verdict: Literal["blocked", "allowed"] = "allowed" if guard.ok else "blocked"
        engine_blocks = None
        if case.expect == "blocked":
            # Defense-in-depth check: send the raw SQL straight to the read-only engine.
            try:
                database.execute(case.sql)
                engine_blocks = False
            except Exception:
                engine_blocks = True
        results.append(
            SafetyResult(
                id=case.id,
                category=case.category,
                expect=case.expect,
                guard_verdict=verdict,
                reason=guard.error,
                engine_blocks_alone=engine_blocks,
                passed=verdict == case.expect,
            )
        )
    unsafe = [r for r in results if r.expect == "blocked"]
    safe = [r for r in results if r.expect == "allowed"]
    return SafetyReport(
        unsafe_total=len(unsafe),
        unsafe_blocked=sum(r.passed for r in unsafe),
        safe_total=len(safe),
        safe_allowed=sum(r.passed for r in safe),
        engine_alone_blocked=sum(bool(r.engine_blocks_alone) for r in unsafe),
        cases=results,
    )


def results_match(predicted: QueryResult, gold: QueryResult, ordered: bool = False) -> bool:
    """True if `predicted` contains gold's columns (in any position) with the same rows."""
    if predicted.row_count != gold.row_count or len(predicted.columns) < len(gold.columns):
        return False
    if not gold.rows:
        return True
    gold_rows = [tuple(_normalize(value) for value in row) for row in gold.rows]
    predicted_rows = [tuple(_normalize(value) for value in row) for row in predicted.rows]
    gold_columns = [Counter(column) for column in zip(*gold_rows, strict=True)]
    predicted_columns = [Counter(column) for column in zip(*predicted_rows, strict=True)]

    # For each gold column, the predicted columns holding the same multiset of values.
    candidates = [
        [index for index, column in enumerate(predicted_columns) if column == gold_column]
        for gold_column in gold_columns
    ]
    expected = gold_rows if ordered else Counter(gold_rows)
    for mapping in _assignments(candidates):
        projected = [tuple(row[index] for index in mapping) for row in predicted_rows]
        if (projected if ordered else Counter(projected)) == expected:
            return True
    return False


def _assignments(candidates: list[list[int]], used: tuple[int, ...] = ()):
    """Injective choices of one predicted column per gold column."""
    if len(used) == len(candidates):
        yield used
        return
    for index in candidates[len(used)]:
        if index not in used:
            yield from _assignments(candidates, (*used, index))


def _normalize(value: Any) -> Any:
    if isinstance(value, bool) or value is None:
        return value
    if isinstance(value, int | float):
        return round(float(value), 2) + 0.0  # + 0.0 folds -0.0 into 0.0
    return str(value)


def _percentile(sorted_values: list[float], fraction: float) -> float:
    index = min(len(sorted_values) - 1, max(0, round(fraction * len(sorted_values)) - 1))
    return sorted_values[index]


def _lines(path: Path) -> list[str]:
    return [line for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]


def render_markdown(report: EvalReport) -> str:
    safety = report.safety
    label = report.provider + (f" ({report.model})" if report.model else "")
    lines = [
        f"## NL-to-SQL evaluation: {label}",
        "",
        "| Metric | Result |",
        "| --- | --- |",
        f"| Questions | {report.total} |",
        f"| **Execution accuracy** (extra columns allowed) | **{report.execution_accuracy:.0%}** |",
        f"| Execution accuracy, strict (exact columns) | {report.execution_accuracy_strict:.0%} |",
        f"| Accuracy on first attempt (no repair) | {report.first_attempt_accuracy:.0%} |",
        f"| Correct only after a repair | {report.repaired_correct} |",
        f"| Valid SQL rate (passed guard and executed) | {report.valid_sql_rate:.0%} |",
        f"| Questions answered (not declined) | {report.answered_rate:.0%} |",
        f"| Generated SQL blocked as unsafe | {report.unsafe_generated} |",
        "| Accuracy by difficulty | "
        + ", ".join(f"{k} {v:.0%}" for k, v in report.accuracy_by_difficulty.items())
        + " |",
        f"| Latency p50 / p95 (end to end) | {_ms(report.latency_p50_ms)} / "
        f"{_ms(report.latency_p95_ms)} |",
        f"| Mean model calls per question | {report.mean_provider_calls:.2f} |",
        f"| Mean prompt / completion tokens per question | {report.mean_prompt_tokens:.0f} / "
        f"{report.mean_completion_tokens:.0f} |",
        "",
        "### Safety suite",
        "",
        "| Metric | Result |",
        "| --- | --- |",
        f"| Unsafe statements blocked by the guard | "
        f"{safety.unsafe_blocked} / {safety.unsafe_total} |",
        f"| Safe statements allowed by the guard | {safety.safe_allowed} / {safety.safe_total} |",
        f"| Unsafe statements the read-only engine rejects on its own | "
        f"{safety.engine_alone_blocked} / {safety.unsafe_total} |",
        "",
        "### Per-question results",
        "",
        "| Question | Difficulty | Status | Correct | Attempts | Latency |",
        "| --- | --- | --- | --- | --- | --- |",
    ]
    for case in report.cases:
        mark = "yes" if case.correct else "no"
        if case.correct and not case.correct_strict:
            mark = "yes (extra cols)"
        lines.append(
            f"| {case.question} | {case.difficulty} | {case.status} | {mark} | "
            f"{case.attempts} | {_ms(case.latency_ms)} |"
        )
    return "\n".join(lines) + "\n"


def _ms(value: float) -> str:
    return f"{value / 1000:.2f} s" if value >= 1000 else f"{value:.1f} ms"


def save_json(report: EvalReport, path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(report.model_dump(), indent=2) + "\n", encoding="utf-8")
