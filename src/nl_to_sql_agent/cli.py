import typer

from nl_to_sql_agent.evaluation import run_evaluation
from nl_to_sql_agent.generator import generate_sql
from nl_to_sql_agent.repair import execute_with_repair
from nl_to_sql_agent.schema import ecommerce_schema
from nl_to_sql_agent.validator import validate_sql

app = typer.Typer(help="Generate validated SQL from natural-language questions.")


@app.command()
def generate(question: str, execute: bool = typer.Option(False, help="Run generated SQL.")) -> None:
    """Generate SQL for a natural-language question."""
    sql = generate_sql(question, ecommerce_schema())
    validation = validate_sql(sql)

    typer.echo(sql)
    if not validation.valid:
        raise typer.BadParameter(f"Generated SQL is invalid: {validation.error}")

    if execute:
        attempt = execute_with_repair(sql)
        if not attempt.executed or not attempt.execution:
            raise typer.BadParameter(f"SQL execution failed: {attempt.error}")
        if attempt.changed:
            typer.echo("")
            typer.echo(f"Repaired SQL: {attempt.repaired_sql}")
        result = attempt.execution
        typer.echo("")
        typer.echo(f"Rows: {result.row_count}")
        for row in result.rows:
            typer.echo(row)


@app.command()
def repair(sql: str) -> None:
    """Attempt to repair and execute SQL."""
    attempt = execute_with_repair(sql)
    typer.echo(f"Original SQL: {attempt.original_sql}")
    typer.echo(f"Repaired SQL: {attempt.repaired_sql}")
    typer.echo(f"Changed: {attempt.changed}")
    typer.echo(f"Executed: {attempt.executed}")
    if attempt.error:
        typer.echo(f"Error: {attempt.error}")
    if attempt.execution:
        typer.echo(f"Rows: {attempt.execution.row_count}")
        for row in attempt.execution.rows:
            typer.echo(row)


@app.command(name="eval")
def evaluate() -> None:
    """Run the NL-to-SQL evaluation suite."""
    report = run_evaluation()
    typer.echo(f"Total cases: {report.total}")
    typer.echo(f"Generation success: {report.generation_success_rate:.0%}")
    typer.echo(f"SQL validity: {report.sql_validity_rate:.0%}")
    typer.echo(f"Execution success: {report.execution_success_rate:.0%}")
    typer.echo(f"Result accuracy: {report.result_accuracy_rate:.0%}")

    failed = [case for case in report.cases if not case.correct_result]
    if failed:
        raise typer.Exit(code=1)


if __name__ == "__main__":
    app()
