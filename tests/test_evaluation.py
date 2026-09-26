import pytest

from nl_to_sql_agent.agent import Agent
from nl_to_sql_agent.database import QueryResult
from nl_to_sql_agent.evaluation import (
    load_cases,
    render_markdown,
    results_match,
    run_evaluation,
)
from nl_to_sql_agent.guard import check_sql
from nl_to_sql_agent.providers import RulesProvider

from .conftest import ScriptedProvider


def result(columns: list[str], rows: list[list]) -> QueryResult:
    return QueryResult(columns=columns, rows=rows, row_count=len(rows))


GOLD = result(["name", "total"], [["Ann", 10.0], ["Bob", 5.5]])


@pytest.mark.parametrize(
    "predicted, ordered, expected",
    [
        (result(["a", "b"], [["Ann", 10.0], ["Bob", 5.5]]), True, True),
        (result(["a", "b"], [["Bob", 5.5], ["Ann", 10.0]]), False, True),
        (result(["a", "b"], [["Bob", 5.5], ["Ann", 10.0]]), True, False),
        (result(["b", "a"], [[10, "Ann"], [5.499, "Bob"]]), True, True),  # order + rounding
        (result(["a", "b", "c"], [["Ann", 10.0, 1], ["Bob", 5.5, 2]]), True, True),  # extra col
        (result(["a"], [["Ann"], ["Bob"]]), True, False),  # missing column
        (result(["a", "b"], [["Ann", 10.0]]), True, False),  # missing row
        (result(["a", "b"], [["Ann", 5.5], ["Bob", 10.0]]), False, False),  # wrong pairing
    ],
)
def test_results_match(predicted: QueryResult, ordered: bool, expected: bool) -> None:
    assert results_match(predicted, GOLD, ordered=ordered) is expected


def test_gold_sql_is_valid_and_deterministic(database) -> None:
    cases = load_cases()

    assert len(cases) >= 25
    assert len({case.id for case in cases}) == len(cases)
    for case in cases:
        assert check_sql(case.gold_sql, database.schema).ok, case.id
        assert database.execute(case.gold_sql).row_count > 0, case.id


def test_gold_sql_scores_100_percent(database) -> None:
    cases = load_cases()
    agent = Agent(ScriptedProvider([case.gold_sql for case in cases]), database)

    report = run_evaluation(agent, cases=cases)

    assert report.execution_accuracy == 1.0
    assert report.execution_accuracy_strict == 1.0
    assert report.valid_sql_rate == 1.0


def test_rules_baseline_report(database) -> None:
    report = run_evaluation(Agent(RulesProvider(), database))

    # The rules baseline is a keyword matcher: it answers some questions and declines the rest.
    assert 0.3 <= report.execution_accuracy < 0.7
    assert report.unsafe_generated == 0
    assert report.safety.passed
    assert report.safety.unsafe_blocked == report.safety.unsafe_total
    assert report.safety.engine_alone_blocked < report.safety.unsafe_total
    markdown = render_markdown(report)
    assert "Execution accuracy" in markdown
    assert "Unsafe statements blocked by the guard" in markdown
