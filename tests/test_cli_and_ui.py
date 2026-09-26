from pathlib import Path

from streamlit.testing.v1 import AppTest
from typer.testing import CliRunner

from nl_to_sql_agent.cli import app

runner = CliRunner()
APP_PATH = Path(__file__).resolve().parents[1] / "app" / "streamlit_app.py"


def test_cli_ask() -> None:
    result = runner.invoke(app, ["ask", "How many orders are there in each status?"])

    assert result.exit_code == 0, result.output
    assert "status: ok" in result.output
    assert "completed" in result.output


def test_cli_sql_blocks_unsafe_sql() -> None:
    result = runner.invoke(app, ["sql", "DELETE FROM orders"])

    assert result.exit_code == 1
    assert "status: blocked" in result.output


def test_cli_schema() -> None:
    result = runner.invoke(app, ["schema"])

    assert "CREATE TABLE order_items" in result.output


def test_cli_eval_writes_reports(tmp_path: Path) -> None:
    output = tmp_path / "eval.md"
    json_output = tmp_path / "eval.json"

    result = runner.invoke(
        app, ["eval", "--output", str(output), "--json", str(json_output), "--min-accuracy", "0.3"]
    )

    assert result.exit_code == 0, result.output
    assert "Execution accuracy" in output.read_text(encoding="utf-8")
    assert json_output.exists()


def test_cli_eval_enforces_min_accuracy() -> None:
    result = runner.invoke(app, ["eval", "--min-accuracy", "0.99"])

    assert result.exit_code == 1


def test_streamlit_app_renders_an_answer_and_a_blocked_query() -> None:
    at = AppTest.from_file(str(APP_PATH), default_timeout=30).run()

    assert not at.exception
    assert [metric.value for metric in at.metric][:2] == ["ok", "1"]
    assert "blocked" in [metric.value for metric in at.metric]
    assert any("Exactly one statement" in error.value for error in at.error)
