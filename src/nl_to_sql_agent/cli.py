import dataclasses
from pathlib import Path
from typing import Any

import typer

from nl_to_sql_agent.agent import Agent, AgentResult
from nl_to_sql_agent.config import Settings
from nl_to_sql_agent.evaluation import CaseResult, render_markdown, run_evaluation, save_json
from nl_to_sql_agent.schema import format_schema_context

app = typer.Typer(help="Ask questions of a database in plain English, safely.")

ProviderOption = typer.Option(None, help="Override NL2SQL_PROVIDER: 'rules' or 'openai'.")
ModelOption = typer.Option(None, help="Override NL2SQL_MODEL.")
OutputOption = typer.Option(None, help="Write the Markdown report here.")
JsonOption = typer.Option(None, "--json", help="Write the full JSON report.")
MinAccuracyOption = typer.Option(
    0.0, help="Exit non-zero if execution accuracy is below this fraction (for CI)."
)


def _agent(provider: str | None = None, model: str | None = None) -> tuple[Agent, Settings]:
    settings = Settings.from_env()
    overrides = {"provider": provider, "model": model}
    settings = dataclasses.replace(settings, **{k: v for k, v in overrides.items() if v})
    return Agent.from_settings(settings), settings


@app.command()
def ask(
    question: str,
    provider: str | None = ProviderOption,
    model: str | None = ModelOption,
) -> None:
    """Answer a question: generate SQL, check it, run it, and print the result."""
    agent, _ = _agent(provider, model)
    _print_result(agent.ask(question))


@app.command()
def sql(query: str) -> None:
    """Run your own SQL through the same guard and read-only executor."""
    agent, _ = _agent()
    _print_result(agent.run_sql(query))


@app.command()
def schema() -> None:
    """Print the schema context the model sees."""
    agent, _ = _agent()
    typer.echo(format_schema_context(agent.database.schema))


@app.command(name="eval")
def evaluate(
    provider: str | None = ProviderOption,
    model: str | None = ModelOption,
    output: Path | None = OutputOption,
    json_output: Path | None = JsonOption,
    min_accuracy: float = MinAccuracyOption,
) -> None:
    """Run the gold-question evaluation and the safety suite."""
    agent, settings = _agent(provider, model)

    def progress(case: CaseResult) -> None:
        mark = "PASS" if case.correct else "FAIL"
        typer.echo(f"  {mark}  {case.status:<15} {case.latency_ms:8.1f} ms  {case.question}")

    report = run_evaluation(
        agent, model=settings.model if agent.provider.name != "rules" else None, progress=progress
    )
    markdown = render_markdown(report)
    typer.echo("")
    typer.echo(markdown)
    if output:
        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_text(markdown, encoding="utf-8")
    if json_output:
        save_json(report, json_output)

    if not report.safety.passed:
        typer.echo("Safety suite failed.", err=True)
        raise typer.Exit(code=1)
    if report.execution_accuracy < min_accuracy:
        typer.echo(
            f"Execution accuracy {report.execution_accuracy:.0%} is below {min_accuracy:.0%}.",
            err=True,
        )
        raise typer.Exit(code=1)


def _print_result(result: AgentResult) -> None:
    for index, attempt in enumerate(result.attempts, start=1):
        typer.echo(f"[{index}] {attempt.stage}: {attempt.sql}")
        if attempt.error:
            typer.echo(f"    {attempt.error_kind} error: {attempt.error}")
    typer.echo(f"status: {result.status} ({result.latency_ms:.1f} ms)")
    if result.status != "ok":
        if result.error and not result.attempts:
            typer.echo(result.error)
        raise typer.Exit(code=1)
    if result.result:
        typer.echo("")
        typer.echo(_format_table(result.result.columns, result.result.rows))
        suffix = " (truncated)" if result.result.truncated else ""
        typer.echo(f"({result.result.row_count} rows{suffix})")


def _format_table(columns: list[str], rows: list[list[Any]], max_rows: int = 20) -> str:
    cells = [[_cell(value) for value in row] for row in rows[:max_rows]]
    widths = [
        max([len(column)] + [len(row[index]) for row in cells])
        for index, column in enumerate(columns)
    ]
    lines = [
        "  ".join(column.ljust(width) for column, width in zip(columns, widths, strict=True)),
        "  ".join("-" * width for width in widths),
    ]
    lines += ["  ".join(c.ljust(w) for c, w in zip(row, widths, strict=True)) for row in cells]
    if len(rows) > max_rows:
        lines.append(f"... {len(rows) - max_rows} more rows")
    return "\n".join(lines)


def _cell(value: Any) -> str:
    if isinstance(value, float):
        return f"{value:,.2f}"
    return "NULL" if value is None else str(value)


if __name__ == "__main__":
    app()
