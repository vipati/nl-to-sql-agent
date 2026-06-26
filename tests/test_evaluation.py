from nl_to_sql_agent.evaluation import load_cases, run_evaluation


def test_load_cases() -> None:
    cases = load_cases()

    assert len(cases) == 3
    assert cases[0].id == "revenue_by_customer"


def test_run_evaluation_reports_accuracy() -> None:
    report = run_evaluation()

    assert report.total == 3
    assert report.generation_success_rate == 1.0
    assert report.sql_validity_rate == 1.0
    assert report.execution_success_rate == 1.0
    assert report.result_accuracy_rate == 1.0

